#!/usr/bin/env python3
"""Flows: hold Center on an album cover for a ring that plays the whole album — Play All, Crossfade Mix,
Shuffle, Add to Queue.   Run: python3 tests/flow_hold.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-native-player.js').read_text()
def hold(pg, ms=750):
    b = pg.locator('#center').bounding_box(); pg.mouse.move(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2)
    pg.mouse.down(); pg.wait_for_timeout(ms); pg.mouse.up(); pg.wait_for_timeout(250)
ring = lambda pg: pg.evaluate("(()=>{const s=document.getElementById('sheet');return {on:s.classList.contains('on')&&s.classList.contains('radial'),btns:[...document.querySelectorAll('#sheetBtns .bt span')].map(x=>x.textContent),hub:document.querySelector('#sheetBtns .rhub i')?.textContent||'',sel:document.querySelector('#sheetBtns .rhub b')?.textContent||''}})()")
srv, url = C.serve(); errors = []
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True, args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'],
          viewport={'width': 390, 'height': 844}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort())
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,accel:false}))")
    pg.add_init_script(FAKE)
    pg.goto(url); pg.wait_for_timeout(1200)
    pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('*.mp3'))); pg.wait_for_timeout(4000); C.wait_sync(pg)
    pg.wait_for_function("window.__native.files.size>=5", timeout=30000); pg.wait_for_timeout(1500)
    C.home(pg); C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow'); pg.wait_for_timeout(300)
    # find an album with several songs
    album = None
    for _ in range(15):
        pg.wait_for_timeout(900)
        head = pg.evaluate("document.querySelector('#flow .fpanel h4')?.textContent||''")
        if 'songs' in head.lower(): album = pg.text_content('#fal'); break
        C.key(pg, 'ArrowDown', wait=60)
    check('setup: an album with several songs', album, head)
    hold(pg); r = ring(pg)
    check('holding Center on an album cover opens the ring', r['on'] and r['btns'] == ['Play All', 'Mix', 'Shuffle', 'Add to Queue'], r)
    check('…titled with the album', r['hub'] == album, (r['hub'], album))
    pg.screenshot(path='/tmp/flow-hold-ring.png', clip=pg.locator('#screen').bounding_box())
    pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(150)
    check('spinning moves to Crossfade Mix', ring(pg)['sel'] == 'Crossfade Mix', ring(pg))
    pg.keyboard.press('Enter'); pg.wait_for_timeout(700)
    P = pg.evaluate("({n:window.__native.player.queue.length,smart:window.__native.player.smart,playing:window.__native.player.playing,al:window.__native.player.queue.map(x=>x.album)})")
    check('Crossfade Mix plays the whole album', P['n'] >= 2 and P['playing'] and len(set(P['al'])) == 1 and P['al'][0] == album, P)
    check('…with Smart crossfade on, though the setting is Off', P['smart'] is True, P)
    check('it opens Now Playing', pg.text_content('#htitle') == 'Now Playing')
    # Play All from another cover goes back to the normal crossfade setting
    C.home(pg); C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow'); pg.wait_for_timeout(300)
    for _ in range(15):
        pg.wait_for_timeout(900)
        if pg.text_content('#fal') == album: break
        C.key(pg, 'ArrowDown', wait=60)
    hold(pg); pg.keyboard.press('Enter'); pg.wait_for_timeout(700)
    check('Play All plays it with your normal crossfade setting', pg.evaluate("window.__native.player.smart") is False)
    n0 = pg.evaluate("window.__native.player.queue.length")
    C.home(pg); C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow'); pg.wait_for_timeout(300)
    for _ in range(15):
        pg.wait_for_timeout(900)
        if pg.text_content('#fal') == album: break
        C.key(pg, 'ArrowDown', wait=60)
    hold(pg)
    for _ in range(3): pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(120)
    pg.keyboard.press('Enter'); pg.wait_for_timeout(1200)
    n1 = pg.evaluate("window.__native.player.queue.length")
    check('Add to Queue adds the whole album after what’s playing', n1 == 2 * n0, (n0, n1))
    check('no page errors', not errors, errors)
    ctx.close()
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
