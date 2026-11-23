"""Benign fixtures only: no game or malware is executed by these tests."""
import hashlib
import io
import json
import pickle
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

from nexus_repacks.downloads import build_command, extract_zip
from nexus_repacks.library import candidates, clean_title, discover
from nexus_repacks.pe_icon import extract_icon
from nexus_repacks.security import Scanner, snapshot_unchanged


def rpc(source):
    payload = zlib.compress(pickle.dumps({'source': source}, protocol=4))
    return b'RENPY RPC2' + struct.pack('<III', 1, 34, len(payload)) + bytes(12) + payload


def rpa(path, source):
    data = rpc(source)
    start = 51
    index_start = start + len(data)
    key = 0x42424242
    index = pickle.dumps({'script.rpyc': [(start ^ key, len(data) ^ key, b'')]}, protocol=4)
    header = f'RPA-3.0 {index_start:016x} {key:08x}\n'.encode()
    path.write_bytes(header + bytes(start - len(header)) + data + zlib.compress(index))


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_benign_setup_is_not_a_malware_verdict(self):
        (self.root / 'setup.py').write_text('print("hello")')
        result = Scanner().scan(self.root)
        self.assertFalse(result.blocked)
        self.assertIn('small-setup', [f.rule for f in result.findings])

    def test_python_runtime_compile_and_exec_in_separate_functions_are_not_a_loader(self):
        (self.root / 'python.py').write_text('import marshal\ndef compile_cache(bytecode):\n    return marshal.loads(bytecode)\ndef run_code(code):\n    exec(code)\n')
        self.assertFalse(Scanner().scan(self.root).blocked)

    def test_native_binary_with_python_symbols_is_not_treated_as_python_source(self):
        (self.root / 'libpython3.12.dll').write_bytes(b'MZ\x00marshal.loads\x00exec(bytecode)\x00b64decode\x00')
        self.assertFalse(Scanner().scan(self.root).blocked)

    def test_decoded_payload_to_exec_still_blocks_even_with_runtime_filename(self):
        (self.root / 'python.py').write_text('import marshal\ndef run(payload):\n    code = marshal.loads(payload)\n    exec(code)\n')
        result = Scanner().scan(self.root)
        self.assertIn('encoded-python', [f.rule for f in result.findings])
        self.assertTrue(result.blocked)

    def test_legacy_compiled_renpy_is_inspected_without_unpickling(self):
        (self.root / 'screen.rpymc').write_bytes(zlib.compress(pickle.dumps({'source': 'screen preferences: pass'}, protocol=2)))
        with patch('pickle.loads', side_effect=AssertionError('must not unpickle')):
            self.assertFalse(Scanner().scan(self.root).blocked)

    def test_legacy_compiled_renpy_with_loader_is_still_blocked(self):
        code = 'def xor_decrypt_to_memory(): pass\ndef extract_and_run(): pass'
        (self.root / 'screen.rpymc').write_bytes(zlib.compress(pickle.dumps({'source': code}, protocol=2)))
        self.assertTrue(Scanner().scan(self.root).blocked)

    def test_pickle_global_execution_is_blocked_without_invoking_it(self):
        (self.root / 'screen.rpymc').write_bytes(zlib.compress(b'cos\nsystem\n.'))
        result = Scanner().scan(self.root)
        self.assertIn('pickle-execution-global', [f.rule for f in result.findings])

    def test_corrupt_legacy_compiled_renpy_is_not_accepted(self):
        (self.root / 'screen.rpymc').write_bytes(b'not-a-supported-format')
        self.assertTrue(Scanner().scan(self.root).blocked)

    def test_renpy_loader_inside_rpa_is_detected_without_execution(self):
        rpa(self.root / 'assets.rpa', 'def xor_decrypt_to_memory(): pass\ndef extract_and_run(): pass')
        with patch('pickle.loads', side_effect=AssertionError('unpickle is forbidden')), patch('subprocess.Popen', side_effect=AssertionError('execution is forbidden')):
            result = Scanner().scan(self.root)
        self.assertTrue(result.blocked)
        self.assertIn('xor-loader', [f.rule for f in result.findings])

    def test_hidden_metadata_variant(self):
        import base64
        raw = json.dumps({'file_nm': 'different.bin', 'pasw': 'newkey', 'exc_fl': 'changed.exe'}).encode()
        key = b'81034149cd6f48c8821340204f92766e'
        (self.root / '.different').write_bytes(base64.b64encode(bytes(v ^ key[i % len(key)] for i, v in enumerate(raw))))
        self.assertIn('renpy-hidden-metadata', [f.rule for f in Scanner().scan(self.root).findings])

    def test_known_hash_detection_survives_rename(self):
        data = b'benign test fixture'
        (self.root / 'new-name.dll').write_bytes(data)
        with patch('nexus_repacks.security.KNOWN', {hashlib.sha256(data).hexdigest(): 'fixture'}):
            result = Scanner().scan(self.root)
        self.assertTrue(result.blocked)

    def test_changed_and_added_dependencies_invalidate_snapshot(self):
        (self.root / 'game.exe').write_bytes(b'benign fixture')
        result = Scanner().scan(self.root)
        self.assertTrue(snapshot_unchanged(result))
        (self.root / 'extra.dll').write_bytes(b'extra')
        self.assertFalse(snapshot_unchanged(result))

    def test_script_and_zip_member_detection(self):
        with zipfile.ZipFile(self.root / 'game.zip', 'w') as z:
            z.writestr('nested/start.cmd', 'powershell -EncodedCommand SGVsbG8=')
        self.assertTrue(Scanner().scan(self.root).blocked)

    def test_zip_traversal_is_detected_and_never_extracted(self):
        source = self.root / 'unsafe.zip'
        with zipfile.ZipFile(source, 'w') as z:
            z.writestr('../escape.txt', 'test')
        self.assertIn('zip-traversal', [f.rule for f in Scanner().scan(self.root).findings])
        with self.assertRaises(ValueError):
            extract_zip(source, self.root / 'output')
        self.assertFalse((self.root / 'escape.txt').exists())

    def test_zip_extraction_rejects_windows_aliases_and_duplicates(self):
        source = self.root / 'unsafe.zip'
        with zipfile.ZipFile(source, 'w') as z:
            z.writestr('A.txt', 'one')
            z.writestr('a.txt', 'two')
        with self.assertRaises(ValueError):
            extract_zip(source, self.root / 'out')

    def test_cancel_is_never_a_pass(self):
        (self.root / 'game.exe').write_bytes(b'fixture')
        self.assertTrue(Scanner(cancel=lambda: True).scan(self.root).blocked)

    def test_unknown_archive_is_explicitly_incomplete(self):
        (self.root / 'game.7z').write_bytes(b'fixture')
        result = Scanner().scan(self.root)
        self.assertTrue(result.blocked)
        self.assertIn('unsupported-archive', [f.rule for f in result.findings])

    def test_neighbor_archive_can_be_excluded_for_extracted_game(self):
        (self.root / 'game.7z').write_bytes(b'fixture')
        result = Scanner(inspect_archives=False).scan(self.root)
        self.assertFalse(result.blocked)
        self.assertIn('unused-archive', [f.rule for f in result.findings])

    def test_corrupt_rpa_does_not_pass(self):
        (self.root / 'assets.rpa').write_bytes(b'RPA-3.0 ffffffffffffffff 42424242\n')
        self.assertTrue(Scanner().scan(self.root).blocked)

    def test_downloader_does_not_use_shell_and_disables_config_hooks(self):
        url = 'https://example.com/file.zip?name=a&x=two'
        command = build_command(url, self.root, aria='trusted-aria.exe')
        self.assertEqual(command[-1], url)
        self.assertEqual(command[-2], '--')
        self.assertIn('--no-conf=true', command)
        self.assertIn('--max-connection-per-server=16', command)
        self.assertIn('--on-download-complete=', command)
        for source in ('--on-download-complete=evil', 'file:///C:/bad', 'https://example.com\n--evil'):
            with self.assertRaises(ValueError):
                build_command(source, self.root, aria='fixture')

    def test_discovery_prefers_game_over_crash_handler_or_installer(self):
        game = self.root / 'ExampleGame'
        game.mkdir()
        for name in ('setup.exe', 'UnityCrashHandler64.exe', 'ExampleGame.exe', 'Run Me!.bat'):
            (game / name).write_bytes(b'fixture')
        (game / 'ExampleGame_Data').mkdir()
        self.assertEqual(candidates(game)[0].name, 'ExampleGame.exe')
        self.assertEqual(discover(self.root)[0].launcher, str(game / 'ExampleGame.exe'))

    def test_static_icon_parser_handles_malformed_file(self):
        p = self.root / 'fixture.exe'
        p.write_bytes(b'MZ')
        self.assertIsNone(extract_icon(p))

    def test_launch_gate_rejects_modified_game_without_starting_process(self):
        from nexus_repacks.app import Nexus
        target = self.root / 'game.exe'
        target.write_bytes(b'benign fixture - never executable')
        result = Scanner().scan(self.root)
        digest = result.hashes['game.exe']
        target.write_bytes(b'changed fixture')
        received = []
        done = threading.Event()
        def post(*args):
            received.append(args)
            done.set()
        fake_app = SimpleNamespace(post=post)
        game = SimpleNamespace(launcher=str(target), title='fixture')
        with patch('nexus_repacks.app.launch_executable') as launch:
            Nexus._launch_verified(fake_app, game, result, digest)
            self.assertTrue(done.wait(5))
            launch.assert_not_called()
        self.assertEqual(received[0][0], 'error')

    def test_launch_gate_calls_mock_only_after_unchanged_snapshot(self):
        from nexus_repacks.app import Nexus
        target = self.root / 'game.exe'
        target.write_bytes(b'benign fixture - never executable')
        result = Scanner().scan(self.root)
        done = threading.Event()
        fake_app = SimpleNamespace(post=lambda *args: done.set())
        game = SimpleNamespace(launcher=str(target), title='fixture')
        with patch('nexus_repacks.app.launch_executable') as launch:
            Nexus._launch_verified(fake_app, game, result, result.hashes['game.exe'])
            self.assertTrue(done.wait(5))
            launch.assert_called_once_with(target)

    def test_verified_cache_survives_reload_and_rejects_corruption(self):
        from nexus_repacks.library import Game
        from nexus_repacks.scan_cache import save_verified, load_verified
        target = self.root / 'game.exe'
        target.write_bytes(b'benign cache fixture')
        game = Game.local(self.root, target)
        result = Scanner().scan(self.root)
        cache = self.root.parent / (self.root.name + '.verified')
        try:
            self.assertTrue(save_verified(cache, game, result))
            loaded = load_verified(cache, game)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.hashes, result.hashes)
            data = bytearray(cache.read_bytes())
            data[len(data)//2] ^= 0xff
            cache.write_bytes(data)
            self.assertIsNone(load_verified(cache, game))
        finally:
            cache.unlink(missing_ok=True)

    def test_successful_cached_play_does_not_run_scanner_again(self):
        from nexus_repacks.app import Nexus
        from nexus_repacks.library import Game
        from unittest.mock import Mock
        target = self.root / 'game.exe'
        target.write_bytes(b'benign cached-play fixture')
        game = Game.local(self.root, target)
        result = Scanner().scan(self.root)
        fake = SimpleNamespace(busy=False, external_blocks={}, results={},
            work=lambda fn: fn(), post=lambda kind, fn: fn(), _launch_verified=Mock(), scan_game=Mock())
        with patch('nexus_repacks.app.load_verified', return_value=result):
            Nexus.play(fake, game)
        fake._launch_verified.assert_called_once()
        fake.scan_game.assert_not_called()

    def test_changed_cached_game_requires_manual_check_without_automatic_scan(self):
        from nexus_repacks.app import Nexus
        from nexus_repacks.library import Game
        from unittest.mock import Mock
        target = self.root / 'game.exe'
        target.write_bytes(b'benign cached-play fixture')
        game = Game.local(self.root, target)
        result = Scanner().scan(self.root)
        target.write_bytes(b'changed fixture')
        fake = SimpleNamespace(busy=False, external_blocks={}, results={game.id: result},
            work=lambda fn: fn(), post=lambda kind, fn: fn(), _launch_verified=Mock(), scan_game=Mock(),
            status_text=Mock(), show_protection=Mock())
        Nexus.play(fake, game)
        fake._launch_verified.assert_not_called()
        fake.scan_game.assert_not_called()
        fake.show_protection.assert_called_once_with(game)

    def test_saves_and_logs_do_not_invalidate_first_analysis(self):
        from nexus_repacks.scan_cache import verified_files_unchanged
        (self.root / 'game.exe').write_bytes(b'benign fixture')
        result = Scanner().scan(self.root)
        (self.root / 'saves').mkdir()
        (self.root / 'saves' / 'auto-1.save').write_bytes(b'progress')
        (self.root / 'Player.log').write_text('new session')
        self.assertTrue(verified_files_unchanged(result))
        (self.root / 'added.dll').write_bytes(b'new code')
        self.assertFalse(verified_files_unchanged(result))

    def test_admin_launcher_does_not_spawn_elevated_game(self):
        from nexus_repacks.platform_launch import launch_executable
        target = self.root / 'game.exe'
        with patch('nexus_repacks.platform_launch.is_elevated', return_value=True), \
             patch('nexus_repacks.platform_launch.launch_as_desktop_user', return_value=123) as desktop_launch, \
             patch('nexus_repacks.platform_launch.subprocess.Popen') as elevated_spawn:
            self.assertEqual(launch_executable(target), 123)
            desktop_launch.assert_called_once()
            elevated_spawn.assert_not_called()

    def test_admin_launcher_does_not_fall_back_when_standard_launch_fails(self):
        from nexus_repacks.platform_launch import launch_executable
        with patch('nexus_repacks.platform_launch.is_elevated', return_value=True), \
             patch('nexus_repacks.platform_launch.launch_as_desktop_user', side_effect=OSError('fixture denial')), \
             patch('nexus_repacks.platform_launch.subprocess.Popen') as elevated_spawn:
            with self.assertRaises(OSError):
                launch_executable(self.root / 'game.exe')
            elevated_spawn.assert_not_called()

    def test_batch_command_rejects_environment_expansion(self):
        from nexus_repacks.desktop_user import build_batch_command
        self.assertEqual(build_batch_command('cmd.exe', r'C:\Games\Run Me!.bat'),
                         '"cmd.exe" /d /v:off /s /c ""C:\\Games\\Run Me!.bat""')
        with self.assertRaises(ValueError):
            build_batch_command('cmd.exe', r'C:\Games\%INJECT%\Run Me.bat')


if __name__ == '__main__':
    unittest.main()
