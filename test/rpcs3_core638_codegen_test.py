#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 638: no codegen input changes.

Core 638 = Core 636 + build-utils/rpcs3/core638-from-636.patch (REWINDBOX_READBACK_PREDICTION_638: texture cache
counters and one log line). It touches no codegen input, so no alias is added and every cached PPU module and SPU
object stays valid. This audit reads the materialized Core 638 tree (source) and the delivered a4ae86d0 tree
(baseline); no compiler, CMake or LLVM is executed. It requires:
- no file of the patch is a codegen input, and the compatibility table and identity recipe are untouched;
- with the patch reversed, the Core 636 audit passes (which runs the 634 audit on its own reversed tree);
- the identities are PPU a987639e9f838d1c / SPU 477a3fa442d27917.
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
PATCH = ROOT / 'build-utils/rpcs3/core638-from-636.patch'


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c636 = module('core636_codegen', ROOT / 'test/rpcs3_core636_codegen_test.py')
c619, c616, c610 = c636.c619, c636.c616, c636.c610


def audit(source: Path, baseline: Path) -> dict:
    patch = PATCH.read_text('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', patch, re.M)
    inputs = c619.codegen_inputs(source)
    assert not set(files) & set(inputs), 'codegen inputs changed: ' + repr(sorted(set(files) & set(inputs)))
    assert c610.COMPAT not in files and c610.CMAKE not in files and 'rpcs3/Emu/CMakeLists.txt' not in files, 'identity recipe touched'

    with tempfile.TemporaryDirectory(prefix='core638-codegen-') as temporary:
        tree = Path(temporary) / 'core636'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in inputs:
            if (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 636 bytes'
        report636 = c636.audit(tree, baseline)

    compat = (source / c610.COMPAT).read_text()
    cmake_text = (source / c610.CMAKE).read_text()
    current = c610.aliases(compat)
    result = {}
    for kind in ('PPU', 'SPU'):
        candidate, _ = c616.identity(source, cmake_text, current, kind)
        result[kind] = candidate
        assert candidate == c610.DELIVERED[kind], kind + ' identity changed: ' + candidate
    return dict(passed=True, codegen=result, new_exact_aliases=0, core636_audit=report636, compiler_executed=False,
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
