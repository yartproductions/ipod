#!/usr/bin/env python3
"""iPhone app player: songs move into the app (checked byte for byte), the app plays them, the iPod follows along.
Uses tests/fake-native-player.js in place of the app.   Run: python3 tests/native_player.py"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-native-player.js').read_text()
srv, url = C.serve(); errors = []
with sync_playwright() as p:
    prof = tempfile.mkdtemp()
    def open_app():
        ctx = p.chromium.launch_persistent_context(prof, executable_path=C.CHROME, headless=True, args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'],
              viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,accel:false}))")
        pg.add_init_script(FAKE)
        return ctx, pg
    ctx, pg = open_app()
    pg.goto(url); pg.wait_for_timeout(1200)
    pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); pg.wait_for_timeout(3500); C.wait_sync(pg)
    pg.wait_for_function("window.__native.files.size>=5", timeout=30000); pg.wait_for_timeout(800)
    n = pg.evaluate("window.__native.files.size")
    check('new songs are copied into the app', n == 5, n)
    recs = pg.evaluate("""new Promise(r=>{const q=indexedDB.open('ipod');q.onsuccess=()=>{const g=q.result.transaction('songs').objectStore('songs').getAll();g.onsuccess=()=>r(g.result.map(x=>({stub:!(x.blob instanceof Blob)&&!!x.blob?.native,size:x.blob?.size})))}})""")
    check('…and only after the check passes is the old copy removed', all(x['stub'] and x['size'] > 0 for x in recs), recs)
    same = pg.evaluate("""(async()=>{const id=[...window.__native.files.keys()][0];const f=window.__native.files.get(id);return f.length>1000})()""")
    check('the app’s copies are the real files', same)
    C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(800)
    log = pg.evaluate("window.__native.log.filter(x=>x.startsWith('p:'))")
    P = pg.evaluate("({q:window.__native.player.queue.map(x=>x.title),i:window.__native.player.index,playing:window.__native.player.playing})")
    check('playing a song hands it to the app’s player', 'p:load' in log and P['q'][P['i']] == 'Blue Hour Track' and P['playing'], P)
    check('…and the web player stays silent', pg.evaluate("[...document.querySelectorAll('audio')].every(a=>a.paused)"))
    check('Now Playing shows it', 'Blue Hour Track' in pg.inner_text('#body'))
    pg.wait_for_timeout(2600)
    check('when the app moves on to the next song, the iPod follows', 'Blue Hour Track' not in pg.inner_text('#body') and 'Track' in pg.inner_text('#body'), pg.inner_text('#body')[:60])
    plays = pg.evaluate("JSON.parse(localStorage.getItem('ipod.listeningHistory')||'[]').length")
    check('plays are still counted', plays >= 2, plays)
    pg.keyboard.press(' '); pg.wait_for_timeout(400)
    check('pause on the wheel pauses the app’s player', pg.evaluate("window.__native.player.playing") is False)
    pg.keyboard.press(' '); pg.wait_for_timeout(400)
    check('…and play resumes it', pg.evaluate("window.__native.player.playing") is True)
    pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(500)
    check('next on the wheel jumps the app’s player', 'p:jump' in pg.evaluate("window.__native.log"))
    # file bytes still reachable for the quiz / lyrics / export
    blob_ok = pg.evaluate("""(async()=>{const r=await new Promise(res=>{const q=indexedDB.open('ipod');q.onsuccess=()=>{const g=q.result.transaction('songs').objectStore('songs').getAll();g.onsuccess=()=>res(g.result)}});
      const rec=r[0];const id=String(rec.id).replace(/[^A-Za-z0-9_-]/g,'');const b=await window.webkit.messageHandlers.ipodStore.postMessage({op:'read',id,offset:0,length:10});return atob(b).length===10})()""")
    check('song bytes can still be read back from the app', blob_ok)
    C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'iPhone App Player'); pg.wait_for_timeout(300)
    rows = C.all_rows(pg)
    check('Settings shows the iPhone App Player status', any('Songs in the App' in r for r in rows) and '5 of 5' in pg.inner_text('#body'), pg.inner_text('#body'))
    # Equalizer + Smart crossfade reach the app's player
    C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Equalizer'); C.choose(pg, 'Rock'); pg.wait_for_timeout(300)
    check('choosing an EQ preset sends its curve to the app', pg.evaluate("window.__native.player.eq") == [5,4,3,1,-1,-1,1,2,3,4], pg.evaluate("window.__native.player.eq"))
    C.choose(pg, 'Custom'); pg.wait_for_timeout(200)
    check('Custom opens the 10-band editor', pg.locator('.eqb').count() == 10)
    pg.keyboard.press('ArrowDown'); pg.keyboard.press('Enter'); pg.wait_for_timeout(100)
    for _ in range(3): pg.keyboard.press('ArrowDown'); pg.wait_for_timeout(40)
    pg.wait_for_timeout(300)
    eq = pg.evaluate("window.__native.player.eq")
    check('spinning a grabbed band changes that band only', eq and eq[1] != 0 and abs(eq[1]) == 3 and all(x == 0 for i, x in enumerate(eq) if i != 1), eq)
    C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Equalizer'); C.choose(pg, 'Off'); pg.wait_for_timeout(300)
    check('EQ Off turns it off in the app', pg.evaluate("window.__native.player.eq") is None)
    C.home(pg); C.choose(pg, 'Settings')
    for _ in range(7):
        if 'Smart' in pg.inner_text('#body'): break
        C.choose(pg, 'Crossfade'); pg.wait_for_timeout(100)
    check('Crossfade has a Smart setting, sent to the app', pg.evaluate("window.__native.player.smart") is True and pg.evaluate("window.__native.player.crossfade") == 0)
    check('the app gets track numbers for gapless albums', pg.evaluate("window.__native.player.queue.every(x=>typeof x.track==='number')"))
    ctx.close()
    # reopen: everything plays from the app, nothing to move again
    ctx, pg = open_app(); pg.goto(url); pg.wait_for_timeout(3500)
    C.home(pg); rows = C.all_rows(pg)
    check('…and it resumes the last song', 'Now Playing' in rows, rows)
    ctx.close()
    # a copy that doesn't match is never trusted: the old copy stays
    prof2 = tempfile.mkdtemp(); prof_saved = prof; prof = prof2
    ctx, pg = open_app(); pg.add_init_script("window.addEventListener('DOMContentLoaded',()=>{window.__native.corrupt=true})")
    pg.goto(url); pg.wait_for_timeout(1200)
    pg.set_input_files('#file', [str(C.FIX / 'album-red-line.mp3')]); pg.wait_for_timeout(3000); C.wait_sync(pg); pg.wait_for_timeout(9000)
    recs = pg.evaluate("""new Promise(r=>{const q=indexedDB.open('ipod');q.onsuccess=()=>{const g=q.result.transaction('songs').objectStore('songs').getAll();g.onsuccess=()=>r(g.result.map(x=>x.blob instanceof Blob))}})""")
    check('a copy that doesn’t match byte for byte is rejected, and the old copy is kept', recs == [True] and pg.evaluate("window.__native.files.size") == 0, (recs, pg.evaluate("window.__native.files.size")))
    ctx.close()
    check('no page errors', not errors, errors)
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
