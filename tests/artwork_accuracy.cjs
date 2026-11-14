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
 const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',classList:{remove(){}}});return nodes.get(id)};
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
// --- Real iTunes result shapes (captured Nov 2026) ---
const best=new Function('known',section('function artworkNormalize','function artworkCacheKey')+section('function itunesBest','async function artworkFromITunes')+'return itunesBest;')(x=>!!x&&!/^unknown/i.test(x));
const R=(artistName,trackName,collectionName,extra={})=>({kind:'song',artworkUrl100:'https://x/'+collectionName+'/100x100bb.jpg',artistName,trackName,collectionName,...extra});
test('Collaboration credit still matches the primary artist',()=>{
 const b=best({artist:'Daft Punk',title:'Get Lucky'},[R('Daft Punk','Get Lucky (feat. Pharrell Williams & Nile Rodgers) [Daft Punk Remix]','Remix'),R('Daft Punk, Pharrell Williams & Nile Rodgers','Get Lucky','Random Access Memories',{releaseDate:'2013-05-17'})]);
 assert.equal(b&&b.item.collectionName,'Random Access Memories');
});
test('"A x B" YouTube artist matches the primary credit',()=>assert.equal(score({artist:'SZA x Travis Scott',title:'Open Arms'},{artistName:'SZA',trackName:'Open Arms (feat. Travis Scott)'}),1));
test('Covers and tributes by other artists are rejected',()=>assert.equal(best({artist:'Frank Ocean',title:'Pink + White'},[R('Vitamin String Quartet','Pink + White','VSQ Performs Frank Ocean')]),null));
test('Featured-artist suffix on the store title is ignored',()=>assert.equal(score({artist:'Drake',title:'One Dance'},{artistName:'Drake',trackName:'One Dance (feat. Wizkid & Kyla)'}),1));
test('Original album beats singles/live/remix versions',()=>{
 const b=best({artist:'The Weeknd',title:'Blinding Lights'},[R('The Weeknd & ROSALÍA','Blinding Lights (Remix)','Blinding Lights (Remix) - Single'),R('The Weeknd','Blinding Lights (Live)','Live At SoFi Stadium'),R('The Weeknd','Blinding Lights','After Hours (Deluxe)',{releaseDate:'2020-03-23'}),R('The Weeknd','Blinding Lights','After Hours',{releaseDate:'2020-03-20'})]);
 assert.equal(b.item.collectionName,'After Hours');
});
test('Song tagged with its album prefers that album',()=>{
 const b=best({artist:'SZA',title:'Snooze',album:'SOS Deluxe: LANA'},[R('SZA','Snooze','SOS',{releaseDate:'2022-12-09'}),R('SZA','Snooze','SOS Deluxe: LANA',{releaseDate:'2024-12-20'})]);
 assert.equal(b.item.collectionName,'SOS Deluxe: LANA');
});
test('Album tag that the store doesn’t list still gets the original cover',()=>{
 const b=best({artist:'Kendrick Lamar',title:'Not Like Us',album:'Hits 2024'},[R('Kendrick Lamar','Not Like Us','Not Like Us - Single')]);
 assert.equal(b&&b.item.collectionName,'Not Like Us - Single');
});
test('YouTube "(Lyrics)" / "(Explicit)" tags are cleaned from titles',()=>{
 const p=parse({snippet:{title:'Sabrina Carpenter - Espresso (Lyrics)',channelTitle:'7clouds'}});
 assert.equal(p.title,'Espresso');
 assert.equal(parse({snippet:{title:'Kendrick Lamar - Not Like Us (Explicit)',channelTitle:'x'}}).title,'Not Like Us');
});
test('Studio album preferred over its single and deluxe re-issue',()=>{
 const b=best({artist:'SZA',title:'Snooze'},[R('SZA','Snooze','SOS',{releaseDate:'2022-12-09',trackCount:23}),R('SZA','Snooze','SOS Deluxe: LANA',{releaseDate:'2022-12-08',trackCount:23}),R('SZA','Snooze','Snooze - Single',{releaseDate:'2022-12-08',trackCount:4})]);
 assert.equal(b.item.collectionName,'SOS');
});

test('Album artwork reuse preserves release editions and other artists',()=>{
 const {key,reusable}=new Function('known','isYoutubeThumbnail',
  section('function albumArtworkKey','async function saveArtwork')+'return {key:albumArtworkKey,reusable:reusableAlbumCover};')(
   t=>!!t&&!/^unknown (album|artist)$/i.test(t),()=>false);
 const studio={id:'a',album:'Amber Days',artist:'Fixture Artist',artUrl:'https://example.com/cover',artSource:'itunes',artworkAlbum:'Amber Days'};
 assert.equal(key(studio),key({...studio,album:' amber days ',artist:'fixture artist'}));
 assert.notEqual(key(studio),key({...studio,album:'Amber Days (Deluxe)'}));
 assert.notEqual(key(studio),key({...studio,artist:'Other Artist'}));
 assert.equal(key({...studio,album:'Offline Music'}),'');
 assert.equal(reusable(studio,{id:'b'}),true);
 assert.equal(reusable({...studio,artworkAlbum:'Amber Days (Deluxe)'},{id:'b'}),false);
});

test('Concurrent tracks share a verified album lookup and reuse its cached result',async()=>{
 const saved={};
 let searches=0;
 const resolveAlbum=new Function('albumArtworkKey','artSaved','artworkStore','fetchCover',
  section('const albumArtworkPending=new Map();','/* ---------- Cover chooser')+'return resolveAlbumArtwork;')(
   song=>song.album,saved,(key,match)=>{saved[key]=match},async()=>null);
 const resolve=async()=>{searches++;return {match:{album:'Amber Days',url:'https://example.com/art'},blob:{}}};
 const album={album:'Amber Days'};
 const [a,b]=await Promise.all([resolveAlbum(album,resolve,false),resolveAlbum(album,resolve,false)]);
 assert.equal(a,b);
 assert.equal(searches,1);
 assert.equal((await resolveAlbum(album,resolve,false)).match.url,a.match.url);
 assert.equal(searches,1);
 const deluxe={album:'Amber Days (Deluxe)'};
 await Promise.all([resolveAlbum(deluxe,resolve,false),resolveAlbum(deluxe,resolve,false)]);
 assert.equal(searches,3);
 assert.equal(saved['album:Amber Days (Deluxe)'],undefined);
});

test('Refresh All searches each verified edition once per run',async()=>{
 const refresh=new Function('albumArtworkKey',
  section('async function refreshAlbumArtwork','/* ---------- Cover chooser')+'return refreshAlbumArtwork;')(s=>s.album);
 const run=new Map();
 const original={album:'Album'},deluxe={album:'Album (Deluxe)'};
 const searches=[];
 const lookup=album=>async()=>{searches.push(album);return {match:{album,url:'https://example.com/cover'},blob:{}}};
 const first=await refresh(original,lookup(original.album),run);
 assert.equal(await refresh(original,lookup(original.album),run),first);
 await refresh(deluxe,lookup(original.album),run);
 assert(!run.has(deluxe.album));
 await refresh(deluxe,lookup(deluxe.album),run);
 await refresh(deluxe,lookup(deluxe.album),run);
 await refresh(original,lookup(original.album),new Map());
 assert.deepEqual(searches,['Album','Album','Album (Deluxe)','Album']);
});
