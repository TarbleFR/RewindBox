#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 624 (unchanged from Core 621).

Core 624 = Core 621 + build-utils/rpcs3/core624-from-621.patch: the reports block
placement of lv2 (Emu/Cell/lv2/sys_rsx.cpp), the conditional render decision
(RSXThread.cpp), the ZCULL fault census (RSXZCULL.cpp), the profiler line and their
header. None of them is a PPU or SPU codegen input, and neither the identity recipe
nor the compatibility table changes, so the delivered identities PPU a987639e9f838d1c /
SPU 477a3fa442d27917 and every cached PPU module and SPU object stay valid.

This audit reads the materialized Core 624 tree (source) and the delivered a4ae86d0
tree (baseline). It requires that no file of the 624 patch is a PPU or SPU codegen
input of rpcs3/Emu/CMakeLists.txt nor JITCacheCompatibility.cmake, reverses the 624
patch on a copy of the tree, requires every codegen input byte-identical, and runs
the Core 621 audit (test/rpcs3_core621_codegen_test.py, itself the Core 619 audit on
its own reversed tree) on that Core 621 tree. No compiler, CMake or LLVM is executed.
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
PATCH = ROOT / 'build-utils/rpcs3/core624-from-621.patch'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c621 = module('core621_codegen', ROOT / 'test/rpcs3_core621_codegen_test.py')
c619 = c621.c619


def audit(source: Path, baseline: Path) -> dict:
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', PATCH.read_text('utf-8', 'surrogateescape'), re.M)
    inputs = c619.codegen_inputs(source)
    assert files and not (set(files) & set(inputs)), 'a Core 624 file is a codegen input'
    assert COMPAT not in files and 'rpcs3/Emu/CMakeLists.txt' not in files, 'the identity recipe or its table changed'
    with tempfile.TemporaryDirectory(prefix='core624-codegen-') as temporary:
        tree = Path(temporary) / 'core621'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git'), symlinks=True)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in inputs + [COMPAT, 'rpcs3/Emu/CMakeLists.txt']:
            if (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 621 bytes'
        report621 = c621.audit(tree, baseline)
    report619 = report621['core619_audit']
    assert report619['core616_audit']['codegen']['PPU']['candidate'] == 'a987639e9f838d1c'
    assert report619['core616_audit']['codegen']['SPU']['candidate'] == '477a3fa442d27917'
    return dict(passed=True, core624_files=sorted(files), codegen_inputs_checked=len(inputs), core621_audit=report621,
                compiler_executed=False, cmake_executed=False,
                scope='Core 624 changes no codegen input; the Core 621 audit holds on the reversed tree; no gameplay claim')


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
