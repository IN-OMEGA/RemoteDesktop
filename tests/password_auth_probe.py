"""Required password across HTTP, video and control sockets; no desktop access or email."""
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from aiohttp.test_utils import TestClient,TestServer
from host.password_auth import PasswordAuth
from host.session_gate import SessionGate
from host.server import create_app


async def main():
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'password.bin';password='example-password-for-tests'
        assert not PasswordAuth().verify(password)
        try:PasswordAuth.configure(path,'')
        except ValueError:pass
        else:raise AssertionError('empty password accepted')
        PasswordAuth.configure(path,password)
        assert password.encode() not in path.read_bytes()
        auth=PasswordAuth(path)
        assert auth.verify(password) and not auth.verify('wrong')
        assert not auth.valid('') and not auth.valid('forged')
        state=SimpleNamespace(token='test-code',password_auth=auth,ice_servers=[],ws=None,control_ws=None,session_id='',connecting=False,
                              input=SimpleNamespace(last=0,release=lambda:None),snapshot=lambda:{'protected':True})
        disconnects=[]
        async def disconnect():disconnects.append(True)
        state.disconnect=disconnect
        gate=SessionGate(state)
        try:
            async with gate.admit('a'*16,'Bearer test-code'):raise AssertionError('admitted without password')
        except Exception as exc:assert getattr(exc,'status',None)==401
        assert not disconnects
        async with TestClient(TestServer(create_app(state,None))) as client:
            headers={'Authorization':'Bearer test-code'}
            assert (await client.get('/api/status',headers=headers)).status==401
            for supplied_code,supplied_password in [('test-code',''),('test-code','wrong'),('wrong',password)]:
                r=await client.post('/api/unlock',json={'code':supplied_code,'password':supplied_password})
                assert r.status==401
            r=await client.post('/api/unlock',json={'code':'test-code','password':password},
                                headers={'Origin':'https://example.trycloudflare.com','X-Forwarded-For':'203.0.113.2'})
            assert r.status==200
            ticket=(await r.json())['access'];headers['X-Nexus-Access']=ticket
            assert (await client.get('/api/status',headers=headers)).status==200
            assert (await client.get('/api/status',headers={**headers,'Authorization':'Bearer wrong'})).status==401
            for route in ('stream','control'):
                for access in ('','forged'):
                    async with client.ws_connect('/api/'+route) as ws:
                        await ws.send_json({'token':'test-code','access':access,'session_id':'a'*16})
                        assert (await ws.receive_json())['type']=='error'
            assert not disconnects
            # Valid password ticket is recognized; validation progresses to profile/session checks.
            async with client.ws_connect('/api/stream') as ws:
                await ws.send_json({'token':'test-code','access':ticket,'profile':'invalid'})
                assert 'Profil' in (await ws.receive_json())['message']
            async with client.ws_connect('/api/control') as ws:
                await ws.send_json({'token':'test-code','access':ticket,'session_id':'a'*16})
                assert 'Session' in (await ws.receive_json())['message']
            auth.tickets.clear()
            assert (await client.get('/api/status',headers=headers)).status==401
            while auth.reserve_attempt():pass
            assert (await client.post('/api/unlock',json={'code':'test-code','password':password})).status==429
        assert not PasswordAuth(path).valid(ticket)
    print('PASS: required password, protected persistence, HTTP/video/control denial, correct login, ticket revocation and rate limit; no desktop connected.')

if __name__=='__main__':asyncio.run(main())
