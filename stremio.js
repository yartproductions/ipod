/* Stremio account + installed add-on HTTPS playback. Secrets stay in memory for this page session. */
(()=>{
'use strict';
const b=window.ipodVideoBridge;if(!b)return;
const {list,push,replaceTop,top,msgView,loadingView,inputView}=b;
const API='https://api.strem.io/api/',META='https://v3-cinemeta.strem.io';
let authKey='',addons=[],generation=0,player=null,connecting=false;
const clean=(x,max=160)=>typeof x==='string'?x.slice(0,max):'';
function httpsURL(value){
 try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||u.port&&u.port!=='443')return null;
  const h=u.hostname.toLowerCase();
  if(!h.includes('.')||h.endsWith('.local')||h.endsWith('.localhost')||h.includes(':')||/^\d+\.\d+\.\d+\.\d+$/.test(h))return null;
  return u.href;
 }catch{return null}
}
async function json(url,options={},label='Service'){
 let response;
 try{response=await fetch(url,{...options,credentials:'omit',referrerPolicy:'no-referrer',redirect:url.startsWith(META+'/')?'follow':'error',signal:AbortSignal.timeout(25000)})}
 catch{throw Error(label+' could not be reached. Check your connection and try again.')}
 if(!response.ok)throw Error(label+' returned HTTP '+response.status+'. Try again later.');
 try{return await response.json()}catch{throw Error(label+' returned an unreadable response.')}
}
async function rpc(method,params={}){
 const data=await json(API+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({authKey:authKey||null,...params})},'Stremio');
 if(data.error||!data.result)throw Error(method==='login'?'Sign-in failed. Check your Stremio email and password.':'Stremio could not complete this request. Reconnect your account and try again.');
 return data.result;
}
function normalizeAddons(items){
 if(!Array.isArray(items))throw Error('Stremio did not return an add-on list.');
 return items.filter(a=>a&&httpsURL(a.transportUrl)&&new URL(a.transportUrl).pathname.endsWith('/manifest.json')&&a.manifest&&typeof a.manifest==='object')
  .filter(a=>Array.isArray(a.manifest.resources)&&a.manifest.resources.some(r=>(typeof r==='string'?r:r?.name)==='stream'))
  .map(a=>({base:a.transportUrl.replace(/\/manifest\.json(?:\?.*)?$/,''),manifest:a.manifest,name:clean(a.manifest.name||a.manifest.id||'Video add-on',60)}));
}
function supports(a,type,id){return Array.isArray(a.manifest.resources)&&a.manifest.resources.some(r=>{
 const resource=typeof r==='string'?{name:r,types:a.manifest.types,idPrefixes:a.manifest.idPrefixes}:r;
 return resource?.name==='stream'&&(!resource.types||resource.types.includes(type))&&(!resource.idPrefixes||resource.idPrefixes.some(p=>id.startsWith(p)));
})}
async function loading(title,work){
 const v=loadingView(title),epoch=generation;push(v);
 try{const result=await work();if(top()===v&&epoch===generation)replaceTop(result)}
 catch(e){if(top()===v&&epoch===generation)replaceTop(msgView(title,clean(e.message)||'Please try again.'))}
}
function connect(){
 if(connecting)return;
 push(inputView('Stremio Email','Your Stremio email',email=>{
  email=email.trim();if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){replaceTop(msgView('Email Needed','Enter the email you use for Stremio.'));return}
  const passwordView={...inputView('Stremio Password','Your Stremio password',async password=>{
   if(connecting)return;
   passwordView.value='';const field=document.querySelector('#inpt');if(field)field.value='';
   const v=loadingView('Connecting Stremio'),epoch=++generation;replaceTop(v);connecting=true;
   try{
    const result=await rpc('login',{email,password});password='';
    if(epoch!==generation)return;
    if(typeof result.authKey!=='string'||!result.authKey)throw Error('Stremio did not return a session.');
    authKey=result.authKey;
    const collection=await rpc('addonCollectionGet',{update:true,addFromURL:[]});
    if(epoch!==generation)return;
    addons=normalizeAddons(collection.addons);
    if(top()===v)replaceTop(settingsView());
   }catch(e){if(epoch!==generation)return;authKey='';addons=[];if(top()===v)replaceTop(msgView('Connection Failed',clean(e.message)))}
   finally{connecting=false}
  }),inputType:'password'};
  replaceTop(passwordView);
 }));
}
function disconnect(){
 const key=authKey;generation++;authKey='';addons=[];connecting=false;closePlayer();
 if(key)rpc('logout',{authKey:key}).catch(()=>{});
 replaceTop(settingsView());
}
function settingsView(){return list('Stremio',()=>[
 {label:authKey?'Account Connected':'Connect Account',icon:'people',action:authKey?undefined:connect},
 ...(authKey?[
  {label:'Video Add-ons',val:String(addons.length)},
  {label:'Refresh Add-ons',action:()=>loading('Refreshing Add-ons',async()=>{const epoch=generation,collection=await rpc('addonCollectionGet',{update:true,addFromURL:[]});if(epoch===generation)addons=normalizeAddons(collection.addons);return settingsView()})},
  {label:'Disconnect',action:disconnect},
 ]:[]),
 {label:'Connection Info',icon:'info',action:()=>push(msgView('Connection Info','Sign in with your Stremio email and password. Installed video add-ons such as Torrentio, Absolute Cinema and WebStreamr are retrieved automatically. Passwords and add-on keys are not saved; reconnect after reloading. Apple/Google-only accounts need a Stremio password.'))},
 {label:'Playback Help',icon:'info',action:()=>push(msgView('Playback Help','Uses direct HTTPS streams from your installed Stremio add-ons. A TorBox “downloading” result is still being cached: reopen the title after it finishes or choose an instant source from another add-on. Raw torrents, external webpages and streams requiring custom headers cannot play here. Unsupported codecs may not play on iPhone.'))},
])}
function readProgress(){try{const value=JSON.parse(localStorage.getItem('ipod.videoProgress')||'[]');return Array.isArray(value)?value.filter(x=>x&&typeof x.id==='string'&&['movie','series'].includes(x.type)&&Number.isFinite(x.time)&&x.time>=0):[]}catch{return []}}
function remember(item,time,duration,ended=false){
 if(!Number.isFinite(time)||time<=0)return;
 const old=readProgress().filter(x=>x.id!==item.id||x.type!==item.type);
 const finished=ended||(Number.isFinite(duration)&&duration>0&&time>=duration-15);
 const entry={id:item.id,type:item.type,name:clean(item.name),time,duration:Number.isFinite(duration)?duration:0};
 // Store metadata and position only; stream URLs can contain provider credentials.
 try{localStorage.setItem('ipod.videoProgress',JSON.stringify(finished?old:[entry,...old].slice(0,50)))}catch{}
}
function home(){return list('Videos',()=>[
 {label:'Shows',icon:'playlist',chev:1,action:()=>browse('series')},
 {label:'Movies',icon:'play',chev:1,action:()=>browse('movie')},
 {label:'Search Shows',icon:'search',chev:1,action:()=>search('series')},
 {label:'Search Movies',icon:'search',chev:1,action:()=>search('movie')},
 {label:'Continue Watching',icon:'clock',chev:1,action:()=>push(list('Continue Watching',()=>readProgress().map(x=>({label:x.name,chev:1,action:()=>sources(x)})),{emptyText:'Start an episode or movie to save your place on this device.'}))},
 {label:authKey?'Stremio Settings':'Connect Stremio',icon:'settings',chev:1,action:()=>push(settingsView())},
])}
function search(type){push(inputView(type==='series'?'Search Shows':'Search Movies','Title',q=>{b.pop();browse(type,q.trim())}))}
function browse(type,query='',skip=0){
 return loading(query?'Search Results':type==='series'?'Shows':'Movies',async()=>{
  const extra=new URLSearchParams({...query?{search:query}:{},skip:String(skip)});
  const result=await json(META+'/catalog/'+type+'/top/'+extra+'.json',{},'Catalog');
  const items=(Array.isArray(result.metas)?result.metas:[]).filter(x=>typeof x.id==='string'&&typeof x.name==='string');
  const rows=items.map(x=>({label:clean(x.name),thumb:httpsURL(x.poster),tile:'▶',sub:clean(x.releaseInfo),action:()=>details({...x,type})}));
  if(items.length>=100)rows.push({label:'More…',tile:'›',action:()=>browse(type,query,skip+items.length)});
  return rows.length?{...list(query|| (type==='series'?'Shows':'Movies'),rows),type:'covers'}:msgView('No Results','Try another title.');
 });
}
function details(item){
 return loading(clean(item.name),async()=>{
  const result=await json(META+'/meta/'+item.type+'/'+encodeURIComponent(item.id)+'.json',{},'Title details');
  const meta=result.meta;if(!meta)throw Error('No details are available for this title.');
  const intro={label:'About',icon:'info',action:()=>push(msgView(clean(meta.name),clean(meta.description,1200)||'No description available.'))};
  if(item.type==='movie')return list(clean(meta.name),[{label:'Choose Stream',icon:'play',action:()=>sources({id:meta.id||item.id,type:'movie',name:clean(meta.name)})},intro]);
  const episodes=(Array.isArray(meta.videos)?meta.videos:[]).filter(v=>typeof v.id==='string'&&Number.isInteger(v.season)&&Number.isInteger(v.episode)).sort((a,b)=>a.season-b.season||a.episode-b.episode);
  const seasons=[...new Set(episodes.map(v=>v.season))];
  return list(clean(meta.name),[...seasons.map(season=>({label:season===0?'Specials':'Season '+season,chev:1,action:()=>push(list('Season '+season,episodes.filter(v=>v.season===season).map(v=>({
   label:v.episode+'. '+clean(v.title||v.name||'Episode'),chev:1,action:()=>sources({id:v.id,type:'series',name:clean(meta.name)+' · S'+season+' E'+v.episode})
  }))))})),intro]);
 });
}
function playable(stream){return !!httpsURL(stream?.url)&&!stream?.behaviorHints?.proxyHeaders}
function sources(item){
 if(!authKey){push(settingsView());return}
 return loading('Finding Streams',async()=>{
  const providers=addons.filter(a=>supports(a,item.type,item.id));
  if(!providers.length)throw Error('No compatible video add-on is installed. Check Stremio, then refresh add-ons here.');
  const results=await Promise.allSettled(providers.map(async a=>{
   const result=await json(a.base+'/stream/'+item.type+'/'+encodeURIComponent(item.id)+'.json',{},a.name);
   return (Array.isArray(result.streams)?result.streams:[]).filter(s=>s&&typeof s==='object').map(stream=>({stream,addonName:a.name}));
  }));
  const streams=results.flatMap(r=>r.status==='fulfilled'?r.value:[]),direct=streams.filter(x=>playable(x.stream));
  if(!direct.length)throw Error(results.every(r=>r.status==='rejected')?'Your video add-ons could not be reached. Try again later.':streams.length?'These results need Stremio’s torrent engine, an external webpage or custom request headers. Try a direct source from another add-on.':'No streams returned for this episode. Try another title or refresh your Stremio add-ons.');
  return list('Choose Stream',direct.slice(0,100).map(({stream:s,addonName},i)=>({label:clean(s.name||'Source '+(i+1),60),sub:addonName,chev:1,action:()=>push(list('Stream Details',[
   {label:'Play',icon:'play',action:()=>play(s,item)},
   {label:'Details',icon:'info',action:()=>push(msgView(clean(s.name||'Source'),clean(s.description||s.title,1000)||'Direct HTTPS video from '+addonName+'.'))},
  ]))})));
 });
}
function closePlayer(){if(player)player.close()}
function play(stream,item){
 const url=httpsURL(stream.url);if(!url)return;
 closePlayer();b.pauseMusic();
 const screen=document.querySelector('#screen'),previousFocus=document.activeElement;
 const hidden=[...screen.children].map(el=>[el,el.inert]);
 hidden.forEach(([el])=>el.inert=true);screen.classList.add('video-active');
 const dialog=document.createElement('section');dialog.className='ipod-video';dialog.setAttribute('aria-label',item.name);
 const bar=document.createElement('div');bar.className='video-toolbar';
 const title=document.createElement('strong');title.textContent=item.name;
 const close=document.createElement('button');close.textContent='Close';close.type='button';
 const fullscreen=document.createElement('button');fullscreen.textContent='Fullscreen';fullscreen.type='button';
 const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=url;video.setAttribute('aria-label',item.name);
 const status=document.createElement('p');status.setAttribute('role','status');status.textContent='Loading video…';
 let lastSaved=0,closed=false,finished=false;
 const save=()=>remember(item,video.currentTime,video.duration,finished);
 const onHide=()=>{if(document.hidden)save()};
 const finish=()=>{if(closed)return;closed=true;save();video.pause();video.removeAttribute('src');video.load();dialog.remove();document.removeEventListener('visibilitychange',onHide);window.removeEventListener('pagehide',save);player=null;hidden.forEach(([el,inert])=>el.inert=inert);screen.classList.remove('video-active');if(previousFocus?.isConnected)previousFocus.focus();b.restoreMusicControls()};
 const seek=delta=>{if(Number.isFinite(video.duration))video.currentTime=Math.max(0,Math.min(video.duration,video.currentTime+delta))};
 player={close:finish,control:btn=>{
  if(btn==='menu')finish();
  else if(btn==='play'||btn==='select'){if(video.paused)video.play().catch(()=>{status.textContent='Tap Play to try again.'});else video.pause()}
  else if(btn==='next')seek(10);
  else if(btn==='prev')seek(-10);
 }};
 if('mediaSession' in navigator){try{
  const ms=navigator.mediaSession;ms.setPositionState?.();ms.metadata=new MediaMetadata({title:item.name,artist:'iPod Videos'});
  ms.setActionHandler('play',()=>video.play().catch(()=>{}));ms.setActionHandler('pause',()=>video.pause());
  ms.setActionHandler('stop',finish);ms.setActionHandler('seekto',event=>{if(Number.isFinite(video.duration))video.currentTime=Math.max(0,Math.min(event.seekTime,video.duration))});
  for(const action of ['nexttrack','previoustrack','seekforward','seekbackward'])ms.setActionHandler(action,null);
 }catch{}}

 close.onclick=finish;dialog.addEventListener('cancel',e=>{e.preventDefault();finish()});
 dialog.addEventListener('keydown',e=>{e.stopPropagation();if(e.key==='Escape'){e.preventDefault();finish()}});dialog.addEventListener('wheel',e=>e.stopPropagation());
 fullscreen.onclick=()=>{if(video.webkitEnterFullscreen)video.webkitEnterFullscreen();else if(video.requestFullscreen)video.requestFullscreen().catch(()=>{status.textContent='Fullscreen is unavailable. You can still watch here.'})};
 video.addEventListener('loadedmetadata',()=>{const progress=readProgress().find(x=>x.id===item.id&&x.type===item.type);if(progress&&Number.isFinite(video.duration)&&progress.time<video.duration-15)video.currentTime=progress.time});
 video.addEventListener('playing',()=>{status.textContent='';b.pauseMusic();if(navigator.mediaSession)navigator.mediaSession.playbackState='playing'});
 video.addEventListener('waiting',()=>{status.textContent='Buffering…'});
 video.addEventListener('error',()=>{status.textContent='This source could not play. It may not be ready or may use an unsupported format. Close and choose another source.'});
 video.addEventListener('timeupdate',()=>{if(Date.now()-lastSaved>5000){save();lastSaved=Date.now()}});
 video.addEventListener('ended',()=>{finished=true;save();status.textContent='Finished'});
 video.addEventListener('pause',()=>{save();if(navigator.mediaSession)navigator.mediaSession.playbackState='paused'});
 document.addEventListener('visibilitychange',onHide);window.addEventListener('pagehide',save);
 bar.append(close,title,fullscreen);dialog.append(bar,video,status);screen.append(dialog);close.focus();
 // Use the user's Play tap so iOS can start media without a second gesture.
 video.play().catch(()=>{if(!closed&&!video.error)status.textContent='Tap the video’s Play button to start.'});
}
window.ipodVideos=Object.freeze({open:()=>push(home()),settings:()=>push(settingsView()),close:closePlayer,control:btn=>player?.control(btn),get playing(){return !!player}});
})();
