import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from nexus_repacks import catalog
from nexus_repacks.app import Nexus
from scripts.sync_nexus_catalog import sync


class CatalogTests(unittest.TestCase):
    def row(self, **changes):
        return dict(id='fixture', title='Test Game', description='Game details.',
                    download_url='https://downloads.example.org/game.zip', **changes)

    def parse(self, row):
        return catalog.parse_catalog({'version': 1, 'games': [row]})[0]

    def test_optional_fields_and_magnet(self):
        game = self.parse(self.row())
        self.assertEqual(game.folder, 'fixture')
        self.assertTrue(game.enabled)
        row = self.row()
        row['download_url'] = 'magnet:?xt=urn:btih:'+'a'*40+'&dn=Test'
        self.assertTrue(self.parse(row).download_url.startswith('magnet:'))
        row.pop('download_url')
        row['enabled'] = False
        self.assertEqual(self.parse(row).download_url, '')

    def test_invalid_metadata_and_duplicate_ids(self):
        for field, value in [('id', '../escape'), ('title', ''), ('enabled', 'true'),
                             ('description', 12), ('folder', '../escape'), ('folder', 'CON.txt'),
                             ('filename', 'bad.exe\n--on-download-complete=cmd'),
                             ('download_url', 'javascript:alert(1)'), ('download_url', 'file:///C:/Windows/x'),
                             ('download_url', 'https://user:password@example.org/file'),
                             ('download_url', 'magnet:?xt=urn:btih:bad'), ('download_url', '--dir=C:/'),
                             ('referrer', 'https://example.org/\r\nx'), ('image', '../escape.png'),
                             ('icon', 'C:\\outside.png'), ('image', 'file:///C:/outside.png')]:
            with self.subTest(field=field, value=value):
                row = self.row()
                row[field] = value
                with self.assertRaises(ValueError):
                    self.parse(row)
        with self.assertRaises(ValueError):
            catalog.parse_catalog({'version': 1, 'games': [self.row(), self.row()]})
        with self.assertRaises(ValueError):
            self.parse(self.row(unrecognized=True))

    def test_invalid_json_size_and_bom(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'catalog.json'
            path.write_text(json.dumps({'version': 1, 'games': [self.row()]}), encoding='utf-8-sig')
            self.assertEqual(len(catalog.load_catalog(path)), 1)
            path.write_text('{missing comma')
            with self.assertRaisesRegex(ValueError, 'Invalid catalog JSON'):
                catalog.load_catalog(path)
            path.write_bytes(b' '*(catalog.MAX_CATALOG+1))
            with self.assertRaisesRegex(ValueError, 'larger than'):
                catalog.load_catalog(path)

    def test_portable_override_and_bundled_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            portable = root/'catalog.json'
            portable.write_text('{"version":1,"games":[]}')
            self.assertEqual(catalog.catalog_path(root), portable)
            with patch.object(catalog.sys, 'frozen', True, create=True), patch.object(catalog.sys, 'executable', str(root/'Nexus.exe')):
                self.assertEqual(catalog.catalog_path(), portable)
                portable.unlink()
                self.assertEqual(catalog.catalog_path(), catalog.asset_path('nexus_repacks/catalog.json'))

    def test_publisher_stages_referenced_art_and_missing_file_leaves_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, destination = root/'source/catalog.json', root/'bundle/catalog.json'
            source.parent.mkdir()
            destination.parent.mkdir()
            (source.parent/'catalog-assets').mkdir()
            (source.parent/'catalog-assets/cover.png').write_bytes(b'harmless asset fixture')
            row=self.row(image='catalog-assets/cover.png')
            source.write_text(json.dumps({'version': 1, 'games': [row]}))
            sync(source, destination)
            self.assertEqual((destination.parent/'catalog-assets/cover.png').read_bytes(), b'harmless asset fixture')
            before=destination.read_bytes()
            row['image']='catalog-assets/missing.png'
            source.write_text(json.dumps({'version': 1, 'games': [row]}))
            with self.assertRaises(ValueError):
                sync(source, destination)
            self.assertEqual(destination.read_bytes(), before)

    def owner(self):
        owner=SimpleNamespace(busy=False, status_text=Mock(), transfer={'phase':'idle'},
                              show_downloads=Mock(), begin_download=Mock())
        def begin(*args):
            owner.busy=True
            owner.transfer={'phase':'preparing','name':args[1]}
        owner.begin_download.side_effect=begin
        return owner

    def test_catalog_click_starts_exact_link_without_confirmation_or_execution(self):
        owner=self.owner()
        game=self.parse(self.row(folder='My Game', filename='file.zip', referrer='https://example.org/page'))
        Nexus.download_catalog_game(owner,game)
        owner.begin_download.assert_called_once_with(game.download_url,'My Game','https://example.org/page','file.zip')
        owner.show_downloads.assert_called_once()
        for _ in range(20):
            Nexus.download_catalog_game(owner,game)
        self.assertEqual(owner.begin_download.call_count,1)

    def test_disabled_entry_and_busy_transfer_never_start(self):
        owner=self.owner()
        Nexus.download_catalog_game(owner,self.parse(self.row(enabled=False)))
        owner.begin_download.assert_not_called()
        owner.busy=True
        original=owner.transfer.copy()
        Nexus.download_catalog_game(owner,self.parse(self.row()))
        owner.begin_download.assert_not_called()
        self.assertEqual(owner.transfer,original)


if __name__ == '__main__':
    unittest.main()
