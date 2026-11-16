#!/usr/bin/env python3
"""What's New tour + NEW tags, and the tidied Music menu.   Run: python3 tests/whats_new.py"""
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
              args=['--no-sandbox'], viewport={'width': 390, 'height': 844}, device_scale_factor=2, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings')){localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}));localStorage.setItem('ipod.tour.force','true')}")
        pg.goto(url); pg.wait_for_timeout(2600)
        check('the tour opens by itself once', pg.text_content('#htitle') == 'What’s New' and 'What’s New on your iPod' in pg.inner_text('.tour'))
        pg.screenshot(path='/tmp/shots/tour-0.png', clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowDown', wait=450)
        check('spinning flips to the next card', 'Flow' in pg.inner_text('.tour b'), pg.inner_text('.tour b'))
        pg.screenshot(path='/tmp/shots/tour-1.png', clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowDown', wait=450); C.key(pg, 'ArrowDown', wait=450)
        check('…to DJ Mode', 'DJ Mode' in pg.inner_text('.tour b'))
        C.key(pg, 'Enter', wait=500)
        check('Center takes you to try it', pg.text_content('#htitle') == 'DJ Mode')
        pg.reload(); pg.wait_for_timeout(2600)
        check('it doesn’t open again after a reload', pg.text_content('#htitle') == 'iPod')
        C.home(pg)
        check('new things carry a NEW tag on the menu', pg.locator('.newtag').count() >= 1)
        C.choose(pg, 'Music')
        rows = C.all_rows(pg)
        check('the Music menu is grouped', rows == ['Search', 'Search In', 'Offline Music', 'Music Home', 'Shuffle Songs', 'DJ Mode', 'Playlists', 'Together', 'Your Story', 'Sleep & Wake'], rows)
        pg.screenshot(path='/tmp/shots/music-tidy.png', clip=pg.locator('#screen').bounding_box())
        check('Playlists has a NEW tag before you open it', 'NEW' in pg.inner_text('#body'))
        C.choose(pg, 'Playlists')
        check('Playlists holds Smart Playlists and Sessions', C.all_rows(pg) == ['Smart Playlists', 'Sessions'], C.all_rows(pg))
        C.key(pg, 'Escape', wait=300)
        check('opening it clears its NEW tag', 'Playlists' not in [e for e in pg.eval_on_selector_all('.row .lb', "e=>e.filter(x=>x.querySelector('.newtag')).map(x=>x.querySelector('.lt').textContent)")])
        C.choose(pg, 'Together'); check('Together holds Listen Together and Shared Playlists', C.all_rows(pg) == ['Listen Together', 'Shared Playlists'], C.all_rows(pg))
        C.key(pg, 'Escape', wait=300); C.choose(pg, 'Your Story'); check('Your Story holds Wrapped and Memories', C.all_rows(pg) == ['iPod Wrapped', 'Song Memories'], C.all_rows(pg))
        C.key(pg, 'Escape', wait=300); C.choose(pg, 'Sleep & Wake'); check('Sleep & Wake holds the timer and alarm', C.all_rows(pg) == ['Sleep Timer', 'Wake-Up Alarm'], C.all_rows(pg))
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'What’s New'); pg.wait_for_timeout(300)
        check('Settings ▸ What’s New replays it', pg.text_content('#htitle') == 'What’s New')
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
