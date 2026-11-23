"""Real DXGI/NVENC/AAC over a proxy-shaped WebSocket, browser decode and takeover."""
import asyncio
import json
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp import web,ClientSession
from playwright.async_api import async_playwright
from host.server import State,create_app
from auth_fixture import protect_test_host,TEST_PASSWORD
from host.host_ui import HostUI


async def main():
    state=State();access=protect_test_host(state);ui=HostUI(state,8082)
    state.ice_servers=[{'urls':'stun:127.0.0.1:9'}]
    class Actions:
        prepared=0
        restored=0
        pending=False
        launched=[]
        def prepare(self):self.prepared+=1;self.pending=True;return []
        def restore(self):
            if self.pending:self.restored+=1;self.pending=False
            return []
        def launch(self,action):self.launched.append(action)
    actions=state.desktop_actions=Actions()
    runner=web.AppRunner(create_app(state,ui),access_log=None)
    await runner.setup();await web.TCPSite(runner,'127.0.0.1',8082).start()
    result={}
    try:
        async with async_playwright() as p, ClientSession() as http:
            chunks=[]
            browser=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
            async def connect(mobile=False):
                page=await browser.new_page(bypass_csp=True,extra_http_headers={'X-Forwarded-For':'203.0.113.4'},
                    **({'user_agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'} if mobile else {}))
                if not mobile:page.on('websocket',lambda ws:ws.on('framereceived',lambda data:chunks.append(data) if isinstance(data,bytes) else None))
                await page.goto('http://127.0.0.1:8082')
                # A STUN server that never completes gathering must not delay HTTPS fallback.
                await page.evaluate("""()=>{
                  const Native=window.RTCPeerConnection;
                  window.RTCPeerConnection=class extends Native{
                    constructor(...args){super(...args);window.iceStarted=performance.now();}
                    get iceGatheringState(){return 'gathering';}
                  };
                  const original=connectTunnel;
                  connectTunnel=()=>{window.iceWaitMs=performance.now()-window.iceStarted;return original();};
                }""")
                # This isolated server uses a fake launcher; emulate a person without changing Windows.
                await page.evaluate("Object.defineProperty(navigator,'webdriver',{get:()=>false})")
                await page.locator('#token').fill(state.token);await page.locator('#remotePassword').fill(TEST_PASSWORD)
                await page.locator('#profile').select_option('720p30' if mobile else 'premium')
                await page.locator('#audio').check()
                await page.locator('#connect').click()
                try:await page.wait_for_function('video.videoWidth>0 && video.currentTime>.5',timeout=30000)
                except Exception:
                    print('Stream failure:',await page.locator('#message').text_content(),list(state.errors));raise
                ice_wait=await page.evaluate('window.iceWaitMs')
                assert 1800<ice_wait<5000,ice_wait
                result['stalled_stun_fallback_ms']=round(ice_wait)
                return page
            first=await connect()
            old_id=state.session_id
            await asyncio.sleep(4)
            assert state.control_ws is not None
            assert await first.evaluate('commandSocket?.readyState===WebSocket.OPEN')
            result['dedicated_control_channel']=True
            assert actions.prepared==1
            await state.session_connected();assert actions.prepared==1
            headers={'Authorization':'Bearer '+state.token,'X-Nexus-Access':access,'X-Nexus-Session':old_id}
            for action in ('cmd','classroom'):
                async with http.post('http://127.0.0.1:8082/api/action',headers=headers,json={'action':action}) as response:assert response.status==200
            assert actions.launched==['cmd','classroom']
            async with http.post('http://127.0.0.1:8082/api/action',headers=headers,json={'action':'cmd & calc'}) as response:assert response.status==400
            async with http.post('http://127.0.0.1:8082/api/action',headers={**headers,'X-Nexus-Session':'old-client'},json={'action':'cmd'}) as response:assert response.status==403
            assert actions.launched==['cmd','classroom'];result['session_scoped_fixed_actions_and_once_only_setup']=True
            result['first_video']=await first.evaluate('({width:video.videoWidth,height:video.videoHeight,time:video.currentTime,frames:video.getVideoPlaybackQuality().totalVideoFrames,audioTime:remoteAudio.currentTime,audioPaused:remoteAudio.paused})')
            result['pipeline']={k:state.metrics[k] for k in ('frames','encoded','encode_ms','capture_ms','audio_frames','pacing_missed')}
            Path('test-results/tunnel-sample.mp4').write_bytes(b''.join(chunks))
            result['playback']=await first.evaluate('({buffered:[...Array(video.buffered.length)].map((_,i)=>[video.buffered.start(i),video.buffered.end(i)]),dropped:video.getVideoPlaybackQuality().droppedVideoFrames,ready:video.readyState,paused:video.paused,sourceError:video.error?.message})')
            result['latency']=await first.evaluate('({commandRttMs:latency,videoBufferMs:Math.max(0,(video.buffered.end(video.buffered.length-1)-video.currentTime)*1000)})')
            buffers=await first.evaluate("""()=>new Promise(resolve=>{
              const values=[];const timer=setInterval(()=>{
                if(video.buffered.length)values.push(Math.max(0,video.buffered.end(video.buffered.length-1)-video.currentTime)*1000);
                if(values.length===15){clearInterval(timer);resolve(values);}
              },100);
            })""")
            result['desktop_video_buffer_mean_ms']=round(sum(buffers)/len(buffers))
            assert result['desktop_video_buffer_mean_ms']<500,result['desktop_video_buffer_mean_ms']
            assert result['first_video']['frames']>60,'Video decoded too few frames: '+json.dumps({k:result[k] for k in ('first_video','pipeline','playback','latency')})
            assert result['first_video']['audioTime']>0 and not result['first_video']['audioPaused']
            assert state.metrics['audio_frames']>0
            # Failed authentication cannot evict the current client.
            bad=await http.ws_connect('http://127.0.0.1:8082/api/stream')
            await bad.send_json({'token':'incorrect'})
            assert (await bad.receive_json())['type']=='error'
            await bad.close();assert state.session_id==old_id and state.active
            existing_control=state.control_ws
            for auth in ({'token':'incorrect','session_id':old_id},{'token':state.token,'session_id':'stale-client-123456'}):
                bad_control=await http.ws_connect('http://127.0.0.1:8082/api/control')
                await bad_control.send_json(auth)
                assert (await bad_control.receive_json())['type']=='error'
                await bad_control.close()
                assert state.control_ws is existing_control and state.session_id==old_id
            result['control_authentication_and_session_scope']=True
            result['bad_code_does_not_replace']=True
            second=await connect(mobile=True)
            new_id=state.session_id;assert new_id!=old_id and state.active
            assert actions.prepared==2
            assert actions.restored==1
            await first.wait_for_function('!connected',timeout=5000)
            async with http.post('http://127.0.0.1:8082/api/disconnect',headers={
                'Authorization':'Bearer '+state.token,'X-Nexus-Access':access,'X-Nexus-Session':old_id},json={}) as response:
                assert (await response.json())['replaced']
            assert state.session_id==new_id and state.active
            result['takeover_and_stale_disconnect']=True
            result['iphone_mode']=await second.evaluate('({width:video.videoWidth,height:video.videoHeight,frames:video.getVideoPlaybackQuality().totalVideoFrames,muted:video.muted,inline:video.playsInline})')
            await second.locator('#disconnect').click()
            await asyncio.sleep(.5);assert not state.active and not state.session_id
            assert actions.restored==2
            result['disconnect_cleans_session']=True
            # Exercise x264 and video-only without relying on NVENC/audio availability.
            state.nvenc['available']=False
            software=await browser.new_page(bypass_csp=True,extra_http_headers={'X-Forwarded-For':'203.0.113.4'})
            await software.goto('http://127.0.0.1:8082')
            await software.locator('#token').fill(state.token);await software.locator('#remotePassword').fill(TEST_PASSWORD)
            await software.locator('#profile').select_option('720p30')
            await software.locator('#audio').uncheck()
            await software.locator('#connect').click()
            await software.wait_for_function('video.currentTime>1 && video.videoWidth>0',timeout=25000)
            assert state.encoder=='libx264'
            assert actions.prepared==2,'Automated verification must not launch Chrome or change Windows scale'
            result['software_video_only']=True
            await software.locator('#disconnect').click()
            await browser.close()
        print(json.dumps(result,indent=2))
        Path('test-results').mkdir(exist_ok=True)
        Path('test-results/tunnel-integration.json').write_text(json.dumps(result,indent=2))
    finally:await runner.cleanup()

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    asyncio.run(main())
