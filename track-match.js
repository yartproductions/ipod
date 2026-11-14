/* Track matching for externally supplied metadata; never silently choose an unrelated recording. */
(function(){
'use strict';
const b=window.ipodTrackMatchBridge;
if(!b)return;
const {list,push,replaceTop,top,msgView,loadingView,inputView,ytApi,settings,playYT}=b;
function normalize(value){
 return String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'')
 .replace(/[\u200b-\u200d\uFEFF]/g,'').toLowerCase()
 .replace(/\b(?:official\s+)?(?:music video|lyric video|lyrics video|audio|visualizer)\b/g,'')
 .replace(/[^\p{L}\p{N}]+/gu,' ').trim().replace(/\s+/g,' ');
}
function edition(value){
 const source=normalize(value);
 const tags=['live','remix','acoustic','instrumental','karaoke','demo','cover','extended','sped up','slowed','radio edit','re recorded','remaster','remastered'];
 return tags.filter(tag=>new RegExp('(?:^|\\s)'+tag+'(?:\\s|$)').test(source)).sort().join('|');
}
function coreTitle(value){
 return normalize(value).replace(/\b(?:remastered|remaster|live|acoustic|instrumental|karaoke|demo|extended|sped up|slowed|radio edit|re recorded)\b/g,'')
 .replace(/\b(?:19|20)\d\d\b/g,'').trim().replace(/\s+/g,' ');
}
function parseTitle(raw,channel){
 const text=String(raw||'').replace(/&amp;/g,'&').replace(/&quot;/g,'"');
 const parts=text.split(/\s+[-–—]\s+/);
 if(parts.length>=2){
   const artist=parts.shift().trim(),title=parts.join(' - ').trim();
   return {artist,title};
 }
 return {artist:String(channel||'').replace(/\s+-\s+Topic$/i,'').replace(/VEVO$/i,'').trim(),title:text.trim()};
}
function artistNames(value){
 const stripped=normalize(value).replace(/\b(?:feat|featuring|ft|with)\b.*$/,'');
 return [stripped,...stripped.split(/\s+(?:and|x|vs)\s+/)].filter(Boolean);
}
function exactCandidate(request,candidate){
 const artist=normalize(request.artist),title=coreTitle(request.title);
 const artistOptions=artistNames(candidate.artist);
 const artistOK=artistOptions.includes(artist)||artistNames(request.artist).some(a=>a===normalize(candidate.artist));
 return Boolean(artist&&title&&artistOK&&coreTitle(candidate.title)===title
   &&edition(request.title)===edition(candidate.title));
}
function durationSeconds(iso){
 const m=String(iso||'').match(/^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/);
 return m?Number(m[1]||0)*3600+Number(m[2]||0)*60+Number(m[3]||0):null;
}
function durationOK(expected,found){
 if(!Number.isFinite(expected)||expected<=0)return true;
 return Number.isFinite(found)&&Math.abs(expected-found)<=Math.max(5,Math.round(expected*.03));
}
async function search(request){
 if(!settings.ytKey)throw Error('Add a YouTube API key under YouTube → YouTube Key first.');
 const phrase=request.artist+' '+request.title;
 const data=await ytApi('search',{part:'snippet',type:'video',maxResults:25,
   q:phrase,videoCategoryId:'10',videoEmbeddable:'true'});
 const candidates=(data.items||[]).filter(x=>x.id?.videoId&&x.snippet).map(x=>{
   const info=parseTitle(x.snippet.title,x.snippet.channelTitle);
   return {id:x.id.videoId,artist:info.artist,title:info.title,channel:x.snippet.channelTitle||'',
     rawTitle:x.snippet.title||'',matching:exactCandidate(request,info)};
 });
 const verified=candidates.filter(x=>x.matching);
 if(!verified.length)return {verified:[],review:candidates.slice(0,5)};
 const info=await ytApi('videos',{part:'contentDetails',id:verified.map(x=>x.id).join(',')});
 const byId=new Map((info.items||[]).map(x=>[x.id,durationSeconds(x.contentDetails?.duration)]));
 return {verified:verified.filter(x=>durationOK(request.duration,byId.get(x.id)))
     .map(x=>({...x,duration:byId.get(x.id)})),
    review:candidates.filter(x=>!x.matching).slice(0,5)};
}
function trackLabel(item){return item.title+' — '+item.artist}
function formatDuration(s){return s==null?'Unknown duration':Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
function chooseResult(request,result){
 const approved=result.verified;
 if(!approved.length)return msgView('No Verified Match',
  'Nothing exactly matched '+request.artist+' — '+request.title+
  '. The search results were not downloaded. Check spelling, edition and duration, or try another track.');
 return list('Verified Matches',[
  {label:'Requested',val:request.artist+' — '+request.title},
  ...approved.map(it=>({label:it.title,val:it.artist+' · '+formatDuration(it.duration),
   action:()=>push(list('Confirm Recording',[
    {label:'Imported',val:trackLabel(request)},
    {label:'YouTube Match',val:trackLabel(it)},
    {label:'Duration',val:formatDuration(it.duration)},
    {label:'Play / Save Verified Result',action:()=>{
      const chosen={kind:'yt',id:it.id,title:request.title,artist:request.artist,album:request.album||'Offline Music'};
      playYT([chosen],0);
    }}
   ]))}))
 ]);
}
function startSearch(request){
 const loading=loadingView('Matching Metadata…');push(loading);
 search(request).then(result=>{if(top()===loading)replaceTop(chooseResult(request,result))})
 .catch(e=>{if(top()===loading)replaceTop(msgView('Match Failed',e.message||'Could not search YouTube.'))});
}
function begin(){
 push(inputView('Artist Name','Exact artist from source',artist=>{
  artist=String(artist||'').trim();
  if(!artist)return replaceTop(msgView('Artist Required','Enter the original artist.'));
  replaceTop(inputView('Track Title','Exact title, including version',title=>{
   title=String(title||'').trim();
   if(!title)return replaceTop(msgView('Title Required','Enter the original song title.'));
   replaceTop(inputView('Duration (Optional)','M:SS, seconds, or 0 to skip',raw=>{
    const value=String(raw||'').trim();
    let duration=0;
    if(/^\d+:\d{2}$/.test(value)){
      const [min,sec]=value.split(':').map(Number);
      if(sec>=60)return replaceTop(msgView('Invalid Duration','Seconds must be between 00 and 59.'));
      duration=min*60+sec;
    }else if(/^\d+$/.test(value))duration=Number(value);
    else return replaceTop(msgView('Invalid Duration','Enter M:SS, total seconds, or 0 to skip.'));
    startSearch({artist,title,duration});
   },'0'));
  }));
 }));
}
window.ipodTrackMatch={open:begin,normalize,edition,coreTitle,exactCandidate,durationSeconds,durationOK,parseTitle};
})();
