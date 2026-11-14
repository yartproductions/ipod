// Run: node tests/spotify-import.cjs
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const id='3cEYpjA9oz9GiPac4AsH4n';
const base='https://yartproductions.github.io/ipod/';
const path='/v1/playlists/'+id;
function storage(){
 const data=new Map();
 return {getItem:key=>data.get(key),setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};
}
const location={href:base,assign(url){this.href=url},origin:new URL(base).origin,pathname:new URL(base).pathname};
const requests=[];
const item={type:'track',name:'Wicked Games',artists:[{name:'The Weeknd'}],album:{name:'Trilogy'},
 duration_ms:327000,external_ids:{isrc:'USABC1234567'}};
let next='https://api.spotify.com'+path+'/items?limit=50&offset=50';
const window={};
vm.runInNewContext(fs.readFileSync(require.resolve('../spotify-import.js'),'utf8'),{
 window,location,history:{replaceState(_state,_title,url){location.href=url.href}},
 URL,URLSearchParams,Uint8Array,TextEncoder,btoa,crypto:webcrypto,
 localStorage:storage(),sessionStorage:storage(),
 fetch:async (url,options)=>{
  url=String(url);
  requests.push({url,options});
  const result=url.includes('/api/token')?{access_token:'test-token',expires_in:3600}:
   url.endsWith('fields=name')?{name:'Spotify Test'}:
   url.includes('offset=50')?{items:[{track:item}],next:null}:
   {items:[{item},{item:{type:'episode'}},{item,is_local:true}],next};
  return {ok:true,json:async()=>result};
 }
});
const spotify=window.ipodSpotifyImport;
(async()=>{
 assert.equal(await spotify.playlist(id),null);
 spotify.configure('a'.repeat(32));
 await spotify.connect(id);
 const auth=new URL(location.href);
 assert.equal(auth.origin,'https://accounts.spotify.com');
 assert.equal(auth.searchParams.get('redirect_uri'),base);
 assert.equal(auth.searchParams.get('code_challenge_method'),'S256');
 location.href=base+'?code=mock&state=wrong';
 await assert.rejects(spotify.callback(),/expired/);
 assert.equal(requests.length,0);
 await spotify.connect(id);
 const state=new URL(location.href).searchParams.get('state');
 location.href=base+'?code=mock&state='+state;
 assert.equal(await spotify.callback(),id);
 assert.equal(location.href,base);
 const playlist=await spotify.playlist(id);
 assert.equal(playlist.source,'https://open.spotify.com/playlist/'+id);
 assert.equal(playlist.tracks.length,2);
 assert.equal(playlist.tracks[0].duration,327);
 assert.equal(playlist.tracks[1].isrc,'USABC1234567');
 next='https://example.org'+path+'/items';
 await assert.rejects(spotify.playlist(id),/invalid playlist page/);
 assert(!requests.some(request=>request.url.includes('example.org')));
 console.log('PASS Spotify PKCE callback, paging, track metadata, and next-page URL validation');
})().catch(error=>{console.error(error);process.exitCode=1});
