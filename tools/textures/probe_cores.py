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
  nestopia           HD packs (a Mesen feature: none expected);
  mesen              Mesen's HD packs (mesen_hdpacks, the HdPacks folder,
                     hires.txt and its <supportedRom> check).

  python3 tools/textures/probe_cores.py --cores dist/libretro [--out report.json]
  python3 tools/textures/probe_cores.py --buildbot mesen [--out report.json]

--buildbot reads a core NeoStation does not ship yet from the libretro
buildbot directory of cores.json (the archive add_cores.py would package):
its Mach-O platform, minimum OS, dependencies and libretro exports, as
add_cores.py checks them, and the same strings.

Exit status 0 when every core was found; the verdict per core is in the
report. A string in a binary shows the code is compiled in, not that a game
displays textures on an iPhone.
"""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

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
    'mesen': {
        'options': ['mesen_hdpacks'],
        'markers': ['HdPacks', 'hires.txt', '<supportedrom>', 'disksys.rom'],
    },
}


def strings(path, minimum=6):
    data = Path(path).read_bytes()
    return {match.group().decode('ascii', 'replace') for match in re.finditer(rb'[\x20-\x7e]{%d,}' % minimum, data)}


def exports(binary):
    for tool in ('llvm-nm', 'nm'):
        if shutil.which(tool):
            run = subprocess.run([tool, '-gU', str(binary)], capture_output=True, text=True)
            if run.returncode == 0:
                return {line.split()[-1] for line in run.stdout.splitlines() if line.strip()}
    return None


def from_buildbot(ids, work):
    """Downloads each core from the buildbot into work/<id>_libretro and checks it as add_cores.py does."""
    sys.path.insert(0, str(ROOT / 'build-utils/libretro'))
    import build_cores  # noqa: E402  (its MANIFEST names the buildbot directory)
    available = set(build_cores.buildbot_listing())
    checks = {}
    for core in ids:
        names = [f'{core}_libretro_ios.dylib.zip', f'{core}_libretro.dylib.zip']
        name = next((n for n in names if n in available), None)
        if not name:
            checks[core] = {'published': False}
            print(f'BUILDBOT {core}: not published in {build_cores.MANIFEST["buildbot"]}')
            continue
        data, headers = build_cores.fetch(build_cores.MANIFEST['buildbot'] + name)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            member = next(m for m in archive.namelist() if m.endswith('.dylib'))
            binary = build_cores.thin_arm64(archive.read(member))
        path = Path(work) / f'{core}_libretro'
        path.write_bytes(binary)
        info = build_cores.macho(binary)
        symbols = exports(path)
        record = {'published': True, 'archive': name, 'archiveSha256': build_cores.sha(data), 'sha256': build_cores.sha(binary),
                  'bytes': len(binary), 'lastModified': headers.get('lastModified'), 'platform': info['platform'],
                  'minimumOS': info['minimumOS'], 'dependencies': info['dependencies'],
                  'exports': None if symbols is None else all(e in symbols for e in build_cores.REQUIRED_EXPORTS)}
        try:
            build_cores.check_dependencies(core, info)
            record['dependenciesOK'] = True
        except ValueError as error:
            record['dependenciesOK'] = str(error)
        record['minimumOSOK'] = info['minimumOS'] is not None and \
            build_cores.version_tuple(info['minimumOS']) <= build_cores.version_tuple(build_cores.MANIFEST['maximumCoreMinimumOS'])
        checks[core] = record
        print(f'BUILDBOT {core}: ' + json.dumps(record, sort_keys=True))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cores', default='', help='the LibretroCores artifact folder')
    parser.add_argument('--buildbot', default='', help='core ids read from the buildbot instead, separated by commas')
    parser.add_argument('--out', default='')
    args = parser.parse_args()
    if bool(args.cores) == bool(args.buildbot):
        parser.error('give --cores or --buildbot')
    work = tempfile.mkdtemp(prefix='probe-cores-') if args.buildbot else None
    buildbot = from_buildbot([c for c in args.buildbot.split(',') if c], work) if args.buildbot else {}
    root = Path(args.cores or work)
    probes = {core: PROBES[core] for core in buildbot} if args.buildbot else PROBES
    report, missing = {}, []
    for core, probe in probes.items():
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
        if core in buildbot:
            result['buildbot'] = buildbot[core]
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
