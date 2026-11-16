'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync(require.resolve('../stremio.js'),'utf8');new vm.Script(code);
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');for(const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
let views=[],calls=[],store=new Map(),fail=false,paused=0,restored=0;
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.events={};this.currentTime=0;this.duration=600;this.value='';this.paused=true;this.classList={add(){},remove(){}}}
 setAttribute(){} removeAttribute(name){delete this[name]} addEventListener(name,fn){this.events[name]=fn} removeEventListener(){}
 append(...items){this.children.push(...items)} showModal(){} focus(){} remove(){} load(){} pause(){this.paused=true;this.events.pause?.()} play(){this.paused=false;return Promise.resolve()}
}
const screen=new Element('screen'),menu=new Element('menu');screen.append(menu);
const document={body:new Element('body'),createElement:tag=>new Element(tag),querySelector:selector=>selector==='#screen'?screen:null,addEventListener(){},removeEventListener(){}};
const bridge={list:(title,items,extra={})=>({title,items,...extra}),push:v=>views.push(v),pop:()=>views.pop(),replaceTop:v=>views[views.length-1]=v,top:()=>views.at(-1),msgView:(title,msg)=>({title,msg}),loadingView:title=>({title}),inputView:(title,ph,onSubmit,value='')=>({title,ph,onSubmit,value}),pauseMusic:()=>paused++,restoreMusicControls:()=>restored++};
const window={ipodVideoBridge:bridge,addEventListener(){},removeEventListener(){}};
const localStorage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)};
const descriptor={transportUrl:'https://torrentio.strem.fun/realdebrid=secret/manifest.json',manifest:{id:'com.stremio.torrentio',name:'Torrentio',resources:[{name:'stream',types:['series','movie'],idPrefixes:['tt']}],types:['movie','series']}};
const webstreamr={transportUrl:'https://webstreamr.example.com/manifest.json',manifest:{id:'webstreamr',name:'WebStreamr',resources:['stream'],types:['movie','series'],idPrefixes:['tt']}};
const absolute={transportUrl:'https://absolute.example.com/manifest.json',manifest:{id:'absolute.cinema',name:'Absolute Cinema',resources:[{name:'stream',types:['movie']}],types:['movie'],idPrefixes:['tt']}};
const catalogOnly={transportUrl:'https://catalog.example.com/manifest.json',manifest:{id:'catalog.only',name:'Catalog Only',resources:['catalog'],types:['movie']}};
let respond=async(url,opts)=>{
 calls.push({url,opts});if(fail)throw Error('https://secret-in-error/realdebrid=key');
 if(url.endsWith('/api/login'))return {result:{authKey:'session-secret'}};
 if(url.endsWith('/api/addonCollectionGet'))return {result:{addons:[descriptor,webstreamr,absolute,catalogOnly]}};
 if(url.includes('/catalog/'))return {metas:[{id:'tt123',name:'Sample Show',poster:'https://images.example.com/poster.jpg'}]};
 if(url.includes('/meta/'))return {meta:{id:'tt123',name:'Sample Show',description:'Description',videos:[{id:'tt123:2:1',season:2,episode:1,title:'Next'},{id:'tt123:1:1',season:1,episode:1,title:'Pilot'}]}};
 if(url.includes('webstreamr.example.com/stream/'))return {streams:[{name:'WebStreamr 720p',url:'https://web.example.com/video.m3u8'}]};
 if(url.includes('absolute.example.com/stream/'))return {streams:[{name:'Absolute Cinema',url:'https://absolute.example.com/video.mp4'}]};
 if(url.includes('/stream/'))return {streams:[{name:'P2P',infoHash:'abc'},{name:'Unsafe',url:'http://example.com/a.mp4'},{name:'Headers',url:'https://example.com/a.mp4',behaviorHints:{proxyHeaders:{}}},{name:'Torrentio RD',url:'https://rd.example.com/token/video.mp4'}]};
 if(url.endsWith('/api/logout'))return {result:{}};
 throw Error(url);
};
const fetch=async(url,opts)=>({ok:true,status:200,json:()=>respond(url,opts)});
const api=new Function('window','document','localStorage','navigator','fetch','AbortSignal',code+';return window.ipodVideos')(window,document,localStorage,{},fetch,AbortSignal);
const rows=()=>typeof views.at(-1).items==='function'?views.at(-1).items():views.at(-1).items;
const choose=label=>{const row=rows().find(x=>x.label===label);assert(row,'missing '+label);return row.action()};
(async()=>{
 api.settings();choose('Connect Account');views.at(-1).onSubmit('me@example.com');assert.equal(views.at(-1).inputType,'password');
 await views.at(-1).onSubmit('password-secret');assert.equal(rows()[0].label,'Account Connected');assert.equal(rows()[1].label,'Video Add-ons');assert.equal(rows()[1].val,'3');assert.equal(store.size,0,'no login or provider credentials saved');
 api.open();await choose('Shows');assert.equal(views.at(-1).type,'covers');await choose('Sample Show');assert.equal(rows()[0].label,'Season 1');choose('Season 1');await choose('1. Pilot');assert.equal(rows().length,2,'direct HTTPS sources from every compatible add-on');assert.equal(rows().find(x=>x.label==='WebStreamr 720p').sub,'WebStreamr');choose('Torrentio RD');choose('Play');assert.equal(paused,1);assert(api.playing);
 const dialog=screen.children.at(-1),video=dialog.children[1];assert.equal(dialog.tag,'section');assert.equal(document.body.children.length,0);assert.equal(menu.inert,true);
 api.control('play');assert(video.paused);api.control('select');assert(!video.paused);
 api.control('prev');assert.equal(video.currentTime,0);api.control('next');assert.equal(video.currentTime,10);
 video.currentTime=599;api.control('next');assert.equal(video.currentTime,600);
 video.currentTime=90;video.events.timeupdate();
 assert(![...store.values()].join().includes('secret'));assert(![...store.values()].join().includes('https://'));
 api.control('menu');assert.equal(menu.inert,undefined);assert(!api.playing);assert.equal(restored,1);
 api.open();choose('Continue Watching');assert.equal(rows().length,1);await rows()[0].action();choose('Torrentio RD');choose('Play');
 const resumed=screen.children.at(-1).children[1];resumed.events.loadedmetadata();assert.equal(resumed.currentTime,90);resumed.events.ended();api.close();
 api.open();choose('Continue Watching');assert.equal(rows().length,0,'finished titles are removed');
 fail=true;api.open();await choose('Movies');assert(!views.at(-1).msg.includes('secret'),'network errors never expose source URLs');fail=false;
 api.settings();choose('Disconnect');assert.equal(rows()[0].label,'Connect Account');
 assert(calls.some(c=>c.url.includes('/stream/series/tt123%3A1%3A1.json')));
 assert(calls.some(c=>c.url.includes('webstreamr.example.com/stream/series/tt123%3A1%3A1.json')));
 assert(!calls.some(c=>c.url.includes('absolute.example.com/stream/series/')),'movie-only add-ons are not queried for shows');
 assert(!calls.some(c=>c.url.includes('catalog.example.com')),'non-stream add-ons are ignored');
 assert(calls.every(c=>c.opts.credentials==='omit'&&c.opts.referrerPolicy==='no-referrer'));
 assert(calls.find(c=>c.url.includes('/catalog/')).opts.redirect==='follow');
 assert(calls.find(c=>c.url.endsWith('/api/login')).opts.redirect==='error');
 const login=JSON.parse(calls.find(c=>c.url.endsWith('/api/login')).opts.body);assert.equal(login.password,'password-secret');
 assert.equal(views.some(v=>v.value==='password-secret'),false);
 console.log('PASS Stremio login, add-on retrieval, catalog, ordered seasons, HTTPS filtering, playback, progress/resume/completion, credential handling, safe errors and disconnect');
})().catch(e=>{console.error(e);process.exitCode=1});
