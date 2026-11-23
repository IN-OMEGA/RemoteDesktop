'use strict';
(()=>{
 const svg=body=>`<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
 const icons={camera:svg('<path d="M4 6h4l2-3h4l2 3h4v14H4z"/><circle cx="12" cy="12" r="4"/>'),record:svg('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3" fill="currentColor"/>'),cmd:svg('<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m6 9 3 3-3 3m6 0h5"/>'),classroom:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="1" y="2" width="22" height="20" rx="2" fill="#f6bf26"/><path fill="#0f9d58" d="M3 4h18v15H3z"/><circle cx="12" cy="10" r="2.1" fill="white"/><path d="M8 17v-2a4 3 0 0 1 8 0v2" fill="white"/><path d="M5 14h3v3H5zm11 0h3v3h-3" fill="#a6e3bc"/></svg>',hide:svg('<path d="m9 5 7 7-7 7"/>'),stop:svg('<rect x="6" y="6" width="12" height="12" rx="1"/>')};
 const dock=document.createElement('aside');dock.className='session-tools';dock.setAttribute('aria-label','Outils de session');
 dock.innerHTML=`<button type="button" id="toolCapture" title="Capture d’écran" aria-label="Capture d’écran">${icons.camera}</button><button type="button" id="toolRecord" title="Enregistrer l’écran" aria-label="Enregistrer l’écran">${icons.record}</button><button type="button" id="toolCmd" title="Ouvrir CMD sur le PC distant" aria-label="Ouvrir CMD sur le PC distant">${icons.cmd}</button><button type="button" id="toolClassroom" title="Ouvrir Google Classroom dans Chrome" aria-label="Ouvrir Google Classroom dans Chrome">${icons.classroom}</button><button type="button" id="toolHide" title="Masquer la barre" aria-label="Masquer la barre">${icons.hide}</button>`;
 const menu=document.createElement('div');menu.className='tool-menu';menu.hidden=true;
 const reveal=document.createElement('button');reveal.type='button';reveal.className='tools-reveal';reveal.title='Afficher les outils';reveal.setAttribute('aria-label','Afficher les outils');reveal.innerHTML=svg('<path d="m15 5-7 7 7 7"/>');reveal.hidden=true;
 const toast=document.createElement('div');toast.className='tool-toast';toast.hidden=true;toast.setAttribute('role','status');
 viewer.append(dock,menu,reveal,toast);
 const keyboardButton=document.createElement('button');keyboardButton.type='button';keyboardButton.id='toolKeyboard';keyboardButton.title='Clavier rétroéclairé';keyboardButton.setAttribute('aria-label','Clavier rétroéclairé');
 keyboardButton.innerHTML=svg('<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M5 9h1m3 0h1m3 0h1m3 0h1M5 12h1m3 0h1m3 0h1m3 0h1M7 16h10"/>');
 dock.insertBefore(keyboardButton,$('toolCmd'));keyboardButton.onclick=()=>window.neonKeyboard?.toggle();
 let dwellTimer,toastTimer,selection=null,recording=null;
 function fullscreen(){return document.fullscreenElement===viewer||viewer.classList.contains('expanded');}
 function notify(text){message(text);toast.textContent=text;toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.hidden=true,4000);}
 function error(err){notify(err.message||String(err));}
 function clearDwell(){clearTimeout(dwellTimer);dwellTimer=null;reveal.hidden=true;}
 function hideTools(){clearDwell();viewer.classList.add('tools-hidden');menu.hidden=true;screen.focus({preventScroll:true});}
 $('toolHide').onclick=hideTools;
 reveal.onclick=()=>{viewer.classList.remove('tools-hidden');clearDwell();screen.focus({preventScroll:true});};
 window.addEventListener('pointermove',e=>{
  const r=viewer.getBoundingClientRect(),vp=window.visualViewport;
  const right=Math.min(r.right,(vp?.offsetLeft||0)+(vp?.width||innerWidth));
  const top=Math.max(r.top,vp?.offsetTop||0),bottom=Math.min(r.bottom,(vp?.offsetTop||0)+(vp?.height||innerHeight));
  const edge=e.clientX>=right-48&&e.clientX<=right&&e.clientY>=top&&e.clientY<=bottom;
  if(!fullscreen()||!viewer.classList.contains('tools-hidden')||!edge){clearDwell();return;}
  // Keep the handle reachable even with a virtual keyboard or a clipped viewport.
  reveal.style.top=Math.max(top-r.top+4,Math.min(bottom-r.top-46,e.clientY-r.top-21))+'px';
  reveal.style.bottom='auto';reveal.style.right=Math.max(4,r.right-right+4)+'px';
  if(!dwellTimer)dwellTimer=setTimeout(()=>{
   dwellTimer=null;
   if(fullscreen()&&viewer.classList.contains('tools-hidden'))reveal.hidden=false;
  },2000);
 },{capture:true,passive:true});
 window.addEventListener('blur',clearDwell);
 document.documentElement.addEventListener('pointerleave',clearDwell);
 function choose(kind){
  if(!connected||!video.videoWidth)return;
  if(kind==='record'&&recording){stopRecording();return;}
  menu.replaceChildren();menu.hidden=false;
  for(const [label,region] of [['Tout l’écran',false],['Sélectionner une zone',true]]){
   const button=document.createElement('button');button.type='button';button.textContent=label;
   button.onclick=()=>{menu.hidden=true;const action=rect=>Promise.resolve(kind==='capture'?capture(rect):startRecording(rect)).then(()=>screen.focus({preventScroll:true})).catch(error);if(region)selectRegion(action);else action({x:0,y:0,w:1,h:1});};menu.append(button);
  }
 }
 $('toolCapture').onclick=()=>choose('capture');$('toolRecord').onclick=()=>choose('record');
 for(const [id,action] of [['toolCmd','cmd'],['toolClassroom','classroom']])$(id).onclick=async()=>{
  try{await api('action',{action});screen.focus({preventScroll:true});}catch(err){error(err);}
 };
 document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target)&&!dock.contains(e.target))menu.hidden=true;},true);
 function download(blob,extension,prefix){
  const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`Nexus-${prefix}-${new Date().toISOString().replace(/[:.]/g,'-')}.${extension}`;viewer.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
 }
 function frameCanvas(rect){
  if(!video.videoWidth||video.readyState<2)throw new Error('Le bureau distant ne fournit pas encore d’image.');
  const canvas=document.createElement('canvas');canvas.width=Math.max(2,Math.round(rect.w*video.videoWidth));canvas.height=Math.max(2,Math.round(rect.h*video.videoHeight));
  const context=canvas.getContext('2d',{alpha:false});
  const draw=()=>context.drawImage(video,rect.x*video.videoWidth,rect.y*video.videoHeight,rect.w*video.videoWidth,rect.h*video.videoHeight,0,0,canvas.width,canvas.height);
  draw();return {canvas,draw};
 }
 async function capture(rect){
  const {canvas}=frameCanvas(rect);
  const blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('Capture impossible.')),'image/png'));
  download(blob,'png','capture');
 }
 function selectRegion(callback){
  cancelSelection();releaseLocalInput();
  const layer=document.createElement('div');layer.className='region-selector';layer.setAttribute('aria-label','Dessinez la zone de capture. Échap pour annuler.');
  const box=document.createElement('div');box.className='region-box';layer.append(box);viewer.append(layer);
  let start;
  function point(e){const r=imageRect();if(!r)throw new Error('Image indisponible');return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))};}
  const rectangle=end=>({x:Math.min(start.x,end.x),y:Math.min(start.y,end.y),w:Math.abs(start.x-end.x),h:Math.abs(start.y-end.y)});
  layer.onpointerdown=e=>{e.preventDefault();e.stopPropagation();start=point(e);layer.setPointerCapture(e.pointerId);};
  layer.onpointermove=e=>{if(!start)return;e.preventDefault();const r=rectangle(point(e)),image=imageRect(),base=viewer.getBoundingClientRect();Object.assign(box.style,{left:(image.left-base.left+r.x*image.width)+'px',top:(image.top-base.top+r.y*image.height)+'px',width:r.w*image.width+'px',height:r.h*image.height+'px'});};
  layer.onpointerup=e=>{if(!start)return;e.preventDefault();e.stopPropagation();const rect=rectangle(point(e));cancelSelection();if(rect.w*video.videoWidth<8||rect.h*video.videoHeight<8){notify('Sélection trop petite.');return;}callback(rect);screen.focus({preventScroll:true});};
  selection={layer};
 }
 function cancelSelection(){selection?.layer.remove();selection=null;}
 document.addEventListener('keydown',e=>{if(selection&&e.code==='Escape'){e.preventDefault();e.stopImmediatePropagation();cancelSelection();}},true);
 async function startRecording(rect){
  if(recording)throw new Error('Un enregistrement est déjà en cours.');
  if(!window.MediaRecorder)throw new Error('Ce navigateur ne prend pas en charge l’enregistrement.');
  const {canvas,draw}=frameCanvas(rect);
  if(!canvas.captureStream)throw new Error('Enregistrement non disponible dans ce navigateur.');
  const fps=Math.min(60,Math.max(15,Math.round(hostState.fps||30))),stream=canvas.captureStream(fps);
  // Reuse existing received tracks; never capture the controller's microphone or desktop.
  let sound=remoteAudio.srcObject;
  if(!sound&&remoteAudio.captureStream)try{sound=remoteAudio.captureStream();}catch{}
  for(const track of sound?.getAudioTracks?.()||[])stream.addTrack(track.clone());
  const mime=['video/mp4','video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'].find(t=>MediaRecorder.isTypeSupported(t));
  if(!mime){stream.getTracks().forEach(t=>t.stop());throw new Error('Aucun format d’enregistrement compatible.');}
  let recorder;
  try{recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:12_000_000});}catch(err){stream.getTracks().forEach(t=>t.stop());throw err;}
  const session={recorder,stream,chunks:[],bytes:0,draw,timer:null};recording=session;
  recorder.ondataavailable=e=>{if(e.data.size){session.chunks.push(e.data);session.bytes+=e.data.size;if(session.bytes>512*1024*1024){notify('Limite mémoire atteinte : enregistrement téléchargé.');stopRecording();}}};
  recorder.onstop=()=>{
   clearInterval(session.timer);stream.getTracks().forEach(t=>t.stop());
   if(recording===session)recording=null;
   $('toolRecord').innerHTML=icons.record;$('toolRecord').classList.remove('recording');$('toolRecord').title='Enregistrer l’écran';
   if(session.chunks.length)download(new Blob(session.chunks,{type:recorder.mimeType}),recorder.mimeType.includes('mp4')?'mp4':'webm','enregistrement');
  };
  recorder.onerror=e=>{error(e.error||new Error('Erreur d’enregistrement'));stopRecording();};
  try{recorder.start(1000);}catch(err){recording=null;stream.getTracks().forEach(t=>t.stop());throw err;}
  session.timer=setInterval(()=>{if(video.readyState>=2)draw();},1000/fps);
  $('toolRecord').innerHTML=icons.stop;$('toolRecord').classList.add('recording');$('toolRecord').title='Arrêter et télécharger';
  if(!stream.getAudioTracks().length&&$('audio').checked)notify('Enregistrement vidéo démarré sans son : capture audio non disponible dans ce navigateur.');
 }
 function stopRecording(){if(recording&&recording.recorder.state!=='inactive')recording.recorder.stop();}
 window.sessionTools={capture,startRecording,stopRecording,selectRegion,hideTools,endSession(){stopRecording();cancelSelection();menu.hidden=true;reveal.hidden=true;viewer.classList.remove('tools-hidden');clearTimeout(dwellTimer);dwellTimer=null;}};
 new MutationObserver(()=>{if(!fullscreen()){clearTimeout(dwellTimer);dwellTimer=null;reveal.hidden=true;menu.hidden=true;}}).observe(viewer,{attributes:true,attributeFilter:['class']});
})();
