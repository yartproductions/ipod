#!/usr/bin/env python3
"""Look & Feel: hold switch positions, lock screen with Hold, boot animation, wear & polish, touch ripples, screen glare.
Run: python3 tests/look_feel.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, device_scale_factor=2, service_workers='block', has_touch=True)
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("localStorage.setItem('ipod.settings',JSON.stringify(Object.assign(JSON.parse(localStorage.getItem('ipod.settings')||'{}'),{autoArt:false,repeat:'One'})))")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(500)
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Look & Feel')
        rows = C.all_rows(pg)
        check('Settings has Look & Feel with all the options', all(x in rows for x in ['Hold Switch', 'Lock Screen', 'Boot Animation', 'Wear & Scratches', 'Polish iPod', 'Touch Ripples', 'Screen Glare']), rows)
        # hold switch positions
        def hold_box():
            return pg.evaluate("(()=>{const h=document.getElementById('hold').getBoundingClientRect(),i=document.getElementById('ipod').getBoundingClientRect();return {t:h.top-i.top,b:i.bottom-h.bottom,l:h.left-i.left,r:i.right-h.right}})()")
        b0 = hold_box()
        check('the hold switch starts at the bottom', b0['b'] < 0, b0)
        C.choose(pg, 'Hold Switch'); b1 = hold_box()
        check('…moves to the top left', b1['t'] < 0 and b1['l'] < 80, b1)
        C.choose(pg, 'Hold Switch'); b2 = hold_box()
        check('…the top right', b2['t'] < 0 and b2['r'] < 80, b2)
        C.choose(pg, 'Hold Switch'); b3 = hold_box()
        check('…the left side', b3['l'] < 0, b3)
        C.choose(pg, 'Hold Switch'); b4 = hold_box()
        check('…the right side', b4['r'] < 0, b4)
        pg.screenshot(path='/tmp/shots/hold-right.png')
        pg.reload(); pg.wait_for_timeout(1500)
        check('the position is remembered', hold_box()['r'] < 0)
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Look & Feel'); C.choose(pg, 'Hold Switch')
        check('…and back to the bottom', hold_box()['b'] < 0)
        # lock screen
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(500)
        pg.keyboard.press('h'); pg.wait_for_timeout(500)
        ls = pg.locator('#lockscr')
        check('Hold shows the lock screen', 'on' in ls.get_attribute('class') and ls.evaluate("e=>getComputedStyle(e).opacity") == '1')
        check('…with the time, date and what’s playing', ':' in pg.text_content('#locktime') and len(pg.text_content('#lockdate')) > 5 and pg.text_content('#locktitle') == 'Blue Hour Track', [pg.text_content('#locktime'), pg.text_content('#lockdate'), pg.text_content('#locktitle')])
        cls = pg.evaluate("document.getElementById('screen').className")
        check('…the screen rests a bit dimmer, not dark', 'held' in cls and 'dim' not in cls, cls)
        pg.wait_for_timeout(6200)
        f = pg.evaluate("getComputedStyle(document.getElementById('screen')).filter")
        check('…brightness turned down part-way', 'brightness(0.74)' in f, f)
        pg.evaluate("document.documentElement.classList.add('hdr');const v=document.getElementById('hdrboost');v.classList.add('playing')"); pg.wait_for_timeout(900)
        hd = float(pg.evaluate("getComputedStyle(document.getElementById('hdrboost')).opacity"))
        check('…Bright Screen is turned down but not off', 0.1 < hd < 0.6, hd)
        pg.screenshot(path='/tmp/shots/lockscreen.png', clip=pg.locator('#screen').bounding_box())
        pg.locator('#screen').tap(); pg.wait_for_timeout(900)
        hd2 = float(pg.evaluate("getComputedStyle(document.getElementById('hdrboost')).opacity"))
        check('tapping lights it up fully', 'lit' in pg.evaluate("document.getElementById('screen').className") and hd2 > hd * 2, (hd, hd2))
        check('…while it stays locked', pg.text_content('#htitle') == 'Now Playing' and 'on' in ls.get_attribute('class'))
        pg.wait_for_timeout(5400)
        check('…and settles back down after a few seconds', 'lit' not in pg.evaluate("document.getElementById('screen').className"))
        pg.evaluate("document.documentElement.classList.remove('hdr')")
        pg.keyboard.press('h'); pg.wait_for_timeout(500)
        check('turning Hold off hides the lock screen', 'on' not in (ls.get_attribute('class') or '') and 'held' not in pg.evaluate("document.getElementById('screen').className"))
        # wear
        def wear_px():
            return pg.evaluate("(()=>{const c=document.getElementById('wear'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i]>8)n++;return n})()")
        n0 = wear_px()
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Look & Feel'); C.choose(pg, 'Wear & Scratches')
        pg.wait_for_timeout(300); n = wear_px()
        check('Heavy wear draws far more scratches and dings than a fairly new iPod', n > 1000 and n > n0 * 5, (n0, n))
        pg.screenshot(path='/tmp/shots/wear.png')
        check('…and the iPod shows how worn it is', '100% worn' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, 'Polish iPod'); pg.wait_for_timeout(600)
        pg.screenshot(path='/tmp/shots/polish.png'); pg.wait_for_timeout(1500)
        check('Polish iPod wipes them away', wear_px() == 0, wear_px())
        pg.evaluate("(()=>{const w=JSON.parse(localStorage.getItem('ipod.wear'));w.plays=w.base+175;localStorage.setItem('ipod.wear',JSON.stringify(w))})()")
        pg.reload(); pg.wait_for_timeout(1500); n2 = wear_px()
        check('wear builds up naturally with plays', 50 < n2 < n, (n2, n))
        # ripples
        wb = pg.locator('#wheel').bounding_box()
        pg.mouse.move(wb['x'] + wb['width'] * .5, wb['y'] + 15); pg.mouse.down()
        for i in range(8): pg.mouse.move(wb['x'] + wb['width'] * (.55 + i * .05), wb['y'] + 18 + i * 8); pg.wait_for_timeout(30)
        rips = pg.locator('.rip').count(); rings = pg.locator('.rip.ring').count()
        pg.screenshot(path='/tmp/shots/ripples.png'); pg.mouse.up()
        check('touching the wheel leaves light ripples', rips >= 4 and rings == 1, (rips, rings))
        pg.wait_for_timeout(1000)
        check('…that fade away', pg.locator('.rip').count() == 0)
        # glare
        g = pg.locator('#glare')
        check('Screen Glare is on', g.evaluate("e=>getComputedStyle(e).opacity") == '1')
        pg.evaluate("window.ipodTilt(.5,-.9)"); pg.wait_for_timeout(100)
        check('…and follows the phone’s tilt', g.evaluate("e=>e.style.getPropertyValue('--gx')") == '0.500', g.evaluate("e=>e.style.cssText"))
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Look & Feel'); C.choose(pg, 'Screen Glare'); pg.wait_for_timeout(500)
        check('…and can be turned off', g.evaluate("e=>getComputedStyle(e).opacity") == '0')
        # boot
        pg.evaluate("localStorage.setItem('ipod.boot.force','true')"); pg.reload(); pg.wait_for_timeout(1500)
        check('the iPod boots with an animation', pg.locator('#boot.on').count() == 1 and pg.locator('#boot').is_visible())
        pg.screenshot(path='/tmp/shots/boot.png', clip=pg.locator('#screen').bounding_box())
        pg.wait_for_timeout(1600)
        check('…that gets out of the way', pg.locator('#boot.on').count() == 0)
        check('no page errors', not errors, errors)
    srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
main()
