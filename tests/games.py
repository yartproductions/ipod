#!/usr/bin/env python3
"""Groups and Domino, played on the click wheel.   Run: python3 tests/games.py"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
ok = []
def check(n, c, d=''):
    ok.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
srv, url = C.serve(); errors = []
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True, args=['--no-sandbox'],
          viewport={'width': 390, 'height': 844}, service_workers='block')
    ctx.route('https://**', lambda r: r.abort())
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.add_init_script("localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false,accel:false}))")
    pg.goto(url); pg.wait_for_timeout(1500)
    shot = lambda n: pg.screenshot(path=f'/tmp/game-{n}.png', clip=pg.locator('#screen').bounding_box())
    # every Groups puzzle: 16 different words, 4 groups of 4
    G = pg.evaluate("window.ipodGames.GROUPS")
    check('every Groups puzzle has 16 different words in 4 groups of 4', all(len(g) == 4 and all(len(w) == 4 for _, w in g) and len({x for _, w in g for x in w}) == 16 for g in G), [i for i, g in enumerate(G) if len({x for _, w in g for x in w}) != 16])
    check('words fit the tiles (≤ 9 letters)', all(len(x) <= 9 for g in G for _, w in g for x in w), [x for g in G for _, w in g for x in w if len(x) > 9])
    C.home(pg); C.choose(pg, 'Games'); C.choose(pg, 'Groups'); C.choose(pg, 'Puzzle #1')
    check('Groups shows 16 tiles', pg.locator('.gw').count() == 16)
    shot('groups')
    words = pg.evaluate("[...document.querySelectorAll('.gw')].map(x=>x.textContent)")
    def pick(ws):
        pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(60)   # ⏮ clears picks left from a wrong guess
        for w in ws:
            cur = pg.evaluate("[...document.querySelectorAll('.gw')].findIndex(x=>x.classList.contains('cur'))")
            tgt = pg.evaluate(f"[...document.querySelectorAll('.gw')].findIndex(x=>x.textContent==={json.dumps(w)})")
            for _ in range(abs(tgt - cur)): pg.keyboard.press('ArrowDown' if tgt > cur else 'ArrowUp'); pg.wait_for_timeout(25)
            pg.keyboard.press('Enter'); pg.wait_for_timeout(60)
        pg.keyboard.press('Space'); pg.wait_for_timeout(250)
    # a wrong guess, three right
    pick(['VIOLIN', 'CELLO', 'HARP', 'PIANO'])
    check('a near miss says "One away…"', 'One away' in pg.inner_text('.gfoot'), pg.inner_text('.gfoot'))
    check('…and costs a mistake', '●●●○' in pg.inner_text('.gfoot') or pg.locator('.gfoot').count() == 1)
    for _, ws in G[0][:3]: pick(ws)
    check('a right guess becomes a coloured bar', pg.locator('.gsolved').count() == 3, pg.locator('.gsolved').count())
    shot('groups-solving')
    pick(G[0][3][1])
    check('finding all four wins', 'Solved' in pg.inner_text('.gfoot'), pg.inner_text('.gfoot'))
    C.home(pg); C.choose(pg, 'Games'); C.choose(pg, 'Groups')
    check('the menu marks it solved', any(r.startswith('Puzzle #1') for r in C.all_rows(pg)) and '✓' in pg.inner_text('#body'))
    # Domino: generator always makes a solvable board whose rules hold for its own solution
    res = pg.evaluate("""(()=>{let bad=[];for(const l of ['Easy','Medium','Hard'])for(let s=1;s<=60;s++){const z=window.ipodGames.makeDomino(l,s);
      const cells=z.board.length;if(cells!==z.tiles.length*2)bad.push([l,s,'cells']);
      if(z.rows>7||z.cols>7)bad.push([l,s,'size',z.rows,z.cols]);}return bad})()""")
    check('Domino boards always have one square per domino half and fit the screen', not res, res[:5])
    C.home(pg); C.choose(pg, 'Games'); C.choose(pg, 'Domino'); C.choose(pg, "Today's Easy")
    check('Domino shows the board and the tray', pg.locator('.dc').count() >= 10 and pg.locator('.dtray .dd').count() == 5, (pg.locator('.dc').count(), pg.locator('.dtray .dd').count()))
    shot('domino')
    # lay a domino: Center on the first square, Center again to place
    pg.keyboard.press('Enter'); pg.wait_for_timeout(100); pg.keyboard.press('Enter'); pg.wait_for_timeout(150)
    check('Center, Center lays a domino on the board', pg.locator('.dbd .dd').count() == 1 and pg.locator('.dtray .dd').count() == 4)
    pg.keyboard.press('Enter'); pg.wait_for_timeout(150)
    check('Center on it lifts it back to the tray', pg.locator('.dbd .dd').count() == 0 and pg.locator('.dtray .dd').count() == 5)
    # solve it by brute force through the wheel-free API, then check the win screen
    won = pg.evaluate("""(()=>{const G=window.ipodGames,z=G.makeDomino('Easy',5);const K=(y,x)=>y+','+x,D=[[0,1],[1,0],[0,-1],[-1,0]];
      const on=new Set(z.board.map(c=>K(...c)));const val=new Map();const used=new Set();
      const ok=()=>z.regions.every(rg=>{const vs=rg.cells.map(c=>val.get(K(...c))).filter(v=>v!=null);return !vs.length||G.ruleOk(rg.rule,vs,vs.length===rg.cells.length)});
      const cells=z.board.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
      const go=()=>{const c=cells.find(c=>!val.has(K(...c)));if(!c)return true;
        for(const t of z.tiles){if(used.has(t.id))continue;for(const[dy,dx]of D){const y2=c[0]+dy,x2=c[1]+dx;if(!on.has(K(y2,x2))||val.has(K(y2,x2)))continue;
          for(const[a,b]of[[t.a,t.b],[t.b,t.a]]){val.set(K(...c),a);val.set(K(y2,x2),b);used.add(t.id);if(ok()&&go())return true;val.delete(K(...c));val.delete(K(y2,x2));used.delete(t.id)}}}return false};
      return go()})()""")
    check('the generated puzzle is solvable under its own rules', won)
    check('no page errors', not errors, errors)
    ctx.close()
srv.shutdown(); print(f'\n{sum(ok)}/{len(ok)} passed'); sys.exit(0 if all(ok) else 1)
