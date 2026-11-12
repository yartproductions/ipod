#!/usr/bin/env python3
"""Headless browser tests for the iPod web app.

Run from the repo root:   python3 tests/e2e.py
Needs: Python Playwright and a Chromium/Chrome (set CHROME=/path/to/chrome if not at /usr/bin/google-chrome).

These cover what a desktop browser can verify. Real Taptic Engine output, iPhone Safari,
Home Screen mode and lock-screen behaviour still need a physical iPhone (see README).
"""
import functools, http.server, math, os, socketserver, sys, tempfile, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / 'tests' / 'fixtures'
CHROME = os.environ.get('CHROME', '/usr/bin/google-chrome')

# Stand-in for https://www.youtube.com/iframe_api: records every player call, becomes ready after 600 ms.
YT_STUB = """
window.__yt = [];
window.YT = { Player: function(id, opts){
  const rec = (n) => (...a) => { window.__yt.push([n, ...a]); };
  let state = -1;
  const p = { loadVideoById: (...a)=>{window.__yt.push(['loadVideoById',...a]); state=1;},
              cueVideoById: rec('cueVideoById'), loadPlaylist: (...a)=>{window.__yt.push(['loadPlaylist',...a]); state=1;},
              stopVideo: ()=>{window.__yt.push(['stopVideo']); state=5;}, pauseVideo: ()=>{window.__yt.push(['pauseVideo']); state=2;},
              playVideo: ()=>{window.__yt.push(['playVideo']); state=1;}, getPlayerState: ()=>state,
              getCurrentTime: ()=>0, getDuration: ()=>200, getVolume: ()=>100, setVolume: rec('setVolume'), unMute: rec('unMute'),
              seekTo: rec('seekTo'), getVideoData: ()=>({title:'Stub Video', author:'Stub Channel'}),
              nextVideo: rec('nextVideo'), previousVideo: rec('previousVideo') };
  setTimeout(()=>opts.events.onReady({target:p}), window.__ytDelay||600);
  return p;
}};
setTimeout(()=>window.onYouTubeIframeAPIReady && window.onYouTubeIframeAPIReady(), 0);
"""

# ---------- Audius stand-in (same JSON shape as https://api.audius.co/v1) ----------
import io, json, urllib.parse
from PIL import Image
_buf = io.BytesIO(); Image.new('RGB', (48, 48), (200, 60, 90)).save(_buf, 'JPEG'); ART = _buf.getvalue()
MP3 = [(FIX / f'song{i}.mp3').read_bytes() for i in (1, 2, 3)]

DOWNLOADABLE = {'T1', 'T4', 'T101'}   # tracks whose artists allow downloads
def au_track(n, genre='Electronic', **kw):
    t = {'id': f'T{n}', 'title': f'Stream Song {n}', 'duration': 2, 'genre': genre, 'is_streamable': True,
         'is_stream_gated': False, 'user': {'name': f'Artist {n}', 'handle': f'artist{n}'},
         'artwork': {'150x150': f'https://img.audius.test/{n}/150.jpg', '480x480': f'https://img.audius.test/{n}/480.jpg'}}
    t['is_downloadable'] = f'T{n}' in DOWNLOADABLE
    t.update(kw); return t
# 30 trending tracks; 3 of them can't be streamed for free and must be hidden
TRENDING = [au_track(n) for n in range(1, 31)]
TRENDING[2]['is_stream_gated'] = True; TRENDING[5]['is_streamable'] = False; TRENDING[26]['is_stream_gated'] = True
PLAYLISTS = [{'id': 'P1', 'playlist_name': 'Chill Mix', 'user': {'name': 'Curator'}}, {'id': 'P2', 'playlist_name': 'Gym', 'user': {'name': 'Coach'}}]
PL_TRACKS = {'P1': [au_track(101, title='Chill One'), au_track(102, title='Chill Two'), au_track(103, title='Chill Paid', is_stream_gated=True)]}
au_requests = []
DL_HOLD = []          # routes held open to test cancelling a download

