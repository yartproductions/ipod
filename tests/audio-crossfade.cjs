'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');
const code=html.slice(html.indexOf('const CROSSFADE_OPTIONS='),html.indexOf('function syncMediaPlaybackState'));
const test=new Function(code+`
  const makeDeck=()=>({duration:100,currentTime:0,playbackRate:1,paused:true,
    async play(){this.paused=false},pause(){this.paused=true},removeAttribute(){this.src=''},load(){}});
  const mainDeck=makeDeck(),spareDeck=makeDeck(),ramps=[];
  let audio=mainDeck,qi=0,importedPlayback=null;
  const queue=[{url:'blob:first'},{url:'blob:second'}],settings={crossfade:4,repeat:'Off'};
  function onActiveAudio(){}
  const setSession=()=>{},syncMediaPlaybackState=()=>{},syncMediaPosition=()=>{},render=()=>{};
  const setTimeout=()=>1,clearTimeout=()=>{};
  fadeContext={state:'running',currentTime:10};
  for(const deck of [mainDeck,spareDeck])deckGain.set(deck,{
    cancelScheduledValues(){},setValueAtTime(){},linearRampToValueAtTime(value,end){ramps.push([value,end])}
  });
  return (async()=>{
    mainDeck.paused=false;mainDeck.currentTime=95;
    await maybeCrossfade();
    const before=qi;
    mainDeck.currentTime=96;
    await maybeCrossfade();
    const during=[qi,audio===spareDeck,mainDeck.paused];
    cancelCrossfade();
    return {before,during,ramps,stopped:mainDeck.paused,playing:!spareDeck.paused};
  })();
`);
test().then(result=>{
  assert.deepEqual(result,{before:0,during:[1,true,false],ramps:[[0,14],[1,14]],stopped:true,playing:true});
  console.log('PASS crossfade starts inside the selected window and overlaps both decks');
}).catch(error=>{console.error(error);process.exitCode=1});
