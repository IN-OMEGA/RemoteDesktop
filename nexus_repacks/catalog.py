"""Publisher-managed game catalog. No game code or remote scripts are loaded."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit

from nexus_repacks.library import asset_path

MAX_CATALOG = 2 * 1024 * 1024
MAX_GAMES = 2000
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def simple_name(value):
    return bool(isinstance(value, str) and value and len(value) <= 120 and
                not re.search(r'[<>:"/\\|?*\x00-\x1f]', value) and value not in ('.', '..') and
                not value.endswith((' ', '.')) and value.split('.')[0].upper() not in RESERVED)


def web_url(value, magnet=False):
    if not isinstance(value, str) or len(value) > 8192 or re.search(r'[\x00-\x20\x7f]', value):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ('http', 'https'):
            return bool(parsed.hostname and not parsed.username and not parsed.password)
        if magnet and parsed.scheme == 'magnet':
            return any(re.fullmatch(r'urn:btih:(?:[0-9a-fA-F]{40}|[A-Z2-7a-z2-7]{32})', xt)
                       for xt in parse_qs(parsed.query).get('xt', []))
    except ValueError:
        pass
    return False


@dataclass(frozen=True)
class CatalogGame:
    id: str
    title: str
    description: str
    download_url: str
    folder: str
    image: str = ''
    icon: str = ''
    filename: str = ''
    referrer: str = ''
    genre: str = ''
    size: str = ''
    enabled: bool = True


def parse_catalog(data):
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError('Catalog must have "version": 1 and a "games" array.')
    rows = data.get('games')
    if not isinstance(rows, list) or len(rows) > MAX_GAMES:
        raise ValueError(f'Catalog games must be an array with at most {MAX_GAMES} entries.')
    games, seen = [], set()
    fields = set(CatalogGame.__dataclass_fields__)
    for index, row in enumerate(rows, 1):
        prefix = f'Game #{index}: '
        if not isinstance(row, dict):
            raise ValueError(prefix + 'expected an object.')
        unknown = row.keys() - fields
        if unknown:
            raise ValueError(prefix + 'unknown field(s): ' + ', '.join(sorted(unknown)))
        for field, limit in (('id', 80), ('title', 160), ('description', 12000), ('download_url', 8192),
                             ('folder', 120), ('image', 8192), ('icon', 8192), ('filename', 120),
                             ('referrer', 8192), ('genre', 100), ('size', 80)):
            value = row.get(field, '')
            if not isinstance(value, str) or len(value) > limit or '\x00' in value:
                raise ValueError(prefix + field + ' must be text within its size limit.')
        ident = row.get('id', '')
        if not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', ident) or ident in seen:
            raise ValueError(prefix + 'id must be unique and use letters, digits, - or _.')
        if not row.get('title', '').strip() or not row.get('description', '').strip():
            raise ValueError(prefix + 'title and description are required.')
        if type(row.get('enabled', True)) is not bool:
            raise ValueError(prefix + 'enabled must be true or false.')
        enabled = row.get('enabled', True)
        if (enabled or row.get('download_url')) and not web_url(row.get('download_url'), magnet=True):
            raise ValueError(prefix + 'download_url must be an HTTP(S) file URL or valid magnet.')
        folder = row.get('folder') or ident
        if not simple_name(folder) or (row.get('filename') and not simple_name(row['filename'])):
            raise ValueError(prefix + 'folder/filename must be a simple Windows name.')
        if row.get('referrer') and not web_url(row['referrer']):
            raise ValueError(prefix + 'referrer must be an HTTP(S) URL.')
        for field in ('icon', 'image'):
            location = row.get(field, '')
            if location:
                if '://' in location:
                    if not web_url(location):
                        raise ValueError(prefix + field + ' must be an HTTP(S) URL or relative image path.')
                elif Path(location).is_absolute() or ':' in location or '..' in location.replace('\\', '/').split('/'):
                    raise ValueError(prefix + field + ' must stay inside the catalog folder.')
        seen.add(ident)
        values = dict(row, folder=folder, download_url=row.get('download_url', ''))
        games.append(CatalogGame(**values))
    return games


def load_catalog(path):
    path = Path(path)
    with path.open('rb') as source:
        content = source.read(MAX_CATALOG + 1)
    if len(content) > MAX_CATALOG:
        raise ValueError('Catalog is larger than 2 MiB.')
    try:
        return parse_catalog(json.loads(content.decode('utf-8-sig')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid catalog JSON: ' + str(exc)) from exc


def catalog_path(root=None):
    # Portable override is intentional and never overwritten by an application update.
    portable = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(root) if root else None
    if portable and (portable / 'catalog.json').is_file():
        return portable / 'catalog.json'
    return asset_path('nexus_repacks/catalog.json')


def local_art(directory, value):
    directory = Path(directory).resolve()
    result = (directory / value).resolve()
    if not result.is_relative_to(directory):
        raise ValueError('Image path is outside the catalog folder.')
    return result


if __name__ == '__main__':
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else catalog_path()
    games = load_catalog(path)
    print(f'Valid catalog: {len(games)} game(s) · {path}')
