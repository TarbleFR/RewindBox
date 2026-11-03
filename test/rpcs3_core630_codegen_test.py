#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 630 (unchanged from Core 627).

Core 630 = Core 627 + build-utils/rpcs3/core630-from-627.patch. The patch touches no codegen
input: the RSX, the fault handler (Utilities/Thread.cpp) and the iOS policy are not part of the PPU
or SPU identity, so the identities PPU a987639e9f838d1c / SPU 477a3fa442d27917 and every cached PPU
module and SPU object stay valid.

This audit reads the materialized Core 630 tree (source) and the delivered a4ae86d0 tree
(baseline). It requires that no file of the patch is a codegen input, reverses the patch on a copy
of the tree, requires every codegen input byte-identical, and runs the Core 627 audit on that tree.
No compiler, CMake or LLVM is executed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'build-utils/rpcs3/core630-from-627.patch'


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c627 = module('core627_codegen', ROOT / 'test/rpcs3_core627_codegen_test.py')
c619 = c627.c619


def audit(source: Path, baseline: Path) -> dict:
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', PATCH.read_text('utf-8', 'surrogateescape'), re.M)
    inputs = c619.codegen_inputs(source)
    assert not set(files) & set(inputs), 'a codegen input changed: ' + repr(sorted(set(files) & set(inputs)))
    assert 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake' not in files and 'rpcs3/Emu/CMakeLists.txt' not in files, 'the identity recipe changed'
    with tempfile.TemporaryDirectory(prefix='core630-codegen-') as temporary:
        tree = Path(temporary) / 'core627'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in [*inputs, 'rpcs3/Emu/CMakeLists.txt']:
            if (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 627 bytes'
        report627 = c627.audit(tree, baseline)
    return dict(passed=True, core630_files=sorted(files), codegen_inputs_checked=len(inputs), core627_audit=report627,
                compiler_executed=False, cmake_executed=False,
                scope='Core 630 changes no codegen input; the Core 627 audit holds on the reversed tree; no gameplay claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = audit(args.source.resolve(), args.baseline.resolve())
    text = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
