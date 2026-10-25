#!/usr/bin/env python3
"""Small original-file download/install probes through the real native Store.

Uses anonymous production NSURLSession, host resolvers, MEGA crypto and real
engine adapters. An input row is {pack, identity}; raw catalogue capability
metadata is validated by NeoTextureCatalog before the Store sees it. No paid
access, retry, account, mirror, credential or device session is used.
"""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/neo_texture_catalog/ios/Classes'
PUBLIC = CLASSES / 'Public'
LZMA = ROOT / 'packages/neo_texture_catalog/ios/ThirdParty/lzma'


def build_native(folder: Path, source: Path, *, armsx2: bool = False) -> Path:
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    folder.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('neotex_rar_build', ROOT / 'tools/textures/build_rar_library.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rar = module.build(folder / 'rar', cc='xcrun clang', flags=['-isysroot', sdk])
    common = ['-isysroot', sdk, '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
              '-Wno-deprecated-declarations', '-fobjc-arc', '-I', str(CLASSES), '-I', str(PUBLIC), '-I', str(LZMA)]
    units = [('c', CLASSES / 'NeoTextureLZMA.c'),
             ('objective-c', CLASSES / 'NeoTextureCatalog.m'),
             ('objective-c', CLASSES / 'NeoTextureSupport.m'),
             ('objective-c', CLASSES / 'NeoTextureHostResolver.m'),
             ('objective-c++', CLASSES / 'NeoTextureMega.mm'),
             ('objective-c++', CLASSES / 'NeoTextureEngines.mm'),
             ('objective-c++', CLASSES / 'NeoTextureIdentityReader.mm'),
             ('objective-c++', CLASSES / 'NeoTexturePackStore.mm'),
             ('objective-c++', source)]
    if armsx2:
        armsx2_classes = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'
        units.append(('objective-c++', armsx2_classes / 'ARMSX2TexturePackStore.mm'))
        common += ['-I', str(armsx2_classes)]
    objects = []
    for language, unit in units:
        obj = folder / (unit.stem + '.o')
        command = ['xcrun', 'clang++' if language.endswith('++') else 'clang', '-x', language,
                   '-c', str(unit), '-o', str(obj), *common]
        if language == 'c':
            command = ['xcrun', 'clang', '-x', 'c', '-c', str(unit), '-o', str(obj),
                       '-isysroot', sdk, '-O1', '-I', str(LZMA)]
        elif language.endswith('++'):
            command += ['-std=c++20']
        subprocess.run(command, check=True)
        objects.append(obj)
    binary = folder / source.stem
    subprocess.run(['xcrun', 'clang++', '-isysroot', sdk, *map(str, objects), str(rar), '-lz', '-liconv',
                    '-framework', 'Foundation', '-framework', 'Metal', '-o', str(binary)], check=True)
    return binary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        print('NOT RUN: native Store network probe requires macOS Foundation/CommonCrypto', file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='neotex-network-') as temporary:
        folder = Path(temporary)
        binary = build_native(folder / 'build', ROOT / 'test/texture_direct_network_test.mm')
        subprocess.run([str(binary), str(args.input.resolve()), str(args.out.resolve()), str(folder / 'work')],
                       check=True, timeout=2400)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
