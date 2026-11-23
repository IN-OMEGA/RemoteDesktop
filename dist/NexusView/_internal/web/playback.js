'use strict';
(()=>{
 let lastProgress=performance.now(),lastTime=0,lastRepair=0,repairs=0,callbackFrames=0,lastCallbackFrames=0;
 function frame(){callbackFrames++;video.requestVideoFrameCallback(frame);}
 if(video.requestVideoFrameCallback)video.requestVideoFrameCallback(frame);
 function reset(){lastProgress=performance.now();lastTime=0;repairs=0;lastCallbackFrames=callbackFrames;lastRepair=0;}
 async function repair(){
  lastRepair=performance.now();lastProgress=lastRepair;repairs++;reportClient('video-recovery',String(repairs));
  send({type:'video-refresh'});
  if(video.srcObject){
   const stream=video.srcObject;video.pause();video.srcObject=null;video.srcObject=stream;await playVideo();
  }else{
   for(const player of tunnelPlayers)player.recover();
   await playVideo();
  }
 }
 setInterval(()=>{
  if(!connected||document.hidden||!video.videoWidth){lastProgress=performance.now();return;}
  const progressed=video.requestVideoFrameCallback?callbackFrames!==lastCallbackFrames:video.currentTime>lastTime+.03;
  if(progressed){lastProgress=performance.now();lastTime=video.currentTime;lastCallbackFrames=callbackFrames;return;}
  if(performance.now()-lastProgress>2500&&performance.now()-lastRepair>6000)repair().catch(()=>{});
 },500);
 window.playbackGuard={reset,repair};
})();
