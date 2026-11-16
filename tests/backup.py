#!/usr/bin/env python3
"""Backup & Restore: export everything but the audio, restore it on a fresh iPod.  Run: python3 tests/backup.py"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))

def new_ctx(p):
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True, accept_downloads=True,
          args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort()); return ctx

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = new_ctx(p); pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,theme:'Frost'}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        files = sorted(str(f) for f in C.FIX.glob('album-*.mp3'))
        pg.set_input_files('#file', files); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Shuffle Songs'); pg.wait_for_timeout(500)
        pg.evaluate("""(async()=>{const q=ipodMacBridge.queue();localStorage.setItem('ipod.memories',JSON.stringify({[q[0].id]:{text:'first dance',at:Date.now(),t:q[0].title,a:q[0].artist}}));})()""")
        pg.keyboard.press('Enter'); pg.wait_for_timeout(60); pg.keyboard.press('Enter'); pg.wait_for_timeout(350); C.choose(pg, 'Add to Favorites'); pg.wait_for_timeout(300)
        fav_title = pg.evaluate("ipodMacBridge.cur().title")
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Backup & Restore')
        with pg.expect_download() as dl: C.choose(pg, 'Back Up Now')
        path = dl.value.path(); data = json.loads(Path(path).read_text())
        check('Back Up Now saves a backup file', data['app'] == 'ipod-classic-web' and dl.value.suggested_filename.startswith('iPod Backup'))
        check('it holds settings, memories and the library (no audio)', 'ipod.settings' in data['store'] and 'ipod.memories' in data['store']
              and len(data['library']) == len(files) and all('blob' not in x for x in data['library']), list(data['store'])[:6])
        check('favorites are in it', any(x.get('favorite') and x['title'] == fav_title for x in data['library']))
        check('the screen confirms what was saved', pg.text_content('#htitle') == 'Backup Saved')
        bfile = Path(tempfile.mkdtemp()) / 'iPod Backup.json'; bfile.write_text(Path(path).read_text())
        ctx.close()

        # a brand-new iPod with the same music
        ctx = new_ctx(p); pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', files); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Settings'); C.choose(pg, 'Backup & Restore')
        with pg.expect_file_chooser() as fc: C.choose(pg, 'Restore from Backup')
        fc.value.set_files(str(bfile)); pg.wait_for_timeout(500)
        check('restore asks first, showing the backup date', pg.text_content('#htitle') == 'Restore Backup?' and 'Restore Everything' in pg.inner_text('#body'))
        C.choose(pg, 'Restore Everything'); pg.wait_for_timeout(1000)
        check('it reports what came back', 'favorites' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.wait_for_timeout(3500)
        check('settings came back (Frost body)', 'ed-frost' in pg.get_attribute('#ipod', 'class'))
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Song Memories')
        check('memories came back', 'first dance' in pg.inner_text('#body'))
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Favorites')
        check('favorites came back on the matching songs', fav_title in pg.inner_text('#body'), pg.inner_text('#body'))
        # a wrong file is refused
        C.home(pg); C.choose(pg, 'Settings'); C.choose(pg, 'Backup & Restore')
        junk = Path(tempfile.mkdtemp()) / 'x.json'; junk.write_text('{"hello":1}')
        with pg.expect_file_chooser() as fc: C.choose(pg, 'Restore from Backup')
        fc.value.set_files(str(junk)); pg.wait_for_timeout(500)
        check('a file that isn’t a backup is refused', pg.text_content('#htitle') == 'Not an iPod Backup')
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
