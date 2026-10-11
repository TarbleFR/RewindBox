#!/usr/bin/env python3
"""Build assets/data/libretro_skin_overlays.json from RetroArch overlay repositories.

The index lists the touch overlays of libretro/common-overlays (CC BY 4.0) and
stunrelay/PocketArch (MIT) at pinned commits, for NeoStation's unified skin
catalogs. Nothing is bundled but this index: on the iPhone NeoStation reads an
overlay's .cfg, converts it (lib/services/libretro_overlay_converter.dart),
lets the native compatibility filter judge it, and downloads the listed images
only when the user installs it.

Every .cfg is classified by its path, before any conversion:
- keyboards/ -> excluded: keyboard and mouse (SKIN_COMPAT_DESKTOP);
- borders/, effects/, wii/, ctr/ -> excluded: decoration without controls
  (SKIN_COMPAT_DECORATIVE);
- misc/xperia_play* -> excluded: made for one Android device
  (SKIN_COMPAT_DEVICE_SPECIFIC);
- gamepads/, ipad/, misc/ and PocketArch's touch overlays -> candidates for
  the consoles named by their folder or file (generic RetroPad overlays for
  every RetroPad console); systems NeoStation does not emulate are left out.
PocketArch ships each overlay twice (Phone 18x37 and Phone Taller 9x20); only
the 9x20 version, closest to edge-to-edge iPhones, is listed.

Usage: build_skin_overlay_catalog.py COMMON_OVERLAYS_CLONE POCKETARCH_CLONE OUTPUT
Both clones must be at the pinned commits below (a blob-less clone is enough
for the tree; the .cfg files must be checked out).
"""
import hashlib
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

SOURCES = {
    'libretro-overlays': {
        'name': 'Libretro common-overlays',
        'repository': 'libretro/common-overlays',
        'commit': '42c21b99889468a8e77fd7f002229ec16e2f9fa2',
        'license': 'CC BY 4.0',
        'author': 'libretro contributors',
        'url': 'https://github.com/libretro/common-overlays',
    },
    'pocketarch': {
        'name': 'PocketArch',
        'repository': 'stunrelay/PocketArch',
        'commit': '33dc23be7ea5938956bbe686c1c9494ef5628e30',
        'license': 'MIT',
        'author': 'stunrelay',
        'url': 'https://github.com/stunrelay/PocketArch',
    },
}

RETROPAD_CONSOLES = ['nes', 'snes', 'gb', 'gbc', 'gba', 'md', 'sms', 'gg', 'psx', 'arcade']
GENESIS = ['md', 'mcd', '32x']

# common-overlays gamepad folders (and file names in flat/, lite/).
FOLDER_CONSOLES = {
    'gba': ['gba'], 'gba-grey': ['gba'], 'gba_easy_touch': ['gba'], 'gba_landscape_6x': ['gba'],
    'gba-anim_landscape': ['gba'], 'gameboy': ['gb', 'gbc'], 'gb_anim_portrait': ['gb', 'gbc'],
    'gb-portrait': ['gb', 'gbc'], 'nes': ['nes'], 'nes-small': ['nes'], 'snes': ['snes'], 'n64': ['n64'],
    'psx': ['psx'], 'dual-shock': ['psx'], 'box-psx': ['psx'], 'psx-dark': ['psx'], 'n64-dark': ['n64'],
    'genesis': GENESIS, 'arcade': ['arcade'], 'arcade-minimal': ['arcade'], 'arcade-anim': ['arcade'],
    'neo-ds-portrait': ['nds'], 'retropad': RETROPAD_CONSOLES, 'neo-retropad': RETROPAD_CONSOLES,
    'rgpad': RETROPAD_CONSOLES, 'quadpad': RETROPAD_CONSOLES, 'Piixel-Gamepads': RETROPAD_CONSOLES,
    '720-med': RETROPAD_CONSOLES, 'example': RETROPAD_CONSOLES, 'old': RETROPAD_CONSOLES,
}
FILE_CONSOLES = [
    (re.compile(r'gba|game ?boy advance', re.I), ['gba']),
    (re.compile(r'game ?boy color|gbc', re.I), ['gbc']),
    (re.compile(r'game ?boy|gameboy|\bgb\b', re.I), ['gb', 'gbc']),
    (re.compile(r'super nintendo|snes|sfc', re.I), ['snes']),
    (re.compile(r'nintendo entertainment|famicom disk|\bnes\b|\bfds\b', re.I), ['nes']),
    (re.compile(r'nintendo 64(?!dd)|\bn64\b', re.I), ['n64']),
    (re.compile(r'nintendo ds(?!i)|\bnds\b|\bds\b', re.I), ['nds']),
    (re.compile(r'nintendo 3ds|3ds', re.I), ['3ds']),
    (re.compile(r'playstation portable|\bpsp\b', re.I), ['psp']),
    (re.compile(r'sony - playstation\.cfg|\bpsx\b|ps1|playstation(?! [234])(?! portable)', re.I), ['psx']),
    (re.compile(r'mega drive|genesis|mega-cd|sega cd|32x', re.I), GENESIS),
    (re.compile(r'master system|mark iii|\bsms\b', re.I), ['sms']),
    (re.compile(r'game gear', re.I), ['gg']),
    (re.compile(r'sg-1000', re.I), ['sg1000']),
    (re.compile(r'fbneo|mame|arcade|cps|neo ?geo(?! pocket)(?! cd)', re.I), ['arcade']),
    (re.compile(r'retropad', re.I), RETROPAD_CONSOLES),
]
POCKETARCH_SYSTEMS = {
    'GB': ['gb'], 'GBC': ['gbc'], 'GBA': ['gba'], 'NES': ['nes'], 'SNES': ['snes'], 'N64': ['n64'],
    'NDS': ['nds'], 'PSX': ['psx'], 'PSP': ['psp'], 'GENESIS': GENESIS, 'Universal': RETROPAD_CONSOLES,
}
IMAGE = re.compile(r'^\s*(overlay\d+(?:_desc\d+)?_overlay)\s*=\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', re.M)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), '-c', 'gc.auto=0', *args], check=True, capture_output=True,
                          text=True).stdout


