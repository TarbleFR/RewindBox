"""Libretro collections rebuilt from source by RewindBox, reviewed before a delivery retains one.

The source-cores route of .github/workflows/libretro-cores.yml (build-utils/libretro_source_cores.py) authenticates
the retained collection file by file, compiles the pinned, patched sources of a few cores with the RewindBox JIT
interface (packages/libretro_internal_bridge/ios/Classes/RewindBoxLibretroJit.h) and keeps every other file byte for
byte. A delivery may retain such a collection instead of the 609 archive only when it is listed here: the manifest's
origin must equal the entry, and the collection's identity must name exactly these compiled cores, each with its JIT
interface record and its exported install function.

Kept apart from retained_components.py, which is a frozen input of the MeloNX Core producer.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTE = '.github/workflows/libretro-cores.yml'
INSTALL_SYMBOL = '_rewindbox_libretro_jit_install'
COLLECTIONS = {
    14824217397: dict(run=45186888197, source='ee0654160122fb639ea50ce990d866d302d6d6d4',
                      name='LibretroCores-ee0654160122fb639ea50ce990d866d302d6d6d4', bytes=55658336,
                      sha256='c5fc92e5ce1db5f0bf947fd020d8ffe5404a5062fac392ecc7e692426025c1d8',
                      cores=('azahar',)),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def collection(spec):
    """The reviewed collection a libretro component retains, None for one from another route."""
    origin = spec['origin']
    if origin['workflow'] != ROUTE:
        return None
    entry = COLLECTIONS.get(origin['artifact'])
    require(entry is not None and all(origin[key] == entry[key] for key in ('run', 'source', 'name', 'bytes', 'sha256')),
            'Unreviewed libretro source collection: ' + str(origin['artifact']))
    return entry


def verify(spec, macho):
    """After retained_components.verify_libretro: the compiled cores of the unpacked collection are exactly the
    reviewed ones, each with its JIT interface record and install export. `macho` parses a Mach-O image."""
    entry = collection(spec)
    root = ROOT / spec['destination']
    identity = json.loads((root / 'identity.json').read_text())
    compiled = sorted(core['id'] for core in identity['cores'] if core.get('compiled'))
    require(compiled == sorted(entry['cores'] if entry else ()),
            'Libretro cores compiled from source differ from the reviewed collection: ' + repr(compiled))
    for core in identity['cores']:
        if not core.get('compiled'):
            continue
        require(core.get('jitInterface') == 1 and core.get('jitArenaBytes', 0) > 0,
                'A source-built libretro core lacks its JIT interface record: ' + core['id'])
        binary = root / 'Frameworks' / f"{core['id']}_libretro.framework" / f"{core['id']}_libretro"
        require(INSTALL_SYMBOL in macho(binary.read_bytes())['definedSymbols'],
                'Source-built libretro core without its JIT install export: ' + core['id'])
    return dict(sourceCollection=spec['origin']['artifact'] if entry else None, compiledCores=compiled)
