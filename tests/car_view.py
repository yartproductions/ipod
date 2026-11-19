#!/usr/bin/env python3
"""Car View: full-screen player with spinning record, swipes, Car Flow spines, and the feed for the CarPlay widget.
Run: python3 tests/car_view.py"""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
BRIDGE = """window.__np=[];window.webkit={messageHandlers:{ipodNowPlaying:{postMessage:m=>window.__np.push(m)}}};"""
def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 844, 'height': 390}, device_scale_factor=2, service_workers='block', has_touch=True)
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script(BRIDGE)
        pg.add_init_script("if(!sessionStorage.getItem('s')){sessionStorage.setItem('s',1);localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,repeat:'One',glare:'Off',landscape:'Off'}))}")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(500)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Car View'); pg.wait_for_timeout(900)
        cv = pg.locator('#carview')
        check('Car View opens full screen', cv.is_visible() and cv.bounding_box()['width'] == 844)
        check('…with the song and artist', pg.text_content('#cvt').endswith('Track') and pg.text_content('#cva') == 'Fixture Artist', (pg.text_content('#cvt'), pg.text_content('#cva')))
        check('…the cover', 'blob:' in pg.evaluate("getComputedStyle(document.getElementById('cvcover')).backgroundImage"))
        spin = pg.evaluate("getComputedStyle(document.getElementById('cvrec')).animationName+'|'+getComputedStyle(document.getElementById('cvrec')).animationPlayState")
        check('…and a spinning record while it plays', spin == 'cvSpin|running', spin)
        v1 = pg.evaluate("getComputedStyle(document.getElementById('carview')).getPropertyValue('--v1')").strip()
        check('the record takes its colors from the cover', v1.startswith('#') and v1 != '', v1)
        pg.wait_for_timeout(1300); pg.screenshot(path='/tmp/shots/carview-np.png')
        t0 = pg.text_content('#cvt')
        def swipe(dx):
            pg.mouse.move(600, 200); pg.mouse.down(); pg.mouse.move(600 + dx / 2, 202); pg.mouse.move(600 + dx, 204); pg.mouse.up(); pg.wait_for_timeout(700)
        swipe(-160)
        t1 = pg.text_content('#cvt')
        check('swiping left plays the next song', t1 != t0, (t0, t1))
        swipe(160)
        check('swiping right goes back', pg.text_content('#cvt') == t0, pg.text_content('#cvt'))
        pg.click('#cvcover'); pg.wait_for_timeout(500)
        st = pg.evaluate("getComputedStyle(document.getElementById('cvrec')).animationPlayState")
        check('tapping the cover pauses, the record stops and slides back', st == 'paused' and 'paused' in cv.get_attribute('class'), st)
        pg.screenshot(path='/tmp/shots/carview-paused.png')
        pg.click('#cvplay'); pg.wait_for_timeout(400)
        check('the play button resumes', pg.evaluate("getComputedStyle(document.getElementById('cvrec')).animationPlayState") == 'running')
        before = pg.text_content('#cvt')
        pg.evaluate("window.ipodRemote('next')"); pg.wait_for_timeout(600)
        check('a CarPlay widget tap (next) changes the song', pg.text_content('#cvt') != before)
        # Car Flow
        pg.click('.cvdock [data-cv="flow"]'); pg.wait_for_timeout(900)
        n = pg.locator('.cvsp').count(); c = pg.locator('.cvsp.c').count()
        check('Car Flow shows the albums as spines around one facing you', n >= 4 and c == 1, (n, c))
        cap0 = pg.text_content('#cvft')
        check('…with the playing album in the middle', cap0 == pg.evaluate("document.getElementById('cvlt').textContent"), cap0)
        pg.screenshot(path='/tmp/shots/carview-flow.png')
        def drag(dx):
            pg.mouse.move(420, 200); pg.mouse.down()
            for k in range(1, 9): pg.mouse.move(420 + dx * k / 8, 200); pg.wait_for_timeout(20)
            pg.mouse.up(); pg.wait_for_timeout(600)
        drag(-160); cap1 = pg.text_content('#cvft')
        if cap1 == cap0: drag(160); drag(160); cap1 = pg.text_content('#cvft')
        check('dragging flips through the albums', cap1 != cap0, (cap0, cap1))
        box = pg.locator('.cvsp.c').bounding_box(); pg.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2); pg.wait_for_timeout(700)
        check('tapping the middle album plays it', pg.evaluate("document.getElementById('carview').dataset.mode") == 'np' and pg.evaluate("document.getElementById('cvlt').textContent") == cap1, pg.evaluate("document.getElementById('cvlt').textContent"))
        # native feed for the CarPlay widget / Live Activity
        pg.wait_for_timeout(1500)
        msgs = pg.evaluate("window.__np")
        last = msgs[-1] if msgs else {}
        check('the iPhone app is sent what’s playing', last.get('title') and last.get('playing') is True and 'artist' in last, {k: last.get(k) for k in ('title', 'playing')})
        withart = [m for m in msgs if m.get('art')]
        check('…with a small cover image', withart and withart[-1]['art'].startswith('data:image/jpeg'))
        withflow = [m for m in msgs if m.get('flow')]
        fl = withflow[-1]['flow'] if withflow else []
        check('…and the Car Flow albums around it, one marked current', len(fl) >= 3 and sum(1 for f in fl if f['current']) == 1 and all(f['art'].startswith('data:image') for f in fl), len(fl))
        cur = [f for f in fl if f['current']][0]; other = [f for f in fl if not f['current']][0]
        pg.evaluate(f"window.ipodRemote('album',{other['index']})"); pg.wait_for_timeout(600)
        check('a CarPlay widget tap on an album plays it', pg.evaluate("document.getElementById('cvlt').textContent") == other['album'], (other['album'], pg.evaluate("document.getElementById('cvlt').textContent")))
        pg.click('.cvdock [data-cv="close"]'); pg.wait_for_timeout(300)
        check('Close returns to the iPod', not cv.is_visible())
        check('the lyrics Live Activity stays off the Lock Screen when not in the car', pg.evaluate("window.__np[window.__np.length-1].live") is False)
        pg.evaluate("window.ipodSetCarPlayRoute(true)"); pg.wait_for_timeout(500)
        check('connecting to CarPlay opens Car View by itself', cv.is_visible())
        check('…and turns on in the car', pg.evaluate("window.__np[window.__np.length-1].live") is True)
        pg.evaluate("window.ipodSetCarPlayRoute(false)"); pg.wait_for_timeout(300)
        check('…and disconnecting closes it', not cv.is_visible())
        check('no page errors', not errors, errors)
    srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
main()
