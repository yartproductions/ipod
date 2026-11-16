#!/usr/bin/env python3
"""Flow track list: the hovered album's songs slide in on the right; spinning slides them away.
Run: python3 tests/flow_tracklist.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox'], viewport={'width': 390, 'height': 844}, device_scale_factor=2, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('*.mp3'))); pg.wait_for_timeout(4000); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow'); pg.wait_for_timeout(800)
        multi = None
        for _ in range(12):
            pg.wait_for_timeout(650)
            if pg.evaluate("document.getElementById('flow').classList.contains('withpanel')"): multi = pg.text_content('#fal'); break
            C.key(pg, 'ArrowDown', wait=60)
        check('settling on a multi-song album slides its track list in', multi is not None)
        rows = pg.eval_on_selector_all('.fpanel div span', 'e=>e.map(x=>x.textContent)')
        check('the list shows that album’s songs', len(rows) >= 2, rows)
        check('header counts the songs', 'songs' in pg.inner_text('.fpanel h4').lower())
        pg.screenshot(path='/tmp/shots/flow-panel.png', clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowUp', wait=80)
        check('spinning slides it away at once', not pg.evaluate("document.getElementById('flow').classList.contains('withpanel')"))
        pg.screenshot(path='/tmp/shots/flow-panel-out.png', clip=pg.locator('#screen').bounding_box())
        single = pg.text_content('#fal'); pg.wait_for_timeout(700)
        album_size = pg.evaluate("(()=>{const t=document.getElementById('fal').textContent;const ar=document.getElementById('far').textContent;return ipodListenBridge.songs().filter(s=>s.album===t&&s.artist===ar).length})()")
        check('single-song albums keep the full shelf', pg.evaluate("document.getElementById('flow').classList.contains('withpanel')") == (album_size >= 2), (single, album_size))
        C.key(pg, 'ArrowDown', wait=80); pg.wait_for_timeout(700)
        check('settling again brings it back', pg.evaluate("document.getElementById('flow').classList.contains('withpanel')"))
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Flow Track List')
        C.home(pg); C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow')
        for _ in range(12):
            if pg.text_content('#fal') == multi: break
            C.key(pg, 'ArrowDown', wait=60)
        pg.wait_for_timeout(800)
        check('it can be turned off in Settings', not pg.evaluate("document.getElementById('flow').classList.contains('withpanel')"))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
