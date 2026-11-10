#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 634: two exact aliases, the delivered identities.

Core 634 = Core 630 + build-utils/rpcs3/core634-from-630.patch. Two codegen inputs change, host code
only: PPUThread.cpp checks and links the same cached objects on several threads, and JITLLVM.cpp keeps
object bytes outside MCJIT until finalizeObject and skips a debug copy nothing reads. No translator,
pass, emission, relocation or symbol changes. Both keep their Core 630 effective hashes for these
exact source snapshots, so every cached PPU module and SPU object stays valid.

This audit reads the materialized Core 634 tree (source) and the delivered a4ae86d0 tree (baseline).
No compiler, CMake or LLVM is executed. It requires:
- among the codegen inputs, exactly these two files change, and the CMake recipe does not;
- with the patch reversed, every codegen input is the Core 630 file and the Core 630 audit passes;
- JITCacheCompatibility.cmake = the Core 630 file plus exactly the two alias blocks, every alias kept;
- the identities are PPU a987639e9f838d1c / SPU 477a3fa442d27917, both differ without the two
  aliases, and an unknown future JITLLVM.cpp stays unaliased;
- the changes to the two files name nothing of code generation.
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
PATCH = ROOT / 'build-utils/rpcs3/core634-from-630.patch'
MARK = '    # REWINDBOX_FAST_JIT_LOAD_634, REWINDBOX_JIT_OBJECT_RELEASE_634'
END = '    else()\n'
JIT = '../../Utilities/JITLLVM.cpp'
PPU = 'Cell/PPUThread.cpp'
FILES = {JIT: 'Utilities/JITLLVM.cpp', PPU: 'rpcs3/Emu/Cell/PPUThread.cpp'}
FORBIDDEN = ('setMCPU', 'setMAttrs', 'setOptLevel', 'setCodeModel', 'setRelocationModel', 'addPass', 'PPUTranslator', 'emitObject', 'target_attributes',
             'obj_name, "v', 'fmt::append(obj_name', 'sha1_update', 'triple1', 'triple2')


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c630 = module('core630_codegen', ROOT / 'test/rpcs3_core630_codegen_test.py')
c619 = c630.c619
c616 = module('core616_codegen', ROOT / 'test/rpcs3_core616_codegen_test.py')
c610 = c616.c610


def audit(source: Path, baseline: Path) -> dict:
    sha = c610.sha
    patch = PATCH.read_text('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', patch, re.M)
    inputs = c619.codegen_inputs(source)
    assert set(files) & set(inputs) == set(FILES.values()), 'codegen inputs changed: ' + repr(sorted(set(files) & set(inputs)))
    assert 'rpcs3/Emu/CMakeLists.txt' not in files, 'the identity recipe changed'
    assert c610.COMPAT in files, 'the aliases live in the compatibility table'

    for name in FILES.values():
        section = patch[patch.index(f'diff --git a/{name} '):]
        section = section[:section.find('\ndiff --git ', 1) if '\ndiff --git ' in section[1:] else len(section)]
        changed = [line for line in section.splitlines() if line[:1] in '+-' and line[:3] not in ('+++', '---')]
        touched = [word for word in FORBIDDEN if any(word in line for line in changed)]
        assert not touched, name + ' touches code generation: ' + repr(touched)

    with tempfile.TemporaryDirectory(prefix='core634-codegen-') as temporary:
        tree = Path(temporary) / 'core630'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in inputs:
            if name in FILES.values() or not (source / name).exists():
                continue
            assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 630 bytes'
        report630 = c630.audit(tree, baseline)
        restored = {key: (tree / path).read_bytes() for key, path in FILES.items()}
        old_compat = (tree / c610.COMPAT).read_text()

    compat = (source / c610.COMPAT).read_text()
    assert compat.count(MARK) == 1, 'one alias block'
    start = compat.index(MARK)
    stop = compat.index(END, start)
    assert compat[:start] + compat[stop:] == old_compat, 'existing compatibility mappings changed'
    old_aliases, current = c610.aliases(old_compat), c610.aliases(compat)
    assert all(current.get(key) == value for key, value in old_aliases.items())
    jit_sha, ppu_sha = sha((source / FILES[JIT]).read_bytes()), sha((source / FILES[PPU]).read_bytes())
    assert set(current) - set(old_aliases) == {(JIT, jit_sha), (PPU, ppu_sha)}, 'only the two reviewed SHAs may be aliased'
    assert current[(JIT, jit_sha)] == old_aliases[(JIT, sha(restored[JIT]))], 'JITLLVM.cpp keeps its Core 630 effective hash'
    assert current[(PPU, ppu_sha)] == sha(restored[PPU]), 'PPUThread.cpp keeps its Core 630 hash'
    assert 'else()\n        set(${output} "${actual}" PARENT_SCOPE)' in compat

    cmake_text = (source / c610.CMAKE).read_text()
    assert (source / c610.CMAKE).read_bytes() == (baseline / c610.CMAKE).read_bytes(), 'identity recipe changed'
    without = {key: value for key, value in current.items() if key not in {(JIT, jit_sha), (PPU, ppu_sha)}}
    unknown = sha((source / FILES[JIT]).read_bytes() + b'\n// unknown future source\n')
    assert (JIT, unknown) not in current
    result = {}
    for kind in ('PPU', 'SPU'):
        candidate, _ = c616.identity(source, cmake_text, current, kind)
        no_aliases, _ = c616.identity(source, cmake_text, without, kind)
        future, _ = c616.identity(source, cmake_text, current, kind, {JIT: unknown})
        result[kind] = {'candidate': candidate, 'without_634_aliases': no_aliases, 'future_unknown_jitllvm': future}
        assert candidate == c610.DELIVERED[kind], kind + ' identity changed: ' + candidate
        assert no_aliases != c610.DELIVERED[kind], kind + ' depends on the 634 aliases'
        assert future != c610.DELIVERED[kind], kind + ' rejects an unknown JITLLVM.cpp'
    return dict(passed=True, aliases={'JITLLVM.cpp': jit_sha, 'PPUThread.cpp': ppu_sha}, core630_audit=report630, codegen=result,
                compatibility_sha256=sha(compat.encode()), new_exact_aliases=2, compiler_executed=False, cmake_executed=False,
                emitted_objects_compared=False, scope='The ordered CMake identity recipe and exact host-code snapshots; no gameplay claim')


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
