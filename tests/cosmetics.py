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

def serve():
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}/'

rows = lambda pg: pg.eval_on_selector_all('#body .row', 'els=>els.map(e=>e.lastChild.nodeType===3?e.lastChild.textContent:e.childNodes[e.querySelector(".thumb")?1:0].textContent)')
sel = lambda pg: pg.eval_on_selector('#body .row.sel', 'e=>[...e.childNodes].find(n=>n.nodeType===3).textContent')
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
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
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
        pg.set_input_files('#file', files); pg.wait_for_timeout(4000); key(pg, 'Enter', wait=200)
        n = pg.evaluate('document.querySelectorAll("#body .row").length')
        home(pg); choose(pg, next(l for l in ('Ad-Free Local Music', 'Offline Music', 'Music') if l in pg.inner_text('#body')))
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
        home(pg); choose(pg, next(l for l in ('Ad-Free Local Music', 'Offline Music', 'Music') if l in pg.inner_text('#body'))); choose(pg, 'Songs'); key(pg, 'Enter', wait=900)
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
        home(pg); pg.set_input_files('#file', [str(FIX / 'lyrics.mp3')]); pg.wait_for_timeout(1500); key(pg, 'Enter', wait=200)
        music = next(l for l in ('Ad-Free Local Music', 'Offline Music', 'Music') if l in pg.inner_text('#body'))
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

        check('no uncaught page errors', not errors, errors)
        ctx.close()
    srv.shutdown()
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} passed'); sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
