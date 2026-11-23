'use strict';
const $ = id => document.getElementById(id);
let pc, channel, token='', poll, statsTimer, lastStats, latency=0, hostState={}, samples=[], connected=false, busy=false;
let pingTimer, gamepadTimer;
const video=$('video'), screen=$('screen');
function message(text){$('message').textContent=text;}
async function api(path,body){
 const r=await fetch('/api/'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
 if(!r.ok)throw new Error(await r.text());return r.json();
}
function send(event){if(channel?.readyState==='open'&&channel.bufferedAmount<64000)channel.send(JSON.stringify(event));}
function release(){send({type:'release'});$('controlBadge').hidden=true;}
function controls(){return connected&&hostState.control&&$('control').checked&&document.activeElement===screen;}
function setState(text,on=false){$('connectionState').textContent=text;$('stateDot').classList.toggle('active',on);$('liveDot').classList.toggle('active',on);$('streamTag').textContent=on?'EN DIRECT':'EN ATTENTE';}
function reset(){
 release();connected=false;busy=false;clearInterval(poll);clearInterval(statsTimer);clearInterval(pingTimer);clearInterval(gamepadTimer);
 if(pc){pc.onconnectionstatechange=null;pc.close();pc=null;}channel=null;
 video.srcObject=null;video.style.display='none';$('empty').style.display='flex';lastStats=null;
 $('connect').disabled=false;$('disconnect').disabled=true;$('profile').disabled=false;$('audio').disabled=false;
 $('control').checked=false;$('control').disabled=true;$('gamepad').checked=false;$('gamepad').disabled=true;
 setState('Hors connexion');
}
async function disconnect(){try{await api('disconnect',{});}catch{}reset();message('Session terminée.');}
$('disconnect').onclick=disconnect;
$('connectForm').onsubmit=async e=>{
 e.preventDefault();if(busy||connected)return;busy=true;token=$('token').value.trim();
 $('connect').disabled=true;$('disconnect').disabled=false;$('profile').disabled=true;$('audio').disabled=true;
 setState('Connexion en cours');message('Validation du code…');
 try{
  await api('status');
  pc=new RTCPeerConnection({iceServers:[]});const session=pc;
  const videoTransceiver=pc.addTransceiver('video',{direction:'recvonly'});
  const h264=RTCRtpReceiver.getCapabilities('video').codecs.filter(c=>c.mimeType.toLowerCase()==='video/h264');
  if(!h264.length)throw new Error('Ce navigateur ne propose pas de décodeur H.264. Utilisez Chrome ou Edge.');
  videoTransceiver.setCodecPreferences(h264);
  if($('audio').checked)pc.addTransceiver('audio',{direction:'recvonly'});
  channel=pc.createDataChannel('commands',{ordered:true});
  channel.onmessage=e=>{const data=JSON.parse(e.data);if(data.type==='pong'){latency=performance.now()-data.at;$('latency').innerHTML=Math.round(latency)+' <small>ms</small>';}};
  const stream=new MediaStream();
  pc.ontrack=e=>{stream.addTrack(e.track);video.srcObject=stream;video.style.display='block';$('empty').style.display='none';video.play().catch(()=>message('Cliquez sur l’image pour activer le son.'));};
  pc.onconnectionstatechange=()=>{
   if(pc!==session)return;
   if(pc.connectionState==='connected'){
    connected=true;busy=false;setState('Connecté · WebRTC',true);message('Connecté. Les commandes restent désactivées dans ce navigateur.');
    $('control').disabled=false;$('gamepad').disabled=!window.isSecureContext;
    statsTimer=setInterval(receiverStats,1000);poll=setInterval(hostStats,1000);hostStats();
    pingTimer=setInterval(()=>send({type:'ping',at:performance.now()}),500);
    gamepadTimer=setInterval(gamepad,50);
   }else if(['failed','disconnected','closed'].includes(pc.connectionState)){
    reset();message('Connexion interrompue. Reconnectez-vous après vérification de l’hôte.');
   }
  };
  await pc.setLocalDescription(await pc.createOffer());
  if(pc.iceGatheringState!=='complete')await new Promise(resolve=>{const fn=()=>{if(session.iceGatheringState==='complete'){session.removeEventListener('icegatheringstatechange',fn);resolve();}};session.addEventListener('icegatheringstatechange',fn);});
  message('Acceptez la demande dans la fenêtre RemoteCore sur le PC hôte.');
  const answer=await api('offer',{sdp:pc.localDescription.sdp,type:'offer',profile:$('profile').value,audio:$('audio').checked});
  if(pc!==session)return;
  await pc.setRemoteDescription(answer);
 }catch(err){reset();message(err.message);}
};
async function hostStats(){
 try{
  hostState=await api('status');
  $('encoder').textContent=hostState.encoder==='h264_nvenc'?'NVENC':'CPU · x264';
  $('encodeTime').textContent=hostState.encode_ms+' ms · '+hostState.encode_fps+' FPS'+(hostState.gpu_encode_utilization!==null?' · GPU '+hostState.gpu_encode_utilization+' %':'');
  $('resolution').textContent=hostState.resolution||'Acquisition…';
  $('codec').textContent=(hostState.encoder==='h264_nvenc'?'NVIDIA NVENC':'Logiciel x264')+' / H.264';
  $('captureInfo').textContent=(hostState.source_resolution||'—')+' · '+hostState.capture_ms+' ms';
  $('hostInfo').textContent=hostState.cpu_percent+' % CPU · '+hostState.memory_mb+' Mo';
  $('audioInfo').textContent=hostState.audio;
  $('frameInfo').textContent=hostState.source_skipped+' source ignorées · '+hostState.pacing_missed+' échéances manquées';
  $('copyInfo').textContent=hostState.copy_path;$('padInfo').textContent=hostState.gamepad;
  $('errorInfo').textContent=hostState.errors.slice(-2).map(e=>e.time+' · '+e.message).join('\n');
  if(!hostState.control){release();$('control').checked=false;}
  samples.push({at:new Date().toISOString(),host:hostState,commandRttMs:latency});if(samples.length>3600)samples.shift();
  if(!hostState.active&&connected){reset();message('Session terminée par le PC hôte.');}
 }catch(err){message(err.message);}
}
async function receiverStats(){
 if(!pc)return;
 const stats=await pc.getStats();
 for(const r of stats.values())if(r.type==='inbound-rtp'&&r.kind==='video'){
  let fps=r.framesPerSecond||0,mbps=0;
  if(lastStats){const dt=(r.timestamp-lastStats.timestamp)/1000;mbps=(r.bytesReceived-lastStats.bytesReceived)*8/dt/1e6;if(!fps)fps=(r.framesDecoded-lastStats.framesDecoded)/dt;}
  lastStats=r;
  $('fps').innerHTML=Math.round(fps)+' <small>FPS</small>';$('bitrate').innerHTML=mbps.toFixed(1)+' <small>Mb/s</small>';
  $('packetLoss').textContent='Pertes : '+(r.packetsLost||0)+' · décodage ignoré : '+(r.framesDropped||0);
  const bar=document.createElement('i');bar.style.height=Math.max(1,Math.min(12,fps/10))+'px';$('spark').append(bar);if($('spark').children.length>25)$('spark').firstChild.remove();
 }
}
$('control').onchange=()=>{release();if($('control').checked){screen.focus();message('Commandes activées. Cliquez dans l’image ; Échap pour libérer.');}else message('Commandes désactivées dans ce navigateur.');};
screen.onclick=()=>{video.play().catch(()=>{});if($('control').checked)screen.focus();};
screen.onfocus=()=>{$('controlBadge').hidden=!controls();};screen.onblur=release;
screen.onkeydown=e=>{if(e.code==='Escape'){e.preventDefault();release();$('control').checked=false;screen.blur();return;}if(!controls())return;e.preventDefault();send({type:'key',code:e.code,down:true});};
screen.onkeyup=e=>{if(!controls())return;e.preventDefault();send({type:'key',code:e.code,down:false});};
let lastMove=0;
screen.onpointermove=e=>{if(!controls()||performance.now()-lastMove<8)return;lastMove=performance.now();const r=video.getBoundingClientRect();const ratio=video.videoWidth/video.videoHeight;let w=r.width,h=r.height;if(w/h>ratio)w=h*ratio;else h=w/ratio;const x=(e.clientX-r.left-(r.width-w)/2)/w,y=(e.clientY-r.top-(r.height-h)/2)/h;if(x>=0&&x<=1&&y>=0&&y<=1)send({type:'move',x,y});};
screen.onpointerdown=e=>{if(!controls())return;e.preventDefault();screen.setPointerCapture(e.pointerId);send({type:'button',button:e.button,down:true});};
screen.onpointerup=e=>{if(!controls())return;e.preventDefault();send({type:'button',button:e.button,down:false});};
screen.oncontextmenu=e=>{if(controls())e.preventDefault();};
screen.addEventListener('wheel',e=>{if(!controls())return;e.preventDefault();send({type:'wheel',delta:-Math.sign(e.deltaY)*120});},{passive:false});
window.addEventListener('blur',release);document.addEventListener('visibilitychange',()=>{if(document.hidden)release();});
$('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else screen.requestFullscreen().catch(e=>message(e.message));};
$('gamepad').onchange=release;
function gamepad(){if(!connected||!hostState.control||!$('gamepad').checked||document.hidden||!navigator.getGamepads)return;const pad=[...navigator.getGamepads()].find(Boolean);if(pad)send({type:'gamepad',axes:[...pad.axes].slice(0,4),buttons:pad.buttons.map(b=>b.value)});}
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({receiver:lastStats,samples},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='remotecore-mesures.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
window.addEventListener('beforeunload',()=>{release();pc?.close();});
