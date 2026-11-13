#!/usr/bin/env python3
"""Update prompt + What's New checks.  Run: python3 tests/updates.py
Serves a temporary copy of the site, "publishes" a new version by editing that copy mid-test, and replaces
GitHub's commits API with a stand-in that returns invented commit history."""
import functools, http.server, json, os, shutil, socketserver, sys, tempfile, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CHROME = os.environ.get('CHROME', '/usr/bin/google-chrome')
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (f'  [{detail}]' if detail and not cond else ''))

COMMITS = [   # newest first, first-parent chain c3 -> c2 -> c1, plus a branch commit b1 that must be skipped
    {'sha': 'c3', 'parents': [{'sha': 'c2'}, {'sha': 'b1'}], 'commit': {'message': 'Merge pull request #30 from x/feature\n\nShiny new feature for testing', 'committer': {'date': '2026-11-13T15:00:00Z'}}},
    {'sha': 'b1', 'parents': [{'sha': 'c2'}], 'commit': {'message': 'wip branch commit that should not show', 'committer': {'date': '2026-11-13T14:00:00Z'}}},
    {'sha': 'c2', 'parents': [{'sha': 'c1'}], 'commit': {'message': 'Direct fix pushed to main', 'committer': {'date': '2026-11-12T10:00:00Z'}}},
    {'sha': 'c1', 'parents': [], 'commit': {'message': 'Merge pull request #29 from x/older\n\nOlder feature', 'committer': {'date': '2026-11-01T10:00:00Z'}}},
]
api_calls = []
def gh_route(route):
    api_calls.append(route.request.url)
    route.fulfill(status=200, content_type='application/json', body=json.dumps(COMMITS), headers={'Access-Control-Allow-Origin': '*'})

