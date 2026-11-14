"""Friends must ride out slow/stalled Firebase calls instead of showing a timeout.
A fake Firebase SDK is served for www.gstatic.com: its first Firestore read hangs
forever (like a stalled WebKit channel) until the network is reset.
Run: python3 tests/friends_reliability.py"""
import threading, http.server, functools, shutil, tempfile, os, sys
from playwright.sync_api import sync_playwright
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = r"""
(function(){
 if(window.firebase&&window.firebase.__fake)return;
 const S=window.__fb={gets:0,resets:0,hangUntilReset:true,signIns:0,authDelay:0};
 class Doc{constructor(path){this.path=path}
   get(){S.gets++;const p=this.path;
     if(S.hangUntilReset&&S.resets===0)return new Promise(()=>{});
     const d=JSON.parse(localStorage.getItem('fakefs')||'{}')[p];
     return Promise.resolve({exists:!!d,data:()=>d,ref:this})}
   set(v){const all=JSON.parse(localStorage.getItem('fakefs')||'{}');all[this.path]=v;localStorage.setItem('fakefs',JSON.stringify(all));return Promise.resolve()}
   update(v){const all=JSON.parse(localStorage.getItem('fakefs')||'{}');all[this.path]=Object.assign(all[this.path]||{},v);localStorage.setItem('fakefs',JSON.stringify(all));return Promise.resolve()}}
 const coll=n=>({doc:id=>new Doc(n+'/'+id),where:()=>({get:()=>Promise.resolve({docs:[]})})});
 const db={collection:coll,settings(o){S.settings=o},disableNetwork(){S.resets++;return Promise.resolve()},enableNetwork(){return Promise.resolve()},
   runTransaction:async fn=>fn({get:d=>d.get(),set:(d,v)=>d.set(v),update:(d,v)=>d.update(v),delete:()=>{}})};
 const user={uid:'u1'};let signed=localStorage.getItem('fakeauth')==='1';
 const auth={currentUser:signed?user:null,onAuthStateChanged(cb){setTimeout(()=>cb(signed?user:null),S.authDelay);return()=>{}},
   signInAnonymously(){S.signIns++;signed=true;localStorage.setItem('fakeauth','1');return Promise.resolve({user})}};
 const app={name:'ipod-friends',auth:()=>auth,firestore:()=>db};
 const fs=()=>db;fs.FieldValue={serverTimestamp:()=>'now'};
 window.firebase={__fake:1,apps:[],initializeApp(){this.apps.push(app);return app},auth:()=>auth,firestore:fs};
})();
"""
res = []
def check(n, ok, d=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else f'  [{d}]'))
d = tempfile.mkdtemp()
for f in os.listdir(SRC):
    if f not in ('.git', 'tests', 'audio-api', 'worker', 'ios'):
        p = os.path.join(SRC, f); (shutil.copytree if os.path.isdir(p) else shutil.copy)(p, os.path.join(d, f))
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=d); H.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_port}/'
def route(r):
    if 'gstatic.com/firebasejs' in r.request.url: r.fulfill(status=200, content_type='text/javascript', body=FAKE)
    elif r.request.url.startswith('https:'): r.abort()
    else: r.continue_()
def screen(pg): return pg.evaluate("document.getElementById('htitle').textContent+' | '+document.getElementById('body').innerText.slice(0,200)")
def open_friends(pg):
    pg.evaluate("void window.ipodFriends.open()")
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome')
    ctx = b.new_context(viewport={'width': 390, 'height': 760}, service_workers='block'); ctx.route('**/*', route)
    pg = ctx.new_page(); pg.goto(URL); pg.wait_for_timeout(800)
    open_friends(pg); pg.wait_for_timeout(2000)
    check('shows Connecting while the first read is stalled', 'Connecting' in screen(pg), screen(pg))
    pg.wait_for_timeout(10500)
    s = screen(pg)
    check('stalled read is retried after a network reset — no timeout error', 'Create My Profile' in s and 'Error' not in s, s)
    check('channel was reset and retried', pg.evaluate('__fb.resets>=1 && __fb.gets>=2'), pg.evaluate('JSON.stringify(__fb)'))
    check('long polling chosen for WebKit, auto-detect elsewhere', pg.evaluate("!!(__fb.settings&&(__fb.settings.experimentalAutoDetectLongPolling||__fb.settings.experimentalForceLongPolling))"))
    # create profile, then a fresh launch should open instantly from cache even if Firestore stalls
    # Make a profile and let it be cached once, then relaunch with every read stalled.
    pg.evaluate("localStorage.setItem('fakefs',JSON.stringify({'profiles/u1':{uid:'u1',username:'tester',displayName:'tester',sharing:false}}))")
    pg.evaluate("localStorage.setItem('ipod.friends.profile',JSON.stringify({uid:'u1',username:'tester',displayName:'tester',sharing:false}))")
    pg.reload(); pg.wait_for_timeout(3500)   # background warm-up runs (its profile read stalls)
    open_friends(pg); pg.wait_for_timeout(700)
    s = screen(pg)
    check('returning user: Friends opens immediately from cache', 'My Profile' in s, s)
    check('anonymous account reused, no new sign-in', pg.evaluate('__fb.signIns===0'))
    b.close()
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)
