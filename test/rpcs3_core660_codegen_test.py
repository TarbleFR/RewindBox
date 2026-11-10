#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 660 (unchanged from Core 659).

Core 660 = Core 659 + build-utils/rpcs3/core660-from-659.patch. Two codegen inputs change, in host code only:
- rpcs3/Emu/Cell/SPULLVMRecompiler.cpp:
  - REWINDBOX_SPU_TIMEBASE_MAPPING_660 maps spu_timebase_offs again, before its load, in the engine of the module being
    built (an engine mapping, not IR);
  - REWINDBOX_SPU_DIRECT_OBJECT_HIT_660 adds the direct cache-hit link (its includes, the binding table and its helper
    before compile(), the block in compile()) and lifts six lambdas into named static functions with the same bodies,
    called under the same names with the same arguments;
- Utilities/JITLLVM.cpp: the body of jit_compiler::try_add_minimal_object (REWINDBOX_SPU_DIRECT_OBJECT_HIT_660).
rpcs3/Emu/CPU/JITCacheCompatibility.cmake maps the exact new hash of each file to the effective hash the Core 659 file
already had, so the identities PPU a987639e9f838d1c / SPU 477a3fa442d27917 and every cached PPU module and SPU object
stay valid.

This audit reads the materialized Core 660 tree (source) and the delivered a4ae86d0 tree (baseline). It requires:
- exactly those two codegen inputs in the patch, the compatibility table changed, CMakeLists.txt untouched;
- with the patch reversed, every other codegen input byte-identical to its Core 659 bytes;
- the alias table: exactly one new entry per changed file, for its exact hash, to the Core 659 file's effective hash,
  and every older entry unchanged;
- the timebase step (build-utils/rpcs3/core660-lots/0-timebase.patch) changes SPULLVMRecompiler.cpp only by its marked
  mapping statement and comment;
- on the tree after that step, the SPU direct-hit structure audit of test/rpcs3_spu_direct_hit660_test.py: removing its
  marked insertions from the Core 660 file gives the timebase file with the six lambdas lifted mechanically, each lifted
  body byte-equal to its lambda (uniform tab shift), and JITLLVM.cpp differs only inside try_add_minimal_object;
- the Core 659 audit on the reversed tree (which runs the 655 to 634 audits in turn) and the identities.
No compiler, CMake or LLVM is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'build-utils/rpcs3/core660-from-659.patch'
TIMEBASE = ROOT / 'build-utils/rpcs3/core660-lots/0-timebase.patch'
SPU = 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'
JIT = 'Utilities/JITLLVM.cpp'
CHANGED = {SPU: 'Cell/SPULLVMRecompiler.cpp', JIT: '../../Utilities/JITLLVM.cpp'}
TIMEBASE_LINES = ('\t\t\t\t// REWINDBOX_SPU_TIMEBASE_MAPPING_660: ', 'm_engine->updateGlobalMapping("spu_timebase_offs", reinterpret_cast<u64>(&g_timebase_offs));')


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c659 = module('core659_codegen', ROOT / 'test/rpcs3_core659_codegen_test.py')
c619, c616, c610 = c659.c619, c659.c616, c659.c610
spu_test = module('spu_direct_hit660', ROOT / 'test/rpcs3_spu_direct_hit660_test.py')


def aliases(text: str) -> dict:
    return {(source, actual): effective for source, actual, effective in re.findall(
        r'source STREQUAL "([^"]+)" AND\s+actual STREQUAL "([0-9a-f]{64})"\)\s+set\(\$\{output\} "([0-9a-f]{64})"', text)}


def effective(table: dict, source: str, raw: bytes) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    return table.get((source, digest), digest)


def apply(tree: Path, patch: Path, reverse: bool = False) -> None:
    subprocess.run(['git', 'apply', *(['-R'] if reverse else []), '--whitespace=nowarn', str(patch)], cwd=tree, check=True, timeout=120)


