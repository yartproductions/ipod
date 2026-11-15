'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');
const code=html.slice(html.indexOf('const CROSSFADE_OPTIONS='),html.indexOf('const playbackLog='));
const test=new Function('assert',code+`
  const makeDeck=()=>({duration:100,currentTime:0,playbackRate:1,paused:true,
    async play(){this.paused=false},pause(){this.paused=true},removeAttribute(){this.src=''},load(){}});
  const mainDeck=makeDeck(),spareDeck=makeDeck(),backgroundDeck=makeDeck(),ramps=[];
  const document={hidden:false};
  const resumeAudio=()=>audio.play();
  let audio=mainDeck,qi=0,importedPlayback=null;
  const queue=[{url:'blob:first'},{url:'blob:second'}],settings={crossfade:4,repeat:'Off'};
  function onActiveAudio(){}
  function notePlayback(){}
  const top=()=>null;
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
    settings.carPlayMode=true;
    await maybeCrossfade();
    assert.equal(qi,0);
    assert.equal(spareDeck.paused,true);
    settings.carPlayMode=false;
    await maybeCrossfade();
    const during=[qi,audio===spareDeck,mainDeck.paused];
    spareDeck.currentTime=2;
    assert.equal(backgroundDeck.src,'blob:second');
    document.hidden=true;
    useDirectAudio();
    document.hidden=false;
    setCarPlayRoute(true);
    assert.equal(crossfadeEnabled(),false);
    assert.equal(document.hidden,false);
    await maybeCrossfade();
    return {before,during,ramps,stopped:mainDeck.paused&&spareDeck.paused,
      playing:audio===backgroundDeck&&!backgroundDeck.paused,position:audio.currentTime};
  })();
`);
test(assert).then(result=>{
  assert.deepEqual(result,{before:0,during:[1,true,false],ramps:[[0,14],[1,14]],stopped:true,playing:true,position:2});
  console.log('PASS crossfade starts inside the selected window and preserves position when the screen locks');
}).catch(error=>{console.error(error);process.exitCode=1});
