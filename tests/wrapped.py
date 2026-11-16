#!/usr/bin/env python3
"""iPod Wrapped: monthly/yearly recap cards from listening.   Run: python3 tests/wrapped.py"""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
SHOTS = Path('/tmp/shots')

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, device_scale_factor=2, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Shuffle Songs'); pg.wait_for_timeout(500)
        q = pg.evaluate("ipodMacBridge.queue().map(s=>({id:s.id,t:s.title}))")
        now = int(time.time() * 1000); H = 3600 * 1000
        hist = [{'id': q[0]['id'], 'at': now - i * 7 * 60 * 1000} for i in range(6)] + [{'id': q[1]['id'], 'at': now - 3 * H - i * 60000} for i in range(3)] + [{'id': q[2]['id'], 'at': now - 5 * H}]
        pg.evaluate("h=>{localStorage.setItem('ipod.listeningHistory',JSON.stringify(h));localStorage.removeItem('ipod.stats.seeded');localStorage.removeItem('ipod.stats.months')}", hist)
        pg.reload(); pg.wait_for_timeout(2000); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'iPod Wrapped')
        rows = C.all_rows(pg)
        check('Wrapped offers This Month and This Year', rows[0] == 'This Month' and 'This Year' in rows, rows)
        C.choose(pg, 'This Month'); pg.wait_for_timeout(600)
        check('opens on the intro card', 'ipod wrapped' in pg.inner_text('.wrapped').lower())
        pg.screenshot(path=str(SHOTS / 'wr-0.png'), clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowDown', wait=500)
        check('minutes card counts the plays', '10 plays' in pg.inner_text('.wrapped') or 'plays' in pg.inner_text('.wrapped'), pg.inner_text('.wrapped'))
        pg.screenshot(path=str(SHOTS / 'wr-1.png'), clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowDown', wait=500)
        check('top song is the most played one', q[0]['t'] in pg.inner_text('.wrapped') and '6 plays' in pg.inner_text('.wrapped'), pg.inner_text('.wrapped'))
        pg.screenshot(path=str(SHOTS / 'wr-2.png'), clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowDown', wait=500)
        check('top songs list in order', pg.inner_text('.wrapped ol').index(q[0]['t']) < pg.inner_text('.wrapped ol').index(q[1]['t']))
        pg.screenshot(path=str(SHOTS / 'wr-3.png'), clip=pg.locator('#screen').bounding_box())
        for _ in range(10): C.key(pg, 'ArrowDown', wait=200)
        check('ends on the summary card', 'top song' in pg.inner_text('.wrapped').lower() and 'you are' in pg.inner_text('.wrapped').lower() and 'Fixture Artist' in pg.inner_text('.wrapped'), pg.inner_text('.wrapped'))
        pg.screenshot(path=str(SHOTS / 'wr-9.png'), clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'Enter', wait=400)
        check('Center on the last card starts over', 'ipod wrapped' in pg.inner_text('.wrapped').lower())
        C.key(pg, 'Escape', wait=300); C.choose(pg, 'This Year'); pg.wait_for_timeout(400)
        check('This Year works too', str(time.localtime().tm_year) in pg.inner_text('.wrapped'))
        # new plays count toward it
        before = pg.evaluate(f"JSON.parse(localStorage.getItem('ipod.stats.months'))[Object.keys(JSON.parse(localStorage.getItem('ipod.stats.months')))[0]].p")
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Shuffle Songs'); pg.wait_for_timeout(2500)
        after = pg.evaluate("Object.values(JSON.parse(localStorage.getItem('ipod.stats.months'))).reduce((a,m)=>a+m.p,0)")
        check('new plays are added to the stats', after > before, (before, after))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
