"""Ctrl+W from Windows into a dedicated Chromium window, with remote commands recorded."""
import asyncio
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from playwright.async_api import async_playwright
from host.remote_input import RemoteInput
from browser_input_probe import SETUP,ROOT
import psutil


async def main():
    app=web.Application();app.router.add_get('/',lambda r:web.FileResponse(ROOT/'web/index.html'))
    app.router.add_static('/assets',ROOT/'assets');app.router.add_static('/',ROOT/'web')
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8086).start()
    user=c.WinDLL('user32');user.GetForegroundWindow.restype=w.HWND
    user.SetForegroundWindow.argtypes=[w.HWND]
    previous=user.GetForegroundWindow()
    class State:
        control_allowed=True
        def error(self,message):raise RuntimeError(message)
    keys=RemoteInput(State())
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=False)
            try:
                page=await browser.new_page(viewport={'width':1200,'height':850})
                await page.goto('http://127.0.0.1:8086');await page.evaluate(SETUP)
                marker='Nexus keyboard verification '+uuid.uuid4().hex
                await page.evaluate('(title)=>document.title=title',marker)
                cdp=await page.context.new_cdp_session(page)
                await cdp.send('Browser.grantPermissions',{'origin':'http://127.0.0.1:8086','permissions':['keyboardLock']})
                await page.locator('#screen').click();await page.wait_for_function('keyboardLocked')
                matches=[]
                callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
                def inspect(hwnd,_):
                    title=c.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,512)
                    if marker in title.value:matches.append(hwnd)
                    return True
                user.EnumWindows(callback(inspect),0)
                assert len(matches)==1
                target=matches[0];owner=w.DWORD();user.GetWindowThreadProcessId(target,c.byref(owner))
                command=psutil.Process(owner.value).cmdline()
                assert '--remote-debugging-pipe' in command and any('playwright_chromiumdev_profile-' in arg for arg in command)
                await page.bring_to_front();user.SetForegroundWindow(target);await asyncio.sleep(.3)
                assert user.GetForegroundWindow()==target,'Refusing to type into another application'
                keys.key('ControlLeft',True);keys.key('KeyW',True);keys.key('KeyW',False);keys.key('ControlLeft',False)
                await asyncio.sleep(.4)
                assert not page.is_closed(),'Native Ctrl+W closed the controller tab'
                assert await page.evaluate("commands.some(e=>e.code==='ControlLeft'&&e.down)&&commands.some(e=>e.code==='KeyW'&&e.down)")
                print('PASS: Windows Ctrl+W captured; controller tab stays open; remote Ctrl+W commands received.')
            finally:
                keys.release();await browser.close()
    finally:
        if previous:user.SetForegroundWindow(previous)
        await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
