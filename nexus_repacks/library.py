from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

STATE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'NexusRepacks'
STATE.mkdir(parents=True, exist_ok=True)
DEFAULT_ROOT = Path.home() / 'OneDrive' / 'Desktop' / 'REPACKS'


def asset_path(relative):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return base / relative


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def clean_title(name):
    name = re.sub(r'(?i)([-_ ]+(ankergames|repack|fitgirl|dodi))\b.*', '', name)
    name = re.sub(r'(?i)[-_ ]+v?\d+(?:\.\d+){1,3}.*', '', name)
    name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
    return re.sub(r'[_-]+', ' ', name).strip()


@dataclass
class Game:
    id: str
    title: str
    root: str
    launcher: str
    source: str = 'REPACKS'
    description: str = ''
    image: str = ''
    metadata_url: str = ''
    platform_id: str = ''

    @classmethod
    def local(cls, root, launcher, title=None, source='REPACKS'):
        root, launcher = Path(root).resolve(), Path(launcher).resolve()
        ident = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:20]
        return cls(ident, title or clean_title(root.name), str(root), str(launcher), source)


def candidates(root):
    root = Path(root)
    choices = []
    for folder, dirs, files in os.walk(root, followlinks=False):
        rel = Path(folder).relative_to(root)
        dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink() and not (Path(folder) / d).is_junction()]
        if len(rel.parts) >= 5:
            dirs[:] = []
        if any(p.lower() in ('renpy', 'lib', 'monobleedingedge', 'd3d12', 'redist', '_commonredist', 'engine') or p.lower().endswith('_data') for p in rel.parts):
            dirs[:] = []
            continue
        for name in files:
            p = Path(folder) / name
            if p.is_symlink() or p.suffix.lower() not in ('.exe', '.bat', '.cmd'):
                continue
            low = name.lower()
            if any(x in low for x in ('crashhandler', 'unins', 'vcredist', 'dxsetup', 'unitycrash', 'aria2', 'nexus repacks', 'python')):
                continue
            score = 20 if p.suffix.lower() == '.exe' else 5
            if low in ('run me!.bat', 'run me.bat', 'run.bat', 'start.bat'):
                score += 7
            if any(x in low for x in ('setup', 'install')):
                score -= 30
            if (p.parent / (p.stem + '_Data')).is_dir():
                score += 50
            title_words = set(re.findall(r'[a-z]{3,}', clean_title(root.name).lower()))
            score += 10 * len(title_words & set(re.findall(r'[a-z]{3,}', clean_title(p.stem).lower())))
            if len(rel.parts) < 3:
                score += 5
            choices.append((score, p))
    return [p for _, p in sorted(choices, key=lambda item: (-item[0], str(item[1]).lower()))]


def discover(root):
    games = []
    root = Path(root)
    if not root.is_dir():
        return games
    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.is_symlink() or p.is_junction():
            continue
        found = candidates(p)
        if found:
            # Keep the package root: shared DLLs and wrapper scripts must also be inspected.
            games.append(Game.local(p, found[0]))
    return games


def epic_games():
    games = []
    manifest_dir = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'Epic/EpicGamesLauncher/Data/Manifests'
    for p in manifest_dir.glob('*.item'):
        data = read_json(p, {})
        root = Path(data.get('InstallLocation', '__missing__'))
        exe = root / data.get('LaunchExecutable', '__missing__')
        if data.get('bIsIncompleteInstall') or not exe.is_file() or not exe.resolve().is_relative_to(root.resolve()):
            continue
        if exe.suffix.lower() != '.exe':
            continue
        game = Game.local(root, exe, data.get('DisplayName') or root.name, 'EPIC GAMES')
        game.platform_id = data.get('AppName', '')
        games.append(game)
    return games


def windows_apps():
    """User chooses a Start-menu application; do not claim all apps are games."""
    command = '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress'
    p = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command], capture_output=True, timeout=25, creationflags=0x08000000)
    try:
        data = json.loads(p.stdout.decode('utf-8-sig', errors='replace'))
    except ValueError:
        data = json.loads(p.stdout.decode('cp1252', errors='replace'))
    if isinstance(data, dict):
        data = [data]
    return [d for d in data or [] if '!' in d.get('AppID', '')]


def metadata(game):
    query = clean_title(game.title)
    url = 'https://en.wikipedia.org/w/rest.php/v1/search/page?' + urllib.parse.urlencode({'q': query + ' video game', 'limit': 5})
    req = urllib.request.Request(url, headers={'User-Agent': 'NexusRepacks/1.0 (local desktop game library)'})
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.load(response)
    words = set(re.findall(r'\w+', query.lower()))
    ranked = sorted(data.get('pages', []), key=lambda d: len(words & set(re.findall(r'\w+', d.get('title', '').lower()))), reverse=True)
    if not ranked or not words & set(re.findall(r'\w+', ranked[0].get('title', '').lower())):
        return {'description': 'No matching game details found. You can add a description manually.'}
    page = ranked[0]
    return {'description': page.get('description') or re.sub('<[^>]+>', '', page.get('excerpt', '')),
            'metadata_url': 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(page.get('key', page['title'])),
            'image_url': page.get('thumbnail', {}).get('url', '')}


def local_image(game):
    root = Path(game.root)
    names = ('cover.jpg', 'cover.png', 'poster.jpg', 'poster.png', 'game/gui/window_icon.png', 'gui/window_icon.png', 'game/gui/main_menu.png')
    for name in names:
        p = root / name
        if p.is_file() and p.stat().st_size < 12 * 1024 * 1024:
            return str(p)
    # Prefer static PE icon extraction over loading any game DLL or executable.
    if Path(game.launcher).suffix.lower() == '.exe':
        try:
            from nexus_repacks.pe_icon import extract_icon
            ico = extract_icon(Path(game.launcher))
            if ico:
                p = STATE / 'images' / (game.id + '.ico')
                p.parent.mkdir(exist_ok=True)
                p.write_bytes(ico)
                return str(p)
        except (OSError, ValueError, IndexError, KeyError):
            pass
    return ''


def load_library():
    data = read_json(STATE / 'library.json', [])
    games = []
    for d in data:
        try:
            games.append(Game(**d))
        except TypeError:
            continue
    return games


def save_library(games):
    atomic_json(STATE / 'library.json', [asdict(g) for g in games])
