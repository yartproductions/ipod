#!/usr/bin/env python3
"""Flow panel: while you spin it lists the whole Flow (your spot highlighted); when you stop it shows what's
inside that cover (track list, or a song's details).   Run: python3 tests/flow_tracklist.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
panel = lambda pg: pg.evaluate("(()=>{const f=document.getElementById('flow'),p=f&&f.querySelector('.fpanel');return {shown:!!f&&f.classList.contains('withpanel'),inside:!!p&&p.classList.contains('inside'),head:p?p.querySelector('h4')?.textContent||'':'',on:p?p.querySelector('div.on span')?.textContent||'':''}})()")

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
        C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow'); pg.wait_for_timeout(200)
        C.key(pg, 'ArrowDown', wait=120)
        x = panel(pg)
        check('while spinning the panel lists the whole Flow', x['shown'] and not x['inside'] and 'Album Flow' in x['head'], x)
        check('…with the cover you’re on highlighted', x['on'] == pg.text_content('#fal'), (x['on'], pg.text_content('#fal')))
        pg.screenshot(path='/tmp/shots/flow-list.png', clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowDown', wait=120)
        check('the highlight follows the wheel', panel(pg)['on'] == pg.text_content('#fal'))
        pg.wait_for_timeout(900); x = panel(pg)
        check('when you stop it switches to what’s inside', x['shown'] and x['inside'], x)
        pg.screenshot(path='/tmp/shots/flow-inside.png', clip=pg.locator('#screen').bounding_box())
        multi = None
        for _ in range(12):
            if 'songs' in panel(pg)['head'].lower() and panel(pg)['inside']: multi = pg.text_content('#fal'); break
            C.key(pg, 'ArrowDown', wait=60); pg.wait_for_timeout(900)
        check('a multi-song album shows its track list', multi is not None)
        rows = pg.eval_on_selector_all('.fpanel div span', 'e=>e.map(x=>x.textContent)')
        check('…with its songs', len(rows) >= 2, rows)
        C.key(pg, 'ArrowUp', wait=100)
        check('spinning again goes back to the Flow list', not panel(pg)['inside'] and panel(pg)['shown'])
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Flow Track List')
        C.home(pg); C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow'); C.key(pg, 'ArrowDown', wait=900)
        check('it can be turned off in Settings', not panel(pg)['shown'])
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
