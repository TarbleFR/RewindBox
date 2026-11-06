#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 905: no codegen input changes.

Core 903 = Core 668 + build-utils/rpcs3/core901-from-668.patch (the native Metal 4 renderer, stage M1) +
build-utils/rpcs3/core902-from-901.patch (stage M2: shaders to MSL through SPIRV-Cross, the draw path) +
build-utils/rpcs3/core903-from-902.patch (stages M3 and M4: textures, queries, MSAA, conversion kernels, overlays) +
build-utils/rpcs3/core904-from-903.patch (Utilities/JITIOS.cpp high window, Metal M5 part 1, M3 gaps, rsx_cache.h). The
increments add the Metal sources to rpcs3/Emu/CMakeLists.txt, the file that carries the codegen identity recipe, so this audit
recomputes the ordered identity recipe of the source and requires the delivered identities: every cached PPU module
and SPU object stays valid. It reads the materialized Core 905 tree (source) and the delivered a4ae86d0 tree
(baseline); no compiler, CMake or LLVM is executed. It requires:
- no file of either increment is a codegen input, and the compatibility table is untouched;
- the identities computed from the source are the delivered PPU/SPU identities;
- with every increment reversed, the Core 668 audit passes (which runs the 665, 664 and earlier audits in turn) and every
  codegen input is byte-identical between the reversed tree and the source.
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
PATCHES = (ROOT / 'build-utils/rpcs3/core905-from-904.patch', ROOT / 'build-utils/rpcs3/core904-from-903.patch', ROOT / 'build-utils/rpcs3/core903-from-902.patch', ROOT / 'build-utils/rpcs3/core902-from-901.patch',
           ROOT / 'build-utils/rpcs3/core901-from-668.patch')


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c668 = module('core668_codegen', ROOT / 'test/rpcs3_core668_codegen_test.py')
c665 = c668.c665
c619, c616, c610 = c665.c619, c665.c616, c665.c610


def increment_files() -> set:
    files = set()
    for patch in PATCHES:
        files |= set(re.findall(r'^diff --git a/(\S+) b/\S+$', patch.read_text('utf-8', 'surrogateescape'), re.M))
    return files


def identities(source: Path) -> dict:
    compat = (source / c610.COMPAT).read_text()
    cmake_text = (source / c610.CMAKE).read_text()
    current = c610.aliases(compat)
    return {kind: c616.identity(source, cmake_text, current, kind)[0] for kind in ('PPU', 'SPU')}


def audit(source: Path, baseline: Path) -> dict:
    files = increment_files()
    inputs = c619.codegen_inputs(source)
    assert not files & set(inputs), 'codegen inputs changed: ' + repr(sorted(files & set(inputs)))
    assert c610.COMPAT not in files, 'the compatibility table changed'
    result = identities(source)
    for kind, candidate in result.items():
        assert candidate == c610.DELIVERED[kind], kind + ' identity changed: ' + candidate

    with tempfile.TemporaryDirectory(prefix='core905-codegen-') as temporary:
        tree = Path(temporary) / 'core668'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        for patch in PATCHES:
            subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(patch)], cwd=tree, check=True, timeout=300)
        for name in inputs:
            if (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 668 bytes'
        reversed_identities = identities(tree)
        assert reversed_identities == result, 'the reversed Core 668 tree computes other identities'
        report668 = c668.audit(tree, baseline)

    return dict(passed=True, codegen=result, new_exact_aliases=0, identity_recipe_file_changed=c610.CMAKE in files,
                core668_audit=report668, compiler_executed=False, cmake_executed=False, emitted_objects_compared=False,
                scope='The ordered CMake identity recipe and exact host-code snapshots; no gameplay claim')


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
    print(text)


if __name__ == '__main__':
    main()
