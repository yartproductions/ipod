'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');
const start=html.indexOf('let importedPlayback=null;');
const end=html.indexOf("audio.addEventListener('timeupdate',prefetchImported)",start);
const {play,prefetch,advance,current,audio,downloads}=new Function(html.slice(start,end)+`
 const downloads=[],songs=[{id:'local',url:'blob:local'}],settings={repeat:'Off'};
 const audio={currentTime:0,duration:200,paused:false,src:'',addEventListener(){}};
 let queue=[],qi=-1,latestPlayRequest=0;
 const dur=()=>audio.duration,curTime=()=>audio.currentTime,seekTo=t=>{audio.currentTime=t};
 const load=()=>{audio.src=queue[qi].url;audio.currentTime=0};
 const top=()=>({type:'now'}),push=()=>{},render=()=>{};
 const enqueueYT=async video=>{
  downloads.push(video.id);
  const song={id:video.id,sourceId:video.id,url:'blob:'+video.id};
  songs.push(song);return song;
 };
 return {play:()=>playImported([{song:songs[0]},{video:{id:'second'}},{video:{id:'third'}}],0),
  prefetch:prefetchImported,advance:()=>advanceImported(1,false),current:()=>queue[qi].id,audio,downloads};
`)();
play();
audio.currentTime=99;
prefetch();
assert.deepEqual(downloads,[]);
audio.currentTime=100;
prefetch();
prefetch();
assert.deepEqual(downloads,['second']);
assert.equal(current(),'local');
advance();
assert.equal(current(),'second');
assert.deepEqual(downloads,['second']);
audio.currentTime=100;
prefetch();
assert.deepEqual(downloads,['second','third']);
console.log('PASS playlist downloads one track ahead at halfway and advances to the saved song');
