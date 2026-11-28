// Stand-in for the iPhone app's song store + player (IPodMusicStore.swift / IPodPlayer.swift), for tests.
(()=>{
  const files=new Map(),uploads=new Map(),art=new Map(),log=[];
  window.__native={files,log,corrupt:false,refuse:null,player:null};
  const hex=b=>[...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('');
  const unb64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
  const P={queue:[],index:0,t:0,d:0,playing:false,repeat:'Off',crossfade:0,timer:null};window.__native.player=P;
  const st=()=>({id:P.queue[P.index]?.id||'',index:P.index,t:P.t,d:P.d,playing:P.playing,count:P.queue.length});
  const push=(x)=>{try{window.ipodNativeState&&window.ipodNativeState(Object.assign(st(),x||{}))}catch(e){console.error(e)}};
  // like IPodPlayer.handOff: a song still on the web side goes back to the page
  const go=(i,play)=>{P.index=i;P.t=0;if(P.queue[i]?.web){P.playing=false;window.__native.handoffs=(window.__native.handoffs||0)+1;push({handoff:i,play});return false}P.playing=play;return true};
  const startTimer=()=>{clearInterval(P.timer);P.timer=setInterval(()=>{if(P.playing){P.t+=.25;if(P.t>=P.d){if(P.index+1<P.queue.length){if(!go(P.index+1,true))return}else{P.playing=false;return push({ended:true})}}}push()},250)};
  const store=async m=>{const id=m.id;log.push(m.op);switch(m.op){
    case 'inventory':{const o={};for(const [k,v] of files)o[k]={size:v.length,art:art.has(k)};return o}
    case 'begin':uploads.set(id,{parts:[],ext:m.ext,size:m.size,sha:m.sha});return true;
    case 'chunk':uploads.get(id).parts.push(unb64(m.data));return true;
    case 'end':{const u=uploads.get(id);uploads.delete(id);const all=new Uint8Array(u.parts.reduce((n,p)=>n+p.length,0));let o=0;for(const p of u.parts){all.set(p,o);o+=p.length}
      if(window.__native.corrupt||window.__native.refuse===id)all[0]^=1;
      const sha=hex(await crypto.subtle.digest('SHA-256',all));if(all.length!==u.size||sha!==u.sha)return {ok:false,reason:'checksum'};files.set(id,all);return {ok:true,size:all.length,sha}}
    case 'verify':{const f=files.get(id);if(!f)return {ok:false,reason:'missing'};return {ok:true,duration:2}}
    case 'read':{const f=files.get(id);const part=f.subarray(m.offset,m.offset+m.length);let s='';for(let i=0;i<part.length;i+=0x8000)s+=String.fromCharCode.apply(null,part.subarray(i,i+0x8000));return btoa(s)}
    case 'art':art.set(id,m.data);return true;
    case 'delete':files.delete(id);return true;}};
  const player=async m=>{log.push('p:'+m.op);switch(m.op){
    case 'load':P.queue=m.tracks;P.d=2;startTimer();if(!go(m.index,!!m.play))return st();P.t=m.t||0;break;
    case 'requeue':P.queue=m.tracks;P.index=m.index;break;
    case 'jump':if(!go(m.index,!!m.play))return st();break;
    case 'play':P.playing=true;break;case 'pause':P.playing=false;break;case 'toggle':P.playing=!P.playing;break;
    case 'seek':P.t=m.t;break;case 'next':P.index=(P.index+1)%P.queue.length;P.t=0;break;case 'stop':P.queue=[];P.playing=false;break;
    case 'config':P.repeat=m.repeat;P.crossfade=m.crossfade;P.smart=m.smart;P.eq=m.eq;break}
    setTimeout(()=>push(),0);return st()};
  window.webkit=window.webkit||{};window.webkit.messageHandlers=Object.assign(window.webkit.messageHandlers||{},{
    ipodStore:{postMessage:m=>store(m)},ipodPlayer:{postMessage:m=>player(m)}});
})();
