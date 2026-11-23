"""Touch cursor and custom keyboard routing/layout, without sending desktop input."""
import asyncio
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent.parent

async def main():
    app=web.Application();app.router.add_get('/',lambda r:web.FileResponse(ROOT/'web/index.html'))
    app.router.add_static('/assets',ROOT/'assets');app.router.add_static('/',ROOT/'web')
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8092).start()
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch()
            page=await browser.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True,
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 Version/26.6 Mobile/15E148 Safari/604.1')
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto('http://127.0.0.1:8092')
            await page.evaluate("""()=>{window.commands=[];connected=true;hostState={control:true};pc={connectionState:'connected',close(){}};channel={readyState:'open',bufferedAmount:0,send:data=>commands.push(JSON.parse(data))};Object.defineProperty(video,'videoWidth',{value:1920});Object.defineProperty(video,'videoHeight',{value:1080});video.style.display='block';$('empty').style.display='none';$('control').disabled=false;setState('Connecté',true)}""")
            assert await page.locator('#touchMode').input_value()=='trackpad'
            await page.locator('#fullscreen').click()
            await page.locator('#toolKeyboard').click()
            assert await page.locator('.neon-keyboard').is_visible()
            await page.get_by_role('button',name='a',exact=True).click()
            assert await page.evaluate("commands.some(e=>e.type==='text'&&e.text==='a')")
            await page.locator('.neon-keyboard').get_by_role('button',name='Ctrl',exact=True).click()
            await page.get_by_role('button',name='a',exact=True).click()
            assert await page.evaluate("commands.some(e=>e.code==='KeyA'&&e.logical&&e.down)&&commands.some(e=>e.code==='ControlLeft'&&!e.down)")
            await page.get_by_role('button',name='⇧',exact=True).click()
            await page.get_by_role('button',name='A',exact=True).click()
            assert await page.evaluate("commands.some(e=>e.type==='text'&&e.text==='A')")
            await page.get_by_title('Symboles et accents').click()
            await page.get_by_role('button',name='é',exact=True).click()
            assert await page.evaluate("commands.some(e=>e.type==='text'&&e.text==='é')")
            await page.get_by_title('Symboles et accents').click()
            await page.evaluate("document.fonts.load('600 14px NexusKeys')")
            assert await page.evaluate("document.fonts.check('600 14px NexusKeys') && document.documentElement.scrollWidth<=innerWidth")
            # Moving a finger shifts the virtual pointer and sends the same coordinates to the host.
            cdp=await page.context.new_cdp_session(page)
            r=await page.locator('#screen').bounding_box();x=r['x']+r['width']*.4;y=r['y']+r['height']*.5
            await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':1}]})
            await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+35,'y':y,'id':1}]})
            await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
            assert await page.evaluate("!touchCursor.hidden && cursor.x>.5 && commands.filter(e=>e.type==='move').at(-1).x===cursor.x")
            await page.screenshot(path=str(ROOT/'test-results/neon-keyboard-iphone.png'))
            await page.get_by_role('button',name='Masquer le clavier',exact=True).click()
            assert await page.locator('.neon-keyboard').is_hidden()
            assert not errors,errors
            await browser.close()
        print('PASS: iPhone trackpad cursor, backlit keyboard, Unicode/accents/shift, logical Ctrl+A, font and phone layout.')
    finally:await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
