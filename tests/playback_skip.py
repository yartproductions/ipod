#!/usr/bin/env python3
"""A song that won't play is skipped instead of stopping the list.   Run: python3 tests/playback_skip.py"""
import sys, tempfile, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
tmp = Path(tempfile.mkdtemp()); broken = tmp / 'aaa-broken-song.mp3'; broken.write_bytes(os.urandom(40000))
srv, url = C.serve(); errors = []
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True, args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'],
          viewport={'width': 390, 'height': 844}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort())
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.add_init_script("localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,accel:false}))")
    pg.goto(url); pg.wait_for_timeout(1200)
    pg.set_input_files('#file', [str(broken)] + sorted(str(f) for f in C.FIX.glob('album-*.mp3'))[:2]); pg.wait_for_timeout(4000); C.wait_sync(pg)
    q = lambda: pg.evaluate("({q:window.ipodMacBridge.queue().map(x=>x.title),i:window.ipodMacBridge.qi(),paused:window.ipodMacBridge.paused()})")
    C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs')
    rows = C.all_rows(pg)
    check('setup: the broken file is in the list', any('broken' in r.lower() for r in rows), rows)
    C.choose(pg, next(r for r in rows if 'broken' in r.lower())); pg.wait_for_timeout(2500)
    s = q()
    check('a song that can’t play is skipped to the next one', 'broken' not in s['q'][s['i']].lower() and not s['paused'], s)
    check('no page errors', not errors, errors)
    ctx.close()
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
