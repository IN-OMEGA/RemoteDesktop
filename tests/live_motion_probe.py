"""A real animated Windows test window must keep changing in the received iPhone-mode video."""
import asyncio
import ctypes
import json
from pathlib import Path
import sys
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from playwright.async_api import async_playwright
from host.server import State,create_app
from auth_fixture import protect_test_host,TEST_PASSWORD
from host.host_ui import HostUI
from host.display import display_info

async def main():
    ctypes.windll.user32.SetProcessDPIAware()
    root=tk.Tk();root.title('Nexus — vérification vidéo isolée');root.geometry('420x240+180+180');root.attributes('-topmost',True)
    canvas=tk.Canvas(root,highlightthickness=0);canvas.pack(fill='both',expand=True);root.update()
    state=State();access=protect_test_host(state);ui=HostUI(state,8088)
    runner=web.AppRunner(create_app(state,ui),access_log=None);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8088).start()
    running=True
    async def animate():
        n=0
        while running:
            canvas.configure(background='#e800e8' if n%2 else '#00e8e8');n+=1;root.update();await asyncio.sleep(.22)
    animation=asyncio.create_task(animate())
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
            page=await browser.new_page(bypass_csp=True,viewport={'width':390,'height':844},has_touch=True,is_mobile=True,
                extra_http_headers={'X-Forwarded-For':'203.0.113.3'},
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 Version/26.6 Mobile/15E148 Safari/604.1')
            await page.goto('http://127.0.0.1:8088');await page.locator('#token').fill(state.token);await page.locator('#remotePassword').fill(TEST_PASSWORD)
            # An unchecked box must never accidentally select desktop High/60 FPS on an iPhone.
            await page.evaluate("$('compatibility').checked=false")
            await page.locator('#connect').click();await page.wait_for_function('video.videoWidth>0 && video.currentTime>.5',timeout=25000)
            assert state.codec_profile=='baseline' and state.profile['fps']==30 and state.profile['width']<=1280
            original_session=state.session_id;d=display_info()
            x=(canvas.winfo_rootx()+canvas.winfo_width()/2)/d['width'];y=(canvas.winfo_rooty()+canvas.winfo_height()/2)/d['height']
            async def colors():
                samples=[]
                for _ in range(12):
                    samples.append(await page.evaluate("([x,y])=>{const c=document.createElement('canvas');c.width=c.height=1;const g=c.getContext('2d');g.drawImage(video,x*video.videoWidth,y*video.videoHeight,1,1,0,0,1,1);return [...g.getImageData(0,0,1,1).data].slice(0,3)}",[x,y]))
                    await asyncio.sleep(.17)
                return samples
            before=await colors()
            assert any(c[0]>130 and c[1]<100 for c in before) and any(c[1]>130 and c[0]<100 for c in before),before
            await page.evaluate('playbackGuard.repair()');await page.wait_for_function('video.readyState>=2 && !video.paused',timeout=12000)
            await asyncio.sleep(1)
            after=await colors()
            assert any(c[0]>130 and c[1]<100 for c in after) and any(c[1]>130 and c[0]<100 for c in after),after
            assert state.session_id==original_session and state.active
            await page.locator('#disconnect').click();await browser.close()
        result={'real_windows_pixels_change':True,'decoder_repair_keeps_same_session':True,'iphone_forced_baseline_720p30':True}
        print(json.dumps(result));Path('test-results/live-motion.json').write_text(json.dumps(result))
    finally:
        running=False;animation.cancel();await asyncio.gather(animation,return_exceptions=True);root.destroy();await runner.cleanup()

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    asyncio.run(main())
