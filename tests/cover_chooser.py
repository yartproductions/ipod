"""Cover chooser: Apple Music + Deezer + MusicBrainz side by side, busy retry, manual options.
All services are mocked. Run: python3 tests/cover_chooser.py"""
import sys, os, json, tempfile, subprocess, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cosmetics as C
from playwright.sync_api import sync_playwright
res = []
def check(n, ok, d=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else f'  [{d}]'))
state = {'mb_busy': True, 'mb_hits': 0}
APPLE = C._png((220, 40, 60)); DEEZER = C._png((40, 200, 120)); PHOTO = C._png((30, 30, 200))
def itunes(route):
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(route.request.url).query))
    rows = [{'kind': 'song', 'collectionId': 11, 'collectionName': 'Amber Days', 'artistName': 'Fixture Artist', 'trackName': 'Bare Amber',
             'releaseDate': '2020-05-01', 'artworkUrl100': 'https://is1-ssl.mzstatic.com/image/amber/100x100bb.jpg'},
            {'kind': 'song', 'collectionId': 12, 'collectionName': 'Amber Days (Live)', 'artistName': 'Fixture Artist', 'trackName': 'Bare Amber (Live)',
             'releaseDate': '2021-01-01', 'artworkUrl100': 'https://is1-ssl.mzstatic.com/image/live/100x100bb.jpg'}]
    route.fulfill(status=200, content_type='application/json', body=json.dumps({'results': rows}), headers={'Access-Control-Allow-Origin': '*'})
def deezer(route):
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(route.request.url).query))
    al = {'id': 77, 'title': 'Amber Days', 'release_date': '2020-05-01', 'type': 'album',
          'cover_medium': 'https://cdn-images.dzcdn.net/images/cover/a/250x250.jpg', 'cover_xl': 'https://cdn-images.dzcdn.net/images/cover/a/1000x1000.jpg'}
    data = [{'title': 'Bare Amber', 'artist': {'name': 'Fixture Artist'}, 'album': al}] if '/search?' in route.request.url or 'search?' in route.request.url and 'album?' not in route.request.url else [{**al, 'artist': {'name': 'Fixture Artist'}}]
    route.fulfill(status=200, content_type='text/javascript', body=f"{q['callback']}({json.dumps({'data': data})})")
def mb(route):
    state['mb_hits'] += 1
    if state['mb_busy']: return route.fulfill(status=503, body='busy', headers={'Access-Control-Allow-Origin': '*'})
    return C.mb_route(route)
srv, url = C.serve()
bare = os.path.join(tempfile.mkdtemp(), 'bare-amber.mp3')
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(C.FIX / 'album-amber-days.mp3'), '-map', '0:a', '-c', 'copy',
                '-metadata', 'title=Bare Amber', '-metadata', 'artist=Fixture Artist', '-metadata', 'album=Amber Days', bare], check=True)
photo = os.path.join(tempfile.mkdtemp(), 'photo.jpg'); open(photo, 'wb').write(PHOTO)
def caption(pg): return pg.inner_text('.covercap') if pg.query_selector('.covercap') else ''
def tiles(pg): return pg.evaluate("[...document.querySelectorAll('.covergrid .ct')].length")
def walk_to(pg, text, limit=30):
    for _ in range(limit):
        if text in caption(pg): return True
        C.key(pg, 'ArrowDown', wait=60)
    return text in caption(pg)
def walk_back(pg):
    for _ in range(30): C.key(pg, 'ArrowUp', wait=30)
def art_state(pg):
    return pg.evaluate('''new Promise(res=>{const r=indexedDB.open("ipod");r.onsuccess=()=>{const q=r.result.transaction("songs").objectStore("songs").getAll();
        q.onsuccess=()=>res(q.result.filter(s=>s.title==="Bare Amber").map(s=>[!!s.art,s.artSource||'',s.artworkUrl||'']))}})''')
