"""A newer authenticated attempt cancels pending setup and invalid codes cannot evict it."""
import asyncio
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from host.session_gate import SessionGate
from auth_fixture import protect_test_host


async def main():
    class State:
        token='test-only-code';session_id='';connecting=False
        async def disconnect(self):self.session_id='';await asyncio.sleep(.01)
    state=State();access=protect_test_host(state);gate=SessionGate(state);started=asyncio.Event()
    async def pending():
        async with gate.admit('first-client-123456','Bearer '+state.token,access):
            started.set();await asyncio.sleep(60)
    first=asyncio.create_task(pending());await started.wait()
    try:
        async with gate.admit('invalid-client-1234','Bearer wrong'):raise AssertionError('accepted invalid code')
    except web.HTTPUnauthorized:pass
    assert not first.done()
    async with gate.admit('second-client-12345','Bearer '+state.token,access):assert state.session_id=='second-client-12345'
    result=await asyncio.gather(first,return_exceptions=True)
    assert isinstance(result[0],web.HTTPConflict)
    assert state.session_id=='second-client-12345' and not state.connecting
    print('PASS: pending takeover, bad code isolation, latest session retained')

if __name__=='__main__':asyncio.run(main())
