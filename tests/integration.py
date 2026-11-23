"""Real DXGI/NVENC/WASAPI/WebRTC with the production code-only connection policy."""
import asyncio
import json
from pathlib import Path
import sys
import time
import io
import wave
import winsound
import uuid
import argparse
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp import web,ClientSession
from playwright.async_api import async_playwright
from host.server import State,create_app
from auth_fixture import protect_test_host,TEST_PASSWORD
from host.host_ui import HostUI
from host.code_store import CodeStore

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--safari',action='store_true');args=parser.parse_args()
    store=CodeStore(Path('test-results')/('session-code-'+uuid.uuid4().hex+'.bin'))
    state=State(code_store=store);access=protect_test_host(state);consent=HostUI(state,8081);consent.connection_requests=False
    runner=web.AppRunner(create_app(state,consent),access_log=None)
    await runner.setup();await web.TCPSite(runner,'127.0.0.1',8081).start()
    results={'nvenc':state.nvenc}
    try:
        async with ClientSession() as client:
            async with client.get('http://127.0.0.1:8081/api/status') as r:assert r.status==401
            async with client.get('http://127.0.0.1:8081/api/status',headers={'Authorization':'Bearer incorrect','Origin':'http://192.168.1.50:8081'}) as r:assert r.status==401
            # A reverse proxy can change Host: explicit authentication must still work.
            async with client.get('http://127.0.0.1:8081/api/status',headers={'Authorization':'Bearer '+state.token,'X-Nexus-Access':access,'Origin':'http://192.168.1.50:8081'}) as r:
                assert r.status==200
                assert 'Access-Control-Allow-Origin' not in r.headers
            # A valid code cannot bypass the host's connection-disable switch.
            async with client.post('http://127.0.0.1:8081/api/offer',
                headers={'Authorization':'Bearer '+state.token,'X-Nexus-Access':access,'Origin':'http://192.168.1.50:8081'},
                json={'profile':'1080p60','sdp':'test-denied-before-sdp-parsing','type':'offer'}) as r:
                assert r.status==403 and 'hôte' in await r.text()
        results['auth_required_and_proxy_origin_supported']=True
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
            settings={'viewport':{'width':1440,'height':1000},'bypass_csp':True}
            if args.safari:settings.update(user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1',viewport={'width':390,'height':844})
            page=await browser.new_page(**settings)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto('http://127.0.0.1:8081')
            results['browser_h264_profiles']=await page.evaluate("RTCRtpReceiver.getCapabilities('video').codecs.filter(c=>c.mimeType==='video/H264').map(c=>c.sdpFmtpLine)")
            await page.locator('#token').fill(state.token);await page.locator('#remotePassword').fill(TEST_PASSWORD)
            await page.locator('#profile').select_option('premium' if args.safari else '720p30')
            assert await page.locator('#compatibility').is_checked()==args.safari
            await page.locator('#audio').check()
            await page.locator('#connect').click()
            await page.wait_for_function("document.getElementById('message').textContent.includes('refusée')",timeout=15000)
            assert not state.active
            results['host_denial_blocks_connection']=True
            consent.connection_requests=True
            await page.locator('#connect').click()
            await page.wait_for_function("document.getElementById('connectionState').textContent.includes('Connecté')",timeout=25000)
            await page.wait_for_function("document.getElementById('video').videoWidth>0",timeout=25000)
            # Reproduce a transient Safari state without dropping the real media transport.
            assert await page.evaluate("()=>{const live=pc;Object.defineProperty(live,'connectionState',{configurable:true,get:()=>'disconnected'});live.onconnectionstatechange();const alive=pc===live&&connected;delete live.connectionState;live.onconnectionstatechange();return alive}")
            # A server still completing its connected callback must not close the client.
            assert await page.evaluate("async()=>{const live=pc,saved=api;api=async()=>({...hostState,active:false,session_exists:true,errors:[]});try{await hostStats();return pc===live&&connected;}finally{api=saved;}}")
            results['transient_disconnect_and_host_state_race_survive']=True
            await asyncio.sleep(6)
            # A brief, quiet real output tone verifies the actual loopback path and remote decode.
            def play_tone():
                buffer=io.BytesIO()
                with wave.open(buffer,'wb') as wav:
                    wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
                    tone=(np.sin(np.arange(14400)*2*np.pi*523/48000)*1200).astype('<i2')
                    wav.writeframes(np.repeat(tone[:,None],2,axis=1).tobytes())
                winsound.PlaySound(buffer.getvalue(),winsound.SND_MEMORY)
            await asyncio.to_thread(play_tone)
            await asyncio.sleep(1)
            results['video']=await page.evaluate("({width:video.videoWidth,height:video.videoHeight,time:video.currentTime,frames:video.getVideoPlaybackQuality().totalVideoFrames})")
            assert results['video']['frames']>0
            assert await page.evaluate('video.muted && video.playsInline && video.srcObject.getAudioTracks().length===0')
            if args.safari:
                assert results['video']['width']<=1280 and results['video']['height']<=720
                assert state.codec_profile=='baseline' and state.profile['fps']==30 and state.profile['h264_level']==31
                results['iphone_compatibility_encoded_and_decoded']=True
            assert consent.root is None  # No GUI / no approval action involved in this session.
            results['valid_code_connects_without_dialog']=True
            assert state.metrics['audio_frames']>0
            assert state.metrics['encoded']>0,'Custom H.264 encoder was not used'
            assert not await page.locator('#control').is_checked()
            results['host']=state.snapshot()
            results['receiver']=await page.evaluate("async()=>{const r=[];for(const s of (await pc.getStats()).values())if(s.type==='inbound-rtp')r.push({...s});return r}")
            audio_stats=next(s for s in results['receiver'] if s['kind']=='audio')
            results['browser_audio']=await page.evaluate("({context:audioContext?.state,elementPaused:remoteAudio.paused})")
            assert audio_stats['totalAudioEnergy']>0,'No actual loopback audio energy reached receiver'
            results['actual_loopback_audio_decoded']=True
            await page.screenshot(path='test-results/browser-desktop.png',full_page=True)
            await page.set_viewport_size({'width':390,'height':844})
            await page.screenshot(path='test-results/browser-mobile.png',full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.locator('#disconnect').click()
            await page.wait_for_function("document.getElementById('connectionState').textContent==='Hors connexion'")
            await asyncio.sleep(.5)
            assert not state.active and state.pc is None
            results['disconnect_releases_session']=True
            results['browser_errors']=errors
            assert not errors,errors
            # Explicitly exercise the software fallback as a separate session.
            state.nvenc['available']=False
            await page.set_viewport_size({'width':1440,'height':1000})
            await page.locator('#audio').uncheck()
            await page.locator('#connect').click()
            await page.wait_for_function("document.getElementById('video').videoWidth>0",timeout=25000)
            await asyncio.sleep(2)
            assert state.encoder=='libx264' and state.metrics['encoded']>0
            results['software_fallback_decoded']=True
            old_code=state.token
            new_code=state.regenerate_code()
            assert new_code!=old_code and CodeStore(store.path).load_or_create()==new_code
            async with ClientSession() as client:
                async with client.get('http://127.0.0.1:8081/api/status',headers={'Authorization':'Bearer '+old_code}) as r:assert r.status==401
                async with client.get('http://127.0.0.1:8081/api/status',headers={'Authorization':'Bearer '+new_code,'X-Nexus-Access':access}) as r:assert r.status==200
            assert not state.active
            results['manual_rotation_persists_and_revokes_old_code']=True
            await browser.close()
    finally:
        results['final_host']=state.snapshot()
        await runner.cleanup()
        Path('test-results').mkdir(exist_ok=True)
        Path('test-results/'+('safari-compatibility' if args.safari else 'integration')+'.json').write_text(json.dumps(results,indent=2,default=str),encoding='utf-8')
    print(json.dumps(results,indent=2,default=str))

if __name__=='__main__':asyncio.run(main())
