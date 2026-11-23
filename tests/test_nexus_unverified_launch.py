from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from nexus_repacks.app import Nexus
from nexus_repacks.library import Game
from nexus_repacks.security import sha256, ScanResult


def synchronous_thread(target, **kwargs):
    return SimpleNamespace(start=target)


class UnverifiedLaunchTests(unittest.TestCase):
    def owner(self, game):
        owner = SimpleNamespace(busy=False, _launch_in_progress=False, _unscanned_launches=set(),
                                current_page='library', selected=game, select=Mock(), hide_to_tray=Mock(),
                                status_text=Mock(), results={'previous':'preserved'}, events=[])
        def post(kind, value):
            if kind == 'call':
                value()
            else:
                owner.events.append((kind,value))
        owner.post=post
        return owner

    def test_launch_skips_all_scans_and_verification_and_never_marks_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            target=root/'Fixture.exe'
            target.write_text('Harmless fixture. Never executed.')
            game=Game.local(root,target)
            owner=self.owner(game)
            with patch('nexus_repacks.app.threading.Thread',side_effect=synchronous_thread), \
                 patch('nexus_repacks.app.launch_executable') as launch, \
                 patch('nexus_repacks.app.Scanner') as scanner, \
                 patch('nexus_repacks.app.sha256') as hashing, \
                 patch('nexus_repacks.app.save_verified') as save, \
                 patch('nexus_repacks.app.verified_files_unchanged') as verify:
                Nexus._launch_unscanned(owner,game)
                launch.assert_called_once_with(target)
                for operation in (scanner,hashing,save,verify):
                    operation.assert_not_called()
            self.assertEqual(owner.results,{'previous':'preserved'})
            self.assertEqual(owner._unscanned_launches,{game.id})
            self.assertIn('NOT VERIFIED',owner.status_text.set.call_args.args[0])
            owner.hide_to_tray.assert_called_once()
            self.assertFalse(owner._launch_in_progress)

    def test_batch_uses_existing_standard_user_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for suffix in ('.bat','.cmd'):
                target=root/('fixture'+suffix)
                target.write_text('REM harmless fixture')
                game=Game.local(root,target)
                with patch('nexus_repacks.app.threading.Thread',side_effect=synchronous_thread), \
                     patch('nexus_repacks.app.launch_batch') as launch:
                    Nexus._launch_unscanned(self.owner(game),game)
                    launch.assert_called_once_with(target)

    def test_missing_outside_and_unsupported_targets_never_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            game_root=root/'game'
            game_root.mkdir()
            outside=root/'outside.exe'
            outside.write_text('fixture')
            unsupported=game_root/'script.py'
            unsupported.write_text('fixture')
            for target in (outside,unsupported,game_root/'missing.exe',game_root):
                game=Game.local(game_root,target)
                owner=self.owner(game)
                with patch('nexus_repacks.app.threading.Thread',side_effect=synchronous_thread), \
                     patch('nexus_repacks.app.launch_executable') as launch, \
                     patch('nexus_repacks.app.launch_batch') as batch:
                    Nexus._launch_unscanned(owner,game)
                    launch.assert_not_called()
                    batch.assert_not_called()
                self.assertEqual(owner._unscanned_launches,set())
                self.assertTrue(any(kind=='error' for kind,_ in owner.events))

    def test_busy_or_duplicate_launch_does_nothing(self):
        game=SimpleNamespace(id='fixture')
        owner=self.owner(game)
        with patch('nexus_repacks.app.threading.Thread') as thread:
            owner.busy=True
            Nexus._launch_unscanned(owner,game)
            owner.busy=False
            owner._launch_in_progress=True
            Nexus._launch_unscanned(owner,game)
            thread.assert_not_called()

    def test_hashing_can_be_cancelled_mid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'large.exe'
            path.write_bytes(b'x'*(3*1024*1024))
            cancel=Mock(side_effect=[False,True])
            with self.assertRaises(InterruptedError):
                sha256(path,cancel=cancel)
            self.assertEqual(cancel.call_count,2)

    def test_cancel_before_ui_finish_prevents_automatic_scanned_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            target=root/'fixture.exe'
            target.write_text('harmless fixture')
            game=Game.local(root,target)
            owner=self.owner(game)
            owner.cancel_scan=threading.Event()
            owner._launch_verified=Mock()
            owner._active_scan_game_id=None
            callbacks=[]
            owner.post=lambda kind,value: callbacks.append(value) if kind=='call' else None
            owner.work=lambda job: (job(),True)[1]
            result=ScanResult(str(root),hashes={'fixture.exe':'digest'})
            with patch('nexus_repacks.app.Scanner') as scanner, patch('nexus_repacks.app.STATE',root/'state'), \
                 patch('nexus_repacks.app.save_verified'), patch('nexus_repacks.app.sha256') as hashing:
                scanner.return_value.scan.return_value=result
                Nexus.scan_game(owner,game,launch=True)
                owner.cancel_scan.set()
                for callback in callbacks:
                    callback()
                hashing.assert_not_called()
            owner._launch_verified.assert_not_called()
            self.assertEqual(owner.results,{'previous':'preserved'})


if __name__=='__main__':
    unittest.main()
