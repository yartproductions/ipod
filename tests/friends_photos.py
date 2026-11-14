"""Profile pictures: pick, shrink to a small JPEG, show as round avatars, remove.
Uses a fake Firebase SDK (no network). Run: python3 tests/friends_photos.py"""
import threading, http.server, functools, shutil, tempfile, os, sys, io
from PIL import Image
from playwright.sync_api import sync_playwright
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = r"""
(function(){
 if(window.firebase&&window.firebase.__fake)return;
 const DEL={__del:1};
 const load=()=>JSON.parse(localStorage.getItem('fakefs')||'{}'),save=a=>localStorage.setItem('fakefs',JSON.stringify(a));
 class Doc{constructor(p){this.path=p}
   get(){const d=load()[this.path];return Promise.resolve({exists:!!d,data:()=>d,ref:this})}
   set(v){const a=load();a[this.path]=v;save(a);return Promise.resolve()}
   update(v){const a=load(),o=Object.assign({},a[this.path]);for(const k in v){if(v[k]&&v[k].__del)delete o[k];else o[k]=v[k]}a[this.path]=o;save(a);return Promise.resolve()}}
 const db={collection:n=>({doc:id=>new Doc(n+'/'+id),where:(f,_,v)=>({get:()=>Promise.resolve({docs:Object.entries(load()).filter(([k,d])=>k.startsWith(n+'/')&&d[f]===v).map(([k,d])=>({data:()=>d,ref:new Doc(k)}))})})}),
   settings(){},disableNetwork(){return Promise.resolve()},enableNetwork(){return Promise.resolve()}};
 const user={uid:'u1'};
 const auth={currentUser:user,onAuthStateChanged(cb){setTimeout(()=>cb(user),0);return()=>{}},signInAnonymously(){return Promise.resolve({user})}};
 const app={name:'ipod-friends',auth:()=>auth,firestore:()=>db};
 const fs=()=>db;fs.FieldValue={serverTimestamp:()=>'now',delete:()=>DEL};
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
img = os.path.join(d, 'big.png')
im = Image.new('RGB', (1600, 1000), (40, 120, 200))
for x in range(0, 1600, 7):
    for y in range(0, 1000, 13): im.putpixel((x, y), ((x*7) % 255, (y*3) % 255, 90))
im.save(img)
def route(r):
    u = r.request.url
    if 'gstatic.com/firebasejs' in u: r.fulfill(status=200, content_type='text/javascript', body=FAKE)
    elif u.startswith('https:'): r.abort()
    else: r.continue_()
def rows(pg): return pg.evaluate("[...document.querySelectorAll('#body .row')].map(r=>r.innerText.replace(/\\n/g,' ').trim())")
def sel_label(pg, text):
    n = pg.evaluate("[...document.querySelectorAll('#body .row')].findIndex(r=>r.innerText.includes(%r))" % text)
    cur = pg.evaluate("[...document.querySelectorAll('#body .row')].findIndex(r=>r.classList.contains('sel'))")
    for _ in range(abs(n-cur)): pg.keyboard.press('ArrowDown' if n > cur else 'ArrowUp'); pg.wait_for_timeout(60)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome')
    ctx = b.new_context(viewport={'width': 390, 'height': 760}, service_workers='block'); ctx.route('**/*', route)
    pg = ctx.new_page(); pg.goto(f'http://127.0.0.1:{srv.server_port}/'); pg.wait_for_timeout(700)
    pg.evaluate("localStorage.setItem('fakefs',JSON.stringify({'profiles/u1':{uid:'u1',username:'tester',displayName:'Tess',sharing:false},'profiles/u2':{uid:'u2',username:'bob',displayName:'Bob',sharing:true},'friendRequests/u2_u1':{from:'u2',to:'u1',status:'accepted'}}))")
    pg.evaluate("void window.ipodFriends.open()"); pg.wait_for_timeout(800)
    av = pg.evaluate("(()=>{const t=document.querySelector('#body .row .thumb.av');return t&&[getComputedStyle(t).borderRadius,t.style.backgroundImage.slice(0,40)]})()")
    check('My Profile row shows a round initials avatar', av and av[0] == '50%' and 'svg' in av[1], av)
    sel_label(pg, 'My Profile'); pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
    check('My Profile shows name + picture option', any('Tess' in r for r in rows(pg)) and any('Profile Picture' in r for r in rows(pg)), rows(pg))
    sel_label(pg, 'Profile Picture'); pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
    sel_label(pg, 'Choose Picture')
    with pg.expect_file_chooser() as fc: pg.keyboard.press('Enter')
    fc.value.set_files(img); pg.wait_for_timeout(1500)
    photo = pg.evaluate("JSON.parse(localStorage.getItem('fakefs'))['profiles/u1'].photo||''")
    check('picture saved as a small JPEG data URL', photo.startswith('data:image/jpeg;base64,') and len(photo) <= 40000, len(photo))
    dims = pg.evaluate("new Promise(r=>{const i=new Image();i.onload=()=>r([i.width,i.height]);i.src=JSON.parse(localStorage.getItem('fakefs'))['profiles/u1'].photo})")
    check('cropped to a 128×128 square', dims == [128, 128], dims)
    check('confirms the save', any('Picture Saved' in r for r in [pg.inner_text('#body')]), pg.inner_text('#body'))
    pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
    check('picture menu now shows it and offers Remove', any('Set' in r for r in rows(pg)) and any('Remove Picture' in r for r in rows(pg)), rows(pg))
    check('cached for instant open', 'data:image/jpeg' in pg.evaluate("localStorage.getItem('ipod.friends.profile')"))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    check('back in My Profile, the new picture is shown', 'data:image/jpeg' in pg.evaluate("document.querySelector('#body .row .thumb.av').style.backgroundImage"))
    pg.screenshot(path=os.environ.get('SHOT','/tmp/fp1.png'), clip={'x':0,'y':0,'width':390,'height':330})
    pg.evaluate("void window.ipodFriends.open()"); pg.wait_for_timeout(600)
    sel_label(pg, 'My Friends'); pg.keyboard.press('Enter'); pg.wait_for_timeout(700)
    fr = pg.evaluate("[...document.querySelectorAll('#body .row')].map(r=>[r.innerText,!!r.querySelector('.thumb.av')])")
    check('friends list shows avatars', fr and fr[0][1] and '@bob' in fr[0][0], fr)
    pg.evaluate("void window.ipodFriends.open()"); pg.wait_for_timeout(500)
    sel_label(pg, 'My Profile'); pg.keyboard.press('Enter'); pg.wait_for_timeout(200)
    sel_label(pg, 'Profile Picture'); pg.keyboard.press('Enter'); pg.wait_for_timeout(200)
    sel_label(pg, 'Remove Picture'); pg.keyboard.press('Enter'); pg.wait_for_timeout(800)
    pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
    check('Remove Picture deletes it', 'photo' not in pg.evaluate("JSON.parse(localStorage.getItem('fakefs'))['profiles/u1']") and any('Initials' in r for r in rows(pg)), rows(pg))
    b.close()
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)
