"""Required second credential, with a protected verifier and short-lived access tickets."""
import hashlib
import json
from pathlib import Path
import secrets
import time
from collections import deque
from host.code_store import crypt


class PasswordAuth:
    def __init__(self, path=None):
        self.verifier=None;self.tickets={};self.attempts=deque()
        if path and Path(path).exists():
            data=json.loads(crypt(Path(path).read_bytes(),unprotect=True))
            self.verifier=(bytes.fromhex(data['salt']),bytes.fromhex(data['hash']))
            if len(self.verifier[0])!=16 or len(self.verifier[1])!=32:
                raise ValueError('Configuration du mot de passe invalide')

    @staticmethod
    def derive(password,salt):
        return hashlib.scrypt(password.encode('utf-8'),salt=salt,n=16384,r=8,p=1,dklen=32)

    @classmethod
    def configure(cls,path,password):
        if not isinstance(password,str) or not password or len(password)>256:
            raise ValueError('Un mot de passe est obligatoire (256 caractÃ¨res maximum).')
        salt=secrets.token_bytes(16)
        payload=json.dumps({'salt':salt.hex(),'hash':cls.derive(password,salt).hex()}).encode()
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        # Same Windows-account encryption as the connection code; no plaintext password.
        import os,tempfile
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
            temporary=Path(f.name);f.write(crypt(payload))
        try:os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)

    def reserve_attempt(self):
        now=time.monotonic()
        while self.attempts and self.attempts[0]<now-60:self.attempts.popleft()
        if len(self.attempts)>=10:return False
        self.attempts.append(now);return True

    def verify(self,password):
        if not self.verifier or not isinstance(password,str) or not password or len(password)>256:return False
        salt,expected=self.verifier
        return secrets.compare_digest(self.derive(password,salt),expected)

    def issue(self):
        now=time.monotonic()
        self.tickets={key:expiry for key,expiry in self.tickets.items() if expiry>now}
        if len(self.tickets)>=100:self.tickets.pop(next(iter(self.tickets)))
        ticket=secrets.token_urlsafe(32)
        self.tickets[hashlib.sha256(ticket.encode()).digest()]=now+8*3600
        return ticket

    def valid(self,ticket):
        if not self.verifier or not isinstance(ticket,str) or len(ticket)>128:return False
        key=hashlib.sha256(ticket.encode()).digest()
        return self.tickets.get(key,0)>time.monotonic()
