'use strict';
(()=>{
 const limit=32768,encoder=new TextEncoder();
 let identity='',sequence=null,lastLocal='',localKnown=false,busy=false,copying=false,canRead=false,permissionChecked=false,readRequested=false;
 function active(){return connected&&transportConnected()&&hostState.control&&document.hasFocus()&&!document.hidden&&!!sessionId;}
 function current(id){return active()&&sessionId===id;}
 function reset(){identity='';sequence=null;lastLocal='';localKnown=false;canRead=false;permissionChecked=false;readRequested=false;}
 function begin(){if(identity!==sessionId){reset();identity=sessionId;}return identity;}
 function validate(text){if(typeof text!=='string'||text.includes('\0')||encoder.encode(text).length>limit)throw new Error('Le presse-papiers texte est limité à 32 Ko.');return text;}
 async function put(text,paste,id){
  validate(text);if(!current(id))return;
  const result=await api('clipboard',{text,paste});
  if(current(id)){sequence=result.sequence;lastLocal=text;localKnown=true;}
 }
 function permissions(){
  if(permissionChecked)return;permissionChecked=true;
  navigator.permissions?.query({name:'clipboard-read'}).then(permission=>{
   canRead=permission.state==='granted';permission.onchange=()=>canRead=permission.state==='granted';
  }).catch(()=>{});
 }
 async function sync(gesture=false){
  if(!active()||busy||copying)return;
  const id=begin();busy=true;
  try{
   permissions();
   if(navigator.clipboard?.readText&&((gesture&&!readRequested)||canRead)){
    try{
     readRequested=true;
     const text=validate(await navigator.clipboard.readText());if(!current(id))return;
     if((!localKnown&&text!=='')||(localKnown&&text!==lastLocal)){
      await put(text,false,id);return;
     }
     lastLocal=text;localKnown=true;
    }catch{canRead=false;}
   }
   const result=await api('clipboard'+(sequence===null?'':'?since='+encodeURIComponent(sequence)));
   if(!current(id)||result.sequence===sequence)return;
   if(result.text===null){sequence=result.sequence;return;}
   // Don't acknowledge a blocked write: a later user gesture can retry it.
   if(navigator.clipboard?.writeText){
    await navigator.clipboard.writeText(validate(result.text));
    if(current(id)){sequence=result.sequence;lastLocal=result.text;localKnown=true;}
   }
  }catch{}finally{busy=false;}
 }
 async function paste(){
  if(!active())return;
  const id=begin();
  try{
   if(!navigator.clipboard?.readText)throw new Error('Utilisez « Coller » du navigateur pour transmettre le texte.');
   const text=await navigator.clipboard.readText();
   if(current(id)){await put(text,true,id);screen.focus({preventScroll:true});}
  }catch{message('Autorisez le presse-papiers dans le navigateur, ou utilisez son menu « Coller ».');}
 }
 function captureCopy(){
  if(!active()||copying)return;
  const id=begin();copying=true;
  // ClipboardItem accepts a promise, preserving Safari's user-gesture requirement.
  let captured;const before=sequence;
  const content=new Promise(resolve=>setTimeout(resolve,150)).then(async()=>{
   if(!current(id))throw new Error('Session terminée.');
   let result;
   for(let attempt=0;attempt<10;attempt++){
    if(!current(id))throw new Error('Session terminée.');
    result=await api('clipboard'+(before===null?'':'?since='+encodeURIComponent(before)));
    if(result.text!==null||result.sequence!==before)break;
    await new Promise(resolve=>setTimeout(resolve,100));
   }
   if(!current(id)||result.text===null)throw new Error('Aucun texte à copier sur le PC distant.');
   captured=result;return validate(result.text);
  });
  content.catch(()=>{});
  let write;
  try{
   if(navigator.clipboard?.write&&window.ClipboardItem)
    write=navigator.clipboard.write([new ClipboardItem({'text/plain':content.then(text=>new Blob([text],{type:'text/plain'}))})]);
   else write=content.then(text=>navigator.clipboard.writeText(text));
  }catch(error){write=Promise.reject(error);}
  Promise.resolve(write).then(()=>{
   if(current(id)&&captured){sequence=captured.sequence;lastLocal=captured.text;localKnown=true;}
  }).catch(()=>message('Copie bloquée par le navigateur. Utilisez l’icône presse-papiers et autorisez la copie.'))
   .finally(()=>copying=false);
 }
 function copy(){if(active()){remoteCombo(['ControlLeft','KeyC']);captureCopy();screen.focus({preventScroll:true});}}
 document.addEventListener('paste',event=>{
  if(!active()||!inputFocused()||!event.clipboardData?.types.includes('text/plain'))return;
  event.preventDefault();const id=begin();
  put(event.clipboardData.getData('text/plain'),true,id).catch(()=>message('Impossible de transmettre le presse-papiers.'));
 },true);
 screen.addEventListener('pointerdown',()=>sync(true),{capture:true,passive:true});
 window.addEventListener('focus',()=>sync(false));
 setInterval(()=>sync(false),600);
 window.remoteClipboard={sync,paste,copy,captureCopy,reset};
 const button=document.createElement('button');button.type='button';button.id='toolClipboard';button.title='Presse-papiers partagé';button.setAttribute('aria-label','Presse-papiers partagé');
 button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="5" width="14" height="17" rx="2"/><rect x="9" y="2" width="6" height="5" rx="1"/><path d="M9 12h6m-6 4h6"/></svg>';
 document.querySelector('.session-tools').insertBefore(button,$('toolCmd'));
 button.onclick=()=>{
  const menu=document.querySelector('.tool-menu');menu.replaceChildren();menu.hidden=false;
  for(const [label,action] of [['Coller sur le PC distant',paste],['Copier depuis le PC distant',copy]]){
   const item=document.createElement('button');item.type='button';item.textContent=label;
   item.onclick=()=>{menu.hidden=true;action();};menu.append(item);
  }
 };
})();