def open_chooser(pg):
    C.home(pg); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Bare Amber'); pg.wait_for_timeout(600)
    C.key(pg, 'Enter', wait=80); C.key(pg, 'Enter', wait=450)
    C.choose(pg, 'Repair Artwork'); C.choose(pg, 'Choose Album Cover')
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True, args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'],
                                               viewport={'width': 390, 'height': 760}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort())
    ctx.route('https://itunes.apple.com/**', itunes)
    ctx.route('https://is1-ssl.mzstatic.com/**', lambda r: r.fulfill(status=200, content_type='image/jpeg', body=APPLE, headers={'Access-Control-Allow-Origin': '*'}))
    ctx.route('https://api.deezer.com/**', deezer)
    # Simulate a host that lets the grid show the picture but blocks saving the file (a CORS failure looks like a network error).
    ctx.route('https://cdn-images.dzcdn.net/**', lambda r: r.abort() if r.request.resource_type == 'fetch' else r.fulfill(status=200, content_type='image/jpeg', body=DEEZER))
    ctx.route('https://musicbrainz.org/**', mb)
    ctx.route('https://coverartarchive.org/**', C.caa_route)
    pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(url); pg.wait_for_timeout(800)
    pg.evaluate("localStorage.setItem('ipod.settings',JSON.stringify(Object.assign(JSON.parse(localStorage.getItem('ipod.settings')||'{}'),{autoArt:false})))")
    pg.reload(); pg.wait_for_timeout(800)
    pg.set_input_files('#file', [bare]); C.wait_sync(pg); pg.wait_for_timeout(500)
    open_chooser(pg)
    check('chooser opens as a cover grid right away', pg.text_content('#htitle') == 'Choose a Cover' and tiles(pg) > 0, pg.inner_text('#body'))
    pg.wait_for_timeout(1500)
    allcaps = []
    for _ in range(14):
        allcaps.append(caption(pg)); C.key(pg, 'ArrowDown', wait=50)
    blob = ' | '.join(allcaps); walk_back(pg)
    check('Apple Music covers listed', 'Apple Music' in blob, blob)
    check('Deezer covers listed', 'Deezer' in blob, blob)
    check('live/other editions offered too, not only the exact match', 'Amber Days (Live)' in blob, blob)
    check('best match first (album + artist match)', 'Amber Days' in allcaps[0] and '(Live)' not in allcaps[0], allcaps[0])
    check('manual options: photos, image link, different words', all(x in blob for x in ('Choose From Photos', 'Paste Image Link', 'Search Different Words')), blob)
    pg.wait_for_timeout(6000)  # MusicBrainz retries twice, then gives up
    check('busy MusicBrainz shows a Retry tile instead of failing everything', walk_to(pg, 'Retry MusicBrainz'), caption(pg))
    check('MusicBrainz was retried before giving up', state['mb_hits'] >= 3, state['mb_hits'])
    state['mb_busy'] = False
    C.key(pg, 'Enter', wait=3000); walk_back(pg)
    caps = []
    for _ in range(14): caps.append(caption(pg)); C.key(pg, 'ArrowDown', wait=40)
    walk_back(pg)
    check('Retry brings in MusicBrainz covers', any('MusicBrainz' in c for c in caps), caps)
    # pick the Apple Music cover
    walk_to(pg, 'Apple Music'); C.key(pg, 'Enter', wait=1500)
    check('choosing a cover saves the image on the device', art_state(pg) == [[True, 'manual', '']], art_state(pg))
    check('confirmation names the source', 'Apple Music' in pg.inner_text('#body'), pg.inner_text('#body'))
    C.key(pg, 'Enter', wait=200)   # close message
    # Deezer image host blocks saving -> link fallback
    walk_back(pg); walk_to(pg, 'Deezer'); C.key(pg, 'Enter', wait=1500)
    st = art_state(pg)
    check('a host that blocks saving still works (cover linked)', st and st[0][1] == 'manual' and 'dzcdn' in st[0][2] and 'Linked' in pg.inner_text('#body'), (st, pg.inner_text('#body')))
    C.key(pg, 'Enter', wait=200)
    # choose from photos
    walk_back(pg); walk_to(pg, 'Choose From Photos')
    with pg.expect_file_chooser() as fc: C.key(pg, 'Enter', wait=100)
    fc.value.set_files(photo); pg.wait_for_timeout(1500)
    st = art_state(pg)
    check('Choose From Photos saves your own image', st == [[True, 'manual', '']] and 'your photos' in pg.inner_text('#body'), (st, pg.inner_text('#body')))
    C.key(pg, 'Enter', wait=200)
    # search different words
    walk_back(pg); walk_to(pg, 'Search Different Words'); C.key(pg, 'Enter', wait=200)
    check('Search Different Words pre-fills artist – album', 'Fixture Artist' in pg.input_value('#inpt'), pg.input_value('#inpt'))
    pg.fill('#inpt', 'Fixture Artist – Amber Days'); C.key(pg, 'Enter', wait=1500)
    check('new search opens a fresh grid (no stacked duplicates)', pg.text_content('#htitle') == 'Choose a Cover', pg.text_content('#htitle'))
    C.key(pg, 'Escape', wait=200)
    check('Menu goes back to Repair Artwork', pg.text_content('#htitle') == 'Repair Artwork', pg.text_content('#htitle'))
    # tap a tile to select, tap again to choose
    C.key(pg, 'Escape', wait=100); C.choose(pg, 'Repair Artwork'); C.choose(pg, 'Choose Album Cover'); pg.wait_for_timeout(1500)
    t = pg.locator('.covergrid .ct').nth(1); t.click(); pg.wait_for_timeout(150)
    check('tapping a tile selects it', pg.evaluate("document.querySelectorAll('.covergrid .ct')[1].classList.contains('sel')"))
    pg.screenshot(path=os.environ.get('SHOT', '/tmp/covers.png'), clip={'x': 0, 'y': 0, 'width': 390, 'height': 330})
    check('no page errors', not errs, errs)
    ctx.close()
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)
