from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import urllib.parse
import zipfile
from pathlib import Path

from nexus_repacks.library import asset_path

ARIA_SHA256 = 'be2099c214f63a3cb4954b09a0becd6e2e34660b886d4c898d260febfe9d70c2'
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def clean_line(line):
    return ANSI.sub('', line).strip()


def parse_progress(line):
    """Parse aria's console units without inventing progress for unknown totals."""
    line = clean_line(line)
    if line.startswith('FILE: '):
        return {'file': line[6:].strip()}
    match = re.search(r'\[#[a-fA-F0-9]+\s+(\S+)/(\S+)\((\d+)%\)(.*?)\]', line)
    if not match:
        return {}
    done, total, percent, tail = match.groups()
    fields = dict(re.findall(r'\b(CN|SD|DL|ETA):([^\s\]]+)', tail))
    def amount(value):
        m = re.fullmatch(r'([\d.]+)([KMGT]?)(?:i?B)?', value, re.I)
        return float(m[1]) * 1024**('KMGT'.index(m[2].upper())+1 if m[2] else 0) if m else None
    numerator, denominator = amount(done), amount(total)
    ratio = min(1, max(0, numerator/denominator)) if numerator is not None and denominator else None
    return {'done': done, 'total': total, 'ratio': ratio, 'percent': int(percent),
            'speed': fields.get('DL', '—'), 'eta': fields.get('ETA', '—'),
            'connections': fields.get('CN', '—'), 'seeders': fields.get('SD', '—')}


def aria_path():
    path = asset_path('nexus_repacks/vendor/aria2c.exe')
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != ARIA_SHA256:
        raise ValueError('The bundled aria2 binary is missing or modified. Download blocked.')
    return path


def build_command(source, destination, aria=None, referrer='', output_name=''):
    source = source.strip()
    if '\n' in source or '\r' in source or '\x00' in source:
        raise ValueError('Invalid link.')
    scheme = urllib.parse.urlparse(source).scheme.lower()
    torrent = Path(source).is_file() and Path(source).suffix.lower() == '.torrent'
    if scheme not in ('http', 'https', 'magnet') and not torrent:
        raise ValueError('Use an HTTP(S) link, magnet link or .torrent file.')
    command = [str(aria or aria_path()), '--no-conf=true', '--continue=true', '--file-allocation=none',
               '--auto-save-interval=1',
               '--auto-file-renaming=false', '--allow-overwrite=false', '--summary-interval=1',
               '--console-log-level=notice', '--download-result=full', '--check-certificate=true',
               '--max-tries=5', '--retry-wait=5', '--seed-time=0', '--bt-save-metadata=true',
               '--enable-rpc=false', '--follow-metalink=false', '--follow-torrent=false',
               '--on-download-complete=', '--on-download-start=', '--on-bt-download-complete=',
               '--on-download-error=', '--on-download-stop=', '--dir=' + str(Path(destination).resolve())]
    if scheme in ('http', 'https'):
        command += ['--max-connection-per-server=16', '--split=16', '--min-split-size=1M']
        if referrer:
            if urllib.parse.urlsplit(referrer).scheme not in ('http', 'https') or any(c in referrer for c in '\r\n\x00'):
                raise ValueError('Invalid source page.')
            command.append('--referer=' + referrer)
        if output_name:
            if any(c in output_name for c in '<>:"/\\|?*\r\n\x00') or output_name in ('.', '..') or output_name.endswith((' ', '.')):
                raise ValueError('Invalid output filename.')
            if output_name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
                raise ValueError('Reserved Windows filename.')
            command.append('--out=' + output_name)
    return command + ['--', source]


class Download:
    def __init__(self, source, destination, on_line, referrer='', output_name=''):
        self.source, self.destination, self.on_line = source, Path(destination), on_line
        self.process = None
        self.cancelled = False
        self._lock = threading.Lock()
        self.referrer, self.output_name = referrer, output_name

    def run(self):
        self.destination.mkdir(parents=True, exist_ok=True)
        command = build_command(self.source, self.destination, referrer=self.referrer, output_name=self.output_name)
        with self._lock:
            if self.cancelled:
                return -1
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, creationflags=0x08000000,
                                            encoding='utf-8', errors='replace', shell=False)
        for line in self.process.stdout:
            self.on_line(line.rstrip())
        return self.process.wait()

    def cancel(self):
        with self._lock:
            self.cancelled = True
            if self.process and self.process.poll() is None:
                self.process.terminate()


def extract_zip(source, destination, progress=lambda text: None):
    """No shell, overwrites, links, traversal or unbounded expansion."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Choose a new empty folder to extract the ZIP.')
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > 150000 or sum(m.file_size for m in members) > 150 * 1024 ** 3:
            raise ValueError('Archive too large for automatic extraction.')
        seen = set()
        for member in members:
            name = member.filename.replace('\\', '/')
            target = destination / name
            mode = member.external_attr >> 16
            if (name.startswith('/') or ':' in name or '..' in name.split('/') or mode & 0o170000 == 0o120000
                    or not target.resolve().is_relative_to(destination) or member.flag_bits & 1):
                raise ValueError('Encrypted archive, link or unsafe path: extraction refused.')
            canonical = str(target).casefold().rstrip(' .')
            if canonical in seen:
                raise ValueError('Duplicate ZIP paths.')
            seen.add(canonical)
            if any(p.rstrip(' .').split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for p in name.split('/')):
                raise ValueError('Reserved Windows filename.')
        destination.mkdir(parents=True)
        for i, member in enumerate(members):
            target = destination / member.filename.replace('\\', '/')
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.resolve().is_relative_to(destination):
                raise ValueError('The extraction folder changed.')
            progress(f'Extracting · {i + 1}/{len(members)} · {target.name}')
            with archive.open(member) as src, target.open('xb') as dst:
                remaining = member.file_size
                while remaining:
                    block = src.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError('Truncated archive.')
                    dst.write(block)
                    remaining -= len(block)
    return destination
