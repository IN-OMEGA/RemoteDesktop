'use strict';
const $ = id => document.getElementById(id);
let pc, channel, token='', poll, statsTimer, lastStats, latency=0, hostState={}, samples=[], connected=false, busy=false;
let pingTimer, gamepadTimer;
let playbackTimer,audioContext;
let disconnectTimer;
let sessionId='',tunnelSocket=null,tunnelPlayers=[];
let commandSocket=null, access='';
let rtcFallbackTimer;
let requestedDesktopSetup=false;
let lastReport='',lastReportAt=0;
const video=$('video'), screen=$('screen');
const remoteAudio=$('remoteAudio');
const appleMobile=/iPhone|iPad|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
$('compatibility').checked=appleMobile;
$('compatibility').onchange=()=>{if(appleMobile)$('compatibility').checked=true;};
video.muted=true;video.defaultMuted=true;video.playsInline=true;
async function playVideo(){
 if((!video.srcObject&&!video.getAttribute('src'))||!video.paused)return;
 try{await video.play();}
 catch(error){if(video.srcObject&&video.paused){message('Safari retarde la lecture automatique. Nouvelle tentative en cours…');reportClient('playback',error.name);}}
}
video.addEventListener('loadedmetadata',playVideo);
video.addEventListener('canplay',playVideo);
video.addEventListener('playing',()=>reportClient('video-playing'));
video.addEventListener('error',()=>reportClient('video-error',String(video.error?.code||'')));
function unlockAudio(){
 if(!$('audio').checked)return;
 try{
  const Context=window.AudioContext||window.webkitAudioContext;
  if(Context&&!audioContext)audioContext=new Context();
  if(audioContext&&audioContext.state!=='running')audioContext.resume().catch(()=>{});
  if((remoteAudio.srcObject||remoteAudio.getAttribute('src'))&&remoteAudio.paused)remoteAudio.play().catch(()=>{});
 }catch{}
}
// Reuse normal page gestures if iOS temporarily suspends media, without an extra play button.
document.addEventListener('pointerdown',()=>{if(connected){playVideo();unlockAudio();}},{passive:true});
window.addEventListener('pageshow',()=>{if(connected)playVideo();});
if(window.IntersectionObserver)new IntersectionObserver(entries=>{if(connected&&entries.some(e=>e.isIntersecting))playVideo();}).observe(video);
function message(text){$('message').textContent=text;}
async function api(path,body){
 const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),20000);
 let r;
 try{r=await fetch('/api/'+path,{signal:controller.signal,method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,'X-Nexus-Session':sessionId,'X-Nexus-Access':access,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});}
 catch(error){if(error.name==='AbortError')throw new Error('Le PC ne répond pas. Vérifiez le lien et réessayez.');throw error;}
 finally{clearTimeout(deadline);}
 if(!r.ok)throw new Error(await r.text());return r.json();
}
async function unlockRemote(){
 token=$('token').value.trim();
 const password=$('remotePassword').value;
 if(!token||!password)throw new Error('Le code et le mot de passe sont obligatoires.');
 access=(await api('unlock',{code:token,password})).access;
}
function reportClient(event,error=''){
 if(!token)return;
 const data={event,error,connection:pc?.connectionState,ice:pc?.iceConnectionState,signaling:pc?.signalingState,width:video.videoWidth,height:video.videoHeight,paused:video.paused,ready:video.readyState,frames:video.getVideoPlaybackQuality?.().totalVideoFrames,time:Math.round(video.currentTime*100)/100,transport:tunnelSocket?'https':'webrtc'};
 const key=JSON.stringify(data),now=performance.now();if(key===lastReport&&now-lastReportAt<10000)return;
 lastReport=key;lastReportAt=now;api('client-state',data).catch(()=>{});
}
function send(event){if(channel?.readyState==='open'&&(event.type!=='move'||channel.bufferedAmount<16000))channel.send(JSON.stringify(event));}
function release(){send({type:'release'});}
function transportConnected(){return pc?.connectionState==='connected'||tunnelSocket?.readyState===WebSocket.OPEN;}
function controls(){return connected&&transportConnected()&&hostState.control&&$('control').checked&&inputFocused();}
function setState(text,on=false){$('connectionState').textContent=text;$('stateDot').classList.toggle('active',on);$('liveDot').classList.toggle('active',on);$('streamTag').textContent=on?'EN DIRECT':'EN ATTENTE';$('inputToolbar').hidden=!on;}
function reset(){
 window.remoteClipboard?.reset();
 window.sessionTools?.endSession();
 window.neonKeyboard?.close();
 window.playbackGuard?.reset();
 stopControls(false);
 clearTimeout(rtcFallbackTimer);
 release();connected=false;busy=false;clearInterval(poll);clearInterval(statsTimer);clearInterval(pingTimer);clearInterval(gamepadTimer);clearInterval(playbackTimer);clearTimeout(disconnectTimer);
 if(pc){pc.onconnectionstatechange=null;pc.close();pc=null;}channel=null;
 if(tunnelSocket){tunnelSocket.onclose=null;tunnelSocket.close();tunnelSocket=null;}
 if(commandSocket){commandSocket.onclose=null;commandSocket.close();commandSocket=null;}
 for(const player of tunnelPlayers)player.close();tunnelPlayers=[];sessionId='';
 video.srcObject=null;video.style.display='none';$('empty').style.display='flex';lastStats=null;
 remoteAudio.pause();remoteAudio.srcObject=null;
 video.playbackRate=1;remoteAudio.playbackRate=1;
 if(audioContext){audioContext.close().catch(()=>{});audioContext=null;}
 $('connect').disabled=false;$('disconnect').disabled=true;$('profile').disabled=false;$('audio').disabled=false;
 $('quality').disabled=false;$('bandwidth').disabled=false;$('inspect').disabled=false;
 $('compatibility').disabled=appleMobile;
 $('control').checked=false;$('control').disabled=true;$('gamepad').checked=false;$('gamepad').disabled=true;
 setState('Hors connexion');
}
async function disconnect(){try{await api('disconnect',{});}catch{}reset();message('Session terminée.');}
$('disconnect').onclick=disconnect;
$('connectForm').onsubmit=async e=>{
 e.preventDefault();if(busy||connected)return;busy=true;token=$('token').value.trim();
 requestedDesktopSetup=e.isTrusted&&!navigator.webdriver;
 $('token').blur();
 unlockAudio();
 $('connect').disabled=true;$('disconnect').disabled=false;$('profile').disabled=true;$('audio').disabled=true;
 $('quality').disabled=true;$('bandwidth').disabled=true;$('inspect').disabled=true;
 $('compatibility').disabled=true;
 setState('Connexion en cours');message('Validation du code et du mot de passe…');
 try{
  await unlockRemote();
  message('Identifiants validés. Recherche de la connexion la plus rapide…');
  $('remotePassword').value='';
  const initial=await api('status');showDisplay(initial);
  sessionId=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
  const internet=initial.tunnel_required||!isLocalAddress(location.hostname);
  if(internet&&!initial.ice_servers?.length){connectTunnel();return;}
  pc=new RTCPeerConnection({iceServers:internet?(initial.ice_servers||[]):[]});const session=pc;
  session.canFallback=internet;
  const videoTransceiver=pc.addTransceiver('video',{direction:'recvonly'});
  if('jitterBufferTarget' in videoTransceiver.receiver){try{videoTransceiver.receiver.jitterBufferTarget=0;}catch{}}
  const capabilities=RTCRtpReceiver.getCapabilities?.('video');
  let h264=capabilities?.codecs.filter(c=>c.mimeType.toLowerCase()==='video/h264')||[];
  if($('compatibility').checked)h264=h264.filter(c=>c.sdpFmtpLine?.includes('profile-level-id=42e0')&&c.sdpFmtpLine?.includes('packetization-mode=1'));
  const rank=c=>c.sdpFmtpLine?.includes('profile-level-id=64')?0:c.sdpFmtpLine?.includes('profile-level-id=4d')?1:2;
  h264.sort((a,b)=>rank(a)-rank(b));
  if(capabilities&&!h264.length)throw new Error('Aucun profil H.264 compatible annoncé par ce navigateur.');
  if(h264.length&&videoTransceiver.setCodecPreferences)videoTransceiver.setCodecPreferences(h264);
  if($('audio').checked)pc.addTransceiver('audio',{direction:'recvonly'});
  channel=pc.createDataChannel('commands',{ordered:true});
  channel.onmessage=e=>{const data=JSON.parse(e.data);if(data.type==='pong'){latency=performance.now()-data.at;$('latency').innerHTML=Math.round(latency)+' <small>ms</small>';}};
  const stream=new MediaStream(),sound=new MediaStream();
  pc.ontrack=e=>{
   if(pc!==session)return;
   if(e.track.kind==='video'){
    stream.addTrack(e.track);video.srcObject=stream;video.style.display='block';$('empty').style.display='none';
    e.track.onunmute=playVideo;playVideo();
   }else{
    sound.addTrack(e.track);
    remoteAudio.srcObject=sound;remoteAudio.muted=false;
    remoteAudio.play().catch(()=>{});
   }
  };
  pc.onconnectionstatechange=()=>{
   if(pc!==session)return;
   reportClient('connection');
   if(pc.connectionState==='connected'){
    clearTimeout(rtcFallbackTimer);
    clearTimeout(disconnectTimer);
    if(connected){setState('Connecté · WebRTC',true);message('Connexion rétablie.');return;}
    connected=true;busy=false;setState('Connecté · WebRTC',true);message('Connecté. Touchez le bureau ou cliquez dedans pour le contrôler.');
    if(appleMobile)requestAnimationFrame(()=>screen.scrollIntoView({behavior:'smooth',block:'center'}));
    $('control').disabled=false;$('gamepad').disabled=!window.isSecureContext;
    statsTimer=setInterval(receiverStats,1000);poll=setInterval(hostStats,1000);hostStats();
    pingTimer=setInterval(()=>send({type:'ping',at:performance.now()}),500);
    gamepadTimer=setInterval(gamepad,50);
    playVideo();playbackTimer=setInterval(()=>{if(!document.hidden){playVideo();unlockAudio();}},1000);
   }else if(pc.connectionState==='disconnected'){
    release();setState('Reprise de connexion…');message('Réseau momentanément interrompu. Reprise automatique en cours…');
    clearTimeout(disconnectTimer);disconnectTimer=setTimeout(()=>{
     if(pc===session&&session.connectionState!=='connected'){
      api('disconnect',{}).catch(()=>{});reset();message('Le flux réseau ne répond pas. Vérifiez le même Wi-Fi et le pare-feu du PC.');
     }
    },12000);
   }else if(['failed','closed'].includes(pc.connectionState)){
    if(session.canFallback&&pc.connectionState==='failed'&&!connected){fallbackToTunnel(session);return;}
    const failed=pc.connectionState==='failed';reset();
    message(failed?'Connexion vidéo réseau impossible (ICE). Vérifiez le Wi-Fi et le pare-feu du PC.':'Session fermée par le PC hôte.');
   }
  };
  pc.oniceconnectionstatechange=()=>{if(pc===session)reportClient('ice');};
  await pc.setLocalDescription(await pc.createOffer());
  const gathered=await waitForIce(session,2000);
  if(pc!==session)return;
  if(internet&&!gathered){fallbackToTunnel(session);return;}
  message('Code validé. Ouverture automatique du bureau distant…');
  const answer=await api('offer',{sdp:pc.localDescription.sdp,type:'offer',internet,prepare_desktop:requestedDesktopSetup,client_id:sessionId,profile:$('profile').value,audio:$('audio').checked,bitrate_mbps:$('bandwidth').value||null,quality:$('quality').value||null,compatibility:$('compatibility').checked?'safari':null});
  if(pc!==session)return;
  await pc.setRemoteDescription(answer);
  if(session.canFallback&&session.connectionState!=='connected')rtcFallbackTimer=setTimeout(()=>fallbackToTunnel(session),3500);
 }catch(err){reset();message(err.message);}
};

