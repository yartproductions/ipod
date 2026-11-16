#!/usr/bin/env python3
"""Star ratings: rate with the wheel, stars on Now Playing, Top Rated / 5 Stars lists.  Run: python3 tests/ratings.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
def options(pg): pg.keyboard.press('Enter'); pg.wait_for_timeout(60); pg.keyboard.press('Enter'); pg.wait_for_timeout(350)

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
        C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(700)
        options(pg)
        check('song options show Rating: None', 'Rating' in pg.inner_text('#body') and 'None' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, 'Rating')
        check('the rating screen opens empty', pg.locator('.rate .big i.on').count() == 0)
        C.key(pg, 'ArrowDown', 6, wait=60)
        check('spinning sets up to 5 stars (and no more)', pg.locator('.rate .big i.on').count() == 5)
        pg.screenshot(path='/tmp/shots/rate.png', clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowUp', wait=60); C.key(pg, 'Enter', wait=500)
        check('Center saves and returns to Now Playing', pg.text_content('#htitle') == 'Now Playing')
        check('Now Playing shows the stars', pg.locator('#np .stars').count() == 1 and pg.inner_text('#np .stars').count('★') == 5)
        pg.screenshot(path='/tmp/shots/rate-np.png', clip=pg.locator('#screen').bounding_box())
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Red Line Track'); pg.wait_for_timeout(600)
        options(pg); C.choose(pg, 'Rating'); C.key(pg, 'ArrowDown', 5, wait=60); C.key(pg, 'Enter', wait=500)
        pg.reload(); pg.wait_for_timeout(2000); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Smart Playlists')
        body = pg.inner_text('#body')
        check('Top Rated and 5 Stars appear', 'Top Rated' in body and '5 Stars' in body, body)
        C.choose(pg, 'Top Rated'); rows = C.all_rows(pg)
        check('Top Rated has both, 5 stars first (ratings survive a reload)', rows[3:5] == ['Red Line Track', 'Blue Hour Track'], rows)
        C.key(pg, 'Escape', wait=250); C.choose(pg, '5 Stars')
        check('5 Stars has only the 5-star song', C.all_rows(pg)[3:] == ['Red Line Track'], C.all_rows(pg))
        check('rating unlocks Critic', 'rate1' in pg.evaluate("JSON.parse(localStorage.getItem('ipod.achievements')).unlocked"))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
