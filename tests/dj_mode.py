#!/usr/bin/env python3
"""DJ Mode: an endless mix taking an equal share from every playlist.   Run: python3 tests/dj_mode.py"""
import sys, tempfile, json
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
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('*.mp3'))); pg.wait_for_timeout(4000); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Shuffle Songs'); pg.wait_for_timeout(400)
        songs = pg.evaluate("ipodMacBridge.queue().map(s=>({id:s.id,t:s.title}))")
        A, B = songs[:1], songs[1:7]
        pls = [{'id': 'pa', 'name': 'Tiny List', 'tracks': [{'localSongId': s['id'], 'title': s['t']} for s in A]},
               {'id': 'pb', 'name': 'Big List', 'tracks': [{'localSongId': s['id'], 'title': s['t']} for s in B]}]
        pg.evaluate("p=>localStorage.setItem('ipod.importedPlaylists.v1',JSON.stringify(p))", pls)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'DJ Mode')
        check('DJ Mode counts the playlists it will mix', '2 lists' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, 'Start DJ'); pg.wait_for_timeout(500)
        q = pg.evaluate("ipodMacBridge.queue().map(s=>s.id)")
        check('DJ starts playing on Now Playing', pg.text_content('#htitle') == 'Now Playing' and len(q) >= 60, len(q))
        a_share = sum(1 for x in q[:40] if x == A[0]['id']) / 40
        check('a 1-song playlist gets an equal share against a 6-song one', 0.4 <= a_share <= 0.6, a_share)
        check('no song plays twice in a row', all(q[i] != q[i + 1] for i in range(len(q) - 1)))
        bq = [x for x in q[:60] if x != A[0]['id']]
        check('the big list cycles through all its songs', set(bq) == {s['id'] for s in B}, len(set(bq)))
        # three lists of equal size: each about a third, no repeats within the window
        pls.append({'id': 'pc', 'name': 'Other', 'tracks': [{'localSongId': s['id'], 'title': s['t']} for s in songs[7:]]})
        pls[0]['tracks'] = [{'localSongId': s['id'], 'title': s['t']} for s in songs[:3]]
        pls[1]['tracks'] = [{'localSongId': s['id'], 'title': s['t']} for s in songs[3:6]]
        pls[2]['tracks'] = pls[2]['tracks'][:3]
        pg.evaluate("p=>localStorage.setItem('ipod.importedPlaylists.v1',JSON.stringify(p))", pls)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'DJ Mode'); C.choose(pg, 'Start DJ'); pg.wait_for_timeout(400)
        q = pg.evaluate("ipodMacBridge.queue().map(s=>s.id)")
        groups = [{t['localSongId'] for t in pl['tracks']} for pl in pls]
        shares = [sum(1 for x in q[:60] if x in g) for g in groups]
        check('three playlists share the mix equally', all(18 <= s_ <= 22 for s_ in shares), shares)
        check('songs don’t repeat close together', all(len(set(q[i:i + 4])) == 4 for i in range(0, 50)))
        # turning a source off
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'DJ Mode'); C.choose(pg, 'Sources'); C.choose(pg, 'Other')
        check('a source can be switched off', 'Off' in pg.inner_text('#body'))
        C.key(pg, 'Escape', wait=250); C.choose(pg, 'Start DJ'); pg.wait_for_timeout(400)
        q = pg.evaluate("ipodMacBridge.queue().map(s=>s.id)")
        check('switched-off lists are left out', not any(x in groups[2] for x in q))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
