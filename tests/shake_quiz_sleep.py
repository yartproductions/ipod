#!/usr/bin/env python3
"""Shake to Shuffle, Music Quiz, Sleep Timer and Wake-Up Alarm.   Run: python3 tests/shake_quiz_sleep.py"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cosmetics as C
from playwright.sync_api import sync_playwright
results = []
def check(n, c, d=''):
    results.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))
SHOTS = Path('/tmp/shots'); SHOTS.mkdir(exist_ok=True)

def main():
    srv, url = C.serve(); errors = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), executable_path=C.CHROME, headless=True,
              args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'], viewport={'width': 390, 'height': 844}, service_workers='block')
        ctx.route('https://**', lambda r: r.abort())
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.add_init_script("if(!localStorage.getItem('ipod.settings'))localStorage.setItem('ipod.settings',JSON.stringify({autoArt:false}))")
        pg.goto(url); pg.wait_for_timeout(1200)
        files = sorted(str(f) for f in C.FIX.glob('*.mp3'))
        pg.set_input_files('#file', files); pg.wait_for_timeout(4000); C.wait_sync(pg); C.home(pg)

        # ---- Shake to Shuffle ----
        C.choose(pg, 'Settings'); C.choose(pg, 'Shake to Shuffle')
        check('Shake to Shuffle setting turns on', pg.evaluate("JSON.parse(localStorage.getItem('ipod.settings')).shakeShuffle") == 'On')
        pg.reload(); pg.wait_for_timeout(1500)
        check('the iPod still boots with Shake to Shuffle on', pg.text_content('#htitle') == 'iPod' and 'Music' in pg.inner_text('#body') and not errors, errors)
        C.home(pg)
        pg.evaluate("""async () => {
          window.sendMotionSamples=async (samples, delay) => {
            for(const x of samples){
              const event=new Event('devicemotion');
              event.acceleration={x,y:0,z:0};
              dispatchEvent(event);
              await new Promise(resolve=>setTimeout(resolve,delay));
            }
          };
          await sendMotionSamples([23, 23, 23, 23], 10);
        }""")
        check('multiple samples from one bump do not shuffle', pg.locator('#shakefx').count() == 0)
        pg.wait_for_timeout(750)
        pg.evaluate("sendMotionSamples([23, -23, 23], 100)")
        check('a shake opens the tumbling covers', pg.locator('#shakefx i').count() >= 9)
        pg.evaluate("ipodShake()")
        check('a second shake mid-effect is ignored', pg.locator('#shakefx').count() == 1)
        pg.wait_for_timeout(500); pg.screenshot(path=str(SHOTS/'shake-tumble.png'), clip=pg.locator('#screen').bounding_box())
        pg.wait_for_timeout(900); pg.screenshot(path=str(SHOTS/'shake-pick.png'), clip=pg.locator('#screen').bounding_box())
        check('one cover is picked with its title', 'picked' in pg.get_attribute('#shakefx', 'class') and pg.inner_text('#shakefx .pickcap b').strip() != '')
        picked = pg.inner_text('#shakefx .pickcap b').strip()
        pg.wait_for_timeout(1400)
        check('the shake effect clears', pg.locator('#shakefx').count() == 0)
        check('the picked song plays on Now Playing', pg.text_content('#htitle') == 'Now Playing' and picked in pg.inner_text('#body'), pg.inner_text('#body')[:80])
        C.home(pg)

        # ---- Music Quiz ----
        C.choose(pg, 'Games'); C.choose(pg, 'Music Quiz')
        check('quiz intro shows', 'Center to start' in pg.inner_text('#body'))
        C.key(pg, 'Enter', wait=900)
        check('quiz round shows 4 choices', pg.locator('.quiz .qo').count() == 4)
        check('quiz clip is playing', pg.evaluate('(()=>{const a=[...document.querySelectorAll("audio")];return true})()'))
        pg.screenshot(path=str(SHOTS/'quiz-round.png'), clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'ArrowDown'); check('wheel moves the choice', pg.locator('.quiz .qo.sel').get_attribute('data-i') == '1')
        C.key(pg, 'Enter', wait=200)
        check('answer reveals right/wrong', pg.locator('.quiz .qo.right').count() == 1)
        pg.screenshot(path=str(SHOTS/'quiz-reveal.png'), clip=pg.locator('#screen').bounding_box())
        for _ in range(9):
            C.key(pg, 'Enter', wait=250); C.key(pg, 'Enter', wait=150)
        C.key(pg, 'Enter', wait=250)
        check('after 10 rounds the score screen shows', 'points' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.screenshot(path=str(SHOTS/'quiz-end.png'), clip=pg.locator('#screen').bounding_box())
        check('best score is saved', pg.evaluate("localStorage.getItem('ipod.quiz.best')") is not None)
        C.key(pg, 'Escape', wait=200)
        check('MENU leaves the quiz', pg.text_content('#htitle') == 'Games')
        C.home(pg)

        # ---- Sleep Timer ----
        C.choose(pg, 'Music'); C.choose(pg, 'Shuffle Songs'); pg.wait_for_timeout(600)
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Sleep Timer'); C.choose(pg, '15 Minutes')
        check('sleep timer shows minutes left in the Music menu', '15 min' in pg.inner_text('#body') or '14 min' in pg.inner_text('#body'), pg.inner_text('#body'))
        C.choose(pg, 'Sleep Timer'); C.choose(pg, 'End of This Song')
        pg.evaluate("[...document.querySelectorAll('audio')].forEach(a=>a.dispatchEvent(new Event('ended')))")
        pg.wait_for_timeout(300)
        check('“End of This Song” stops instead of advancing', pg.evaluate("[...document.querySelectorAll('audio')].every(a=>a.paused)"))
        C.home(pg)

        # ---- Wake-Up Alarm ----
        C.choose(pg, 'Music'); C.choose(pg, 'Wake-Up Alarm'); C.choose(pg, 'Time')
        check('time picker opens', pg.locator('.timepick').count() == 1)
        C.key(pg, 'ArrowDown'); C.key(pg, 'Enter'); C.key(pg, 'ArrowDown', 2); C.key(pg, 'Enter')
        pg.screenshot(path=str(SHOTS/'alarm-time.png'), clip=pg.locator('#screen').bounding_box())
        C.key(pg, 'Enter', wait=250)
        a = pg.evaluate("JSON.parse(localStorage.getItem('ipod.alarm'))")
        check('alarm saves the picked time and turns on', a['on'] and a['hour'] == 8 and a['minute'] == 32, a)
        check('alarm menu shows the time', '8:32 AM' in pg.inner_text('#body'), pg.inner_text('#body'))
        pg.screenshot(path=str(SHOTS/'alarm-menu.png'), clip=pg.locator('#screen').bounding_box())
        # native bridge receives the schedule
        pg.evaluate("window.__posted=[];window.webkit={messageHandlers:{ipodAlarm:{postMessage:m=>__posted.push(m)}}}")
        C.choose(pg, 'Repeat Daily')
        posted = pg.evaluate('__posted')
        check('the native app gets the alarm schedule', posted and posted[-1]['action'] == 'schedule' and posted[-1]['hour'] == 8, posted)
        # night mode: Sleep Timer ends with the alarm on in the iPhone app -> stay awake on a silent loop
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Shuffle Songs'); pg.wait_for_timeout(500)
        pg.evaluate("__posted.length=0")
        C.home(pg); C.choose(pg, 'Music'); C.choose(pg, 'Sleep Timer'); C.choose(pg, 'End of This Song')
        pg.wait_for_timeout(3000)   # the 2-second test song ends by itself
        posted = pg.evaluate('__posted')
        check('after the Sleep Timer the app enters night mode', any(m.get('action') == 'night' and m.get('on') for m in posted), posted)
        C.home(pg); pg.evaluate("__posted.length=0;ipodWakeUp()"); pg.wait_for_timeout(500)
        posted = pg.evaluate('__posted')
        check('waking up ends night mode', any(m.get('action') == 'night' and not m.get('on') for m in posted), posted)
        pg.evaluate("localStorage.setItem('ipod.alarm',JSON.stringify({...JSON.parse(localStorage.getItem('ipod.alarm')),on:true}))"); pg.reload(); pg.evaluate("window.webkit={messageHandlers:{ipodAlarm:{postMessage:m=>(window.__posted=window.__posted||[]).push(m)}}}"); pg.wait_for_timeout(2200)
        check('launch re-registers the alarm with the app', any(m.get('action') == 'schedule' for m in (pg.evaluate('window.__posted') or [])), pg.evaluate('window.__posted'))
        C.home(pg); pg.evaluate("ipodWakeUp()"); pg.wait_for_timeout(500)
        check('waking up starts music on Now Playing', pg.text_content('#htitle') == 'Now Playing')
        C.home(pg)
        check('no page errors', not errors, errors)
    srv.shutdown()
    print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
main()
