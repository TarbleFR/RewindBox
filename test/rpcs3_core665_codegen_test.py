#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 665: no codegen input changes.

Core 665 = Core 664 + build-utils/rpcs3/core665-from-664.patch (REWINDBOX_THREAD_ORCHESTRATOR_665: placement samples,
writer-lock suspend timing, the PPU threads one relative step above the default USER_INTERACTIVE priority; its setting,
policy line, COREPROF PLACEMENT665 and levers627 digit 18). It touches no codegen input, so no alias is added and every cached PPU
module and SPU object stays valid. This audit reads the materialized Core 665 tree (source) and the delivered a4ae86d0
tree (baseline); no compiler, CMake or LLVM is executed. It requires:
- no file of the patch is a codegen input, and the compatibility table and identity recipe are untouched;
- with the patch reversed, the Core 664 audit passes (which runs the 660 audit and the earlier ones in turn);
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
PATCH = ROOT / 'build-utils/rpcs3/core665-from-664.patch'


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c664 = module('core664_codegen', ROOT / 'test/rpcs3_core664_codegen_test.py')
c619, c616, c610 = c664.c619, c664.c616, c664.c610


def audit(source: Path, baseline: Path) -> dict:
    patch = PATCH.read_text('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', patch, re.M)
    inputs = c619.codegen_inputs(source)
    assert not set(files) & set(inputs), 'codegen inputs changed: ' + repr(sorted(set(files) & set(inputs)))
    assert c610.COMPAT not in files and c610.CMAKE not in files and 'rpcs3/Emu/CMakeLists.txt' not in files, 'identity recipe touched'

    with tempfile.TemporaryDirectory(prefix='core665-codegen-') as temporary:
        tree = Path(temporary) / 'core664'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in inputs:
            if (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 664 bytes'
        report664 = c664.audit(tree, baseline)

    compat = (source / c610.COMPAT).read_text()
    cmake_text = (source / c610.CMAKE).read_text()
    current = c610.aliases(compat)
    result = {}
    for kind in ('PPU', 'SPU'):
        candidate, _ = c616.identity(source, cmake_text, current, kind)
        result[kind] = candidate
        assert candidate == c610.DELIVERED[kind], kind + ' identity changed: ' + candidate
    return dict(passed=True, codegen=result, new_exact_aliases=0, core664_audit=report664, compiler_executed=False,
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
