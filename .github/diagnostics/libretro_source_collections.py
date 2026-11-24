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
    # Azahar 2127.0-rc5 (build date fixed by sourceDateEpoch), Beetle PSX and Beetle PSX HW with Lightrec, DeSmuME
    # with the AArch64 JIT of TASEmulators/desmume (native/desmume): docs/libretro-jit-collection-handoff.md.
    14839590544: dict(run=45213717171, source='6cd6a89bfdaded3e52400d4640fff4ac17f1c6d9',
                      name='LibretroCores-6cd6a89bfdaded3e52400d4640fff4ac17f1c6d9', bytes=56247458,
                      sha256='0b1d6bb6ce002ca39d15f8c0185cc513fa492bfcdd044e465b165fae7bf21125',
                      cores=('azahar', 'desmume', 'mednafen_psx', 'mednafen_psx_hw')),
    # DeSmuME with steps 1 to 4 of its JIT (native/desmume at 66e232e0): common layer, cached interpreter ("cached",
    # and the fallback without JIT), RewindBox JIT ("jit_exact"); Azahar and both Beetle PSX binaries are identical to
    # those of 14839590544.
    14850324552: dict(run=45237317896, source='66e232e00b980d5495c6d2d30233b13831596858',
                      name='LibretroCores-66e232e00b980d5495c6d2d30233b13831596858', bytes=56286779,
                      sha256='b5816595ae8d02c4c493404e1803b7a73661ce4eedd0f41c9c74d00b7a65af26',
                      cores=('azahar', 'desmume', 'mednafen_psx', 'mednafen_psx_hw')),
    # Beetle PSX and Beetle PSX HW: a cheat that rewrites code Lightrec compiled takes effect (native/beetle-psx at
    # 416333ff); DeSmuME and Azahar are identical to those of 14850324552.
    14870941984: dict(run=45280386958, source='416333ff6b623c789307b6679ca98c90a8c4c373',
                      name='LibretroCores-416333ff6b623c789307b6679ca98c90a8c4c373', bytes=56287018,
                      sha256='8cc3950e6c87523fe865e95ac24380260f8a36fdf25b0b2db06ed21e5bba13c5',
                      cores=('azahar', 'desmume', 'mednafen_psx', 'mednafen_psx_hw')),
    # DeSmuME: the JIT's multi-register stores no longer write outside its block table (the freeze of the IPA 828),
    # faster rendering at high internal resolutions, desmume_num_cores "auto" by default (native/desmume at
    # ccd5f047); Azahar and both Beetle PSX binaries are identical to those of 14870941984.
    14872740403: dict(run=45284351707, source='ccd5f0476caa402823984be589185666d110e7a5',
                      name='LibretroCores-ccd5f0476caa402823984be589185666d110e7a5', bytes=56290109,
                      sha256='2255194bbbfc91c989aa9334bc73fe387dbb693a8d67c052cfa677baa8cee6bb',
                      cores=('azahar', 'desmume', 'mednafen_psx', 'mednafen_psx_hw')),
    # DeSmuME: 3D supersampling (desmume_rb_3d_supersampling), [rb-perf] timings, a 64 MiB JIT arena (native/desmume
    # at 67ce2d3b); Azahar and both Beetle PSX binaries are identical to those of 14872740403.
    14881770592: dict(run=45304481777, source='67ce2d3b2dc6c479dbebf7da73d1f48a64f5f61b',
                      name='LibretroCores-67ce2d3b2dc6c479dbebf7da73d1f48a64f5f61b', bytes=56295241,
                      sha256='9b5a949081f9138fc4d7a49b0b07d056da7f5932e18c2cb758c22c05d2027edc',
                      cores=('azahar', 'desmume', 'mednafen_psx', 'mednafen_psx_hw')),
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
