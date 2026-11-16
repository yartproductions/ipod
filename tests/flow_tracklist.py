#!/usr/bin/env python3
"""Flow panel: while you spin it lists the whole Flow (your spot highlighted); when you stop it shows what's
inside that cover (track list, or a song's details).   Run: python3 tests/flow_tracklist.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
panel = lambda pg: pg.evaluate("(()=>{const f=document.getElementById('flow'),p=f&&f.querySelector('.fpanel');return {shown:!!f&&f.classList.contains('withpanel'),inside:!!p&&p.classList.contains('inside'),head:p?p.querySelector('h4')?.textContent||'':'',on:p?p.querySelector('div.on span')?.textContent||'':''}})()")

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox'], viewport={'width': 390, 'height': 844}, device_scale_factor=2, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('*.mp3'))); pg.wait_for_timeout(4000); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow'); pg.wait_for_timeout(200)
        C.key(pg, 'ArrowDown', wait=120)
        x = panel(pg)
        check('while spinning the panel lists the whole Flow', x['shown'] and not x['inside'] and 'Album Flow' in x['head'], x)
        check('…with the cover you’re on highlighted', x['on'] == pg.text_content('#fal'), (x['on'], pg.text_content('#fal')))
        pg.screenshot(path='/tmp/shots/flow-list.png', clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowDown', wait=120)
        check('the highlight follows the wheel', panel(pg)['on'] == pg.text_content('#fal'))
        pg.wait_for_timeout(900); x = panel(pg)
        check('when you stop it switches to what’s inside', x['shown'] and x['inside'], x)
        pg.screenshot(path='/tmp/shots/flow-inside.png', clip=pg.locator('#screen').bounding_box())
        multi = None
        for _ in range(12):
            if 'songs' in panel(pg)['head'].lower() and panel(pg)['inside']: multi = pg.text_content('#fal'); break
            C.key(pg, 'ArrowDown', wait=60); pg.wait_for_timeout(900)
        check('a multi-song album shows its track list', multi is not None)
        rows = pg.eval_on_selector_all('.fpanel div span', 'e=>e.map(x=>x.textContent)')
        check('…with its songs', len(rows) >= 2, rows)
        C.key(pg, 'ArrowUp', wait=100)
        check('spinning again goes back to the Flow list', not panel(pg)['inside'] and panel(pg)['shown'])
        # Song Flow
        C.home(pg); C.choose(pg, 'Flows'); C.choose(pg, 'Song Flow'); C.key(pg, 'ArrowDown', wait=120)
        check('Song Flow lists its songs while spinning', panel(pg)['shown'] and 'Song Flow' in panel(pg)['head'], panel(pg))
        pg.wait_for_timeout(900)
        check('…and shows the song’s details when you stop', panel(pg)['inside'])
        # Playlist Flow
        ids = pg.evaluate("ipodListenBridge.songs().slice(0,3).map(s=>({id:s.id,t:s.title,a:s.artist}))")
        pls = [{'id': 'p1', 'name': 'Gym Mix', 'provider': 'Qobuz', 'tracks': [{'title': x['t'], 'artist': x['a'], 'localSongId': x['id'], 'status': 'matched'} for x in ids] + [{'title': 'Song I Lack', 'artist': 'Nobody'}]},
               {'id': 'p2', 'name': 'Chill', 'provider': 'Qobuz', 'tracks': [{'title': ids[0]['t'], 'artist': ids[0]['a'], 'localSongId': ids[0]['id'], 'status': 'matched'}]}]
        pg.evaluate("p=>localStorage.setItem('ipod.importedPlaylists.v1',JSON.stringify(p))", pls)
        C.home(pg); C.choose(pg, 'Flows'); C.choose(pg, 'Playlist Flow'); C.key(pg, 'ArrowUp', wait=120)
        x = panel(pg)
        check('Playlist Flow lists the playlists while spinning', x['shown'] and 'Playlist Flow' in x['head'] and x['on'] == pg.text_content('#fal'), x)
        pg.wait_for_timeout(900)
        rows = pg.eval_on_selector_all('.fpanel div span', 'e=>e.map(x=>x.textContent)')
        check('…and shows the playlist’s tracks when you stop', panel(pg)['inside'] and 'tracks' in panel(pg)['head'].lower() and len(rows) >= 1, (panel(pg), rows))
        pg.screenshot(path='/tmp/shots/flow-playlist.png', clip=pg.locator('#screen').bounding_box())
        if 'Gym Mix' == pg.text_content('#fal'):
            check('tracks you don’t have are dimmed', pg.locator('.fpanel div.dim').count() == 1)
        # the Flows menu shelf (Menu Style: Flow)
        pg.evaluate("(()=>{const s=JSON.parse(localStorage.getItem('ipod.settings'));s.menuStyle='Flow';localStorage.setItem('ipod.settings',JSON.stringify(s))})()")
        pg.reload(); pg.wait_for_timeout(1500); C.home(pg); C.key(pg, 'ArrowDown', wait=150)
        x = panel(pg)
        check('the Flow-style menu shelf lists its entries too', x['shown'] and x['on'] == pg.text_content('#fal'), x)
        pg.screenshot(path='/tmp/shots/flow-menu.png', clip=pg.locator('#screen').bounding_box())
        pg.evaluate("(()=>{const s=JSON.parse(localStorage.getItem('ipod.settings'));delete s.menuStyle;localStorage.setItem('ipod.settings',JSON.stringify(s))})()")
        pg.reload(); pg.wait_for_timeout(1500)
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Flow Track List')
        C.home(pg); C.choose(pg, 'Flows'); C.choose(pg, 'Album Flow'); C.key(pg, 'ArrowDown', wait=900)
        check('it can be turned off in Settings', not panel(pg)['shown'])
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
