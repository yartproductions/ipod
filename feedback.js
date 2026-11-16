/* iPod ▸ Feedback & Ideas — report bugs (private, with device details) and suggest ideas that every
   listener can see and upvote. Stored in the Friends Firebase project: feedback/{id} (+ votes/{uid}). */
(function(){
'use strict';
const B=window.ipodFeedbackBridge;
if(!B){console.error('iPod Feedback: bridge unavailable');return}
const CONFIG={apiKey:"AIzaSyDSMe2R6QTVd3htWfP7-ScKMZyWd5dePNU",authDomain:"ipod-friends.firebaseapp.com",projectId:"ipod-friends",
  storageBucket:"ipod-friends.firebasestorage.app",messagingSenderId:"222255543131",appId:"1:222255543131:web:135687a1679707d515e07e"};
const SDK='13.3.0';
let db=null,uid=null;
const now=()=>firebase.firestore.FieldValue.serverTimestamp();
const myName=()=>{try{return (JSON.parse(localStorage.getItem('ipod.friends.profile')||'null')?.username||'').slice(0,32)}catch(e){return ''}};

// the last few errors, so a bug report says what actually went wrong
const recentErrors=[];
addEventListener('error',e=>{recentErrors.push(String(e.message||e.error||'error').slice(0,160));if(recentErrors.length>5)recentErrors.shift()});
addEventListener('unhandledrejection',e=>{recentErrors.push(('promise: '+String(e.reason&&e.reason.message||e.reason)).slice(0,160));if(recentErrors.length>5)recentErrors.shift()});

function loadScript(f){return new Promise((ok,no)=>{const s=document.createElement('script');s.src=`https://www.gstatic.com/firebasejs/${SDK}/${f}`;s.onload=ok;s.onerror=()=>{s.remove();no(Error('Could not load '+f))};document.head.appendChild(s)})}
let connecting=null;
async function connect(){
  if(db)return;if(connecting)return connecting;
  connecting=(async()=>{
    if(!(window.firebase&&firebase.initializeApp))await loadScript('firebase-app-compat.js');
    if(!firebase.auth)await loadScript('firebase-auth-compat.js');
    if(!firebase.firestore)await loadScript('firebase-firestore-compat.js');
    let app=firebase.apps.find(a=>a.name==='ipod-feedback'),fresh=!app;
    if(!app)app=firebase.initializeApp(CONFIG,'ipod-feedback');
    const store=app.firestore(),auth=app.auth();
    if(fresh){const webkit=/AppleWebKit/.test(navigator.userAgent)&&!/Chrome|Chromium|Android/.test(navigator.userAgent);
      try{store.settings(webkit?{experimentalForceLongPolling:true,merge:true}:{experimentalAutoDetectLongPolling:true,merge:true})}catch(e){}}
    const user=await new Promise(r=>{const u=auth.onAuthStateChanged(x=>{u();r(x)},()=>r(null))});
    uid=(user||(await auth.signInAnonymously()).user).uid;db=store;
  })();
  try{await connecting}finally{connecting=null}
}
const friendly=e=>e&&e.code==='permission-denied'?'Feedback needs the updated Firestore rules (firebase deploy --only firestore:rules).':(e&&e.message)||'Couldn’t reach the server. Try again.';

function diagnostics(){
  let settings={};try{const s=JSON.parse(localStorage.getItem('ipod.settings')||'{}');settings={theme:s.theme,nowStyle:s.nowStyle,menuStyle:s.menuStyle,landscape:s.landscape}}catch(e){}
  return JSON.stringify({
    app:window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.ipodHaptics?'iPhone app':(matchMedia('(display-mode: standalone)').matches?'Home Screen app':'browser'),
    ua:navigator.userAgent.slice(0,180),screen:innerWidth+'x'+innerHeight+'@'+devicePixelRatio,
    screenName:B.screenName(),songs:B.songCount(),settings,errors:recentErrors.slice(),at:new Date().toISOString(),
  }).slice(0,2000);
}
async function send(kind,text){
  text=String(text||'').trim();
  if(text.length<4)throw Error('Write a little more so it’s clear what you mean.');
  await connect();
  await db.collection('feedback').add({kind,text:text.slice(0,1000),diag:kind==='bug'?diagnostics():'',uid,name:myName()||'',createdAt:now()});
  window.ipodAchievements?.event(kind==='bug'?'bugReport':'idea');
}

/* ---- the idea board ---- */
let ideas=[];
async function loadIdeas(){
  await connect();
  const q=await db.collection('feedback').where('kind','==','idea').limit(100).get();
  const list=(q.docs||[]).map(d=>({id:d.id,...d.data()}));
  await Promise.all(list.map(async x=>{try{const v=await db.collection('feedback').doc(x.id).collection('votes').get();
    x.votes=v.size!=null?v.size:(v.docs||[]).length;x.mine=(v.docs||[]).some(d=>d.id===uid)}catch(e){x.votes=0}}));
  ideas=list.sort((a,b)=>b.votes-a.votes||(b.createdAt?.toMillis?.()||0)-(a.createdAt?.toMillis?.()||0));
  return ideas;
}
async function toggleVote(x){
  await connect();const ref=db.collection('feedback').doc(x.id).collection('votes').doc(uid);
  if(x.mine){await ref.delete();x.mine=false;x.votes--}else{await ref.set({at:now()});x.mine=true;x.votes++}
}
async function myReports(){
  await connect();
  const q=await db.collection('feedback').where('uid','==',uid).limit(50).get();
  return (q.docs||[]).map(d=>({id:d.id,...d.data()})).sort((a,b)=>(b.createdAt?.toMillis?.()||0)-(a.createdAt?.toMillis?.()||0));
}

/* ---- iPod screens ---- */
const short=t=>t.length>42?t.slice(0,40)+'…':t;
function compose(kind){
  const bug=kind==='bug';
  return B.inputView(bug?'Report a Bug':'Suggest an Idea',bug?'What went wrong? What were you doing?':'Your idea for the iPod…',async text=>{
    B.replaceTop(B.loadingView('Sending…'));
    try{await send(kind,text);B.replaceTop(B.msgView(bug?'Thanks for the Report':'Idea Posted',
      bug?'It went straight to the developer, with your device details and any recent errors so it can be reproduced.'
         :'It’s on the Idea Board now. Other listeners can upvote it, and the most wanted ideas rise to the top.'))}
    catch(e){B.replaceTop(B.msgView('Couldn’t Send',friendly(e)))}
  });
}
function ideaView(x){
  return B.list('Idea',()=>[
    {label:short(x.text),action:()=>B.push(B.msgView('Idea',x.text+(x.name?'\n\n— @'+x.name:'')))},
    {label:x.mine?'Remove My Vote':'Upvote',val:'▲ '+x.votes,action:async()=>{try{await toggleVote(x);B.haptic('success');B.render()}catch(e){B.toast(friendly(e))}}},
    {label:'Posted',val:x.createdAt?.toDate?x.createdAt.toDate().toLocaleDateString():''},
  ]);
}
function boardView(){
  const v=B.list('Idea Board',()=>ideas.length?ideas.map(x=>({label:short(x.text),val:(x.mine?'▲ ':'△ ')+x.votes,chev:1,action:()=>B.push(ideaView(x))}))
    :[{label:v.loaded?'No ideas yet: be the first':'Loading…',action:()=>{if(v.loaded)B.push(compose('idea'))}}]);
  loadIdeas().then(()=>{v.loaded=true;B.render()}).catch(e=>{v.loaded=true;B.toast(friendly(e));B.render()});
  return v;
}
function mineView(){
  let rows=null;
  const v=B.list('My Reports',()=>rows?(rows.length?rows.map(x=>({label:(x.kind==='bug'?'🐞 ':'💡 ')+short(x.text),val:x.createdAt?.toDate?x.createdAt.toDate().toLocaleDateString(undefined,{month:'short',day:'numeric'}):'',
      action:()=>B.push(B.msgView(x.kind==='bug'?'Bug Report':'Idea',x.text))})):[{label:'Nothing sent yet',action:()=>{}}]):[{label:'Loading…',action:()=>{}}]);
  myReports().then(r=>{rows=r;B.render()}).catch(e=>{rows=[];B.toast(friendly(e));B.render()});
  return v;
}
function menu(){
  return B.list('Feedback & Ideas',[
    {label:'Report a Bug',icon:'info',chev:1,action:()=>B.push(compose('bug'))},
    {label:'Suggest an Idea',icon:'sparkle',chev:1,action:()=>B.push(compose('idea'))},
    {label:'Idea Board',icon:'people',chev:1,action:()=>B.push(boardView())},
    {label:'My Reports',icon:'library',chev:1,action:()=>B.push(mineView())},
  ]);
}
window.ipodFeedback=Object.freeze({open:()=>B.push(menu()),_send:send,_diag:diagnostics});
})();
