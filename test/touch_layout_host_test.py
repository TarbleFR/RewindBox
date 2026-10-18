#!/usr/bin/env python3
"""Build 484 host checks (any OS with a C/C++ compiler).

Executes the portable geometry of stored touch layouts (normalised safe-area
positions, clamping on screen, scale/opacity ranges, orientation classes,
corner-handle resize) and the PS3 pad merge of touch and controller input.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def compiler(*names):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit('A C/C++ compiler is required: ' + ', '.join(names))


def main():
    with tempfile.TemporaryDirectory(prefix='touch-layout-host-') as temporary:
        work = Path(temporary)
        cc = os.environ.get('CC') or compiler('cc', 'clang', 'gcc')
        cxx = os.environ.get('CXX') or compiler('c++', 'clang++', 'g++')
        geometry = work / 'geometry'
        subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'packages/neo_touch_layout/ios/Classes/Public'),
                        str(ROOT / 'test/native/touch_layout_geometry_test.c'), '-lm', '-o', str(geometry)], check=True)
        subprocess.run([str(geometry)], check=True, timeout=10)
        # The same header compiles as C++ (Objective-C++ sources include it).
        subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', '-x', 'c++',
                        '-I', str(ROOT / 'packages/neo_touch_layout/ios/Classes/Public'),
                        str(ROOT / 'test/native/touch_layout_geometry_test.c'), '-o', str(work / 'geometry_cpp')],
                       check=True)
        subprocess.run([str(work / 'geometry_cpp')], check=True, timeout=10)
        merge = work / 'merge'
        subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'),
                        str(ROOT / 'test/native/rpcs3_pad_merge_test.cpp'), '-o', str(merge)], check=True)
        subprocess.run([str(merge)], check=True, timeout=10)
    subprocess.run([sys.executable, str(ROOT / 'tools/touch_layout/generate_strings.py'), '--check'], check=True)
    print('PASS touch layout host checks: geometry (C and C++), PS3 pad merge, generated catalogues')


if __name__ == '__main__':
    main()
