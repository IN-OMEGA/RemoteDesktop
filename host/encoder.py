"""H.264/NVENC through PyAV's supported FFmpeg integration."""
import time
from fractions import Fraction
import av
from aiortc.codecs.h264 import H264Encoder
from aiortc.mediastreams import VIDEO_TIME_BASE, convert_timebase


def context(name, width, height, fps, bitrate, quality='performance', profile='baseline', level=None):
    codec = av.CodecContext.create(name, 'w')
    codec.width, codec.height = width, height
    codec.pix_fmt = 'nv12' if name=='h264_nvenc' else 'yuv420p'
    codec.colorspace=1
    codec.color_primaries=1
    codec.color_trc=1
    codec.color_range=1
    codec.time_base = Fraction(1, 90000)
    codec.framerate = Fraction(fps)
    codec.bit_rate = bitrate
    codec.gop_size = fps
    if profile=='baseline' and level==31:codec.gop_size=max(1,fps//2)
    codec.max_b_frames = 0
    if name == 'h264_nvenc':
        codec.options = {'preset': {'performance':'p1','balanced':'p3','premium':'p4'}[quality],
                         'tune': 'ull', 'rc': 'cbr', 'rc-lookahead':'0',
                         'spatial-aq':'1' if quality!='performance' else '0','aq-strength':'8',
                         'zerolatency': '1', 'delay': '0', 'profile': profile,'forced-idr':'1'}
    else:
        codec.options = {'preset': 'ultrafast', 'tune': 'zerolatency', 'profile': profile}
    if level is not None:codec.options={**codec.options,'level':str(level)}
    codec.open()
    return codec


def probe_nvenc():
    try:
        codec = context('h264_nvenc', 640, 360, 60, 2_000_000)
        decoder = av.CodecContext.create('h264', 'r')
        frame = av.VideoFrame(640, 360, 'yuv420p')
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        frame.pts, frame.time_base = 0, Fraction(1, 90000)
        packets = codec.encode(frame) + codec.encode(None)
        count = sum(len(decoder.decode(p)) for p in packets)
        count += len(decoder.decode(None))
        if not count:
            raise RuntimeError('Aucune image décodée')
        return {'available': True, 'decoded_frames': count, 'error': None}
    except Exception as exc:
        return {'available': False, 'decoded_frames': 0, 'error': str(exc)}


class DesktopEncoder(H264Encoder):
    def __init__(self, state, profile='baseline'):
        super().__init__()
        self.state = state
        self.profile=profile
        state.codec_profile=profile
        self._bitrate = state.profile['bitrate']

    @property
    def target_bitrate(self):
        return self._bitrate

    @target_bitrate.setter
    def target_bitrate(self, value):
        # REMB feedback from the receiver bounds bandwidth; never exceed the chosen profile.
        self._bitrate = max(300_000, min(int(value), self.state.profile['bitrate']))

    def encode(self, frame, force_keyframe=False):
        start = time.perf_counter()
        try:
            if self.codec and (self.codec.width != frame.width or self.codec.height != frame.height
                    or abs(self.codec.bit_rate-self._bitrate)/self.codec.bit_rate > .25):
                self.codec = None
            if self.codec is None:
                self.codec = context(self.state.encoder, frame.width, frame.height,
                                     self.state.profile['fps'], self._bitrate,
                                     self.state.profile.get('quality','performance'),self.profile,
                                     self.state.profile.get('h264_level'))
            frame.pict_type = av.video.frame.PictureType.I if force_keyframe else av.video.frame.PictureType.NONE
            data = b''.join(bytes(p) for p in self.codec.encode(frame))
            elapsed = (time.perf_counter()-start)*1000
            self.state.metrics['encode_ms'] = round(elapsed, 2)
            self.state.metrics['encoded'] += 1
            self.state.metrics['encoded_bytes'] += len(data)
            self.state.metrics['target_bitrate'] = self._bitrate
            return self._packetize(self._split_bitstream(data)), convert_timebase(frame.pts, frame.time_base, VIDEO_TIME_BASE)
        except Exception as exc:
            self.state.error('Encodeur : ' + str(exc))
            self.codec = None
            # Fallback is explicit in UI/telemetry, never presented as hardware encoding.
            if self.state.encoder == 'h264_nvenc':
                self.state.encoder = 'libx264'
                return self.encode(frame, True)
            raise
