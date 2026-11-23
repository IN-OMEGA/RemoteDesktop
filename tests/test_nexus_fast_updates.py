import base64
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from nexus_repacks import updater
from nexus_repacks.app import Nexus


class FastUpdateTests(unittest.TestCase):
    def manifest(self, value='9.0.0', key=None):
        key=key or Ed25519PrivateKey.generate()
        public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
        data={'version':value,'url':'https://example.org/Nexus.exe','size':2048,'sha256':'a'*64}
        data['signature']=base64.b64encode(key.sign(updater.payload(data))).decode()
        return data,public

    def owner(self):
        owner=SimpleNamespace(update_button=Mock(),events=[],on_update_event=Mock())
        def post(kind,callback):
            owner.events.append(callback)
            callback()
        owner.post=post
        return owner

    def test_five_second_interval_and_early_startup(self):
        self.assertEqual(updater.CHECK_INTERVAL_MS,5000)
        self.assertLessEqual(updater.INITIAL_CHECK_MS,1000)

    def test_channel_has_cache_buster_and_network_failure_falls_back(self):
        job=updater.AutoUpdater(self.owner(),'1.0.0')
        config={'channel_url':'https://raw.example.org/channel.json','manifest_url':'https://example.org/latest.json'}
        data={'fixture':'value'}
        with patch.object(updater,'open_https',side_effect=[OSError('offline'),io.BytesIO(json.dumps(data).encode())]) as fetch:
            self.assertEqual(job.fetch_manifest(config),data)
        self.assertTrue(fetch.call_args_list[0].args[0].startswith(config['channel_url']+'?nexus_check='))
        self.assertTrue(fetch.call_args_list[1].args[0].startswith(config['manifest_url']+'?nexus_check='))

    def test_notice_is_dispatched_before_downloading_and_success_is_recorded(self):
        data,public=self.manifest()
        owner=self.owner()
        job=updater.AutoUpdater(owner,'1.0.0')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'config.json'
            config.write_text(json.dumps({'public_key':public,'manifest_url':'https://example.org/latest'}))
            staged=root/'staged.exe'
            staged.write_bytes(b'fixture')
            def download(manifest,folder,progress):
                self.assertEqual(owner.on_update_event.call_args_list[0].args[0],'available')
                progress(.5)
                return staged
            with patch.object(updater.sys,'frozen',True,create=True), \
                 patch.object(updater,'asset_path',return_value=config), patch.object(updater,'STATE',root), \
                 patch.object(job,'fetch_manifest',return_value=data), patch.object(updater,'download',side_effect=download), \
                 patch.object(updater.threading,'Thread',side_effect=lambda target,**kw:SimpleNamespace(start=target)):
                job.check()
            self.assertEqual([call.args[0] for call in owner.on_update_event.call_args_list],['available','downloading','ready'])
            self.assertEqual(job.pending,(staged,data))
            state=json.loads((root/'update-state.json').read_text())
            self.assertEqual((state['running_version'],state['latest_version'],state['phase']),('1.0.0','9.0.0','ready'))

    def test_stale_manifest_cannot_dismiss_a_pending_newer_release(self):
        data,public=self.manifest('2.0.0')
        owner=self.owner()
        job=updater.AutoUpdater(owner,'1.0.0')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'config.json'
            config.write_text(json.dumps({'public_key':public}))
            job.pending=(root/'staged.exe',dict(data,version='3.0.0'))
            with patch.object(updater.sys,'frozen',True,create=True), patch.object(updater,'STATE',root), \
                 patch.object(updater,'asset_path',return_value=config), patch.object(job,'fetch_manifest',return_value=data), \
                 patch.object(updater,'download') as download, \
                 patch.object(updater.threading,'Thread',side_effect=lambda target,**kw:SimpleNamespace(start=target)):
                job.check()
            download.assert_not_called()
            owner.on_update_event.assert_called_once_with('ready',job.pending[1],1.,'')
            owner.update_button.configure.assert_not_called()
            self.assertEqual(job.pending[1]['version'],'3.0.0')

    def test_restart_helper_only_relaunches_after_successful_replacement(self):
        script=updater.replacement_script('new.exe','Nexus.exe','a'*64,12,'install.log',restart=True)
        self.assertGreater(script.index('Start-Process -FilePath $target'),script.index('if (-not $done)'))
        self.assertIn("-ArgumentList '--updated'",script)
        self.assertNotIn('Start-Process',updater.replacement_script('new.exe','Nexus.exe','a'*64,12,'install.log'))

    def test_restart_saves_paused_transfer_and_requests_install_before_destroy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            order=[]
            owner=SimpleNamespace(updater=SimpleNamespace(pending=(root/'staged.exe',{}),on_close=lambda **kw:order.append(('install',kw))),
                _update_restart_requested=False,_skip_pending_launch=True,busy=True,_tray=None,games=[],
                _update_notice=SimpleNamespace(restarting=Mock()),_launch_in_progress=False,root_path=root,
                transfer={'phase':'downloading'},_resume_download=('https://example.org/game.zip','Fixture','','game.zip'),
                destroy=lambda:order.append(('destroy',{})))
            def pause():
                owner.transfer['phase']='paused'
                owner.busy=False
            owner.pause_download=pause
            with patch('nexus_repacks.app.STATE',root),patch('nexus_repacks.app.library.save_library'):
                Nexus.restart_for_update(owner)
            self.assertEqual(order,[('install',{'restart':True}),('destroy',{})])
            self.assertEqual(json.loads((root/'updates/resume.json').read_text())['download'],list(owner._resume_download))

    def test_restore_stages_resume_without_starting_a_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'updates').mkdir()
            path=root/'updates/resume.json'
            owner=SimpleNamespace(root_path=root,valid_download_name=Nexus.valid_download_name,
                                  show_downloads=Mock(),status_text=Mock(),begin_download=Mock())
            job=['https://example.org/game.zip','Fixture','','game.zip']
            path.write_text(json.dumps({'root':str(root.resolve()),'download':job}))
            with patch('nexus_repacks.app.STATE',root):
                self.assertTrue(Nexus.restore_update_session(owner))
            self.assertEqual(owner.transfer['phase'],'paused')
            self.assertEqual(owner._resume_download,tuple(job))
            owner.begin_download.assert_not_called()
            self.assertFalse(path.exists())

    def test_stale_raw_channel_cannot_hide_a_newer_public_release(self):
        key=Ed25519PrivateKey.generate()
        old,public=self.manifest('1.0.0',key)
        new,_=self.manifest('2.0.0',key)
        owner=self.owner()
        job=updater.AutoUpdater(owner,'1.0.0')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'config.json'
            config.write_text(json.dumps({'public_key':public,'channel_url':'https://raw.example.org/channel',
                                          'manifest_url':'https://example.org/latest'}))
            staged=root/'staged.exe'
            staged.write_bytes(b'fixture')
            with patch.object(updater.sys,'frozen',True,create=True),patch.object(updater,'STATE',root), \
                 patch.object(updater,'asset_path',return_value=config),patch.object(job,'fetch_manifest',side_effect=[old,new]), \
                 patch.object(updater,'download',return_value=staged), \
                 patch.object(updater.threading,'Thread',side_effect=lambda target,**kw:SimpleNamespace(start=target)):
                job.check()
            self.assertEqual(job.pending[1]['version'],'2.0.0')
            self.assertEqual(owner.on_update_event.call_args_list[0].args[0],'available')

    def test_network_error_is_not_reported_as_up_to_date(self):
        owner=self.owner()
        job=updater.AutoUpdater(owner,'1.0.0')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'config.json'
            config.write_text('{}')
            with patch.object(updater.sys,'frozen',True,create=True),patch.object(updater,'STATE',root), \
                 patch.object(updater,'asset_path',return_value=config),patch.object(job,'fetch_manifest',side_effect=OSError('offline')), \
                 patch.object(updater.threading,'Thread',side_effect=lambda target,**kw:SimpleNamespace(start=target)):
                job.check()
            self.assertIn('failed',owner.update_button.configure.call_args.kwargs['text'])
            self.assertNotIn('up to date',owner.update_button.configure.call_args.kwargs['text'])
            self.assertEqual(json.loads((root/'update-state.json').read_text())['phase'],'error')
