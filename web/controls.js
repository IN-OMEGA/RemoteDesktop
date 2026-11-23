'use strict';
const viewer=screen.closest('.viewer'),remoteKeyboard=$('remoteKeyboard');
let keyboardLocked=false,lockPending=false,controlGeneration=0,helpTimer,escapeTimer,escapeDown=false,escapePresses=[];
let mouseHeld=new Set(),touches=new Map(),gesture=null,dragTimer,exitTouchTimer,latchedKeys=new Set();
let cursor={x:.5,y:.5},lastMouseMove=0;
let helpSeen=false;
try{helpSeen=localStorage.getItem('nexus-input-help-v1')==='seen';}catch{}
const touchCursor=document.createElement('div');touchCursor.className='touch-cursor';touchCursor.hidden=true;screen.append(touchCursor);
touchCursor.innerHTML='<svg viewBox="0 0 28 34" aria-hidden="true"><path d="M3 2v25l6-6 5 11 5-2-5-11h10z" fill="#f4fcff" stroke="#173d5b" stroke-width="1.5" stroke-linejoin="round"/></svg>';
if(appleMobile)$('touchMode').value='trackpad';
video.controls=false;video.disablePictureInPicture=true;
video.setAttribute('controlslist','nofullscreen noremoteplayback nodownload');

