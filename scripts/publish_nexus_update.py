"""Publish only the signed EXE/manifest to the dedicated public update repo."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nexus_repacks.updater import validate


def credentials():
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, timeout=20, env=env)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or not fields.get('password'):
        raise RuntimeError('No GitHub credentials available. Sign in with Git Credential Manager or GitHub CLI first.')
    return fields['password']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true', help='Create repo if absent, upload and publish release')
    args = parser.parse_args()
    config = json.loads((ROOT/'nexus_repacks/update_config.json').read_text('utf-8'))
    repository = config['repository']
    owner, name = repository.split('/')
    token = credentials()

    def api(path, method='GET', body=None, content_type='application/json'):
        url = path if path.startswith('https://uploads.github.com/') else 'https://api.github.com'+path
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer '+token, 'Accept': 'application/vnd.github+json',
            'User-Agent': 'NexusRepacks-Publisher', 'X-GitHub-Api-Version': '2022-11-28',
            'Content-Type': content_type})
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)

    user = api('/user')['login']
    print('GitHub account:', user)
    if user.casefold() != owner.casefold():
        raise RuntimeError('The GitHub account does not match the configured publisher.')
    try:
        repo = api('/repos/'+repository)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        repo = None
    if repo and repo['private']:
        raise RuntimeError('Update repo is private. Public unauthenticated updates require a public repo.')
    print('Update repository:', repository, '(exists)' if repo else '(not yet created)')
    if not args.publish:
        return
    directory = ROOT/'dist/nexus-update-release'
    manifest_path = directory/'nexus-update.json'
    exe = directory/'Nexus-Repacks.exe'
    manifest = json.loads(manifest_path.read_text('utf-8'))
    if not validate(manifest, config['public_key'], '0.0.0'):
        raise RuntimeError('Invalid update version.')
    content = exe.read_bytes()
    if len(content) != manifest['size'] or hashlib.sha256(content).hexdigest() != manifest['sha256']:
        raise RuntimeError('Release EXE differs from the signed manifest.')
    tag = 'nexus-v'+manifest['version']
    expected_url = f'https://github.com/{repository}/releases/download/{tag}/{exe.name}'
    if manifest['url'] != expected_url:
        raise RuntimeError('Release URL differs from signed manifest.')
    if repo is None:
        repo = api('/user/repos', 'POST', {'name': name, 'private': False, 'auto_init': True,
                   'description': 'Official Nexus Repacks portable updates. Signed application releases only.'})
        print('Created:', repo['html_url'])
    releases = api('/repos/'+repository+'/releases')
    existing = next((release for release in releases if release['tag_name'] == tag), None)
    if existing and not existing['draft']:
        for path in (exe, manifest_path):
            expected = 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
            asset = next((item for item in existing['assets'] if item['name'] == path.name), None)
            if not asset or asset.get('digest') != expected:
                raise RuntimeError('This version is already published with different files. Increase APP_VERSION and rebuild.')
    notes_file = ROOT/'docs/nexus-release-notes.md'
    notes = notes_file.read_text('utf-8') if notes_file.is_file() else 'Portable Windows application update.'
    release = existing or api('/repos/'+repository+'/releases', 'POST', {
        'tag_name': tag, 'name': 'Nexus Repacks '+manifest['version'], 'draft': True,
        'body': notes.strip()+'\n\n'
                'Download Nexus-Repacks.exe only. Existing compatible copies check for updates automatically '
                'and apply verified updates after closing. No game files or library data are replaced.'})
    # Work in a draft until both assets have been checked. Never overwrite public assets.
    for path in (exe, manifest_path):
        data = path.read_bytes()
        digest = 'sha256:'+hashlib.sha256(data).hexdigest()
        asset = next((item for item in release['assets'] if item['name'] == path.name), None)
        if asset:
            if asset.get('digest') != digest:
                raise RuntimeError('Draft contains a different asset: '+path.name)
        else:
            url = release['upload_url'].split('{', 1)[0]+'?name='+urllib.parse.quote(path.name)
            asset = api(url, 'POST', data, 'application/octet-stream')
        if asset['size'] != len(data) or (asset.get('digest') and asset['digest'] != digest):
            raise RuntimeError('Uploaded asset verification failed: '+path.name)
        print('Verified upload:', path.name)
    published = (api('/repos/'+repository+'/releases/'+str(release['id']), 'PATCH',
                    {'draft': False, 'prerelease': False, 'make_latest': 'true'}) if release['draft'] else release)
    print('Published:', published['html_url'])
    # A lightweight signed channel avoids API polling limits and stale /latest redirects.
    content_path = '/repos/'+repository+'/contents/nexus-update.json'
    try:
        previous = api(content_path)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        previous = None
    channel = {'message': 'Publish signed Nexus '+manifest['version']+' update channel',
               'content': base64.b64encode(manifest_path.read_bytes()).decode('ascii'),
               'branch': repo['default_branch']}
    if previous:
        channel['sha'] = previous['sha']
    if not previous or base64.b64decode(previous.get('content','')) != manifest_path.read_bytes():
        api(content_path, 'PUT', channel)
    print('Fast signed update channel refreshed.')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as exc:
        raise SystemExit('GitHub API failed (HTTP '+str(exc.code)+'). Check account permissions and rerun to resume publication; published assets are preserved.')
    except (RuntimeError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
