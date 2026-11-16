/* iPod ▸ Listen Together — one person hosts, friends join with a 6-character code and hear the same
   song at the same moment, each from their own library. The host's iPod streams what it's playing
   (song, position, play/pause) through the Friends Firebase project; guests follow it.
   Nothing is downloaded: a guest who doesn't have a song sees it and picks up again on the next one they do. */
(function(){
'use strict';
const B=window.ipodListenBridge;
if(!B){console.error('iPod Listen Together: player bridge unavailable');return}
const CONFIG={apiKey:"AIzaSyDSMe2R6QTVd3htWfP7-ScKMZyWd5dePNU",authDomain:"ipod-friends.firebaseapp.com",projectId:"ipod-friends",
  storageBucket:"ipod-friends.firebasestorage.app",messagingSenderId:"222255543131",appId:"1:222255543131:web:135687a1679707d515e07e"};
const SDK='13.3.0',ABC='ABCDEFGHJKLMNPQRSTUVWXYZ23456789',CODE_RE=/^[A-HJ-NP-Z2-9]{6}$/,KEY='ipod.listen.session';
let db=null,uid=null,role=null,code=null,room=null,unsubs=[],timer=null,lastSig='',lastNp=null,lastNpAt=0;
let hostName='',listeners=0,state=null,offset=0,missing=null,lastApplied=null;
const now=()=>firebase.firestore.FieldValue.serverTimestamp();
const myName=()=>{try{return (JSON.parse(localStorage.getItem('ipod.friends.profile')||'null')?.displayName||'').slice(0,32)}catch(e){return ''}};

/* ---- Firebase ---- */
function loadScript(f){return new Promise((ok,no)=>{const s=document.createElement('script');s.src=`https://www.gstatic.com/firebasejs/${SDK}/${f}`;s.onload=ok;s.onerror=()=>{s.remove();no(Error('Could not load '+f))};document.head.appendChild(s)})}
let connecting=null;
async function connect(){
  if(db)return;if(connecting)return connecting;
  connecting=(async()=>{
    if(!(window.firebase&&firebase.initializeApp))await loadScript('firebase-app-compat.js');
    if(!firebase.auth)await loadScript('firebase-auth-compat.js');
    if(!firebase.firestore)await loadScript('firebase-firestore-compat.js');
    let app=firebase.apps.find(a=>a.name==='ipod-listen'),fresh=!app;
    if(!app)app=firebase.initializeApp(CONFIG,'ipod-listen');
    const store=app.firestore(),auth=app.auth();
    if(fresh){const webkit=/AppleWebKit/.test(navigator.userAgent)&&!/Chrome|Chromium|Android/.test(navigator.userAgent);
      try{store.settings(webkit?{experimentalForceLongPolling:true,merge:true}:{experimentalAutoDetectLongPolling:true,merge:true})}catch(e){}}
    const user=await new Promise(r=>{const u=auth.onAuthStateChanged(x=>{u();r(x)},()=>r(null))});
    uid=(user||(await auth.signInAnonymously()).user).uid;db=store;
  })();
  try{await connecting}finally{connecting=null}
}
const clearSubs=()=>{unsubs.forEach(u=>{try{u()}catch(e){}});unsubs=[]};
function remember(){try{role?localStorage.setItem(KEY,JSON.stringify({role,code})):localStorage.removeItem(KEY)}catch(e){}}

/* ---- matching a host's song to your own library ---- */
const norm=x=>String(x||'').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g,'')
  .replace(/\s*[\(\[][^)\]]*(remaster|live|version|edit|mono|stereo|feat|ft\.)[^)\]]*[\)\]]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
function findLocal(np){
  const live=B.songs().filter(s=>!s.deleted),t=norm(np.t),a=norm(np.a);
  return live.find(s=>norm(s.title)===t&&norm(s.artist)===a)
    ||live.find(s=>norm(s.title)===t&&(norm(s.artist).includes(a)||a.includes(norm(s.artist)))&&a)
    ||live.find(s=>norm(s.title)===t&&np.al&&norm(s.album)===norm(np.al));
}

