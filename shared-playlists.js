/* iPod ▸ Shared Playlists — playlists you build together with friends. Anyone with the 6-character code
   can add songs; everyone plays the songs they have in their own library (nothing is downloaded).
   Stored in the Friends Firebase project: sharedPlaylists/{code} and sharedPlaylists/{code}/tracks. */
(function(){
'use strict';
const B=window.ipodSharedBridge;
if(!B){console.error('iPod Shared Playlists: player bridge unavailable');return}
const CONFIG={apiKey:"AIzaSyDSMe2R6QTVd3htWfP7-ScKMZyWd5dePNU",authDomain:"ipod-friends.firebaseapp.com",projectId:"ipod-friends",
  storageBucket:"ipod-friends.firebasestorage.app",messagingSenderId:"222255543131",appId:"1:222255543131:web:135687a1679707d515e07e"};
const SDK='13.3.0',ABC='ABCDEFGHJKLMNPQRSTUVWXYZ23456789',CODE_RE=/^[A-HJ-NP-Z2-9]{6}$/,KEY='ipod.shared.codes';
let db=null,uid=null;
const cache=new Map();   // code -> {meta, tracks:[...]}
const now=()=>firebase.firestore.FieldValue.serverTimestamp();
const myName=()=>{try{return (JSON.parse(localStorage.getItem('ipod.friends.profile')||'null')?.displayName||'').slice(0,32)}catch(e){return ''}};
const codes=()=>{try{const x=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(x)?x:[]}catch(e){return []}};
const saveCodes=x=>{try{localStorage.setItem(KEY,JSON.stringify([...new Set(x)]))}catch(e){}};

function loadScript(f){return new Promise((ok,no)=>{const s=document.createElement('script');s.src=`https://www.gstatic.com/firebasejs/${SDK}/${f}`;s.onload=ok;s.onerror=()=>{s.remove();no(Error('Could not load '+f))};document.head.appendChild(s)})}
let connecting=null;
async function connect(){
  if(db)return;if(connecting)return connecting;
  connecting=(async()=>{
    if(!(window.firebase&&firebase.initializeApp))await loadScript('firebase-app-compat.js');
    if(!firebase.auth)await loadScript('firebase-auth-compat.js');
    if(!firebase.firestore)await loadScript('firebase-firestore-compat.js');
    let app=firebase.apps.find(a=>a.name==='ipod-shared'),fresh=!app;
    if(!app)app=firebase.initializeApp(CONFIG,'ipod-shared');
    const store=app.firestore(),auth=app.auth();
    if(fresh){const webkit=/AppleWebKit/.test(navigator.userAgent)&&!/Chrome|Chromium|Android/.test(navigator.userAgent);
      try{store.settings(webkit?{experimentalForceLongPolling:true,merge:true}:{experimentalAutoDetectLongPolling:true,merge:true})}catch(e){}}
    const user=await new Promise(r=>{const u=auth.onAuthStateChanged(x=>{u();r(x)},()=>r(null))});
    uid=(user||(await auth.signInAnonymously()).user).uid;db=store;
  })();
  try{await connecting}finally{connecting=null}
}
const friendly=e=>e&&e.code==='permission-denied'?'Shared Playlists need the updated Firestore rules (firebase deploy --only firestore:rules).'
  :e&&e.message||'Couldn’t reach the server. Try again.';

/* ---- matching a shared track to your own library ---- */
const norm=x=>String(x||'').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g,'')
  .replace(/\s*[\(\[][^)\]]*(remaster|live|version|edit|mono|stereo|feat|ft\.)[^)\]]*[\)\]]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
function findLocal(t){
  const live=B.songs().filter(s=>!s.deleted),tt=norm(t.t),a=norm(t.a);
  return live.find(s=>norm(s.title)===tt&&norm(s.artist)===a)
    ||live.find(s=>norm(s.title)===tt&&a&&(norm(s.artist).includes(a)||a.includes(norm(s.artist))))
    ||live.find(s=>norm(s.title)===tt&&t.al&&norm(s.album)===norm(t.al));
}

/* ---- data ---- */
async function create(name){
  await connect();
  for(let i=0;i<5;i++){
    const c=Array.from(crypto.getRandomValues(new Uint32Array(6)),n=>ABC[n%ABC.length]).join('');
    try{await db.collection('sharedPlaylists').doc(c).set({owner:uid,ownerName:myName()||'Someone',name:String(name).trim().slice(0,60),createdAt:now(),updatedAt:now()});
      saveCodes([c,...codes()]);return c}
    catch(e){if(e.code==='permission-denied'||i===4)throw Error(friendly(e))}
  }
}
async function join(raw){
  const c=String(raw||'').toUpperCase().replace(/[^A-Z0-9]/g,'');
  if(!CODE_RE.test(c))throw Error('Codes are 6 letters and numbers, like K7MQ4D.');
  await connect();
  let d;try{d=await db.collection('sharedPlaylists').doc(c).get()}catch(e){throw Error(friendly(e))}
  if(!d.exists)throw Error('No shared playlist has that code.');
  saveCodes([c,...codes()]);return c;
}
async function load(c){
  await connect();
  const ref=db.collection('sharedPlaylists').doc(c),d=await ref.get();
  if(!d.exists){saveCodes(codes().filter(x=>x!==c));cache.delete(c);return null}
  const q=await ref.collection('tracks').get();
  const tracks=(q.docs||[]).map(x=>({id:x.id,...x.data()})).sort((a,b)=>(a.addedAt?.toMillis?.()||0)-(b.addedAt?.toMillis?.()||0));
  const v={code:c,meta:d.data(),tracks};cache.set(c,v);return v;
}
async function addSong(c,s){
  await connect();
  const ref=db.collection('sharedPlaylists').doc(c),v=cache.get(c);
  if(v&&v.tracks.some(t=>norm(t.t)===norm(s.title)&&norm(t.a)===norm(s.artist)))throw Error('“'+s.title+'” is already on this playlist.');
  await ref.collection('tracks').add({t:String(s.title||'').slice(0,140),a:String(s.artist||'').slice(0,140),al:String(s.album||'').slice(0,140),
    by:uid,byName:myName()||'Someone',addedAt:now()});
  await ref.update({updatedAt:now()}).catch(()=>{});
  window.ipodAchievements?.event('sharedAdd');
}
async function removeTrack(c,t){await connect();await db.collection('sharedPlaylists').doc(c).collection('tracks').doc(t.id).delete()}
async function leave(c){saveCodes(codes().filter(x=>x!==c));cache.delete(c)}
async function destroy(c){
  await connect();const ref=db.collection('sharedPlaylists').doc(c),v=cache.get(c)||await load(c);
  for(const t of (v?.tracks||[]))await ref.collection('tracks').doc(t.id).delete().catch(()=>{});
  await ref.delete();await leave(c);
}

