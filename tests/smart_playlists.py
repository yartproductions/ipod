#!/usr/bin/env python3
"""Smart Playlists and listening Sessions.   Run: python3 tests/smart_playlists.py"""
import sys, tempfile, json, time
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
        C.choose(pg, 'Music'); C.choose(pg, 'Smart Playlists')
        check('with no history only the library lists show', 'Never Played' in pg.inner_text('#body') and 'Most Played' not in pg.inner_text('#body'), pg.inner_text('#body'))
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Shuffle Songs'); pg.wait_for_timeout(500)
        songs = pg.evaluate("ipodMacBridge.queue().map(s=>({id:s.id,t:s.title}))")
        now = int(time.time() * 1000); H = 3600 * 1000
        yday = pg.evaluate("(()=>{const d=new Date();d.setHours(0,0,0,0);return +d-4*3600*1000})()")   # yesterday 8 PM, whatever the time now
        # tonight: 3 plays (A twice), yesterday evening: 2 plays, last week: 1 play; A played at 11 PM-ish counts toward After Dark
        a, b, c, d = songs[0], songs[1], songs[2], songs[3]
        hist = [{'id': a['id'], 'at': now - 5 * 60 * 1000}, {'id': b['id'], 'at': now - 10 * 60 * 1000}, {'id': a['id'], 'at': now - 15 * 60 * 1000},
                {'id': c['id'], 'at': yday}, {'id': a['id'], 'at': yday - 20 * 60 * 1000},
                {'id': d['id'], 'at': now - 6 * 24 * H}]
        pg.evaluate("h=>{localStorage.setItem('ipod.listeningHistory',JSON.stringify(h))}", hist)
        pg.reload(); pg.wait_for_timeout(1800); C.home(pg)

        C.choose(pg, 'Music'); C.choose(pg, 'Sessions')
        rows = C.all_rows(pg); pg.screenshot(path='/tmp/shots/sessions.png', clip=pg.locator('#screen').bounding_box())
        check('three listening sessions are found', len(rows) == 3, rows)
        check('the newest session comes first with a friendly name', rows and rows[0] in ('Tonight', 'This Morning', 'This Afternoon', 'Last Night'), rows)
        check('yesterday is named as such', any(r.startswith('Yesterday') for r in rows), rows)
        check('session shows its song count', '2 songs' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, rows[0])
        body = C.all_rows(pg)
        check('a session opens with Play / Shuffle / Save and its songs in play order', body[:3] == ['Play', 'Shuffle', 'Save as Playlist'] and body[3:] == [a['t'], b['t']], body)
        C.choose(pg, 'Play'); pg.wait_for_timeout(500)
        check('Play starts the session', pg.text_content('#htitle') == 'Now Playing' and a['t'] in pg.inner_text('#body'))
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Smart Playlists')
        lists = C.all_rows(pg); pg.screenshot(path='/tmp/shots/smart.png', clip=pg.locator('#screen').bounding_box())
        check('smart playlists appear once you have history', 'Most Played' in lists and 'Heavy Rotation' in lists and 'Never Played' in lists, lists)
        C.choose(pg, 'Most Played')
        mp = C.all_rows(pg)
        check('Most Played puts your most-played song first', mp[3] == a['t'], mp)
        C.key(pg, 'Escape', wait=250); C.choose(pg, 'Never Played')
        check('Never Played excludes played songs', a['t'] not in C.all_rows(pg) and len(C.all_rows(pg)) == 3 + len(songs) - 4)
        C.choose(pg, 'Save as Playlist'); pg.wait_for_timeout(400)
        check('Save as Playlist saves it', 'Saved' in pg.inner_text('.hdr'), pg.inner_text('.hdr'))
        # the alarm can wake you to any smart list, session or saved playlist
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Wake-Up Alarm'); C.choose(pg, 'Play')
        opts = C.all_rows(pg)
        check('alarm offers smart lists and sessions', all(x in opts for x in ['Favorites', 'Last Session', 'Most Played', 'Never Played']), opts)
        check('the playlist you saved (“Never Played”) is offered too', opts.count('Never Played') == 2, opts)
        C.choose(pg, 'Most Played'); pg.wait_for_timeout(200)
        check('picking one sets the alarm source', 'Most Played' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.evaluate("ipodWakeUp()"); pg.wait_for_timeout(600)
        check('waking up plays that list', pg.text_content('#htitle') == 'Now Playing' and a['t'] in pg.inner_text('#body'), pg.inner_text('#body')[:80])
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Wake-Up Alarm'); C.choose(pg, 'Play')
        C.key(pg, 'ArrowDown', 20, wait=30); C.key(pg, 'Enter', wait=250)
        src = pg.evaluate("JSON.parse(localStorage.getItem('ipod.alarm')).source")
        check('a saved playlist can be the alarm', src.startswith('playlist:') and 'Never Played' in pg.inner_text('#body'), (src, pg.inner_text('#body')))
        check('no page errors', not errors, errors)

        # volume: in the iPhone app the wheel drives the system volume
        pg2 = ctx.new_page()
        pg2.add_init_script("window.__vol=[];window.webkit={messageHandlers:{ipodVolume:{postMessage:m=>__vol.push(m)}}}")
        pg2.goto(url); pg2.wait_for_timeout(1500)
        check('the page asks the app for the system volume', {'get': True} in pg2.evaluate('__vol'), pg2.evaluate('__vol'))
        pg2.evaluate('ipodSystemVolume(0.5)'); C.home(pg2); C.choose(pg2, 'Music'); C.choose(pg2, 'Shuffle Songs'); pg2.wait_for_timeout(500)
        pg2.evaluate('__vol.length=0'); C.key(pg2, 'ArrowDown', 2, wait=80)
        sets = [m['set'] for m in pg2.evaluate('__vol') if 'set' in m]
        check('spinning on Now Playing sets the system volume', sets and abs(sets[-1] - 0.625) < 1e-6, sets)
        check('the volume bar shows it', abs(float(pg2.evaluate("parseFloat(document.getElementById('vbi').style.width)")) - 62.5) < .1)
        pg2.wait_for_timeout(500); pg2.evaluate('ipodSystemVolume(0.25)'); pg2.wait_for_timeout(100)
        check('the side buttons move the iPod volume bar', abs(float(pg2.evaluate("parseFloat(document.getElementById('vbi').style.width)")) - 25) < .1 and 'showvol' in pg2.get_attribute('#np', 'class'))
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
