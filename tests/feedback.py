#!/usr/bin/env python3
"""Feedback & Ideas: private bug reports with diagnostics, a shared idea board with upvotes.
Firebase is replaced by tests/fake-firebase.js shared between two tabs.  Run: python3 tests/feedback.py"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-firebase.js').read_text()
def docs(pg): return pg.evaluate("Object.keys(localStorage).filter(k=>/^fakefs:feedback\\/[^/]+$/.test(k)).map(k=>JSON.parse(localStorage.getItem(k)))")
def open_fb(pg): C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Feedback & Ideas')

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--disable-background-timer-throttling', '--disable-renderer-backgrounding'], viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        ctx.route('https://www.gstatic.com/firebasejs/**', lambda r: r.fulfill(status=200, content_type='text/javascript',
                  body=FAKE if 'app-compat' in r.request.url else '/* fake */'))
        ctx.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        a = ctx.new_page(); a.on('pageerror', lambda e: errors.append('a: ' + str(e))); a.goto(url); a.wait_for_timeout(1200)
        b = ctx.new_page(); b.on('pageerror', lambda e: errors.append('b: ' + str(e))); b.goto(url); b.wait_for_timeout(1200)

        open_fb(a)
        check('Settings ▸ Feedback & Ideas has the four entries', C.all_rows(a) == ['Report a Bug', 'Suggest an Idea', 'Idea Board', 'My Reports'], C.all_rows(a))
        C.choose(a, 'Report a Bug'); a.fill('#inpt', 'x'); C.key(a, 'Enter', wait=600)
        check('too-short reports are refused kindly', 'Couldn’t Send' in a.text_content('#htitle'))
        C.key(a, 'Escape', wait=200); C.choose(a, 'Report a Bug')
        a.fill('#inpt', 'The lyrics froze after skipping twice'); C.key(a, 'Enter', wait=800)
        check('a bug report is sent', a.text_content('#htitle') == 'Thanks for the Report')
        d = [x for x in docs(a) if x['kind'] == 'bug']
        diag = json.loads(d[0]['diag']) if d else {}
        check('it carries device details for reproducing it', d and 'ua' in diag and 'screen' in diag and diag.get('songs') == 0, diag)
        open_fb(a); C.choose(a, 'Suggest an Idea'); a.fill('#inpt', 'Let me pick a custom body color'); C.key(a, 'Enter', wait=800)
        check('an idea is posted', a.text_content('#htitle') == 'Idea Posted')
        check('ideas don’t carry device details', [x for x in docs(a) if x['kind'] == 'idea'][0]['diag'] == '')

        open_fb(b); C.choose(b, 'Idea Board'); b.wait_for_timeout(800)
        body = b.inner_text('#body')
        check('another listener sees the idea on the board', 'custom body color' in body and '△ 0' in body, body)
        check('…but not the private bug report', 'lyrics froze' not in body)
        C.choose(b, C.all_rows(b)[0]); C.choose(b, 'Upvote'); b.wait_for_timeout(500)
        check('they can upvote it', '▲ 1' in b.inner_text('#body'), b.inner_text('#body'))
        b.screenshot(path='/tmp/shots/idea.png', clip=b.locator('#screen').bounding_box())
        C.choose(b, 'Remove My Vote'); b.wait_for_timeout(400); C.choose(b, 'Upvote'); b.wait_for_timeout(400)
        check('one vote each (toggle)', '▲ 1' in b.inner_text('#body'))
        open_fb(a); C.choose(a, 'Idea Board'); a.wait_for_timeout(800)
        check('the author sees the vote', '1' in a.inner_text('#body') and 'custom body color' in a.inner_text('#body'), a.inner_text('#body'))
        a.screenshot(path='/tmp/shots/idea-board.png', clip=a.locator('#screen').bounding_box())
        open_fb(a); C.choose(a, 'My Reports'); a.wait_for_timeout(700)
        check('My Reports lists both of mine', 'lyrics froze' in a.inner_text('#body') and 'custom body' in a.inner_text('#body'), a.inner_text('#body'))
        open_fb(b); C.choose(b, 'My Reports'); b.wait_for_timeout(700)
        check('other people’s reports aren’t in mine', 'Nothing sent yet' in b.inner_text('#body'), b.inner_text('#body'))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
