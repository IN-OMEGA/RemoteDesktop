# Build from the repository root with .venv/Scripts/python -m PyInstaller NexusRepacks.spec
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('customtkinter')
datas += [('nexus_repacks/vendor/PROVENANCE.json', 'nexus_repacks/vendor'), ('assets/nexus.ico', 'assets')]
datas += [('nexus_repacks/update_config.json', 'nexus_repacks')]
datas += [('nexus_repacks/catalog.json', 'nexus_repacks')]
import pathlib
from nexus_repacks.catalog import load_catalog, local_art
catalog_file = pathlib.Path('nexus_repacks/catalog.json')
for game in load_catalog(catalog_file):
    for reference in (game.icon, game.image):
        if reference and not reference.startswith(('http://', 'https://')):
            source = local_art(catalog_file.parent, reference)
            if not source.is_file():
                raise ValueError('Missing catalog image: ' + str(source))
            destination = str(pathlib.Path('nexus_repacks') / pathlib.Path(reference).parent)
            if (str(source), destination) not in datas:
                datas.append((str(source), destination))
for license_file in pathlib.Path('nexus_repacks/vendor').glob('*.txt'):
    datas.append((str(license_file), 'licenses/aria2'))
binaries += [('nexus_repacks/vendor/aria2c.exe', 'nexus_repacks/vendor')]
a = Analysis(['nexus_repacks/launch.py'], pathex=['.'], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports + ['pystray._win32', 'PIL.IcoImagePlugin', 'PIL.JpegImagePlugin', 'PIL.PngImagePlugin', 'PIL.WebPImagePlugin'],
             excludes=['numpy', 'aiohttp', 'aiortc', 'av', 'soundcard', 'vgamepad', 'pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Nexus Repacks',
          debug=False, strip=False, upx=False, console=False, icon='assets/nexus.ico', uac_admin=True)
