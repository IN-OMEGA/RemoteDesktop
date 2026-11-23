"""Two real temporary Cloudflare links to a health-only test server; never connects a desktop."""
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from host.public_tunnel import QuickTunnel

async def main():
    app=web.Application();app.router.add_get('/healthz',lambda r:web.Response(text='nexus-tunnel-test'))
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8091).start()
    state=SimpleNamespace(public_url='',public_status='')
    try:
        with tempfile.TemporaryDirectory(prefix='nexus-public-test-') as directory:
            tunnel=QuickTunnel(state,Path('third_party/cloudflared/cloudflared.exe').resolve(),8091,directory)
            try:
                await tunnel.start()
                async def live_url(previous=''):
                    async with asyncio.timeout(65):
                        while not state.public_url or state.public_url==previous:await asyncio.sleep(.2)
                        url=state.public_url
                        def check():
                            with urllib.request.urlopen(url+'/healthz',timeout=5) as response:return response.read()==b'nexus-tunnel-test'
                        while True:
                            try:
                                if await asyncio.to_thread(check):return url
                            except OSError:pass
                            await asyncio.sleep(.5)
                first=await live_url();await tunnel.restart();second=await live_url(first)
                assert first!=second
                print('PASS: two different real Cloudflare URLs, both forwarded to the health-only test server.')
            except Exception:
                print('Tunnel diagnostic:',state.public_status,tunnel.last_error)
                raise
            finally:await tunnel.close()
    finally:await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
