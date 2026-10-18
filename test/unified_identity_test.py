#!/usr/bin/env python3
"""Execute production Libretro identity/adapters against original synthetic vectors (macOS)."""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT/'packages/neo_cheat_catalog/ios/Classes'
def catalogue_dependency(work):
    include=work/'include/neo_cheat_catalog';include.mkdir(parents=True)
    (include/'NeoUnifiedCheatCatalog.h').write_bytes((CATALOG/'Public/NeoUnifiedCheatCatalog.h').read_bytes())
    return ['-I',str(include.parent),str(CATALOG/'NeoUnifiedCheatCatalog.m')]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--only-fbneo', action='store_true',
                    help='Run only the FBNeo Host/file checks; reuse earlier passing identities/PSP checks.')
args = parser.parse_args()
if sys.platform != 'darwin':
    raise SystemExit('Unified identity native tests require macOS Foundation; not executed here.')
if not args.only_fbneo:
    with tempfile.TemporaryDirectory(prefix='neostation-unified-identity-') as work:
        classes = ROOT / 'packages/libretro_internal_bridge/ios/Classes'
        binary = Path(work) / 'unified-identity'
        subprocess.run(['clang', '-fobjc-arc', '-fblocks', '-O1', '-Wall', '-Wextra',
                        '-Wno-unused-parameter', '-Wno-deprecated-declarations', '-I', str(classes),
                        str(classes / 'LibretroCheats.m'), str(ROOT / 'test/unified_identity_test.m'),
                        '-framework', 'Foundation', '-lz', '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)

    # A separate instrumented core observes the production Host's option lifecycle.
    with tempfile.TemporaryDirectory(prefix='neostation-unified-host-') as work:
        work = Path(work)
        classes = ROOT / 'packages/libretro_internal_bridge/ios/Classes'
        libretro = ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include/libretro'
        core = work / 'ppsspp_libretro.dylib'
        subprocess.run(['clang', '-shared', '-fPIC', '-O1', '-Wall', '-Wextra', '-I', str(libretro),
                        str(ROOT / 'test/unified_identity_host_core.c'), '-o', str(core)], check=True)
        binary = work / 'unified-host'
        units = ['LibretroCoreHost.m', 'LibretroCoreOptions.m', 'LibretroResolution.m',
                 'LibretroStateCodec.m', 'LibretroZipReader.m', 'LibretroCheats.m']
        subprocess.run(['clang', '-fobjc-arc', '-fblocks', '-O1', '-Wall', '-Wno-deprecated-declarations',
                        '-I', str(classes), '-I', str(libretro), *catalogue_dependency(work),
                        *(str(classes / name) for name in units), str(ROOT / 'test/unified_identity_host_test.m'),
                        '-framework', 'Foundation', '-lz', '-o', str(binary)], check=True)
        subprocess.run([str(binary), str(core), str(work / 'data')], check=True)

# Exercise the native FBNeo file/option path through the same production Host.
with tempfile.TemporaryDirectory(prefix='neostation-unified-fbneo-') as work:
    work = Path(work)
    classes = ROOT / 'packages/libretro_internal_bridge/ios/Classes'
    libretro = ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include/libretro'
    core = work / 'fbneo_libretro.dylib'
    subprocess.run(['clang', '-shared', '-fPIC', '-O1', '-Wall', '-Wextra', '-DFBNEO',
                    '-I', str(libretro), str(ROOT / 'test/unified_identity_host_core.c'),
                    '-o', str(core)], check=True)
    binary = work / 'unified-fbneo'
    units = ['LibretroCoreHost.m', 'LibretroCoreOptions.m', 'LibretroResolution.m',
             'LibretroStateCodec.m', 'LibretroZipReader.m', 'LibretroCheats.m']
    subprocess.run(['clang', '-fobjc-arc', '-fblocks', '-O1', '-Wall', '-Wno-deprecated-declarations',
                    '-I', str(classes), '-I', str(libretro), *catalogue_dependency(work),
                    *(str(classes / name) for name in units), str(ROOT / 'test/unified_identity_fbneo_test.m'),
                    '-framework', 'Foundation', '-lz', '-o', str(binary)], check=True)
    subprocess.run([str(binary), str(core), str(work / 'data')], check=True)
