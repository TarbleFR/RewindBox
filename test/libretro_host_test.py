#!/usr/bin/env python3
"""Build the portable libretro host with a test core and run it (macOS)."""
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/libretro_internal_bridge/ios/Classes'
LIBRETRO = ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include/libretro'
PORTABLE = ('LibretroCoreHost.m', 'LibretroCheats.m', 'LibretroCoreOptions.m', 'LibretroResolution.m', 'LibretroStateCodec.m',
            'LibretroZipReader.m')
# Value cases and rules shared with Dart's LibretroResolution (Build 455).
RESOLUTION_FIXTURES = ROOT / 'test/fixtures/libretro_resolution'
# Since Build 474 LibretroCoreHost.m imports the unified cheat catalogue pod as
# <neo_cheat_catalog/...> (installed programs of the loaded game). The harness
# searches the pods' public headers, staged as the pods publish them, and
# compiles the catalogue's Flutter-free store (zlib, CommonCrypto).
CATALOGUE = ROOT / 'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m'
sys.path.insert(0, str(ROOT / 'test'))
from libretro_ios_syntax_test import stage_dependency_headers  # noqa: E402


def run(*arguments):
    print('+', ' '.join(str(argument) for argument in arguments), flush=True)
    subprocess.run([str(argument) for argument in arguments], check=True)


def main():
    if sys.platform != 'darwin':
        raise SystemExit('The libretro host test runs on macOS.')
    with tempfile.TemporaryDirectory(prefix='libretro-host-') as temporary:
        temporary = Path(temporary)
        core = temporary / 'neotest_libretro.dylib'
        run('clang', '-shared', '-fPIC', '-O1', '-Wall', '-I', LIBRETRO,
            ROOT / 'test/libretro_host/test_core.c', '-o', core)
        harness = temporary / 'libretro_host_test'
        include = stage_dependency_headers(temporary)
        run('clang', '-fobjc-arc', '-O1', '-Wall', '-I', CLASSES, '-I', LIBRETRO, '-I', include,
            *(CLASSES / name for name in PORTABLE), CATALOGUE, ROOT / 'test/libretro_host/host_test.m',
            '-framework', 'Foundation', '-lz', '-o', harness)
        work = temporary / 'work'
        work.mkdir()
        archive = temporary / 'Test Game.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('readme.txt', 'not the game')
            bundle.writestr('Test Game.ntc', bytes(range(1, 101)))
        run(harness, core, work, archive, RESOLUTION_FIXTURES)


if __name__ == '__main__':
    main()
