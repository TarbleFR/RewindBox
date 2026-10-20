#!/usr/bin/env python3
"""Build the same private RAR4/RAR5 reader sources that the iOS pod compiles.

No host libarchive, unrar executable, network dependency or format converter is
used. The returned static library links with zlib (and iconv on Apple platforms).
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
POD = ROOT / 'packages/neo_texture_catalog/ios'
VENDOR = POD / 'ThirdParty/libarchive'


def build(output: Path | str, cc: str = 'cc', flags: tuple | list = ()) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sources = sorted(VENDOR.glob('*.c')) + [POD / 'Classes/NeoTextureRARMemory.c']
    compiler = shlex.split(cc)
    common = [*compiler, '-x', 'c', '-std=c11', '-O1', '-fvisibility=hidden', '-D_DEFAULT_SOURCE=1',
              '-DHAVE_CONFIG_H=1', f'-I{VENDOR}', *map(str, flags)]

    def compile_source(source):
        obj = output / (source.stem + '.o')
        subprocess.run([*common, '-c', str(source), '-o', str(obj)], check=True)
        return obj

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        objects = list(pool.map(compile_source, sources))
    library = output / 'libNeoTextureRAR.a'
    if library.exists():
        library.unlink()
    subprocess.run(['ar', 'rcs', str(library), *map(str, objects)], check=True)
    (output / 'build.json').write_text(json.dumps({
        'upstream': 'libarchive/libarchive v3.8.10', 'compiler': compiler, 'flags': list(map(str, flags)),
        'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'configuration': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                          [VENDOR / 'config.h', VENDOR / 'NeoTextureLibarchivePrefix.h', POD / 'Classes/NeoTextureRARMemory.h']},
        'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
    }, indent=2) + '\n')
    return library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--cflag', action='append', default=[])
    args = parser.parse_args()
    print(build(args.out, args.cc, args.cflag))


if __name__ == '__main__':
    main()
