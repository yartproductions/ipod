#!/usr/bin/env python3
"""Friends social: activity feed on the split screen, top songs this week, taste match, sending songs.
Firebase is replaced by tests/fake-firebase.js.   Run: python3 tests/friends_social.py"""
import sys, tempfile, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-firebase.js').read_text()
NOW = int(time.time() * 1000)
SEED = """(()=>{if(sessionStorage.getItem('seeded'))return;sessionStorage.setItem('seeded','1');
 sessionStorage.setItem('fakeuid:ipod-friends','me');
 const put=(p,d)=>localStorage.setItem('fakefs:'+p,JSON.stringify(d));
 put('profiles/me',{uid:'me',username:'me_1',displayName:'Me',sharing:true});
 put('profiles/alex',{uid:'alex',username:'alex_k',displayName:'Alex',sharing:true});
 put('friendRequests/alex_me',{from:'alex',to:'me',status:'accepted'});
 put('activity/alex',{uid:'alex',recent:[{title:'Golden Hour (Extended Sunrise Version)',artist:'Sunny Days',album:'',artworkUrl:'',listenedAt:{__ts:%d}}],
   week:[{title:'Golden Hour',artist:'Sunny Days',plays:7},{title:'Late Train',artist:'Night Bus',plays:3}],artists:['Fixture Artist','Sunny Days','Night Bus'],updatedAt:{__ts:%d}});
 localStorage.setItem('ipod.friends.profile',JSON.stringify({uid:'me',username:'me_1',displayName:'Me',sharing:true}));
 localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,split:'Now Playing',repeat:'One'}));})()""" % (NOW - 2 * 60000, NOW)

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, device_scale_factor=2, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        ctx.route('https://www.gstatic.com/firebasejs/**', lambda r: r.fulfill(status=200, content_type='text/javascript',
                  body=FAKE if 'app-compat' in r.request.url else '/* fake */'))
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script(SEED)
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.set_input_files('#file', sorted(str(f) for f in C.FIX.glob('album-*.mp3'))); pg.wait_for_timeout(3500); C.wait_sync(pg); C.home(pg)
        C.choose(pg, 'Music'); C.choose(pg, 'Offline Music'); C.choose(pg, 'Songs'); C.choose(pg, 'Blue Hour Track'); pg.wait_for_timeout(600)
        C.home(pg); pg.wait_for_timeout(6500)
        feed = pg.locator('#splitfeed')
        check('the main menu split screen shows what a friend is playing', 'on' in (feed.get_attribute('class') or '') and '@alex_k' in feed.inner_text() and 'Golden Hour' in feed.inner_text(), feed.inner_text() if feed.count() else '')
        check('a friend who just played shows “Listening now”', 'Listening now' in feed.text_content() and 'islive' in feed.get_attribute('class'), feed.inner_text())
        pg.wait_for_timeout(300); pg.screenshot(path='/tmp/shots/friend-feed.png', clip=pg.locator('#screen').bounding_box())
        x1 = pg.evaluate("getComputedStyle(document.querySelector('#splitfeed .mq>span')).transform"); pg.wait_for_timeout(1500)
        x2 = pg.evaluate("getComputedStyle(document.querySelector('#splitfeed .mq>span')).transform")
        check('a long song name slides across', pg.locator('#splitfeed .mq.go').count() == 1 and x1 != x2, (x1, x2))
        pg.wait_for_timeout(1200); pg.screenshot(path='/tmp/shots/friend-feed-slide.png', clip=pg.locator('#screen').bounding_box())
        pg.screenshot(path='/tmp/shots/friend-feed.png', clip=pg.locator('#screen').bounding_box())
        # bridge stats: what you'd share
        st = pg.evaluate("ipodFriendsBridge.stats()")
        check('your shared stats include top artists', 'artists' in st and isinstance(st['week'], list), st)
        # friend card: top this week + taste match + send
        pg.evaluate("localStorage.setItem('ipod.listeningHistory',JSON.stringify([]))")
        C.home(pg); C.choose(pg, 'Friends'); pg.wait_for_timeout(1500); C.choose(pg, 'My Friends'); pg.wait_for_timeout(1200); C.choose(pg, '@alex_k'); pg.wait_for_timeout(1500)
        rows = C.all_rows(pg)
        check('a friend’s card shows Top This Week', 'Top This Week' in rows, rows)
        C.choose(pg, 'Top This Week')
        check('…their most played songs this week', '1. Golden Hour' in C.all_rows(pg) and '7 plays' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.key(pg, 'Escape', wait=300)
        check('the card shows a Taste Match', any(r == 'Taste Match' for r in C.all_rows(pg)) and '%' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, 'Taste Match')
        check('…naming the artists you share', 'Fixture Artist' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.screenshot(path='/tmp/shots/taste.png', clip=pg.locator('#screen').bounding_box())
        # send a song from Now Playing's options
        C.home(pg); C.choose(pg, 'Now Playing'); pg.wait_for_timeout(300)
        pg.keyboard.press('Enter'); pg.wait_for_timeout(60); pg.keyboard.press('Enter'); pg.wait_for_timeout(400)
        C.choose(pg, 'Send to a Friend'); pg.wait_for_timeout(1500)
        check('Send to a Friend lists your friends', '@alex_k' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, '@alex_k'); C.choose(pg, 'Send with a Note'); pg.fill('#inpt', 'this one is for you'); C.key(pg, 'Enter', wait=1200)
        sent = pg.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('fakefs:sends/')).map(k=>JSON.parse(localStorage.getItem(k)))")
        check('the song is sent to the friend with the note', any(x['to'] == 'alex' and x['from'] == 'me' and x['title'] == 'Blue Hour Track' and x['note'] == 'this one is for you' for x in sent), sent)
        check('…and it says so', 'Sent to @alex_k' in pg.text_content('#htitle'), pg.text_content('#htitle'))
        # receiving one
        pg.evaluate("""(()=>{const k='fakefs:sends/s1';localStorage.setItem(k,JSON.stringify({from:'alex',to:'me',title:'Red Line Track',artist:'Fixture Artist',album:'',artworkUrl:'',note:'turn it up',createdAt:{__ts:Date.now()}}));
          window.dispatchEvent(new StorageEvent('storage',{key:k}))})()""")
        pg.wait_for_timeout(1500)
        notes = pg.evaluate("JSON.parse(localStorage.getItem('ipod.notifications')||'[]')")
        check('a song from a friend raises a notification', any('sent you a song' in n['title'] and 'Red Line Track' in n['body'] for n in notes), notes)
        C.home(pg); C.choose(pg, 'Friends'); pg.wait_for_timeout(800); C.choose(pg, 'Songs for You'); pg.wait_for_timeout(1500)
        check('Songs for You lists it with who sent it', 'Red Line Track' in pg.inner_text('#body') and '@alex_k' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, 'Red Line Track')
        check('…with the note, and Play It when it’s in your library', 'turn it up' in pg.inner_text('#body') and 'Play It' in C.all_rows(pg), C.all_rows(pg))
        C.choose(pg, 'Play It'); pg.wait_for_timeout(600)
        check('Play It plays it', pg.text_content('#htitle') == 'Now Playing' and 'Red Line Track' in pg.inner_text('#body'))
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
