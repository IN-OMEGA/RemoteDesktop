"""Low latency fragmented H.264/AAC MP4 for same-origin HTTPS WebSockets."""
import asyncio
from fractions import Fraction
import time
import logging
import re
import av
from concurrent.futures import ThreadPoolExecutor


class Sink:
    def __init__(self):self.data=bytearray();self.position=0
    def write(self,data):self.data.extend(data);self.position+=len(data);return len(data)
    def tell(self):return self.position
    def writable(self):return True
    def seekable(self):return False
    def flush(self):pass
    def drain(self):
        data=bytes(self.data);self.data.clear();return data


class TunnelMux:
    def __init__(self,state,frame,audio):
        self.state=state;self.sink=Sink();self.origin=frame.pts
        state.metrics['target_bitrate']=state.profile['bitrate']
        self.container=av.open(self.sink,'w',format='mp4',options={
            'movflags':'empty_moov+default_base_moof','frag_duration':'100000','flush_packets':'1'})
        fps=state.profile['fps']
        self.video=self.container.add_stream(state.encoder,rate=fps)
        self.video.width=frame.width;self.video.height=frame.height
        codec=self.video.codec_context
        codec.pix_fmt='nv12' if state.encoder=='h264_nvenc' else 'yuv420p'
        codec.time_base=Fraction(1,90000);codec.framerate=Fraction(fps);codec.bit_rate=state.profile['bitrate']
        codec.gop_size=fps;codec.max_b_frames=0
        codec.colorspace=codec.color_primaries=codec.color_trc=1;codec.color_range=1
        level=31 if frame.height<=720 and frame.width<=1280 and fps<=30 else 42 if fps>30 else 41
        profile=state.profile.get('codec_profile','baseline')
        if profile=='baseline':codec.gop_size=max(1,fps//2)
        codec.options=({'preset':'p4','tune':'ull','rc':'vbr','rc-lookahead':'0','spatial-aq':'1','aq-strength':'8',
                        'zerolatency':'1','delay':'0','profile':profile,'level':str(level),'forced-idr':'1'}
                       if state.encoder=='h264_nvenc' else
                       {'preset':'ultrafast','tune':'zerolatency','profile':profile,'level':str(level/10)})
        self.audio=None;self.resampler=None
        if audio:
            self.audio=self.container.add_stream('aac',rate=48000)
            self.audio.layout='stereo';self.audio.bit_rate=128000
            self.resampler=av.AudioResampler(format='fltp',layout='stereo',rate=48000)
        self.container.start_encoding()
        extra=codec.extradata
        # avcC contains the actual profile, compatibility and level bytes.
        sps=re.search(b'\x00\x00(?:\x00)?\x01\x67(.{3})',extra or b'',re.DOTALL)
        identifier=extra[1:4].hex() if extra and extra[0]==1 else sps.group(1).hex() if sps else ('6400' if profile=='high' else '42c0')+f'{level:02x}'
        self.mime='video/mp4; codecs="avc1.'+identifier+(',mp4a.40.2' if audio else '')+'"'

    def encode(self,frame,kind):
        start=time.perf_counter()
        if kind=='video':
            frame.pts=max(0,frame.pts-self.origin)
            if getattr(self.state,'force_keyframe',False):
                frame.pict_type=av.video.frame.PictureType.I;self.state.force_keyframe=False
            if self.state.encoder!='h264_nvenc':frame=frame.reformat(format='yuv420p')
            packets=self.video.encode(frame)
            self.state.metrics['encoded']+=1
            self.state.metrics['encode_ms']=round((time.perf_counter()-start)*1000,2)
        else:
            frame.pts=max(0,frame.pts-int(self.origin*48000/90000))
            packets=[]
            for converted in self.resampler.resample(frame):packets.extend(self.audio.encode(converted))
        for packet in packets:self.container.mux(packet)
        data=self.sink.drain();self.state.metrics['encoded_bytes']+=len(data)
        return data

    def close(self):self.container.close()


async def run_stream(state,ws,wants_audio):
    """One sender owns the mux. Await TCP drain, never accumulate encoded frames."""
    from host.capture import DesktopTrack
    from host.audio import LoopbackTrack
    from aiortc.mediastreams import MediaStreamError
    state.video=video=DesktopTrack(state)
    audio=state.audio=LoopbackTrack(state) if wants_audio else None
    mux=None
    executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='TunnelEncoder')
    async def work(callback,*args):
        future=asyncio.get_running_loop().run_in_executor(executor,callback,*args)
        try:return await asyncio.shield(future)
        except asyncio.CancelledError:
            # Finish the in-flight encode before closing AV contexts or DXGI shared memory.
            await future
            raise
    try:
        first=await asyncio.wait_for(video.recv(),12)
        first_audio=None
        if audio:
            try:first_audio=await audio.recv()
            except MediaStreamError:audio.stop();state.audio=None;audio=None
        def initialize():
            nonlocal mux
            try:mux=TunnelMux(state,first,audio is not None)
            except Exception:
                if state.encoder!='h264_nvenc':raise
                state.error('Tunnel : NVENC indisponible, utilisation de x264.')
                state.encoder='libx264';mux=TunnelMux(state,first,audio is not None)
        await work(initialize)
        state.codec_profile=state.profile.get('codec_profile','baseline');state.active=True
        await state.session_connected()
        await ws.send_json({'type':'ready','session_id':state.session_id,'mime':mux.mime,
                            'audio':audio is not None,'width':first.width,'height':first.height,
                            'fps':state.profile['fps'],'transport':'HTTPS WebSocket'})
        await ws.send_bytes(mux.sink.drain())
        await ws.send_bytes(await work(mux.encode,first,'video'))
        if first_audio:await ws.send_bytes(await work(mux.encode,first_audio,'audio'))
        pending={asyncio.create_task(video.recv()):'video'}
        if audio:pending[asyncio.create_task(audio.recv())]='audio'
        try:
            while state.ws is ws and not ws.closed:
                done,_=await asyncio.wait(pending,return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    kind=pending.pop(task)
                    frame=task.result()
                    # One encoding worker preserves AV ordering while input stays responsive.
                    data=await work(mux.encode,frame,kind)
                    if data:await asyncio.wait_for(ws.send_bytes(data),10)
                    track=video if kind=='video' else audio
                    pending[asyncio.create_task(track.recv())]=kind
        finally:
            for task in pending:task.cancel()
            await asyncio.gather(*pending,return_exceptions=True)
    except asyncio.CancelledError:raise
    except Exception as exc:
        logging.exception('Tunnel encoder failed')
        state.error('Tunnel : '+str(exc))
        if not ws.closed:
            await ws.send_json({'type':'error','message':'Flux interrompu : '+str(exc)})
            await ws.close(code=1011,message=b'Stream failed')
    finally:
        try:
            if mux:await work(mux.close)
        finally:executor.shutdown(wait=True,cancel_futures=True)
