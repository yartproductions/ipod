#!/usr/bin/env python3
"""Song Memories: pin a short note to a song; it appears when the song plays.   Run: python3 tests/song_memories.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,repeat:'One'}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(800)
        pg.keyboard.press('Enter'); pg.wait_for_timeout(60); pg.keyboard.press('Enter'); pg.wait_for_timeout(350)   # double-press Center = song options
        check('song options offer Add Memory', 'Add Memory' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, 'Add Memory'); pg.fill('#inpt', 'summer ’24 road trip'); C.key(pg, 'Enter', wait=600)
        check('saving returns to the song and shows the memory card', pg.locator('#memocard.on').count() == 1 and 'road trip' in pg.inner_text('#memocard'))
        pg.screenshot(path='/tmp/shots/memory.png', clip=pg.locator('#screen').bounding_box())
        pg.wait_for_timeout(6600)
        check('the card slides away after a few seconds', pg.locator('#memocard').count() == 0)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Green Room Track'); pg.wait_for_timeout(900)
        check('songs without a memory show nothing', pg.locator('#memocard').count() == 0)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(900)
        check('playing the song again brings its memory back', pg.locator('#memocard').count() == 1)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Song Memories')
        check('Song Memories lists it', 'Blue Hour Track' in pg.inner_text('#body') and 'road trip' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.reload(); pg.wait_for_timeout(1500); C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Song Memories')
        check('memories survive a reload', 'road trip' in pg.inner_text('#body'))
        C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(900)
        pg.keyboard.press('Enter'); pg.wait_for_timeout(60); pg.keyboard.press('Enter'); pg.wait_for_timeout(350)   # double-press Center = song options
        check('options now say Edit / Delete Memory', 'Edit Memory' in pg.inner_text('#body') and 'Delete Memory' in pg.inner_text('#body'))
        C.choose(pg, 'Delete Memory'); pg.wait_for_timeout(300)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Song Memories')
        check('deleting removes it', 'road trip' not in pg.inner_text('#body'))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
