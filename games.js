/* iPod games, played on the click wheel.
   Groups — find four groups of four among sixteen words.
   Domino — lay every domino on the board so each coloured region's rule holds. */
(()=>{
'use strict';
const B=()=>window.ipodGamesBridge;
const store={get:(k,d)=>{try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v)}catch{return d}},set:(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const today=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')};
const dayNumber=()=>Math.floor((Date.UTC(...today().split('-').map((n,i)=>i===1?n-1:+n)))/864e5);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function rng(seed){let a=seed>>>0;return()=>{a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
const shuffle=(arr,r=Math.random)=>{const a=arr.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(r()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
const tick=()=>B()?.click?.(),buzz=k=>B()?.haptic?.(k);
const fmtTime=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');

/* ================= Groups ================= */
// level 0 = easiest (yellow) … 3 = trickiest (purple). Each puzzle has red herrings that only resolve one way.
const GROUPS=[
 [['Strings attached',['VIOLIN','CELLO','HARP','BANJO']],['Tempo markings',['ALLEGRO','ADAGIO','PRESTO','LARGO']],['___ rock',['PUNK','HARD','SOFT','GLAM']],['Things with keys',['PIANO','LOCK','MAP','ANSWER']]],
 [['Coffee orders',['LATTE','MOCHA','ESPRESSO','CORTADO']],['Card games',['POKER','RUMMY','SNAP','HEARTS']],['___cake',['CUP','PAN','CHEESE','SPONGE']],['Hidden animals',['CATALOG','PIGMENT','BEARD','CROWD']]],
 [['Shades of blue',['NAVY','TEAL','COBALT','AZURE']],['Dog breeds',['POODLE','BEAGLE','PUG','CORGI']],['Kinds of shorts',['BOXER','CARGO','BERMUDA','BIKE']],['___light',['SPOT','FLASH','MOON','TRAFFIC']]],
 [['Fruit',['MANGO','PEACH','GRAPE','PLUM']],['Pasta shapes',['PENNE','ORZO','FUSILLI','RIGATONI']],['Total flops',['LEMON','FLOP','BUST','TURKEY']],['___ bowl',['SUPER','DUST','FISH','SALAD']]],
 [['Parts of a guitar',['NECK','FRET','BRIDGE','PICKUP']],['In a deck of cards',['JACK','ACE','JOKER','KING']],['Chess pieces',['QUEEN','ROOK','PAWN','BISHOP']],['___ pin',['BOBBY','SAFETY','ROLLING','HAIR']]],
 [['Weather',['RAIN','SNOW','HAIL','SLEET']],['Fast',['QUICK','RAPID','SWIFT','BRISK']],['Birds',['ROBIN','WREN','FINCH','CROW']],['___storm',['BRAIN','THUNDER','FIRE','SAND']]],
 [['Very small',['TINY','WEE','PETITE','MINUTE']],['Spans of time',['SECOND','DECADE','ERA','CENTURY']],['___hand',['FIRST','UNDER','BACK','OFF']],['___glass',['HOUR','SPY','WINE','LOOKING']]],
 [['Music genres',['JAZZ','BLUES','FUNK','DISCO']],['___box',['JUKE','BOOM','MUSIC','SOAP']],['Parts of a shoe',['TONGUE','HEEL','LACE','EYELET']],['___mate',['SOUL','CLASS','ROOM','PLAY']]],
 [['Sea creatures',['SHARK','WHALE','SQUID','OCTOPUS']],['Parts of a ship',['MAST','HULL','DECK','KEEL']],['At the pool table',['RACK','POCKET','BREAK','CHALK']],['___ball',['CUE','SNOW','EYE','BASE']]],
 [['Breakfast',['BACON','WAFFLE','OMELET','GRITS']],['Celebrate!',['CHEERS','BRAVO','HOORAY','TOAST']],['On a computer',['CURSOR','PIXEL','SERVER','LAPTOP']],['___pad',['MOUSE','LAUNCH','KEY','NOTE']]],
 [['In a rainbow',['RED','GREEN','INDIGO','VIOLET']],['Flowers',['ROSE','TULIP','DAISY','LILY']],['Golf',['EAGLE','BOGEY','PUTT','IRON']],['Colours that are fruit',['PLUM','PEACH','LIME','ORANGE']]],
 [['On a bike',['PEDAL','CHAIN','SPOKE','SADDLE']],['Past tense',['RODE','SANG','DROVE','SWAM']],['Horse gear',['BRIDLE','REINS','HALTER','STIRRUP']],['Jewellery',['RING','BANGLE','LOCKET','ANKLET']]]
];
const GROUP_COLORS=['#f3d36b','#9fcd6a','#8fb4ec','#b88bd6'];
const groupsKey=n=>'ipod.groups.'+n;
function todaysGroups(){return ((dayNumber()%GROUPS.length)+GROUPS.length)%GROUPS.length}
function groupsView(n){
  const pz=GROUPS[n],saved=store.get(groupsKey(n),null);
  const v={type:'custom',title:'Groups #'+(n+1),n,cursor:0,picked:[],
    solved:saved?.solved||[],mistakes:saved?.mistakes||0,done:saved?.done||false,guesses:saved?.guesses||[],
    words:null,msg:'',msgT:0};
  const solvedWords=()=>new Set(v.solved.flatMap(i=>pz[i][1]));
  v.words=saved?.order?.filter(w=>!solvedWords().has(w))||shuffle(pz.flatMap(g=>g[1]).filter(w=>!solvedWords().has(w)));
  const save=()=>store.set(groupsKey(n),{solved:v.solved,mistakes:v.mistakes,done:v.done,order:v.words,guesses:v.guesses});
  const say=t=>{v.msg=t;clearTimeout(v.msgT);v.msgT=setTimeout(()=>{v.msg='';if(B().top()===v)B().render()},1800)};
  const finish=win=>{v.done=true;v.win=win;
    if(!win)for(let i=0;i<4;i++)if(!v.solved.includes(i))v.solved.push(i);
    v.words=[];v.picked=[];save();buzz(win?'success':'warning');
    if(win){const st=store.get('ipod.groups.stats',{won:0,played:0});st.won++;st.played++;store.set('ipod.groups.stats',st)}
    else{const st=store.get('ipod.groups.stats',{won:0,played:0});st.played++;store.set('ipod.groups.stats',st)}};
  v.render=el=>{
    const left=4-v.mistakes;
    el.innerHTML=`<div class="ggrid">${v.solved.map(i=>`<div class="gsolved" style="background:${GROUP_COLORS[i]}"><b>${esc(pz[i][0])}</b><span>${pz[i][1].map(esc).join(', ')}</span></div>`).join('')}
      ${v.words.map((w,k)=>`<div class="gw${v.picked.includes(w)?' on':''}${k===v.cursor&&!v.done?' cur':''}${w.length>7?' sm':''}">${esc(w)}</div>`).join('')}</div>
      <div class="gfoot">${v.done?(v.win?`Solved${v.mistakes?` with ${v.mistakes} mistake${v.mistakes>1?'s':''}`:' perfectly'}!`:'Next time!')
        :v.msg?esc(v.msg):v.picked.length===4?'Press ▶︎❚❚ to submit':`Mistakes left <i>${'●'.repeat(left)}${'○'.repeat(4-left)}</i>`}</div>`;
    el.querySelector('.gw.cur')?.scrollIntoView?.({block:'nearest'});
  };
  v.input=(btn,dir)=>{
    if(v.done){if(btn==='select'||btn==='play')B().pop();return}
    if(dir){const c=Math.max(0,Math.min(v.words.length-1,v.cursor+dir));if(c!==v.cursor){v.cursor=c;tick();B().render()}return}
    if(btn==='select'){const w=v.words[v.cursor];if(!w)return;
      if(v.picked.includes(w))v.picked=v.picked.filter(x=>x!==w);else if(v.picked.length<4)v.picked.push(w);else{say('Four at a time');buzz('warning')}
      tick();B().render();return}
    if(btn==='prev'){v.picked=[];B().render();return}
    if(btn==='next'){v.words=shuffle(v.words);v.cursor=0;save();B().render();return}
    if(btn==='play'){
      if(v.picked.length<4){say('Pick four words');buzz('warning');B().render();return}
      const key=v.picked.slice().sort().join('|');
      if(v.guesses.includes(key)){say('Already guessed');B().render();return}
      v.guesses.push(key);
      const g=pz.findIndex(([,ws])=>v.picked.every(w=>ws.includes(w)));
      if(g>=0){v.solved.push(g);v.words=v.words.filter(w=>!v.picked.includes(w));v.picked=[];v.cursor=0;buzz('success');
        if(v.solved.length===4)finish(true)}
      else{v.mistakes++;const close=pz.some(([,ws])=>v.picked.filter(w=>ws.includes(w)).length===3);
        say(close?'One away…':'Not a group');buzz('error');if(v.mistakes>=4)finish(false)}
      save();B().render();
    }
  };
  return v;
}
function groupsMenu(){
  const t=todaysGroups(),st=store.get('ipod.groups.stats',{won:0,played:0});
  const state=n=>{const s=store.get(groupsKey(n),null);return !s?'':s.done?(s.solved?.length===4&&s.mistakes<4?'✓':'✗'):'…'};
  return B().list('Groups',()=>[
    {label:"Today's Puzzle",val:state(t)||'#'+(t+1),action:()=>B().push(groupsView(t))},
    {label:'How to Play',chev:1,action:()=>B().push(B().msgView('Groups','Find four groups of four words that share something.\n\nSpin to move · Center picks a word · ▶︎❚❚ submits four.\n⏭ shuffles · ⏮ clears your picks. Four mistakes and it’s over.'))},
    {label:'Stats',val:st.played?`${st.won}/${st.played} won`:'—'},
    ...GROUPS.map((_,n)=>({label:'Puzzle #'+(n+1),val:state(n),action:()=>B().push(groupsView(n))}))]);
}

/* ================= Domino ================= */
const DIRS=[[0,1],[1,0],[0,-1],[-1,0]];   // right, down, left, up
const LEVELS={Easy:{pairs:5,blank:0},Medium:{pairs:7,blank:.12},Hard:{pairs:9,blank:.22}};
// Builds a board by laying random dominoes edge to edge (so it always has a solution), then carves it into
// regions and writes each region's rule from that solution. Any arrangement that meets every rule wins.
function makeDomino(level,seed){
  const r=rng(seed),L=LEVELS[level],N=7,cells=new Map(),key=(y,x)=>y+','+x,sol=[];
  const free=(y,x)=>y>=0&&x>=0&&y<N&&x<N&&!cells.has(key(y,x));
  const near=(y,x)=>DIRS.some(([dy,dx])=>cells.has(key(y+dy,x+dx)));
  for(let guard=0;sol.length<L.pairs&&guard<4000;guard++){
    let y,x;
    if(!sol.length){y=3;x=2}
    else{const c=[...cells.keys()][Math.floor(r()*cells.size)].split(',').map(Number);const[dy,dx]=DIRS[Math.floor(r()*4)];y=c[0]+dy;x=c[1]+dx}
    const[dy,dx]=DIRS[Math.floor(r()*2)],y2=y+dy,x2=x+dx;
    if(!free(y,x)||!free(y2,x2)||(sol.length&&!near(y,x)&&!near(y2,x2)))continue;
    const a=Math.floor(r()*7),b=Math.floor(r()*7);
    cells.set(key(y,x),a);cells.set(key(y2,x2),b);sol.push([[y,x],[y2,x2],a,b]);
  }
  // trim to the bounding box
  const ys=[...cells.keys()].map(k=>+k.split(',')[0]),xs=[...cells.keys()].map(k=>+k.split(',')[1]);
  const y0=Math.min(...ys),x0=Math.min(...xs),rows=Math.max(...ys)-y0+1,cols=Math.max(...xs)-x0+1;
  const board=[...cells.keys()].map(k=>{const[y,x]=k.split(',').map(Number);return[y-y0,x-x0]});
  const val=new Map([...cells].map(([k,v])=>{const[y,x]=k.split(',').map(Number);return[key(y-y0,x-x0),v]}));
  // regions: grow random connected patches of 1–4 cells
  const region=new Map(),regions=[];
  for(const[y,x]of shuffle(board,r)){
    if(region.has(key(y,x)))continue;
    const want=1+Math.floor(r()*4),mine=[[y,x]];region.set(key(y,x),regions.length);
    while(mine.length<want){
      const opts=mine.flatMap(([cy,cx])=>DIRS.map(([dy,dx])=>[cy+dy,cx+dx])).filter(([ny,nx])=>val.has(key(ny,nx))&&!region.has(key(ny,nx)));
      if(!opts.length)break;const p=opts[Math.floor(r()*opts.length)];region.set(key(...p),regions.length);mine.push(p);
    }
    const vs=mine.map(c=>val.get(key(...c))),sum=vs.reduce((a,b)=>a+b,0);
    let rule;
    if(r()<L.blank)rule={t:'any'};
    else if(mine.length>1&&vs.every(v=>v===vs[0]))rule={t:'eq'};
    else if(mine.length>1&&new Set(vs).size===vs.length&&r()<.35)rule={t:'ne'};
    else if(mine.length===1&&r()<.4)rule=vs[0]>=3&&r()<.5?{t:'gt',n:vs[0]-1-Math.floor(r()*Math.min(2,vs[0]-1))}:vs[0]<=4?{t:'lt',n:vs[0]+1+Math.floor(r()*2)}:{t:'sum',n:sum};
    else rule={t:'sum',n:sum};
    regions.push({cells:mine,rule});
  }
  const tiles=shuffle(sol.map(([,,a,b])=>[a,b]),r).map(([a,b],i)=>({id:i,a,b}));
  return {rows,cols,board,regions,tiles,regionOf:region};
}
const ruleText=u=>u.t==='sum'?String(u.n):u.t==='eq'?'=':u.t==='ne'?'≠':u.t==='gt'?'>'+u.n:u.t==='lt'?'<'+u.n:'';
const ruleOk=(u,vs,full)=>{
  if(u.t==='any')return true;
  if(u.t==='eq')return vs.every(v=>v===vs[0]);
  if(u.t==='ne')return new Set(vs).size===vs.length;
  const s=vs.reduce((a,b)=>a+b,0);
  if(u.t==='sum')return full?s===u.n:s<=u.n;
  if(u.t==='gt')return full?s>u.n:true;
  if(u.t==='lt')return s<u.n;
  return true;
};
const REGION_TINTS=['#f6c8a8','#bfe0b0','#b9d2f3','#e7c2ea','#f4e3a1','#b8e6e0','#f2b7c2','#d5ccf4'];
const PIPS={0:[],1:[4],2:[0,8],3:[0,4,8],4:[0,2,6,8],5:[0,2,4,6,8],6:[0,2,3,5,6,8]};
const pipHtml=n=>`<span class="dp">${[...Array(9)].map((_,i)=>`<i${PIPS[n].includes(i)?' class="o"':''}></i>`).join('')}</span>`;
const dominoKey=(lvl,seed)=>'ipod.domino.'+lvl+'.'+seed;
function dominoView(level,seed,label){
  const pz=makeDomino(level,seed),K=(y,x)=>y+','+x,cellsSorted=pz.board.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const saved=store.get(dominoKey(level,seed),null);
  const v={type:'custom',title:'Domino · '+(label||level),cursor:0,mode:'board',tray:0,
    placed:saved?.placed||[],   // {id, y, x, d (dir index), flip}
    done:saved?.done||false,secs:saved?.secs||0,started:Date.now(),msg:'',bad:new Set()};
  const tile=id=>pz.tiles.find(t=>t.id===id);
  const halves=p=>{const t=tile(p.id),[dy,dx]=DIRS[p.d];return[[p.y,p.x,p.flip?t.b:t.a],[p.y+dy,p.x+dx,p.flip?t.a:t.b]]};
  const occ=()=>{const m=new Map();for(const p of v.placed)for(const[y,x,n]of halves(p))m.set(K(y,x),{p,n});return m};
  const onBoard=(y,x)=>pz.regionOf.has(K(y,x));
  const trayLeft=()=>pz.tiles.filter(t=>!v.placed.some(p=>p.id===t.id));
  const elapsed=()=>v.secs+(v.done?0:(Date.now()-v.started)/1000);
  const save=()=>store.set(dominoKey(level,seed),{placed:v.placed,done:v.done,secs:elapsed()});
  const say=t=>{v.msg=t;clearTimeout(v.mt);v.mt=setTimeout(()=>{v.msg='';if(B().top()===v)B().render()},1800)};
  const fits=(y,x,d,o)=>{const[dy,dx]=DIRS[d];return onBoard(y,x)&&onBoard(y+dy,x+dx)&&!o.has(K(y,x))&&!o.has(K(y+dy,x+dx))};
  const check=()=>{
    const o=occ(),bad=new Set();
    pz.regions.forEach((rg,i)=>{const vs=rg.cells.map(c=>o.get(K(...c))?.n).filter(n=>n!=null);if(vs.length&&!ruleOk(rg.rule,vs,vs.length===rg.cells.length))bad.add(i)});
    v.bad=bad;
    if(!trayLeft().length){
      if(!bad.size){v.done=true;v.secs=elapsed();buzz('success');
        const best=store.get('ipod.domino.best.'+level,0);if(!best||v.secs<best)store.set('ipod.domino.best.'+level,Math.round(v.secs))}
      else{say('Not quite — check the red regions');buzz('error')}
    }
    save();
  };
  v.render=el=>{
    const W=el.clientWidth||300,H=(el.clientHeight||210)-34,cs=Math.max(16,Math.floor(Math.min((W-12)/pz.cols,(H-6)/pz.rows,40)));
    const o=occ(),cur=cellsSorted[v.cursor],cy=cur?.[0],cx=cur?.[1];
    let html=`<div class="dbd" style="width:${pz.cols*cs}px;height:${pz.rows*cs}px">`;
    pz.regions.forEach((rg,i)=>{
      const tint=rg.rule.t==='any'?'#e3e3e3':REGION_TINTS[i%REGION_TINTS.length];
      for(const[y,x]of rg.cells)html+=`<div class="dc${v.bad.has(i)?' bad':''}" style="left:${x*cs}px;top:${y*cs}px;width:${cs}px;height:${cs}px;background:${tint}"></div>`;
      const lab=ruleText(rg.rule);
      if(lab){const[y,x]=rg.cells.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1])[0];html+=`<b class="dl" style="left:${x*cs+1}px;top:${y*cs+1}px">${esc(lab)}</b>`}
    });
    for(const p of v.placed){const[[y1,x1,a],[y2,x2,b]]=halves(p),y=Math.min(y1,y2),x=Math.min(x1,x2),hz=y1===y2,first=(y1<y2||x1<x2);
      html+=`<div class="dd${hz?' h':''}" style="left:${x*cs+2}px;top:${y*cs+2}px;width:${(hz?2:1)*cs-4}px;height:${(hz?1:2)*cs-4}px">${pipHtml(first?a:b)}${pipHtml(first?b:a)}</div>`}
    if(cur&&!v.done)html+=`<div class="dcur${v.mode==='tray'?' pick':''}" style="left:${cx*cs}px;top:${cy*cs}px;width:${cs}px;height:${cs}px"></div>`;
    html+='</div>';
    const left=trayLeft();
    const tray=v.done?`<div class="dmsg">Solved in ${fmtTime(v.secs)}!</div>`:v.msg?`<div class="dmsg">${esc(v.msg)}</div>`:
      `<div class="dtray">${left.map((t,i)=>`<div class="dd h mini${v.mode==='tray'&&i===v.tray?' sel':''}">${pipHtml(t.a)}${pipHtml(t.b)}</div>`).join('')||'<span>All placed</span>'}</div>`;
    el.innerHTML=`<div class="dwrap" style="--cs:${cs}px">${html}${tray}</div>`;
    el.querySelector('.dtray .sel')?.scrollIntoView?.({inline:'nearest',block:'nearest'});
  };
  v.input=(btn,dir)=>{
    if(v.done){if(btn==='select'||btn==='play')B().pop();return}
    const cur=cellsSorted[v.cursor],o=occ(),here=cur&&o.get(K(...cur));
    if(dir){
      if(v.mode==='tray'){const n=trayLeft().length,t=Math.max(0,Math.min(n-1,v.tray+dir));if(t!==v.tray){v.tray=t;tick();B().render()}return}
      const c=Math.max(0,Math.min(cellsSorted.length-1,v.cursor+dir));if(c!==v.cursor){v.cursor=c;tick();B().render()}return}
    if(btn==='select'){
      if(v.mode==='tray'){
        const t=trayLeft()[v.tray];if(!t){v.mode='board';B().render();return}
        const d=[0,1,2,3].find(d=>fits(cur[0],cur[1],d,o));
        if(d==null){say('No room for a domino here');buzz('warning');v.mode='board';B().render();return}
        v.placed.push({id:t.id,y:cur[0],x:cur[1],d,flip:false});v.mode='board';tick();check();B().render();return}
      if(here){v.placed=v.placed.filter(p=>p!==here.p);v.tray=0;tick();check();B().render();return}   // pick it back up
      if(!trayLeft().length)return;
      if(![0,1,2,3].some(d=>fits(cur[0],cur[1],d,o))){say('No room for a domino here');buzz('warning');B().render();return}
      v.mode='tray';v.tray=Math.min(v.tray,trayLeft().length-1);tick();B().render();return}
    if(btn==='next'&&here){   // turn it round its first half
      const p=here.p,rest=new Map([...o].filter(([,x])=>x.p!==p));
      for(let k=1;k<=4;k++){const d=(p.d+k)%4;if(fits(p.y,p.x,d,rest)){p.d=d;break}}
      tick();check();B().render();return}
    if(btn==='prev'&&here){here.p.flip=!here.p.flip;tick();check();B().render();return}
    if(btn==='play'&&v.mode==='tray'){v.mode='board';B().render()}
  };
  return v;
}
function dominoMenu(){
  const d=dayNumber(),state=(l,s)=>store.get(dominoKey(l,s),null)?.done?'✓':'';
  return B().list('Domino',()=>[
    ...Object.keys(LEVELS).map((l,i)=>({label:"Today's "+l,val:state(l,d*10+i)||(store.get('ipod.domino.best.'+l,0)?'best '+fmtTime(store.get('ipod.domino.best.'+l,0)):''),action:()=>B().push(dominoView(l,d*10+i,l))})),
    {label:'Random Puzzle',chev:1,action:()=>{const l=Object.keys(LEVELS)[Math.floor(Math.random()*3)];B().push(dominoView(l,Math.floor(Math.random()*1e9),l+' · Random'))}},
    {label:'How to Play',chev:1,action:()=>B().push(B().msgView('Domino','Lay every domino on the board. Each coloured region has a rule: a number is the total of its pips, = means all the same, ≠ all different, < and > compare the total. Grey regions take anything.\n\nSpin to move · Center on an empty square picks a domino from the tray, Center again lays it · Center on a domino lifts it · ⏭ turns it · ⏮ flips it.'))}]);
}

window.ipodGames=Object.freeze({groupsMenu,dominoMenu,groupsView,dominoView,makeDomino,ruleOk,GROUPS});
})();
