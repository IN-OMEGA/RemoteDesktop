"""Signed portable updates; download in background, replace only after exit."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.parse
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from nexus_repacks.library import STATE, asset_path, atomic_json

MAX_UPDATE = 256 * 1024 * 1024
CHECK_INTERVAL_MS = 5000
INITIAL_CHECK_MS = 700


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Invalid version')
    return tuple(map(int, value.split('.')))


def payload(manifest):
    return json.dumps({k: manifest[k] for k in ('version', 'url', 'sha256', 'size')},
                      sort_keys=True, separators=(',', ':')).encode('utf-8')


def https(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('HTTPS address required')
    return url


def open_https(url):
    request = urllib.request.Request(https(url), headers={'User-Agent': 'NexusRepacks-Updater/2',
        'Cache-Control': 'no-cache, no-store', 'Pragma': 'no-cache'})
    response = urllib.request.urlopen(request, timeout=25)
    try:
        https(response.url)
    except Exception:
        response.close()
        raise
    return response


def validate(manifest, public_key, current):
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
        base64.b64decode(manifest['signature'], validate=True), payload(manifest))
    https(manifest['url'])
    if not re.fullmatch('[a-f0-9]{64}', manifest['sha256']):
        raise ValueError('Invalid digest')
    if type(manifest['size']) is not int or not 1024 <= manifest['size'] <= MAX_UPDATE:
        raise ValueError('Invalid update size')
    return version(manifest['version']) > version(current)


def download(manifest, directory, progress=lambda ratio: None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix='update-', suffix='.exe', dir=directory)
    path = Path(filename)
    digest, total = hashlib.sha256(), 0
    try:
        with os.fdopen(fd, 'wb') as output, open_https(manifest['url']) as response:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > manifest['size']:
                    raise ValueError('Download too large')
                digest.update(chunk)
                output.write(chunk)
                progress(total / manifest['size'])
        if total != manifest['size'] or digest.hexdigest() != manifest['sha256']:
            raise ValueError('Corrupted update')
        with path.open('rb') as source:
            if source.read(2) != b'MZ':
                raise ValueError('Invalid EXE')
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def ps_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def replacement_script(staged, target, digest, pid, log, backup=None, restart=False):
    # Literal PowerShell strings: paths are never interpreted as shell code.
    recover = "if (Test-Path -LiteralPath $target) { try { Start-Process -FilePath $target -ArgumentList '--updated' } catch {} }" if restart else ''
    return f"""$ErrorActionPreference = 'Stop'
