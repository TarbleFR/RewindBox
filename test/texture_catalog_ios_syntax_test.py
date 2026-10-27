#!/usr/bin/env python3
"""Compile and link every source of packages/neo_texture_catalog for iPhone (macOS).

iPhoneOS SDK, arm64, the podspec's settings (ARC, C++20, the LZMA SDK
search path, hidden LZMA symbols through Classes/NeoTextureLZMA.c). The
Flutter plugin header is the repository's declaration stub
(test/libretro_host/stubs); everything else is the real SDK. The objects are
linked into one dynamic library and `nm -u` must list no symbol of the pod
itself (NeoTexture*, NeoTex*), and no LZMA SDK symbol may be exported.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from libretro_ios_syntax_test import public_headers

ROOT = Path(__file__).resolve().parents[1]
POD = ROOT / 'packages/neo_texture_catalog/ios'
TARGET = 'arm64-apple-ios17.4'
FRAMEWORKS = ('Foundation', 'UIKit', 'UniformTypeIdentifiers', 'Metal')
# The HD page imports <neo_cheat_catalog/RBLiquidProgressView.h> (Liquid Glass,
# 598d35d5); the podspec depends on neo_cheat_catalog. Only the headers that
# pod publishes resolve that way in the app build, so only those are staged.
CHEAT_CATALOG = ROOT / 'packages/neo_cheat_catalog/ios'


def stage_cheat_catalog_headers(directory):
    staged = directory / 'include' / 'neo_cheat_catalog'
    staged.mkdir(parents=True)
    headers = public_headers('neo_cheat_catalog', CHEAT_CATALOG)
    for header in headers:
        shutil.copyfile(header, staged / header.name)
    print(f'Staged {len(headers)} public neo_cheat_catalog header(s) as <neo_cheat_catalog/...>', flush=True)
    return directory / 'include'


def main():
    if sys.platform != 'darwin':
        raise SystemExit('The iPhone syntax check runs on macOS.')
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    sources = sorted((POD / 'Classes').glob('*.m')) + sorted((POD / 'Classes').glob('*.mm')) + [POD / 'Classes/NeoTextureLZMA.c', POD / 'Classes/NeoTextureRARMemory.c'] + sorted((POD / 'ThirdParty/libarchive').glob('*.c'))
    base = ['-target', TARGET, '-isysroot', sdk, '-Wall', '-Wno-unused-parameter', '-I', str(POD / 'Classes'),
            '-I', str(POD / 'Classes/Public'), '-DHAVE_CONFIG_H=1', '-I', str(POD / 'ThirdParty/libarchive'), '-I', str(POD / 'ThirdParty/lzma'), '-I', str(ROOT / 'test/libretro_host/stubs')]
    failed, objects = [], []
    with tempfile.TemporaryDirectory(prefix='texture-catalog-ios-') as temporary:
        directory = Path(temporary)
        base += ['-I', str(stage_cheat_catalog_headers(directory))]
        for source in sources:
            output = directory / (source.name + '.o')
            if source.suffix == '.c':
                command = ['xcrun', '--sdk', 'iphoneos', 'clang', '-x', 'c', *base, '-c', str(source), '-o', str(output)]
            elif source.suffix == '.mm':
                command = ['xcrun', '--sdk', 'iphoneos', 'clang++', '-x', 'objective-c++', '-std=c++20', '-fobjc-arc', *base,
                           '-c', str(source), '-o', str(output)]
            else:
                command = ['xcrun', '--sdk', 'iphoneos', 'clang', '-x', 'objective-c', '-fobjc-arc', '-fmodules', *base,
                           '-c', str(source), '-o', str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            print(f"{'ok' if result.returncode == 0 else 'FAILED':6} {source.relative_to(ROOT)}", flush=True)
            if result.stderr.strip():
                print(result.stderr, flush=True)
            if result.returncode:
                failed.append(source.name)
            objects.append(output)
        if failed:
            raise SystemExit('iPhone compilation failed: ' + ', '.join(failed))
        library = directory / 'libneo_texture_catalog.dylib'
        command = ['xcrun', '--sdk', 'iphoneos', 'clang++', '-dynamiclib', '-target', TARGET, '-isysroot', sdk, '-fobjc-arc',
                   *map(str, objects), '-lz', '-liconv', '-lc++', '-Wl,-undefined,dynamic_lookup', '-o', str(library)]
        for framework in FRAMEWORKS:
            command += ['-framework', framework]
        subprocess.run(command, check=True)
        undefined = subprocess.check_output(['xcrun', 'nm', '-u', str(library)], text=True).split()
        own = sorted(name for name in undefined if 'NeoTex' in name)
        if own:
            raise SystemExit('Pod symbols used but defined by no source: ' + ', '.join(own))
        exported = subprocess.check_output(['xcrun', 'nm', '-gU', str(library)], text=True).splitlines()
        lzma = [line for line in exported if any(name in line for name in (' _SzArEx_', ' _LzmaDec_', ' _Lzma2Dec_', ' _CrcCalc'))]
        if lzma:
            raise SystemExit('LZMA SDK symbols are exported (the app links another copy): ' + ', '.join(lzma[:5]))
    print(f'PASS: {len(sources)} neo_texture_catalog sources compile and link for iPhone ({TARGET}); no pod symbol undefined, '
          'no LZMA symbol exported')


if __name__ == '__main__':
    main()
