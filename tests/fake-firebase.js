/* Test double for the Firebase compat SDK: a tiny Firestore shared between tabs of one browser
   (localStorage + storage events). Enough for Mac Display's pairing and live state; no rules. */
(()=>{
const local=new Set();
const K=p=>'fakefs:'+p;
const read=p=>{const v=localStorage.getItem(K(p));return v?JSON.parse(v):null};
const revive=o=>{if(o&&typeof o==='object'){if(o.__ts)return {toMillis:()=>o.__ts};for(const k in o)o[k]=revive(o[k])}return o};
const stamp=o=>{if(o&&typeof o==='object'){if(o.__serverTs)return {__ts:Date.now()};const r=Array.isArray(o)?[]:{};for(const k in o)r[k]=stamp(o[k]);return r}return o};
function notify(path){local.forEach(fn=>fn(path))}   // this tab; other tabs hear the storage event
addEventListener('storage',e=>{if(e.key&&e.key.startsWith('fakefs:'))local.forEach(fn=>fn(e.key.slice(7)))});
const err=(code,m)=>Object.assign(Error(m||code),{code});
const snap=(path,id)=>{const d=read(path);return {id,exists:!!d,data:()=>d?revive(JSON.parse(JSON.stringify(d))):undefined}};
function docRef(path){
  const id=path.split('/').pop();
  return {id,path,
    collection:n=>collRef(path+'/'+n),
    async get(){return snap(path,id)},
    async set(data){localStorage.setItem(K(path),JSON.stringify(stamp(data)));notify(path)},
    async update(data){const cur=read(path);if(!cur)throw err('not-found');localStorage.setItem(K(path),JSON.stringify({...cur,...stamp(data)}));notify(path)},
    async delete(){localStorage.removeItem(K(path));notify(path)},
    onSnapshot(cb){const fn=p=>{if(p===path)cb(snap(path,id))};local.add(fn);setTimeout(()=>cb(snap(path,id)),0);return ()=>local.delete(fn)}};
}
function collRef(path){
  const list=()=>Object.keys(localStorage).filter(k=>k.startsWith(K(path)+'/')&&k.slice(K(path).length+1).indexOf('/')<0).map(k=>k.slice(7));
  return {doc:id=>docRef(path+'/'+id),
    onSnapshot(cb){let seen=new Map();const emit=()=>{const changes=[];for(const p of list()){const raw=localStorage.getItem(K(p));if(seen.get(p)!==raw){seen.set(p,raw);changes.push({type:'modified',doc:snap(p,p.split('/').pop())})}}
        if(changes.length)cb({docChanges:()=>changes})};
      const fn=p=>{if(p.startsWith(path+'/'))emit()};local.add(fn);setTimeout(emit,0);return ()=>local.delete(fn)}};
}
let n=0;
const app=name=>({name,
  auth:()=>({onAuthStateChanged(cb){setTimeout(()=>cb(null),0);return ()=>{}},
    async signInAnonymously(){let u=sessionStorage.getItem('fakeuid:'+name);if(!u){u=name+'-'+Math.random().toString(36).slice(2,8);sessionStorage.setItem('fakeuid:'+name,u)}return {user:{uid:u}}}}),
  firestore:()=>({settings(){},collection:p=>collRef(p)})});
const apps=[];
window.firebase={apps,initializeApp(cfg,name){const a=app(name||'[DEFAULT]');apps.push(a);return a},
  auth:function(){},firestore:Object.assign(function(){},{FieldValue:{serverTimestamp:()=>({__serverTs:1})}})};
})();
