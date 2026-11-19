#!/usr/bin/env python3
"""Lock Screen / CarPlay artwork: always a JPEG data URL of the real cover, re-sent when the song changes.
Run: python3 tests/session_art.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
srv, url = C.serve(); errors = []
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
          args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort())
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.add_init_script("localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,repeat:'One'}))")
    pg.goto(url); pg.wait_for_timeout(1200)
    pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
    C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(1500)
    meta = lambda: pg.evaluate("(()=>{const m=navigator.mediaSession.metadata;return m?{t:m.title,a:(m.artwork[0]||{}).src||'',ty:(m.artwork[0]||{}).type||''}:null})()")
    m = meta()
    check('the Lock Screen gets the song', m and m['t'] == 'Blue Hour Track', m and m['t'])
    check('…with the cover as a JPEG image, not an in-memory link', m and m['a'].startswith('data:image/jpeg') and m['ty'] == 'image/jpeg', m and m['a'][:30])
    px = pg.evaluate("""(async()=>{const m=navigator.mediaSession.metadata,im=new Image();im.src=m.artwork[0].src;await im.decode();const c=document.createElement('canvas');c.width=c.height=8;const g=c.getContext('2d');g.drawImage(im,0,0,8,8);return Array.from(g.getImageData(4,4,1,1).data).slice(0,3)})()""")
    check('…that is the real (blue) cover, not the initials stand-in', px[2] > 150 and px[0] < 150, px)
    a1 = m['a']
    pg.keyboard.press('ArrowRight') if False else None
    C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Red Line Track'); pg.wait_for_timeout(1500)
    m2 = meta()
    check('a new song sends its own cover', m2['t'] == 'Red Line Track' and m2['a'].startswith('data:image/jpeg') and m2['a'] != a1)
    st = pg.evaluate("navigator.mediaSession.playbackState")
    check('the Lock Screen is told it is playing', st == 'playing', st)
    pg.evaluate("navigator.mediaSession.playbackState='paused'"); pg.wait_for_timeout(1300)
    check('…and corrected if that ever drifts', pg.evaluate("navigator.mediaSession.playbackState") == 'playing')
    check('no page errors', not errors, errors)
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
