"""WebKit UI/policy checks. This is not a physical iPhone/WebRTC decoder test."""
import asyncio
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent.parent

async def main():
    async def index(request):return web.FileResponse(ROOT/'web'/'index.html')
    app=web.Application();app.router.add_get('/',index)
    app.router.add_static('/assets',ROOT/'assets')
    app.router.add_static('/',ROOT/'web')
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8084).start()
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch()
            page=await browser.new_page(viewport={'width':390,'height':844},has_touch=True,
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1')
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            await page.goto('http://127.0.0.1:8084')
            assert await page.locator('#compatibility').is_checked()
            assert await page.evaluate('video.muted && video.defaultMuted && video.playsInline')
            assert await page.locator('.guide').is_visible()
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.evaluate("async()=>{Object.defineProperty(video,'srcObject',{configurable:true,get:()=>({})});video.play=()=>Promise.reject(new DOMException('Gesture required','NotAllowedError'));await playVideo();}")
            assert await page.locator('#startVideo').count()==0
            await page.evaluate('video.play=()=>{window.automaticPlayCalled=true;return Promise.resolve()}')
            await page.evaluate("video.dispatchEvent(new Event('canplay'))")
            assert await page.evaluate('window.automaticPlayCalled===true')
            await page.evaluate("()=>{connected=true;hostState={control:true};pc={connectionState:'connected'};channel={readyState:'open',bufferedAmount:0,send:()=>{}};setState('Connecté',true);video.webkitEnterFullscreen=()=>{throw new Error('Native player would disable remote touch')}}")
            await page.locator('#fullscreen').click()
            assert await page.evaluate("viewer.classList.contains('expanded') && !video.controls && getComputedStyle(video).pointerEvents==='none'")
            assert await page.locator('#inputToolbar').is_hidden()
            await page.evaluate('screen.setPointerCapture=()=>{}')  # Synthetic pointers have no native capture handle.
            for identifier in (1,2,3):
                await page.locator('#screen').dispatch_event('pointerdown',{'pointerId':identifier,'pointerType':'touch','clientX':120+identifier*25,'clientY':150})
            await asyncio.sleep(1.1)
            assert await page.evaluate("!viewer.classList.contains('expanded')")
            assert not errors,errors
            await browser.close()
        print('PASS: WebKit iPhone layout, muted inline video, autoplay recovery and interactive fullscreen.')
    finally:await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
