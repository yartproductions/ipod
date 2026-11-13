#!/usr/bin/env python3
"""Headless checks for the cosmetic / feel features: colours, Hold switch, backlight, fast scroll,
generated album art + Albums thumbnails, Clock and Brick.   Run: python3 tests/cosmetics.py"""
import functools, http.server, os, socketserver, sys, tempfile, threading, math
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / 'tests' / 'fixtures'
CHROME = os.environ.get('CHROME', '/usr/bin/google-chrome')
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (f'  [{detail}]' if detail and not cond else ''))

import io, json, urllib.parse
from PIL import Image as _Img
def _png(rgb):
    b = io.BytesIO(); _Img.new('RGB', (300, 300), rgb).save(b, 'JPEG'); return b.getvalue()
COVERS = {'rel-amber': _png((240, 170, 40)), 'rel-blue': _png((60, 150, 230)), 'rel-other': _png((90, 90, 90))}
import time as _time
mb_calls = []; mb_times = []
def mb_route(route):
    u = urllib.parse.urlparse(route.request.url); q = dict(urllib.parse.parse_qsl(u.query)); mb_calls.append((u.path, q.get('query', ''))); mb_times.append(_time.monotonic())
    query = q.get('query', '').lower()
    rel = []
    if 'amber days' in query:
        rel = [{'id': 'rel-amber', 'title': 'Amber Days', 'score': 100, 'date': '2020-05-01', 'country': 'US', 'artist-credit': [{'name': 'Fixture Artist'}]},
               {'id': 'rel-other', 'title': 'Amber Days (Deluxe)', 'score': 70, 'date': '2021', 'country': 'GB', 'artist-credit': [{'name': 'Fixture Artist'}]}]
    elif 'test album' in query:
        rel = [{'id': 'rel-blue', 'title': 'Something Else', 'score': 60, 'artist-credit': [{'name': 'Nobody'}]}]   # not confident
    return route.fulfill(status=200, content_type='application/json', body=json.dumps({'releases': rel, 'recordings': []}),
                         headers={'Access-Control-Allow-Origin': '*'})
def caa_route(route):
    rid = route.request.url.split('/release/')[1].split('/')[0]
    if rid not in COVERS: return route.fulfill(status=404, body='')
    return route.fulfill(status=200, content_type='image/jpeg', body=COVERS[rid], headers={'Access-Control-Allow-Origin': '*'})

def serve():
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}/'

LABEL_JS = 'e=>{const l=e.querySelector(".lt");return l?l.textContent:[...e.childNodes].find(n=>n.nodeType===3).textContent}'
rows = lambda pg: pg.eval_on_selector_all('#body .row', f'els=>els.map({LABEL_JS})')
sel = lambda pg: pg.eval_on_selector('#body .row.sel', LABEL_JS)
def key(pg, k, n=1, wait=40):
    for _ in range(n): pg.keyboard.press(k); pg.wait_for_timeout(wait)
def selpos(pg): return pg.evaluate('(()=>{const r=[...document.querySelectorAll("#body .row")];const t=document.querySelector("#body .sb i");return r.findIndex(e=>e.classList.contains("sel"))+"|"+(t?t.style.top:"")+"|"+r.map(e=>e.textContent).join("/")})()')
def choose(pg, label):
    for _ in range(3):
        for _ in range(200):
            if sel(pg) == label: key(pg, 'Enter', wait=250); return
            before = selpos(pg); pg.keyboard.press('ArrowDown')
            if selpos(pg) == before: break
        for _ in range(200): pg.keyboard.press('ArrowUp')
    raise AssertionError(f'could not reach {label!r}')
def music_label(pg):
    for _ in range(15): pg.keyboard.press('ArrowUp')
    txt = pg.inner_text('#body')
    for l in ('Ad-Free Local Music', 'Offline Music', 'Music'):
        if l in txt: return l
    raise AssertionError('music entry not found; title=%r body=%r' % (pg.text_content('#htitle'), txt))
def wait_sync(pg, timeout=20000):
    pg.wait_for_function('!document.querySelector(".hdr").classList.contains("busy") || document.querySelector(".hdr").classList.contains("done")', timeout=timeout)
    pg.wait_for_timeout(100)
def home(pg):
    for _ in range(8):
        if pg.text_content('#htitle') == 'iPod': return
        key(pg, 'Escape', wait=120)

