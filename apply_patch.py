#!/usr/bin/env python3
"""Idempotently upgrade the existing single-file iPod app in-place."""
from pathlib import Path
p=Path(__file__).resolve().parent/'index.html'
if not p.exists():
    raise SystemExit('Copy this handoff into the root of the yartproductions/ipod checkout, then rerun.')
s=p.read_text()
old="if(settings.haptics){let ok=false;try{if(navigator.vibrate)ok=navigator.vibrate(7)}catch(e){}if(!ok)iosTap()}"
new="if(settings.haptics)triggerHaptic('selection')"
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('Haptic code has changed upstream; review manually before patching.')
marker='/* ---------- click + haptics ---------- */'
bridge='''/* Native iOS bridge; browser vibration is best-effort, not a promise of iPhone haptics. */
let lastHapticAt=0;
function triggerHaptic(kind='selection'){
  if(!settings.haptics)return;
  const now=performance.now();
  if(kind==='selection'&&now-lastHapticAt<35)return;
  lastHapticAt=now;
  const bridge=window.webkit?.messageHandlers?.ipodHaptics;
  if(bridge){try{bridge.postMessage(kind);return}catch(e){}}
  try{if(navigator.vibrate?.(kind==='success'?[12,45,12]:7))return}catch(e){}
  // iOS Safari doesn't expose reliable haptic feedback; avoid hidden switch hacks.
}
'''
if 'function triggerHaptic(' not in s:s=s.replace(marker,bridge+'\n'+marker,1)
oldtest="{label:'Test Haptic',action:()=>{for(let k=0;k<3;k++)setTimeout(iosTap,k*120);try{navigator.vibrate&&navigator.vibrate([20,80,20,80,20])}catch(e){}}},"
newtest="{label:'Test Haptic',action:()=>triggerHaptic('success')},"
if oldtest in s:s=s.replace(oldtest,newtest,1)
elif newtest not in s:raise SystemExit('Test haptic menu changed upstream; review manually.')
# iOS native wrapper can distinguish selection from button press.
if "triggerHaptic('confirm')" not in s:
    s=s.replace("function press(btn){\n  click();", "function press(btn){\n  click();\n  if(btn==='select')triggerHaptic('confirm');",1)
p.write_text(s)
print('Patched',p)
