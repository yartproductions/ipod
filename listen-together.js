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
  unsubs.push(room.collection('guests').onSnapshot(q=>{const n=q.size!=null?q.size:q.docs?.length||0;if(n>listeners){B.toast('Someone joined · '+n+' listening');window.ipodNotify?.({id:'lt:'+code+':'+n+':'+Date.now(),kind:'listen',title:'Listen Together',body:'Someone joined · '+n+' listening'})}listeners=n;B.refresh()},()=>{}));
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
    if(missing!==np.t+'|'+np.a){missing=np.t+'|'+np.a;if(!B.paused())B.pause();B.toast('Not in your library: '+np.t);noteMissed(np);B.refresh()}
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

/* ---- songs you didn't have, kept so you can add them later ---- */
const MKEY='ipod.listen.missed';let missedThisSession=0;
const readMissed=()=>{try{const x=JSON.parse(localStorage.getItem(MKEY)||'[]');return Array.isArray(x)?x:[]}catch(e){return []}};
function noteMissed(np){
  const k=norm(np.t)+'|'+norm(np.a),list=readMissed().filter(x=>norm(x.t)+'|'+norm(x.a)!==k);
  list.unshift({t:np.t,a:np.a,al:np.al||'',host:hostName,at:Date.now()});missedThisSession++;
  try{localStorage.setItem(MKEY,JSON.stringify(list.slice(0,200)))}catch(e){}
}
function missedMenu(){
  return B.list('Songs You Missed',()=>{const m=readMissed().filter(x=>!findLocal({t:x.t,a:x.a,al:x.al}));
    if(!m.length)return [{label:'Nothing missing',action:()=>{}}];
    return [...m.map(x=>({label:x.t,val:x.a,action:B.go(B.msgView(x.t,[x.a,x.al].filter(Boolean).join(' — ')+'\n\nPlayed by '+x.host+' on '+new Date(x.at).toLocaleDateString()+'. Add it to your library to hear it next time.'))})),
      {label:'Clear List',action:()=>{try{localStorage.removeItem(MKEY)}catch(e){}B.render()}}];
  });
}

/* ---- the session screen: cover, live progress bar and the current lyric line ---- */
const lyricCache=new Map();
function lyricsFor(np,song){
  const k=norm(np.t)+'|'+norm(np.a);if(lyricCache.has(k))return lyricCache.get(k);
  lyricCache.set(k,null);
  Promise.resolve(B.lyrics(song||{title:np.t,artist:np.a,album:np.al||'',duration:np.dur})).then(d=>{lyricCache.set(k,d||{lines:[],text:''})}).catch(()=>lyricCache.set(k,{lines:[],text:''}));
  return null;
}
const fmt=t=>{t=Math.max(0,t|0);return (t/60|0)+':'+String(t%60).padStart(2,'0')};
function shown(){
  if(role==='host'){const s=B.cur();return s?{np:{t:s.title,a:s.artist,al:s.album,dur:B.duration()||0},pos:B.time(),song:s,art:B.art(s)}:null}
  const np=state&&state.np;if(!np)return null;
  const song=findLocal(np);
  return {np,pos:Math.min(expected(),np.dur||1e9),song,art:song?B.art(song):(np.art||B.genArt(np.al||np.t,np.a))};
}
function sessionView(){
  const v={type:'custom',title:'Listen Together',
    render(body){
      const x=shown(),who=role==='host'?`Code ${code} · ${listeners} listening`:`Listening with ${B.esc(hostName)}`;
      if(!x){body.innerHTML=`<div class="ltg"><div class="ltg-top"><div class="ltg-art"></div><div class="ltg-meta"><b>${role==='host'?'Play something to share it':'Waiting for '+B.esc(hostName)+'…'}</b><div class="ltg-who">${who}</div></div></div><div class="ltg-note">Center for options · MENU to go back</div></div>`;v.start();return}
      body.innerHTML=`<div class="ltg"><div class="ltg-top"><div class="ltg-art" style="background-image:url(&quot;${B.esc(x.art||'')}&quot;)"></div>
        <div class="ltg-meta"><b>${B.esc(x.np.t)}</b><span>${B.esc([x.np.a,x.np.al].filter(Boolean).join(' — '))}</span><div class="ltg-who">${who}</div>
        ${role==='guest'&&!x.song?'<div class="ltg-miss">Not in your library</div>':''}</div></div>
        <div class="ltg-bar"><span id="lt-c">0:00</span><div class="t"><i id="lt-i"></i></div><span id="lt-d">0:00</span></div>
        <div class="ltg-lyric" id="lt-l"></div><div class="ltg-note">Center for options · MENU to go back</div></div>`;
      v.update();v.start();
    },
    update(){
      const x=shown();if(!x)return;
      const c=document.getElementById('lt-c'),i=document.getElementById('lt-i'),d=document.getElementById('lt-d'),l=document.getElementById('lt-l');if(!i)return;
      const dur=x.np.dur||0,pos=Math.min(x.pos,dur||x.pos);
      c.textContent=fmt(pos);d.textContent=dur?'-'+fmt(dur-pos):'';i.style.width=dur?(pos/dur*100).toFixed(2)+'%':'0';
      const L=lyricsFor(x.np,x.song);let line='';
      if(L&&L.lines&&L.lines.length){for(const y of L.lines){if(y.at<=pos+.15)line=y.text;else break}}
      if(l.textContent!==line)l.textContent=line;
    },
    input(btn){if(btn==='select')B.push(menu())},
    key:null};
  let lastKey='';
  // refresh while this screen is showing; stops when you leave it and restarts when you come back
  v.start=()=>{if(v._t)return;v._t=setInterval(()=>{
    if(B.top()!==v||!role){clearInterval(v._t);v._t=null;return}
    const x=shown(),k=x?x.np.t+'|'+x.np.a+'|'+!!x.song+'|'+listeners:'none';
    if(k!==lastKey){lastKey=k;B.render()}else v.update()},250)};
  return v;
}

