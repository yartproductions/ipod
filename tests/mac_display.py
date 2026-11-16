#!/usr/bin/env python3
"""Mac Display: pair with a code, phone streams Now Playing / Flow / lyrics to mac.html.
Firebase is replaced by tests/fake-firebase.js (shared between the two tabs). Run: python3 tests/mac_display.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-firebase.js').read_text()
SHOTS = Path('/tmp/shots'); SHOTS.mkdir(exist_ok=True)

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling',
              '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows', '--disable-features=IntensiveWakeUpThrottling'], viewport={'width': 1440, 'height': 900}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        ctx.route('https://www.gstatic.com/firebasejs/**', lambda r: r.fulfill(status=200, content_type='text/javascript',
                  body=FAKE if 'app-compat' in r.request.url else '/* provided by the app-compat fake */'))
        mac = ctx.new_page(); mac.on('pageerror', lambda e: errors.append('mac: ' + str(e)))
        mac.goto(url + 'mac.html'); mac.wait_for_timeout(800)
        code = mac.evaluate('window.__macDisplay.code')
        check('Mac shows a 6-character pairing code', code and len(code) == 6 and mac.inner_text('#code').replace('\n', '') == code, code)
        mac.screenshot(path=str(SHOTS / 'mac-pair.png'))

        ph = ctx.new_page(); ph.set_viewport_size({'width': 390, 'height': 844}); ph.on('pageerror', lambda e: errors.append('phone: ' + str(e)))
        ph.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        ph.goto(url); ph.wait_for_timeout(1200)
        ph.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3')) + [str(C.FIX / 'lyrics.mp3')]); ph.wait_for_timeout(3500); C.wait_sync(ph); C.home(ph)

        C.choose(ph, 'Settings'); C.choose(ph, 'Mac Display')
        ph.fill('#inpt', 'ZZZZZZ'); C.key(ph, 'Enter', wait=600)
        check('a wrong code is refused', 'Couldn’t Connect' in ph.text_content('#htitle') + ph.inner_text('#body'), ph.inner_text('#body'))
        C.key(ph, 'Escape', wait=200); C.choose(ph, 'Mac Display')
        ph.fill('#inpt', code.lower()); C.key(ph, 'Enter', wait=800)
        check('phone pairs with the code (any case)', ph.text_content('#htitle') == 'Mac Connected', ph.text_content('#htitle'))
        mac.wait_for_timeout(500)
        check('Mac hides the code once paired', 'gone' in mac.get_attribute('#pair', 'class'))

        # play something: Mac follows Now Playing
        C.home(ph); C.choose(ph, 'Music'); C.choose(ph, 'Offline Music'); C.choose(ph, 'Songs'); C.choose(ph, 'Lyric Test'); ph.wait_for_timeout(300)
        C.key(ph, 'Space', wait=900)
        check('Mac shows the playing song', 'Lyric Test' in mac.inner_text('#np'), mac.inner_text('#np'))
        check('Mac carousel shows the queue around it', mac.locator('#shelf .cv').count() >= 3 and 'Lyric Test' in mac.inner_text('#cap'), mac.inner_text('#cap'))
        mac.wait_for_timeout(4500)
        check('Mac shows the song’s lyrics', 'fixture lyric' in mac.inner_text('#lines').lower() or len(mac.inner_text('#lines').strip()) > 10, mac.inner_text('#lines')[:120])
        check('cover art reached the Mac', mac.evaluate("[...document.querySelectorAll('#shelf .cv')].some(e=>e.style.backgroundImage.includes('data:image/jpeg'))"))
        mac.screenshot(path=str(SHOTS / 'mac-now.png'))

        # browse a Flow on the phone: the Mac carousel follows the wheel
        C.home(ph); C.choose(ph, 'Flows'); C.choose(ph, 'Album Flow'); ph.wait_for_timeout(600)
        mac.wait_for_timeout(700); first = mac.inner_text('#cap b')
        check('Mac switches to the Flow you opened', mac.inner_text('#ctx') == 'ALBUM FLOW' or mac.inner_text('#ctx').lower() == 'album flow', mac.inner_text('#ctx'))
        C.key(ph, 'ArrowUp', wait=250); C.key(ph, 'ArrowUp', wait=250); mac.wait_for_timeout(700)
        check('spinning on the phone moves the Mac carousel', mac.inner_text('#cap b') != first and mac.inner_text('#cap b') == ph.text_content('#fal') if ph.locator('#fal').count() else mac.inner_text('#cap b') != first,
              (first, mac.inner_text('#cap b')))
        mac.screenshot(path=str(SHOTS / 'mac-flow.png'))

        # disconnect from the phone: Mac offers a fresh code
        C.home(ph); C.choose(ph, 'Settings'); C.choose(ph, 'Mac Display')
        check('phone shows the connection', 'Connected' in ph.inner_text('#body'))
        C.choose(ph, 'Disconnect'); mac.wait_for_timeout(900)
        mac.wait_for_timeout(600)
        new = mac.evaluate('window.__macDisplay.code')
        check('after Disconnect the Mac shows a new code', 'gone' not in mac.get_attribute('#pair', 'class') and new and new != code, (code, new))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
