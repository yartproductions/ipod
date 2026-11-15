'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');
const source=html.slice(html.indexOf('let centerPress=null'),html.indexOf("addEventListener('keydown',e=>{",html.indexOf('let centerPress=null')));
const run=new Function('assert',`
 const events=new Map(),timers=new Map(),frames=new Map(),pulses=[],selections=[];
 let now=0,id=0,sheet=null,holdOn=false,saved=0;
 const node=()=>({textContent:'',classList:{add(){},remove(){}},style:{setProperty(){},removeProperty(){}}});
 const center={...node(),addEventListener:(event,handler)=>events.set(event,handler),
   getBoundingClientRect:()=>({left:10,right:100,top:10,bottom:100})};
 const captions=new Map(['i','b','span'].map(tag=>[tag,node()]));
 const hub={...node(),querySelector:tag=>captions.get(tag)};
 const $=()=>hub;
 const document={addEventListener(){}};
 const performance={now:()=>now};
 const setTimeout=(fn,delay)=>{timers.set(++id,{fn,at:now+delay});return id};
 const clearTimeout=id=>timers.delete(id);
 const requestAnimationFrame=fn=>{frames.set(++id,fn);return id};
 const cancelAnimationFrame=id=>frames.delete(id);
 const advance=target=>{
   now=target;
   for(const [id,timer] of timers)if(timer.at<=now){timers.delete(id);timer.fn()}
   for(const [id,fn] of [...frames]){frames.delete(id);fn(now)}
 };
 const song={id:'song'},queue=[song],view={type:'now'};
 const cur=()=>song,top=()=>view,highlightedTrack=()=>null;
 const wake=()=>{},radialHub=()=>{},render=()=>{},setHdrTask=()=>{};
 const openQueueRing=()=>{sheet={kind:'queue-ring'}},closeSheet=()=>{sheet=null};
 const press=button=>selections.push(button),triggerHaptic=kind=>pulses.push(kind);
 const importedTrackSong=()=>song,songRecord=s=>s;
 const dbPut=async()=>{saved++};
 const touch=(type,x=40)=>events.get(type)({
  changedTouches:[{identifier:1,clientX:x,clientY:40}],preventDefault(){},stopPropagation(){}
 });
`+source+`
 return (async()=>{
   touch('touchstart');
   advance(550);
   assert.equal(sheet.kind,'queue-ring');
   assert.equal(captions.get('b').textContent,'1.0s');
   assert.deepEqual(pulses,['confirm']);
   touch('touchend');
   assert.equal(saved,0);
   touch('touchstart');
   advance(600);
   touch('touchend');
   assert.deepEqual(selections,['select']);
   touch('touchstart');
   touch('touchmove',65);
   advance(1150);
   advance(2150);
   await Promise.resolve();
   assert.equal(saved,1);
   assert.equal(song.favorite,true);
   assert.equal(sheet,null);
   assert.deepEqual(pulses,['confirm','confirm','confirm']);
 })();
`);
run(assert).then(()=>console.log('PASS Center touch opens the queue dial and continued hold saves a favorite'))
 .catch(error=>{console.error(error);process.exitCode=1});
