"""Static inspection only. Never import, unpickle or execute a game file."""
from __future__ import annotations

import base64
import ast
import hashlib
import io
import json
import os
import pickletools
import re
import struct
import time
import zipfile
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

KNOWN = {
    '7123e1514b939b165985560057fe3c761440a9fff9783a3b84e861fd2888d4ab': 'Launcher from the analyzed Ren’Py sample',
    '271ba916be2f399e210739345cf5f142d165d0cd0ecd0e13b9af9d1977133bf4': 'Malicious Ren’Py loader archive',
    'd4007a71a6d3af6e6ec732ccee6be9c4bafeef2a35b03d7aeb4afb63e79bf008': 'XOR-hidden ZIP payload',
    'df5602861a28a95e466c57e8c49f316687a66e30c884b0760020c7f8499aaabe': 'EventEmitter host used by this sample',
    '4d1003846a3da1305e0da9ac176a88e1df728d4dbe3dfb7b2472bc3c4970035b': 'Malicious ETWProviders proxy DLL',
    '145543857b7a17d3d0122c0b9f851729b96f7c9abf72610574e7d436461d174e': 'Hidden loader configuration',
}
ACTIVE = {'.exe', '.dll', '.pyd', '.bat', '.cmd', '.ps1', '.py', '.pyc', '.rpy', '.rpyc', '.rpym', '.rpymc', '.rpa', '.lnk', '.vbs', '.js', '.msi', '.scr', '.com', '.hta'}
TEXT = {'.bat', '.cmd', '.ps1', '.py', '.rpy', '.rpym', '.vbs', '.js', '.hta'}
MAX_MEMBER = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_FILES = 150000