/* ---- ending ---- */
async function end(remote){
  const r=room,was=role;clearInterval(timer);timer=null;clearSubs();
  role=null;room=null;state=null;missing=null;remember();
  if(was==='guest'&&missedThisSession)B.toast(missedThisSession+(missedThisSession===1?' song':' songs')+' to add · Listen Together ▸ Songs You Missed');
  else if(!remote)B.toast(was==='host'?'Listen Together ended':'You left Listen Together');
  missedThisSession=0;
  if(B.top()?.type==='custom'&&B.top().title==='Listen Together')B.pop();
  B.refresh();
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
      {label:'End Session',action:()=>end(false)},
    ];
    if(role==='guest'){const np=state&&state.np;return [
      {label:'Listening With',val:hostName},
      {label:np?(missing?'Not in Your Library':'Now Playing'):'Waiting for '+hostName,val:np?np.t:'',action:()=>{if(np&&!missing)B.openNow()}},
      ...(missing?[{label:'You’ll rejoin on the next song you have',action:()=>{}}]:[]),
      {label:'Leave',action:()=>end(false)},
    ]}
    return [
      {label:'Host a Session',icon:'people',chev:1,action:async()=>{
        B.push(B.loadingView('Starting…'));
        try{await host();B.replaceTop(sessionView())}
        catch(e){B.replaceTop(B.msgView('Couldn’t Start',e.message||'Please try again.'))}}},
      {label:'Join with Code',icon:'people',chev:1,action:()=>B.push(B.inputView('Join Listen Together','Code from your friend',async val=>{
        B.replaceTop(B.loadingView('Joining…'));
        try{await join(val);B.replaceTop(sessionView())}
        catch(e){B.replaceTop(B.msgView('Couldn’t Join',e.message||'Please try again.'))}}))},
      {label:'Songs You Missed',icon:'library',chev:1,val:String(readMissed().filter(x=>!findLocal({t:x.t,a:x.a,al:x.al})).length||''),action:()=>B.push(missedMenu())},
      {label:'How It Works',chev:1,action:B.go(B.msgView('Listen Together','One person hosts and shares a 6-character code. Everyone who joins hears the same song at the same moment, each from their own library. Nothing is downloaded.'))},
    ];
  });
}
window.ipodListen=Object.freeze({open:()=>B.push(role?sessionView():menu()),missed:missedMenu,get role(){return role},get code(){return code},get listeners(){return listeners},
  get missing(){return missing},end:()=>end(false),_host:host,_join:join});
resume();
})();
