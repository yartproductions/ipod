/* Spotify authorization and playlist metadata for the browser importer. */
(function(){
'use strict';
const ACCOUNTS='https://accounts.spotify.com';
const API='https://api.spotify.com';
const CLIENT='ipod.spotify.clientId',SESSION='ipod.spotify.session',PENDING='ipod.spotify.pending';
const redirectUri=()=>location.origin+location.pathname;
const read=key=>JSON.parse(sessionStorage.getItem(key)||'null');
const store=(key,value)=>sessionStorage.setItem(key,JSON.stringify(value));
const clientId=()=>localStorage.getItem(CLIENT)||'';
const configured=()=>/^[0-9a-f]{32}$/i.test(clientId());
function configure(value){
 const id=value.trim();
 if(!/^[0-9a-f]{32}$/i.test(id))throw Error('Enter the Client ID from your Spotify Developer Dashboard.');
 if(id!==clientId())sessionStorage.removeItem(SESSION);
 localStorage.setItem(CLIENT,id);
}
function encode(bytes){
 return btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
const random=()=>encode(crypto.getRandomValues(new Uint8Array(32)));
async function connect(id){
 if(!configured())throw Error('Set your Spotify Client ID first.');
 const verifier=random(),state=random();
 const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier));
 store(PENDING,{id,verifier,state,clientId:clientId(),createdAt:Date.now()});
 const query=new URLSearchParams({client_id:clientId(),response_type:'code',redirect_uri:redirectUri(),
  scope:'playlist-read-private playlist-read-collaborative',state,code_challenge_method:'S256',
  code_challenge:encode(new Uint8Array(hash))});
 location.assign(ACCOUNTS+'/authorize?'+query);
}
async function tokenRequest(values,refreshToken=''){
 const response=await fetch(ACCOUNTS+'/api/token',{method:'POST',body:new URLSearchParams(values)});
 if(!response.ok){
  if(response.status===400||response.status===401)sessionStorage.removeItem(SESSION);
  throw Error('Spotify could not authorize this session. Check your app settings and connect again.');
 }
 const data=await response.json();
 if(!data.access_token)throw Error('Spotify did not return an access token.');
 const session={accessToken:data.access_token,refreshToken:data.refresh_token||refreshToken,
  expiresAt:Date.now()+Number(data.expires_in)*1000};
 store(SESSION,session);
 return session.accessToken;
}
function callback(){
 const url=new URL(location.href),params=url.searchParams;
 if(!params.has('state')||(!params.has('code')&&!params.has('error')))return null;
 const query=new URLSearchParams(params);
 const pending=read(PENDING);
 sessionStorage.removeItem(PENDING);
 for(const key of ['code','state','error','error_description'])params.delete(key);
 history.replaceState(history.state,'',url);
 return finish(query,pending);
}
async function finish(query,pending){
 if(!pending||query.get('state')!==pending.state||clientId()!==pending.clientId||
  Date.now()-pending.createdAt>15*60*1000)throw Error('Spotify sign-in expired. Paste the playlist link again.');
 if(query.has('error'))throw Error('Spotify access was declined. Paste the playlist link to try again.');
 await tokenRequest({grant_type:'authorization_code',code:query.get('code'),redirect_uri:redirectUri(),
  client_id:pending.clientId,code_verifier:pending.verifier});
 return pending.id;
}
async function accessToken(){
 const session=read(SESSION);
 if(!session)return '';
 if(session.expiresAt>Date.now()+30000)return session.accessToken;
 if(!session.refreshToken)return '';
 return tokenRequest({grant_type:'refresh_token',refresh_token:session.refreshToken,client_id:clientId()},session.refreshToken);
}
async function playlist(id){
 if(!/^[a-zA-Z0-9]{22}$/.test(id))throw Error('Invalid Spotify playlist ID.');
 const token=await accessToken();
 if(!token)return null;
 const path='/v1/playlists/'+id;
 const request=async url=>{
  const response=await fetch(url,{headers:{Authorization:'Bearer '+token},redirect:'error'});
  if(response.status===401){sessionStorage.removeItem(SESSION);return null}
  if(response.status===403)throw Error('Spotify denied access. Use a playlist you own or collaborate on and check your Spotify app access.');
  if(response.status===429)throw Error('Spotify is rate-limiting requests. Wait a minute and try again.');
  if(!response.ok)throw Error('Spotify could not read this playlist (HTTP '+response.status+').');
  return response.json();
 };
 const details=await request(API+path+'?fields=name');
 if(!details)return null;
 const tracks=[],seen=new Set();
 let next=API+path+'/items?limit=50';
 while(next){
  const url=new URL(next);
  if(url.origin!==API||url.pathname!==path+'/items'||seen.has(url.href))throw Error('Spotify returned an invalid playlist page.');
  seen.add(url.href);
  const page=await request(url);
  if(!page)return null;
  if(!Array.isArray(page.items))throw Error('Spotify did not return playlist tracks.');
  for(const row of page.items){
   const item=row?.item??row?.track;
   if(item?.type!=='track'||row.is_local||item.is_local||!item.name||!item.artists?.length)continue;
   tracks.push({title:item.name,artist:item.artists.map(artist=>artist.name).join(', '),
    album:item.album?.name,duration:Math.round((item.duration_ms||0)/1000),isrc:item.external_ids?.isrc});
  }
  next=page.next;
 }
 if(!tracks.length)throw Error('This Spotify playlist has no importable songs.');
 return {name:details.name||'Spotify Playlist',provider:'Spotify',source:'https://open.spotify.com/playlist/'+id,tracks};
}
window.ipodSpotifyImport={configured,configure,connect,callback,playlist,redirectUri};
})();
