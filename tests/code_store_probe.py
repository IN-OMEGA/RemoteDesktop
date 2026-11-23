"""Verify encrypted persistence across processes, rotation, and fail-closed corruption."""
import hashlib
from pathlib import Path
import secrets
import subprocess
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.code_store import CodeStore

def main():
    directory=Path('test-results')/('code-store-'+uuid.uuid4().hex)
    store=CodeStore(directory/'code.bin')
    original=secrets.token_urlsafe(18)
    assert store.load_or_create(initial_code=original)==original
    encrypted=store.path.read_bytes()
    assert original.encode() not in encrypted
    assert CodeStore(store.path).load_or_create(initial_code=secrets.token_urlsafe(18))==original
    script='from host.code_store import CodeStore;import hashlib,sys;print(hashlib.sha256(CodeStore(sys.argv[1]).load_or_create().encode()).hexdigest())'
    digest=subprocess.check_output([sys.executable,'-c',script,str(store.path)],text=True).strip()
    assert digest==hashlib.sha256(original.encode()).hexdigest()
    replacement=secrets.token_urlsafe(18)
    store.replace(replacement)
    assert CodeStore(store.path).load_or_create()==replacement and replacement!=original
    store.path.write_bytes(b'corrupt-file')
    try:store.load_or_create()
    except OSError:pass
    else:raise AssertionError('Corrupt code was silently replaced')
    assert store.path.read_bytes()==b'corrupt-file'
    print('PASS: encrypted code survives a new process; manual rotation persists; corrupt data is not replaced.')

if __name__=='__main__':main()
