#!/usr/bin/env python3
"""Bright Screen video: hidden (no iOS play button) unless it is actually playing.  Run: python3 tests/hdr_overlay.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
srv, url = C.serve()
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True, args=['--no-sandbox'], viewport={'width': 390, 'height': 844}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort())
    pg = ctx.new_page(); pg.goto(url); pg.wait_for_timeout(1200)
    vis = lambda: pg.evaluate("(()=>{const v=document.getElementById('hdrboost'),c=getComputedStyle(v);return [c.visibility,c.opacity]})()")
    pg.evaluate("document.documentElement.classList.add('hdr');const v=document.getElementById('hdrboost');v.classList.remove('playing');v.dispatchEvent(new Event('pause'))")
    pg.wait_for_timeout(900)
    check('a brightness video that iOS won’t start stays hidden', vis()[0] == 'hidden', vis())
    pg.evaluate("document.getElementById('hdrboost').dispatchEvent(new Event('playing'))"); pg.wait_for_timeout(900)
    check('…and shows once it is really playing', vis()[0] == 'visible' and float(vis()[1]) > 0.5, vis())
    pg.evaluate("document.getElementById('hdrboost').dispatchEvent(new Event('pause'))"); pg.wait_for_timeout(100)
    check('…and hides again if it stops', vis()[0] == 'hidden', vis())
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
