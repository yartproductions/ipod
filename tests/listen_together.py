#!/usr/bin/env python3
"""Listen Together: host shares a code, a guest joins and follows song / play-pause / position from their
own library. Firebase is replaced by tests/fake-firebase.js shared between two tabs.  Run: python3 tests/listen_together.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-firebase.js').read_text()

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'], viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        ctx.route('https://www.gstatic.com/firebasejs/**', lambda r: r.fulfill(status=200, content_type='text/javascript',
                  body=FAKE if 'app-compat' in r.request.url else '/* fake */'))
        ctx.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,repeat:'One'}))")
        hostp = ctx.new_page(); hostp.on('pageerror', lambda e: errors.append('host: ' + str(e)))
        hostp.goto(url); hostp.wait_for_timeout(1200)
        hostp.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); hostp.wait_for_timeout(3500); C.wait_sync(hostp); C.home(hostp)
        guest = ctx.new_page(); guest.on('pageerror', lambda e: errors.append('guest: ' + str(e)))
        guest.goto(url); guest.wait_for_timeout(1500)

        C.choose(hostp, 'Music'); C.choose(hostp, 'Listen Together'); C.choose(hostp, 'Host a Session'); hostp.wait_for_timeout(600)
        code = hostp.evaluate('ipodListen.code')
        check('host gets a 6-character code on the session screen', code and len(code) == 6 and code in hostp.inner_text('.ltg-who'), (code, hostp.inner_text('#body')))

        C.choose(guest, 'Music'); C.choose(guest, 'Listen Together'); C.choose(guest, 'Join with Code')
        guest.fill('#inpt', 'ABCDEF'); C.key(guest, 'Enter', wait=600)
        check('a wrong code is refused', 'Couldn’t Join' in guest.text_content('#htitle'), guest.text_content('#htitle'))
        C.key(guest, 'Escape', wait=200); C.choose(guest, 'Join with Code')
        guest.fill('#inpt', code.lower()); C.key(guest, 'Enter', wait=900)
        check('guest joins and sees the session screen', guest.evaluate('ipodListen.role') == 'guest' and 'Listening with' in guest.inner_text('.ltg-who'), guest.inner_text('#body'))
        hostp.wait_for_timeout(400)
        check('host sees one listener', hostp.evaluate('ipodListen.listeners') == 1 and '1 listening' in hostp.inner_text('.ltg-who'), hostp.inner_text('#body'))

        # host plays: guest follows from its own library
        C.home(hostp); C.choose(hostp, 'Music'); C.choose(hostp, 'Offline Music'); C.choose(hostp, 'Songs'); C.choose(hostp, 'Green Room Track'); hostp.wait_for_timeout(1500)
        guest.wait_for_timeout(1200)
        check('guest plays the same song', guest.evaluate('ipodListenBridge.cur()?.title') == 'Green Room Track', guest.evaluate('ipodListenBridge.cur()?.title'))
        check('guest is playing', guest.evaluate('!ipodListenBridge.paused()'))
        C.home(guest); C.choose(guest, 'Music'); C.choose(guest, 'Listen Together'); guest.wait_for_timeout(500)
        check('guest session screen shows the song and a moving progress bar', 'Green Room Track' in guest.inner_text('.ltg') and guest.evaluate("parseFloat(document.getElementById('lt-i').style.width)") > 0, guest.inner_text('#body'))
        C.key(hostp, 'Space', wait=300); guest.wait_for_timeout(1500)
        check('host pauses → guest pauses', hostp.evaluate('ipodListenBridge.paused()') and guest.evaluate('ipodListenBridge.paused()'))
        hostp.evaluate('ipodListenBridge.seek(1.2)'); hostp.wait_for_timeout(400); guest.wait_for_timeout(1500)
        gt = guest.evaluate('ipodListenBridge.time()')
        check('host seeks → guest jumps there', abs(gt - 1.2) < 0.35, gt)
        C.key(hostp, 'Space', wait=300); guest.wait_for_timeout(1500)
        check('host resumes → guest resumes', not guest.evaluate('ipodListenBridge.paused()'))

        # a song the guest doesn't have: guest pauses and says so, then rejoins on the next one it has
        guest.evaluate("ipodListenBridge.songs().find(s=>s.title==='Red Line Track').deleted=true")
        C.home(hostp); C.choose(hostp, 'Music'); C.choose(hostp, 'Offline Music'); C.choose(hostp, 'Songs'); C.choose(hostp, 'Red Line Track'); hostp.wait_for_timeout(1200)
        guest.wait_for_timeout(1500)
        check('guest without the song is told and stays paused', guest.evaluate('ipodListen.missing') and guest.evaluate('ipodListenBridge.paused()'), guest.evaluate('ipodListen.missing'))
        guest.wait_for_timeout(600)
        check('guest screen shows the unavailable song and keeps the bar moving', 'Couldn’t get this song' in guest.inner_text('.ltg') and 'Red Line Track' in guest.inner_text('.ltg'), guest.inner_text('#body'))
        guest.screenshot(path='/tmp/shots/listen-missing.png', clip=guest.locator('#screen').bounding_box())
        C.home(hostp); C.choose(hostp, 'Music'); C.choose(hostp, 'Offline Music'); C.choose(hostp, 'Songs'); C.choose(hostp, 'Blue Hour Track'); hostp.wait_for_timeout(1200)
        guest.wait_for_timeout(1500)
        check('guest rejoins on the next song it has', guest.evaluate('ipodListenBridge.cur()?.title') == 'Blue Hour Track' and not guest.evaluate('ipodListen.missing'))

        # leaving and ending
        guest.screenshot(path='/tmp/shots/listen-playing.png', clip=guest.locator('#screen').bounding_box())
        C.key(guest, 'Enter', wait=300); C.choose(guest, 'Leave'); hostp.wait_for_timeout(700)
        check('leaving tells the guest about songs to add', 'Songs You Missed' in guest.inner_text('.hdr'), guest.inner_text('.hdr'))
        C.home(guest); C.choose(guest, 'Music'); C.choose(guest, 'Listen Together'); C.choose(guest, 'Songs You Missed')
        check('Songs You Missed lists what you didn’t have', 'Red Line Track' in guest.inner_text('#body') and 'Green Room Track' not in guest.inner_text('#body'), guest.inner_text('#body'))
        check('guest leaves; host count drops', guest.evaluate('ipodListen.role') is None and hostp.evaluate('ipodListen.listeners') == 0, hostp.evaluate('ipodListen.listeners'))
        guest.evaluate(f"ipodListen._join('{code}')"); guest.wait_for_timeout(800)
        C.home(hostp); C.choose(hostp, 'Music'); C.choose(hostp, 'Listen Together'); C.key(hostp, 'Enter', wait=300); C.choose(hostp, 'End Session'); guest.wait_for_timeout(900)
        check('host ends; guest is let go', hostp.evaluate('ipodListen.role') is None and guest.evaluate('ipodListen.role') is None, guest.evaluate('ipodListen.role'))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
