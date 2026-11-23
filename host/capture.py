import asyncio
import ctypes as ct
import time
import threading
import multiprocessing as mp
from multiprocessing import shared_memory
from fractions import Fraction
from concurrent.futures import ThreadPoolExecutor
import av
import numpy as np
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError


class NativeCapture:
    def __init__(self, path, width=1920, height=1080, use_nv12=True):
        self.dll = ct.CDLL(str(path))
        self.dll.rc_create.restype = ct.c_void_p
        self.dll.rc_destroy.argtypes = [ct.c_void_p]
        self.dll.rc_error.argtypes = [ct.c_void_p]
        self.dll.rc_error.restype = ct.c_char_p
        self.dll.rc_frame.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_uint,
                                     ct.POINTER(ct.c_uint), ct.POINTER(ct.c_uint), ct.POINTER(ct.c_uint)]
        self.dll.rc_size.argtypes = [ct.c_void_p,ct.c_uint,ct.c_uint]
        self.dll.rc_source_width.argtypes=[ct.c_void_p]
        self.dll.rc_source_height.argtypes=[ct.c_void_p]
        self.dll.rc_source_width.restype=ct.c_uint
        self.dll.rc_source_height.restype=ct.c_uint
        self.dll.rc_format.argtypes=[ct.c_void_p]
        self.dll.rc_format.restype=ct.c_uint
        self.dll.rc_prefer_nv12.argtypes=[ct.c_void_p,ct.c_uint]
        self.handle = self.dll.rc_create()
        self.lock = threading.Lock()
        if not self.handle:
            raise MemoryError('DXGI capture')
        self.dll.rc_size(self.handle,width,height)
        self.dll.rc_prefer_nv12(self.handle,int(use_nv12))
        self.pixel_format='bgra'
        self.buffer = np.empty(1920*1080*4, dtype=np.uint8)

    def read(self, copy=True):
        with self.lock:
            return self._read(copy)

    def _read(self, copy=True):
        if not self.handle:
            return None,0
        w,h,n = ct.c_uint(),ct.c_uint(),ct.c_uint()
        status = self.dll.rc_frame(self.handle, self.buffer.ctypes.data, self.buffer.nbytes,
                                   ct.byref(w),ct.byref(h),ct.byref(n))
        if status == -2:
            self.buffer = np.empty(w.value*h.value*4, dtype=np.uint8)
            return self._read(copy)
        if status < 0:
            raise RuntimeError(self.dll.rc_error(self.handle).decode())
        if status == 0:
            return None, 0
        self.pixel_format='nv12' if self.dll.rc_format(self.handle) else 'bgra'
        if self.pixel_format=='nv12':image=self.buffer[:w.value*h.value*3//2].reshape(h.value*3//2,w.value)
        else:image=self.buffer[:w.value*h.value*4].reshape(h.value,w.value,4)
        return image.copy() if copy else image, n.value

    def close(self):
        with self.lock:
            if self.handle:
                self.dll.rc_destroy(self.handle)
                self.handle = None


def capture_worker(path,width,height,connection,name,use_nv12):
    """Isolate Optimus DXGI from FFmpeg's CUDA context in the encoder process."""
    memory=shared_memory.SharedMemory(name=name)
    capture=None
    try:
        capture=NativeCapture(path,width,height,use_nv12)
        capture.buffer=np.ndarray((width*height*4,),dtype=np.uint8,buffer=memory.buf)
        while True:
            command=connection.recv()
            if command=='stop':break
            try:
                slot=int(command[1])
                capture.buffer=np.ndarray((width*height*4,),dtype=np.uint8,buffer=memory.buf,offset=slot*width*height*4)
                start=time.perf_counter()
                image,accumulated=capture.read(copy=False)
                native_ms=(time.perf_counter()-start)*1000
                size=(capture.dll.rc_source_width(capture.handle),capture.dll.rc_source_height(capture.handle))
                connection.send((None if image is None else image.shape,accumulated,None,size,capture.pixel_format,slot,native_ms))
            except Exception as exc:connection.send((None,0,str(exc),(0,0),'bgra',0,0))
    except (EOFError,BrokenPipeError):pass
    finally:
        if capture:capture.close();capture.buffer=None
        memory.close();connection.close()


class IsolatedCapture:
    def __init__(self,path,width,height,use_nv12=True):
        self.slot_bytes=width*height*4
        self.memory=shared_memory.SharedMemory(create=True,size=self.slot_bytes*2)
        self.next_slot=0
        context=mp.get_context('spawn')
        self.connection,child=context.Pipe()
        self.process=context.Process(target=capture_worker,args=(str(path),width,height,child,self.memory.name,use_nv12),daemon=True)
        self.process.start();child.close()
        self.lock=threading.Lock()
        self.closed=False
        self.source_size=(0,0)
        self.pixel_format='bgra'
        self.last_capture_ms=0

    def read(self):
        with self.lock:
            if self.closed:return None,0
            self.connection.send(('frame',self.next_slot))
            if not self.connection.poll(5):raise RuntimeError('Le processus DXGI ne répond pas.')
            shape,accumulated,error,self.source_size,self.pixel_format,slot,self.last_capture_ms=self.connection.recv()
            if error:raise RuntimeError(error)
            if shape is None:return None,0
            self.next_slot=1-slot
            # Two slots allow acquisition of N+1 while NVENC reads N, without tearing/copying.
            return np.ndarray(shape,dtype=np.uint8,buffer=self.memory.buf,offset=slot*self.slot_bytes),accumulated

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True
            try:self.connection.send('stop')
            except (EOFError,BrokenPipeError,OSError):pass
            self.process.join(3)
            if self.process.is_alive():self.process.terminate();self.process.join(2)
            self.connection.close();self.memory.close();self.memory.unlink()


class DesktopTrack(MediaStreamTrack):
    kind = 'video'

    def __init__(self, state):
        super().__init__()
        self.state = state
        capture_width,capture_height=getattr(state,'capture_envelope',(state.profile['width'],state.profile['height']))
        self.native = IsolatedCapture(state.native_path,capture_width,capture_height,getattr(state,'use_gpu_conversion',True))
        self.executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix='DXGI')
        self.previous = None
        self.started = time.perf_counter()
        self.next_frame = self.started
        self.retries = 0
        self.pending=None
        # Windows' default timer granularity otherwise adds jitter to 60/120 FPS pacing.
        self.timer_active=ct.windll.winmm.timeBeginPeriod(1)==0

    async def recv(self):
        fps = self.state.profile['fps']
        await asyncio.sleep(max(0,self.next_frame-time.perf_counter()))
        now = time.perf_counter()
        missed = max(0,int((now-self.next_frame)*fps))
        self.state.metrics['pacing_missed'] += missed
        self.next_frame = max(self.next_frame+1/fps,now)
        while self.readyState == 'live':
            t = time.perf_counter()
            try:
                future=self.pending or asyncio.get_running_loop().run_in_executor(self.executor,self.native.read)
                self.pending=None
                # A slow GPU readback must not stall the media clock and build a latency queue.
                # Keep at most one native read; repeat the last real desktop image meanwhile.
                if self.previous is not None and not future.done():
                    await asyncio.wait([future],timeout=min(.008,1/fps/4))
                if self.previous is not None and not future.done():
                    self.pending=future;image,accumulated=None,0
                else:image,accumulated=await future
                self.state.metrics['capture_wait_ms'] = round((time.perf_counter()-t)*1000,2)
                self.state.metrics['capture_ms'] = round(self.native.last_capture_ms,2)
                if image is not None:
                    self.previous = image
                    self.state.metrics['source_frames'] += 1
                    self.state.metrics['source_skipped'] += max(0,accumulated-1)
                    self.state.metrics['source_resolution'] = f'{self.native.source_size[0]} × {self.native.source_size[1]}'
                    self.retries = 0
                if self.previous is None:
                    await asyncio.sleep(.01)
                    continue
                frame = av.VideoFrame.from_numpy_buffer(self.previous,format=self.native.pixel_format)
                self.state.metrics['pixel_format']=self.native.pixel_format
                width,height = self.state.profile['width'],self.state.profile['height']
                # Scaling/rotation already happened on GPU; this only converts BGRA to encoder YUV.
                scale = min(width/frame.width,height/frame.height)
                out_w,out_h = max(2,int(frame.width*scale)//2*2),max(2,int(frame.height*scale)//2*2)
                # Never upscale beyond the native desktop; profile sizes are upper bounds.
                scale=min(1,scale)
                out_w,out_h=max(2,int(frame.width*scale)//2*2),max(2,int(frame.height*scale)//2*2)
                if frame.format.name!='nv12' or frame.width!=out_w or frame.height!=out_h:
                    frame = await asyncio.to_thread(frame.reformat,width=out_w,height=out_h,format='nv12')
                frame.time_base = Fraction(1,90000)
                frame.colorspace=1
                frame.color_range=1
                frame.pts = int((time.perf_counter()-self.state.epoch)*90000)
                self.state.metrics['resolution'] = f'{out_w} × {out_h}'
                self.state.metrics['frames'] += 1
                # Bound buffering to exactly one future image; never queue stale desktop frames.
                if self.pending is None:self.pending=asyncio.get_running_loop().run_in_executor(self.executor,self.native.read)
                return frame
            except Exception as exc:
                self.state.error('Capture : '+str(exc))
                self.previous = None
                self.retries += 1
                if self.retries > 15:
                    self.stop()
                    raise MediaStreamError
                await asyncio.sleep(.5)  # recreate DXGI after mode changes / lost device
        raise MediaStreamError

    def stop(self):
        super().stop()
        # recv() can be inside a native read on a worker thread; close after the read completes.

    def close_native(self):
        self.executor.shutdown(wait=True,cancel_futures=True)
        self.pending=None;self.previous=None
        self.native.close()
        if self.timer_active:
            ct.windll.winmm.timeEndPeriod(1);self.timer_active=False
