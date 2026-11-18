#!/usr/bin/env python3
"""Lock screen styles: Glass, Big Art, Night Stand, Classic LCD, Flip Clock, Live Lyrics.  Run: python3 tests/lock_styles.py"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
LRC = '\n'.join(f'[00:{i:02d}.00]Line number {i}' for i in range(0, 60))
def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, device_scale_factor=2, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        ctx.route('https://lrclib.net/**', lambda r: r.fulfill(status=200, content_type='application/json',
                  body=json.dumps({'trackName': 'Blue Hour Track', 'artistName': 'Fixture Artist', 'instrumental': False, 'plainLyrics': 'x', 'syncedLyrics': LRC})))
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!sessionStorage.getItem('s')){sessionStorage.setItem('s',1);localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,repeat:'One',glare:'Off'}))}")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(500)
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Look & Feel')
        check('Look & Feel has Lock Screen Style', 'Lock Screen Style' in C.all_rows(pg), C.all_rows(pg))
        C.choose(pg, 'Lock Screen Style'); pg.wait_for_timeout(400)
        check('changing the style previews it', 'on' in pg.get_attribute('#lockscr', 'class') and 'ls-bigart' in pg.get_attribute('#lockscr', 'class'))
        pg.wait_for_timeout(3000)
        check('…then the preview goes away by itself', 'on' not in pg.get_attribute('#lockscr', 'class'))
        expect = {'Big Art': 'ls-bigart', 'Night Stand': 'ls-night', 'Classic LCD': 'ls-lcd', 'Flip Clock': 'ls-flip', 'Live Lyrics': 'ls-lyrics', 'Glass': 'ls-glass'}
        for i, (name, cls) in enumerate(expect.items()):
            if i: C.choose(pg, 'Lock Screen Style'); pg.wait_for_timeout(300)
            pg.keyboard.press('h'); pg.wait_for_timeout(1300 if name == 'Live Lyrics' else 700)
            box = pg.locator('#lockscr')
            txt = pg.inner_text('#lockin')
            check(f'{name}: shown on Hold with the time', cls in box.get_attribute('class') and (':' in txt or name == 'Flip Clock'), txt[:80])
            check(f'{name}: shows the song', 'Blue Hour Track' in pg.text_content('#lockin'), pg.text_content('#lockin')[:120])
            if name == 'Big Art':
                check('Big Art: shows elapsed and remaining time', '-' in pg.text_content('[data-k="rem"]'))
            if name == 'Flip Clock':
                fh, fm = pg.text_content('[data-k="fh"]'), pg.text_content('[data-k="fm"]')
                check('Flip Clock: hour and minute cards', fh.isdigit() and len(fm) == 2, (fh, fm))
            if name == 'Live Lyrics':
                pg.wait_for_timeout(800)
                cur = pg.text_content('[data-k="lc"]'); nxt = pg.text_content('[data-k="ln"]')
                check('Live Lyrics: follows the song line by line', cur.startswith('Line number') and nxt.startswith('Line number') and cur != nxt, (cur, nxt))
                bg = pg.evaluate("getComputedStyle(document.getElementById('lockbg')).filter")
                check('Live Lyrics: the cover is only lightly blurred behind it', 'blur(7px)' in bg, bg)
            pg.screenshot(path=f'/tmp/shots/lock-{cls}.png', clip=pg.locator('#screen').bounding_box())
            pg.keyboard.press('h'); pg.wait_for_timeout(300)
        check('the style is remembered', json.loads(pg.evaluate("localStorage.getItem('ipod.settings')"))['lockStyle'] == 'Glass')
        check('no page errors', not errors, errors)
    srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
main()
