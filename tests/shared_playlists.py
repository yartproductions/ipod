#!/usr/bin/env python3
"""Shared Playlists: create, share a code, a friend joins and adds songs; each plays what they have.
Firebase is replaced by tests/fake-firebase.js shared between two tabs.  Run: python3 tests/shared_playlists.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-firebase.js').read_text()
def play(pg, title):
    C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, title); pg.wait_for_timeout(500)
def open_shared(pg, name=None):
    C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Shared Playlists'); pg.wait_for_timeout(500)
    if name: C.choose(pg, name); pg.wait_for_timeout(500)

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'], viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        ctx.route('https://www.gstatic.com/firebasejs/**', lambda r: r.fulfill(status=200, content_type='text/javascript',
                  body=FAKE if 'app-compat' in r.request.url else '/* fake */'))
        ctx.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,repeat:'One'}))")
        a = ctx.new_page(); a.on('pageerror', lambda e: errors.append('a: ' + str(e)))
        a.goto(url); a.wait_for_timeout(1200)
        a.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); a.wait_for_timeout(3500); C.wait_sync(a); C.home(a)
        b = ctx.new_page(); b.on('pageerror', lambda e: errors.append('b: ' + str(e)))
        b.goto(url); b.wait_for_timeout(1500)

        C.choose(a, 'Music'); C.choose(a, 'Shared Playlists'); C.choose(a, 'New Shared Playlist')
        a.fill('#inpt', 'Road Trip'); C.key(a, 'Enter', wait=900)
        check('creating opens the new playlist', a.text_content('#htitle') == 'Road Trip', a.text_content('#htitle'))
        code = a.evaluate('ipodShared.codes()[0]')
        check('it has a 6-character share code', code and len(code) == 6 and code in a.inner_text('#body'), (code, a.inner_text('#body')))
        play(a, 'Blue Hour Track'); open_shared(a, 'Road Trip'); C.choose(a, 'Add Now Playing'); a.wait_for_timeout(500)
        check('owner adds the playing song', 'Blue Hour Track' in a.inner_text('#body'), a.inner_text('#body'))
        C.choose(a, 'Add Now Playing'); a.wait_for_timeout(400)
        check('adding the same song twice is refused', 'already' in a.inner_text('.hdr'), a.inner_text('.hdr'))

        C.choose(b, 'Music'); C.choose(b, 'Shared Playlists'); C.choose(b, 'Join with Code')
        b.fill('#inpt', 'ZZZZZZ'); C.key(b, 'Enter', wait=700)
        check('a wrong code is refused', 'Couldn’t Join' in b.text_content('#htitle'))
        C.key(b, 'Escape', wait=200); C.choose(b, 'Join with Code'); b.fill('#inpt', code.lower()); C.key(b, 'Enter', wait=900)
        check('friend joins and sees the songs', b.text_content('#htitle') == 'Road Trip' and 'Blue Hour Track' in b.inner_text('#body'), b.inner_text('#body'))
        b.evaluate("ipodSharedBridge.songs().find(s=>s.title==='Red Line Track').deleted=true")   # the friend lacks this one
        play(a, 'Red Line Track'); open_shared(a, 'Road Trip'); C.choose(a, 'Add Now Playing'); a.wait_for_timeout(400)
        play(b, 'Green Room Track'); open_shared(b, 'Road Trip'); C.choose(b, 'Add Now Playing'); b.wait_for_timeout(500)
        body = b.inner_text('#body')
        check('friend adds a song too', 'Green Room Track' in body, body)
        check('songs the friend doesn’t have say so', 'Not in library' in body, body)
        check('Play counts only what you have', '2 of 3' in body, body)
        C.choose(b, 'Play'); b.wait_for_timeout(500)
        q = b.evaluate("ipodSharedBridge.cur()?.title")
        check('friend plays the ones in their library', b.text_content('#htitle') == 'Now Playing' and q in ('Blue Hour Track', 'Green Room Track'), q)
        open_shared(a, 'Road Trip')
        check('owner sees everyone’s songs', all(t in a.inner_text('#body') for t in ['Blue Hour Track', 'Red Line Track', 'Green Room Track']) and '3 of 3' in a.inner_text('#body'))
        C.home(b); C.choose(b, 'Music'); C.choose(b, 'DJ Mode'); C.choose(b, 'Sources')
        check('shared playlists are DJ Mode sources', 'Road Trip' in b.inner_text('#body'), b.inner_text('#body'))
        C.home(b); C.choose(b, 'Music'); C.choose(b, 'Wake-Up Alarm'); C.choose(b, 'Play')
        check('and alarm choices', 'Road Trip' in C.all_rows(b))
                # remove: friend can remove their own song, owner can delete the playlist
        open_shared(b, 'Road Trip'); C.choose(b, 'Red Line Track')
        check('friend can’t remove someone else’s song', 'Remove from Playlist' not in b.inner_text('#body'))
        C.home(a); open_shared(a, 'Road Trip'); C.choose(a, 'Delete Playlist'); C.choose(a, 'Delete'); a.wait_for_timeout(500)
        check('owner deletes the playlist', 'Road Trip' not in a.inner_text('#body'), a.inner_text('#body'))
        open_shared(b); b.wait_for_timeout(600)
        check('it disappears for the friend', 'Road Trip' not in b.inner_text('#body'), b.inner_text('#body'))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
