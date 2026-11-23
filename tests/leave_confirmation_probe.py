"""Native leave confirmation: cancel preserves the session; accepting closes transports."""
import asyncio
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright,Error
ROOT=Path(__file__).resolve().parent.parent


async def main():
    app=web.Application();app.router.add_get('/',lambda r:web.FileResponse(ROOT/'web/index.html'))
    app.router.add_static('/assets',ROOT/'assets');app.router.add_static('/',ROOT/'web')
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8095).start()
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch();page=await browser.new_page()
            await page.goto('http://127.0.0.1:8095')
            await page.locator('#token').click()  # Sticky activation required by the browser.
            await page.evaluate("""()=>{
              connected=true;window.closedTransports=0;window.releases=0;
              const close=()=>{closedTransports++;sessionStorage.setItem('closed-transports',closedTransports)};
              pc={connectionState:'connected',close};tunnelSocket={close};commandSocket={close};
              channel={readyState:'open',bufferedAmount:0,send:()=>releases++};
            }""")
            async with page.expect_event('dialog') as event:
                reload=asyncio.create_task(page.reload())
            dialog=await event.value;assert dialog.type=='beforeunload'
            await dialog.dismiss()
            try:await reload
            except Error:pass
            assert await page.evaluate('connected&&closedTransports===0&&releases===0')
            async with page.expect_event('dialog') as event:
                reload=asyncio.create_task(page.reload())
            await (await event.value).accept();await reload
            assert await page.evaluate("sessionStorage.getItem('closed-transports')")=='3'
            # Disconnected pages navigate normally, without a confirmation loop.
            dialogs=[];page.on('dialog',lambda d:dialogs.append(d.type))
            await page.reload();assert not dialogs
            await browser.close()
        print('PASS: native confirmation, cancel keeps the connection, confirmed exit closes all transports, disconnected page leaves freely.')
    finally:await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
