/* iPod Friends — optional anonymous social layer. The music player does not depend on Firebase. */
(function(){
'use strict';
const bridge=window.ipodFriendsBridge;
if(!bridge){console.error('iPod Friends: player bridge unavailable');return}
const {audio,cur,list,go,push,replaceTop,top,msgView,loadingView,inputView}=bridge;
const CONFIG={
  apiKey:"AIzaSyDSMe2R6QTVd3htWfP7-ScKMZyWd5dePNU",
  authDomain:"ipod-friends.firebaseapp.com",
  projectId:"ipod-friends",
  storageBucket:"ipod-friends.firebasestorage.app",
  messagingSenderId:"222255543131",
  appId:"1:222255543131:web:135687a1679707d515e07e"
};
const SDK="13.3.0";
let api=null,initTask=null,account=null,profile=null;
const nameOK=s=>/^[a-z][a-z0-9_]{2,19}$/.test(s);
const normalize=s=>String(s||'').trim().replace(/^@/,'').toLowerCase();
const serverTime=()=>firebase.firestore.FieldValue.serverTimestamp();
const maybeError=e=>e&&e.code==='permission-denied'
  ?'Firestore permission denied. Deploy the reviewed Friends rules first.'
  :e&&(e.code==='unreachable'||isTransient(e))?'Friends couldn’t reach the server. Check your connection and try again.'
  :e&&e.message||'Please try again.';
// Reliability layer. Firebase is slow to (re)connect after a cold start, after iOS
// suspends the page, or when WebKit stalls the streaming channel. Rather than
// failing on the first slow request, every call gets a bounded wait, the Firestore
// channel is reset, and the call is retried. Errors only surface after all retries.
const TRANSIENT=new Set(['unavailable','deadline-exceeded','aborted','internal','resource-exhausted',
  'auth/network-request-failed','auth/timeout','auth/internal-error','timeout']);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function limited(task,label,ms){
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{const e=Error(label+' timed out.');e.code='timeout';reject(e)},ms);
    Promise.resolve(task).then(v=>{clearTimeout(timer);resolve(v)},e=>{clearTimeout(timer);reject(e)});
  });
}
const isTransient=e=>!e||TRANSIENT.has(e.code)||/network|timed out|offline|failed to fetch|load failed/i.test(e.message||'');
async function resetNetwork(){
  if(!dbRef)return;
  try{await limited(dbRef.disableNetwork(),'disable',3000)}catch(e){}
  try{await limited(dbRef.enableNetwork(),'enable',3000)}catch(e){}
}
// Run fn() with retries. fn must be safe to repeat (all Friends writes are).
async function withRetry(label,fn,waits=[9000,12000,18000,25000]){
  let last;
  for(let i=0;i<waits.length;i++){
    if(i&&!navigator.onLine)await waitOnline(8000);
    try{return await limited(fn(),label,waits[i])}
    catch(e){
      last=e;
      if(!isTransient(e))throw e;
      console.warn('Friends:',label,'attempt',i+1,'failed:',e.code||e.message);
      await resetNetwork();
      await sleep(400*(i+1));
    }
  }
  const e=Error('Friends couldn’t reach the server. Check your connection and try again.');e.code='unreachable';e.cause=last;throw e;
}
function waitOnline(ms){
  if(navigator.onLine)return Promise.resolve();
  return new Promise(r=>{const t=setTimeout(done,ms);function done(){clearTimeout(t);window.removeEventListener('online',done);r()}window.addEventListener('online',done)});
}
function loadSDKOnce(file){
  return new Promise((resolve,reject)=>{
    const src='https://www.gstatic.com/firebasejs/'+SDK+'/'+file;
    document.querySelectorAll('script[data-fb="'+file+'"]').forEach(x=>x.remove());
    const script=document.createElement('script');
    script.dataset.fb=file;script.src=src;
    script.onload=()=>resolve();
    script.onerror=()=>{script.remove();reject(Object.assign(Error('Could not load '+file),{code:'unavailable'}))};
    document.head.appendChild(script);
  });
}
const sdkReady={'firebase-app-compat.js':()=>window.firebase&&firebase.initializeApp,
  'firebase-auth-compat.js':()=>window.firebase&&firebase.auth,
  'firebase-firestore-compat.js':()=>window.firebase&&firebase.firestore};
