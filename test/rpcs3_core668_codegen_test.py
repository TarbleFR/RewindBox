#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 668: no codegen input changes.

Core 668 = Core 665 + build-utils/rpcs3/core668-from-665.patch: the thread orchestrator v1 removed (maintainer decision of
5 November 2026), every file back to Core 664 except ios/IOSThreadOrchestrator.h, now a comment. It touches no codegen input,
so no alias is added and every cached PPU module and SPU object stays valid. This audit reads the materialized Core 668 tree
(source) and the delivered a4ae86d0 tree (baseline); no compiler, CMake or LLVM is executed. It requires:
- no file of the patch is a codegen input, and the compatibility table and identity recipe are untouched;
- with the patch reversed, the Core 665 audit passes (which runs the 664 audit and the earlier ones in turn);
- the identities are the delivered PPU/SPU identities.
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
PATCH = ROOT / 'build-utils/rpcs3/core668-from-665.patch'


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c665 = module('core665_codegen', ROOT / 'test/rpcs3_core665_codegen_test.py')
c619, c616, c610 = c665.c619, c665.c616, c665.c610


def audit(source: Path, baseline: Path) -> dict:
    patch = PATCH.read_text('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', patch, re.M)
    inputs = c619.codegen_inputs(source)
    assert not set(files) & set(inputs), 'codegen inputs changed: ' + repr(sorted(set(files) & set(inputs)))
    assert c610.COMPAT not in files and c610.CMAKE not in files and 'rpcs3/Emu/CMakeLists.txt' not in files, 'identity recipe touched'

    with tempfile.TemporaryDirectory(prefix='core668-codegen-') as temporary:
        tree = Path(temporary) / 'core665'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in inputs:
            if (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 665 bytes'
        report665 = c665.audit(tree, baseline)

    compat = (source / c610.COMPAT).read_text()
    cmake_text = (source / c610.CMAKE).read_text()
    current = c610.aliases(compat)
    result = {}
    for kind in ('PPU', 'SPU'):
        candidate, _ = c616.identity(source, cmake_text, current, kind)
        result[kind] = candidate
        assert candidate == c610.DELIVERED[kind], kind + ' identity changed: ' + candidate
    return dict(passed=True, codegen=result, new_exact_aliases=0, core665_audit=report665, compiler_executed=False,
                cmake_executed=False, emitted_objects_compared=False,
                scope='The ordered CMake identity recipe and exact host-code snapshots; no gameplay claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = audit(args.source.resolve(), args.baseline.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