def main():
    srv, url = serve()
    errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844})
        ctx.route('https://**', lambda r: r.abort())          # no network: these features must work offline
        ctx.route('https://musicbrainz.org/**', mb_route)
        ctx.route('https://coverartarchive.org/**', caa_route)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        pg.goto(url); pg.wait_for_timeout(1200)

        # ---- colours ----
        choose(pg, 'Settings'); seen = []
        for _ in range(8):
            seen.append(pg.evaluate('document.getElementById("ipod").className')); choose(pg, 'Color')
        check('Color cycles through 8 finishes', len(set(seen)) == 8, seen)
        check('dark finishes use the dark wheel', any('black' in c and 'c-graphite' in c for c in seen) and any(c.strip() == 'ipod black' for c in seen), seen)
        body_bg = pg.evaluate('getComputedStyle(document.getElementById("ipod")).backgroundImage')
        check('back to Silver after a full cycle', 'c-' not in pg.evaluate('document.getElementById("ipod").className') and 'gradient' in body_bg)

        # ---- Hold switch ----
        home(pg); before = sel(pg)
        pg.click('#hold'); pg.wait_for_timeout(100)
        key(pg, 'ArrowDown'); key(pg, 'Enter', wait=150)
        check('Hold blocks the wheel and buttons', sel(pg) == before and pg.text_content('#htitle') == 'iPod')
        check('Hold shows the lock message + header lock', 'on' in pg.get_attribute('#lockpop', 'class') and 'on' in pg.get_attribute('#lk', 'class'))
        pg.click('#hold'); pg.wait_for_timeout(100); key(pg, 'ArrowDown')
        check('releasing Hold restores control', sel(pg) != before)

        # ---- backlight ----
        choose(pg, 'Settings'); choose(pg, 'Backlight')   # 20 sec -> 1 min
        for _ in range(2): choose(pg, 'Backlight')        # -> Always On -> 10 sec
        check('Backlight setting reaches 10 sec', '10 sec' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.wait_for_timeout(10600)
        check('screen dims after the backlight timeout', 'dim' in pg.get_attribute('#screen', 'class'))
        key(pg, 'ArrowDown')
        check('any input wakes the screen', 'dim' not in pg.get_attribute('#screen', 'class'))
        choose(pg, 'Backlight'); choose(pg, 'Backlight')  # -> 20 sec -> 1 min (out of the way for the rest)

        # ---- generated album art + Albums thumbnails + fast scroll ----
        home(pg)
        files = [str(FIX / f'song{i % 3 + 1}.mp3') for i in range(45)]
        pg.set_input_files('#file', files); pg.wait_for_timeout(4000); wait_sync(pg)
        n = pg.evaluate('document.querySelectorAll("#body .row").length')
        home(pg); choose(pg, music_label(pg))
        choose(pg, 'Albums')
        thumbs = pg.evaluate('[...document.querySelectorAll("#body .row .thumb")].map(t=>t.style.backgroundImage.slice(0,30))')
        check('Albums list shows cover thumbnails', len(thumbs) >= 1 and all('url(' in t for t in thumbs), thumbs)
        key(pg, 'Escape', wait=150); choose(pg, 'Songs')
        total = pg.evaluate('document.querySelector("#body .sb")!==null')
        # fast spin on a 45-song list: drag around the wheel quickly
        box = pg.locator('#wheel').bounding_box(); cx, cy, r = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, box['width'] * .4
        a = -90; pg.mouse.move(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))); pg.mouse.down()
        for _ in range(140):
            a += 5; pg.mouse.move(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))); pg.wait_for_timeout(8)
        pg.mouse.up()
        idx = pg.evaluate('[...document.querySelectorAll("#body .row")].findIndex(r=>r.classList.contains("sel"))')
        pos = pg.evaluate('(()=>{const t=document.querySelector("#body .sb i");return t?parseFloat(t.style.top):0})()')
        check('fast spinning accelerates on long lists (moves more than 1 row per detent)', total and pos > 60, pos)
        check('jump letter appears while fast scrolling', pg.evaluate('document.getElementById("letter").textContent.length') == 1)
        for _ in range(60): pg.keyboard.press('ArrowUp')
        key(pg, 'Enter', wait=700)
        art = pg.get_attribute('.np .art', 'style') or ''
        check('Now Playing always has cover art (embedded or generated)', 'url(' in art, art[:60])
        check('cover reflection drawn', pg.evaluate('!!document.querySelector(".np .refl")'))
        md = pg.evaluate('navigator.mediaSession.metadata && navigator.mediaSession.metadata.artwork.length')
        check('lock screen gets artwork too', md == 1, md)
        gen = pg.evaluate('(()=>{const c=document.createElement("canvas");return typeof c.getContext("2d").fillText})()')

        # ---- Clock ----
        home(pg); choose(pg, 'Extras'); choose(pg, 'Clock'); pg.wait_for_timeout(300)
        check('Clock shows an analogue face and the time', pg.evaluate('!!document.querySelector(".clock svg")') and (':' in pg.text_content('.clock .dig')))
        t1 = pg.inner_html('.clock svg'); pg.wait_for_timeout(2100)
        check('Clock ticks every second', pg.inner_html('.clock svg') != t1)
        key(pg, 'Escape', wait=150)

        # ---- Brick ----
        choose(pg, 'Brick'); pg.wait_for_timeout(300)
        check('Brick canvas mounts', pg.evaluate('!!document.getElementById("game")'))
        key(pg, 'ArrowDown', n=4, wait=30)
        key(pg, 'Enter', wait=100)                 # launch
        pg.wait_for_timeout(2500)
        pixels = pg.evaluate('(()=>{const c=document.getElementById("game").getContext("2d").getImageData(0,0,540,380).data;let n=0;for(let i=0;i<c.length;i+=4)if(c[i]>200&&c[i+1]>200&&c[i+2]>200)n++;return n})()')
        check('Brick draws paddle/ball/bricks', pixels > 50, pixels)
        key(pg, ' ', wait=300)
        a1 = pg.evaluate('document.getElementById("game").toDataURL()'); pg.wait_for_timeout(400)
        check('Play/Pause freezes the game', pg.evaluate('document.getElementById("game").toDataURL()') == a1)
        key(pg, 'Escape', wait=200)
        check('MENU leaves the game', pg.text_content('#htitle') == 'Extras')

        # ---- Modern style ----
        home(pg); choose(pg, 'Settings'); choose(pg, 'Style')
        check('Style switches to Modern', 'modern' in pg.get_attribute('#ipod', 'class') and 'Modern' in pg.inner_text('#body'))
        check('Modern hides Color (fixed slate finish)', 'Color' not in pg.inner_text('#body'))
        check('Modern wheel uses outline icons', pg.evaluate('getComputedStyle(document.querySelector(".wheel svg.mod.m")).display') == 'block'
              and pg.evaluate('getComputedStyle(document.querySelector(".wheel .lbl.m")).display') == 'none')
        check('status bar shows the time', ':' in pg.text_content('#hclock'))
        home(pg); choose(pg, music_label(pg)); choose(pg, 'Songs'); key(pg, 'Enter', wait=900)
        check('Modern Now Playing layout', pg.evaluate('!!document.querySelector(".mnp .bg") && !!document.querySelector(".mnp .row3")'))
        check('background tone taken from the artwork', pg.evaluate('getComputedStyle(document.getElementById("np")).getPropertyValue("--tone").trim().startsWith("rgb")'),
              pg.evaluate('getComputedStyle(document.getElementById("np")).getPropertyValue("--tone")'))
        check('format badge shows the file type', 'MP3' in pg.text_content('.mnp .fmt'))
        key(pg, 'ArrowUp', wait=100)
        check('volume overlay works in Modern', 'showvol' in pg.get_attribute('#np', 'class'))
        key(pg, 'Enter', wait=200)
        check('scrubbing works in Modern', 'scrub' in pg.get_attribute('.mnp .bar', 'class'))
        home(pg); choose(pg, 'Settings'); choose(pg, 'Style')
        check('back to Classic', 'modern' not in pg.get_attribute('#ipod', 'class'))

        # ---- Modern ▸ Light / Dark / Auto ----
        home(pg); choose(pg, 'Settings'); choose(pg, 'Style')
        cls = lambda: pg.get_attribute('#ipod', 'class')
        check('Modern defaults to Light appearance', 'modern' in cls() and 'lightui' in cls())
        scr_bg = pg.evaluate('getComputedStyle(document.getElementById("screen")).backgroundColor')
        check('Light screen is light', scr_bg in ('rgb(245, 247, 250)',), scr_bg)
        choose(pg, 'Appearance')
        check('Appearance → Dark', 'lightui' not in cls())
        choose(pg, 'Appearance')
        check('Appearance → Auto follows the system (headless = light)', 'lightui' in cls() and 'Auto' in pg.inner_text('#body'))
        pg.emulate_media(color_scheme='dark'); pg.wait_for_timeout(200)
        check('Auto switches live when the system goes dark', 'lightui' not in cls())
        pg.emulate_media(color_scheme='light'); pg.wait_for_timeout(200)
        choose(pg, 'Appearance')                       # -> Light

        # ---- interactive controls (tap + wheel) ----
        home(pg); pg.set_input_files('#file', [str(FIX / 'lyrics.mp3')]); pg.wait_for_timeout(1500); wait_sync(pg)
        music = music_label(pg)
        home(pg); choose(pg, 'Settings'); choose(pg, 'Fast Scroll'); home(pg)      # keyboard presses are fast; avoid jump-scrolling in tests
        choose(pg, music); choose(pg, 'Songs'); choose(pg, 'Lyric Test'); pg.wait_for_timeout(800)
        key(pg, ' ', wait=150)                                                      # pause: the 2-second test song would auto-advance
        tint = pg.evaluate('getComputedStyle(document.getElementById("np")).getPropertyValue("--tint").trim()')
        check('Light Now Playing gets a soft tint from the art', tint.startswith('rgb'), tint)
        pg.click('.mnp [data-act="fav"]'); pg.wait_for_timeout(300)
        check('tapping ☆ favorites the song', 'on' in pg.get_attribute('.mnp [data-act="fav"]', 'class') and 'Favorites' in pg.text_content('#nptoast'))
        pg.click('.mnp [data-act="lyrics"]'); pg.wait_for_timeout(500)
        check('tapping lyrics shows the lyrics embedded in the file', 'Placeholder line for the lyrics test' in pg.inner_text('#body'), pg.inner_text('#body')[:80])
        y0 = pg.evaluate('getComputedStyle(document.querySelector(".lyr .in")).transform')
        key(pg, 'ArrowDown', n=3, wait=80)
        check('wheel scrolls the lyrics', pg.evaluate('getComputedStyle(document.querySelector(".lyr .in")).transform') != y0)
        key(pg, 'Escape', wait=200)
        check('MENU returns from lyrics to Now Playing', pg.evaluate('!!document.querySelector(".mnp")'))
        pg.click('.mnp [data-act="queue"]'); pg.wait_for_timeout(300)
        check('tapping the list icon opens Up Next', pg.text_content('#htitle') == 'Up Next' and '▶ Lyric Test' in pg.inner_text('#body'), pg.inner_text('#body')[:120])
        key(pg, 'Escape', wait=200)
        pg.click('.mnp [data-act="out"]'); pg.wait_for_timeout(200)
        check('tapping the output row explains how to switch output', 'Playing on' in pg.inner_text('#body'))
        key(pg, 'Enter', wait=200)
        # wheel path: center → scrub → controls
        key(pg, 'Enter', wait=200)
        check('center #1 → scrub', 'scrub' in pg.get_attribute('.mnp .bar', 'class'))
        key(pg, 'Enter', wait=200)
        check('center #2 → controls with focus ring on ☆', 'ctl' in pg.get_attribute('#np', 'class') and 'focus' in pg.get_attribute('.mnp [data-act="fav"]', 'class'))
        key(pg, 'ArrowDown', wait=120)
        check('spinning moves the focus to ⋯', 'focus' in pg.get_attribute('.mnp [data-act="more"]', 'class'))
        key(pg, 'Enter', wait=250)
        check('center opens the ⋯ song menu', pg.text_content('#htitle') == 'Song' and 'Play Next' in pg.inner_text('#body'))
        choose(pg, 'Song Info'); 
        check('Song Info shows format + favorite', 'MP3' in pg.inner_text('#body') and 'Yes' in pg.inner_text('#body'), pg.inner_text('#body'))
        key(pg, 'Escape', wait=150); key(pg, 'Escape', wait=150)
        cnt0 = pg.text_content('.mnp .cnt')
        pg.click('.mnp [data-act="more"]'); pg.wait_for_timeout(200); choose(pg, 'Add to Up Next'); pg.wait_for_timeout(200)
        cnt1 = pg.text_content('.mnp .cnt')
        check('Add to Up Next appends to the queue', int(cnt1.split()[-1]) == int(cnt0.split()[-1]) + 1, (cnt0, cnt1))
        pg.click('.mnp [data-act="more"]'); pg.wait_for_timeout(200); choose(pg, 'Play Next'); pg.wait_for_timeout(200)
        pg.click('.mnp [data-act="queue"]'); pg.wait_for_timeout(200)
        check('Play Next puts it right after the current song', rows(pg)[:2] == ['▶ Lyric Test', 'Lyric Test'], rows(pg)[:3])
        key(pg, 'Escape', wait=150)
        key(pg, 'Enter', wait=150); key(pg, 'Enter', wait=150)   # → controls
        key(pg, 'Escape', wait=150)
        check('MENU leaves controls but stays on Now Playing', pg.text_content('#htitle') == 'Now Playing' and 'ctl' not in pg.get_attribute('#np', 'class'))
        # favourites persist + list
        pg.reload(); pg.wait_for_timeout(1500)
        choose(pg, music); choose(pg, 'Favorites')
        check('favorite is saved and listed after reload', rows(pg) == ['Lyric Test'], rows(pg))
        choose(pg, 'Lyric Test'); pg.wait_for_timeout(500); key(pg, ' ', wait=150)
        pg.click('.mnp [data-act="fav"]'); pg.wait_for_timeout(200)
        home(pg); choose(pg, music); choose(pg, 'Songs'); choose(pg, 'Test Song 2'); pg.wait_for_timeout(500)
        pg.click('.mnp [data-act="lyrics"]'); pg.wait_for_timeout(400)
        check('song without lyrics says so', 'No Lyrics' in pg.inner_text('#body'))
        home(pg); choose(pg, 'Settings'); choose(pg, 'Fast Scroll'); choose(pg, 'Style')     # Fast Scroll back on, back to Classic
        check('Classic unaffected', 'modern' not in pg.get_attribute('#ipod', 'class'))

        # ---- split screen + Album Flow ----
        home(pg); albums = sorted(FIX.glob('album-*.mp3'))
        pg.set_input_files('#file', [str(f) for f in albums]); pg.wait_for_timeout(2000); wait_sync(pg)
        check('main menu shows split-screen art', 'splitmode' in pg.get_attribute('#screen', 'class') and pg.evaluate('getComputedStyle(document.getElementById("split")).display') == 'block')
        bg1 = pg.evaluate('[...document.querySelectorAll("#split .ken")].map(e=>e.style.backgroundImage.slice(0,40)).join("|")')
        check('split panel shows a cover', 'url(' in bg1, bg1)
        check('menu text stays on the left half', pg.evaluate('document.querySelector("#body .list").getBoundingClientRect().width') < 200)
        pg.wait_for_timeout(7400)
        bg2 = pg.evaluate('[...document.querySelectorAll("#split .ken.on")].map(e=>e.style.backgroundImage).join("|")')
        check('split art crossfades to another cover', bg2 and bg2 not in bg1, (bg1[:60], bg2[:60]))
        choose(pg, 'Settings')
        check('split screen only on the main menu', 'splitmode' not in pg.get_attribute('#screen', 'class'))
        flips = []
        for _ in range(8):
            key(pg, 'ArrowDown', wait=60); flips.append('splitmode' in pg.get_attribute('#screen', 'class'))
        for _ in range(8):
            key(pg, 'ArrowUp', wait=60); flips.append('splitmode' in pg.get_attribute('#screen', 'class'))
        check('split screen never appears while scrolling Settings (regression)', not any(flips), flips)
        choose(pg, 'Split Screen')                    # Album Art -> Now Playing
        check('Split Screen offers Now Playing mode', 'Now Playing' in pg.inner_text('#body'), pg.inner_text('#body'))
        home(pg); choose(pg, music_label(pg)); choose(pg, 'Songs'); key(pg, 'Enter', wait=500); key(pg, ' ', wait=150)
        home(pg); pg.wait_for_timeout(300)
        check('Now Playing panel shows the playing song', 'npmode' in pg.get_attribute('#split', 'class') and pg.text_content('#splitnp .t') != '' and 'Paused' in pg.text_content('#splitnp .st'),
              pg.inner_text('#splitnp'))
        key(pg, ' ', wait=300)
        check('Now Playing panel updates when playback resumes', 'Now Playing' in pg.text_content('#splitnp .st'))
        key(pg, ' ', wait=150)
        choose(pg, 'Settings'); choose(pg, 'Split Screen'); home(pg)   # -> Off
        check('Split Screen can be turned off', 'splitmode' not in pg.get_attribute('#screen', 'class'))
        choose(pg, 'Settings'); choose(pg, 'Split Screen'); home(pg)   # -> Album Art
        check('back to Album Art panel', 'splitmode' in pg.get_attribute('#screen', 'class') and 'npmode' not in pg.get_attribute('#split', 'class'))
        # long labels scroll instead of staying cut off
        for _ in range(15): pg.keyboard.press('ArrowUp')
        found = False
        for _ in range(12):
            if pg.evaluate('(()=>{const l=document.querySelector("#body .row.sel .lb");return l&&l.firstElementChild.scrollWidth>l.clientWidth+2})()'):
                found = True; break
            key(pg, 'ArrowDown', wait=60)
        pg.wait_for_timeout(200)
        check('a cut-off selected label scrolls (marquee)', found and 'marq' in pg.get_attribute('#body .row.sel .lb', 'class')
              and pg.evaluate('parseFloat(getComputedStyle(document.querySelector("#body .row.sel .lb")).getPropertyValue("--mx"))') > 0)
        key(pg, 'ArrowDown', wait=200)
        check('rows that fit don\'t scroll', pg.evaluate('(()=>{const l=document.querySelector("#body .row.sel .lb");return l.firstElementChild.scrollWidth<=l.clientWidth+2?!l.classList.contains("marq"):true})()'))

        choose(pg, 'Album Flow'); pg.wait_for_timeout(600)
        n_cov = pg.evaluate('document.querySelectorAll("#flow .cv").length')
        check('Album Flow shows one cover per album', n_cov >= 6, n_cov)
        cap0 = (pg.text_content('#fal'), pg.text_content('#far'), pg.text_content('#fcnt'))
        z = pg.evaluate('(()=>{const c=[...document.querySelectorAll("#flow .cv")];return c.map(e=>+e.style.zIndex)})()')
        sel_i = z.index(max(z))
        tf_center = pg.evaluate(f'document.querySelectorAll("#flow .cv")[{sel_i}].style.transform')
        tf_side = pg.evaluate(f'document.querySelectorAll("#flow .cv")[{(sel_i + 1) % n_cov}].style.transform')
        check('centre cover faces you, neighbours are angled', 'rotateY(0deg)' in tf_center and 'rotateY(' in tf_side and '0deg' not in tf_side, (tf_center, tf_side))
        i, n = [int(v) for v in cap0[2].split(' OF ')]
        key(pg, 'ArrowDown' if i < n else 'ArrowUp', wait=400)
        cap1 = (pg.text_content('#fal'), pg.text_content('#far'), pg.text_content('#fcnt'))
        check('spinning flips to the next album', cap1 != cap0, (cap0, cap1))
        check('caption shows album + artist + count', pg.text_content('#far') != '' and 'OF' in pg.text_content('#fcnt'))
        pg.goto(url); pg.wait_for_timeout(1200)   # fresh state for the open/play checks
        choose(pg, 'Album Flow'); pg.wait_for_timeout(400)
        for _ in range(12):
            if pg.text_content('#fal') == 'Blue Hour': break
            key(pg, 'ArrowDown', wait=120)
        key(pg, 'Enter', wait=300)
        check('center opens the album\'s songs', pg.text_content('#htitle') == 'Blue Hour' and 'Blue Hour Track' in pg.inner_text('#body'), pg.inner_text('#body'))
        key(pg, 'Escape', wait=300)
        check('MENU returns to Album Flow on the same album', pg.text_content('#fal') == 'Blue Hour')
        key(pg, ' ', wait=700)
        check('play button plays the album', pg.text_content('#htitle') == 'Now Playing' and 'Blue Hour Track' in pg.inner_text('#body'))
        key(pg, ' ', wait=150)
        home(pg); choose(pg, 'Album Flow'); pg.wait_for_timeout(300)
        check('Album Flow opens on the playing album', pg.text_content('#fal') == 'Blue Hour')
        home(pg); choose(pg, 'Settings'); choose(pg, 'Style'); home(pg); choose(pg, 'Album Flow'); pg.wait_for_timeout(300)
        check('Album Flow works in Modern style', pg.evaluate('!!document.querySelector("#flow .cv")') and 'modern' in pg.get_attribute('#ipod', 'class'))
        home(pg); check('split screen works in Modern style', 'splitmode' in pg.get_attribute('#screen', 'class'))
        choose(pg, 'Settings'); choose(pg, 'Style')

        # ---- header sync bar ----
        home(pg); for_sync = [str(FIX / f'song{i % 3 + 1}.mp3') for i in range(12)]
        pg.evaluate('''window.__labels=[];window.__titleHidden=false;new MutationObserver(()=>{window.__labels.push(document.getElementById("tasktl").textContent);
            if(getComputedStyle(document.getElementById("htitle")).display==="none")window.__titleHidden=true})
            .observe(document.querySelector(".hdr"),{subtree:true,childList:true,characterData:true,attributes:true})''')
        pg.set_input_files('#file', for_sync); pg.wait_for_timeout(60)
        labels = pg.evaluate('window.__labels')
        check('import shows "Syncing N of 12" progress in the header', any(l.startswith('Syncing') and l.endswith(' of 12') for l in labels) and 'Syncing 12 of 12' in labels, labels[:6])
        check('screen title is replaced while syncing', pg.evaluate('window.__titleHidden'))
        key(pg, 'ArrowDown', wait=60)
        check('iPod stays usable during sync (no loading screen)', pg.evaluate('!!document.querySelector("#body .row.sel")') and pg.text_content('#htitle') == 'iPod')
        w1 = pg.evaluate('parseFloat(document.getElementById("taskbar").style.width)')
        wait_sync(pg)
        check('bar fills and shows Sync Complete', pg.text_content('#tasktl') == 'Sync Complete' and 'done' in pg.get_attribute('.hdr', 'class')
              and pg.evaluate('parseFloat(document.getElementById("taskbar").style.width)') == 100, (w1, pg.text_content('#tasktl')))
        pg.wait_for_timeout(2500)
        check('title comes back after the sync', 'busy' not in pg.get_attribute('.hdr', 'class') and pg.evaluate('getComputedStyle(document.getElementById("htitle")).display') != 'none')
        choose(pg, 'Settings'); choose(pg, 'Style'); home(pg)
        pg.set_input_files('#file', [str(FIX / 'song1.mp3'), str(FIX / 'song2.mp3')]); pg.wait_for_timeout(40)
        check('sync bar works in Modern style', 'busy' in pg.get_attribute('.hdr', 'class') or pg.text_content('#tasktl') == 'Sync Complete')
        wait_sync(pg); choose(pg, 'Settings'); choose(pg, 'Style')

        # ---- Flow menu style ----
        home(pg); choose(pg, 'Settings'); choose(pg, 'Menu Style')
        check('Menu Style switches to Flow (and hides Split Screen)', 'Flow' in pg.inner_text('#body') and 'Split Screen' not in pg.inner_text('#body'))
        home(pg); pg.wait_for_timeout(400)
        n_cards = pg.evaluate('document.querySelectorAll("#flow .cv.card").length')
        check('main menu becomes a card shelf', n_cards >= 7 and 'splitmode' not in pg.get_attribute('#screen', 'class'), n_cards)
        check('every card has an icon', pg.evaluate('[...document.querySelectorAll("#flow .cv.card svg")].every(s=>s.innerHTML.length>10)'))
        check('shelf reopens on the card you last used', pg.text_content('#fal') == 'Settings', pg.text_content('#fal'))
        for _ in range(12): key(pg, 'ArrowUp', wait=40)
        c0 = pg.text_content('#fal')
        check('caption shows the selected item', c0 == 'Offline Music', c0)
        tfs = pg.evaluate('[...document.querySelectorAll("#flow .cv")].slice(0,2).map(e=>e.style.transform)')
        check('front card faces you, next card is angled', 'rotateY(0deg)' in tfs[0] and '-62deg' in tfs[1], tfs)
        for _ in range(12):
            if pg.text_content('#fal') == 'Settings': break
            key(pg, 'ArrowDown', wait=120)
        check('spinning flips through the menu', pg.text_content('#fal') == 'Settings')
        key(pg, 'Enter', wait=300)
        check('center opens the item', pg.text_content('#htitle') == 'Settings')
        key(pg, 'Escape', wait=400)
        check('MENU returns to the shelf on the same card', pg.evaluate('!!document.querySelector("#flow .cv.card")') and pg.text_content('#fal') == 'Settings')
        for _ in range(12): key(pg, 'ArrowUp', wait=40)
        for _ in range(12):
            if pg.text_content('#fal') == 'Album Flow': break
            key(pg, 'ArrowDown', wait=100)
        key(pg, 'Enter', wait=500)
        check('Album Flow still opens from the Flow menu', pg.text_content('#htitle') == 'Album Flow' and pg.evaluate('!!document.querySelector("#flow .cv:not(.card)")'))
        key(pg, 'Escape', wait=300)
        for _ in range(12): key(pg, 'ArrowDown', wait=40)
        for _ in range(12):
            if pg.text_content('#fal') == 'Settings': break
            key(pg, 'ArrowUp', wait=100)
        key(pg, 'Enter', wait=300); choose(pg, 'Menu Style')
        home(pg)
        check('back to the List menu', pg.evaluate('!document.querySelector("#flow")') and len(rows(pg)) >= 5)

        # ---- Flow Now Playing ----
        home(pg); choose(pg, 'Settings'); choose(pg, 'Now Playing Style')
        check('Now Playing Style switches to Flow', pg.evaluate('JSON.parse(localStorage.getItem("ipod.settings")).npStyle') == 'Flow')
        home(pg); choose(pg, music_label(pg)); choose(pg, 'Album Flow'); pg.wait_for_timeout(300)
        for _ in range(12):
            if pg.text_content('#fal') == 'Blue Hour': break
            key(pg, 'ArrowDown', wait=100)
        home(pg); choose(pg, music_label(pg)); choose(pg, 'Songs')
        for _ in range(60):
            if sel(pg) == 'Blue Hour Track': break
            key(pg, 'ArrowDown', wait=30)
        key(pg, 'Enter', wait=700); key(pg, ' ', wait=200)
        check('Flow Now Playing shows a cover shelf', pg.evaluate('!!document.querySelector(".fnp .cv")') and 'Blue Hour Track' in pg.text_content('.fnp .cap b'))
        check('previous and upcoming songs are on the shelf', pg.evaluate('document.querySelectorAll(".fnp .cv").length') >= 3
              and pg.text_content('.fnp .tag.l') == 'Previous' and pg.text_content('.fnp .tag.r') == 'Up Next')
        center = pg.evaluate('(()=>{const c=[...document.querySelectorAll(".fnp .cv")];return c.find(e=>e.style.transform.includes("rotateY(0deg)")).dataset.q})()')
        key(pg, 'ArrowRight', wait=700); key(pg, ' ', wait=150)
        center2 = pg.evaluate('(()=>{const c=[...document.querySelectorAll(".fnp .cv")];return c.find(e=>e.style.transform.includes("rotateY(0deg)")).dataset.q})()')
        check('next glides the shelf to the upcoming song', int(center2) == int(center) + 1, (center, center2))
        prev_card = pg.locator('.fnp .cv[data-q="%d"]' % (int(center2) - 1))
        prev_card.click(force=True); pg.wait_for_timeout(700); key(pg, ' ', wait=150)
        check('tapping the previous cover jumps back to it', 'Blue Hour Track' in pg.text_content('.fnp .cap b'), pg.text_content('.fnp .cap b'))
        key(pg, 'ArrowUp', wait=150)
        check('wheel still controls volume', 'showvol' in pg.get_attribute('#np', 'class'))
        key(pg, 'Enter', wait=200)
        check('center #1 scrubs', 'scrub' in pg.get_attribute('.fnp .bar', 'class'))
        key(pg, 'Enter', wait=300)
        check('center #2 opens the song menu with Get Artwork', pg.text_content('#htitle') == 'Song' and ('Get Artwork' in pg.inner_text('#body') or 'Replace Artwork' in pg.inner_text('#body')))
        key(pg, 'Escape', wait=200)

        # ---- Get Artwork (pick a candidate) ----
        home(pg); pg.set_input_files('#file', [str(FIX / 'song1.mp3')]); pg.wait_for_timeout(300); wait_sync(pg)
        pg.evaluate("1")
        # an untagged-art song: re-import the Amber Days track without its cover via a stripped copy
        import subprocess, tempfile as _tf
        bare = _tf.mktemp(suffix='.mp3')
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(FIX / 'album-amber-days.mp3'), '-map', '0:a', '-c', 'copy', '-id3v2_version', '3',
                        '-metadata', 'title=Bare Amber', '-metadata', 'artist=Fixture Artist', '-metadata', 'album=Amber Days', bare], check=True)
        pg.set_input_files('#file', [bare]); pg.wait_for_timeout(300); wait_sync(pg)
        home(pg); choose(pg, music_label(pg)); choose(pg, 'Songs')
        for _ in range(80):
            if sel(pg) == 'Bare Amber': break
            key(pg, 'ArrowDown', wait=25)
        key(pg, 'Enter', wait=600); key(pg, ' ', wait=150)
        key(pg, 'Enter', wait=150); key(pg, 'Enter', wait=300)
        check('song without art offers Get Artwork', 'Get Artwork' in pg.inner_text('#body') or 'Get Artwork' in ' '.join(rows(pg)))
        choose(pg, 'Get Artwork'); pg.wait_for_timeout(2500)
        check('Get Artwork lists candidates with thumbnails', pg.text_content('#htitle') == 'Choose Artwork' and pg.evaluate('document.querySelectorAll("#body .thumb").length') >= 2,
              pg.inner_text('#body'))
        check('MusicBrainz searched by album + artist', any('amber days' in q.lower() and 'fixture artist' in q.lower() for _, q in mb_calls), mb_calls[-2:])
        key(pg, 'Enter', wait=1200)
        check('picking a candidate saves the cover', 'Artwork Saved' in pg.inner_text('#body'), pg.inner_text('#body'))
        key(pg, 'Enter', wait=200)
        for _ in range(4):
            if pg.text_content('#htitle') == 'Now Playing': break
            key(pg, 'Escape', wait=250)
        art = pg.evaluate('getComputedStyle(document.querySelector(".fnp .cv[style*=blob]")||document.body).backgroundImage')
        check('Now Playing shows the new cover', 'blob:' in art, art[:60])
        pg.reload(); pg.wait_for_timeout(1500)
        has_art = pg.evaluate('''new Promise(res=>{const r=indexedDB.open("ipod");r.onsuccess=()=>{const q=r.result.transaction("songs").objectStore("songs").getAll();
            q.onsuccess=()=>res(q.result.filter(s=>s.title==="Bare Amber").map(s=>!!s.art&&s.art.size>2048&&s.artSource==="coverartarchive"))}})''')
        check('cover is saved with the song (persists after reload)', has_art == [True], has_art)

        # ---- Find Missing Artwork (auto, confident matches only) ----
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(FIX / 'album-amber-days.mp3'), '-map', '0:a', '-c', 'copy', '-id3v2_version', '3',
                        '-metadata', 'title=Bare Amber Two', '-metadata', 'artist=Fixture Artist', '-metadata', 'album=Amber Days', bare], check=True)
        n_before = pg.evaluate('''new Promise(res=>{const r=indexedDB.open("ipod");r.onsuccess=()=>{const q=r.result.transaction("songs").objectStore("songs").getAll();q.onsuccess=()=>res(q.result.filter(s=>!s.art).length)}})''')
        pg.set_input_files('#file', [bare]); pg.wait_for_timeout(300); wait_sync(pg); pg.wait_for_timeout(2300)
        home(pg); choose(pg, 'Settings'); choose(pg, 'Find Missing Artwork')
        check('Find Missing Artwork starts in the background', 'Finding Artwork' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.wait_for_function('document.getElementById("tasktl").textContent.startsWith("Found") || document.getElementById("tasktl").textContent.startsWith("No new")', timeout=30000)
        status = pg.text_content('#tasktl')
        rec = pg.evaluate('''new Promise(res=>{const r=indexedDB.open("ipod");r.onsuccess=()=>{const q=r.result.transaction("songs").objectStore("songs").getAll();
            q.onsuccess=()=>res(q.result.map(s=>[s.title,!!s.art,s.artSource||""]))}})''')
        check('confident match filled automatically', ['Bare Amber Two', True, 'coverartarchive'] in rec, (status, [r_ for r_ in rec if 'Bare' in r_[0]]))
        check('uncertain matches are left alone', all(not r_[1] or r_[2] == '' or 'Bare' in r_[0] for r_ in rec if r_[0].startswith('Test Song')), [r_ for r_ in rec if r_[0].startswith('Test Song')][:3])
        check('embedded covers are never replaced', all(r_[2] == '' for r_ in rec if r_[0].endswith(' Track')), [r_ for r_ in rec if r_[0].endswith(' Track')])
        gaps = [b - a_ for a_, b in zip(mb_times, mb_times[1:])]
        check('MusicBrainz calls are spaced ≥1 s apart', len(gaps) >= 1 and min(gaps) >= 1.0, [round(g, 2) for g in gaps])
        home(pg); choose(pg, 'Settings'); choose(pg, 'Now Playing Style')

        # ---- Auto Artwork: covers looked up automatically after an import ----
        home(pg); choose(pg, 'Settings'); choose(pg, 'Auto Artwork'); home(pg)
        check('Auto Artwork can be switched on', pg.evaluate('JSON.parse(localStorage.getItem("ipod.settings")).autoArt') is True)
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(FIX / 'album-amber-days.mp3'), '-map', '0:a', '-c', 'copy', '-id3v2_version', '3',
                        '-metadata', 'title=Auto Amber', '-metadata', 'artist=Fixture Artist', '-metadata', 'album=Amber Days', bare], check=True)
        calls0 = len(mb_calls)
        pg.set_input_files('#file', [bare]); pg.wait_for_timeout(300); wait_sync(pg)
        pg.wait_for_function('document.getElementById("tasktl").textContent.startsWith("Found") || document.getElementById("tasktl").textContent.startsWith("No new")', timeout=30000)
        rec = pg.evaluate('''new Promise(res=>{const r=indexedDB.open("ipod");r.onsuccess=()=>{const q=r.result.transaction("songs").objectStore("songs").getAll();
            q.onsuccess=()=>res(q.result.filter(s=>s.title==="Auto Amber").map(s=>[!!s.art,s.artSource||""]))}})''')
        check('imported song gets its cover automatically', rec == [[True, 'coverartarchive']], rec)
        check('no "Finding Artwork" screen interrupts you (runs quietly)', pg.text_content('#htitle') == 'iPod')
        new_calls = mb_calls[calls0:]
        check('Auto Artwork looked up the new album (and other albums still missing art)', any('amber days' in q.lower() for _, q in new_calls), new_calls)
        check('each album looked up at most once per pass', len(new_calls) == len(set(new_calls)), new_calls)
        calls1 = len(mb_calls)
        pg.set_input_files('#file', [str(FIX / 'song1.mp3')]); pg.wait_for_timeout(300); wait_sync(pg); pg.wait_for_timeout(3500)
        check('albums already tried are not looked up again', not any(c in mb_calls[calls0:calls1] for c in mb_calls[calls1:]), mb_calls[calls1:])
        home(pg); choose(pg, 'Settings'); choose(pg, 'Auto Artwork'); home(pg)

        # ---- Song Flow ----
        home(pg); choose(pg, music_label(pg)); choose(pg, 'Song Flow'); pg.wait_for_timeout(500)
        total = int(pg.text_content('#fcnt').split(' OF ')[1])
        n_cards = pg.evaluate('document.querySelectorAll("#flow .cv").length')
        check('Song Flow shows one card per song', total >= 45 and pg.text_content('#htitle') == 'Song Flow', total)
        check('big library builds only nearby covers (windowed)', n_cards <= 25, n_cards)
        for _ in range(200): pg.keyboard.press('ArrowUp')
        pg.wait_for_timeout(300)
        check('Song Flow starts at the first song', pg.text_content('#fcnt').startswith('1 OF'))
        seen = set()
        for _ in range(30):
            key(pg, 'ArrowDown', wait=50); seen.add(pg.text_content('#fcnt'))
        pg.wait_for_timeout(400)
        pos = int(pg.text_content('#fcnt').split(' OF ')[0])
        check('spinning far past the window keeps working', pos == 31 and len(seen) == 30, (pos, len(seen)))
        sel_card = pg.evaluate('(()=>{const c=[...document.querySelectorAll("#flow .cv")].find(e=>e.style.transform.includes("rotateY(0deg)"));return c&&+c.dataset.i})()')
        check('the front card is the selected song after re-windowing', sel_card == pos - 1, (sel_card, pos))
        want_title = pg.text_content('#fal')
        check('caption shows song title + artist', want_title != '' and pg.text_content('#far') != '')
        key(pg, 'Enter', wait=800)
        now_title = pg.evaluate('(document.querySelector(".fnp .cap b")||document.querySelector(".mnp .t")||document.querySelector(".np .t")||{}).textContent')
        check('center plays the selected song', pg.text_content('#htitle') == 'Now Playing' and now_title == want_title, (want_title, now_title))
        cnt = pg.evaluate('(document.querySelector(".np .cnt")||document.querySelector(".mnp .cnt")||{textContent:""}).textContent')
        key(pg, ' ', wait=150)
        check('it plays on through the rest of your songs (queue = whole library)', cnt == '' or cnt.endswith(str(total)), cnt)
        home(pg); choose(pg, 'Song Flow'); pg.wait_for_timeout(400)
        check('Song Flow opens on the playing song (from the main menu too)', pg.text_content('#fal') == want_title)
        key(pg, 'Escape', wait=200)

        check('no uncaught page errors', not errors, errors)
        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} passed'); sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
