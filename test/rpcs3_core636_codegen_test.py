#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 636: one exact alias, the delivered identities.

Core 636 = Core 634 + build-utils/rpcs3/core636-from-634.patch. One codegen input changes, host code only:
PPUThread.cpp's parallel check pass assigns no further object check after a missing object or a stop
(REWINDBOX_PPU_CHECK_STOP_636). No translator, pass, emission, relocation or symbol changes. It keeps its
delivered effective hash for this exact source snapshot, so every cached PPU module and SPU object stays valid.

This audit reads the materialized Core 636 tree (source) and the delivered a4ae86d0 tree (baseline). No
compiler, CMake or LLVM is executed. It requires:
- among the codegen inputs, exactly PPUThread.cpp changes, and the CMake recipe does not;
- its changed lines name nothing of code generation;
- with the patch reversed, every codegen input is the Core 634 file and the Core 634 audit passes;
- JITCacheCompatibility.cmake = the Core 634 file plus exactly one alias block, every alias kept;
- the identities are PPU a987639e9f838d1c / SPU 477a3fa442d27917 and both differ without the new alias.
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
PATCH = ROOT / 'build-utils/rpcs3/core636-from-634.patch'
MARK = '    # REWINDBOX_PPU_CHECK_STOP_636'
END = '    else()\n'
PPU = 'Cell/PPUThread.cpp'
FILES = {PPU: 'rpcs3/Emu/Cell/PPUThread.cpp'}


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c634 = module('core634_codegen', ROOT / 'test/rpcs3_core634_codegen_test.py')
c619, c616, c610 = c634.c619, c634.c616, c634.c610


def audit(source: Path, baseline: Path) -> dict:
    sha = c610.sha
    patch = PATCH.read_text('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', patch, re.M)
    inputs = c619.codegen_inputs(source)
    assert set(files) & set(inputs) == set(FILES.values()), 'codegen inputs changed: ' + repr(sorted(set(files) & set(inputs)))
    assert 'rpcs3/Emu/CMakeLists.txt' not in files, 'the identity recipe changed'
    assert c610.COMPAT in files, 'the alias lives in the compatibility table'

    for name in FILES.values():
        section = patch[patch.index(f'diff --git a/{name} '):]
        section = section[:section.find('\ndiff --git ', 1) if '\ndiff --git ' in section[1:] else len(section)]
        changed = [line for line in section.splitlines() if line[:1] in '+-' and line[:3] not in ('+++', '---')]
        touched = [word for word in c634.FORBIDDEN if any(word in line for line in changed)]
        assert not touched, name + ' touches code generation: ' + repr(touched)

    with tempfile.TemporaryDirectory(prefix='core636-codegen-') as temporary:
        tree = Path(temporary) / 'core634'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in inputs:
            if name in FILES.values() or not (source / name).exists():
                continue
            assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 634 bytes'
        report634 = c634.audit(tree, baseline)
        restored = {key: (tree / path).read_bytes() for key, path in FILES.items()}
        old_compat = (tree / c610.COMPAT).read_text()

    compat = (source / c610.COMPAT).read_text()
    assert compat.count(MARK) == 1, 'one alias block'
    start = compat.index(MARK)
    stop = compat.index(END, start)
    assert compat[:start] + compat[stop:] == old_compat, 'existing compatibility mappings changed'
    old_aliases, current = c610.aliases(old_compat), c610.aliases(compat)
    assert all(current.get(key) == value for key, value in old_aliases.items())
    ppu_sha = sha((source / FILES[PPU]).read_bytes())
    assert set(current) - set(old_aliases) == {(PPU, ppu_sha)}, 'only the reviewed PPUThread.cpp SHA may be aliased'
    assert current[(PPU, ppu_sha)] == old_aliases[(PPU, sha(restored[PPU]))], 'PPUThread.cpp keeps its delivered effective hash'
    assert 'else()\n        set(${output} "${actual}" PARENT_SCOPE)' in compat

    cmake_text = (source / c610.CMAKE).read_text()
    assert (source / c610.CMAKE).read_bytes() == (baseline / c610.CMAKE).read_bytes(), 'identity recipe changed'
    without = {key: value for key, value in current.items() if key != (PPU, ppu_sha)}
    result = {}
    for kind in ('PPU', 'SPU'):
        candidate, _ = c616.identity(source, cmake_text, current, kind)
        no_alias, _ = c616.identity(source, cmake_text, without, kind)
        result[kind] = {'candidate': candidate, 'without_636_alias': no_alias}
        assert candidate == c610.DELIVERED[kind], kind + ' identity changed: ' + candidate
    # PPUThread.cpp is a PPU codegen input: without the alias its identity moves; SPU does not read it.
    assert result['PPU']['without_636_alias'] != c610.DELIVERED['PPU'], 'PPU identity does not depend on the 636 alias'
    return dict(passed=True, aliases={'PPUThread.cpp': ppu_sha}, core634_audit=report634, codegen=result,
                compatibility_sha256=sha(compat.encode()), new_exact_aliases=1, compiler_executed=False, cmake_executed=False,
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
