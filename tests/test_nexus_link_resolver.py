import io
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch

from nexus_repacks.link_resolver import (
    Candidate, LinkResolver, MAX_PAGE, NetworkPolicy, ResolutionCancelled,
    candidates_from_page, valid_magnet,
)
from nexus_repacks.downloads import build_command


class Response:
    def __init__(self, url, content_type='text/html', body=b'', **headers):
        self.url = url
        self.headers = Message()
        self.headers['Content-Type'] = content_type
        for name, value in headers.items():
            self.headers[name.replace('_', '-')] = str(value)
        self.body = body
        self.read_called = False
        self.closed = False

    def geturl(self): return self.url
    def getcode(self): return 200
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
    def close(self): self.closed = True
    def read(self, size=-1):
        self.read_called = True
        return self.body if size < 0 else self.body[:size]


class LinkResolverTests(unittest.TestCase):
    def test_filehost_page_is_a_candidate_and_never_assumed_to_be_the_file(self):
        _, links = candidates_from_page('<a href="https://gofile.io/d/example">Mirror A</a>', 'https://games.example/page')
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].kind, 'page')

    def test_same_page_download_anchor_is_ignored(self):
        self.assertEqual(candidates_from_page('<a href="#download">Download</a>', 'https://games.example/page')[1], [])

    def test_relative_download_link_is_found_without_following_advertisement(self):
        html = '<title>Example Game</title><a href="/files/game.zip">Download game</a><a href="https://ads.example/offer.exe">Sponsored offer</a><a href="/login">Login</a>'
        title, links = candidates_from_page(html, 'https://games.example/game')
        self.assertEqual(title, 'Example Game')
        self.assertEqual([x.url for x in links], ['https://games.example/files/game.zip'])

    def test_dynamic_button_literal_is_parsed_but_script_is_not_executed(self):
        html = '<button onclick="window.location.href=\'/game.7z\'">Télécharger</button><button onclick="eval(evil())">Download</button>'
        _, links = candidates_from_page(html, 'https://games.example/page')
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, 'https://games.example/game.7z')

    def test_data_attributes_and_jsonld_download_links(self):
        html = '<button data-download-url="/one.zip">Download</button><script type="application/ld+json">{"contentUrl":"https://cdn.example/two.7z"}</script>'
        _, links = candidates_from_page(html, 'https://games.example/page')
        self.assertEqual({x.url for x in links}, {'https://games.example/one.zip', 'https://cdn.example/two.7z'})

    def test_private_addresses_and_unsafe_schemes_are_not_candidates(self):
        html = ''.join(f'<a href="{url}">Download</a>' for url in ('file:///C:/Windows/win.ini', 'javascript:evil()', 'http://127.0.0.1/admin', 'http://localhost/file.zip', 'http://192.168.0.1/file.zip'))
        self.assertEqual(candidates_from_page(html, 'https://games.example/page')[1], [])

    def test_explicit_local_page_is_rejected_by_default(self):
        with self.assertRaises(ValueError):
            LinkResolver().resolve('http://127.0.0.1/test')

    def test_direct_file_only_reads_headers_not_file_body(self):
        response = Response('https://cdn.example/game.zip', 'application/zip', b'not to be read', Content_Length=12345)
        opener = Mock()
        opener.open.return_value = response
        resolver = LinkResolver(NetworkPolicy(allow_local=True), opener=opener)
        result = resolver.resolve('https://cdn.example/game.zip')
        self.assertTrue(result.direct)
        self.assertEqual(result.candidates[0].size, 12345)
        self.assertFalse(response.read_called)
        self.assertEqual(opener.open.call_args.args[0].get_method(), 'HEAD')

    def test_html_page_gets_links_without_reading_any_link_target(self):
        url = 'https://games.example/page'
        head = Response(url)
        page = Response(url, body=b'<a href="https://cdn.example/file.zip">Download</a>')
        opener = Mock()
        opener.open.side_effect = [head, page]
        resolver = LinkResolver(NetworkPolicy(allow_local=True), opener=opener)
        result = resolver.resolve(url)
        self.assertFalse(result.direct)
        self.assertEqual(result.candidates[0].url, 'https://cdn.example/file.zip')
        self.assertEqual([c.args[0].get_full_url() for c in opener.open.call_args_list], [url, url])

    def test_html_named_zip_is_not_mistaken_for_a_file(self):
        url = 'https://games.example/fake.zip'
        opener = Mock()
        opener.open.side_effect = [Response(url), Response(url, body=b'<title>Login required</title>')]
        result = LinkResolver(NetworkPolicy(allow_local=True), opener=opener).resolve(url)
        self.assertFalse(result.direct)
        self.assertEqual(result.candidates, [])
        self.assertTrue(result.note)

    def test_page_size_budget(self):
        url = 'https://games.example/page'
        opener = Mock()
        opener.open.side_effect = [Response(url), Response(url, body=b'a'*(MAX_PAGE+1))]
        with self.assertRaises(ValueError):
            LinkResolver(NetworkPolicy(allow_local=True), opener=opener).resolve(url)

    def test_magnet_and_local_torrent_do_not_trigger_http(self):
        magnet = 'magnet:?xt=urn:btih:' + 'a'*40 + '&dn=Example'
        self.assertTrue(valid_magnet(magnet))
        opener = Mock()
        resolver = LinkResolver(opener=opener)
        self.assertTrue(resolver.resolve(magnet).direct)
        with tempfile.TemporaryDirectory() as tmp:
            torrent = Path(tmp)/'example.torrent'
            torrent.write_bytes(b'fixture')
            self.assertTrue(resolver.resolve(str(torrent)).direct)
        opener.open.assert_not_called()

    def test_invalid_magnet_is_rejected(self):
        with self.assertRaises(ValueError):
            LinkResolver().resolve('magnet:?dn=missing-hash')

    def test_cancelled_inspection_does_not_open_network(self):
        opener = Mock()
        with self.assertRaises(ResolutionCancelled):
            LinkResolver(opener=opener, cancel=lambda: True).resolve('https://games.example/page')
        opener.open.assert_not_called()

    def test_referrer_and_output_name_are_separate_aria_arguments(self):
        command = build_command('https://cdn.example/download?id=123', Path.cwd(), aria='fixture', referrer='https://games.example/page', output_name='Example Game.zip')
        self.assertIn('--referer=https://games.example/page', command)
        self.assertIn('--out=Example Game.zip', command)
        with self.assertRaises(ValueError):
            build_command('https://cdn.example/a', Path.cwd(), aria='fixture', output_name='../escape.exe')
        with self.assertRaises(ValueError):
            build_command('https://cdn.example/a', Path.cwd(), aria='fixture', referrer='https://example.com\r\nInjected: yes')


if __name__ == '__main__':
    unittest.main()