/* ---- iPod screens ---- */
function playlistView(c){
  const v=B.list('Shared Playlist',()=>{
    const x=cache.get(c);
    if(!x)return [{label:'Loading…',action:()=>{}}];
    const have=x.tracks.map(t=>({t,song:findLocal(t)})),local=have.filter(h=>h.song).map(h=>h.song),cur=B.cur();
    return [
      {label:'Play',icon:'play',val:local.length+' of '+x.tracks.length,action:()=>{if(local.length){B.playList(local,0);B.push(B.nowView())}else B.toast('None of these are in your library yet')}},
      {label:'Shuffle',icon:'shuffle',action:()=>{if(local.length){B.playList(B.shuffled(local),0);B.push(B.nowView())}}},
      ...(cur?[{label:'Add Now Playing',icon:'plus',val:cur.title,action:async()=>{try{await addSong(c,cur);await load(c);B.toast('Added “'+cur.title+'”');B.render()}catch(e){B.toast(e.message)}}}]:[]),
      {label:'Share Code',val:c,action:()=>B.push(B.msgView('Code: '+c,'Friends open Music ▸ Shared Playlists ▸ Join with Code and type '+c+'. Everyone can add songs; each person plays the ones in their own library.'))},
      ...have.map(({t,song})=>({label:t.t,val:song?(t.byName||''):'Not in library',
        action:()=>song?(B.playList(local,local.indexOf(song)),B.push(B.nowView())):B.push(trackView(c,t))})),
      {label:x.meta.owner===uid?'Delete Playlist':'Leave Playlist',action:()=>B.push(B.list(x.meta.owner===uid?'Delete for Everyone?':'Leave Playlist?',[
        {label:'Cancel',action:()=>B.pop()},
        {label:x.meta.owner===uid?'Delete':'Leave',action:async()=>{try{x.meta.owner===uid?await destroy(c):await leave(c)}catch(e){}B.pop();B.pop();B.render()}}]))},
    ];
  });
  v.title=cache.get(c)?.meta.name||'Shared Playlist';
  load(c).then(x=>{if(x){v.title=x.meta.name}B.render()}).catch(e=>B.toast(friendly(e)));
  return v;
}
function trackView(c,t){
  const x=cache.get(c),mine=t.by===uid||x?.meta.owner===uid;
  return B.list(t.t,[
    {label:'Artist',val:t.a},{label:'Album',val:t.al||'—'},{label:'Added by',val:t.byName||'—'},
    {label:'Not in your library',val:'add it to play'},
    ...(mine?[{label:'Remove from Playlist',action:async()=>{try{await removeTrack(c,t);await load(c)}catch(e){B.toast(friendly(e))}B.pop();B.render()}}]:[]),
  ]);
}
function menu(){
  return B.list('Shared Playlists',()=>[
    ...codes().map(c=>({label:cache.get(c)?.meta.name||'Playlist '+c,val:cache.get(c)?String(cache.get(c).tracks.length):'',chev:1,action:()=>B.push(playlistView(c))})),
    {label:'New Shared Playlist',icon:'plus',chev:1,action:()=>B.push(B.inputView('New Shared Playlist','Name it',async name=>{
      B.replaceTop(B.loadingView('Creating…'));
      try{const c=await create(name);window.ipodAchievements?.event('sharedCreate');B.replaceTop(playlistView(c))}
      catch(e){B.replaceTop(B.msgView('Couldn’t Create',e.message))}}))},
    {label:'Join with Code',icon:'people',chev:1,action:()=>B.push(B.inputView('Join Shared Playlist','Code from your friend',async val=>{
      B.replaceTop(B.loadingView('Joining…'));
      try{const c=await join(val);B.replaceTop(playlistView(c))}catch(e){B.replaceTop(B.msgView('Couldn’t Join',e.message))}}))},
  ]);
}
// warm the names in the background so the list shows them
async function warm(){for(const c of codes())try{await load(c)}catch(e){}}
window.ipodShared=Object.freeze({open:()=>{B.push(menu());warm().then(()=>B.render())},codes,
  songsOf:c=>(cache.get(c)?.tracks||[]).map(findLocal).filter(Boolean),nameOf:c=>cache.get(c)?.meta.name||'Shared Playlist'});
// load your shared playlists shortly after launch so DJ Mode and the alarm can use them
if(codes().length)setTimeout(()=>warm().catch(()=>{}),2500);
})();
