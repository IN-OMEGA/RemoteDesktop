"""Download a harmless local fixture with the verified, bundled aria2 binary."""
import functools
import hashlib
import http.server
import tempfile
import threading
from pathlib import Path

from nexus_repacks.downloads import Download
from nexus_repacks.link_resolver import LinkResolver, NetworkPolicy


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / 'source'
        source.mkdir()
        data = b'Nexus Repacks local integration fixture.\n' * 1024
        (source / 'fixture.zip').write_bytes(data)
        (source / 'index.html').write_text('<title>Fixture</title><a href="fixture.zip" download>Download fixture</a>')
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(source))
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            logs = []
            resolver = LinkResolver(policy=NetworkPolicy(allow_local=True))
            page = resolver.resolve(f'http://127.0.0.1:{server.server_port}/index.html')
            assert not page.direct and len(page.candidates) == 1
            direct = resolver.resolve(page.candidates[0].url, page.final_url)
            assert direct.direct
            candidate = direct.candidates[0]
            job = Download(candidate.url, root / 'download', logs.append,
                           referrer=page.final_url, output_name='fixture.zip')
            code = job.run()
            assert code == 0, '\n'.join(logs)
            actual = (root / 'download' / 'fixture.zip').read_bytes()
            assert hashlib.sha256(actual).digest() == hashlib.sha256(data).digest()
            print('PASS: verified aria2, local HTTP download, exact SHA256 match, no target execution')
        finally:
            server.shutdown()


if __name__ == '__main__':
    main()
