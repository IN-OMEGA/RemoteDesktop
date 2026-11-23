"""Create signed public release assets. The private key stays outside the repo."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from nexus_repacks.updater import payload, version

ROOT = Path(__file__).resolve().parents[1]
KEY = Path(os.environ['LOCALAPPDATA']) / 'NexusRepacksPublisher' / 'signing-key.pem'
REPO = 'IN-OMEGA/NexusRepacks-Updates'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--init', action='store_true', help='Create key/config before first build')
    parser.add_argument('--exe', type=Path, default=ROOT / 'dist/Nexus Repacks.exe')
    args = parser.parse_args()
    config_path = ROOT / 'nexus_repacks/update_config.json'
    if args.init:
        if not KEY.exists():
            if config_path.exists():
                raise SystemExit('Clé privée manquante : restaure sa sauvegarde, ne remplace pas la clé publique.')
            KEY.parent.mkdir(parents=True, exist_ok=True)
            key = Ed25519PrivateKey.generate()
            with KEY.open('xb') as output:
                output.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
        key = serialization.load_pem_private_key(KEY.read_bytes(), password=None)
        config = {'repository': REPO,
                  'channel_url': f'https://raw.githubusercontent.com/{REPO}/main/nexus-update.json',
                  'manifest_url': f'https://github.com/{REPO}/releases/latest/download/nexus-update.json',
                  'public_key': base64.b64encode(key.public_key().public_bytes(
                      serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode('ascii')}
        config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
        print('Configuration publique prête. Clé privée :', KEY)
        return
    from nexus_repacks.app import APP_VERSION
    version(APP_VERSION)
    config = json.loads(config_path.read_text('utf-8'))
    key = serialization.load_pem_private_key(KEY.read_bytes(), password=None)
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                         serialization.PublicFormat.Raw)).decode('ascii')
    if public != config['public_key']:
        raise SystemExit('La clé privée ne correspond pas à cet EXE.')
    output = ROOT / 'dist' / 'nexus-update-release'
    output.mkdir(parents=True, exist_ok=True)
    exe = output / 'Nexus-Repacks.exe'
    shutil.copy2(args.exe, exe)
    manifest = {'version': APP_VERSION,
                'url': f"https://github.com/{config['repository']}/releases/download/nexus-v{APP_VERSION}/{exe.name}",
                'sha256': hashlib.sha256(exe.read_bytes()).hexdigest(), 'size': exe.stat().st_size}
    manifest['signature'] = base64.b64encode(key.sign(payload(manifest))).decode('ascii')
    (output / 'nexus-update.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Fichiers publics prêts :', output)
    print('Publier les deux fichiers dans la release nexus-v' + APP_VERSION + ' (Latest).')


if __name__ == '__main__':
    main()
