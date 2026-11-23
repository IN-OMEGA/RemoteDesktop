import asyncio
import json
from pathlib import Path
import sys
import time
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.server import State,PROFILES
from host.capture import DesktopTrack
from host.encoder import DesktopEncoder

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--compare',action='store_true')
    parser.add_argument('--profile',choices=PROFILES)
    args=parser.parse_args()
    state=State()
    results={}
    cases=([(args.profile,PROFILES[args.profile])] if args.profile else PROFILES.items()) if not args.compare else [('before_bgra_cpu_conversion',PROFILES[args.profile or '1080p120']),('after_nv12_gpu_conversion',PROFILES[args.profile or '1080p120'])]
    for name,profile in cases:
        if args.compare:
            state.use_gpu_conversion=not name.startswith('before')
        state.profile=profile.copy();state.profile_name=name;state.reset_metrics()
        state.epoch=time.perf_counter()
        track=DesktopTrack(state);encoder=DesktopEncoder(state)
        t=time.perf_counter()
        first=None
        captures=[];encodes=[]
        cpu_start=state.process.cpu_times()
        try:
            # Exclude process spawn / CUDA session warm-up from steady-state throughput.
            for _ in range(3):
                frame=await asyncio.wait_for(track.recv(),10)
                await asyncio.to_thread(encoder.encode,frame)
            state.reset_metrics();t=time.perf_counter()
            while time.perf_counter()-t<4:
                frame=await asyncio.wait_for(track.recv(),10)
                if first is None:first=[frame.width,frame.height]
                payloads,stamp=await asyncio.to_thread(encoder.encode,frame)
                captures.append(state.metrics['capture_ms']);encodes.append(state.metrics['encode_ms'])
                if not payloads:raise RuntimeError('Aucune donnée H.264')
            elapsed=time.perf_counter()-t
            results[name]={'actual_resolution':first,'frames':state.metrics['frames'],'source_frames':state.metrics['source_frames'],
                           'seconds':elapsed,'pipeline_fps':state.metrics['frames']/elapsed,
                           'last_encode_ms':state.metrics['encode_ms'],'capture_ms':state.metrics['capture_ms'],
                           'pacing_missed':state.metrics['pacing_missed'],'source_skipped':state.metrics['source_skipped'],
                           'mbps':state.metrics['encoded_bytes']*8/elapsed/1e6,'encoder':state.encoder,
                           'mean_capture_ms':sum(captures)/len(captures),'mean_encode_ms':sum(encodes)/len(encodes),
                           'pixel_format':state.metrics.get('pixel_format'), 'full_profile_verified':False}
        except Exception as exc:results[name]={'error':str(exc),'errors':list(state.errors)}
        finally:
            track.stop();track.close_native()
        print(name,results[name],flush=True)
    Path('test-results/'+('optimization' if args.compare else 'benchmark')+'.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
if __name__=='__main__':asyncio.run(main())
