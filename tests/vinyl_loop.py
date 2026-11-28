#!/usr/bin/env python3
"""Wind the record to loop: drag around the vinyl in Now Playing to charge it, let go and it whirls,
toggling Repeat One with an animation.   Run: python3 tests/vinyl_loop.py"""
import sys, math, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-native-player.js').read_text()
def wind(pg, turns, start=0, ccw=False):
    b = pg.locator('#np .vinyl-record').bounding_box(); cx, cy = b['x'] + b['width'] / 2, b['y'] + b['height'] / 2
    r = pg.evaluate("document.querySelector('#np .vinyl-record').offsetWidth") * .4
    a = start; pt = lambda a: (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
    pg.mouse.move(*pt(a)); pg.mouse.down()
    for _ in range(int(turns * 360 / 12)):
        a += -12 if ccw else 12; pg.mouse.move(*pt(a)); pg.wait_for_timeout(8)
    pg.mouse.up()
state = lambda pg: pg.evaluate("({rep:JSON.parse(localStorage.getItem('ipod.settings')).repeat,nat:window.__native.player.repeat,loop:document.getElementById('np').classList.contains('vinyl-loop'),"
                               "fx:document.querySelector('#np .vinyl-jacket').className,whirl:!!document.querySelector('#np .vinyl-whirl')})")
srv, url = C.serve(); errors = []
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True, args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'],
          viewport={'width': 390, 'height': 844}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort())
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,accel:false,repeat:'All'}))")
    pg.add_init_script(FAKE)
    pg.goto(url); pg.wait_for_timeout(1200)
    pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('*.mp3'))); pg.wait_for_timeout(4000); C.wait_sync(pg)
    pg.wait_for_function("window.__native.files.size>=5", timeout=30000); pg.wait_for_timeout(1500)
    C.home(pg); C.choose(pg, C.music_label(pg)); C.choose(pg, 'Songs'); C.key(pg, 'Enter', wait=2200)
    check('setup: Now Playing shows the record', pg.locator('#np .vinyl-record').count() == 1)
    b = pg.locator('#np .vinyl-record').bounding_box(); pg.mouse.click(b['x'] + b['width'] * .8, b['y'] + b['height'] / 2); pg.wait_for_timeout(300)
    check('a tap on the record does nothing', state(pg)['rep'] == 'All', state(pg))
    wind(pg, .35); pg.wait_for_timeout(300)
    check('a short wind isn’t enough: loop stays off', state(pg)['rep'] == 'All', state(pg))
    wind(pg, 1.2); pg.wait_for_timeout(120)
    S = state(pg)
    check('a full wind turns loop on (Repeat One)', S['rep'] == 'One', S)
    check('…in the native player too', S['nat'] == 'One', S)
    check('the record whirls after you let go', S['whirl'], S)
    check('the loop-on animation plays', 'fx-on' in S['fx'], S)
    pg.wait_for_timeout(250); pg.screenshot(path='/tmp/vinyl-loop-on.png', clip=pg.locator('#screen').bounding_box())
    pg.wait_for_timeout(4200); S = state(pg)
    check('it settles back to the normal spin, with a loop badge on the record', not S['whirl'] and S['loop'] and 'fx-on' not in S['fx'], S)
    check('…and the badge is visible', pg.evaluate("getComputedStyle(document.querySelector('#np .vinyl-badge')).opacity") == '1')
    pg.screenshot(path='/tmp/vinyl-loop-badge.png', clip=pg.locator('#screen').bounding_box())
    wind(pg, 1.2, ccw=True); pg.wait_for_timeout(120); S = state(pg)
    check('winding again (either way) turns loop off, back to Repeat All', S['rep'] == 'All' and S['nat'] == 'All' and 'fx-off' in S['fx'] and not S['loop'], S)
    pg.wait_for_timeout(200); pg.screenshot(path='/tmp/vinyl-loop-off.png', clip=pg.locator('#screen').bounding_box())
    pg.wait_for_timeout(4000)
    C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Style')
    C.home(pg); C.choose(pg, C.music_label(pg)); C.choose(pg, 'Songs'); C.key(pg, 'Enter', wait=2200)
    wind(pg, 1.2); pg.wait_for_timeout(150)
    check('works in the Modern Now Playing too', state(pg)['rep'] == 'One', state(pg))
    check('no page errors', not errors, errors)
    ctx.close()
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
