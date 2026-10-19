#!/usr/bin/env python3
"""What the pinned libretro core binaries offer for texture replacement.

Before a console's packs become installable, the core NeoStation ships must
be shown to read them. This reads the printable strings of the pinned iOS
binaries (the LibretroCores artifact the delivery copies into the IPA) and
reports, per core, the option keys and the folder names that its texture
replacement uses:

  mupen64plus_next   GLideN64 high-resolution textures (GLideNHQ):
                     mupen64plus-txHiresEnable and the other hires options,
                     the hires_texture folder, the _HIRESTEXTURES cache names
                     and GLideNHQ's loader messages;
  mednafen_psx_hw    Beetle PSX texture tracking and replacement
                     (beetle_psx_hw_track_textures / replace_textures, the
                     <content>-texture-replacements folder);
  nestopia           HD packs (a Mesen feature: none expected).

  python3 tools/textures/probe_cores.py --cores dist/libretro [--out report.json]

Exit status 0 when every core was found; the verdict per core is in the
report. A string in a binary shows the code is compiled in, not that a game
displays textures on an iPhone.
"""
import argparse
import json
import re
import sys
from pathlib import Path

PROBES = {
    'mupen64plus_next': {
        'options': ['mupen64plus-txHiresEnable', 'mupen64plus-txHiresFullAlphaChannel', 'mupen64plus-txCacheCompression',
                    'mupen64plus-EnableEnhancedHighResStorage', 'mupen64plus-EnableHiResAltCRC', 'mupen64plus-rdp-plugin'],
        'markers': ['hires_texture', 'HIRESTEXTURES', 'ciByRGBA', 'allciByRGBA', 'Mupen64plus'],
    },
    'mednafen_psx_hw': {
        'options': ['beetle_psx_hw_track_textures', 'beetle_psx_hw_replace_textures', 'beetle_psx_hw_dump_textures',
                    'beetle_psx_hw_renderer'],
        'markers': ['texture-replacements', 'texture-dump', 'hdcache'],
    },
    'nestopia': {
        'options': [],
        'markers': ['hdpack', 'HdPacks', 'hires.txt'],
    },
}


def strings(path, minimum=6):
    data = Path(path).read_bytes()
    return {match.group().decode('ascii', 'replace') for match in re.finditer(rb'[\x20-\x7e]{%d,}' % minimum, data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cores', required=True, help='the LibretroCores artifact folder')
    parser.add_argument('--out', default='')
    args = parser.parse_args()
    root = Path(args.cores)
    report, missing = {}, []
    for core, probe in PROBES.items():
        binaries = [p for p in root.rglob(f'{core}_libretro*') if p.is_file() and p.stat().st_size > 4096]
        binaries = [p for p in binaries if not p.name.endswith(('.info', '.json', '.plist'))]
        if not binaries:
            missing.append(core)
            report[core] = {'binary': None}
            continue
        binary = max(binaries, key=lambda p: p.stat().st_size)
        found = strings(binary)
        result = {'binary': str(binary.relative_to(root)), 'bytes': binary.stat().st_size,
                  'options': {key: any(key == s or s.startswith(key) for s in found) for key in probe['options']},
                  'markers': {marker: [s for s in sorted(found) if marker in s][:8] for marker in probe['markers']}}
        result['verdict'] = ('present' if (not probe['options'] or all(result['options'].values()))
                             and any(result['markers'].values()) else 'absent' if not any(result['options'].values())
                             and not any(result['markers'].values()) else 'partial')
        report[core] = result
        print(f'PROBE {core}: {result["verdict"]} ({result["binary"]}, {result["bytes"]} bytes)')
        for key, present in result['options'].items():
            print(f'  option {key}: {"yes" if present else "no"}')
        for marker, lines in result['markers'].items():
            print(f'  marker {marker}: {len(lines)} ' + ' | '.join(line[:100] for line in lines[:4]))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    if missing:
        print('FAIL cores not found: ' + ', '.join(missing))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