function inputFocused(){return document.activeElement===screen||document.activeElement===remoteKeyboard;}
function inputAvailable(){return connected&&transportConnected()&&hostState.control;}
function showInputHelp(force=false,extra=''){
 if(helpSeen&&!force)return;
 helpSeen=true;try{localStorage.setItem('nexus-input-help-v1','seen');}catch{}
 $('inputHelp').textContent=extra||(appleMobile?'Glissez pour déplacer la souris virtuelle, touchez pour cliquer, deux doigts pour défiler. Clavier dans la barre droite.':'Clavier distant : maintenez Échap 2 secondes ou appuyez 3 fois pour libérer les commandes.');
 $('inputHelp').hidden=false;clearTimeout(helpTimer);helpTimer=setTimeout(()=>$('inputHelp').hidden=true,6500);
}
function unlockKeyboard(){controlGeneration++;keyboardLocked=false;lockPending=false;try{navigator.keyboard?.unlock();}catch{}}
async function captureKeyboard(){
 if(appleMobile||keyboardLocked||lockPending||!$('control').checked)return;
 if(!window.isSecureContext||!navigator.keyboard?.lock){
  $('inputToolbar').dataset.keyboard='limited';
  showInputHelp(false,'Capture clavier limitée dans ce navigateur. Pour Ctrl+W et les raccourcis du navigateur, utilisez Chrome/Edge en HTTPS et autorisez la capture en plein écran.');return;
 }
 const generation=controlGeneration;lockPending=true;
 try{
  if(!document.fullscreenElement)await viewer.requestFullscreen();
  if(generation!==controlGeneration||!$('control').checked)return;
  await navigator.keyboard.lock();
  if(generation!==controlGeneration||!$('control').checked){navigator.keyboard.unlock();return;}
  keyboardLocked=true;$('inputToolbar').dataset.keyboard='locked';
  screen.focus({preventScroll:true});showInputHelp();
 }catch{
  $('inputToolbar').dataset.keyboard='limited';
  showInputHelp(false,'Capture clavier non autorisée. Autorisez-la dans Chrome/Edge pour transmettre Ctrl+W. Les boutons de la barre restent disponibles.');
 }finally{if(generation===controlGeneration)lockPending=false;}
}
function activateControls({keyboard=false}={}){
 if(!inputAvailable())return false;
 $('control').checked=true;
 if(!keyboard||!appleMobile)screen.focus({preventScroll:true});
 if(appleMobile)showInputHelp();else if(!keyboard)captureKeyboard();
 return true;
}
function clearGestures(){
 clearTimeout(dragTimer);clearTimeout(exitTouchTimer);touches.clear();gesture=null;
 mouseHeld.clear();touchCursor.hidden=true;
}
function releaseLocalInput(){
 window.neonKeyboard?.releaseHeld();
 release();clearGestures();clearTimeout(escapeTimer);escapeDown=false;escapePresses=[];
 latchedKeys.clear();$('ctrlLatch').setAttribute('aria-pressed','false');$('altLatch').setAttribute('aria-pressed','false');
}
function stopControls(help=false){
 releaseLocalInput();unlockKeyboard();$('control').checked=false;remoteKeyboard.blur();
 viewer.classList.remove('expanded');document.body.classList.remove('viewer-expanded');
 if(document.fullscreenElement===viewer)document.exitFullscreen().catch(()=>{});
 if(document.activeElement===screen)screen.blur();
 if(help)showInputHelp(true,'Commandes libérées. Cliquez dans le bureau pour reprendre. Maintenez Échap 2 s ou appuyez 3 fois pour sortir.');
}
function tapKey(code,logical=false){send({type:'key',code,down:true,logical});send({type:'key',code,down:false,logical});}
function clickButton(button=0){send({type:'button',button,down:true});send({type:'button',button,down:false});}
function remoteCombo(codes){
 for(const code of codes)send({type:'key',code,down:true});
 for(const code of [...codes].reverse())send({type:'key',code,down:false});
}
$('control').onchange=()=>{if($('control').checked)activateControls();else stopControls(false);};
screen.onblur=()=>{if(document.activeElement!==remoteKeyboard)releaseLocalInput();};
screen.onclick=()=>{playVideo();};
screen.onkeydown=e=>{
 if(!controls())return;
 e.preventDefault();e.stopPropagation();
 if((e.ctrlKey||e.metaKey)&&e.code==='KeyV'&&window.remoteClipboard){
  if(!e.repeat)window.remoteClipboard.paste();return;
 }
 if((e.ctrlKey||e.metaKey)&&['KeyC','KeyX'].includes(e.code)&&!e.repeat)
  window.remoteClipboard?.captureCopy();
 if(e.code==='Escape'){
  if(e.repeat||escapeDown)return;
  escapeDown=true;const now=performance.now();escapePresses=escapePresses.filter(t=>now-t<1400);escapePresses.push(now);
  if(escapePresses.length>=3){stopControls(true);return;}
  escapeTimer=setTimeout(()=>{if(escapeDown)stopControls(false);},2000);return;
 }
 send({type:'key',code:e.code,down:true,repeat:e.repeat});
};
screen.onkeyup=e=>{
 if(!controls())return;
 e.preventDefault();e.stopPropagation();
 if(e.code==='Escape'){
  clearTimeout(escapeTimer);if(escapeDown)tapKey('Escape');escapeDown=false;return;
 }
 send({type:'key',code:e.code,down:false});
};
function imageRect(){
 const r=video.getBoundingClientRect(),ratio=video.videoWidth/video.videoHeight;
 if(!Number.isFinite(ratio)||!ratio)return null;
 let w=r.width,h=r.height;if(w/h>ratio)w=h*ratio;else h=w/ratio;
 return {left:r.left+(r.width-w)/2,top:r.top+(r.height-h)/2,width:w,height:h};
}
function placeCursor(x,y,touch=false){
 cursor={x:Math.max(0,Math.min(1,x)),y:Math.max(0,Math.min(1,y))};send({type:'move',...cursor});
 if(touch){touchCursor.hidden=false;renderTouchCursor();}
}
function renderTouchCursor(){const r=imageRect(),s=screen.getBoundingClientRect();if(r){touchCursor.style.left=(r.left-s.left+cursor.x*r.width)+'px';touchCursor.style.top=(r.top-s.top+cursor.y*r.height)+'px';}}
if(window.ResizeObserver)new ResizeObserver(renderTouchCursor).observe(screen);
function movePointer(e,touch=false){
 const r=imageRect();if(!r)return false;
 const x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
 if(x<0||x>1||y<0||y>1)return false;
 placeCursor(x,y,touch);return true;
}
function centroid(){const a=[...touches.values()];return {x:a.reduce((s,p)=>s+p.x,0)/a.length,y:a.reduce((s,p)=>s+p.y,0)/a.length};}
screen.onpointerdown=e=>{
 if(!inputAvailable()||!activateControls())return;
 e.preventDefault();
 screen.setPointerCapture?.(e.pointerId);
 if(e.pointerType!=='touch'){
  if(!movePointer(e))return;
  mouseHeld.add(e.button);send({type:'button',button:e.button,down:true});return;
 }
 touches.set(e.pointerId,{x:e.clientX,y:e.clientY});
 if(touches.size===1){
  gesture={start:{x:e.clientX,y:e.clientY},last:{x:e.clientX,y:e.clientY},at:performance.now(),moved:false,multi:false,drag:false,maxFingers:1,scroll:0};
  if($('touchMode').value==='direct')movePointer(e,true);
  else placeCursor(cursor.x,cursor.y,true);
  dragTimer=setTimeout(()=>{if(gesture&&!gesture.multi&&!gesture.moved&&touches.size===1){gesture.drag=true;send({type:'button',button:0,down:true});}},450);
 }else{
  clearTimeout(dragTimer);
  if(gesture?.drag)send({type:'button',button:0,down:false});
  if(gesture){gesture.drag=false;gesture.multi=true;gesture.maxFingers=Math.max(gesture.maxFingers,touches.size);gesture.last=centroid();}
  if(touches.size===3&&(document.fullscreenElement===viewer||viewer.classList.contains('expanded')))
   exitTouchTimer=setTimeout(()=>stopControls(false),1000);
 }
};
screen.onpointermove=e=>{
 if(!controls())return;
 if(e.pointerType!=='touch'){
  if(performance.now()-lastMouseMove<8)return;lastMouseMove=performance.now();movePointer(e);return;
 }
 if(!touches.has(e.pointerId)||!gesture)return;
 e.preventDefault();touches.set(e.pointerId,{x:e.clientX,y:e.clientY});
 const point=centroid(),dx=point.x-gesture.last.x,dy=point.y-gesture.last.y;
 if(Math.hypot(point.x-gesture.start.x,point.y-gesture.start.y)>7){gesture.moved=true;clearTimeout(exitTouchTimer);if(!gesture.drag)clearTimeout(dragTimer);}
 if(touches.size>=2){
  gesture.scroll+=dy;
  if(Math.abs(gesture.scroll)>=4){send({type:'wheel',delta:Math.round(-gesture.scroll*6)});gesture.scroll=0;gesture.moved=true;}
 }else if(!gesture.multi){
  if($('touchMode').value==='trackpad'){
   const r=imageRect();if(r)placeCursor(cursor.x+dx/r.width,cursor.y+dy/r.height,true);
  }else movePointer(e,true);
 }
 gesture.last=point;
};
screen.onpointerup=e=>{
 if(e.pointerType!=='touch'){
  if(mouseHeld.delete(e.button))send({type:'button',button:e.button,down:false});return;
 }
 if(!touches.has(e.pointerId))return;e.preventDefault();touches.delete(e.pointerId);clearTimeout(dragTimer);clearTimeout(exitTouchTimer);
 if(!gesture)return;
 if(!touches.size){
  if(gesture.drag)send({type:'button',button:0,down:false});
  else if(!gesture.moved&&performance.now()-gesture.at<650)clickButton(gesture.multi?(gesture.maxFingers>=3?1:2):0);
  gesture=null;
 }else gesture.last=centroid();
};
screen.onpointercancel=releaseLocalInput;
screen.onlostpointercapture=e=>{if(touches.has(e.pointerId)||mouseHeld.size)releaseLocalInput();};
screen.oncontextmenu=e=>{if(controls())e.preventDefault();};
screen.addEventListener('wheel',e=>{
 if(!controls())return;e.preventDefault();
 const scale=e.deltaMode===1?36:e.deltaMode===2?600:1;
 send({type:'wheel',delta:Math.round(-e.deltaY*scale),horizontal:Math.round(e.deltaX*scale)});
},{passive:false});
window.addEventListener('blur',releaseLocalInput);
document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseLocalInput();});
document.addEventListener('fullscreenchange',()=>{
 if(document.fullscreenElement!==viewer){releaseLocalInput();unlockKeyboard();$('control').checked=false;}
});
$('fullscreen').onclick=()=>{
 if(document.fullscreenElement===viewer||viewer.classList.contains('expanded')){stopControls(false);return;}
 if(!activateControls())return;
 if(appleMobile||!viewer.requestFullscreen){viewer.classList.add('expanded');document.body.classList.add('viewer-expanded');}
 else if(!navigator.keyboard?.lock)viewer.requestFullscreen().catch(()=>{});
};
$('leaveControls').onclick=()=>stopControls(false);
function openNativeKeyboard(){if(activateControls({keyboard:true})){remoteKeyboard.value='\u200b';remoteKeyboard.focus({preventScroll:true});}}
$('showKeyboard').onclick=openNativeKeyboard;
$('rightClick').onclick=()=>{if(activateControls({keyboard:true}))clickButton(2);};
for(const button of document.querySelectorAll('[data-remote-key],[data-remote-combo]'))button.onclick=()=>{
 if(!activateControls({keyboard:true}))return;
 if(button.dataset.remoteCombo)remoteCombo(button.dataset.remoteCombo.split(','));else tapKey(button.dataset.remoteKey);
};
for(const [id,code] of [['ctrlLatch','ControlLeft'],['altLatch','AltLeft']])$(id).onclick=()=>{
 if(!activateControls({keyboard:true}))return;
 const down=!latchedKeys.has(code);send({type:'key',code,down});
 if(down)latchedKeys.add(code);else latchedKeys.delete(code);
 $(id).setAttribute('aria-pressed',String(down));
};
remoteKeyboard.addEventListener('beforeinput',e=>{
 if(!controls())return;
 const key={deleteContentBackward:'Backspace',deleteContentForward:'Delete',insertLineBreak:'Enter',insertParagraph:'Enter'}[e.inputType];
 if(key){e.preventDefault();tapKey(key);}
});
function sendMobileText(text){
 if(!text||!controls())return;
 // Latched modifiers turn ASCII letters into shortcuts; ordinary text uses Unicode.
 if(latchedKeys.size&&/^[a-z0-9]$/i.test(text))tapKey(/[0-9]/.test(text)?'Digit'+text:'Key'+text.toUpperCase(),true);
 else{
  const characters=Array.from(text);
  for(let at=0;at<characters.length;at+=512)send({type:'text',text:characters.slice(at,at+512).join('')});
 }
 for(const code of latchedKeys)send({type:'key',code,down:false});
 latchedKeys.clear();$('ctrlLatch').setAttribute('aria-pressed','false');$('altLatch').setAttribute('aria-pressed','false');
}
remoteKeyboard.addEventListener('input',e=>{if(!e.isComposing){sendMobileText(remoteKeyboard.value.replace(/^\u200b/,''));remoteKeyboard.value='\u200b';}});
remoteKeyboard.addEventListener('compositionend',()=>{sendMobileText(remoteKeyboard.value.replace(/^\u200b/,''));remoteKeyboard.value='\u200b';});
remoteKeyboard.addEventListener('blur',releaseLocalInput);
// Keep the active viewer above the iOS keyboard without switching to a native video player.
function fitViewport(){viewer.style.setProperty('--viewport-height',(window.visualViewport?.height||innerHeight)+'px');}
window.visualViewport?.addEventListener('resize',fitViewport);fitViewport();
setInterval(()=>{if(controls()||(inputAvailable()&&$('control').checked&&latchedKeys.size))send({type:'keepalive'});},500);
