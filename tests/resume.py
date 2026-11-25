#!/usr/bin/env python3
"""Resume where you left off: after closing and reopening, the same song, queue and second are back.
Run: python3 tests/resume.py"""
import sys, tempfile, subprocess, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FX = Path(tempfile.mkdtemp())
for n in ['Long Road', 'Slow River', 'Quiet Town']:
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=40', '-ac', '1', '-b:a', '48k',
                    '-metadata', f'title={n}', '-metadata', 'artist=Fixture Artist', '-metadata', 'album=Long Album', str(FX / f'{n}.mp3')], check=True)
srv, url = C.serve(); errors = []
with sync_playwright() as p:
    prof = tempfile.mkdtemp()
    def open_ipod():
        ctx = p.chromium.launch_persistent_context(prof, executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        return ctx, pg
    ctx, pg = open_ipod()
    pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
    pg.goto(url); pg.wait_for_timeout(1200)
    pg.set_input_files('#file', sorted(str(f) for f in FX.glob('*.mp3'))); pg.wait_for_timeout(3000); C.wait_sync(pg); C.home(pg)
    C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Slow River'); pg.wait_for_timeout(600)
    pg.wait_for_timeout(5000)
    saved = pg.evaluate("JSON.parse(localStorage.getItem('ipod.resume')||'null')")
    check('while playing, the iPod keeps note of the song and second', saved and saved['t'] >= 1 and len(saved['ids']) == 3, saved and {k: saved[k] for k in ('t', 'qi')})
    # pretend we were 21.5 s in when the app was closed
    pg.evaluate("(()=>{const r=JSON.parse(localStorage.getItem('ipod.resume'));r.t=21.5;localStorage.setItem('ipod.resume',JSON.stringify(r))})()")
    ctx.close()  # quit the app
    ctx, pg = open_ipod()
    pg.goto(url); pg.wait_for_timeout(3000)
    C.home(pg)
    rows = C.all_rows(pg)
    check('reopening offers Now Playing straight away', 'Now Playing' in rows, rows)
    C.choose(pg, 'Now Playing'); pg.wait_for_timeout(600)
    body = pg.inner_text('#body')
    check('…with the same song', 'Slow River' in body, body[:80])
    check('…at the same second', '0:21' in body, body)
    check('…waiting for you, not playing on its own', pg.evaluate("navigator.mediaSession.playbackState") != 'playing')
    pg.keyboard.press(' '); pg.wait_for_timeout(1600)
    body2 = pg.inner_text('#body')
    check('pressing play continues from there', '0:22' in body2 or '0:23' in body2, body2)
    pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(800)
    b3 = pg.inner_text('#body')
    check('…and the rest of the queue is there (next goes on to another song)', 'Slow River' not in b3 and 'OF 3' in b3.upper(), b3[:80])
    check('no page errors', not errors, errors)
    ctx.close()
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