$staged = {ps_literal(staged)}
$target = {ps_literal(target)}
$backup = {ps_literal(backup if backup is not None else str(target) + '.update-backup')}
$log = {ps_literal(log)}
try {{
    $process = Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue
    if ($process) {{ $process | Wait-Process -Timeout 120 -ErrorAction Stop }}
    if ((Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash.ToLowerInvariant() -ne {ps_literal(digest)}) {{ throw 'SHA256 mismatch' }}
    $done = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {{
        try {{
            [System.IO.File]::Replace($staged, $target, $backup, $true)
            $done = $true
            break
        }} catch {{ Start-Sleep -Milliseconds 1000 }}
    }}
    if (-not $done) {{ throw 'Cannot replace executable; original kept' }}
    'Update installed.' | Set-Content -LiteralPath $log -Encoding UTF8
    {"Start-Process -FilePath $target -ArgumentList '--updated'" if restart else ''}
}} catch {{
    $_.Exception.Message | Set-Content -LiteralPath $log -Encoding UTF8
    {recover}
}}
"""


class AutoUpdater:
    def __init__(self, owner, current):
        self.owner, self.current = owner, current
        self.lock = threading.Lock()
        self.pending = None
        self.stopped = threading.Event()
        self.latest = None

    def status(self, text):
        self.owner.post('call', lambda: self.owner.update_button.configure(text=text))

    def notify(self, stage, manifest, ratio=None, error=''):
        callback = getattr(self.owner, 'on_update_event', None)
        if callback:
            self.owner.post('call', lambda: callback(stage, manifest, ratio, error))

    def record(self, phase, manifest=None, error=''):
        try:
            atomic_json(STATE / 'update-state.json', {
                'running_version': self.current, 'latest_version': manifest.get('version') if manifest else None,
                'phase': phase, 'checked_at': time.time(), 'error': error})
        except OSError:
            pass

    def fetch_manifest(self, config):
        urls = [config[key] for key in ('channel_url', 'manifest_url') if config.get(key)]
        for index, url in enumerate(urls):
            # A distinct URL per polling window avoids a cached /latest redirect.
            url += ('&' if '?' in url else '?') + 'nexus_check=' + str(int(time.time() // 5))
            try:
                with open_https(url) as response:
                    data = response.read(65537)
                if len(data) > 65536:
                    raise ValueError('Update manifest too large')
                return json.loads(data)
            except OSError:
                if index + 1 == len(urls):
                    raise
        raise ValueError('No update channel configured')

    def check(self):
        if not getattr(sys, 'frozen', False) or self.stopped.is_set():
            return
        if not self.lock.acquire(blocking=False):
            return
        def run():
            try:
                if not self.pending:
                    self.status('Checking for updates…')
                config = json.loads(asset_path('nexus_repacks/update_config.json').read_text('utf-8'))
                manifest = self.fetch_manifest(config)
                baseline = self.pending[1]['version'] if self.pending else self.current
                newer = validate(manifest, config['public_key'], baseline)
                if not newer and config.get('channel_url'):
                    # A failed channel publication must not hide a public release.
                    try:
                        fallback = self.fetch_manifest({'manifest_url': config['manifest_url']})
                        fallback_newer = validate(fallback, config['public_key'], baseline)
                        if version(fallback['version']) > version(manifest['version']):
                            manifest, newer = fallback, fallback_newer
                    except OSError:
                        pass
                if self.latest and version(self.latest['version']) > version(manifest['version']):
                    manifest = self.latest
                    newer = validate(manifest, config['public_key'], baseline)
                if not newer:
                    self.record('ready' if self.pending else 'current', self.pending[1] if self.pending else manifest)
                    if self.pending:
                        self.notify('ready', self.pending[1], 1.)
                    else:
                        self.status('Nexus ' + self.current + ' · up to date')
                    return
                self.latest = manifest
                self.record('downloading', manifest)
                # Queue the visible notice before doing any large download.
                self.notify('available', manifest)
                self.status('Update ' + manifest['version'] + ' · downloading…')
                # Same volume as target for atomic File.Replace; never touch games/state.
                path = download(manifest, Path(sys.executable).parent / '.nexus-updates',
                                progress=lambda ratio: self.notify('downloading', manifest, ratio))
                if self.stopped.is_set():
                    path.unlink(missing_ok=True)
                    return
                previous = self.pending
                self.pending = (path, manifest)
                if previous and previous[0] != path:
                    previous[0].unlink(missing_ok=True)
                self.record('ready', manifest)
                self.notify('ready', manifest, 1.)
                self.status('Version ' + manifest['version'] + ' ready · update & restart')
            except Exception as exc:
                (STATE / 'update-check.log').write_text(str(exc), encoding='utf-8')
                self.record('error', self.latest, str(exc))
                if self.latest:
                    self.notify('error', self.latest, error=str(exc))
                self.status('Update check failed · click to retry')
            finally:
                self.lock.release()
        threading.Thread(target=run, daemon=True, name='Nexus-updates').start()

    def on_close(self, restart=False):
        self.stopped.set()
        if not self.pending:
            return
        staged, manifest = self.pending
        folder = STATE / 'updates'
        folder.mkdir(exist_ok=True)
        script = folder / ('apply-' + uuid.uuid4().hex + '.ps1')
        script.write_text(replacement_script(staged, Path(sys.executable), manifest['sha256'],
                                             os.getpid(), folder / 'install.log', staged.parent / 'previous.exe', restart=restart), encoding='utf-8-sig')
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                          '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                         creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
