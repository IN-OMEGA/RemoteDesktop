'use strict';
(()=>{
 const panel=document.createElement('section');panel.className='neon-keyboard';panel.hidden=true;
 panel.setAttribute('aria-label','Clavier distant Nexus');
 panel.innerHTML='<div class="keys-header"><span>NEXUS <b>KEYS</b></span><div><button type="button" data-action="layout" title="Changer de disposition">FR</button><button type="button" data-action="symbols" title="Symboles et accents">é#</button><button type="button" data-action="native" title="Clavier du téléphone">⌨</button><button type="button" data-action="close" title="Masquer le clavier" aria-label="Masquer le clavier">×</button></div></div><div class="keys-grid"></div>';
 viewer.append(panel);
 let shifted=false,layout='FR',symbols=false;
 const held=new Map(),modifiers=new Set();
 const grid=panel.querySelector('.keys-grid');
 function available(){return inputAvailable()&&activateControls({keyboard:true});}
 function focus(){screen.focus({preventScroll:true});}
 function releaseHeld(){
  for(const [id,item] of held){clearTimeout(item.delay);clearInterval(item.repeat);send({type:'key',code:item.code,down:false,logical:true});item.button.classList.remove('key-held');}
  held.clear();
 }
 function clearModifiers(){for(const code of modifiers)send({type:'key',code,down:false});modifiers.clear();}
 function close(){releaseHeld();clearModifiers();panel.hidden=true;viewer.classList.remove('keyboard-open');viewer.style.removeProperty('--keyboard-height');}
 function open(){
  if(!available())return;
  if(appleMobile&&!document.fullscreenElement&&!viewer.classList.contains('expanded')){viewer.classList.add('expanded');document.body.classList.add('viewer-expanded');}
  panel.hidden=false;viewer.classList.add('keyboard-open');focus();fit();
 }
 function fit(){if(!panel.hidden)viewer.style.setProperty('--keyboard-height',(panel.getBoundingClientRect().height+18)+'px');}
 function text(value){
  if(modifiers.size&&/^[a-z0-9]$/i.test(value))tapKey(/\d/.test(value)?'Digit'+value:'Key'+value.toUpperCase(),true);
  else sendMobileText(shifted?value.toUpperCase():value);
  clearModifiers();
  if(shifted){shifted=false;render();}else updateModifiers();
 }
 function updateModifiers(){
  for(const button of grid.querySelectorAll('[data-modifier]'))button.setAttribute('aria-pressed',String(modifiers.has(button.dataset.modifier)));
 }
 function key(row,label,{code,value,modifier,action,wide=false}={}){
  const button=document.createElement('button');button.type='button';button.className='neon-key'+(wide?' key-wide':'');button.textContent=label;
  button.setAttribute('aria-label',label==='⌫'?'Retour arrière':label==='↵'?'Entrée':label);
  if(modifier){button.dataset.modifier=modifier;button.setAttribute('aria-pressed',String(modifiers.has(modifier)));}
  button.onpointerdown=e=>{
   e.preventDefault();e.stopPropagation();if(!available())return;focus();button.setPointerCapture?.(e.pointerId);
   if(modifier){
    const down=!modifiers.has(modifier);send({type:'key',code:modifier,down});
    if(down)modifiers.add(modifier);else modifiers.delete(modifier);updateModifiers();return;
   }
   if(action){action();return;}
   if(value!==undefined){text(value);return;}
   if(code){
    send({type:'key',code,down:true,logical:true});button.classList.add('key-held');
    const item={code,button,delay:null,repeat:null};held.set(e.pointerId,item);
    if(code==='Backspace'||code.startsWith('Arrow'))item.delay=setTimeout(()=>{item.repeat=setInterval(()=>send({type:'key',code,down:true,repeat:true,logical:true}),65);},380);
   }
  };
  const up=e=>{
   const item=held.get(e.pointerId);if(!item)return;
   e.preventDefault();clearTimeout(item.delay);clearInterval(item.repeat);held.delete(e.pointerId);
   send({type:'key',code:item.code,down:false,logical:true});button.classList.remove('key-held');clearModifiers();updateModifiers();
  };
  button.onpointerup=up;button.onpointercancel=up;button.onlostpointercapture=up;
  row.append(button);return button;
 }
 function row(){const result=document.createElement('div');result.className='keys-row';grid.append(result);return result;}
 function render(){
  releaseHeld();grid.replaceChildren();
  let r=row();key(r,'Esc',{code:'Escape'});for(let n=1;n<=12;n++)key(r,'F'+n,{code:'F'+n});
  r=row();for(const value of (shifted?'!@#$%^&*()':'1234567890'))key(r,value,{value});key(r,'⌫',{code:'Backspace',wide:true});
  const letters=symbols?['éèàùçœ€£¥°','@#%&*()[]{}','.,;:!?/\\+-=']:layout==='FR'?['azertyuiop','qsdfghjklm','wxcvbn']:['qwertyuiop','asdfghjkl','zxcvbnm'];
  r=row();key(r,'Tab',{code:'Tab',wide:true});for(const value of letters[0])key(r,shifted?value.toUpperCase():value,{value});
  r=row();for(const value of letters[1])key(r,shifted?value.toUpperCase():value,{value});key(r,'↵',{code:'Enter',wide:true});
  r=row();const shift=key(r,'⇧',{action:()=>{shifted=!shifted;render();},wide:true});shift.setAttribute('aria-pressed',String(shifted));
  for(const value of letters[2])key(r,shifted?value.toUpperCase():value,{value});key(r,'↑',{code:'ArrowUp'});
  r=row();key(r,'Ctrl',{modifier:'ControlLeft'});key(r,'Alt',{modifier:'AltLeft'});key(r,'Win',{modifier:'MetaLeft'});
  const space=key(r,'espace',{value:' ',wide:true});space.classList.add('key-space');
  key(r,'←',{code:'ArrowLeft'});key(r,'↓',{code:'ArrowDown'});key(r,'→',{code:'ArrowRight'});
  fit();
 }
 panel.addEventListener('pointerdown',e=>e.stopPropagation());
 panel.querySelector('[data-action="close"]').onclick=close;
 panel.querySelector('[data-action="layout"]').onclick=e=>{layout=layout==='FR'?'EN':'FR';e.currentTarget.textContent=layout;render();};
 panel.querySelector('[data-action="symbols"]').onclick=()=>{symbols=!symbols;render();};
 panel.querySelector('[data-action="native"]').onclick=()=>{close();openNativeKeyboard();};
 window.addEventListener('blur',()=>{releaseHeld();clearModifiers();updateModifiers();});
 window.addEventListener('resize',fit);
 if(window.ResizeObserver)new ResizeObserver(fit).observe(panel);
 window.neonKeyboard={open,close,toggle:()=>panel.hidden?open():close(),releaseHeld};
 render();
})();
