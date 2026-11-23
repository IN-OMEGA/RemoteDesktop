"""Tunnel lifecycle with real child processes and no external network or desktop effects."""
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.public_tunnel import QuickTunnel

async def wait_for(predicate):
    async with asyncio.timeout(8):
        while not predicate():await asyncio.sleep(.03)

async def main():
    state=SimpleNamespace(public_url='',public_status='',token='persistent-test-code')
    children=[];calls=[]
    async def factory(*args,**options):
        calls.append(args)
        assert '--url' in args and 'http://127.0.0.1:8080' in args
        assert not any(k.startswith('TUNNEL_') for k in options['env'])
        url='https://'+uuid.uuid4().hex+'.trycloudflare.com'
        process=await asyncio.create_subprocess_exec(sys.executable,'-u','-c',f'import time;print({url!r},flush=True);time.sleep(60)',**options)
        children.append(process);return process
    with tempfile.TemporaryDirectory(prefix='nexus-tunnel-') as directory:
        tunnel=QuickTunnel(state,sys.executable,8080,directory,process_factory=factory)
        try:
            await tunnel.start();await wait_for(lambda:bool(state.public_url));first=state.public_url
            await tunnel.restart();await wait_for(lambda:bool(state.public_url) and state.public_url!=first)
            assert children[0].returncode is not None
            second=state.public_url
            assert Path(directory,'public-url.txt').read_text().strip()==second
            assert state.token=='persistent-test-code'
            await tunnel.close();assert not state.public_url
            assert not Path(directory,'public-url.txt').exists()
            assert all(p.returncode is not None for p in children)
            # Starting the application again produces another fresh URL.
            next_tunnel=QuickTunnel(state,sys.executable,8080,directory,process_factory=factory)
            await next_tunnel.start();await wait_for(lambda:bool(state.public_url))
            assert state.public_url not in (first,second)
            await next_tunnel.close();assert all(p.returncode is not None for p in children)
        finally:await tunnel.close()
    print('PASS: fresh URL on restart/relaunch, persistent code, owned child cleanup, stale URL cleared.')

if __name__=='__main__':asyncio.run(main())
