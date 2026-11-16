#!/usr/bin/env python3
"""Hold switch: locks the wheel, keeps the backlight on, keeps the phone's screen awake.  Run: python3 tests/hold.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
WAKE_MOCK = """window.__wl={req:0,rel:0,fail:0};Object.defineProperty(navigator,'wakeLock',{value:{request:async t=>{
  if(window.__wlFailOnce){window.__wlFailOnce=false;__wl.fail++;throw Object.assign(new Error('not allowed'),{name:'NotAllowedError'})}
  __wl.req++;const l={released:false,_h:[],addEventListener(e,f){this._h.push(f)},async release(){this.released=true;__wl.rel++}};return l}}});"""

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox'], viewport={'width': 390, 'height': 844}, service_workers='block', has_touch=True)
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,backlight:'10 sec'}))"); pg.add_init_script(WAKE_MOCK)
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.tap('#hold'); pg.wait_for_timeout(300)
        check('tapping Hold turns it on', 'on' in pg.get_attribute('#hold', 'class'))
        check('Hold asks the browser to keep the screen on', pg.evaluate('__wl.req') == 1, pg.evaluate('__wl'))
        before = C.sel(pg); C.key(pg, 'ArrowDown')
        check('the wheel is locked while on', C.sel(pg) == before)
        pg.wait_for_timeout(11000)
        check('the iPod backlight doesn’t dim while on', 'dim' not in (pg.get_attribute('#screen', 'class') or ''))
        pg.tap('#hold'); pg.wait_for_timeout(300)
        check('Hold off releases the screen lock', pg.evaluate('__wl.rel') == 1, pg.evaluate('__wl'))
        # refused (no "real" tap yet in Safari): retried on the next tap
        pg.evaluate('window.__wlFailOnce=true'); pg.tap('#hold'); pg.wait_for_timeout(300)
        pg.tap('#screen'); pg.wait_for_timeout(300)
        check('a refused request is retried on the next touch and succeeds', pg.evaluate('__wl.fail') == 1 and pg.evaluate('__wl.req') == 2, pg.evaluate('__wl'))
        pg.tap('#hold'); pg.wait_for_timeout(200)
        # iPhone app: the app keeps the screen on instead
        pg2 = ctx.new_page(); pg2.on('pageerror', lambda e: errors.append(str(e)))
        pg2.add_init_script("window.__ka=[];window.webkit={messageHandlers:{ipodKeepAwake:{postMessage:m=>__ka.push(m)}}}")
        pg2.goto(url); pg2.wait_for_timeout(1200)
        pg2.keyboard.press('h'); pg2.wait_for_timeout(200); pg2.keyboard.press('h'); pg2.wait_for_timeout(200)
        check('in the iPhone app, Hold tells the app to keep the screen on, then off', pg2.evaluate('__ka') == [{'on': True}, {'on': False}], pg2.evaluate('__ka'))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
