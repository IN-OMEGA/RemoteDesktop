"""Use the public signed release and real exit helper; never execute the update."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from nexus_repacks import updater


def worker(folder):
    folder=Path(folder)
    target=folder/'Nexus fixture.exe'
    target.write_bytes(b'Harmless original update fixture. Never executed.')
    statuses=[]
    owner=SimpleNamespace(update_button=SimpleNamespace(configure=lambda **kw:statuses.append(kw['text'])),
                          post=lambda kind,callback:callback())
    with patch.object(sys,'frozen',True,create=True), patch.object(sys,'executable',str(target)), patch.object(updater,'STATE',folder):
        job=updater.AutoUpdater(owner,'2.1.1')
        job.check()
        if not job.lock.acquire(timeout=45):
            raise RuntimeError('Timed out checking the public update')
        job.lock.release()
        assert job.pending,statuses
        staged,manifest=job.pending
        assert target.read_bytes().startswith(b'Harmless original'), 'Replaced before closing'
        assert staged.exists()
        job.on_close()
        (folder/'expected.json').write_text(json.dumps({'digest':manifest['sha256'],'version':manifest['version'],
                                                     'statuses':statuses}),encoding='utf-8')


def main():
    if len(sys.argv)>1:
        worker(sys.argv[1])
        return
    with tempfile.TemporaryDirectory(prefix='nexus-public-update-') as directory:
        subprocess.run([sys.executable,'-m','tests.nexus_update_integration',directory],check=True,timeout=55)
        folder=Path(directory)
        deadline=time.monotonic()+20
        while not (folder/'updates/install.log').exists() and time.monotonic()<deadline:
            time.sleep(.1)
        log=(folder/'updates/install.log').read_text(encoding='utf-8-sig').strip()
        expected=json.loads((folder/'expected.json').read_text('utf-8'))
        target=folder/'Nexus fixture.exe'
        assert hashlib.sha256(target.read_bytes()).hexdigest()==expected['digest'],log
        assert (folder/'.nexus-updates/previous.exe').read_bytes().startswith(b'Harmless original'),log
        result={'public_release':expected['version'],'signed_background_download':True,
                'original_preserved_until_exit':True,'replacement_after_process_exit':True,
                'backup_preserved':True,'installer_log':log,'downloaded_exe_executed':False,
                'statuses':expected['statuses']}
        Path('docs/nexus-update-integration.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
