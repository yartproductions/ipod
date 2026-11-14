/* iPod Friends — optional anonymous social layer. The music player does not depend on Firebase. */
(function(){
'use strict';
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
  :e&&e.message||'Please try again.';
function loadSDK(file){
  return new Promise((resolve,reject)=>{
    const script=document.createElement('script');
    script.src='https://www.gstatic.com/firebasejs/'+SDK+'/'+file;
    script.onload=resolve;
    script.onerror=()=>reject(Error('Firebase could not load. Check your connection.'));
    document.head.appendChild(script);
  });
}
async function connect(){
  if(api)return api;
  if(initTask)return initTask;
  initTask=(async()=>{
    await loadSDK('firebase-app-compat.js');
    await loadSDK('firebase-auth-compat.js');
    await loadSDK('firebase-firestore-compat.js');
    const app=firebase.apps.find(x=>x.name==='ipod-friends')||firebase.initializeApp(CONFIG,'ipod-friends');
    const auth=app.auth(),db=app.firestore();
    // Wait for persisted authentication to resolve before creating a new anonymous user.
    const existing=await new Promise(resolve=>{const off=auth.onAuthStateChanged(u=>{off();resolve(u)},()=>{off();resolve(null)})});
    account=existing||(await auth.signInAnonymously()).user;
    const doc=await db.collection('profiles').doc(account.uid).get();
    profile=doc.exists?doc.data():null;
    api={auth,db};
    return api;
  })();
  try{return await initTask}finally{initTask=null}
}
function friendsMenu(){
  if(!profile)return list('Friends',[
    {label:'Create My Profile',chev:1,action:()=>push(inputView('Choose Username','3–20 letters, numbers, _',createProfile))},
    {label:'About Identity',chev:1,action:()=>push(msgView('No Recovery Yet','Your Friends identity belongs to this browser. If you clear its site data or change devices, you may permanently lose access to this profile.'))}
  ]);
  return list('Friends',[
    {label:'My Profile',chev:1,action:()=>push(profileMenu())},
    {label:'Find Friends',chev:1,action:()=>push(inputView('Find Username','Exact @username',findFriend))},
    {label:'Friend Requests',chev:1,action:()=>runView('Loading requests…',requestMenu)},
    {label:'My Friends',chev:1,action:()=>runView('Loading friends…',friendsList)},
    {label:'Share Listening',val:profile.sharing?'On':'Off',action:()=>runView('Updating privacy…',toggleSharing)},
    {label:'Identity Notice',chev:1,action:()=>push(msgView('Anonymous Identity','No login or recovery is available. Clearing browser storage may permanently lose your profile.'))}
  ]);
}
function profileMenu(){
  return list('My Profile',[
    {label:'Name',val:profile.displayName},
    {label:'Username',val:'@'+profile.username},
    {label:'Change Display Name',chev:1,action:()=>push(inputView('Display Name','New display name',changeDisplayName,profile.displayName))},
    {label:'Change Username',chev:1,action:()=>push(inputView('New Username','3–20 letters, numbers, _',changeUsername,profile.username))},
    {label:'Listening Activity',val:profile.sharing?'Shared':'Private'},
    {label:'My User ID',chev:1,action:()=>push(msgView('Permanent User ID',account.uid))}
  ]);
}
async function runView(label,action){
  const loading=loadingView(label);push(loading);
  try{const next=await action();if(top()===loading)replaceTop(next||friendsMenu())}
  catch(e){if(top()===loading)replaceTop(msgView('Friends Error',maybeError(e)))}
}
async function open(){
  if(!navigator.onLine){push(msgView('Friends Offline','Connect to the internet to use Friends. Your downloaded music still works offline.'));return}
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
      if(userSnapshot.exists)throw Error('This device already has a profile.');
      if(handleSnapshot.exists)throw Error('That username is already taken.');
      const time=serverTime();
      tx.set(user,{uid,username,displayName:username,sharing:false,createdAt:time,updatedAt:time});
      tx.set(handle,{uid});
    });
    profile=(await db.collection('profiles').doc(uid).get()).data();
    return msgView('Welcome, @'+username,'Your identity is ready. Sharing is OFF until you enable it under Friends.');
  });
}
async function changeDisplayName(raw){
  const displayName=String(raw||'').trim();
  if(!displayName||displayName.length>32){replaceTop(msgView('Invalid Name','Choose a display name with 1–32 characters.'));return}
  await runView('Saving Name…',async()=>{
    await api.db.collection('profiles').doc(account.uid).update({displayName,updatedAt:serverTime()});
    profile.displayName=displayName;return profileMenu();
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
      if(newHandle.exists)throw Error('Username already taken.');
      const previous=oldProfile.data().username;
      tx.delete(db.collection('handles').doc(previous));
      tx.set(newRef,{uid});
      tx.update(p,{username,updatedAt:serverTime()});
    });
    profile.username=username;return profileMenu();
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
    {label:p.displayName,val:'@'+p.username},
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
    return {label:(p.exists?'@'+p.data().username:'Unknown user'),val:item.kind,chev:1,
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
    return {label:p?'@'+p.username:'Unknown user',val:p&&p.sharing?'Listening':'Private',chev:1,
      action:()=>runView('Loading Friend…',()=>friendCard(friendUid))};
  }));
  return list('My Friends',entries);
}
async function toggleSharing(){
  const sharing=!profile.sharing;
  await api.db.collection('profiles').doc(account.uid).update({sharing,updatedAt:serverTime()});
  profile.sharing=sharing;
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
    publishPlay(track).catch(e=>console.warn('Friends activity unavailable:',e.message));
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
