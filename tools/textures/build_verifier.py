#!/usr/bin/env python3
"""Build the production texture installer verification driver, including RAR.

Uses the same pinned private decoder sources as the iOS pod, never a host
unrar executable or a host-provided archive library.
"""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

from build_rar_library import build as build_rar

ROOT = Path(__file__).resolve().parents[2]
POD = ROOT / 'packages/neo_texture_catalog/ios'


def build(output, cc=None, cxx=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cc = cc or os.environ.get('CC', 'cc')
    cxx = cxx or os.environ.get('CXX', 'c++')
    objects = output.parent / (output.name + '-objects')
    objects.mkdir(parents=True, exist_ok=True)
    rar = build_rar(objects / 'rar', cc=cc)
    lzma = objects / 'lzma.o'
    subprocess.run([*shlex.split(cc), '-x', 'c', '-O2', '-c', '-I', str(POD / 'ThirdParty/lzma'),
                    str(POD / 'Classes/NeoTextureLZMA.c'), '-o', str(lzma)], check=True)
    command = [*shlex.split(cxx), '-std=c++20', '-O2', '-Wall', '-Wextra', '-I', str(POD / 'Classes'),
               '-I', str(POD / 'ThirdParty/lzma'), '-I', str(ROOT / 'packages/armsx2_internal_bridge/ios/Classes'),
               str(ROOT / 'tools/textures/native/texture_verify.cpp'), str(lzma), str(rar), '-lz']
    if sys.platform == 'darwin':
        command += ['-liconv']
    subprocess.run([*command, '-o', str(output)], check=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cc')
    parser.add_argument('--cxx')
    args = parser.parse_args()
    print(build(args.out, args.cc, args.cxx))
