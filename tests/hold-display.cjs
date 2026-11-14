'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');
let visibility='visible',requests=0,releases=0,finishRequest;
const timers=new Map(),classes=new Set();
const node={classList:{toggle(){},add:name=>classes.add(name),remove:name=>classes.delete(name)},addEventListener(){}};
const section=html.slice(html.indexOf('// ----- Hold switch'),html.indexOf('// ----- Fast scroll'));
const lock=()=>({released:false,async release(){this.released=true;releases++}});
const {setHold,wake,syncHoldDisplayLock}=new Function('$','screenEl','document','navigator','settings','top','setTimeout','clearTimeout',
 section+'return {setHold,wake,syncHoldDisplayLock};')(
 ()=>node,node,{get visibilityState(){return visibility},addEventListener(){}},
 {wakeLock:{request:()=>{requests++;return new Promise(resolve=>{finishRequest=()=>resolve(lock())})}}},
 {backlight:'20 sec'},()=>({}), (fn,delay)=>{const id=Symbol();timers.set(id,{fn,delay});return id},id=>timers.delete(id));
(async()=>{
 const backlight=()=>[...timers.values()].find(timer=>timer.delay===20000);
 wake();
 assert(backlight());
 backlight().fn();
 setHold(true);
 assert(!classes.has('dim'));
 assert(!backlight());
 assert.equal(requests,1);
 finishRequest();
 await Promise.resolve();
 visibility='hidden';
 await syncHoldDisplayLock();
 assert.equal(releases,1);
 visibility='visible';
 const request=syncHoldDisplayLock();
 assert.equal(requests,2);
 setHold(false);
 assert(backlight());
 finishRequest();
 await request;
 assert.equal(releases,2);
 backlight().fn();
 assert(classes.has('dim'));
 console.log('PASS Hold cancels dimming and manages the display wake lock');
})().catch(error=>{console.error(error);process.exitCode=1});