def main():
    site = Path(tempfile.mkdtemp())
    for f in ROOT.iterdir():
        if f.name in ('.git', 'tests', 'audio-api', 'worker', 'ios'): continue
        (shutil.copytree if f.is_dir() else shutil.copy2)(f, site / f.name)
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_address[1]}/'
    errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=CHROME, headless=True, args=['--no-sandbox'], viewport={'width': 390, 'height': 844})
        ctx.route('https://**', lambda r: r.abort())
        ctx.route('https://api.github.com/**', gh_route)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(2500)
        key = lambda k, n=1, w=120: [ (pg.keyboard.press(k), pg.wait_for_timeout(w)) for _ in range(n)]
        sheet_on = lambda: 'on' in (pg.get_attribute('#sheet', 'class') or '')

        check('no prompt when nothing new was published', not sheet_on())
        check('first launch does not show What’s New', not sheet_on())

        # publish a "new version"
        idx = site / 'index.html'; idx.write_text(idx.read_text() + '\n<!-- new build -->\n')
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_timeout(1500)
        check('new version detected → Update Available frame', sheet_on() and pg.text_content('#sheetT') == 'Update Available', pg.text_content('#sheetT'))
        body = pg.inner_text('#sheetIn')
        check('frame lists the latest changes (PR titles + direct commits)', 'Shiny new feature for testing' in body and 'Direct fix pushed to main' in body, body)
        w=pg.evaluate("document.querySelector('#sheetIn p').getBoundingClientRect().width")
        check('frame text is actually visible (has width)', w>100, w)
        check('frame stays short and points to What’s New for the rest', 'more change' in body and 'Older feature' not in body, body)
        check('branch work-in-progress commits are not listed', 'wip branch commit' not in body)
        check('buttons: Update Now / Later', pg.eval_on_selector_all('#sheetBtns .bt', 'e=>e.map(x=>x.textContent)') == ['Update Now', 'Later'])
        key('ArrowDown')
        check('wheel moves between the buttons', 'sel' in pg.get_attribute('#sheetBtns .bt:nth-child(2)', 'class'))
        before = pg.text_content('#htitle')
        key('ArrowRight')
        check('other buttons are blocked while the frame is up', sheet_on() and pg.text_content('#htitle') == before)
        key('Escape', w=300)
        check('MENU = Later (frame closes)', not sheet_on())
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_timeout(1200)
        check('Later is remembered for this version (no nagging)', not sheet_on())

        # manual check, then Update Now via tap
        pg.evaluate("1")
        for _ in range(15): pg.keyboard.press('ArrowUp')
        def choose(label):
            for _ in range(30):
                if pg.eval_on_selector('#body .row.sel', 'e=>(e.querySelector(".lt")||e).textContent.trim()') == label: key('Enter', w=400); return
                pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(20)
            raise AssertionError(label)
        choose('About'); choose('Check for Updates'); pg.wait_for_timeout(1200)
        check('About ▸ Check for Updates shows the frame again', sheet_on())
        with pg.expect_navigation(timeout=10000):
            pg.click('#sheetBtns .bt:first-child')
        pg.wait_for_timeout(2500)
        check('Update Now reloads into the new version', pg.evaluate("[...document.querySelectorAll('*'),document].some(n=>[...n.childNodes].some(c=>c.nodeType===8&&c.data.includes('new build')))"))
        check('What’s New appears automatically after updating', sheet_on() and pg.text_content('#sheetT') == 'What’s New', pg.text_content('#sheetT'))
        check('What’s New lists the changes', 'Shiny new feature for testing' in pg.inner_text('#sheetIn'))
        key('Enter', w=300)
        check('center closes What’s New', not sheet_on())
        pg.reload(); pg.wait_for_timeout(2500)
        check('What’s New is shown only once per update', not sheet_on())
        choose('About'); choose('What’s New'); pg.wait_for_timeout(800)
        check('About ▸ What’s New shows the full changelog anytime', sheet_on() and 'Older feature' in pg.inner_text('#sheetIn'), (sheet_on(), pg.text_content('#sheetT'), pg.inner_text('#sheetIn')[:200], pg.text_content('#htitle')))
        key('Escape', w=300)
        choose('Check for Updates'); pg.wait_for_timeout(1000)
        check('up to date → message, no frame', not sheet_on() and 'Up to Date' in pg.inner_text('#body'))

        # styling: Classic vs Modern Light/Dark
        pg.evaluate("localStorage.setItem('ipod.settings',JSON.stringify(Object.assign(JSON.parse(localStorage.getItem('ipod.settings')||'{}'),{style:'Modern',appearance:'Dark'})))")
        pg.reload(); pg.wait_for_timeout(2000)
        idx.write_text(idx.read_text() + '\n<!-- build 3 -->\n')
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_timeout(1500)
        bg = pg.evaluate('getComputedStyle(document.querySelector("#sheet .card")).backgroundColor')
        radius = pg.evaluate('getComputedStyle(document.querySelector("#sheet .card")).borderRadius')
        check('Modern Dark frame: dark rounded card', sheet_on() and bg == 'rgb(27, 37, 51)' and radius == '14px', (bg, radius))
        pg.screenshot(path=str(Path(tempfile.gettempdir()) / 'upd-modern-dark.png'))
        key('Escape', w=200)
        pg.evaluate("localStorage.setItem('ipod.settings',JSON.stringify(Object.assign(JSON.parse(localStorage.getItem('ipod.settings')),{appearance:'Light'})))")
        pg.reload(); pg.wait_for_timeout(2000); pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_timeout(1500)
        if pg.text_content('#sheetT') == 'What’s New': key('Escape', w=200); pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_timeout(1200)
        bg = pg.evaluate('getComputedStyle(document.querySelector("#sheet .card")).backgroundColor')
        check('Modern Light frame: white card', bg == 'rgb(255, 255, 255)', bg)
        pg.screenshot(path=str(Path(tempfile.gettempdir()) / 'upd-modern-light.png'))
        check('no uncaught page errors', not errors, errors)
        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} passed'); sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
