"""The latest authenticated connection owns the host; stale requests cannot close it."""
import asyncio
from contextlib import asynccontextmanager
import re
import secrets
from aiohttp import web


class SessionGate:
    def __init__(self,state):
        self.state=state
        self.lock=asyncio.Lock()
        self.pending=None
        self.generation=0

    @staticmethod
    def client_id(value):
        if value is None:return secrets.token_hex(16)
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,64}',value):
            raise web.HTTPBadRequest(text='Identifiant de session invalide')
        return value

    def authenticated(self,authorization,access=''):
        return (secrets.compare_digest(authorization.encode(),('Bearer '+self.state.token).encode())
                and self.state.password_auth.valid(access))

    @asynccontextmanager
    async def admit(self,identity,authorization,access=''):
        if not self.authenticated(authorization,access):raise web.HTTPUnauthorized(text='Code de connexion incorrect')
        task=asyncio.current_task()
        self.generation+=1;generation=self.generation
        previous=self.pending;self.pending=task
        if previous and previous is not task and not previous.done():previous.cancel()
        acquired=False
        try:
            await self.lock.acquire();acquired=True
            if generation!=self.generation:raise web.HTTPConflict(text='Connexion remplacée par une nouvelle demande.')
            if not self.authenticated(authorization,access):raise web.HTTPUnauthorized(text='Le code a changé.')
            await self.state.disconnect()
            self.state.session_id=identity
            self.state.connecting=True
            yield
        except asyncio.CancelledError:
            if acquired and self.state.session_id==identity:await self.state.disconnect()
            raise web.HTTPConflict(text='Connexion remplacée par une nouvelle demande.')
        except BaseException:
            if acquired and self.state.session_id==identity:await self.state.disconnect()
            raise
        finally:
            if acquired:self.lock.release()
            if self.pending is task:self.pending=None;self.state.connecting=False
