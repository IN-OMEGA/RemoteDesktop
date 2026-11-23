"""Browser input routing. Records commands without injecting them into the user's desktop."""
import asyncio
import json
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent.parent
SETUP="""()=>{
 window.commands=[];connected=true;hostState={control:true};pc={connectionState:'connected'};
 channel={readyState:'open',bufferedAmount:0,send:data=>commands.push(JSON.parse(data))};
 Object.defineProperty(video,'videoWidth',{configurable:true,value:1920});
 Object.defineProperty(video,'videoHeight',{configurable:true,value:1080});
 video.style.display='block';$('empty').style.display='none';$('control').disabled=false;
 setState('Connecté',true);
}"""

async def main():
    app=web.Application()
    app.router.add_get('/',lambda r:web.FileResponse(ROOT/'web/index.html'))
    app.router.add_static('/assets',ROOT/'assets');app.router.add_static('/',ROOT/'web')
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8085).start()
    results={}
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch()
            page=await browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto('http://127.0.0.1:8085');await page.evaluate(SETUP)
            # Exercise actual Fullscreen + Keyboard Lock where Chromium allows it.
            cdp=await page.context.new_cdp_session(page)
            await cdp.send('Browser.grantPermissions',{'origin':'http://127.0.0.1:8085','permissions':['keyboardLock']})
            await page.locator('#screen').click()
            await page.wait_for_function('keyboardLocked',timeout=10000)
            assert await page.evaluate('document.fullscreenElement===viewer')
            assert await page.locator('#inputToolbar').is_hidden()
            assert await page.locator('.viewer-bar').is_hidden()
            assert await page.locator('#controlBadge').count()==0
            assert await page.evaluate('(()=>{const r=screen.getBoundingClientRect();return Math.abs(r.width-innerWidth)<2&&Math.abs(r.height-innerHeight)<2})()')
            results['fullscreen_only_remote_desktop']=True
            await page.keyboard.press('Control+w')
            assert not page.is_closed()
            assert await page.evaluate("commands.some(e=>e.type==='key'&&e.code==='KeyW'&&e.down)&&commands.some(e=>e.code==='ControlLeft'&&e.down)")
            results['fullscreen_keyboard_lock_and_ctrl_w']=True
            await page.keyboard.press('Escape')
            assert await page.evaluate("$('control').checked && commands.some(e=>e.code==='Escape'&&e.down)")
            # A hold exits; a normal Escape still reaches the remote app.
            await page.keyboard.down('Escape');await asyncio.sleep(2.2);await page.keyboard.up('Escape')
            assert not await page.locator('#control').is_checked()
            results['escape_hold_releases']=True
            await page.evaluate("$('inputHelp').hidden=true")
            await page.locator('#screen').click();await page.wait_for_function('keyboardLocked')
            assert await page.locator('#inputHelp').is_hidden()
            # Three short presses exit and show help, even if it was already seen.
            for _ in range(3):await page.keyboard.press('Escape')
            await page.wait_for_function('!document.fullscreenElement')
            assert not await page.locator('#control').is_checked()
            assert await page.locator('#inputHelp').is_visible()
            results['triple_escape_releases_and_shows_help']=True
            await page.close()

            mobile=await browser.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True,
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1')
            mobile.on('pageerror',lambda e:errors.append(str(e)))
            await mobile.goto('http://127.0.0.1:8085');await mobile.evaluate(SETUP)
            await mobile.locator('#screen').scroll_into_view_if_needed()
            rect=await mobile.locator('#video').bounding_box();x=rect['x']+rect['width']*.6;y=rect['y']+rect['height']*.5
            await mobile.touchscreen.tap(x,y)
            assert await mobile.locator('#control').is_checked()
            assert await mobile.evaluate("commands.some(e=>e.type==='move')&&commands.some(e=>e.type==='button'&&e.button===0&&e.down)")
            results['touch_automatically_controls']=True
            mcdp=await mobile.context.new_cdp_session(mobile)
            async def touches(kind,points):await mcdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':points})
            a={'x':x-15,'y':y,'id':1};b={'x':x+15,'y':y,'id':2}
            await mobile.evaluate('commands=[]')
            await touches('touchStart',[a,b]);await touches('touchEnd',[])
            assert await mobile.evaluate("commands.some(e=>e.type==='button'&&e.button===2&&e.down)")
            results['two_finger_right_click']=True
            await mobile.evaluate('commands=[]')
            await touches('touchStart',[a,b]);await touches('touchMove',[{**a,'y':y-25},{**b,'y':y-25}]);await touches('touchEnd',[])
            assert await mobile.evaluate("commands.some(e=>e.type==='wheel')&&!commands.some(e=>e.type==='button'&&e.down)")
            results['two_finger_scroll_no_accidental_click']=True
            await mobile.locator('#touchMode').select_option('trackpad')
            await mobile.evaluate('commands=[]')
            await touches('touchStart',[a]);await touches('touchMove',[{**a,'x':x+30}]);await touches('touchEnd',[])
            assert await mobile.evaluate("commands.some(e=>e.type==='move')&&!commands.some(e=>e.type==='button'&&e.down)")
            results['trackpad_movement']=True
            await mobile.evaluate('commands=[]')
            await touches('touchStart',[a]);await asyncio.sleep(.5);await touches('touchMove',[{**a,'x':x+30}]);await touches('touchEnd',[])
            assert await mobile.evaluate("commands.some(e=>e.type==='button'&&e.down)&&commands.some(e=>e.type==='button'&&!e.down)")
            results['long_press_drag']=True
            await mobile.locator('#showKeyboard').click()
            await mobile.locator('#remoteKeyboard').fill('Bonjour été 😀')
            assert await mobile.evaluate("commands.some(e=>e.type==='text'&&e.text==='Bonjour été 😀')")
            await mobile.locator('#remoteKeyboard').press('Backspace')
            await mobile.locator('#remoteKeyboard').press('Enter')
            assert await mobile.evaluate("commands.some(e=>e.code==='Backspace'&&e.down)&&commands.some(e=>e.code==='Enter'&&e.down)")
            results['mobile_unicode_keyboard']=True
            await mobile.locator('#fullscreen').click()
            assert await mobile.evaluate("viewer.classList.contains('expanded')&&!video.controls")
            assert await mobile.locator('#inputToolbar').is_hidden()
            assert await mobile.locator('.viewer-bar').is_hidden()
            await touches('touchStart',[{'x':120,'y':160,'id':1},{'x':160,'y':160,'id':2},{'x':200,'y':160,'id':3}])
            await asyncio.sleep(1.1)
            await touches('touchEnd',[])
            assert not await mobile.locator('#control').is_checked()
            assert not await mobile.evaluate("viewer.classList.contains('expanded')")
            results['mobile_fullscreen_keeps_input']=True
            assert not errors,errors
            await browser.close()
        print(json.dumps(results,indent=2))
        (ROOT/'test-results/browser-input.json').write_text(json.dumps(results,indent=2))
    finally:await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
