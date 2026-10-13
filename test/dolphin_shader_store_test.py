#!/usr/bin/env python3
"""Dolphin post-processing choice and page (Build 450), on macOS.

1. test/dolphin_shader_store_test.mm runs DOLShaderStore.h on real files:
   names, choices for every game and per game, what reaches GFX.ini and
   Dolphin.ini before the core initializes (explicit empty value, options
   in Dolphin's formats, stale values removed), imports and removal, a
   damaged selection file, and the reversible display trial editing the
   same GFX.ini.
2. The page and the files the change touches compile for iPhone with the
   bridge's dependencies staged as the pod build sees them (<neo_shader_kit/>
   and <external_display/> public headers only): DOLShaderSettings.mm,
   DolphinFramePacing.mm.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
sys.path.insert(0, str(ROOT / 'test'))
from libretro_ios_syntax_test import stage_dependency_headers  # noqa: E402

IPHONE_TARGET = 'arm64-apple-ios17.4'
PAGE_SOURCES = ('DOLShaderSettings.mm', 'DolphinFramePacing.mm')


def run(arguments, **options):
    print('+', ' '.join(str(argument) for argument in arguments), flush=True)
    return subprocess.run([str(argument) for argument in arguments], **options)


def main():
    if sys.platform != 'darwin' or shutil.which('xcrun') is None:
        raise SystemExit('The Dolphin shader store and page checks run on macOS.')
    with tempfile.TemporaryDirectory(prefix='dolphin-shaders-') as temporary:
        temporary = Path(temporary)
        binary = temporary / 'dolphin-shader-store-tests'
        run(['xcrun', 'clang++', '-std=c++20', '-x', 'objective-c++', '-fobjc-arc', '-Wall', '-Wno-unused-function',
             '-I', CLASSES, ROOT / 'test/dolphin_shader_store_test.mm', '-framework', 'Foundation', '-o', binary],
            check=True)
        result = run([binary])
        if result.returncode != 0:
            raise SystemExit('Dolphin shader store behaviour failed')

        sdk = subprocess.run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], check=True, capture_output=True,
                             text=True).stdout.strip()
        include = stage_dependency_headers(temporary)
        failed = []
        for name in PAGE_SOURCES:
            result = run(['xcrun', '--sdk', 'iphoneos', 'clang++', '-target', IPHONE_TARGET, '-isysroot', sdk,
                          '-std=c++20', '-fobjc-arc', '-fmodules', '-fcxx-modules', '-fsyntax-only', '-Wall',
                          '-Wno-unused-function', '-I', CLASSES, '-I', include, CLASSES / name],
                         capture_output=True, text=True)
            print(f'{"ok" if result.returncode == 0 else "FAILED":6} {name}', flush=True)
            if result.stderr.strip():
                print(result.stderr, flush=True)
            if result.returncode != 0:
                failed.append(name)
        if failed:
            raise SystemExit('iPhone compilation failed: ' + ', '.join(failed))
    print('PASS: Dolphin post-processing store behaviour and page iPhone compilation', flush=True)


if __name__ == '__main__':
    main()
