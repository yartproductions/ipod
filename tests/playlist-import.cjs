// Run: node tests/playlist-import.cjs
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
const code=fs.readFileSync(path.join(__dirname,'../playlist-import.js'),'utf8');
const matcherCode=fs.readFileSync(path.join(__dirname,'../track-match.js'),'utf8');
new Function(html.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1]);
new Function(code);
let screens=[],calls=[],storage=new Map();
const bridge={
 list:(title,rows)=>({title,rows:typeof rows==='function'?rows():rows}),
 push:v=>screens.push(v),replaceTop:v=>screens[screens.length-1]=v,top:()=>screens.at(-1),
 msgView:(title,message)=>({title,message}),loadingView:title=>({title}),
 inputView:(title,hint,onSubmit)=>({title,hint,onSubmit}),
 settings:{ytKey:'sample'},playYT:()=>{},playList:()=>{},getSongs:()=>[],
 ytApi:async(endpoint)=>{
  calls.push(endpoint);
  if(endpoint==='playlistItems')return {items:[{snippet:{title:'The Weeknd - Wicked Games',videoOwnerChannelTitle:'The Weeknd',resourceId:{videoId:'AAAAAAAAAAA'}}}]};
  if(endpoint==='playlists')return {items:[{snippet:{title:'Sample Playlist'}}]};
  if(endpoint==='search')return {items:[{id:{videoId:'AAAAAAAAAAA'},snippet:{title:'The Weeknd - Wicked Games',channelTitle:'The Weeknd'}}]};
  if(endpoint==='videos')return {items:[{id:'AAAAAAAAAAA',contentDetails:{duration:'PT5M27S'}}]};
  throw Error(endpoint);
 }
};
const window={ipodTrackMatchBridge:bridge,ipodPlaylistImportBridge:bridge};
new Function('window',matcherCode)(window);
const localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)};
const document={createElement:()=>({style:{},addEventListener(){},click(){}}),body:{appendChild(){}}};
const importer=new Function('window','localStorage','document',code+';return window.ipodPlaylistImport')(window,localStorage,document);
assert.equal(importer.detect('https://open.qobuz.com/playlist/65537360').id,'65537360');
assert.equal(importer.detect('https://music.youtube.com/playlist?list=PLabcdef12345').provider,'youtube');
assert.equal(importer.detect('https://fakeqobuz.com/playlist/123'),null);
const csv=importer.parseFile('Track,Artist,Duration\n"Wicked Games","The Weeknd",5:27','music.csv');
assert.equal(csv[0].duration,327);
const qobuz=importer.parseFile(JSON.stringify({tracks:{items:[{track:{title:'Wicked Games',performer:{name:'The Weeknd'},album:{title:'Trilogy'},duration:327}}]}}),'playlist.json');
assert.equal(qobuz[0].album,'Trilogy');
(async()=>{
 const found=await importer.youtubeMatch(qobuz[0]);assert.equal(found.youtubeId,'AAAAAAAAAAA');
 const youtube=await importer.youtubeTracks('PLabcdef12345');assert.equal(youtube.tracks.length,1);
 importer.open();assert.equal(screens.at(-1).title,'Import Playlist');
 console.log('PASS Qobuz links, exported metadata, CSV, YouTube playlists, exact matching and menu isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
