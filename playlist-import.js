/* iPod Playlist Transfer: import playlist metadata, preview matches, save locally. */
(function(){
'use strict';
const b=window.ipodPlaylistImportBridge;if(!b)return;
const {list,push,replaceTop,top,msgView,loadingView,inputView,ytApi,settings,playYT,playList,getSongs}=b;
const KEY='ipod.importedPlaylists.v1',LIMIT=500;
const text=x=>String(x??'').trim();
const clean=x=>text(x).slice(0,200);
const matcher=()=>window.ipodTrackMatch;
const read=()=>{try{const p=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(p)?p:[]}catch(e){return []}};
const write=items=>localStorage.setItem(KEY,JSON.stringify(items));
function duration(x){if(typeof x==='number')return x>100000?Math.round(x/1000):Math.round(x);
 const s=text(x);if(/^\d+:\d\d(?::\d\d)?$/.test(s)){return s.split(':').map(Number).reduce((a,b)=>a*60+b,0)}return /^\d+$/.test(s)?Number(s):0}
function normalize(s){return text(s).normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim().replace(/\s+/g,' ')}
function toTrack(item){
 const title=clean(item.title||item.track||item.name);
 let artist=item.artist||item.artistName||item.performer;
 if(typeof artist==='object')artist=artist.name||artist.title;
 if(Array.isArray(artist))artist=artist.map(a=>typeof a==='string'?a:a.name||'').join(', ');
 const album=item.album&&typeof item.album==='object'?(item.album.title||item.album.name):item.album;
 if(!title||!text(artist))return null;
 return {title,artist:clean(artist),album:clean(album),duration:duration(item.duration||item.length),
 isrc:clean(item.isrc),youtubeId:clean(item.youtubeId),status:item.youtubeId?'matched':'unmatched'};
}
function csvRows(input){let rows=[],row=[],field='',quoted=false;
 for(let i=0;i<input.length;i++){let c=input[i];
  if(c==='"'){if(quoted&&input[i+1]==='"'){field+='"';i++}else quoted=!quoted}
  else if(c===','&&!quoted){row.push(field);field=''}
  else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&input[i+1]==='\n')i++;row.push(field);rows.push(row);row=[];field=''}
  else field+=c;
 }
 if(row.length||field){row.push(field);rows.push(row)}return rows;
}
function parseFile(data,name){
 if(data.length>3000000)throw Error('The maximum file size is 3 MB.');
 const type=text(name).toLowerCase();let raw=[];
 if(type.endsWith('.json')){
  const j=JSON.parse(data);raw=Array.isArray(j)?j:Array.isArray(j.tracks)?j.tracks:Array.isArray(j.tracks?.items)?j.tracks.items:j.items||j.songs||[];
  if(!Array.isArray(raw))throw Error('JSON must contain a tracks array.');
  raw=raw.map(x=>x.track&&typeof x.track==='object'?x.track:x);
 }else if(type.endsWith('.csv')){
  const rows=csvRows(data.replace(/^\uFEFF/,''));const header=(rows.shift()||[]).map(x=>normalize(x).replace(/\s/g,''));
  const col=(names)=>names.map(x=>header.indexOf(x)).find(i=>i>=0);
  const t=col(['title','track','tracktitle','song','name']),a=col(['artist','artistname','artists','performer']);
  const l=col(['album','albumname','collection']),d=col(['duration','durationms','length']),i=col(['isrc']);
  if(t==null||a==null)throw Error('CSV must contain title and artist columns.');
  raw=rows.map(r=>({title:r[t],artist:r[a],album:l==null?'':r[l],duration:d==null?'':r[d],isrc:i==null?'':r[i]}));
 }else if(type.endsWith('.txt')){
  raw=data.split(/\r?\n/).map(x=>{const s=x.split(/\s+[-–—]\s+/);return s.length>1?{artist:s.shift(),title:s.join(' - ')}:null}).filter(Boolean);
 }else throw Error('Choose a CSV, JSON, or TXT file.');
 const tracks=raw.map(toTrack).filter(Boolean).slice(0,LIMIT);
 if(!tracks.length)throw Error('No tracks containing both artist and title were found.');
 return tracks;
}
function detect(url){
 try{const u=new URL(text(url));if(!/^https?:$/.test(u.protocol))return null;
 const host=u.hostname.toLowerCase();
 if(['youtube.com','www.youtube.com','music.youtube.com','m.youtube.com'].includes(host)){
  const id=u.searchParams.get('list');return id&&/^[\w-]{10,90}$/.test(id)?{provider:'youtube',id}:null}
 if(['qobuz.com','www.qobuz.com','open.qobuz.com','play.qobuz.com'].includes(host)){
  const m=u.pathname.match(/\/playlist\/(\d+)/);return m?{provider:'qobuz',id:m[1]}:null}
 }catch(e){}return null;
}
async function youtubeTracks(id){
 if(!settings.ytKey)throw Error('Set your YouTube API key first.');
 let tracks=[],token='',name='YouTube Playlist';
 for(let page=0;page<10&&tracks.length<LIMIT;page++){
  const response=await ytApi('playlistItems',{part:'snippet',playlistId:id,maxResults:50,pageToken:token});
  for(const row of response.items||[]){
   const s=row.snippet||{},id=s.resourceId?.videoId;
   if(!id||/^(private|deleted) video$/i.test(s.title||''))continue;
   const parsed=matcher()?.parseTitle?.(s.title,s.videoOwnerChannelTitle||s.channelTitle)||{title:s.title,artist:s.videoOwnerChannelTitle||s.channelTitle};
   const t=toTrack({...parsed,youtubeId:id});if(t)tracks.push(t);
  }
  token=response.nextPageToken||'';if(!token)break;
 }
 if(!tracks.length)throw Error('Playlist is empty, private, or contains no usable track metadata.');
 try{const p=await ytApi('playlists',{part:'snippet',id});name=clean(p.items?.[0]?.snippet?.title)||name}catch(e){}
 return {name,tracks:tracks.slice(0,LIMIT),provider:'YouTube',source:'https://www.youtube.com/playlist?list='+id};
}
function save(data){
 const library=read(),pl={id:'playlist-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,9),
  name:clean(data.name)||'Imported Playlist',provider:data.provider||'File',source:data.source||'',
  tracks:data.tracks.slice(0,LIMIT),createdAt:Date.now()};
 library.unshift(pl);write(library);return pl;
}
function available(t){return getSongs().find(s=>s.sourceId&&s.sourceId===t.youtubeId)||
 getSongs().find(s=>(matcher()?.exactCandidate?.(t,s)||
 (!matcher()&&normalize(s.title)===normalize(t.title)&&normalize(s.artist)===normalize(t.artist)))&&
 (!t.duration||!s.duration||Math.abs(t.duration-s.duration)<=Math.max(5,t.duration*.03)));}
