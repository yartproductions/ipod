#!/usr/bin/env python3
"""Notifications: banner, header dot, main-menu entry, list, and live friend-request notifications.
Run: python3 tests/notifications.py"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
FAKE = (Path(__file__).parent / 'fake-firebase.js').read_text()
SEED = """(()=>{if(sessionStorage.getItem('seeded'))return;sessionStorage.setItem('seeded','1');
 sessionStorage.setItem('fakeuid:ipod-friends','me');
 const put=(p,d)=>localStorage.setItem('fakefs:'+p,JSON.stringify(d));
 put('profiles/me',{uid:'me',username:'me_1',displayName:'Me',sharing:true});
 put('profiles/alex',{uid:'alex',username:'alex_k',displayName:'Alex',sharing:true});
 put('profiles/sam',{uid:'sam',username:'sam_r',displayName:'Sam',sharing:true});
 put('friendRequests/alex_me',{from:'alex',to:'me',status:'pending',updatedAt:{__ts:1700000000000}});
 put('friendRequests/me_sam',{from:'me',to:'sam',status:'pending'});
 localStorage.setItem('ipod.friends.profile',JSON.stringify({uid:'me',username:'me_1',displayName:'Me',sharing:true}));
 localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}));})()"""

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox'], viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        ctx.route('https://www.gstatic.com/firebasejs/**', lambda r: r.fulfill(status=200, content_type='text/javascript',
                  body=FAKE if 'app-compat' in r.request.url else '/* fake */'))
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script(SEED)
        pg.goto(url); pg.wait_for_timeout(1200)
        pg.wait_for_timeout(3500)   # the Friends watcher starts ~3 s after launch
        check('a pending friend request raises a banner', pg.locator('.nbanner').count() >= 1 and 'alex_k' in pg.inner_text('.nbanner'), pg.inner_text('#screen')[:120])
        pg.screenshot(path='/tmp/shots/notif-banner.png', clip=pg.locator('#screen').bounding_box())
        check('the header shows the red dot', 'on' in pg.get_attribute('#nbell', 'class'))
        check('Notifications appears at the top of the main menu with the count', C.all_rows(pg)[0] == 'Notifications' and '1' in pg.inner_text('#body'), C.all_rows(pg))
        # a request I sent gets accepted -> notification
        pg.evaluate("""(()=>{const k='fakefs:friendRequests/me_sam',d=JSON.parse(localStorage.getItem(k));d.status='accepted';localStorage.setItem(k,JSON.stringify(d));
          window.dispatchEvent(new StorageEvent('storage',{key:k}))})()""")
        pg.wait_for_timeout(5000)
        notes = pg.evaluate("JSON.parse(localStorage.getItem('ipod.notifications'))")
        check('an accepted request raises a notification', any('sam_r accepted' in n['body'] for n in notes), notes)
        C.home(pg); C.choose(pg, 'Notifications')
        rows = C.all_rows(pg)
        check('the list shows newest first, unread marked', rows[0].startswith('● Request Accepted') and any('Friend Request' in r for r in rows), rows)
        pg.screenshot(path='/tmp/shots/notif-list.png', clip=pg.locator('#screen').bounding_box())
        pg.reload(); pg.wait_for_timeout(5000)
        notes2 = pg.evaluate("JSON.parse(localStorage.getItem('ipod.notifications'))")
        check('the same request doesn’t notify again after a reload', len(notes2) == len(notes), (len(notes), len(notes2)))
        C.home(pg); C.choose(pg, 'Notifications'); C.choose(pg, 'Mark All as Read'); C.home(pg)
        check('reading them clears the dot and the menu entry', 'on' not in (pg.get_attribute('#nbell', 'class') or '') and C.all_rows(pg)[0] != 'Notifications')
        C.choose(pg, 'Library'); C.choose(pg, 'Notifications'); C.choose(pg, 'Clear All')
        check('Clear All empties the list', 'No notifications' in pg.inner_text('#body'))
        pg.evaluate("ipodNotify({id:'x1',kind:'info',title:'Hello',body:'World'})"); pg.wait_for_timeout(300)
        pg.evaluate("ipodNotify({id:'x1',kind:'info',title:'Hello',body:'World'})"); pg.wait_for_timeout(300)
        check('a notification id only ever shows once', len(pg.evaluate("JSON.parse(localStorage.getItem('ipod.notifications'))")) == 1)
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
