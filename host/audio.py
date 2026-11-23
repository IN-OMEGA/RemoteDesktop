"""WASAPI loopback, 20 ms stereo frames, bounded queue, output-device recovery."""
import asyncio
import threading
import time
from fractions import Fraction
import av
import numpy as np
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError


class LoopbackTrack(MediaStreamTrack):
    kind = 'audio'

    def __init__(self,state):
        super().__init__()
        self.state=state
        self.loop=asyncio.get_running_loop()
        self.queue=asyncio.Queue(maxsize=4)
        self.halt=threading.Event()
        self.thread=threading.Thread(target=self.record,daemon=True)
        self.thread.start()

    def deliver(self,data,stamp):
        if self.halt.is_set():
            return
        if self.queue.full():
            self.queue.get_nowait()
            self.state.metrics['audio_dropped']+=1
        self.queue.put_nowait((data,stamp))

    def record(self):
        # COM is per-thread; soundcard's cached module may have been imported by a prior session.
        import ctypes
        import soundcard  # Its first import initializes COM itself and expects S_OK.
        result=ctypes.windll.ole32.CoInitializeEx(None,0)
        try:self._record()
        finally:
            if result in (0,1):ctypes.windll.ole32.CoUninitialize()

    def _record(self):
        import soundcard as sc
        while not self.halt.is_set():
            try:
                speaker=sc.default_speaker()
                mic=sc.get_microphone(id=speaker.id,include_loopback=True)
                self.state.audio_status=speaker.name
                with mic.recorder(samplerate=48000,channels=2,blocksize=960) as recorder:
                    check=time.monotonic()
                    while not self.halt.is_set():
                        data=recorder.record(numframes=960)
                        stamp=time.perf_counter()-self.state.epoch-.02
                        self.loop.call_soon_threadsafe(self.deliver,data,stamp)
                        if time.monotonic()-check>2:
                            check=time.monotonic()
                            if sc.default_speaker().id!=speaker.id:
                                break
            except Exception as exc:
                self.state.audio_status='Erreur WASAPI : '+str(exc)
                self.state.error(self.state.audio_status)
                self.halt.wait(1)

    async def recv(self):
        if self.readyState!='live':
            raise MediaStreamError
        try:
            data,stamp=await asyncio.wait_for(self.queue.get(),3)
        except asyncio.TimeoutError:
            # No synthetic audio: surface capture failure and keep the video session alive.
            self.stop()
            raise MediaStreamError
        pcm=(np.clip(data,-1,1)*32767).astype(np.int16).reshape(1,-1)
        frame=av.AudioFrame.from_ndarray(pcm,format='s16',layout='stereo')
        frame.sample_rate=48000
        frame.time_base=Fraction(1,48000)
        frame.pts=max(0,int(stamp*48000))
        self.state.metrics['audio_frames']+=1
        return frame

    def stop(self):
        self.halt.set()
        super().stop()
