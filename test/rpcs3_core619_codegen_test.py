#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 619 (unchanged from Core 616).

Core 619 = Core 616 + build-utils/rpcs3/core619-from-616.patch (insertions only,
11 files: RSX ZCULL, the vertex prologue and its shader properties, the iOS policy,
title levers and profiler). None of them is a PPU or SPU codegen input, and the
compatibility table is untouched, so the delivered identities PPU a987639e9f838d1c /
SPU 477a3fa442d27917 and every cached PPU module and SPU object stay valid.

This audit reads the materialized Core 619 tree (source) and the delivered a4ae86d0
tree (baseline). It requires that no file of the 619 patch is listed among the PPU or
SPU codegen inputs of rpcs3/Emu/CMakeLists.txt nor is JITCacheCompatibility.cmake,
reverses the 619 patch on a copy of the tree, requires every codegen input byte-identical
between the two, and runs the Core 616 four-alias audit
(test/rpcs3_core616_codegen_test.py) on that Core 616 tree: the recomputed identities
are the delivered ones. No compiler, CMake or LLVM is executed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'build-utils/rpcs3/core619-from-616.patch'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c616 = module('core616_codegen', ROOT / 'test/rpcs3_core616_codegen_test.py')


def codegen_inputs(source: Path) -> list[str]:
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    names = []
    for kind in ('PPU', 'SPU'):
        block = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1)
        names += [os.path.normpath(os.path.join('rpcs3/Emu', name)) for name in block.split()]
    return sorted(set(names))


def audit(source: Path, baseline: Path) -> dict:
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', PATCH.read_text(), re.M)
    inputs = codegen_inputs(source)
    assert files and not (set(files) & set(inputs)), 'a Core 619 file is a codegen input'
    assert COMPAT not in files and 'rpcs3/Emu/CMakeLists.txt' not in files, 'the identity recipe or its table changed'
    with tempfile.TemporaryDirectory(prefix='core619-codegen-') as temporary:
        tree = Path(temporary) / 'core616'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git'), symlinks=True)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in inputs + [COMPAT, 'rpcs3/Emu/CMakeLists.txt']:
            if (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 616 bytes'
        report616 = c616.audit(tree, baseline)
    assert report616['codegen']['PPU']['candidate'] == 'a987639e9f838d1c' and report616['codegen']['SPU']['candidate'] == '477a3fa442d27917'
    return dict(passed=True, core619_files=sorted(files), codegen_inputs_checked=len(inputs), core616_audit=report616,
                compiler_executed=False, cmake_executed=False,
                scope='Core 619 changes no codegen input; the Core 616 alias audit holds on the reversed tree; no gameplay claim')


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
