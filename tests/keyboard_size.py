#!/usr/bin/env python3
"""The keyboard coming up doesn't shrink the iPod.  Run: python3 tests/keyboard_size.py"""
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
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True, args=['--no-sandbox'], viewport={'width': 390, 'height': 844}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort())
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(url); pg.wait_for_timeout(1500)
    scale = lambda: pg.evaluate("getComputedStyle(document.getElementById('stage')).transform")
    s0 = scale()
    C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Lyrica API URL'); pg.wait_for_timeout(400)
    check('a text field is open and focused', pg.evaluate("document.activeElement&&document.activeElement.tagName==='INPUT'"))
    pg.set_viewport_size({'width': 390, 'height': 480}); pg.wait_for_timeout(1100)   # the keyboard takes the bottom of the screen
    check('the iPod keeps its size while typing', scale() == s0, (s0, scale()))
    check('…and doesn’t flip to landscape', 'landscape' not in pg.evaluate("document.documentElement.className"))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300); pg.evaluate("document.activeElement&&document.activeElement.blur()")
    pg.set_viewport_size({'width': 390, 'height': 844}); pg.wait_for_timeout(1100)
    check('after typing it’s still the normal size', scale() == s0, (s0, scale()))
    pg.set_viewport_size({'width': 390, 'height': 600}); pg.wait_for_timeout(1100)
    check('a real window resize (not typing) still re-fits', scale() != s0)
    check('no page errors', not errors, errors)
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
