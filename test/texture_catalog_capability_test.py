#!/usr/bin/env python3
"""Compile/run the production catalogue capability boundary on Foundation.

This focused check needs macOS; it never reports a pass when Foundation is
unavailable. It does not download textures or rerun unchanged emulator tests.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/neo_texture_catalog/ios/Classes'


def main():
    if sys.platform != 'darwin':
        print('NOT RUN: native catalogue capability check requires macOS Foundation', file=sys.stderr)
        return 1
    sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='texture-capability-') as work:
        directory = Path(work)
        common = ['-isysroot', sdk, '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-fobjc-arc',
                  '-I', str(CLASSES), '-I', str(CLASSES / 'Public')]
        units = [('objective-c', CLASSES / 'NeoTextureCatalog.m'),
                 ('objective-c', CLASSES / 'NeoTextureSupport.m'),
                 ('objective-c', CLASSES / 'NeoTextureHostResolver.m'),
                 ('objective-c++', CLASSES / 'NeoTextureMega.mm'),
                 ('objective-c', ROOT / 'test/texture_catalog_capability_test.m')]
        built = []
        for language, source in units:
            target = directory / (source.stem + '.o')
            command = ['xcrun', 'clang++' if language.endswith('++') else 'clang', '-x', language,
                       '-c', str(source), '-o', str(target), *common]
            if language.endswith('++'):
                command += ['-std=c++20']
            subprocess.run(command, check=True)
            built.append(str(target))
        binary = directory / 'capability-test'
        subprocess.run(['xcrun', 'clang++', '-isysroot', sdk, *built, '-lz', '-framework', 'Foundation', '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=45)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