def audius_route(route):
    u = urllib.parse.urlparse(route.request.url); q = dict(urllib.parse.parse_qsl(u.query)); path = u.path[len('/v1'):]
    au_requests.append((path, q))
    def ok(data): return route.fulfill(status=200, content_type='application/json', body=json.dumps({'data': data}),
                                       headers={'Access-Control-Allow-Origin': '*'})
    off, lim = int(q.get('offset', 0)), int(q.get('limit', 25))
    if path.endswith('/download'):
        tid = path.split('/')[2]
        if tid == 'T4': return route.fulfill(status=500, body='boom')
        if tid == 'T101': DL_HOLD.append(route); return          # never answers until the test aborts it
        if tid not in DOWNLOADABLE: return route.fulfill(status=403, body='not downloadable')
        body = MP3[int(tid[1:]) % 3]
        return route.fulfill(status=200, content_type='audio/mpeg', body=body,
                             headers={'Access-Control-Allow-Origin': '*', 'Content-Length': str(len(body))})
    if path.endswith('/stream'):
        tid = path.split('/')[2]
        if tid == 'Tbroken': return route.fulfill(status=404, body='not found')
        n = int(''.join(c for c in tid if c.isdigit()) or 0)
        return route.fulfill(status=200, content_type='audio/mpeg', body=MP3[n % 3], headers={'Access-Control-Allow-Origin': '*'})
    if path == '/tracks/trending':
        if q.get('genre'): return ok([au_track(200 + i, genre=q['genre'], title=f"{q['genre']} Hit {i}") for i in range(3)][off:off + lim])
        return ok(TRENDING[off:off + lim])
    if path == '/tracks/search':
        if q.get('query') == 'broken': return ok([au_track('broken', title='Broken Song'), au_track(2)][off:off + lim])
        return ok([au_track(300 + i, title=f"{q.get('query')} {i}") for i in range(3)][off:off + lim] if off == 0 else [])
    if path in ('/playlists/search', '/playlists/trending'): return ok(PLAYLISTS)
    if path.startswith('/playlists/') and path.endswith('/tracks'): return ok(PL_TRACKS.get(path.split('/')[2], []))
    return route.fulfill(status=404, body='{}')

BRIDGE = ("window.__haptics=[];window.__hapticRaw=[];window.webkit={messageHandlers:{ipodHaptics:{postMessage:m=>{"
          "window.__hapticRaw.push(m);window.__haptics.push(typeof m==='string'?m:m.kind)}}}};")
VIBRATE = "window.__vib=[];navigator.vibrate=p=>{window.__vib.push(p);return true};"

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{detail}]' if detail and not cond else ''))

def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    handler = functools.partial(Quiet, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}/'

def rows(pg):  return pg.eval_on_selector_all('#body .row', 'els=>els.map(e=>e.childNodes[0].textContent)')
def sel(pg):   return pg.eval_on_selector('#body .row.sel', 'e=>e.childNodes[0].textContent')
def title(pg): return pg.text_content('#htitle')
def key(pg, k, n=1, wait=60):
    for _ in range(n): pg.keyboard.press(k); pg.wait_for_timeout(wait)
def to_top(pg):
    for _ in range(80):
        before = sel(pg); pg.keyboard.press('ArrowUp')
        if sel(pg) == before: return
def all_rows(pg):
    """Every row in the current list (the screen shows only 7), leaving the selection at the top."""
    to_top(pg); out = [sel(pg)]
    for _ in range(200):
        pg.keyboard.press('ArrowDown')
        if sel(pg) == out[-1]: break
        out.append(sel(pg))
    to_top(pg); return out
def choose(pg, label):
    """Move the selection to `label` anywhere in the list and press select."""
    if label in rows(pg):
        for _ in range(10):
            if sel(pg) == label: break
            key(pg, 'ArrowDown' if rows(pg).index(label) > rows(pg).index(sel(pg)) else 'ArrowUp', wait=20)
    else:
        to_top(pg)
        for _ in range(200):
            if sel(pg) == label: break
            before = sel(pg); pg.keyboard.press('ArrowDown')
            if sel(pg) == before: break
    if sel(pg) != label: raise AssertionError(f'could not reach {label!r}; rows={rows(pg)}')
    key(pg, 'Enter', wait=250)
def back_to_main(pg):
    for _ in range(8):
        if title(pg) == 'iPod': return
        key(pg, 'Escape', wait=120)

def spin(pg, degrees, step=5, pause=45):
    """Drag a finger around the click wheel ring, clockwise for positive degrees."""
    box = pg.locator('#wheel').bounding_box()
    cx, cy, r = box['x'] + box['width']/2, box['y'] + box['height']/2, box['width']*0.40
    a = -90.0
    pg.mouse.move(cx + r*math.cos(math.radians(a)), cy + r*math.sin(math.radians(a))); pg.mouse.down()
    for _ in range(int(abs(degrees)/step)):
        a += step if degrees > 0 else -step
        pg.mouse.move(cx + r*math.cos(math.radians(a)), cy + r*math.sin(math.radians(a))); pg.wait_for_timeout(pause)
    pg.mouse.up()

def tap_center(pg):
    pg.locator('#center').dispatch_event('pointerdown'); pg.locator('#center').dispatch_event('pointerup')

