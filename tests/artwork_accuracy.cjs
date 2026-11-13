'use strict';
const fs=require('node:fs');
const assert=require('node:assert/strict');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
function section(start,end){
 const a=source.indexOf(start),b=source.indexOf(end,a);
 assert(a>=0&&b>a,'Missing code section '+start);
 return source.slice(a,b);
}
function test(label,fn){Promise.resolve().then(fn).then(()=>console.log('PASS '+label),e=>{console.error('FAIL '+label,e);process.exitCode=1})}
const parse=new Function('decodeHTML',section('function cleanMusicVideoText','function recommendationAddPage')+'return recommendationTrackInfo;')(x=>x);
const score=new Function(section('function artworkNormalize','function artworkCacheKey')+'return artworkScore;')();
const yt=[
 ['Frank Ocean - Pink + White (Official Video)','FrankOceanVEVO','Frank Ocean','Pink + White'],
 ['SZA - Snooze [Official Music Video]','SZA - Topic','SZA','Snooze'],
 ['The Weeknd - Call Out My Name (Official Audio)','The WeekndVEVO','The Weeknd','Call Out My Name'],
 ['Coldplay - Yellow (Live)','Coldplay','Coldplay','Yellow (Live)'],
 ['Snooze (Official Music Video)','SZA - Topic','SZA','Snooze']
];
for(const [raw,channel,artist,title] of yt)test('Parse '+raw,()=>{
 const parsed=parse({snippet:{title:raw,channelTitle:channel}});
 assert.equal(parsed.artist,artist);
 assert.equal(parsed.title,title);
});
test('Correct match succeeds',()=>assert.equal(score({artist:'SZA',title:'Snooze'},{artistName:'SZA',trackName:'Snooze'}),1));
test('Live mismatch rejected',()=>assert.equal(score({artist:'Coldplay',title:'Yellow'},{artistName:'Coldplay',trackName:'Yellow (Live)'}),0));
test('Different title rejected',()=>assert.equal(score({artist:'Frank Ocean',title:'Pink + White'},{artistName:'Frank Ocean',trackName:'Pink Matter'}),0));
test('Different artist rejected',()=>assert.equal(score({artist:'SZA',title:'Snooze'},{artistName:'Another Artist',trackName:'Snooze'}),0));
test('Album Flow renders without Now Playing lyrics reference',()=>{
 const body={innerHTML:''},nodes=new Map(),dom={querySelectorAll(){return []}};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:''});return nodes.get(id)};
 const renderFlow=new Function('body','document','$','requestAnimationFrame','recommendationArtPreview','esc',
 section('const FLOW_WIN=12;','/* ---------- Flow Now Playing')+'return renderFlow;')(body,dom,node,fn=>fn(),()=>{},String);
 renderFlow({type:'flow',sel:0,albums:[{art:'cover',album:'Test Album',artist:'Test Artist'}]});
 assert.match(body.innerHTML,/id="flow"/);
 assert.doesNotMatch(body.innerHTML,/np-lyric-lines/);
 assert.equal(node('#fal').textContent,'Test Album');
});
test('Flow Now Playing still renders synchronized lyrics',()=>{
 const body={innerHTML:''},dom={querySelectorAll(){return []}};
 const node=()=>({classList:{remove(){}},style:{},dataset:{}});
 let lyrics=false;
 const render=new Function('cur','qi','queue','artFor','esc','body','document','requestAnimationFrame','$','tick','ensureNowLyrics','nowLyricsHTML','scrub',
 section('let flowNpQi=null;','/* ---------- Artwork lookup: MusicBrainz')+'return renderNowFlow;')(
 ()=>({id:'one',title:'Yellow',artist:'Coldplay',album:'Parachutes'}),0,
 [{id:'one',title:'Yellow',artist:'Coldplay',album:'Parachutes'}],()=> 'cover',String,
 body,dom,fn=>fn(),node,()=>{},()=>{lyrics=true},()=> 'Lyrics',false);
 render();
 assert.match(body.innerHTML,/np-lyric-lines/);assert(lyrics);
});
test('Strict mode rejects thumbnails and allows matched art',()=>{
 const gen=()=> 'generated';
 const make=settings=>new Function('settings','genArt',
 section('const isYoutubeThumbnail','// Average colour of the artwork')+'return artFor;')(settings,gen);
 const song={title:'Yellow',artist:'Coldplay',album:'Parachutes',artUrl:'https://i.ytimg.com/vi/abc/hqdefault.jpg'};
 assert.equal(make({artworkMode:'Strict'})(song),'generated');
 assert.equal(make({artworkMode:'Thumbnails'})(song),song.artUrl);
 song.artUrl='https://is1-ssl.mzstatic.com/image/abc';
 assert.equal(make({artworkMode:'Strict'})(song),song.artUrl);
});
test('Artwork is retained with the downloaded song',()=>{
 assert.match(source,/await dbPut\(rec\);const song=hydrate\(rec\)/);
 assert.match(source,/repairSongArtwork\(song/);
 assert.match(source,/await dbPut\(songRecord\(t\)\)/);
});
