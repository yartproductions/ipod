// Run: node tests/friends.cjs
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.resolve(__dirname,'../index.html'),'utf8');
const friends=fs.readFileSync(path.resolve(__dirname,'../friends.js'),'utf8');
new Function(html.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1]);
new Function(friends);
assert.match(html,/\{label:'Friends',action:/);
assert.match(html,/<script src="\.\/friends\.js" defer><\/script>/);
assert.match(friends,/signInAnonymously/);
assert.doesNotMatch(friends,/signInWithEmailAndPassword|recoveryPhrase|recoveryKey/);
assert.match(friends,/sharing:false/);
assert.match(friends,/seconds>=30/);
assert.match(friends,/\.slice\(0,3\)/);
assert.match(friends,/firebase-firestore-compat/);
const originalFlow=fs.readFileSync(path.resolve(__dirname,'../index.html'),'utf8');
const browsing=originalFlow.slice(originalFlow.indexOf('function renderFlow(v,from)'),originalFlow.indexOf('function flowUpdate(v)'));
assert.doesNotMatch(browsing,/np-lyrics/);
const np=originalFlow.slice(originalFlow.indexOf('function renderNowFlow()'),originalFlow.indexOf('\/\* ---------- Artwork lookup'));
assert.match(np,/np-lyric-lines/);
// Smoke the optional module without loading Firebase or affecting music playback.
let pushed=null,timeHandler=null;
const mockAudio={addEventListener(name,fn){if(name==='timeupdate')timeHandler=fn},paused:true};
const fakeWindow={};
const module=new Function('window','audio','navigator','push','msgView',friends+';return window.ipodFriends;')(
 fakeWindow,mockAudio,{onLine:false},view=>{pushed=view},(title,msg)=>({title,msg}));
assert.equal(typeof module.open,'function');
assert.equal(typeof timeHandler,'function');
module.open();
assert.equal(pushed.title,'Friends Offline');
console.log('PASS Friends integration syntax, no-recovery scope, local playback isolation, privacy defaults and Flow guardrails');
