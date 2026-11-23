"""Real WebRTC over proxy-shaped signaling and deterministic fallback when UDP is unavailable."""
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from playwright.async_api import async_playwright
from host.server import State,create_app
from auth_fixture import protect_test_host,TEST_PASSWORD
from host.host_ui import HostUI

async def main():
    state=State();access=protect_test_host(state);ui=HostUI(state,8089)
    state.ice_servers=[{'urls':'stun:stun.cloudflare.com:3478'}]
    runner=web.AppRunner(create_app(state,ui),access_log=None)
    await runner.setup();await web.TCPSite(runner,'127.0.0.1',8089).start()
    results={}
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
            for fallback in (False,True):
                page=await browser.new_page(bypass_csp=True,extra_http_headers={'X-Forwarded-For':'203.0.113.5'})
                await page.goto('http://127.0.0.1:8089');await page.locator('#token').fill(state.token);await page.locator('#remotePassword').fill(TEST_PASSWORD)
                await page.locator('#profile').select_option('720p30')
                if fallback:
                    # Preserve real signaling/tracks, but remove remote UDP candidates so ICE cannot connect.
                    async def drop_candidates(route):
                        response=await route.fetch();data=await response.json()
                        data['sdp']='\r\n'.join(line for line in data['sdp'].split('\r\n') if not line.startswith('a=candidate:'))
                        await route.fulfill(json=data)
                    await page.route('**/api/offer',drop_candidates)
                await page.locator('#connect').click()
                await page.wait_for_function("connected && video.videoWidth>0",timeout=35000)
                await asyncio.sleep(.5)
                label=await page.locator('#connectionState').text_content()
                assert ('Tunnel' in label) if fallback else ('WebRTC' in label),label
                results['udp_failure_falls_back_to_https' if fallback else 'proxy_signaling_can_use_direct_webrtc']=True
                await page.locator('#disconnect').click();await page.close()
            await browser.close()
        print(json.dumps(results,indent=2));Path('test-results/internet-transport.json').write_text(json.dumps(results,indent=2))
    finally:await runner.cleanup()

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    asyncio.run(main())