def main():
    srv, url = serve()
    profile = tempfile.mkdtemp()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, executable_path=CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844})
        ctx.route('https://api.audius.co/v1/**', audius_route)
        ctx.route('https://img.audius.test/**', lambda r: r.fulfill(status=200, content_type='image/jpeg', body=ART))
        ctx.route('https://www.youtube.com/iframe_api', lambda r: r.fulfill(status=200, content_type='text/javascript', body=YT_STUB))
        errors = []

        # ---------- 1. navigation + native haptic bridge ----------
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script(BRIDGE)
        pg.goto(url); pg.wait_for_timeout(1500)
        check('main menu shows Ad-Free Local Music entry', 'Ad-Free Local Music' in rows(pg), rows(pg))
        check('main menu has Audius (Ad-Free) streaming', 'Audius (Ad-Free)' in rows(pg), rows(pg))
        check('YouTube is hidden from the main menu by default', not any('YouTube' in x for x in rows(pg)), rows(pg))

        spin(pg, 90)  # 6 detents of 15 degrees
        h = pg.evaluate('window.__haptics')
        check('wheel spin moves selection', sel(pg) != 'Ad-Free Local Music', sel(pg))
        check('wheel spin sends selection haptics to native bridge', len(h) >= 4 and set(h) == {'selection'}, h)

        spin(pg, -720, pause=10)  # back to top quickly; throttling may drop some
        pg.evaluate('window.__haptics=[]')
        choose(pg, 'Settings'); pg.evaluate('window.__haptics=[]')
        choose(pg, 'Test Haptic'); pg.wait_for_timeout(50)
        h = pg.evaluate('window.__haptics')
        check('Test Haptic sends exactly one "success"', h[-1:] == ['success'] and h.count('success') == 1 and 'confirm' not in h, h)

        pg.evaluate('window.__haptics=[]'); tap_center(pg); pg.wait_for_timeout(50)
        h = pg.evaluate('window.__haptics')
        check('center on Test Haptic coalesces to a single haptic', h == ['success'], h)
        choose(pg, 'Color'); pg.evaluate('window.__haptics=[]'); tap_center(pg); pg.wait_for_timeout(50)
        check('center button sends one "confirm" (no double haptic)', pg.evaluate('window.__haptics') == ['confirm'], pg.evaluate('window.__haptics'))
        tap_center(pg)  # restore colour
        pg.wait_for_timeout(100)
        pg.evaluate('window.__haptics=[]'); key(pg, 'Escape', wait=150)
        check('MENU press sends "selection"', pg.evaluate('window.__haptics') == ['selection'], pg.evaluate('window.__haptics'))

        # ---- strength / feel are adjustable and reach the native bridge ----
        choose(pg, 'Settings')
        raw = lambda: pg.evaluate('window.__hapticRaw')
        pg.evaluate('window.__hapticRaw=[]'); key(pg, 'ArrowDown', wait=80); key(pg, 'ArrowUp', wait=80)
        m = raw()[-1]
        check('bridge message carries intensity + sharpness (default Strong / Crisp)',
              isinstance(m, dict) and m.get('kind') == 'selection' and m.get('intensity') == 0.9 and m.get('sharpness') == 0.95, m)
        choose(pg, 'Haptic Strength'); pg.wait_for_timeout(200)       # Strong -> Max
        check('Haptic Strength cycles to Max', 'Max' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.evaluate('window.__hapticRaw=[]'); key(pg, 'ArrowDown', wait=80)
        check('Max strength sends intensity 1.0', raw()[-1].get('intensity') == 1, raw())
        for _ in range(3): choose(pg, 'Haptic Strength'); pg.wait_for_timeout(150)   # Max -> Light -> Medium -> Strong
        choose(pg, 'Haptic Feel'); pg.wait_for_timeout(200)          # Crisp -> Click
        check('Haptic Feel cycles to Click', 'Click' in pg.inner_text('#body'))
        pg.evaluate('window.__hapticRaw=[]'); key(pg, 'ArrowDown', wait=80)
        check('feel changes sharpness', raw()[-1].get('sharpness') == 0.7, raw())
        for _ in range(3): choose(pg, 'Haptic Feel'); pg.wait_for_timeout(150)       # back to Crisp
        pg.evaluate('window.__hapticRaw=[]'); choose(pg, 'Test Haptic'); pg.wait_for_timeout(50)
        check('Test Haptic sends a double tap (count 2)', raw()[-1].get('count') == 2, raw())
        back_to_main(pg)

        choose(pg, 'Settings'); choose(pg, 'Haptics')  # turn off
        pg.evaluate('window.__haptics=[]'); key(pg, 'ArrowDown'); key(pg, 'ArrowUp')
        check('Haptics Off silences the bridge', pg.evaluate('window.__haptics') == [])
        choose(pg, 'Haptics')  # back on
        back_to_main(pg); choose(pg, 'About')
        check('About reports Native haptics when bridge exists', 'Native' in pg.inner_text('#body'), pg.inner_text('#body'))
        back_to_main(pg); pg.close()

        # ---------- 2. browser fallback ----------
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script(VIBRATE); pg.goto(url); pg.wait_for_timeout(800)
        key(pg, 'ArrowDown', wait=80)
        check('without bridge, falls back to navigator.vibrate (length follows strength)', pg.evaluate('window.__vib') == [15], pg.evaluate('window.__vib'))
        check('no hidden <input switch> elements are created', pg.evaluate('document.querySelectorAll("input[switch]").length') == 0)
        pg.close()

        # ---------- 3. local import, tags, persistence ----------
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(800)
        pg.set_input_files('#file', [str(FIX / f'song{i}.mp3') for i in (1, 2, 3)]); pg.wait_for_timeout(1500)
        check('import reports 3 songs added', '3 songs added' in pg.inner_text('#body'), pg.inner_text('#body'))
        key(pg, 'Enter', wait=200); choose(pg, 'Ad-Free Local Music')
        check('local music menu title', title(pg) == 'Local Music', title(pg))
        choose(pg, 'Songs')
        check('ID3 titles read', rows(pg) == ['Test Song 1', 'Test Song 2', 'Test Song 3'], rows(pg))
        key(pg, 'Escape', wait=150); choose(pg, 'Artists')
        check('artists grouped from ID3', rows(pg) == ['Other Artist', 'Test Artist'], rows(pg))
        pg.reload(); pg.wait_for_timeout(1500)
        choose(pg, 'Ad-Free Local Music'); choose(pg, 'Songs')
        check('library persists after reload (IndexedDB)', len(rows(pg)) == 3, rows(pg))

        # ---------- 4. playback, repeat, media session, no YouTube autoplay ----------
        pg.evaluate('window.__yt=window.__yt||[]')
        choose(pg, 'Test Song 1'); pg.wait_for_timeout(700)
        check('local song opens Now Playing', title(pg) == 'Now Playing' and pg.text_content('.np .t') == 'Test Song 1')
        check('embedded album art shown', 'blob:' in (pg.get_attribute('.np .art', 'style') or ''))
        check('header shows play icon while playing', '<path' in pg.inner_html('#pi'), pg.inner_html('#pi'))
        md = pg.evaluate('navigator.mediaSession.metadata && [navigator.mediaSession.metadata.title, navigator.mediaSession.metadata.artist]')
        check('lock-screen metadata set (Media Session)', md == ['Test Song 1', 'Test Artist'], md)
        yt_calls = [c[0] for c in pg.evaluate('window.__yt')]
        check('local playback never loads/plays YouTube', not any(c in ('loadVideoById', 'loadPlaylist', 'playVideo', 'cueVideoById') for c in yt_calls), yt_calls)
        pg.wait_for_timeout(2600)
        check('auto-advances to next song when one ends', pg.text_content('.np .t') == 'Test Song 2', pg.text_content('.np .t'))
        key(pg, 'ArrowRight', wait=400)
        check('next button skips', pg.text_content('.np .t') == 'Test Song 3')
        pg.wait_for_timeout(2600)
        check('repeat Off stops after last song', pg.text_content('.np .t') == 'Test Song 3' and '<rect' in pg.inner_html('#pi'), pg.inner_html('#pi'))

        back_to_main(pg); choose(pg, 'Settings'); choose(pg, 'Repeat'); choose(pg, 'Repeat')  # Off -> One -> All
        check('repeat cycles to All', 'All' in pg.inner_text('#body'))
        back_to_main(pg); choose(pg, 'Ad-Free Local Music'); choose(pg, 'Songs'); choose(pg, 'Test Song 3'); pg.wait_for_timeout(2800)
        check('repeat All wraps to first song', pg.text_content('.np .t') == 'Test Song 1', pg.text_content('.np .t'))

        back_to_main(pg); choose(pg, 'Settings'); choose(pg, 'Shuffle')
        back_to_main(pg); choose(pg, 'Ad-Free Local Music'); choose(pg, 'Songs'); choose(pg, 'Test Song 2'); pg.wait_for_timeout(400)
        check('shuffle starts with the chosen song', pg.text_content('.np .t') == 'Test Song 2' and '1 of 3' in pg.inner_text('.np'))
        back_to_main(pg); choose(pg, 'Settings'); choose(pg, 'Shuffle'); choose(pg, 'Repeat')
        back_to_main(pg); pg.close()

        # ---------- 5. YouTube still works, and a stale queued load never autoplays ----------
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(1200)   # stub becomes ready after 600 ms
        choose(pg, 'Settings'); choose(pg, 'YouTube (Has Ads)'); back_to_main(pg)
        check('Settings toggle brings YouTube back, labelled as having ads', 'YouTube (Has Ads)' in rows(pg), rows(pg))
        choose(pg, 'YouTube (Has Ads)'); choose(pg, 'Paste Link'); pg.keyboard.type('https://youtu.be/dQw4w9WgXcQ'); key(pg, 'Enter', wait=400)
        calls = pg.evaluate('window.__yt')
        check('Paste Link loads the official embed', ['loadVideoById', 'dQw4w9WgXcQ'] in calls, calls)
        check('video view shown for YouTube', pg.evaluate('document.getElementById("screen").classList.contains("video")'))
        key(pg, 'Escape', wait=500)
        check('leaving the video pauses it (embed must stay visible)', ['pauseVideo'] in pg.evaluate('window.__yt'))
        pg.close()

        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script('window.__ytDelay=5000')
        pg.goto(url); pg.wait_for_timeout(150)    # player NOT ready for 5 s
        choose(pg, 'YouTube (Has Ads)'); choose(pg, 'Paste Link'); pg.keyboard.type('youtu.be/dQw4w9WgXcQ'); key(pg, 'Enter', wait=10)
        back_to_main(pg); choose(pg, 'Ad-Free Local Music'); choose(pg, 'Songs'); choose(pg, 'Test Song 1')
        check('YouTube player was still loading when local song started', pg.evaluate('window.__yt.length') == 0)
        pg.wait_for_timeout(5500)                 # player becomes ready, queued load would fire here
        calls = [c[0] for c in pg.evaluate('window.__yt')]
        check('queued YouTube load is dropped once local music starts', 'loadVideoById' not in calls and 'playVideo' not in calls, calls)
        check('still on local Now Playing (no switch to video) after YouTube becomes ready',
              title(pg) == 'Now Playing' and not pg.evaluate('document.getElementById("screen").classList.contains("video")')
              and (pg.text_content('.np .t') or '').startswith('Test Song'))
        pg.close()

        # ---------- 6. Audius ad-free streaming ----------
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("localStorage.setItem('ipod.settings', JSON.stringify(Object.assign(JSON.parse(localStorage.getItem('ipod.settings')||'{}'),{showYouTube:false})))")
        pg.goto(url); pg.wait_for_timeout(1000); pg.evaluate('window.__yt=window.__yt||[]')
        choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Trending'); pg.wait_for_timeout(500)
        r0 = all_rows(pg)
        check('Trending lists Play All / Shuffle', r0[:2] == ['Play All', 'Shuffle'], r0[:3])
        tracks = [x for x in r0 if x.startswith('Stream Song')]
        check('gated / unstreamable tracks are hidden (23 playable of first 25)', len(tracks) == 23 and 'Stream Song 3' not in tracks and 'Stream Song 6' not in tracks, len(tracks))
        check('first page offers More…', r0[-1] == 'More…')
        choose(pg, 'More…'); pg.wait_for_timeout(500)
        r1 = all_rows(pg); tracks = [x for x in r1 if x.startswith('Stream Song')]
        check('More… appends the next page (27 playable of 30) and stops paging', len(tracks) == 27 and 'Stream Song 27' not in tracks and r1[-1] != 'More…', (len(tracks), r1[-1]))
        check('requests identify the app (app_name)', all(q.get('app_name') == 'iPodClassicWeb' for _, q in au_requests))

        au_requests.clear(); choose(pg, 'Stream Song 1'); pg.wait_for_timeout(900)
        check('Audius track opens Now Playing with title and artist',
              pg.text_content('.np .t') == 'Stream Song 1' and pg.text_content('.np .a') == 'Artist 1', pg.inner_text('.np'))
        check('Now Playing credits Audius', 'Audius' in pg.text_content('.np .al'))
        check('artwork shown from Audius', 'img.audius.test/1/480.jpg' in (pg.get_attribute('.np .art', 'style') or ''))
        check('audio streamed from /tracks/{id}/stream', any(pth == '/tracks/T1/stream' for pth, _ in au_requests), au_requests)
        check('header shows playing', '<path' in pg.inner_html('#pi'))
        md = pg.evaluate('[navigator.mediaSession.metadata.title, navigator.mediaSession.metadata.artist, navigator.mediaSession.metadata.artwork.map(a=>a.src).join()]')
        check('lock-screen metadata + artwork for streams', md[0] == 'Stream Song 1' and md[1] == 'Artist 1' and '480.jpg' in md[2], md)
        pg.wait_for_timeout(2600)
        check('stream auto-advances to next track', pg.text_content('.np .t') == 'Stream Song 2', pg.text_content('.np .t'))
        key(pg, 'ArrowRight', wait=500)
        check('next skips over the hidden gated track', pg.text_content('.np .t') == 'Stream Song 4', pg.text_content('.np .t'))
        key(pg, 'ArrowLeft', wait=500)
        check('previous goes back', pg.text_content('.np .t') == 'Stream Song 2', pg.text_content('.np .t'))
        ytc = [c[0] for c in pg.evaluate('window.__yt||[]')]
        check('Audius playback never loads/plays YouTube', not any(c in ('loadVideoById', 'loadPlaylist', 'playVideo', 'cueVideoById') for c in ytc), ytc)

        key(pg, 'Escape', n=2, wait=150); choose(pg, 'Save Now Playing'); key(pg, 'Enter', wait=150)
        choose(pg, 'Search Songs'); pg.keyboard.type('broken'); key(pg, 'Enter', wait=600)
        choose(pg, 'Broken Song'); pg.wait_for_timeout(2600)
        check('unplayable stream is skipped automatically', pg.text_content('.np .t') == 'Stream Song 2', pg.text_content('.np .t'))
        key(pg, 'Escape', n=2, wait=150)
        choose(pg, 'Search Songs'); pg.keyboard.type('lofi'); key(pg, 'Enter', wait=600)
        check('song search returns results (no More… when results are short)', rows(pg)[2:] == ['lofi 0', 'lofi 1', 'lofi 2'], rows(pg))
        key(pg, 'Escape', wait=150)

        choose(pg, 'Search Playlists'); pg.keyboard.type('chill'); key(pg, 'Enter', wait=600)
        check('playlist search lists playlists', rows(pg) == ['Chill Mix', 'Gym'], rows(pg))
        choose(pg, 'Chill Mix'); pg.wait_for_timeout(500)
        check('playlist opens with paid track hidden, no paging', rows(pg) == ['Play All', 'Shuffle', 'Save Playlist', 'Chill One', 'Chill Two'], rows(pg))
        choose(pg, 'Save Playlist'); key(pg, 'Enter', wait=150)
        choose(pg, 'Play All'); pg.wait_for_timeout(700)
        check('Play All plays the playlist', pg.text_content('.np .t') == 'Chill One' and '1 of 2' in pg.inner_text('.np'))
        back_to_main(pg); choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Saved')
        sv = rows(pg)
        check('Saved holds the playlist and the saved song', '▤ Chill Mix' in sv and 'Stream Song 2' in sv, sv)
        key(pg, 'Escape', wait=150); choose(pg, 'Recently Played')
        rp = rows(pg)
        check('Recently Played lists tracks that played, newest first', rp[2] in ('Chill One', 'Chill Two') and 'Stream Song 2' in rp and 'Stream Song 1' in rp, rp)
        check('a track that failed to stream is not in Recently Played', 'Broken Song' not in rp, rp)
        key(pg, 'Escape', wait=150); choose(pg, 'Genres'); choose(pg, 'Lo-Fi'); pg.wait_for_timeout(500)
        check('genre browsing loads trending by genre', 'Lo-Fi Hit 0' in rows(pg), rows(pg))
        check('genre request passes the genre', any(pth == '/tracks/trending' and q.get('genre') == 'Lo-Fi' for pth, q in au_requests))
        back_to_main(pg); choose(pg, 'Ad-Free Local Music'); choose(pg, 'Songs'); choose(pg, 'Test Song 1'); pg.wait_for_timeout(500)
        check('local music still plays after streaming', pg.text_content('.np .t') == 'Test Song 1')
        pg.close()

        # ---------- 7. offline library: migration, dedupe, delete, Save Offline, airplane mode, backup ----------
        import zipfile
        ctx2 = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=CHROME, headless=True,
               args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844},
               accept_downloads=True)
        ctx2.route('https://api.audius.co/v1/**', audius_route)
        ctx2.route('https://img.audius.test/**', lambda r: r.fulfill(status=200, content_type='image/jpeg', body=ART))
        ctx2.route('https://www.youtube.com/iframe_api', lambda r: r.fulfill(status=200, content_type='text/javascript', body=YT_STUB))
        pg = ctx2.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(url + 'tests/fixtures/seed-v1.html'); pg.wait_for_function('document.title==="done"', timeout=10000)
        pg.goto(url); pg.wait_for_timeout(2500)
        dbinfo = lambda: pg.evaluate("""() => new Promise(res => { const r = indexedDB.open('ipod'); r.onsuccess = () => { const d = r.result, st = d.transaction('songs').objectStore('songs');
            const q = st.getAll(); q.onsuccess = () => { res({version: d.version, indexes: [...st.indexNames],
              songs: q.result.map(x => ({id: x.id, title: x.title, size: x.blob && x.blob.size, hash: !!x.hash, source: x.source, sourceId: x.sourceId, status: x.downloadStatus}))}); d.close(); } } })""")
        info = dbinfo()
        check('v1 → v2 upgrade keeps the existing song', [x['title'] for x in info['songs']] == ['Legacy Song'], info)
        check('v2 adds sourceId + hash indexes', info['version'] == 2 and set(info['indexes']) == {'sourceId', 'hash'}, info)
        check('legacy song gets its hash back-filled', info['songs'][0]['hash'], info)
        choose(pg, 'Ad-Free Local Music'); choose(pg, 'Songs')
        check('legacy song is listed and plays', rows(pg) == ['Legacy Song'])
        choose(pg, 'Legacy Song'); pg.wait_for_timeout(500)
        check('legacy song plays from its stored blob', pg.text_content('.np .t') == 'Legacy Song' and '<path' in pg.inner_html('#pi'))
        back_to_main(pg)

        pg.set_input_files('#file', [str(FIX / 'song3.mp3'), str(FIX / 'song1.mp3')]); pg.wait_for_timeout(1500)
        check('duplicate import is skipped (same audio bytes)', '1 song added' in pg.inner_text('#body') and '1 already in your library' in pg.inner_text('#body'), pg.inner_text('#body'))
        key(pg, 'Enter', wait=200)

        # Save Offline from Audius (artist allows downloads)
        choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Downloadable Songs'); pg.keyboard.type('chill'); key(pg, 'Enter', wait=600)
        check('downloadable search asks Audius for only_downloadable', any(q.get('only_downloadable') == 'true' for _, q in au_requests))
        back_to_main(pg); choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Trending'); pg.wait_for_timeout(500)
        choose(pg, 'Stream Song 1'); pg.wait_for_timeout(500); key(pg, ' ', wait=100)   # pause so the 2-second test song doesn't advance
        back_to_main(pg); choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Save Now Playing Offline'); pg.wait_for_timeout(1500)
        check('Save Offline completes', 'Download Complete' in pg.inner_text('#body'), pg.inner_text('#body'))
        info = dbinfo(); dl = [x for x in info['songs'] if x['source'] == 'audius-download']
        check('downloaded song stored with real audio bytes + source id', len(dl) == 1 and dl[0]['sourceId'] == 'audius:T1' and dl[0]['size'] == len(MP3[1]) and dl[0]['status'] == 'complete', dl)
        key(pg, 'Enter', wait=200); choose(pg, 'Save Now Playing Offline'); pg.wait_for_timeout(300)
        check('saving again says it is already offline (no re-download)', 'Available Offline' in pg.inner_text('#body'))
        key(pg, 'Enter', wait=200); back_to_main(pg)
        choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Trending'); pg.wait_for_timeout(500)
        check('saved track shows ✓ in Audius lists', '✓' in pg.inner_text('#body'))
        choose(pg, 'Stream Song 2'); pg.wait_for_timeout(400); key(pg, ' ', wait=100)
        back_to_main(pg); choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Save Now Playing Offline'); pg.wait_for_timeout(500)
        check('non-downloadable track is refused', 'Not Downloadable' in pg.inner_text('#body'), pg.inner_text('#body'))
        key(pg, 'Enter', wait=200); back_to_main(pg)
        n_before = len(dbinfo()['songs'])
        choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Trending'); pg.wait_for_timeout(500); choose(pg, 'Stream Song 4'); pg.wait_for_timeout(300); key(pg, ' ', wait=100)
        back_to_main(pg); choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Save Now Playing Offline'); pg.wait_for_timeout(1200)
        check('server error → Download Failed, nothing saved', 'Download Failed' in pg.inner_text('#body') and len(dbinfo()['songs']) == n_before, pg.inner_text('#body'))
        key(pg, 'Enter', wait=200); back_to_main(pg)
        choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Search Playlists'); pg.keyboard.type('x'); key(pg, 'Enter', wait=500)
        choose(pg, 'Chill Mix'); pg.wait_for_timeout(400); choose(pg, 'Chill One'); pg.wait_for_timeout(300); key(pg, ' ', wait=100)
        back_to_main(pg); choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Save Now Playing Offline'); pg.wait_for_timeout(600)
        check('download shows progress state while waiting', 'Preparing audio' in pg.inner_text('#body') and 'MENU to cancel' in pg.inner_text('#body'), pg.inner_text('#body'))
        key(pg, 'Escape', wait=500)
        check('MENU cancels the download, nothing saved', 'Download Cancelled' in pg.inner_text('#body') and len(dbinfo()['songs']) == n_before, pg.inner_text('#body'))
        for rt in DL_HOLD:
            try: rt.abort()
            except Exception: pass
        key(pg, 'Enter', wait=200); back_to_main(pg)

        # Delete a song
        choose(pg, 'Settings'); choose(pg, 'Library & Storage')
        check('Library & Storage shows usage', 'Storage Used' in pg.inner_text('#body'))
        choose(pg, 'Delete Songs'); choose(pg, 'Test Song 1'); choose(pg, 'Delete “Test Song 1”'); pg.wait_for_timeout(300)
        check('deleted song disappears from the list', 'Test Song 1' not in all_rows(pg), all_rows(pg))
        check('deleted song is gone from IndexedDB', 'Test Song 1' not in [x['title'] for x in dbinfo()['songs']])
        back_to_main(pg)

        # Airplane mode: the app opens from the service worker and saved songs play
        pg.evaluate('navigator.serviceWorker.ready.then(()=>true)'); pg.reload(); pg.wait_for_timeout(1500)
        ctx2.set_offline(True)
        pg.reload(); pg.wait_for_timeout(1500)
        check('app opens with no network (service worker)', title(pg) == 'iPod' and 'Ad-Free Local Music' in rows(pg), rows(pg))
        choose(pg, 'Ad-Free Local Music'); choose(pg, 'Songs'); choose(pg, 'Stream Song 1'); pg.wait_for_timeout(900)
        check('downloaded song plays offline', pg.text_content('.np .t') == 'Stream Song 1' and '<path' in pg.inner_html('#pi'), pg.inner_html('#pi'))
        back_to_main(pg); choose(pg, 'Audius (Ad-Free)'); choose(pg, 'Trending'); pg.wait_for_timeout(500)
        check('Audius browsing explains it is offline', 'offline' in pg.inner_text('#body').lower(), pg.inner_text('#body'))
        key(pg, 'Escape', wait=150); choose(pg, 'Recently Played'); choose(pg, 'Stream Song 2'); pg.wait_for_timeout(400)
        check('unsaved stream says Unavailable Offline', 'Unavailable Offline' in pg.inner_text('#body'), pg.inner_text('#body'))
        ctx2.set_offline(False); back_to_main(pg)

        # Backup → clear → restore → restore again (duplicates skipped)
        expected = sorted(x['title'] for x in dbinfo()['songs'])
        choose(pg, 'Settings'); choose(pg, 'Library & Storage')
        with pg.expect_download() as dlinfo: choose(pg, 'Back Up Library')
        bk = tempfile.mktemp(suffix='.zip'); dlinfo.value.save_as(bk); pg.wait_for_timeout(300)
        check('backup reports ready', 'Backup Ready' in pg.inner_text('#body'), pg.inner_text('#body'))
        z = zipfile.ZipFile(bk); man = json.loads(z.read('manifest.json'))
        check('backup ZIP is valid (CRC checks pass)', z.testzip() is None)
        check('manifest is versioned and lists every song', man['format'] == 'ipod-library-backup' and man['version'] == 1 and sorted(s_['title'] for s_ in man['songs']) == expected, man.get('songs'))
        check('backup holds the original audio bytes', z.read([s_ for s_ in man['songs'] if s_['title'] == 'Stream Song 1'][0]['audio']) == MP3[1])
        check('backup includes Audius saved playlists/songs', isinstance(man['audius']['saved'], list))
        key(pg, 'Enter', wait=200); choose(pg, 'Clear Library'); choose(pg, 'Erase All Songs'); pg.wait_for_timeout(500)
        check('library cleared', dbinfo()['songs'] == [])
        pg.set_input_files('#restore', bk); pg.wait_for_timeout(2500)
        check('restore brings every song back', 'Restore Complete' in pg.inner_text('#body') and sorted(x['title'] for x in dbinfo()['songs']) == expected, (pg.inner_text('#body'), dbinfo()['songs']))
        key(pg, 'Enter', wait=200)
        pg.set_input_files('#restore', bk); pg.wait_for_timeout(2500)
        check('restoring twice adds no duplicates', 'already in your library' in pg.inner_text('#body') and len(dbinfo()['songs']) == len(expected), pg.inner_text('#body'))
        key(pg, 'Enter', wait=200)
        junk = tempfile.mktemp(suffix='.zip'); Path(junk).write_bytes(b'not a zip at all' * 100)
        pg.set_input_files('#restore', junk); pg.wait_for_timeout(800)
        check('invalid backup is rejected without changes', 'Restore Failed' in pg.inner_text('#body') and len(dbinfo()['songs']) == len(expected), pg.inner_text('#body'))
        key(pg, 'Enter', wait=200); back_to_main(pg)
        choose(pg, 'Ad-Free Local Music'); choose(pg, 'Songs'); choose(pg, 'Stream Song 1'); pg.wait_for_timeout(700)
        check('restored song plays', pg.text_content('.np .t') == 'Stream Song 1' and '<path' in pg.inner_html('#pi'))
        pg.reload(); pg.wait_for_timeout(1500)
        check('library survives a reload', sorted(x['title'] for x in dbinfo()['songs']) == expected)
        pg.close(); ctx2.close()

        check('no uncaught page errors', not errors, errors)
        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} passed')
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
