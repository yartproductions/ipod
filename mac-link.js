/* iPod ▸ Mac Display — the phone keeps playing; a Mac (mac.html) shows a big Cover Flow and synced lyrics.
   Pairing: the Mac shows a 6-character code; you type it on the iPod. State flows one way, phone → Mac,
   through the same Firebase project as Friends (anonymous sign-in, rules in firestore.rules). */
(function(){
'use strict';
const B=window.ipodMacBridge;
if(!B){console.error('iPod Mac Display: player bridge unavailable');return}
const CONFIG={apiKey:"AIzaSyDSMe2R6QTVd3htWfP7-ScKMZyWd5dePNU",authDomain:"ipod-friends.firebaseapp.com",projectId:"ipod-friends",
  storageBucket:"ipod-friends.firebasestorage.app",messagingSenderId:"222255543131",appId:"1:222255543131:web:135687a1679707d515e07e"};
const SDK='13.3.0',KEY='ipod.mac.code',CODE_RE=/^[A-HJ-NP-Z2-9]{6}$/;
let db=null,uid=null,code=null,pairRef=null,timer=null,lastSig='',lastWrite=0,pending=null,status='off',unwatch=null;
const sentArt=new Set(),sentLyrics=new Set();

/* ---- Firebase ---- */
function loadScript(file){
  return new Promise((ok,fail)=>{const s=document.createElement('script');s.src=`https://www.gstatic.com/firebasejs/${SDK}/${file}`;
    s.onload=ok;s.onerror=()=>{s.remove();fail(Error('Could not load '+file))};document.head.appendChild(s)});
}
let connecting=null;
async function connect(){
  if(db)return;
  if(connecting)return connecting;
  connecting=(async()=>{
    if(!(window.firebase&&firebase.initializeApp))await loadScript('firebase-app-compat.js');
    if(!firebase.auth)await loadScript('firebase-auth-compat.js');
    if(!firebase.firestore)await loadScript('firebase-firestore-compat.js');
    let app=firebase.apps.find(a=>a.name==='ipod-mac'),fresh=!app;
    if(!app)app=firebase.initializeApp(CONFIG,'ipod-mac');
    const store=app.firestore(),auth=app.auth();
    if(fresh){const webkit=/AppleWebKit/.test(navigator.userAgent)&&!/Chrome|Chromium|Android/.test(navigator.userAgent);
      try{store.settings(webkit?{experimentalForceLongPolling:true,merge:true}:{experimentalAutoDetectLongPolling:true,merge:true})}catch(e){}}
    const user=await new Promise(r=>{const u=auth.onAuthStateChanged(x=>{u();r(x)},()=>r(null))});
    uid=(user||(await auth.signInAnonymously()).user).uid;db=store;
  })();
  try{await connecting}finally{connecting=null}
}
const now=()=>firebase.firestore.FieldValue.serverTimestamp();

/* ---- pairing ---- */
async function pair(raw){
  const c=String(raw||'').toUpperCase().replace(/[^A-Z0-9]/g,'');
  if(!CODE_RE.test(c))throw Error('Codes are 6 letters and numbers, like K7MQ4D.');
  await connect();
  const ref=db.collection('pairs').doc(c);
  try{await ref.update({phone:uid,pairedAt:now()})}
  catch(e){
    if(e.code==='not-found')throw Error('No Mac is showing that code. Check the code on your Mac.');
    if(e.code==='permission-denied')throw Error('That code has expired or is already in use. Your Mac will show a fresh one.');
    throw e;
  }
  start(c);window.ipodAchievements?.event('mac');
}
function start(c){
  stop(false);code=c;pairRef=db.collection('pairs').doc(c);status='on';sentArt.clear();sentLyrics.clear();lastSig='';
  try{localStorage.setItem(KEY,c)}catch(e){}
  timer=setInterval(tick,250);tick(true);
  // the Mac ended the session (or it was deleted): stop sending
  unwatch=pairRef.onSnapshot(d=>{if(!d.exists){stop(true);B.toast?.('Mac Display disconnected')}},()=>{});
}
function stop(forget){
  clearInterval(timer);timer=null;if(unwatch){try{unwatch()}catch(e){}unwatch=null}
  status='off';if(forget){code=null;pairRef=null;try{localStorage.removeItem(KEY)}catch(e){}}
}
async function disconnect(){
  const ref=pairRef;stop(true);
  if(ref)try{await ref.delete()}catch(e){}
}
async function resume(){
  let c=null;try{c=localStorage.getItem(KEY)}catch(e){}
  if(!c)return;
  try{await connect();const d=await db.collection('pairs').doc(c).get();
    if(d.exists&&d.data().phone===uid)start(c);else localStorage.removeItem(KEY)}catch(e){}
}

/* ---- what the Mac sees ---- */
function hashKey(s){let h=2166136261;for(const ch of String(s)){h^=ch.charCodeAt(0);h=Math.imul(h,16777619)}return 'a'+(h>>>0).toString(36)}
const songKey=s=>'s'+hashKey((s.id||'')+'|'+s.title+'|'+s.artist).slice(1);
function viewItems(){
  const v=B.top();
  if(v&&v.type==='flow'&&Array.isArray(v.albums)&&v.albums.length){
    const from=Math.max(0,v.sel-10),to=Math.min(v.albums.length,v.sel+11);
    return {mode:'flow',title:v.title||'Flow',sel:v.sel-from,total:v.albums.length,
      items:v.albums.slice(from,to).map((a,i)=>{const art=a.art||B.artFor(a.songs&&a.songs[0]);
        return {id:hashKey((from+i)+'|'+(a.album||'')+'|'+(a.artist||'')),k:art?hashKey(art):'',t:String(a.album||'').slice(0,140),a:String(a.artist||'').slice(0,140),_art:art}})};
  }
  const q=B.queue(),qi=B.qi();
  if(!q.length||qi<0)return {mode:'idle',items:[],sel:0,title:''};
  const from=Math.max(0,qi-8),to=Math.min(q.length,qi+9);
  return {mode:'now',title:'Now Playing',sel:qi-from,total:q.length,
    items:q.slice(from,to).map((s,i)=>{const art=B.nowPlayingArt(s);
      return {id:hashKey((from+i)+'|'+songKey(s)),k:art?hashKey(art):'',t:String(s.title||'').slice(0,140),a:String(s.artist||'').slice(0,140),_art:art}})};
}
function snapshot(){
  const s=B.cur(),view=viewItems(),art=s?B.nowPlayingArt(s):null;
  const np=s?{k:art?hashKey(art):'',sk:songKey(s),t:String(s.title||'').slice(0,140),a:String(s.artist||'').slice(0,140),
    al:String(s.album||'').slice(0,140),pos:Math.round(B.time()*100)/100,dur:Math.round((B.duration()||0)*10)/10,playing:!B.paused()}:null;
  if(s&&art)view.items.push({k:np.k,_art:art,_only:1});   // make sure the current cover is sent
  return {view,np};
}
function tick(force){
  if(!pairRef)return;
  const {view,np}=snapshot();
  const posBucket=np?Math.floor(np.pos/8):0;   // heartbeat every ~8 s keeps the lyrics in time
  const sig=JSON.stringify([view.mode,view.sel,view.items.map(x=>x.id),np&&[np.sk,np.playing,posBucket,np.dur]]);
  const jumped=np&&lastNp&&np.sk===lastNp.sk&&Math.abs(np.pos-(lastNp.pos+(Date.now()-lastNpAt)/1000*(lastNp.playing?1:0)))>1.5;
  if(!force&&sig===lastSig&&!jumped)return;
  lastSig=sig;
  view.items.filter(x=>x.k&&x._art).forEach(x=>sendArt(x.k,x._art));
  if(np)sendLyrics(np.sk);
  const state={v:1,mode:view.mode,title:view.title,sel:view.sel,total:view.total||0,
    items:view.items.filter(x=>!x._only).map(({id,k,t,a})=>({id,k,t,a})),np};
  lastNp=np;lastNpAt=Date.now();
  queueWrite(state);
}
let lastNp=null,lastNpAt=0;
// Scrolling a flow can change state many times a second: send at most ~6 writes/s, always the latest.
function queueWrite(state){
  pending=state;const wait=Math.max(0,160-(Date.now()-lastWrite));
  if(queueWrite.t)return;
  queueWrite.t=setTimeout(()=>{queueWrite.t=null;const st=pending;pending=null;lastWrite=Date.now();
    pairRef?.update({state:st,updatedAt:now()}).catch(e=>{if(e.code==='permission-denied'||e.code==='not-found'){stop(true)}})},wait);
}
async function thumb(url){
  return new Promise(res=>{
    const im=new Image();if(/^https?:/.test(url))im.crossOrigin='anonymous';
    im.onload=()=>{try{const c=document.createElement('canvas'),n=240;c.width=c.height=n;const g=c.getContext('2d');
      const s=Math.min(im.naturalWidth,im.naturalHeight)||n;g.drawImage(im,(im.naturalWidth-s)/2,(im.naturalHeight-s)/2,s,s,0,0,n,n);
      res(c.toDataURL('image/jpeg',.74))}catch(e){res(null)}};
    im.onerror=()=>res(null);im.src=url;
  });
}
async function sendArt(k,url){
  if(sentArt.has(k)||!pairRef)return;sentArt.add(k);
  let data=await thumb(url);
  const doc=data&&data.length<=60000?{data}:/^https:\/\//.test(url)&&url.length<=500?{url}:null;
  if(!doc)return;
  pairRef.collection('art').doc(k).set(doc).catch(()=>sentArt.delete(k));
}
async function sendLyrics(sk){
  if(sentLyrics.has(sk)||!pairRef)return;
  const s=B.cur();if(!s||songKey(s)!==sk)return;
  sentLyrics.add(sk);
  let data=null;try{data=await B.lyrics(s)}catch(e){}
  if(!pairRef)return;
  const lines=(data&&data.lines||[]).slice(0,400).map(x=>({at:Math.round(x.at*100)/100,t:String(x.text).slice(0,200)}));
  const text=lines.length?'':String(data&&data.text||'').slice(0,12000);
  pairRef.collection('lyrics').doc(sk).set({lines,text,source:String(data&&data.source||'').slice(0,20)}).catch(()=>sentLyrics.delete(sk));
}

/* ---- iPod menu: Settings ▸ Mac Display ---- */
function open(){
  if(status==='on')return B.push(B.list('Mac Display',()=>[
    {label:'Connected',val:code||'',action:()=>{}},
    {label:'Disconnect',action:async()=>{await disconnect();B.pop();B.render()}},
    {label:'How It Works',chev:1,action:B.go(B.msgView('Mac Display','Your phone keeps playing. The Mac shows Cover Flow and the lyrics; spin through any Flow here and the Mac follows.'))},
  ]));
  B.push(B.inputView('Mac Display','Code shown on your Mac',async val=>{
    B.replaceTop(B.loadingView('Connecting…'));
    try{await pair(val);B.replaceTop(B.msgView('Mac Connected','Your Mac now shows what’s playing. Open any Flow to browse it on the big screen.'))}
    catch(e){B.replaceTop(B.msgView('Couldn’t Connect',e.message||'Please try again.'))}
  }));
}
window.ipodMac=Object.freeze({open,get status(){return status},get code(){return code},disconnect,_tick:()=>tick(true)});
resume();
})();
