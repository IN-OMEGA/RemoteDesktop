"""Native clipboard bindings and browser/API synchronization without touching Windows clipboard."""
import asyncio
import ctypes
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp import web,ClientSession
from playwright.async_api import async_playwright
from host.server import State,create_app
from host.clipboard_sync import WindowsClipboard,validate_text
from auth_fixture import protect_test_host


def native_probe():
    class Kernel:
        def __init__(self):self.blocks={};self.next=0
        def GlobalAlloc(self,flags,size):
            self.next+=1;self.blocks[self.next]=ctypes.create_string_buffer(size);return self.next
        def GlobalLock(self,handle):return ctypes.addressof(self.blocks[handle])
        def GlobalUnlock(self,handle):return True
        def GlobalSize(self,handle):return ctypes.sizeof(self.blocks[handle])
        def GlobalFree(self,handle):del self.blocks[handle]
    class User:
        sequence=0;handle=None;opened=False;locked=False;fail=False
        def GetClipboardSequenceNumber(self):return self.sequence
        def IsClipboardFormatAvailable(self,fmt):return self.handle is not None
        def CreateWindowExW(self,*args):return 42
        def DestroyWindow(self,handle):return True
        def OpenClipboard(self,owner):self.opened=not self.locked;return self.opened
        def CloseClipboard(self):self.opened=False
        def EmptyClipboard(self):self.handle=None;return True
        def SetClipboardData(self,fmt,handle):
            if self.fail:return None
            self.sequence+=1;self.handle=handle;return handle
        def GetClipboardData(self,fmt):return self.handle
    bridge=WindowsClipboard();bridge.kernel=Kernel();bridge.user=User()
    text='Bonjour — accents é et emoji 😀'
    seq=bridge.set_text(text)
    assert bridge.snapshot()['text']==text
    assert bridge.snapshot(seq)['text'] is None
    assert not bridge.user.opened
    before=len(bridge.kernel.blocks);bridge.user.fail=True
    try:bridge.set_text('failed')
    except OSError:pass
    else:raise AssertionError('failed native transfer accepted')
    assert len(bridge.kernel.blocks)==before and not bridge.user.opened
    bridge.user.locked=True
    try:bridge.set_text('busy')
    except OSError:pass
    else:raise AssertionError('busy clipboard accepted')
    assert len(bridge.kernel.blocks)==before
    bridge.close()
    for text in (None,'\0','x'*32769):
        try:validate_text(text)
        except ValueError:pass
        else:raise AssertionError('invalid clipboard accepted')


async def main():
    native_probe()
    class Clipboard:
        text='host initial';sequence=1;reads=0;writes=0
        def snapshot(self,since=None):
            self.reads+=1;return {'sequence':str(self.sequence),'text':None if since==str(self.sequence) else self.text}
        def set_text(self,text):self.text=text;self.sequence+=1;self.writes+=1;return str(self.sequence)
        def close(self):pass
    state=State();access=protect_test_host(state);state.clipboard=Clipboard()
    state.active=True;state.session_id='clipboard-test-session-123';calls=[]
    state.input=SimpleNamespace(keys=set(),last=1e30,release=lambda:None,key=lambda *args,**kw:calls.append((args,kw)))
    runner=web.AppRunner(create_app(state,None),access_log=None);await runner.setup()
    await web.TCPSite(runner,'127.0.0.1',8094).start()
    headers={'Authorization':'Bearer '+state.token,'X-Nexus-Access':access,'X-Nexus-Session':state.session_id}
    try:
        async with ClientSession() as http:
            url='http://127.0.0.1:8094/api/clipboard'
            assert (await http.get(url,headers={'Authorization':headers['Authorization']})).status==401
            assert (await http.post(url,headers={**headers,'X-Nexus-Session':'stale'},json={'text':'bad'})).status==403
            assert (await http.post(url,headers=headers,json={'text':'x'*32769})).status==400
        async with async_playwright() as p:
            browser=await p.chromium.launch();page=await browser.new_page()
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.add_init_script("""(()=>{
              window.testClip={text:'client initial'};
              Object.defineProperty(navigator,'clipboard',{value:{
                readText:async()=>testClip.text,writeText:async text=>{testClip.text=text},
                write:async items=>{testClip.text=await (await items[0].getType('text/plain')).text()}
              }});
              const query=navigator.permissions.query.bind(navigator.permissions);
              navigator.permissions.query=desc=>desc.name==='clipboard-read'?Promise.resolve({state:'granted'}):query(desc);
            })()""")
            await page.goto('http://127.0.0.1:8094');await page.wait_for_timeout(700)
            assert state.clipboard.reads==0 and state.clipboard.writes==0
            await page.evaluate("""data=>{
              token=data.token;access=data.access;sessionId=data.identity;
              connected=true;hostState={control:true};pc={connectionState:'connected'};
              channel={readyState:'open',bufferedAmount:0,send:()=>{}};
              $('control').disabled=false;$('control').checked=true;screen.focus();
            }""",{'token':state.token,'access':access,'identity':state.session_id})
            await page.evaluate('remoteClipboard.sync(true)')
            assert state.clipboard.text=='client initial'
            state.clipboard.set_text('host → client 😀')
            await page.evaluate('remoteClipboard.sync(false)')
            assert await page.evaluate('testClip.text')=='host → client 😀'
            writes=state.clipboard.writes
            await page.evaluate('remoteClipboard.sync(false)');assert state.clipboard.writes==writes
            await page.evaluate("testClip.text='client second'")
            await page.wait_for_timeout(750);assert state.clipboard.text=='client second'
            await page.evaluate("testClip.text='paste with accents é'")
            await page.keyboard.press('Control+v')
            await page.wait_for_timeout(250)
            assert state.clipboard.text=='paste with accents é'
            assert any(args[:2]==('KeyV',True) for args,kw in calls),calls
            state.clipboard.set_text('copied remotely')
            await page.evaluate('remoteClipboard.captureCopy()')
            await page.wait_for_timeout(350)
            assert await page.evaluate('testClip.text')=='copied remotely'
            await page.evaluate('connected=false;remoteClipboard.reset();testClip.text="after disconnect"')
            writes=state.clipboard.writes;reads=state.clipboard.reads
            await page.wait_for_timeout(800)
            assert state.clipboard.writes==writes and state.clipboard.reads==reads
            assert not errors,errors
            await browser.close()
        print('PASS: Unicode native ownership/error paths, authenticated session guard, both directions, no echo, automatic sync, Ctrl+V, gesture copy and disconnect stop. No real Windows clipboard access.')
    finally:await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
