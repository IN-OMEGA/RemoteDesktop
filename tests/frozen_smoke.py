"""Exercise password-protected connection against the distributed executable.
Clicks only the host's navigation and Copy button, never an approval dialog.
Restores clipboard text after obtaining the transient code. Never prints/stores it.
"""
import asyncio
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import tkinter as tk
import time
import sys
import argparse
import os
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from playwright.async_api import async_playwright

u=c.WinDLL('user32',use_last_error=True)
u.SetProcessDPIAware()
u.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
u.SendMessageW.restype=w.LPARAM
u.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
u.WindowFromPoint.restype=w.HWND
u.WindowFromPoint.argtypes=[w.POINT]
CALLBACK=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
PID=int(Path('runtime/host.pid').read_text().strip())

class RECT(c.Structure):_fields_=[('left',c.c_long),('top',c.c_long),('right',c.c_long),('bottom',c.c_long)]

def windows(parent=None):
    items=[]
    def cb(hwnd,_):
        pid=w.DWORD();u.GetWindowThreadProcessId(hwnd,c.byref(pid))
        if pid.value==PID:
            name=c.create_unicode_buffer(128);u.GetClassNameW(hwnd,name,128)
            rect=RECT();u.GetWindowRect(hwnd,c.byref(rect))
            items.append((hwnd,name.value,rect))
        return True
    if parent:u.EnumChildWindows(parent,CALLBACK(cb),0)
    else:u.EnumWindows(CALLBACK(cb),0)
    return items

def get_token():
    from host.code_store import CodeStore
    store=CodeStore()
    if store.path.exists():return store.load_or_create()
    root=next(h for h,cls,r in windows() if cls=='TkTopLevel')
    # Navigate/copy through the real CustomTkinter buttons, not an authentication bypass.
    u.SetForegroundWindow(root);time.sleep(.25)
    rect=RECT();u.GetClientRect(root,c.byref(rect))
    origin=w.POINT(0,0);u.ClientToScreen(root,c.byref(origin))
    def click(x,y):
        point=w.POINT(origin.x+int(x),origin.y+int(y))
        target=u.WindowFromPoint(point)
        pid=w.DWORD();u.GetWindowThreadProcessId(target,c.byref(pid))
        if pid.value!=PID:raise RuntimeError('Host button is obscured; refusing to click another application')
        from host.remote_input import RemoteInput
        class TestState:
            control_allowed=True
            def error(self,message):raise RuntimeError(message)
        remote=RemoteInput(TestState())
        u.SetCursorPos(point.x,point.y)
        remote.button(0,True);remote.button(0,False)
        time.sleep(.15)
    # Sidebar Connection, then Copy code. Scale to the dashboard's default dimensions.
    cursor=w.POINT();u.GetCursorPos(c.byref(cursor))
    click(rect.right*.08,rect.bottom*.295);time.sleep(.3)
    clip=tk.Tk();clip.withdraw()
    try:
        try:previous=clip.clipboard_get()
        except tk.TclError:previous=''
        click(rect.right*.282,rect.bottom*.462)
        time.sleep(.3)
        token=clip.clipboard_get()
        clip.clipboard_clear()
        if previous:clip.clipboard_append(previous)
        clip.update()
        if len(token)<20 or len(token)>100:raise RuntimeError('No connection code copied')
        return token
    finally:
        clip.destroy();u.SetCursorPos(cursor.x,cursor.y)

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',default='1080p60')
    parser.add_argument('--url',default='http://localhost:8080')
    parser.add_argument('--safari',action='store_true')
    parser.add_argument('--audio',action='store_true')
    args=parser.parse_args()
    password=os.environ.get('NEXUS_TEST_PASSWORD')
    if not password:raise RuntimeError('Set NEXUS_TEST_PASSWORD before running this explicit desktop connection test.')
    token=get_token()
    result={}
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
        settings={'bypass_csp':True,'extra_http_headers':{'ngrok-skip-browser-warning':'true'}}
        if args.safari:settings.update(user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1',viewport={'width':390,'height':844})
        page=await browser.new_page(**settings)
        await page.goto(args.url)
        await page.locator('#token').fill(token)
        await page.locator('#remotePassword').fill(password)
        await page.locator('#profile').select_option(args.profile)
        if args.audio:await page.locator('#audio').check()
        await page.locator('#connect').click()
        await page.wait_for_function("document.getElementById('video').videoWidth>0",timeout=30000)
        assert not any(cls=='#32770' for _,cls,_ in windows()),'Unexpected host dialog'
        initial_frames=await page.evaluate('video.getVideoPlaybackQuality().totalVideoFrames')
        started=time.perf_counter()
        await asyncio.sleep(6)
        result=await page.evaluate("({width:video.videoWidth,height:video.videoHeight,frames:video.getVideoPlaybackQuality().totalVideoFrames})")
        assert result['frames']>0
        result['valid_code_connects_without_dialog']=True
        result['measured_seconds']=time.perf_counter()-started
        result['average_received_fps']=(result['frames']-initial_frames)/result['measured_seconds']
        result['host']=await page.evaluate("api('status')")
        if args.safari:
            assert await page.locator('#compatibility').is_checked()
            assert result['width']<=1280 and result['height']<=720 and result['host']['codec_profile']=='baseline'
            result['safari_compatibility_mode']=True
        result['video_rtp']=await page.evaluate("async()=>pc?[...(await pc.getStats()).values()].find(s=>s.type==='inbound-rtp'&&s.kind==='video'):{}")
        result['transport']=await page.locator('#connectionState').text_content()
        result['latency']=await page.evaluate('({commandRttMs:latency,videoBufferMs:video.buffered.length?Math.max(0,(video.buffered.end(video.buffered.length-1)-video.currentTime)*1000):null})')
        if args.audio:
            result['audio']=await page.evaluate('({time:remoteAudio.currentTime,paused:remoteAudio.paused})')
            assert result['audio']['time']>0 and not result['audio']['paused']
        await page.screenshot(path='test-results/nexus-web-connected.png',full_page=True)
        await page.locator('#disconnect').click()
        await browser.close()
    Path('test-results/frozen.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print({k:v for k,v in result.items() if k not in ('host','video_rtp')},'receiver_fps=',result['video_rtp'].get('framesPerSecond'))

if __name__=='__main__':asyncio.run(main())
