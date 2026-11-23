"""Persist successful preflight results, bound to the current Windows user."""
import ctypes
import hashlib
import hmac
import json
import os
from ctypes import wintypes
from pathlib import Path

from nexus_repacks.security import ACTIVE, Finding, ScanResult

VERSION = 1


def verified_files_unchanged(result):
    """Ignore saves/logs/media; detect changes to inspected code and new active files."""
    root = Path(result.root).resolve()
    expected = set(result.hashes)
    found = set()
    errors = []
    try:
        for folder, dirs, files in os.walk(root, followlinks=False, onerror=errors.append):
            if any((Path(folder) / name).is_symlink() or (Path(folder) / name).is_junction() for name in dirs):
                return False
            for name in files:
                p = Path(folder) / name
                relative = str(p.relative_to(root))
                relevant = relative in expected or p.suffix.lower() in ACTIVE or name.startswith('.')
                if not relevant:
                    continue
                if p.is_symlink() or relative not in expected:
                    return False
                stat = p.stat()
                if result.snapshot.get(relative) != [stat.st_size, stat.st_mtime_ns]:
                    return False
                found.add(relative)
        return not errors and found == expected
    except (OSError, ValueError):
        return False


class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def dpapi(data, decrypt=False):
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel.LocalFree(outgoing.pbData)


def save_verified(path, game, result):
    if result.blocked or not result.finished:
        return False
    raw = json.dumps({'version': VERSION, 'launcher': game.launcher, 'result': result.to_dict()},
                     ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    protected = dpapi(hashlib.sha256(raw).digest() + raw)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_bytes(protected)
    temp.replace(path)
    return True


def load_verified(path, game):
    try:
        path = Path(path)
        if path.stat().st_size > 40 * 1024 * 1024:
            return None
        data = dpapi(path.read_bytes(), decrypt=True)
        digest, raw = data[:32], data[32:]
        if not hmac.compare_digest(digest, hashlib.sha256(raw).digest()):
            return None
        cached = json.loads(raw)
        if cached['version'] != VERSION or cached['launcher'] != game.launcher:
            return None
        data = cached['result']
        if Path(data['root']).resolve() != Path(game.root).resolve():
            return None
        result = ScanResult(root=data['root'], started=data['started'], finished=data['finished'],
                            files=data['files'], hashes=data['hashes'], snapshot=data['snapshot'],
                            findings=[Finding(**f) for f in data['findings']], engine=data['engine'])
        if result.blocked or not result.finished or result.engine != ScanResult('').engine:
            return None
        return result
    except (OSError, ValueError, TypeError, KeyError):
        return None