function waitForIce(session,timeout){
 if(session.iceGatheringState==='complete')return Promise.resolve(true);
 return new Promise(resolve=>{
  const finish=()=>{clearTimeout(timer);session.removeEventListener('icegatheringstatechange',changed);resolve(session.iceGatheringState==='complete');};
  const changed=()=>{if(session.iceGatheringState==='complete')finish();};
  const timer=setTimeout(finish,timeout);
  session.addEventListener('icegatheringstatechange',changed);changed();
 });
}
function fallbackToTunnel(session){
 if(pc!==session||session.connectionState==='connected')return;
 clearTimeout(rtcFallbackTimer);session.onconnectionstatechange=null;session.close();pc=null;channel=null;
 message('Connexion directe indisponible. Ouverture du tunnel HTTPS…');connectTunnel();
}
async function hostStats(){
 const owner=sessionId;
 try{
  const result=await api('status');if(owner!==sessionId)return;hostState=result;
  if(connected&&hostState.session_id&&hostState.session_id!==owner){reset();message('Session remplacée par une nouvelle connexion.');return;}
  $('encoder').textContent=hostState.encoder==='h264_nvenc'?'NVENC':'CPU · x264';
  $('encodeTime').textContent=hostState.encode_ms+' ms · '+hostState.encode_fps+' FPS'+(hostState.gpu_encode_utilization!==null?' · GPU '+hostState.gpu_encode_utilization+' %':'');
  $('resolution').textContent=hostState.resolution||'Acquisition…';
  $('codec').textContent=(hostState.encoder==='h264_nvenc'?'NVIDIA NVENC':'Logiciel x264')+' / H.264 '+hostState.codec_profile;
  $('captureInfo').textContent=(hostState.source_resolution||'—')+' · '+hostState.capture_ms+' ms';
  $('hostInfo').textContent=hostState.cpu_percent+' % CPU · '+hostState.memory_mb+' Mo';
  $('audioInfo').textContent=hostState.audio;
  $('frameInfo').textContent=hostState.source_skipped+' source ignorées · '+hostState.pacing_missed+' échéances manquées';
  $('copyInfo').textContent=hostState.copy_path;$('padInfo').textContent=hostState.gamepad;
  $('errorInfo').textContent=hostState.errors.slice(-2).map(e=>e.time+' · '+e.message).join('\n');
  if(!hostState.control&&$('control').checked)stopControls(false);
  samples.push({at:new Date().toISOString(),host:hostState,commandRttMs:latency});if(samples.length>3600)samples.shift();
  if(hostState.session_exists===false&&connected){reset();message('Session terminée par le PC hôte.');}
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
// Pointer, touch and keyboard policies live in controls.js for both transports.
$('gamepad').onchange=release;
function gamepad(){if(!connected||!transportConnected()||!hostState.control||!$('gamepad').checked||document.hidden||!navigator.getGamepads)return;const pad=[...navigator.getGamepads()].find(Boolean);if(pad)send({type:'gamepad',axes:[...pad.axes].slice(0,4),buttons:pad.buttons.map(b=>b.value)});}
function showDisplay(info){const d=info.display;if(!d?.width)return;$('displayHint').textContent=`Écran hôte : ${d.width} × ${d.height} · ${d.refresh_hz} Hz. `+(d.width<3840?'Pour la 4K native, Windows doit proposer un affichage 3840 × 2160.':'Affichage 4K disponible ; cadence à vérifier en direct.');}
$('inspect').onclick=async()=>{token=$('token').value.trim();try{await unlockRemote();showDisplay(await api('status'));message('PC vérifié. Choisissez votre profil, puis connectez-vous.');}catch(err){message(err.message);}};
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({receiver:lastStats,samples},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='remotecore-mesures.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
window.addEventListener('beforeunload',event=>{
 if(!connected&&!busy)return;
 event.preventDefault();event.returnValue='';
});
window.addEventListener('pagehide',event=>{
 release();
 if(!event.persisted){pc?.close();tunnelSocket?.close();commandSocket?.close();}
});

function isLocalAddress(host){
 return host==='localhost'||host==='[::1]'||/^(127\.|10\.|192\.168\.|169\.254\.)/.test(host)||/^172\.(1[6-9]|2\d|3[01])\./.test(host);
}
// Both elements consume the same timestamped MP4: video stays muted for iOS autoplay,
// while the existing audio element handles sound independently of video permission.
function mp4Player(element,mime,onFailure){
 const Source=[window.MediaSource,window.ManagedMediaSource].find(s=>s?.isTypeSupported(mime));
 if(!Source||!Source.isTypeSupported(mime))throw new Error('H.264 en streaming nécessite un navigateur récent (iOS 17.1 ou supérieur sur iPhone).');
 let current,closed=false,header,history=[],historyBytes=0;
 function build(){
  if(current){current.closed=true;URL.revokeObjectURL(current.url);}
  const media=new Source(),url=URL.createObjectURL(media);
  const generation=current={media,url,buffer:null,queue:[],queued:0,closed:false,boot:true};
  element.disableRemotePlayback=true;element.srcObject=null;element.src=url;element.playbackRate=1;
  function pump(){
   const buffer=generation.buffer;if(closed||generation.closed||!buffer||buffer.updating||media.readyState!=='open')return;
   try{
    if(buffer.buffered.length){
     const start=buffer.buffered.start(0),end=buffer.buffered.end(buffer.buffered.length-1);
     if(end>start)try{media.setLiveSeekableRange?.(start,end);}catch{}
     if(generation.boot&&end-start>.15){generation.boot=false;if(start>element.currentTime+.05)element.currentTime=Math.max(start,end-(appleMobile?.35:.1));element.play().catch(()=>{});}
     if(element===video&&!appleMobile)followLiveEdge(element);
     if(element.currentTime>8&&start<element.currentTime-8){buffer.remove(0,element.currentTime-5);return;}
    }
    if(generation.queue.length){const next=generation.queue.shift();generation.queued-=next.byteLength;buffer.appendBuffer(next);}
   }catch(e){if(!generation.closed)onFailure(e);}
  }
  generation.pump=pump;
  media.addEventListener('sourceopen',()=>{
   if(closed||generation.closed||generation.buffer)return;
   try{
    media.duration=Infinity;generation.buffer=media.addSourceBuffer(mime);
    generation.buffer.addEventListener('updateend',pump);
    generation.buffer.addEventListener('error',()=>{if(!generation.closed)onFailure(new Error('Décodage du flux impossible.'));});
    pump();element.play().catch(()=>{});
   }catch(e){if(!generation.closed)onFailure(e);}
  });
  media.addEventListener('startstreaming',()=>{pump();element.play().catch(()=>{});});
 }
 function enqueue(data){
  current.queued+=data.byteLength;
  if(current.queued>8*1024*1024){onFailure(new Error('Connexion trop lente pour le débit choisi. Réduisez le débit puis reconnectez-vous.'));return;}
  current.queue.push(data);current.pump();
 }
 build();
 return {append(data){
   if(closed||!data.byteLength)return;
   if(!header)header=data;
   else{
    history.push({data,at:performance.now()});historyBytes+=data.byteLength;
    while(history.length>1&&(performance.now()-history[0].at>3000||historyBytes>6*1024*1024))historyBytes-=history.shift().data.byteLength;
   }
   enqueue(data);
  },recover(){if(closed||!header)return;build();enqueue(header);for(const chunk of history)enqueue(chunk.data);},
  close(){closed=true;current.closed=true;current.queue=[];history=[];header=null;element.pause();element.removeAttribute('src');element.load();URL.revokeObjectURL(current.url);}};
}
function connectTunnel(){
 if(!(window.ManagedMediaSource||window.MediaSource))throw new Error('Mettez Safari à jour (iOS 17.1 minimum) pour la connexion Internet.');
 const socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/stream`);
 tunnelSocket=socket;socket.binaryType='arraybuffer';let ready=false,received=0,previousBytes=0,previousFrames=0;
 const identity=sessionId;
 const failed=err=>{if(tunnelSocket!==socket)return;reset();message(err.message);};
 const timeout=setTimeout(()=>failed(new Error('Le tunnel ne répond pas. Vérifiez le lien Cloudflare et le PC hôte.')),25000);
 socket.onopen=()=>socket.send(JSON.stringify({token,access,client_id:identity,prepare_desktop:requestedDesktopSetup,profile:$('profile').value,audio:$('audio').checked,
  compatibility:$('compatibility').checked?'safari':null,quality:$('quality').value||null,bitrate_mbps:$('bandwidth').value||null}));
 socket.onmessage=e=>{
  if(tunnelSocket!==socket||sessionId!==identity)return;
  if(e.data instanceof ArrayBuffer){received+=e.data.byteLength;for(const player of tunnelPlayers)player.append(e.data);return;}
  try{
   const data=JSON.parse(e.data);
   if(data.type==='error'){clearTimeout(timeout);failed(new Error(data.message));return;}
   if(data.type==='pong'){latency=performance.now()-data.at;$('latency').innerHTML=Math.round(latency)+' <small>ms</small>';return;}
   if(data.type!=='ready'||ready)return;
   if(data.session_id!==identity)throw new Error('La session a été remplacée.');
   clearTimeout(timeout);ready=true;
   tunnelPlayers=[mp4Player(video,data.mime,failed)];
   if(data.audio){remoteAudio.muted=false;tunnelPlayers.push(mp4Player(remoteAudio,data.mime,failed));}
   channel={readyState:'open',get bufferedAmount(){return socket.bufferedAmount;},send:value=>socket.send(value)};
   connectCommandSocket(identity,channel);
   connected=true;busy=false;setState('Connecté · Tunnel HTTPS',true);
   message(`Bureau connecté via HTTPS · ${data.width} × ${data.height} · ${data.fps} FPS.`+(data.audio?'':' Audio indisponible.'));
   video.style.display='block';$('empty').style.display='none';
   $('control').disabled=false;$('gamepad').disabled=!window.isSecureContext;
   poll=setInterval(hostStats,1000);hostStats();pingTimer=setInterval(()=>send({type:'ping',at:performance.now()}),500);gamepadTimer=setInterval(gamepad,50);
   playbackTimer=setInterval(()=>{
    if(document.hidden)return;
    followLiveEdge(video);
    if(data.audio&&remoteAudio.readyState>=2&&Math.abs(remoteAudio.currentTime-video.currentTime)>.12)remoteAudio.currentTime=video.currentTime;
    if(data.audio)remoteAudio.playbackRate=video.playbackRate;
    playVideo();unlockAudio();
   },100);
   statsTimer=setInterval(()=>{
    const frames=video.getVideoPlaybackQuality?.().totalVideoFrames||0;
    $('fps').innerHTML=Math.max(0,frames-previousFrames)+' <small>FPS</small>';previousFrames=frames;
    $('bitrate').innerHTML=((received-previousBytes)*8/1e6).toFixed(1)+' <small>Mb/s</small>';previousBytes=received;
    $('packetLoss').textContent='Transport : WebSocket sécurisé / TCP';
   },1000);
    if(appleMobile)requestAnimationFrame(()=>screen.scrollIntoView({behavior:'smooth',block:'center'}));
  }catch(err){clearTimeout(timeout);failed(err);}
 };
 socket.onerror=()=>{clearTimeout(timeout);failed(new Error('Connexion au tunnel impossible. Vérifiez le lien Cloudflare.'));};
 socket.onclose=e=>{clearTimeout(timeout);if(tunnelSocket===socket){reset();message(e.code===4001?'Session terminée ou remplacée par une nouvelle connexion.':'Connexion au tunnel interrompue.');}};
}

function followLiveEdge(element){
 if(!element.buffered.length||element.seeking)return;
 const end=element.buffered.end(element.buffered.length-1),behind=end-element.currentTime;
 const now=performance.now(),threshold=appleMobile?1.5:.25,reserve=appleMobile?.35:.08;
 const canSeek=element._nexusSeekAt===undefined||now-element._nexusSeekAt>(appleMobile?5000:500);
 if(behind>threshold&&canSeek){element._nexusSeekAt=now;element.currentTime=Math.max(element.buffered.start(element.buffered.length-1),end-reserve);element.playbackRate=1;}
 else element.playbackRate=behind>(appleMobile?.45:.16)?(appleMobile?1.04:1.12):behind<.05?.98:1;
}

function connectCommandSocket(identity,fallback){
 const socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/control`);
 commandSocket=socket;
 socket.onopen=()=>socket.send(JSON.stringify({token,access,session_id:identity}));
 socket.onmessage=e=>{
  if(commandSocket!==socket||sessionId!==identity)return;
  try{
   const data=JSON.parse(e.data);
   if(data.type==='control-ready'&&data.session_id===identity)
    channel={readyState:'open',get bufferedAmount(){return socket.bufferedAmount;},send:value=>socket.send(value)};
   else if(data.type==='pong'){latency=performance.now()-data.at;$('latency').innerHTML=Math.round(latency)+' <small>ms</small>';}
  }catch{}
 };
 socket.onclose=()=>{if(commandSocket===socket&&sessionId===identity){channel=fallback;commandSocket=null;}};
}