def audit(source: Path, baseline: Path) -> dict:
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', PATCH.read_text('utf-8', 'surrogateescape'), re.M)
    inputs = c619.codegen_inputs(source)
    assert set(files) & set(inputs) == set(CHANGED), 'codegen inputs changed: ' + repr(sorted(set(files) & set(inputs)))
    assert c610.COMPAT in files and 'rpcs3/Emu/CMakeLists.txt' not in files and c610.CMAKE not in files, 'the identity recipe changed'
    with tempfile.TemporaryDirectory(prefix='core660-codegen-') as temporary:
        tree = Path(temporary) / 'core659'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        apply(tree, PATCH, reverse=True)
        for name in [*inputs, 'rpcs3/Emu/CMakeLists.txt']:
            if name not in CHANGED and (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 659 bytes'

        # The aliases: one exact entry per changed file, to the effective hash of its Core 659 file.
        new_table, old_table = aliases((source / c610.COMPAT).read_text()), aliases((tree / c610.COMPAT).read_text())
        assert all(new_table.get(key) == value for key, value in old_table.items()), 'an older alias changed or disappeared'
        added = {key: value for key, value in new_table.items() if key not in old_table}
        expected = {(cmake_name, hashlib.sha256((source / name).read_bytes()).hexdigest()):
                    effective(old_table, cmake_name, (tree / name).read_bytes()) for name, cmake_name in CHANGED.items()}
        assert added == expected, 'alias table: ' + json.dumps({f'{k[0]} {k[1]}': v for k, v in added.items()})

        # The timebase step: its marked statement and comment only.
        step0 = Path(temporary) / 'core660-step0'
        shutil.copytree(tree, step0, symlinks=True)
        apply(step0, TIMEBASE)
        old_spu, tb_spu = (tree / SPU).read_text('utf-8', 'surrogateescape'), (step0 / SPU).read_text('utf-8', 'surrogateescape')
        old_lines, tb_lines = old_spu.splitlines(keepends=True), tb_spu.splitlines(keepends=True)
        extra = [line for line in tb_lines if line not in old_lines]
        assert extra and all(line.strip().startswith('//') or TIMEBASE_LINES[1] in line for line in extra), 'timebase step lines'
        assert sum(TIMEBASE_LINES[1] in line for line in extra) == 1 and any(TIMEBASE_LINES[0].strip() in line for line in extra)
        assert ''.join(line for line in tb_lines if line not in extra) == old_spu, 'the timebase step changes more than its insertion'
        assert (step0 / JIT).read_bytes() == (tree / JIT).read_bytes(), 'the timebase step touches JITLLVM.cpp'

        # The direct-hit step: the structure audit of its own test, on the Core 660 files.
        new_spu = (source / SPU).read_text('utf-8', 'surrogateescape')
        new_jit, old_jit = (source / JIT).read_text('utf-8', 'surrogateescape'), (tree / JIT).read_text('utf-8', 'surrogateescape')
        structure = spu_test.audit_structure(tb_spu, new_spu, old_jit, new_jit)
        lifted = spu_test.audit_lambdas(tb_spu, new_spu)
        report659 = c659.audit(tree, baseline)

    compat = (source / c610.COMPAT).read_text()
    cmake_text = (source / c610.CMAKE).read_text()
    current = c610.aliases(compat)
    identities = {}
    for kind in ('PPU', 'SPU'):
        candidate, _ = c616.identity(source, cmake_text, current, kind)
        identities[kind] = candidate
        assert candidate == c610.DELIVERED[kind], kind + ' identity changed: ' + candidate
    return dict(passed=True, core660_files=sorted(files), codegen_inputs_checked=len(inputs), changed_codegen_inputs=sorted(CHANGED),
                exact_aliases={f'{k[0]} {k[1]}': v for k, v in added.items()}, codegen=identities, timebase_lines=len(extra),
                direct_structure=structure, lifted_functions=sorted(lifted), core659_audit=report659,
                compiler_executed=False, cmake_executed=False,
                scope='Core 660 changes two codegen inputs in host code only, with exact aliases; the Core 659 audit holds on the reversed tree; no gameplay claim')


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