function playlistView(pl){
 return list(pl.name,()=>{
  const existing=pl.tracks.filter(available).length,matched=pl.tracks.filter(t=>t.youtubeId).length;
  return [
   {label:'Tracks',val:pl.tracks.length+' total'},
   {label:'Available Offline',val:existing+' tracks'},
   {label:'YouTube Links',val:matched+' matched'},
   {label:'Match Unresolved',action:()=>matchPlaylist(pl)},
   {label:'Play Available Offline',action:()=>{
    const ready=pl.tracks.map(available).filter(Boolean);
    if(!ready.length)push(msgView('No Offline Songs','Match or add songs before playing.'));
    else playList(ready,0);
   }},
   ...pl.tracks.map((t,i)=>({label:(i+1)+'. '+t.title,val:t.artist,action:()=>{
    const local=available(t);
    if(local)playList([local],0);
    else if(t.youtubeId)playYT([{kind:'yt',id:t.youtubeId,title:t.title,artist:t.artist,album:t.album}],0);
    else push(msgView('Unmatched Track',t.artist+' — '+t.title+'. Use Match Unresolved first.'));
   }}))
  ];
 });
}
function preview(data){return list('Import Preview',[
 {label:'Playlist',val:data.name},{label:'Source',val:data.provider},{label:'Songs',val:String(data.tracks.length)},
 {label:'Save to iPod',action:()=>replaceTop(playlistView(save(data)))},
 ...data.tracks.slice(0,25).map((t,i)=>({label:(i+1)+'. '+t.title,val:t.artist}))
]);}
function picker(){
 const el=document.createElement('input');el.type='file';el.accept='.json,.csv,.txt';el.style.display='none';
 document.body.appendChild(el);
 el.addEventListener('change',async()=>{
  const file=el.files?.[0];el.remove();if(!file)return;
  const loading=loadingView('Reading Playlist…');push(loading);
  try{const content=await file.text();const tracks=parseFile(content,file.name);
   if(top()===loading)replaceTop(preview({name:file.name.replace(/\.[^.]+$/,''),provider:'File',tracks,source:''}));}
  catch(e){if(top()===loading)replaceTop(msgView('Import Failed',e.message));}
 },{once:true});el.click();
}
function linkInput(){push(inputView('Playlist Link','YouTube Music or Qobuz URL',url=>{
 const info=detect(url);
 if(!info)return replaceTop(msgView('Unsupported Link','Paste a YouTube playlist or Qobuz playlist URL.'));
 if(info.provider==='qobuz')return replaceTop(list('Qobuz Playlist',[
  {label:'Playlist ID',val:info.id},
  {label:'Import Export File',action:picker},
  {label:'Why an Export?',action:()=>push(msgView('Qobuz API Access','Qobuz requires an approved partner application and credentials to retrieve playlist tracks. Export the playlist as CSV, JSON or TXT, then import its metadata here.'))}
 ]));
 const loading=loadingView('Reading Playlist…');replaceTop(loading);
 youtubeTracks(info.id).then(data=>{if(top()===loading)replaceTop(preview(data))})
 .catch(e=>{if(top()===loading)replaceTop(msgView('Import Failed',e.message))});
 }));}