async function loadSDK(file){
  if(sdkReady[file]())return;
  await withRetry('Loading '+file,()=>loadSDKOnce(file),[12000,15000,20000]);
}
// Profile is cached so Friends opens instantly and refreshes in the background.
const PKEY='ipod.friends.profile';
function cachedProfile(uid){try{const c=JSON.parse(localStorage.getItem(PKEY)||'null');return c&&c.uid===uid?c:null}catch(e){return null}}
function cacheProfile(p){try{p?localStorage.setItem(PKEY,JSON.stringify({...p,createdAt:null,updatedAt:null})):localStorage.removeItem(PKEY)}catch(e){}}
let dbRef=null,profileLoaded=false;
async function refreshProfile(){
  const doc=await withRetry('Loading Friends profile',()=>dbRef.collection('profiles').doc(account.uid).get());
  profile=doc.exists?doc.data():null;profileLoaded=true;cacheProfile(profile);
  return profile;
}
async function connect(){
  if(api)return api;
  if(initTask)return initTask;
  initTask=(async()=>{
    await loadSDK('firebase-app-compat.js');
    await loadSDK('firebase-auth-compat.js');
    await loadSDK('firebase-firestore-compat.js');
    if(!window.firebase)throw Error('Firebase SDK did not initialize.');
    let app=firebase.apps.find(x=>x.name==='ipod-friends'),fresh=!app;
    if(!app)app=firebase.initializeApp(CONFIG,'ipod-friends');
    const auth=app.auth(),db=app.firestore();
    if(fresh){
      // WebKit (iOS app + Safari) often stalls Firestore's streaming channel; long polling is steady.
      const webkit=/AppleWebKit/.test(navigator.userAgent)&&!/Chrome|Chromium|Android/.test(navigator.userAgent);
      try{db.settings(webkit?{experimentalForceLongPolling:true,merge:true}:{experimentalAutoDetectLongPolling:true,merge:true})}catch(e){}
    }
    dbRef=db;
    // Restoring a saved session is local (IndexedDB); just wait for it.
    const existing=await limited(new Promise(resolve=>{
      const unsub=auth.onAuthStateChanged(user=>{try{unsub()}catch(e){}resolve(user)},()=>resolve(null));
    }),'Restoring session',10000).catch(()=>auth.currentUser);
    account=existing||(await withRetry('Creating anonymous account',()=>auth.signInAnonymously())).user;
    const cached=cachedProfile(account.uid);
    if(cached&&!profileLoaded){profile=cached;refreshProfile().catch(e=>console.warn('Friends: profile refresh',e.message))}
    else if(!profileLoaded)await refreshProfile();
    api={auth,db};
    return api;
  })();
  try{return await initTask}finally{initTask=null}
}
// Keep the connection warm: reconnect when the app comes back, and pre-connect
// in the background for people who already use Friends.
function wake(){if(dbRef&&navigator.onLine)dbRef.enableNetwork().catch(()=>{})}
const usedBefore=()=>{try{return !!localStorage.getItem(PKEY)||localStorage.getItem('ipod.friends.used')==='1'}catch(e){return false}};
if(typeof document!=='undefined'){
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')wake()});
  window.addEventListener('online',()=>{wake();if(!api&&usedBefore())connect().catch(()=>{})});
  if(usedBefore()&&navigator.onLine)setTimeout(()=>connect().catch(e=>console.warn('Friends warm-up:',e.message)),2500);
}
/* ---------- profile pictures: a small square JPEG kept in the profile doc ---------- */
const PHOTO_PX=128,PHOTO_MAX=40000;
const AV_COLORS=['#2b7fde','#e0573e','#2fa36b','#8a5cd6','#d9922b','#d64a8b','#3a9bb0','#6b7686'];
function initialsAvatar(p){
  const name=String(p&&(p.displayName||p.username)||'?').trim();
  const ch=(name.match(/[A-Za-z0-9]/)||['?'])[0].toUpperCase();
  let h=0;for(const c of String(p&&p.username||name))h=(h*31+c.charCodeAt(0))>>>0;
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" fill="${AV_COLORS[h%AV_COLORS.length]}"/><text x="20" y="27" font-family="-apple-system,Helvetica,Arial,sans-serif" font-size="19" font-weight="700" fill="#fff" text-anchor="middle">${ch}</text></svg>`;
  return 'data:image/svg+xml,'+encodeURIComponent(svg);
}
const avatarOf=p=>p&&typeof p.photo==='string'&&p.photo.startsWith('data:image/jpeg;base64,')?p.photo:initialsAvatar(p);
async function shrinkPhoto(file){
  if(!file||!/^image\//.test(file.type||'image/'))throw Error('Choose a photo.');
  let src;
  try{src=await createImageBitmap(file,{imageOrientation:'from-image'})}
  catch(e){
    src=await new Promise((res,rej)=>{const u=URL.createObjectURL(file),im=new Image();
      im.onload=()=>{URL.revokeObjectURL(u);res(im)};im.onerror=()=>{URL.revokeObjectURL(u);rej(Error('That photo couldn’t be read. Try a JPEG or PNG.'))};im.src=u});
  }
  const w=src.width,h=src.height,side=Math.min(w,h);
  if(!side)throw Error('That photo couldn’t be read.');
  const c=document.createElement('canvas');c.width=c.height=PHOTO_PX;
  const g=c.getContext('2d');g.imageSmoothingQuality='high';
  g.fillStyle='#fff';g.fillRect(0,0,PHOTO_PX,PHOTO_PX);
  g.drawImage(src,(w-side)/2,(h-side)/2,side,side,0,0,PHOTO_PX,PHOTO_PX);
  if(src.close)src.close();
  for(const q of [.85,.75,.62,.5]){const d=c.toDataURL('image/jpeg',q);if(d.length<=PHOTO_MAX)return d}
  throw Error('That photo is too detailed. Try another one.');
}
function pickPhoto(){
  // Must run synchronously inside the wheel press so iOS allows the picker.
  const input=document.createElement('input');
  input.type='file';input.accept='image/*';input.style.display='none';
  document.body.appendChild(input);
  input.addEventListener('change',()=>{
    const file=input.files&&input.files[0];input.remove();
    if(!file)return;
    runView('Saving Picture…',async()=>{
      const photo=await shrinkPhoto(file);
      await api.db.collection('profiles').doc(account.uid).update({photo,updatedAt:serverTime()});
      profile.photo=photo;cacheProfile(profile);
      return msgView('Picture Saved','Friends will see it next to @'+profile.username+'.');
    });
  },{once:true});
  input.click();
  setTimeout(()=>{if(document.body.contains(input)&&!input.files.length)input.remove()},120000);
}
function photoMenu(){
  return list('Profile Picture',()=>{const has=!!(profile.photo);return [
    {label:has?'Your Picture':'No Picture Yet',val:has?'Set':'Initials',thumb:avatarOf(profile),avatar:1},
    {label:has?'Choose New Picture':'Choose Picture',chev:1,action:pickPhoto},
    ...(has?[{label:'Remove Picture',action:()=>runView('Removing Picture…',async()=>{
      await api.db.collection('profiles').doc(account.uid).update({photo:firebase.firestore.FieldValue.delete(),updatedAt:serverTime()});
      delete profile.photo;cacheProfile(profile);return msgView('Picture Removed','Your initials are shown instead.');
    })}]:[]),
    {label:'Who Sees It',chev:1,action:()=>push(msgView('Profile Picture','Your picture is shown with your username, so anyone who looks you up can see it. It’s shrunk to a small square on this device before uploading.'))}
  ]});
}
function friendsMenu(){
  if(!profile)return list('Friends',[
    {label:'Create My Profile',chev:1,action:()=>push(inputView('Choose Username','3–20 letters, numbers, _',createProfile))},
    {label:'About Identity',chev:1,action:()=>push(msgView('No Recovery Yet','Your Friends identity belongs to this browser. If you clear its site data or change devices, you may permanently lose access to this profile.'))}
  ]);
  return list('Friends',[
    {label:'My Profile',chev:1,thumb:avatarOf(profile),avatar:1,action:()=>push(profileMenu())},
    {label:'Find Friends',chev:1,action:()=>push(inputView('Find Username','Exact @username',findFriend))},
    {label:'Friend Requests',chev:1,action:()=>runView('Loading requests…',requestMenu)},
    {label:'My Friends',chev:1,action:()=>runView('Loading friends…',friendsList)},
    {label:'Share Listening',val:profile.sharing?'On':'Off',action:()=>runView('Updating privacy…',toggleSharing)},
    {label:'Identity Notice',chev:1,action:()=>push(msgView('Anonymous Identity','No login or recovery is available. Clearing browser storage may permanently lose your profile.'))}
  ]);
}
function profileMenu(){
  return list('My Profile',()=>[
    {label:profile.displayName,val:'@'+profile.username,thumb:avatarOf(profile),avatar:1},
    {label:'Profile Picture',chev:1,action:()=>push(photoMenu())},
    {label:'Change Display Name',chev:1,action:()=>push(inputView('Display Name','New display name',changeDisplayName,profile.displayName))},
    {label:'Change Username',chev:1,action:()=>push(inputView('New Username','3–20 letters, numbers, _',changeUsername,profile.username))},
    {label:'Listening Activity',val:profile.sharing?'Shared':'Private'},
    {label:'My User ID',chev:1,action:()=>push(msgView('Permanent User ID',account.uid))}
  ]);
}
async function runView(label,action){
  const loading=loadingView(label);push(loading);
  try{const next=await withRetry(label,action,[15000,20000,25000]);if(top()===loading)replaceTop(next||friendsMenu())}
  catch(e){if(top()===loading)replaceTop(msgView('Friends Error',maybeError(e)))}
}
async function open(){
  if(!navigator.onLine){push(msgView('Friends Offline','Connect to the internet to use Friends. Your downloaded music still works offline.'));return}
  try{localStorage.setItem('ipod.friends.used','1')}catch(e){}
  if(api){push(friendsMenu());return}
  await runView('Connecting Friends…',async()=>{await connect();return friendsMenu()});
}
async function createProfile(raw){
  const username=normalize(raw);
  if(!nameOK(username)){replaceTop(msgView('Invalid Username','Use 3–20 characters, starting with a letter. Only lowercase letters, numbers and underscores are allowed.'));return}
  await runView('Creating Profile…',async()=>{
    const {db}=await connect(),uid=account.uid;
    await db.runTransaction(async tx=>{
      const user=db.collection('profiles').doc(uid),handle=db.collection('handles').doc(username);
      const [userSnapshot,handleSnapshot]=await Promise.all([tx.get(user),tx.get(handle)]);
      if(userSnapshot.exists){if(userSnapshot.data().username===username)return;throw Error('This device already has a profile.')}
      if(handleSnapshot.exists)throw Error('That username is already taken.');
      const time=serverTime();
      tx.set(user,{uid,username,displayName:username,sharing:false,createdAt:time,updatedAt:time});
      tx.set(handle,{uid});
    });
    profile=(await db.collection('profiles').doc(uid).get()).data();cacheProfile(profile);
    return msgView('Welcome, @'+username,'Your identity is ready. Sharing is OFF until you enable it under Friends.');
  });
}
async function changeDisplayName(raw){
  const displayName=String(raw||'').trim();
  if(!displayName||displayName.length>32){replaceTop(msgView('Invalid Name','Choose a display name with 1–32 characters.'));return}
  await runView('Saving Name…',async()=>{
    await api.db.collection('profiles').doc(account.uid).update({displayName,updatedAt:serverTime()});
    profile.displayName=displayName;cacheProfile(profile);return profileMenu();
  });
}
async function changeUsername(raw){
  const username=normalize(raw);
  if(!nameOK(username)){replaceTop(msgView('Invalid Username','Username must start with a letter and contain 3–20 letters, digits or underscores.'));return}
  if(profile.username===username){replaceTop(profileMenu());return}
  await runView('Changing Username…',async()=>{
    const db=api.db,uid=account.uid;
    await db.runTransaction(async tx=>{
      const p=db.collection('profiles').doc(uid);
      const newRef=db.collection('handles').doc(username);
      const [oldProfile,newHandle]=await Promise.all([tx.get(p),tx.get(newRef)]);
      if(!oldProfile.exists)throw Error('Profile missing.');
      const previous=oldProfile.data().username;
      if(previous===username)return;
      if(newHandle.exists)throw Error('Username already taken.');
      tx.delete(db.collection('handles').doc(previous));
      tx.set(newRef,{uid});
      tx.update(p,{username,updatedAt:serverTime()});
    });
    profile.username=username;cacheProfile(profile);return profileMenu();
  });
}
async function findFriend(raw){
  const username=normalize(raw);
  if(!nameOK(username)){replaceTop(msgView('Invalid Username','Search for an exact username such as @moonlight.'));return}
  await runView('Searching…',async()=>{
    const handle=await api.db.collection('handles').doc(username).get();
    if(!handle.exists)return msgView('Not Found','No iPod user has that username.');
    if(handle.data().uid===account.uid)return profileMenu();
    return friendCard(handle.data().uid);
  });
}
async function friendCard(uid){
  const doc=await api.db.collection('profiles').doc(uid).get();
  if(!doc.exists)return msgView('Not Found','This profile is unavailable.');
  const p=doc.data();
  const outbound=await api.db.collection('friendRequests').doc(account.uid+'_'+uid).get();
  const inbound=await api.db.collection('friendRequests').doc(uid+'_'+account.uid).get();
  const chosen=outbound.exists?outbound:inbound;
  const state=chosen.exists?chosen.data().status:'none';
  return list('@'+p.username,[
    {label:p.displayName,val:'@'+p.username,thumb:avatarOf(p),avatar:1},
    {label:'Connection',val:state==='none'?'Not Friends':state},
    ...(state==='none'||(state==='declined'&&outbound.exists)?[{label:state==='declined'?'Send Request Again':'Send Friend Request',chev:1,action:()=>runView('Sending Request…',async()=>{
      if(state==='declined'){
        await outbound.ref.update({status:'pending',updatedAt:serverTime()});
      }else{
        await api.db.collection('friendRequests').doc(account.uid+'_'+uid).set({
          from:account.uid,to:uid,status:'pending',createdAt:serverTime(),updatedAt:serverTime()
        });
      }
      return msgView('Request Sent','Waiting for @'+p.username+' to accept.');
    })}]:[]),
    ...(state==='accepted'?[{label:'Latest 3 Songs',chev:1,action:()=>runView('Loading Listening…',()=>friendListening(uid,p))}]:[]),
    ...(state==='pending'&&inbound.exists?[{label:'Accept Request',chev:1,action:()=>runView('Accepting…',async()=>{
      await inbound.ref.update({status:'accepted',updatedAt:serverTime()});
      return friendCard(uid);
    })}]:[]),
    ...(state==='pending'&&inbound.exists?[{label:'Decline Request',action:()=>runView('Declining…',async()=>{
      await inbound.ref.update({status:'declined',updatedAt:serverTime()});
      return msgView('Declined','The friend request was declined.');
    })}]:[]),
    ...(state==='accepted'?[{label:'Remove Friend',action:()=>runView('Removing Friend…',async()=>{
      await chosen.ref.update({status:'declined',updatedAt:serverTime()});
      return msgView('Removed','You are no longer connected.');
    })}]:[])
  ]);
}
async function requestMenu(){
  const db=api.db,uid=account.uid;
  const [incoming,outgoing]=await Promise.all([
    db.collection('friendRequests').where('to','==',uid).get(),
    db.collection('friendRequests').where('from','==',uid).get()
  ]);
  const pending=[...incoming.docs.filter(d=>d.data().status==='pending').map(d=>({uid:d.data().from,kind:'Received'})),
    ...outgoing.docs.filter(d=>d.data().status==='pending').map(d=>({uid:d.data().to,kind:'Sent'}))];
  if(!pending.length)return msgView('Friend Requests','No pending friend requests.');
  const entries=await Promise.all(pending.map(async item=>{
    const p=await db.collection('profiles').doc(item.uid).get();
    return {label:(p.exists?'@'+p.data().username:'Unknown user'),val:item.kind,chev:1,thumb:avatarOf(p.exists?p.data():null),avatar:1,
      action:()=>runView('Loading…',()=>friendCard(item.uid))};
  }));
  return list('Requests',entries);
}
async function friendsList(){
  const db=api.db,uid=account.uid;
  const [incoming,outgoing]=await Promise.all([
    db.collection('friendRequests').where('to','==',uid).get(),
    db.collection('friendRequests').where('from','==',uid).get()
  ]);
  const uids=[...new Set([
    ...incoming.docs.filter(x=>x.data().status==='accepted').map(x=>x.data().from),
    ...outgoing.docs.filter(x=>x.data().status==='accepted').map(x=>x.data().to)
  ])];
  if(!uids.length)return msgView('No Friends Yet','Search for someone by username to send your first request.');
  const entries=await Promise.all(uids.map(async friendUid=>{
    const doc=await db.collection('profiles').doc(friendUid).get(),p=doc.data();
    return {label:p?'@'+p.username:'Unknown user',val:p&&p.sharing?'Listening':'Private',chev:1,thumb:avatarOf(p),avatar:1,
      action:()=>runView('Loading Friend…',()=>friendCard(friendUid))};
  }));
  return list('My Friends',entries);
}
async function toggleSharing(){
  const sharing=!profile.sharing;await connect();
  await api.db.collection('profiles').doc(account.uid).update({sharing,updatedAt:serverTime()});
  profile.sharing=sharing;cacheProfile(profile);
  return msgView('Listening '+(sharing?'Shared':'Private'),
    sharing?'Approved friends can see your three most recently recorded listens.':'Other users can no longer see your listening history.');
}
function inferVibe(recent){
  const text=recent.map(x=>x.title+' '+x.album).join(' ').toLowerCase();
  if(/\b(love|heart|kiss|romance|snooze)\b/.test(text))return 'Romantic';
  if(/\b(night|moon|dream|sleep|stars)\b/.test(text))return 'Dreamy';
  if(/\b(dance|party|club|disco|energy)\b/.test(text))return 'Energetic';
  if(/\b(sad|lonely|cry|lost|blue)\b/.test(text))return 'Reflective';
  return 'Eclectic Mix';
}
async function friendListening(uid,p){
  if(!p.sharing)return msgView('Private Listening','@'+p.username+' has paused sharing.');
  const doc=await api.db.collection('activity').doc(uid).get();
  if(!doc.exists||!doc.data().recent?.length)return msgView('No Listening Yet','No shared songs have been played yet.');
  const recent=doc.data().recent.slice(0,3);
  return list('@'+p.username+' Listens',[
    {label:'Listening Vibe',val:inferVibe(recent)},
    ...recent.map(x=>({label:x.title,val:x.artist,chev:1,action:()=>push(msgView(x.title,x.artist+(x.album?' — '+x.album:'')))})),
    {label:'About Vibe',action:()=>push(msgView('Music-Based Vibe','This label is a lighthearted guess from song titles, not a statement about a person’s emotional state.'))}
  ]);
}
let trackedId=null,lastTime=0,seconds=0,published=false;
function recordTime(){
  if(!api||!profile?.sharing||audio.paused)return;
  const track=cur();
  if(!track||!track.title)return;
  const id=track.id||track.sourceId||track.title+'|'+track.artist;
  const t=audio.currentTime||0;
  if(trackedId!==id||t<lastTime-2){trackedId=id;seconds=0;published=false;lastTime=t}
  const delta=t-lastTime;
  lastTime=t;
  if(delta>0&&delta<3)seconds+=delta;
  if(!published&&seconds>=30){
    published=true;
    withRetry('Sharing listen',()=>publishPlay(track)).catch(e=>console.warn('Friends activity unavailable:',e.message));
  }
}
async function publishPlay(song){
  if(!profile?.sharing||!api)return;
  const uid=account.uid,ref=api.db.collection('activity').doc(uid);
  const existing=await ref.get();
  const previous=existing.exists?(existing.data().recent||[]):[];
  const artwork=String(song.artworkUrl||song.artUrl||'');
  const entry={
    title:String(song.title||'Untitled').slice(0,140),
    artist:String(song.artist||'').slice(0,140),
    album:String(song.album||'').slice(0,140),
    artworkUrl:artwork.startsWith('https://')?artwork.slice(0,500):'',
    listenedAt:new Date()
  };
  await ref.set({uid,recent:[entry,...previous].slice(0,3),updatedAt:serverTime()});
}
audio.addEventListener('timeupdate',recordTime);
window.ipodFriends={open};
})();