def encoded_python_execution(source):
    """Follow decoder results into exec/eval within a single Python scope."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        # Ren'Py syntax is not a Python module. Only direct decoder-to-exec calls
        # are inferred here; compiled Ren'Py Python blocks are parsed separately.
        return bool(re.search(r'\b(?:exec|eval)\s*\(\s*(?:(?:base64|marshal)\s*\.\s*)?(?:b64decode|urlsafe_b64decode|loads)\s*\(', source))
    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    decoders = {'b64decode', 'urlsafe_b64decode', 'a85decode', 'b85decode'}
    def decoded(node):
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            fn = call.func
            if isinstance(fn, ast.Name) and fn.id in decoders:
                return True
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                if (fn.value.id == 'marshal' and fn.attr == 'loads') or (fn.value.id == 'base64' and fn.attr in decoders):
                    return True
        return False
    for scope in scopes:
        nodes = []
        def visit(node):
            if node is not scope and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                return
            nodes.append(node)
            for child in ast.iter_child_nodes(node):
                visit(child)
        visit(scope)
        tainted = set()
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                uses_tainted = any(isinstance(n, ast.Name) and n.id in tainted for n in ast.walk(node.value))
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name):
                            if decoded(node.value) or uses_tainted:
                                tainted.add(name.id)
                            else:
                                tainted.discard(name.id)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('exec', 'eval') and node.args:
                if decoded(node.args[0]) or any(isinstance(n, ast.Name) and n.id in tainted for n in ast.walk(node.args[0])):
                    return True
    return False


def sha256(path: Path, progress=None, cancel=None) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(1024 * 1024):
            if cancel and cancel():
                raise InterruptedError('Scan cancelled.')
            h.update(block)
    return h.hexdigest()


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    message: str


@dataclass
class ScanResult:
    root: str
    started: float = field(default_factory=time.time)
    finished: float = 0
    files: int = 0
    hashes: dict = field(default_factory=dict)
    snapshot: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    engine: str = 'Nexus Static 1.1 / RenPy-ETW rules 2026-11-19'

    @property
    def blocked(self):
        return any(f.severity in ('danger', 'warning', 'incomplete') for f in self.findings)

    @property
    def status(self):
        if any(f.severity == 'danger' for f in self.findings):
            return 'BLOCKED'
        return 'NEEDS REVIEW' if self.blocked else 'NO INDICATORS DETECTED'

    def to_dict(self):
        return dict(asdict(self), status=self.status, blocked=self.blocked)


class Scanner:
    def __init__(self, progress=None, cancel=None, inspect_archives=True):
        self.progress = progress or (lambda text: None)
        self.cancel = cancel or (lambda: False)
        self.expanded = 0
        self.result = None
        self._seen = set()
        self.inspect_archives = inspect_archives

    def add(self, severity, rule, path, message):
        key = (rule, str(path))
        if key not in self._seen:
            self._seen.add(key)
            self.result.findings.append(Finding(severity, rule, str(path), message))

    def scan(self, root: Path):
        root = root.resolve(strict=True)
        self.result = ScanResult(str(root))
        self.expanded = 0
        self._seen.clear()
        if not root.is_dir():
            raise ValueError('Select a game folder.')
        def onerror(err):
            self.add('incomplete', 'read-error', err.filename or root, 'Folder inaccessible.')
        for folder, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
            for name in list(dirs):
                p = Path(folder) / name
                if p.is_symlink() or p.is_junction():
                    dirs.remove(name)
                    self.add('incomplete', 'reparse', p, 'Link or junction skipped: incomplete inspection.')
            for name in files:
                if self.cancel():
                    self.add('incomplete', 'cancelled', root, 'Scan cancelled.')
                    break
                p = Path(folder) / name
                self.result.files += 1
                if self.result.files > MAX_FILES:
                    self.add('incomplete', 'file-limit', root, 'File count limit reached.')
                    break
                if self.result.files % 20 == 0:
                    self.progress(f'Inspecting · {self.result.files:,} files · {p.name}')
                try:
                    if p.is_symlink():
                        self.add('incomplete', 'symlink', p, 'File link not inspected.')
                        continue
                    st = p.stat()
                    self.result.snapshot[str(p.relative_to(root))] = [st.st_size, st.st_mtime_ns]
                    ext = p.suffix.lower()
                    if ext in ('.zip', '.rar', '.7z', '.iso') and not self.inspect_archives:
                        self.add('info', 'unused-archive', p, 'Archive stored alongside the game: not used for this launch. Scan it separately from Downloads.')
                        continue
                    if ext == '.zip':
                        self.inspect_zip(p, str(p))
                    elif ext in ('.rar', '.7z', '.iso'):
                        self.add('incomplete', 'unsupported-archive', p, 'Archive not inspected. Extract it without running its contents, then scan the extracted folder.')
                    elif ext in ACTIVE or name.startswith('.') or ext in ('.u6', '.rpmc'):
                        digest = sha256(p, cancel=self.cancel)
                        self.result.hashes[str(p.relative_to(root))] = digest
                        if digest in KNOWN:
                            self.add('danger', 'known-sha256', p, KNOWN[digest])
                        if ext == '.rpa':
                            self.inspect_rpa(p)
                        elif st.st_size <= MAX_MEMBER:
                            self.inspect_bytes(p.read_bytes(), str(p), ext)
                        elif ext in ACTIVE:
                            self.add('incomplete', 'large-active', p, 'Active file too large for content inspection; SHA-256 calculated.')
                    if ext in ('.bin', '.rpmc') and st.st_size > 50 * 1024 * 1024:
                        with p.open('rb') as f:
                            samples = []
                            for pos in (0, st.st_size // 2, max(0, st.st_size - 4096)):
                                f.seek(pos)
                                samples.append(f.read(4096))
                        if samples and all(s and not any(s) for s in samples):
                            self.add('warning', 'zero-padding', p, 'Large file appears filled with zeros: possible padding, review required.')
                except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, zlib.error, struct.error) as exc:
                    self.add('incomplete', 'inspection-error', p, f'Inspection unavailable: {type(exc).__name__}.')
            if self.cancel() or self.result.files > MAX_FILES:
                break
        # Names and small size are context only, never a malware verdict by themselves.
        small_setup = any(Path(p).name.lower() in ('setup.exe', 'setup.py') for p in self.result.snapshot)
        total = sum(v[0] for v in self.result.snapshot.values())
        if small_setup and total < 20 * 1024 * 1024:
            self.add('info', 'small-setup', root, 'Small package with setup: check its source. Size and name alone do not prove infection.')
        self.result.finished = time.time()
        self.progress(f'{self.result.status} · {self.result.files:,} files')
        return self.result

    def inspect_bytes(self, data, label, ext='', depth=0):
        digest = hashlib.sha256(data).hexdigest()
        if digest in KNOWN:
            self.add('danger', 'known-sha256', label, KNOWN[digest])
        lower = data.lower()
        if b'ipapi.click' in lower:
            self.add('danger', 'campaign-domain', label, 'Reporting domain found in the analyzed sample.')
        if b'etwprovidersavvozneera' in lower and b'__rust' in lower:
            self.add('danger', 'etw-rust-proxy', label, 'ETW proxy DLL and Rust runtime combination from the analyzed payload.')
        if ext in TEXT or ext in ('.pyc', '.pyd', '.exe', '.dll') or 'RenPy code' in label:
            self.inspect_text(data.decode('utf-8', errors='replace'), label,
                              python_source=ext in ('.py', '.rpy', '.rpym') or 'RenPy code' in label)
        if ext == '.lnk':
            self.add('warning', 'shortcut', label, 'Executable shortcut: target not validated, launch blocked.')
        if ext in ('.rpyc', '.rpymc'):
            if data.startswith(b'RENPY RPC2'):
                self.inspect_rpc(data, label)
            else:
                # RPYC v1 has no RPC2 header: a zlib stream containing a pickle.
                # Parse literal opcodes only; never construct the stored objects.
                try:
                    self.inspect_pickle(self.bounded_zlib(data), label)
                except (ValueError, zlib.error):
                    self.add('incomplete', 'compiled-renpy-format', label, 'Unrecognized compiled Ren’Py format: inspection unavailable.')
        if Path(label).name.startswith('.') and len(data) < 65536:
            try:
                raw = base64.b64decode(data, validate=True)
                key = b'81034149cd6f48c8821340204f92766e'
                meta = json.loads(bytes(v ^ key[i % len(key)] for i, v in enumerate(raw)))
                if isinstance(meta, dict) and {'file_nm', 'pasw', 'exc_fl'} <= meta.keys():
                    self.add('danger', 'renpy-hidden-metadata', label, 'Hidden Ren’Py loader configuration: XOR payload and target executable.')
            except (ValueError, UnicodeError, TypeError):
                pass

    def inspect_text(self, text, label, python_source=True):
        s = text.lower()
        patterns = {
            'xor-loader': ('xor_decrypt_to_memory', 'extract_and_run'),
            'hidden-launch': ('forfiles.exe', 'subprocess.popen', 'zipfile'),
            'renpy-dropper': ('config.gamedir', 'base64.b64decode', 'zone.identifier', 'subprocess'),
            'discord-token': ('discord', 'leveldb', 'token'),
            'browser-secrets': ('login data', 'local state', 'decrypt'),
        }
        for rule, terms in patterns.items():
            if all(t in s for t in terms):
                self.add('danger', rule, label, 'Suspicious function combination: ' + ', '.join(terms))
        encoded = ('frombase64string', ' -enc ', ' -encodedcommand', 'iex(', 'invoke-expression')
        if ('powershell' in s or 'pwsh' in s) and any(t in s for t in encoded):
            self.add('warning', 'encoded-powershell', label, 'Encoded PowerShell or dynamic evaluation in a launcher.')
        if python_source and ('b64decode' in s or 'marshal.loads' in s) and encoded_python_execution(text):
            self.add('warning', 'encoded-python', label, 'Python code decoded then executed dynamically.')
        if any(t in s for t in ('add-mppreference', 'set-mppreference', 'disableantispyware', 'disablerealtimemonitoring')):
            self.add('danger', 'defender-tampering', label, 'Attempt to modify or disable Microsoft Defender.')
        if '/webhooks/' in s and ('discord.com' in s or 'discordapp.com' in s):
            self.add('warning', 'discord-webhook', label, 'Discord webhook in active content.')

    def bounded_zlib(self, data):
        dec = zlib.decompressobj()
        raw = dec.decompress(data, 16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024 or not dec.eof:
            raise ValueError('Uncompressed size too large')
        return raw

    def inspect_rpc(self, data, label):
        if not data.startswith(b'RENPY RPC2'):
            return
        found = False
        for i in range(10, min(len(data) - 11, 10 + 12 * 8), 12):
            slot, off, length = struct.unpack_from('<III', data, i)
            if not slot:
                break
            if slot != 1:
                continue
            if off + length > len(data):
                raise ValueError('Truncated RPC')
            raw = self.bounded_zlib(data[off:off + length])
            self.inspect_pickle(raw, label)
            found = True
        if not found:
            self.add('incomplete', 'rpc-slot', label, 'No inspectable Ren’Py blocks.')

    def inspect_pickle(self, raw, label):
        recent = []
        terminated = False
        forbidden = {
            ('os', 'system'), ('posix', 'system'), ('nt', 'system'), ('subprocess', 'Popen'),
            ('subprocess', 'call'), ('subprocess', 'check_output'), ('builtins', 'exec'),
            ('builtins', 'eval'), ('__builtin__', 'exec'), ('__builtin__', 'eval'),
        }
        for op, value, _ in pickletools.genops(raw):
            if op.name == 'STOP':
                terminated = True
            if isinstance(value, (str, bytes)):
                text = value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value
                recent.append(text)
                recent = recent[-2:]
                if len(text) > 30:
                    self.inspect_text(text, label + ' [RenPy code]')
            reference = None
            if op.name == 'GLOBAL' and isinstance(value, str):
                reference = tuple(value.split(' ', 1))
            elif op.name == 'STACK_GLOBAL' and len(recent) == 2:
                reference = tuple(recent)
            if reference in forbidden:
                self.add('danger', 'pickle-execution-global', label,
                         'Dangerous executable reference in pickle: ' + '.'.join(reference))
        if not terminated:
            raise ValueError('Incomplete pickle')

    def inspect_rpa(self, path):
        with path.open('rb') as f:
            header = f.readline(128)
            if not header.startswith(b'RPA-3.0 '):
                self.add('incomplete', 'rpa-version', path, 'Unsupported Ren’Py archive version.')
                return
            fields = header.split()
            off, key = int(fields[1], 16), int(fields[2], 16)
            size = path.stat().st_size
            if off > size or size - off > MAX_MEMBER:
                raise ValueError('RPA index too large')
            f.seek(off)
            ops = list(pickletools.genops(self.bounded_zlib(f.read())))
            # Parse only literal filename/int tuples. No pickle.load, GLOBAL or REDUCE is evaluated.
            for i, (op, name, _) in enumerate(ops):
                if op.name not in ('SHORT_BINUNICODE', 'BINUNICODE', 'UNICODE', 'SHORT_BINSTRING', 'BINSTRING') or not isinstance(name, str):
                    continue
                if Path(name).suffix.lower() not in ACTIVE:
                    continue
                ints = []
                for o, v, _ in ops[i + 1:i + 16]:
                    if o.name in ('BININT', 'BININT1', 'BININT2', 'LONG1', 'INT') and isinstance(v, int):
                        ints.append(v)
                    if len(ints) == 2:
                        break
                if len(ints) != 2:
                    self.add('incomplete', 'rpa-entry', f'{path}!{name}', 'Cannot interpret RPA entry.')
                    continue
                start, length = (v ^ key for v in ints)
                if start < len(header) or length < 0 or start + length > off or length > MAX_MEMBER:
                    self.add('incomplete', 'rpa-bounds', f'{path}!{name}', 'RPA entry out of bounds or oversized.')
                    continue
                f.seek(start)
                self.inspect_bytes(f.read(length), f'{path}!{name}', Path(name).suffix.lower())

    def inspect_zip(self, source, label, depth=0):
        if depth > 2:
            self.add('incomplete', 'archive-depth', label, 'Nested archive limit reached.')
            return
        with zipfile.ZipFile(source) as archive:
            if len(archive.infolist()) > MAX_FILES:
                self.add('incomplete', 'archive-count', label, 'Too many ZIP entries.')
                return
            for member in archive.infolist():
                if self.cancel():
                    raise ValueError('Cancelled')
                normalized = member.filename.replace('\\', '/')
                if normalized.startswith(('/', '//')) or '..' in normalized.split('/') or ':' in normalized:
                    self.add('danger', 'zip-traversal', label, 'Unsafe archive output path: ' + normalized)
                ext = Path(normalized).suffix.lower()
                if member.flag_bits & 1:
                    self.add('incomplete', 'encrypted-zip', f'{label}!{normalized}', 'Encrypted archive: contents not verified.')
                    continue
                if ext not in ACTIVE | {'.zip', '.7z', '.rar'} and not Path(normalized).name.startswith('.'):
                    continue
                if member.file_size > MAX_MEMBER or self.expanded + member.file_size > MAX_EXPANDED:
                    self.add('incomplete', 'archive-budget', f'{label}!{normalized}', 'ZIP inspection limit reached for an active file.')
                    continue
                if member.file_size > 1024 * 1024 and member.file_size / max(1, member.compress_size) > 300:
                    self.add('incomplete', 'zip-ratio', label, 'Excessive compression ratio: decompression skipped.')
                    continue
                self.expanded += member.file_size
                with archive.open(member) as stream:
                    data = stream.read(MAX_MEMBER + 1)
                if len(data) > MAX_MEMBER:
                    raise ValueError('ZIP limit')
                if ext == '.zip':
                    self.inspect_zip(io.BytesIO(data), f'{label}!{normalized}', depth + 1)
                elif ext in ('.7z', '.rar', '.rpa'):
                    self.add('incomplete', 'nested-archive', f'{label}!{normalized}', 'Nested archive: extract and scan separately.')
                else:
                    self.inspect_bytes(data, f'{label}!{normalized}', ext)


def snapshot_unchanged(result: ScanResult) -> bool:
    """Do not reuse an old verdict when any game file was added/removed/changed."""
    current = {}
    root = Path(result.root)
    try:
        for folder, dirs, files in os.walk(root, followlinks=False):
            if any((Path(folder) / d).is_symlink() or (Path(folder) / d).is_junction() for d in dirs):
                return False
            for name in files:
                p = Path(folder) / name
                if p.is_symlink():
                    return False
                st = p.stat()
                current[str(p.relative_to(root))] = [st.st_size, st.st_mtime_ns]
        return current == result.snapshot
    except OSError:
        return False
