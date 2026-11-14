// node tests/track-match.cjs
'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const path=require('node:path');
const script=fs.readFileSync(path.resolve(__dirname,'../track-match.js'),'utf8');
const html=fs.readFileSync(path.resolve(__dirname,'../index.html'),'utf8');
new Function(script);
new Function(html.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1]);
const w={ipodTrackMatchBridge:{
 list:(title,items)=>({title,items}),push:()=>{},replaceTop:()=>{},top:()=>null,
 msgView:(title,message)=>({title,message}),loadingView:title=>({title}),
 inputView:(title,prompt,callback)=>({title,prompt,callback}),ytApi:async()=>({items:[]}),
 settings:{ytKey:'test'},playYT:()=>{}
}};
const matcher=new Function('window',script+';return window.ipodTrackMatch')(w);
assert.ok(matcher);
const req={artist:'Frank Ocean',title:'Pink + White'};
assert.equal(matcher.exactCandidate(req,{artist:'Frank Ocean',title:'Pink & White (Official Audio)'}),false);
assert.equal(matcher.exactCandidate(req,{artist:'Frank Ocean',title:'Pink + White (Official Audio)'}),true);
assert.equal(matcher.exactCandidate(req,{artist:'Someone Else',title:'Pink + White'}),false);
assert.equal(matcher.exactCandidate(req,{artist:'Frank Ocean',title:'Pink + White (Live)'}),false);
assert.equal(matcher.exactCandidate({artist:'Frank Ocean',title:'Pink + White (Live)'},{artist:'Frank Ocean',title:'Pink + White (Live)'}),true);
assert.equal(matcher.exactCandidate({artist:'The Weeknd',title:'Wicked Games'},{artist:'The Weeknd',title:'Wicked Games (Remix)'}),false);
assert.equal(matcher.durationSeconds('PT3M42S'),222);
assert.equal(matcher.durationSeconds('PT1H2M3S'),3723);
assert.equal(matcher.durationOK(220,224),true);
assert.equal(matcher.durationOK(220,245),false);
assert.equal(matcher.durationOK(null,245),true);
assert.deepEqual(matcher.parseTitle('Frank Ocean - Pink + White','FrankOceanVEVO'),{artist:'Frank Ocean',title:'Pink + White'});
assert.match(html,/Match Imported Track/);
assert.match(html,/track-match\.js/);
assert.match(html,/ipodTrackMatchBridge/);
console.log('PASS strict YouTube metadata matching, editions, duration, imported song metadata and iPod bridge');
