"""Validate the publisher's portable catalog and stage its local artwork for the EXE."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nexus_repacks.catalog import load_catalog, local_art


def sync(source, destination=ROOT/'nexus_repacks/catalog.json'):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    games = load_catalog(source)
    # Validate every referenced file before changing the staged catalog.
    assets = set()
    for game in games:
        for reference in (game.image, game.icon):
            if reference and not reference.startswith(('https://', 'http://')):
                asset = local_art(source.parent, reference)
                if not asset.is_file():
                    raise ValueError('Missing catalog image: ' + str(asset))
                if asset.stat().st_size > 8*1024*1024:
                    raise ValueError('Catalog images must be smaller than 8 MiB: ' + str(asset))
                # Keep publisher images away from app/config source files.
                if not reference.replace('\\', '/').startswith('catalog-assets/'):
                    raise ValueError('Local images must be inside catalog-assets/.')
                assets.add(reference)
    for reference in assets:
        asset = local_art(source.parent, reference)
        target = local_art(destination.parent, reference)
        if asset != target:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, target)
    if source != destination:
        shutil.copy2(source, destination)
    print(f'Catalog prepared: {len(games)} game(s), {len(assets)} local image(s).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    try:
        sync(args.source)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
