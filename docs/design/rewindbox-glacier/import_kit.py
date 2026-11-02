#!/usr/bin/env python3
"""Imports the RewindBox Glacier kit into the app (reproducible).

Usage: python3 docs/design/rewindbox-glacier/import_kit.py <kit-folder>

<kit-folder> is the unpacked "RewindBox-Glacier-Claude" folder (with
SHA256SUMS.txt). The kit is checked against its own checksums first. Writes:

- assets/images/glacier/background.webp   FOND-SEUL.png, lossless-looking WebP
- assets/images/glacier/emblem.png        white emblem cut from the official
                                          assets/images/rewindbox-logo.png
- assets/images/glacier/nav/<tab>.png     the 8 navigation glyphs (runtime)
- assets/system_art/rewindbox-glacier/    compact System Art pack: the 121
  canonical WebP, aliases.json (resolved by the app, never used as paths),
  theme.json, preview, credits and licences, plus bundle-index.json
- docs/design/rewindbox-glacier/          originals kept in the sources (SVG and
  PNG glyphs, references, composition, registry, verifier)
"""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
DESIGN = ROOT / 'docs/design/rewindbox-glacier'
GLACIER = ROOT / 'assets/images/glacier'
PACK = ROOT / 'assets/system_art/rewindbox-glacier'
TABS = ('systems', 'consoles', 'search', 'airplay', 'achievements', 'scraper', 'settings', 'library')
PACK_METADATA = ('theme.json', 'aliases.json', 'preview.webp', 'CREDITS.md', 'CC-BY-4.0.txt',
                 'BAXY-README.md', 'credits-silhouettes.json')


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_kit(kit: Path) -> None:
    for line in (kit / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split(None, 1)
        if sha256((kit / name.strip()).read_bytes()) != digest:
            raise SystemExit(f'Kit file altered: {name}')


def emblem() -> None:
    source = Image.open(ROOT / 'assets/images/rewindbox-logo.png').convert('L')
    # White mark on a dark gradient: luminance becomes coverage.
    alpha = source.point(lambda v: 0 if v < 70 else 255 if v > 215 else int((v - 70) * 255 / 145))
    box = alpha.getbbox()
    alpha = alpha.crop(box)
    height = 256
    width = round(alpha.width * height / alpha.height)
    alpha = alpha.resize((width, height), Image.LANCZOS)
    white = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    white.putalpha(alpha)
    white.save(GLACIER / 'emblem.png', optimize=True)


def main() -> None:
    kit = Path(sys.argv[1]).resolve()
    check_kit(kit)
    GLACIER.mkdir(parents=True, exist_ok=True)
    (GLACIER / 'nav').mkdir(exist_ok=True)
    background = Image.open(kit / '02-Reference/FOND-SEUL.png').convert('RGB')
    background.save(GLACIER / 'background.webp', quality=90, method=6)
    emblem()
    for tab in TABS:
        shutil.copyfile(kit / f'03-Navigation/png/{tab}.png', GLACIER / f'nav/{tab}.png')

    # Originals kept in the sources (not bundled).
    for sub in ('navigation/svg', 'navigation/png', 'reference', 'verification'):
        (DESIGN / sub).mkdir(parents=True, exist_ok=True)
    for tab in TABS:
        shutil.copyfile(kit / f'03-Navigation/svg/{tab}.svg', DESIGN / f'navigation/svg/{tab}.svg')
        shutil.copyfile(kit / f'03-Navigation/png/{tab}.png', DESIGN / f'navigation/png/{tab}.png')
    for name in ('MENU-CIBLE.png', 'FOND-SEUL.png', 'BANNIERE-IDENTITE.png', 'composition.json'):
        shutil.copyfile(kit / f'02-Reference/{name}', DESIGN / f'reference/{name}')
    for name in ('registre-art.json', 'verification.json', 'verify_distribution.py', 'lire-le-registre.md'):
        shutil.copyfile(kit / f'04-Verifications/{name}', DESIGN / f'verification/{name}')
    shutil.copyfile(kit / 'SHA256SUMS.txt', DESIGN / 'KIT-SHA256SUMS.txt')
    shutil.copyfile(kit / '00-LIRE-AVANT.md', DESIGN / 'KIT-LIRE-AVANT.md')

    # Compact pack: the canonical image of every identifier, aliases resolved
    # by the app from aliases.json.
    with zipfile.ZipFile(kit / '01-System-Art/RewindBox-Glacier-System-Art.zip') as archive:
        aliases = json.loads(archive.read('rewindbox-glacier/aliases.json'))
        if shutil.os.path.exists(PACK):
            shutil.rmtree(PACK)
        (PACK / 'backgrounds').mkdir(parents=True)
        files = []
        for name in PACK_METADATA:
            data = archive.read(f'rewindbox-glacier/{name}')
            (PACK / name).write_bytes(data)
            files.append({'path': name, 'size': len(data), 'sha256': sha256(data)})
        for canonical in sorted(aliases['canonicalIds']):
            data = archive.read(f'rewindbox-glacier/backgrounds/{canonical}.webp')
            Image.open(__import__('io').BytesIO(data)).verify()
            relative = f'backgrounds/{canonical}.webp'
            (PACK / relative).write_bytes(data)
            files.append({'path': relative, 'size': len(data), 'sha256': sha256(data)})
    theme = json.loads((PACK / 'theme.json').read_text())
    digest = sha256(json.dumps(files, sort_keys=True).encode())
    index = {
        'schema': 1,
        'id': theme['id'],
        'name': theme['name'],
        'version': theme['version'],
        'catalogueCommit': aliases['catalogueCommit'],
        'contentDigest': digest,
        'files': files,
    }
    (PACK / 'bundle-index.json').write_text(json.dumps(index, indent=1, ensure_ascii=False) + '\n')
    print(f'{len(files)} pack files, digest {digest}')


if __name__ == '__main__':
    main()
