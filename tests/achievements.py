#!/usr/bin/env python3
"""Achievements: unlock from listening and features, notify once, list progress.   Run: python3 tests/achievements.py"""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
def rows_slow(pg):
    for _ in range(80): pg.keyboard.press('ArrowUp')
    pg.wait_for_timeout(300); out = [C.sel(pg)]
    for _ in range(80):
        b = C.selpos(pg); pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(70)
        if C.selpos(pg) == b: break
        out.append(C.sel(pg))
    return out
ach = lambda pg: pg.evaluate("JSON.parse(localStorage.getItem('ipod.achievements')||'{}')")
notes = lambda pg: pg.evaluate("JSON.parse(localStorage.getItem('ipod.notifications')||'[]')")

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('*.mp3'))); pg.wait_for_timeout(4000); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Games'); C.choose(pg, 'Achievements')
        rows = rows_slow(pg)
        check('Achievements lists everything with progress', rows[0] == 'Unlocked' and len(rows) > 40 and 'First Spin' in rows, rows[:5])
        check('secret ones stay hidden', '🔒 Secret' in rows)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Shuffle Songs'); pg.wait_for_timeout(2500)
        a = ach(pg)
        check('playing a song unlocks First Spin', 'play1' in a['unlocked'], list(a['unlocked']))
        check('the unlock raises a notification', any('First Spin' in n['body'] for n in notes(pg)), notes(pg))
        pg.evaluate("ipodShake()"); pg.wait_for_timeout(300)
        check('features unlock theirs (Shake It)', 'shake1' in ach(pg)['unlocked'])
        n_before = len(notes(pg)); pg.evaluate("ipodAchievements.check()"); pg.wait_for_timeout(200)
        check('an achievement notifies only once', len(notes(pg)) == n_before)
        pg.wait_for_timeout(2500)
        C.home(pg); C.choose(pg, 'Games')
        check('Games shows the unlocked count', any('/' in v for v in [pg.inner_text('#body')]) and pg.inner_text('#body').count('/') >= 1, pg.inner_text('#body'))
        C.choose(pg, 'Achievements'); rows = rows_slow(pg)
        check('unlocked ones are listed first with a trophy', rows[1].startswith('🏆'), rows[:4])
        pg.screenshot(path='/tmp/shots/achievements.png', clip=pg.locator('#screen').bounding_box())
        # existing history is credited quietly on first run
        now = int(time.time() * 1000)
        pg.evaluate("t=>{localStorage.removeItem('ipod.achievements');localStorage.setItem('ipod.notifications','[]');localStorage.setItem('ipod.notifications.seen','[]');"
                    "localStorage.setItem('ipod.listeningHistory',JSON.stringify(Array.from({length:30},(_,i)=>({id:'x'+i,at:t-i*60000}))))}", now)
        pg.reload(); pg.wait_for_timeout(2500)
        a = ach(pg)
        check('existing history counts (Warming Up from 30 past plays)', 'play25' in a['unlocked'] and a['plays'] >= 30, (a.get('plays'), list(a['unlocked'])))
        check('…without a flood of notifications', not any('Warming Up' in n['body'] for n in notes(pg)))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
