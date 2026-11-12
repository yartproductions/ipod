const ORIGIN='https://yartproductions.github.io';
const UPSTREAM='https://ytmp3.ge/api/convert';
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json; charset=utf-8'}});
const cors=()=>({'Access-Control-Allow-Origin':ORIGIN,'Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type','Vary':'Origin','Cache-Control':'no-store'});
export default {
 async fetch(request,env){
  const respond=async()=>{
  const origin=request.headers.get('Origin');
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers:cors()});
  if(origin!==ORIGIN)return json({error:'Origin not allowed'},403);
  if(request.method!=='POST')return json({error:'Method not allowed'},405);
  const url=new URL(request.url);
  try{
   if(url.pathname==='/convert'){
    let input;try{input=await request.json()}catch{return json({error:'Invalid JSON'},400)}
    const id=String(input?.videoId||'');
    if(!/^[a-zA-Z0-9_-]{11}$/.test(id))return json({error:'Invalid video ID'},400);
    const response=await fetch(UPSTREAM,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({youtube_url:'https://www.youtube.com/watch?v='+id,quality:'320'}),signal:AbortSignal.timeout(25000)});
    if(!response.ok)return json({error:'Converter returned HTTP '+response.status},502);
    const data=await response.json();
    if(!data.success||!data.downloadUrl)return json({error:data.error||'Converter did not return a download URL'},502);
    const target=new URL(data.downloadUrl);
    if(target.protocol!=='https:')return json({error:'Invalid download URL'},502);
    const token=await sign(target.href,env.DOWNLOAD_SIGNING_KEY);
    return json({success:true,title:data.title||'',thumbnail:data.thumbnail||'',downloadPath:'/audio?url='+encodeURIComponent(target.href)+'&token='+encodeURIComponent(token)});
   }
   if(url.pathname==='/audio'){
    const target=url.searchParams.get('url')||'',token=url.searchParams.get('token')||'';
    if(!target||!token||!(await verify(target,token,env.DOWNLOAD_SIGNING_KEY)))return json({error:'Invalid download token'},403);
    const remote=new URL(target);if(remote.protocol!=='https:')return json({error:'Invalid URL'},400);
    const response=await fetch(remote.href,{redirect:'follow',signal:AbortSignal.timeout(25000)});
    if(!response.ok)return json({error:'Audio download failed: HTTP '+response.status},502);
    const type=(response.headers.get('content-type')||'').toLowerCase();
    if(type.includes('text/html')||type.includes('application/json')){
      const finalHost=new URL(response.url||remote.href).hostname;
      const details={error:'Provider returned non-audio content',contentType:type.split(';')[0],upstreamHost:finalHost,redirected:response.redirected};
      return json(details,502);
    }
    return new Response(response.body,{status:200,headers:{'Content-Type':type||'audio/mpeg','Cache-Control':'no-store'}});
   }
   return json({error:'Not found'},404);
  }catch(e){return json({error:'Upstream request failed: '+(e?.name||'Error')},502)}
  };
  const response=await respond();
  const headers=new Headers(response.headers);for(const [key,value] of Object.entries(cors()))headers.set(key,value);
  return new Response(response.body,{status:response.status,headers});
 }
};
async function sign(message,secret){
 if(!secret)throw new Error('Missing DOWNLOAD_SIGNING_KEY');
 const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 const sig=await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(message));
 return Array.from(new Uint8Array(sig),b=>b.toString(16).padStart(2,'0')).join('');
}
async function verify(message,signature,secret){
 if(!/^[a-f0-9]{64}$/.test(signature))return false;
 const expected=await sign(message,secret);
 let diff=0;for(let i=0;i<64;i++)diff|=expected.charCodeAt(i)^signature.charCodeAt(i);
 return diff===0;
}