/* ---- host ---- */
async function host(){
  await connect();
  for(let i=0;i<5;i++){
    const c=Array.from(crypto.getRandomValues(new Uint32Array(6)),n=>ABC[n%ABC.length]).join('');
    const ref=db.collection('rooms').doc(c);
    try{await ref.set({host:uid,hostName:myName()||'Host',createdAt:now(),state:{},updatedAt:now()});code=c;room=ref;break}
    catch(e){if(e.code==='permission-denied')throw Error('Listen Together needs the updated Firestore rules. Deploy them with: firebase deploy --only firestore:rules');if(i===4)throw e}
  }
  role='host';hostName=myName()||'You';listeners=0;lastSig='';remember();
  unsubs.push(room.collection('guests').onSnapshot(q=>{const n=q.size!=null?q.size:q.docs?.length||0;if(n>listeners)B.toast('Someone joined · '+n+' listening');listeners=n;B.refresh()},()=>{}));
  timer=setInterval(hostTick,300);hostTick(true);
}
function hostTick(force){
  if(role!=='host'||!room)return;
  const s=B.cur(),np=s?{t:String(s.title||'').slice(0,140),a:String(s.artist||'').slice(0,140),al:String(s.album||'').slice(0,140),
    dur:Math.round((B.duration()||0)*10)/10,pos:Math.round(B.time()*100)/100,playing:!B.paused(),art:/^https:\/\//.test(B.art(s)||'')?B.art(s).slice(0,500):''}:null;
  const sig=JSON.stringify(np&&[np.t,np.a,np.playing,np.dur,Math.floor(np.pos/15)]);
  const jumped=np&&lastNp&&np.t===lastNp.t&&Math.abs(np.pos-(lastNp.pos+(Date.now()-lastNpAt)/1000*(lastNp.playing?1:0)))>(np.playing?1.2:.2);
  if(!force&&sig===lastSig&&!jumped)return;
  lastSig=sig;lastNp=np;lastNpAt=Date.now();
  room.update({state:np?{np}:{},updatedAt:now()}).catch(e=>{if(e.code==='not-found'||e.code==='permission-denied')end(true)});
}

/* ---- guest ---- */
async function join(raw){
  const c=String(raw||'').toUpperCase().replace(/[^A-Z0-9]/g,'');
  if(!CODE_RE.test(c))throw Error('Codes are 6 letters and numbers, like K7MQ4D.');
  await connect();
  const ref=db.collection('rooms').doc(c);let d;
  try{d=await ref.get()}catch(e){throw Error(e.code==='permission-denied'?'Listen Together needs the updated Firestore rules (firebase deploy --only firestore:rules).':'Couldn’t reach the server. Try again.')}
  if(!d.exists)throw Error('No one is hosting with that code. Check it and try again.');
  if(d.data().host===uid)throw Error('That’s your own session.');
  const me=ref.collection('guests').doc(uid),t0=Date.now();
  await me.set({name:myName()||'Guest',joinedAt:now()});
  try{const back=await me.get(),t1=Date.now(),ts=back.data()?.joinedAt;if(ts&&ts.toMillis)offset=ts.toMillis()-(t0+t1)/2}catch(e){}
  role='guest';code=c;room=ref;hostName=d.data().hostName||'Host';missing=null;lastApplied=null;remember();
  unsubs.push(ref.onSnapshot(x=>{
    if(!x.exists){B.toast(hostName+' ended Listen Together');return end(true)}
    const v=x.data();state={np:v.state?.np||null,at:v.updatedAt?.toMillis?v.updatedAt.toMillis():Date.now()+offset};follow();
  },()=>{}));
  timer=setInterval(follow,2500);
}
function expected(){const np=state&&state.np;if(!np)return 0;return np.pos+(np.playing?Math.max(0,(Date.now()+offset-state.at)/1000):0)}
function follow(){
  if(role!=='guest'||!state)return;
  const np=state.np;
  if(!np){missing=null;return B.refresh()}
  const song=findLocal(np);
  if(!song){
    if(missing!==np.t+'|'+np.a){missing=np.t+'|'+np.a;if(!B.paused())B.pause();B.toast('Not in your library: '+np.t);B.refresh()}
    return;
  }
  missing=null;
  const key=np.t+'|'+np.a,cur=B.cur();
  if(!cur||cur.id!==song.id||lastApplied!==key){
    lastApplied=key;B.playSong(song);
    // seek once the new song has loaded, then match play/pause
    let tries=0;const settle=setInterval(()=>{if(++tries>40||(B.cur()?.id===song.id&&B.duration())){clearInterval(settle);sync(song,true)}},150);
    return B.refresh();
  }
  sync(song,false);
}
function sync(song,force){
  const np=state&&state.np;if(!np||B.cur()?.id!==song.id)return;
  const want=Math.min(expected(),Math.max(0,(B.duration()||1e9)-.5));
  if(np.playing&&B.paused())B.play();
  if(!np.playing&&!B.paused())B.pause();
  if(force||Math.abs(B.time()-want)>(np.playing?1.2:.25))B.seek(want);   // paused: line up exactly
}

/* ---- ending ---- */
async function end(remote){
  const r=room,was=role;clearInterval(timer);timer=null;clearSubs();
  role=null;room=null;state=null;missing=null;remember();B.refresh();
  if(!remote&&r)try{was==='host'?await r.delete():await r.collection('guests').doc(uid).delete()}catch(e){}
}
async function resume(){
  let s=null;try{s=JSON.parse(localStorage.getItem(KEY)||'null')}catch(e){}
  if(!s)return;
  try{
    await connect();const ref=db.collection('rooms').doc(s.code),d=await ref.get();
    if(!d.exists){localStorage.removeItem(KEY);return}
    if(s.role==='host'&&d.data().host===uid){room=ref;code=s.code;role='host';hostName='You';lastSig='';
      unsubs.push(ref.collection('guests').onSnapshot(q=>{listeners=q.size!=null?q.size:q.docs?.length||0;B.refresh()},()=>{}));
      timer=setInterval(hostTick,300);hostTick(true)}
    else if(s.role==='guest')await join(s.code);
  }catch(e){}
}

/* ---- iPod menu: Music ▸ Listen Together ---- */
function menu(){
  return B.list('Listen Together',()=>{
    if(role==='host')return [
      {label:'Your Code',val:code},
      {label:'Listening',val:String(listeners)},
      {label:'Now Sharing',val:B.cur()?.title||'Nothing yet'},
      {label:'End Session',action:async()=>{await end(false);B.toast('Listen Together ended')}},
    ];
    if(role==='guest'){const np=state&&state.np;return [
      {label:'Listening With',val:hostName},
      {label:np?(missing?'Not in Your Library':'Now Playing'):'Waiting for '+hostName,val:np?np.t:'',action:()=>{if(np&&!missing)B.openNow()}},
      ...(missing?[{label:'You’ll rejoin on the next song you have',action:()=>{}}]:[]),
      {label:'Leave',action:async()=>{await end(false);B.toast('You left Listen Together')}},
    ]}
    return [
      {label:'Host a Session',icon:'people',chev:1,action:async()=>{
        B.push(B.loadingView('Starting…'));
        try{await host();B.replaceTop(B.msgView('Code: '+code,'Friends open Music ▸ Listen Together ▸ Join and type '+code+'. Everyone hears what you play, from their own library.'))}
        catch(e){B.replaceTop(B.msgView('Couldn’t Start',e.message||'Please try again.'))}}},
      {label:'Join with Code',icon:'people',chev:1,action:()=>B.push(B.inputView('Join Listen Together','Code from your friend',async val=>{
        B.replaceTop(B.loadingView('Joining…'));
        try{await join(val);B.replaceTop(B.msgView('Listening with '+hostName,'Songs you have play in sync with '+hostName+'. If you don’t have one, you’ll see it and rejoin on the next.'))}
        catch(e){B.replaceTop(B.msgView('Couldn’t Join',e.message||'Please try again.'))}}))},
      {label:'How It Works',chev:1,action:B.go(B.msgView('Listen Together','One person hosts and shares a 6-character code. Everyone who joins hears the same song at the same moment, each from their own library. Nothing is downloaded.'))},
    ];
  });
}
window.ipodListen=Object.freeze({open:()=>B.push(menu()),get role(){return role},get code(){return code},get listeners(){return listeners},
  get missing(){return missing},end:()=>end(false),_host:host,_join:join});
resume();
})();