async function youtubeMatch(track){
 const m=matcher();if(!m)throw Error('YouTube matcher not loaded.');
 if(!settings.ytKey)throw Error('Set your YouTube API key first.');
 const result=await ytApi('search',{part:'snippet',type:'video',maxResults:25,
 q:track.artist+' '+track.title,videoCategoryId:'10',videoEmbeddable:'true'});
 const matches=(result.items||[]).filter(x=>x.id?.videoId&&x.snippet).map(x=>{
  const candidate=m.parseTitle(x.snippet.title,x.snippet.channelTitle);
  return {id:x.id.videoId,title:candidate.title,artist:candidate.artist};
 }).filter(c=>m.exactCandidate(track,c));
 if(!matches.length)return {status:'unmatched'};
 const data=await ytApi('videos',{part:'contentDetails',id:matches.map(x=>x.id).join(',')});
 const durations=new Map((data.items||[]).map(x=>[x.id,m.durationSeconds(x.contentDetails?.duration)]));
 const verified=matches.filter(x=>m.durationOK(track.duration,durations.get(x.id)));
 if(verified.length!==1)return {status:verified.length?'review':'unmatched',choices:verified};
 return {status:'matched',youtubeId:verified[0].id};
}
async function matchPlaylist(pl){
 const loading=loadingView('Matching Tracks…');push(loading);
 try{
  const tracks=pl.tracks.map(x=>({...x}));let matched=0,review=0,unmatched=0;
  for(let i=0;i<tracks.length;i++){
   const t=tracks[i];
   if(t.youtubeId){matched++;continue}
   if(available(t)){t.status='local';matched++;continue}
   const found=await youtubeMatch(t);
   t.status=found.status;if(found.youtubeId)t.youtubeId=found.youtubeId;
   if(found.status==='matched')matched++;else if(found.status==='review')review++;else unmatched++;
   // Allow the UI to repaint; avoid requesting every playlist track simultaneously.
   if(i%5===4)await new Promise(r=>setTimeout(r,50));
  }
  pl.tracks=tracks;const all=read(),idx=all.findIndex(p=>p.id===pl.id);
  if(idx>=0){all[idx]=pl;write(all)}
  if(top()===loading)replaceTop(list('Matching Complete',[
   {label:'Matched',val:String(matched)},{label:'Needs Review',val:String(review)},
   {label:'Unmatched',val:String(unmatched)},
   {label:'View Playlist',action:()=>push(playlistView(pl))}
  ]));
 }catch(e){if(top()===loading)replaceTop(msgView('Matching Failed',e.message))}
}
function library(){push(list('Imported Playlists',()=>[
 {label:'Import Another',action:open},
 ...read().map(p=>({label:p.name,val:p.tracks.length+' tracks',action:()=>push(playlistView(p))}))
]));}
function open(){push(list('Import Playlist',[
 {label:'Paste Playlist Link',action:linkInput},
 {label:'Import CSV / JSON / TXT',action:picker},
 {label:'Saved Playlists',action:library},
 {label:'How It Works',action:()=>push(msgView('Import Music','A playlist stores song metadata and verified YouTube references. It never automatically downloads audio. Match unresolved tracks before playback.'))}
]));}
window.ipodPlaylistImport={open,library,parseFile,detect,duration,youtubeTracks,youtubeMatch};
})();