"""Real browser PNG downloads, cropped video recording and fullscreen dock gestures."""
import asyncio
import json
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright
from PIL import Image
import av
ROOT=Path(__file__).resolve().parent.parent

async def main():
    app=web.Application();app.router.add_get('/',lambda r:web.FileResponse(ROOT/'web/index.html'))
    app.router.add_static('/assets',ROOT/'assets');app.router.add_static('/',ROOT/'web')
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8087).start()
    output=ROOT/'test-results';output.mkdir(exist_ok=True)
    result={}
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
            page=await browser.new_page(viewport={'width':1280,'height':900},accept_downloads=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            actions=[]
            async def action(route):actions.append(route.request.post_data_json['action']);await route.fulfill(json={'ok':True})
            await page.route('**/api/action',action)
            await page.goto('http://127.0.0.1:8087')
            await page.evaluate("""async()=>{
              connected=true;hostState={control:true,fps:30};sessionId='tools-test-session-12345';token='test-only';
              pc={connectionState:'connected'};channel={readyState:'open',bufferedAmount:0,send:()=>{}};
              window.source=document.createElement('canvas');source.width=640;source.height=360;
              let n=0;setInterval(()=>{const ctx=source.getContext('2d');ctx.fillStyle='#123456';ctx.fillRect(0,0,640,360);ctx.fillStyle=n++%2?'#dd3344':'#22cc55';ctx.fillRect(100,100,100,100)},33);
              video.srcObject=source.captureStream(30);video.style.display='block';$('empty').style.display='none';$('control').disabled=false;
              await video.play();setState('Connecté',true);
            }""")
            cdp=await page.context.new_cdp_session(page)
            await cdp.send('Browser.grantPermissions',{'origin':'http://127.0.0.1:8087','permissions':['keyboardLock']})
            await page.locator('#screen').click();await page.wait_for_function('keyboardLocked')
            assert await page.locator('.session-tools').is_visible()
            async with page.expect_download() as event:
                await page.locator('#toolCapture').click();await page.get_by_role('button',name='Tout l’écran',exact=True).click()
            shot=output/'tools-whole.png';await (await event.value).save_as(shot)
            assert Image.open(shot).size==(640,360);result['whole_screenshot_download']=True
            await page.locator('#toolCapture').click();await page.get_by_role('button',name='Sélectionner une zone',exact=True).click()
            rect=await page.evaluate('imageRect()')
            async def drag():
                await page.mouse.move(rect['left']+rect['width']*.25,rect['top']+rect['height']*.25)
                await page.mouse.down();await page.mouse.move(rect['left']+rect['width']*.75,rect['top']+rect['height']*.75,steps=4);await page.mouse.up()
            async with page.expect_download() as event:await drag()
            shot=output/'tools-crop.png';await (await event.value).save_as(shot)
            assert Image.open(shot).size==(320,180);result['region_screenshot_download']=True
            for region in (False,True):
                await page.locator('#toolRecord').click()
                await page.get_by_role('button',name='Sélectionner une zone' if region else 'Tout l’écran',exact=True).click()
                if region:await drag()
                await asyncio.sleep(1.6)
                async with page.expect_download() as event:await page.locator('#toolRecord').click()
                download=await event.value
                path=output/(('tools-region-record' if region else 'tools-whole-record')+Path(download.suggested_filename).suffix)
                await download.save_as(path)
                with av.open(str(path)) as container:
                    frames=list(container.decode(video=0));assert len(frames)>5
                    assert (frames[0].width,frames[0].height)==((320,180) if region else (640,360))
                result['region_recording_download' if region else 'whole_recording_download']=True
            await page.locator('#toolCmd').click();await page.locator('#toolClassroom').click();assert actions==['cmd','classroom']
            result['fixed_desktop_action_buttons']=True
            await page.locator('#toolHide').click();assert await page.locator('.session-tools').is_hidden()
            assert await page.locator('.tools-reveal').is_hidden()
            await page.mouse.move(1275,895);await asyncio.sleep(1);assert await page.locator('.tools-reveal').is_hidden()
            await asyncio.sleep(1.2);assert await page.locator('.tools-reveal').is_visible()
            await page.locator('.tools-reveal').click();assert await page.locator('.session-tools').is_visible()
            result['hide_completely_and_two_second_reveal']=True
            # The right edge also works away from the exact bottom corner, even
            # when an input handler stops bubbling pointer events.
            await page.evaluate("screen.addEventListener('pointermove',e=>e.stopPropagation())")
            await page.locator('#toolHide').click()
            await page.mouse.move(1275,450);await asyncio.sleep(2.15)
            assert await page.locator('.tools-reveal').is_visible()
            handle=await page.locator('.tools-reveal').bounding_box()
            assert 400<handle['y']<460,handle
            await page.locator('.tools-reveal').click()
            assert await page.evaluate('document.activeElement===screen')
            # Expanded layout with its bottom outside the visible viewport.
            await page.evaluate("document.exitFullscreen()")
            await page.wait_for_function('!document.fullscreenElement')
            await page.evaluate("viewer.classList.add('expanded');viewer.style.height='1200px'")
            await page.locator('#toolHide').click()
            await page.mouse.move(1275,895);await asyncio.sleep(2.15)
            assert await page.locator('.tools-reveal').is_visible()
            handle=await page.locator('.tools-reveal').bounding_box()
            assert handle['y']+handle['height']<=900,handle
            await page.mouse.move(600,450)
            assert await page.locator('.tools-reveal').is_hidden()
            result['right_edge_capture_listener_visible_viewport_and_refocus']=True
            # A second of stale video is discarded instead of delaying key/click feedback.
            lag=await page.evaluate("""()=>{
              const media={buffered:{length:1,start:()=>0,end:()=>10},currentTime:9,seeking:false,playbackRate:1};
              followLiveEdge(media);
              const first=media.currentTime;
              media.currentTime=9;followLiveEdge(media);
              return {first,cooldown:media.currentTime,rate:media.playbackRate};
            }""")
            assert abs(lag['first']-9.92)<.001 and lag['cooldown']==9 and lag['rate']>1,lag
            result['desktop_live_edge_trim_and_seek_cooldown']=True
            assert not errors,errors
            await browser.close()
        print(json.dumps(result,indent=2));(output/'tools-probe.json').write_text(json.dumps(result,indent=2))
    finally:await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
