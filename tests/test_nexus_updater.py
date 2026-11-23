import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from nexus_repacks import updater


class SignedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        self.binary = b'MZ' + b'harmless fixture' * 100
        self.manifest = {'version': '2.3.0', 'url': 'https://example.org/app.exe',
                         'size': len(self.binary), 'sha256': hashlib.sha256(self.binary).hexdigest()}
        self.sign()

    def sign(self):
        self.manifest['signature'] = base64.b64encode(self.key.sign(updater.payload(self.manifest))).decode()

    def test_signed_new_version_and_no_downgrades(self):
        self.assertTrue(updater.validate(self.manifest, self.public, '2.2.0'))
        self.assertFalse(updater.validate(self.manifest, self.public, '2.3.0'))
        self.assertFalse(updater.validate(self.manifest, self.public, '3.0.0'))
        self.assertGreater(updater.version('2.10.0'), updater.version('2.9.0'))

    def test_tampering_is_rejected_for_every_signed_field(self):
        for field, value in [('version', '9.0.0'), ('url', 'https://evil.example/file.exe'),
                             ('size', 2048), ('sha256', '0' * 64)]:
            with self.subTest(field=field):
                manifest = dict(self.manifest, **{field: value})
                with self.assertRaises(InvalidSignature):
                    updater.validate(manifest, self.public, '2.2.0')

    def test_invalid_metadata_even_with_valid_signature(self):
        for field, value in [('url', 'http://example.org/file.exe'), ('size', updater.MAX_UPDATE + 1),
                             ('size', -1), ('sha256', 'abc'), ('version', 'latest')]:
            with self.subTest(field=field):
                original = self.manifest.copy()
                self.manifest[field] = value
                self.sign()
                with self.assertRaises(ValueError):
                    updater.validate(self.manifest, self.public, '2.2.0')
                self.manifest = original

    def test_download_exact_size_digest_and_partial_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(updater, 'open_https', return_value=io.BytesIO(self.binary)):
                path = updater.download(self.manifest, directory)
            self.assertEqual(path.read_bytes(), self.binary)
            path.unlink()
            for content in (self.binary[:-1], self.binary + b'overflow', b'MZ' + b'x' * (len(self.binary)-2)):
                with patch.object(updater, 'open_https', return_value=io.BytesIO(content)):
                    with self.assertRaises(ValueError):
                        updater.download(self.manifest, directory)
                self.assertEqual(list(Path(directory).iterdir()), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows replacement')
    def test_atomic_replace_backup_and_digest_failure_preserves_original(self):
        with tempfile.TemporaryDirectory(prefix="nexus test ' ") as directory:
            folder = Path(directory)
            target, staged, log = folder/'Nexus Repacks.exe', folder/'new.exe', folder/'install.log'
            target.write_bytes(b'original fixture')
            staged.write_bytes(self.binary)
            script = folder/'apply.ps1'
            def execute(digest):
                script.write_text(updater.replacement_script(staged, target, digest, 2147483646, log), encoding='utf-8-sig')
                result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
                                         'Bypass', '-File', str(script)], capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
            execute('0' * 64)
            self.assertEqual(target.read_bytes(), b'original fixture')
            execute(self.manifest['sha256'])
            self.assertEqual(target.read_bytes(), self.binary)
            self.assertEqual(Path(str(target)+'.update-backup').read_bytes(), b'original fixture')
            self.assertFalse(staged.exists())


if __name__ == '__main__':
    unittest.main()