def entry_id(source, cfg_path):
    return source[:2] + '-' + hashlib.sha256(f'{source}:{cfg_path}'.encode()).hexdigest()[:12]


def images(repo, cfg_path, tree):
    text = (repo / cfg_path).read_text(encoding='utf-8', errors='replace')
    base = posixpath.dirname(cfg_path)
    found = []
    for _, value in IMAGE.findall(text):
        resolved = posixpath.normpath(posixpath.join(base, value.strip()))
        if resolved in tree and resolved not in found and resolved.lower().endswith(('.png', '.jpg', '.jpeg')):
            found.append(resolved)
    return found


def console_names(name):
    for pattern, consoles in FILE_CONSOLES:
        if pattern.search(name):
            return consoles
    return []


def classify_common(cfg_path):
    parts = cfg_path.split('/')
    top = parts[0]
    if top == 'keyboards':
        return [], 'SKIN_COMPAT_DESKTOP', None
    if top in ('borders', 'effects', 'wii', 'ctr'):
        return console_names(posixpath.basename(cfg_path)), 'SKIN_COMPAT_DECORATIVE', None
    if top == 'misc' and 'xperia' in cfg_path.lower():
        return [], 'SKIN_COMPAT_DEVICE_SPECIFIC', None
    device = 'ipad' if top == 'ipad' else 'iphone'
    folder = parts[1] if len(parts) > 2 else ''
    file_name = posixpath.splitext(parts[-1])[0]
    if folder in ('flat', 'lite', 'Named_Overlays') or not folder:
        consoles = console_names(file_name)
    else:
        consoles = FOLDER_CONSOLES.get(folder) or console_names(file_name)
    return consoles, None, device


def build(common, pocketarch):
    entries = []
    for source, repo in (('libretro-overlays', common), ('pocketarch', pocketarch)):
        head = git(repo, 'rev-parse', 'HEAD').strip()
        if head != SOURCES[source]['commit']:
            raise SystemExit(f'{repo} is at {head}, expected {SOURCES[source]["commit"]}')
        tree = set(git(repo, 'ls-tree', '-r', '--name-only', 'HEAD').splitlines())
        for cfg_path in sorted(path for path in tree if path.endswith('.cfg')):
            if source == 'pocketarch':
                parts = cfg_path.split('/')
                if 'Touch Overlays' not in parts[0] or len(parts) < 4 or parts[1] != 'Phone Taller (9x20)':
                    continue
                consoles = POCKETARCH_SYSTEMS.get(parts[2], [])
                excluded, device = None, 'iphone'
                name = posixpath.splitext(parts[-1])[0].replace('_', ' ')
                if parts[0].startswith('Transparent') and 'transparent' not in name:
                    name += ' transparent'
            else:
                consoles, excluded, device = classify_common(cfg_path)
                name = posixpath.splitext(posixpath.basename(cfg_path))[0].replace('_', ' ')
                folder = cfg_path.split('/')[1] if cfg_path.count('/') >= 2 else ''
                if folder and folder != 'Named_Overlays':
                    name = f'{folder.replace("_", " ")} · {name}'
            if not consoles and excluded is None:
                continue  # A system NeoStation does not emulate.
            entry = {
                'id': entry_id(source, cfg_path),
                'source': source,
                'path': cfg_path,
                'name': name,
                'consoles': consoles,
            }
            if excluded:
                entry['excluded'] = excluded
            else:
                entry['device'] = device
                entry['files'] = images(repo, cfg_path, tree)
            entries.append(entry)
    return {'version': 1, 'sources': SOURCES, 'entries': entries}


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    catalog = build(Path(sys.argv[1]), Path(sys.argv[2]))
    output = Path(sys.argv[3])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n',
                      encoding='utf-8')
    kept = [entry for entry in catalog['entries'] if 'excluded' not in entry]
    print(f'{output}: {len(catalog["entries"])} overlays, {len(kept)} candidates, '
          f'{len(catalog["entries"]) - len(kept)} excluded by path')


if __name__ == '__main__':
    main()
