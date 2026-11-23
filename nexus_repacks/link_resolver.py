"""Resolve public download pages without running scripts or downloading payloads.

Only HTML/JSON is read. File bodies are left to aria2 after explicit confirmation.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path

MAX_PAGE = 2 * 1024 * 1024
FILE_EXTENSIONS = {'.zip', '.7z', '.rar', '.iso', '.exe', '.msi', '.torrent', '.tar', '.gz', '.xz', '.001', '.bin'}
DOWNLOAD_WORDS = ('download', 'télécharger', 'telecharger', 'direct link', 'mirror', 'lien direct', 'get file')
BAD_WORDS = ('advertisement', 'sponsored', 'casino', 'newsletter', 'subscribe', 'browser extension', 'vpn offer')
# Discovery hints only; these domains are never trusted or allowed to skip confirmation.
FILE_HOST_HINTS = {'mediafire.com', 'gofile.io', 'buzzheavier.com', 'fuckingfast.co',
                   '1fichier.com', 'pixeldrain.com', 'mega.nz', 'filecrypt.cc',
                   'drive.google.com', 'dropbox.com', 'krakenfiles.com', 'datanodes.to',
                   'multiup.io', 'multiup.org'}


class ResolutionCancelled(ValueError):
    pass


@dataclass
class Candidate:
    url: str
    label: str
    kind: str = 'page'
    filename: str = ''
    size: int | None = None
    content_type: str = ''
    source_page: str = ''
    score: int = 0

    @property
    def host(self):
        return urllib.parse.urlparse(self.url).hostname or ('BitTorrent' if self.kind == 'magnet' else 'Local file')


@dataclass
class Resolution:
    source: str
    final_url: str
    title: str = ''
    candidates: list[Candidate] = field(default_factory=list)
    direct: bool = False
    note: str = ''


class NetworkPolicy:
    def __init__(self, allow_local=False):
        self.allow_local = allow_local
        self.checked = set()

    def validate(self, url, resolve_dns=False):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
            raise ValueError('Only public HTTP(S) links are inspected.')
        if parsed.username or parsed.password or any(c in url for c in '\r\n\x00'):
            raise ValueError('Link with credentials or control characters: refused.')
        host = parsed.hostname.rstrip('.').lower()
        if self.allow_local:
            return
        if host == 'localhost' or host.endswith(('.localhost', '.local')) or '.' not in host and ':' not in host:
            raise ValueError('Local network pages are not inspected.')
        addresses = []
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            if resolve_dns and host not in self.checked:
                try:
                    addresses = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)]
                except OSError as exc:
                    raise ValueError('Cannot resolve this domain.') from exc
        if any(not address.is_global for address in addresses):
            raise ValueError('A local or reserved address was refused.')
        if addresses:
            self.checked.add(host)


class Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 6
    max_repeats = 2

    def __init__(self, policy):
        self.policy = policy

    def redirect_request(self, request, fp, code, message, headers, new_url):
        self.policy.validate(new_url, resolve_dns=True)
        return super().redirect_request(request, fp, code, message, headers, new_url)


def valid_magnet(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != 'magnet' or any(c in url for c in '\r\n\x00'):
        return False
    values = urllib.parse.parse_qs(parsed.query)
    return any(re.fullmatch(r'urn:btih:(?:[0-9a-fA-F]{40}|[A-Z2-7a-z]{32})', x) or
               re.fullmatch(r'urn:btmh:1220[0-9a-fA-F]{64}', x) for x in values.get('xt', []))


def filename_from(headers, url):
    message = Message()
    message['Content-Disposition'] = headers.get('Content-Disposition', '')
    name = message.get_filename() or urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1])
    return name.replace('\\', '/').rsplit('/', 1)[-1][:220]


class DownloadHTML(HTMLParser):
    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.base = page
        self.title = ''
        self.in_title = False
        self.current = None
        self.links = []
        self.json_scripts = []
        self.script_json = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        if tag == 'base' and attrs.get('href'):
            candidate = urllib.parse.urljoin(self.page, attrs['href'])
            if urllib.parse.urlsplit(candidate).scheme in ('http', 'https'):
                self.base = candidate
        if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self.script_json = ''
        if tag in ('a', 'button'):
            if self.current:
                self.links.append(self.current)
            link = attrs.get('href') or attrs.get('data-href') or attrs.get('data-url') or attrs.get('data-download-url')
            if not link:
                # Extract a literal location assignment, never evaluate JavaScript.
                match = re.fullmatch(r"\s*(?:window\.)?location(?:\.href)?\s*=\s*(['\"])([^'\"]+)\1\s*;?\s*", attrs.get('onclick', ''))
                if match:
                    link = match.group(2)
            self.current = {'url': link, 'text': attrs.get('aria-label', '') + ' ' + attrs.get('title', ''),
                            'attributes': ' '.join(str(attrs.get(k, '')) for k in ('id', 'class', 'download')), 'download': 'download' in attrs}
        if tag == 'meta' and attrs.get('http-equiv', '').lower() == 'refresh':
            match = re.search(r'(?i)url\s*=\s*[\'\"]?(.+?)[\'\"]?\s*$', attrs.get('content', ''))
            if match:
                self.links.append({'url': match.group(1), 'text': 'Page redirect', 'attributes': 'download', 'download': False})

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.current:
            self.current['text'] += ' ' + data
        if self.script_json is not None:
            self.script_json += data

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag in ('a', 'button') and self.current:
            self.links.append(self.current)
            self.current = None
        if tag == 'script' and self.script_json is not None:
            try:
                self.json_scripts.append(json.loads(self.script_json))
            except ValueError:
                pass
            self.script_json = None


def json_downloads(data):
    found = []
    def visit(value, depth=0):
        if depth > 12:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in ('downloadurl', 'download_url', 'contenturl', 'content_url') and isinstance(item, str):
                    found.append({'url': item, 'text': 'Download', 'attributes': 'download', 'download': True})
                elif isinstance(item, (dict, list)):
                    visit(item, depth+1)
        elif isinstance(value, list):
            for item in value[:1000]:
                visit(item, depth+1)
    visit(data)
    return found


def candidates_from_page(html, page, policy=None, json_data=False):
    policy = policy or NetworkPolicy()
    if json_data:
        links = json_downloads(json.loads(html))
        title, base = '', page
    else:
        parser = DownloadHTML(page)
        parser.feed(html)
        if parser.current:
            parser.links.append(parser.current)
        links = parser.links
        for script in parser.json_scripts:
            links += json_downloads(script)
        title, base = re.sub(r'\s+', ' ', parser.title).strip(), parser.base
    found = {}
    for link in links[:5000]:
        if not link.get('url'):
            continue
        url = urllib.parse.urljoin(base, link['url'].strip())
        parsed = urllib.parse.urlsplit(url)
        label = re.sub(r'\s+', ' ', link.get('text', '')).strip()[:150]
        signal = (label + ' ' + link.get('attributes', '')).lower()
        if any(word in signal for word in BAD_WORDS):
            continue
        if parsed.scheme == 'magnet':
            if not valid_magnet(url):
                continue
            kind, score = 'magnet', 100
        else:
            try:
                policy.validate(url)
            except ValueError:
                continue
            ext = Path(urllib.parse.unquote(parsed.path)).suffix.lower()
            strong = ext in FILE_EXTENSIONS
            semantic = any(word in signal for word in DOWNLOAD_WORDS)
            host = (parsed.hostname or '').lower()
            host_hint = any(host == hint or host.endswith('.'+hint) for hint in FILE_HOST_HINTS) and bool(parsed.path.strip('/') or parsed.query or parsed.fragment)
            path_hint = bool(re.search(r'/(?:download|dl|getfile)(?:/|$)', parsed.path, re.I))
            if not strong and not semantic and not link.get('download') and not host_hint and not path_hint:
                continue
            kind = 'file' if strong or link.get('download') else 'page'
            score = (90 if strong else 40) + (25 if semantic else 0) + (15 if link.get('download') else 0) + (10 if host_hint else 0)
        if urllib.parse.urldefrag(url)[0] == urllib.parse.urldefrag(page)[0]:
            continue
        candidate = Candidate(url, label or filename_from({}, url) or 'Download link', kind,
                              filename=filename_from({}, url) if kind == 'file' else '', source_page=page, score=score)
        if url not in found or candidate.score > found[url].score:
            found[url] = candidate
    return title, sorted(found.values(), key=lambda c: (-c.score, c.url))[:40]


class LinkResolver:
    def __init__(self, policy=None, opener=None, cancel=lambda: False):
        self.policy = policy or NetworkPolicy()
        self.opener = opener or urllib.request.build_opener(Redirects(self.policy))
        self.cancel = cancel

    def check_cancelled(self):
        if self.cancel():
            raise ResolutionCancelled('Link search cancelled.')

    def request(self, url, method, referrer=''):
        self.check_cancelled()
        self.policy.validate(url, resolve_dns=True)
        headers = {'User-Agent': 'NexusRepacks/1.5 (public download link inspection)', 'Accept': 'text/html,application/xhtml+xml,application/json,*/*;q=0.5', 'Accept-Encoding': 'identity'}
        if referrer:
            self.policy.validate(referrer)
            headers['Referer'] = referrer
        request = urllib.request.Request(url, method=method, headers=headers)
        response = self.opener.open(request, timeout=15)
        try:
            self.policy.validate(response.geturl(), resolve_dns=True)
        except Exception:
            response.close()
            raise
        return response

    def resolve(self, source, referrer=''):
        source = source.strip()
        self.check_cancelled()
        if valid_magnet(source):
            values = urllib.parse.parse_qs(urllib.parse.urlsplit(source).query)
            title = values.get('dn', ['Magnet torrent'])[0]
            return Resolution(source, source, title, [Candidate(source, title, 'magnet')], direct=True)
        if urllib.parse.urlsplit(source).scheme == 'magnet':
            raise ValueError('Invalid magnet link: missing or incorrect BitTorrent identifier.')
        if urllib.parse.urlsplit(source).scheme not in ('http', 'https', 'magnet') and Path(source).suffix.lower() == '.torrent' and Path(source).is_file():
            return Resolution(source, source, Path(source).stem, [Candidate(source, Path(source).name, 'torrent', filename=Path(source).name)], direct=True)
        try:
            response = self.request(source, 'HEAD', referrer)
        except urllib.error.HTTPError as exc:
            if exc.code not in (405, 501):
                raise ValueError(f'The server refused inspection (HTTP {exc.code}). Open the page in your browser if login or a CAPTCHA is required.') from exc
            response = self.request(source, 'GET', referrer)
        with response:
            final = response.geturl()
            content_type = response.headers.get_content_type()
            filename = filename_from(response.headers, final)
            disposition = response.headers.get('Content-Disposition', '').lower()
            is_html = content_type in ('text/html', 'application/xhtml+xml')
            is_json = content_type in ('application/json', 'application/ld+json')
            is_file = not is_html and not is_json and ('attachment' in disposition or content_type.startswith(('application/', 'video/', 'audio/')) or Path(filename).suffix.lower() in FILE_EXTENSIONS)
            if is_file:
                try:
                    size = int(response.headers.get('Content-Length', ''))
                    if size < 0:
                        size = None
                except ValueError:
                    size = None
                item = Candidate(final, filename or 'Suggested file', 'file', filename, size, content_type, referrer, 100)
                return Resolution(source, final, filename, [item], direct=True)
        # Only read a bounded textual page. Never read a file's body to discover links.
        if getattr(response, 'getcode', lambda: 200)() == 204:
            raise ValueError('The server returned no content.')
        with self.request(final, 'GET', referrer) as page:
            final = page.geturl()
            kind = page.headers.get_content_type()
            if kind not in ('text/html', 'application/xhtml+xml', 'application/json', 'application/ld+json', 'text/plain'):
                raise ValueError('The server response changed between inspection and reading. Retry the direct link.')
            data = page.read(MAX_PAGE + 1)
            if len(data) > MAX_PAGE:
                raise ValueError('Page too large for automatic inspection (2 MiB limit).')
            charset = page.headers.get_content_charset() or 'utf-8'
            try:
                text = data.decode(charset, errors='replace')
            except LookupError:
                text = data.decode('utf-8', errors='replace')
        self.check_cancelled()
        title, links = candidates_from_page(text, final, self.policy, json_data=kind in ('application/json', 'application/ld+json'))
        note = '' if links else 'No usable public link found. The button may require JavaScript, login, a CAPTCHA or an unsupported host.'
        return Resolution(source, final, title, links, note=note)
