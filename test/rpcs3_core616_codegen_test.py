#!/usr/bin/env python3
"""Authenticate the four exact SPU/PPU codegen aliases of Core 616.

Core 610 aliased one host-only SPUThread.cpp change (test/rpcs3_core610_codegen_test.py)
and Core 613 one SPULLVMRecompiler.cpp change (test/rpcs3_core613_codegen_test.py).
Core 616 adds two: REWINDBOX_SPU_OBJECT_PREFETCH_616 changes only how JITLLVM.cpp's
load_cached_object obtains the compressed bytes of an object file (taken from memory
when ios/IOSSpuObjectPrefetch.h already read that very file) and where
SPUCommonRecompiler.cpp starts that read (after the eviction plan). Object keys,
inflation, symbol validation, linking, emission and relocations are unchanged, so both
files keep their delivered Core 613 effective hashes.

This audit reads the materialized Core 616 tree (source) and the delivered a4ae86d0 tree
(baseline) and recomputes the ordered CMake identity recipe without CMake, a compiler or
LLVM. It requires:
- JITCacheCompatibility.cmake = the baseline file plus exactly the Core 610, Core 613 and
  Core 616 alias blocks, every baseline alias kept;
- only SPUThread.cpp, SPULLVMRecompiler.cpp, JITLLVM.cpp and SPUCommonRecompiler.cpp differ
  among the PPU and SPU codegen inputs;
- SPUThread.cpp is the reviewed Core 610 file and SPULLVMRecompiler.cpp the Core 613 file
  (both restorations as in the earlier audits);
- JITLLVM.cpp and SPUCommonRecompiler.cpp, with build-utils/rpcs3/core616-from-613.patch
  reverted, are the baseline files byte for byte;
- the identities are the delivered PPU a987639e9f838d1c / SPU 477a3fa442d27917, both
  differ without the 616 aliases, and an unknown future JITLLVM.cpp stays unaliased.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MARK_613 = '    # REWINDBOX_SPU_OBJECT_HIT_ADMISSION_613:'
MARK_616 = '    # REWINDBOX_SPU_OBJECT_PREFETCH_616:'
END = '    else()\n'
THREAD = 'Cell/SPUThread.cpp'
LLVM = 'Cell/SPULLVMRecompiler.cpp'
JIT = '../../Utilities/JITLLVM.cpp'
COMMON = 'Cell/SPUCommonRecompiler.cpp'
FILES_616 = {JIT: 'Utilities/JITLLVM.cpp', COMMON: 'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp'}


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c610 = module('core610_codegen', ROOT / 'test/rpcs3_core610_codegen_test.py')
c613 = module('core613_codegen', ROOT / 'test/rpcs3_core613_codegen_test.py')
hit613 = module('core613_hit', ROOT / 'test/rpcs3_spu_object_hit_admission613_test.py')
core616 = module('core616', ROOT / 'test/rpcs3_core616_test.py')


def identity(tree: Path, cmake: str, table: dict, kind: str, replace: dict | None = None):
    names = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1).split()
    payload, digests = '', {}
    for name in names:
        if name in c610.EXTERNAL:
            digest = c610.EXTERNAL[name]
        elif replace and name in replace:
            digest = replace[name]
        else:
            digest = c610.sha((tree / 'rpcs3/Emu' / name).read_bytes())
        digests[name] = digest
        payload += name + ':' + table.get((name, digest), digest) + ';'
    return c610.sha(payload.encode())[:16], digests


def audit(source: Path, baseline: Path) -> dict:
    sha = c610.sha
    old_thread, thread = (baseline / c610.CPP).read_bytes(), (source / c610.CPP).read_bytes()
    assert sha(old_thread) == c610.BASELINE_SHA and sha(thread) == c610.CANDIDATE_SHA, 'Not the reviewed SPUThread.cpp pair'
    before = c610.braced(old_thread.decode(), 'bool spu_thread::process_mfc_cmd()')
    after = c610.braced(thread.decode(), 'bool spu_thread::process_mfc_cmd()')
    assert thread.decode().replace(after, before, 1).encode() == old_thread, 'SPUThread.cpp changes outside process_mfc_cmd'

    llvm_raw = (source / 'rpcs3/Emu' / LLVM).read_bytes()
    assert sha(hit613.restored_612(llvm_raw.decode())) == c613.CORE612_LLVM_SHA, 'SPULLVMRecompiler.cpp is not the Core 613 file'

    with tempfile.TemporaryDirectory(prefix='core616-codegen-') as temporary:
        tree = core616.restore(source, Path(temporary), dict(core616.CORE613))
        restored = {name: (tree / path).read_bytes() for name, path in FILES_616.items()}
    for name, path in FILES_616.items():
        assert restored[name] == (baseline / path).read_bytes(), name + ' with the 616 insertions reverted is not the baseline file'

    old_compat, compat = (baseline / c610.COMPAT).read_text(), (source / c610.COMPAT).read_text()
    assert compat.count(c610.ALIAS_MARK) == compat.count(MARK_613) == compat.count(MARK_616) == 1
    start610 = compat.index(c610.ALIAS_MARK)
    end610 = compat.index(c610.NEXT_MARK, start610)
    start613 = compat.index(MARK_613)
    start616 = compat.index(MARK_616)
    end616 = compat.index(END, start616)
    assert end610 <= start613 < start616, 'the blocks follow each other'
    stripped = compat[:start610] + compat[end610:start613] + compat[end616:]
    assert stripped == old_compat, 'Existing compatibility mappings changed'
    old_aliases, current = c610.aliases(old_compat), c610.aliases(compat)
    assert all(current.get(key) == value for key, value in old_aliases.items())
    jit_sha = sha((source / FILES_616[JIT]).read_bytes())
    common_sha = sha((source / FILES_616[COMMON]).read_bytes())
    llvm_sha = sha(llvm_raw)
    new = {(THREAD, c610.CANDIDATE_SHA), (LLVM, llvm_sha), (JIT, jit_sha), (COMMON, common_sha)}
    assert set(current) - set(old_aliases) == new, 'Only the four reviewed SHAs may be aliased'
    assert current[(JIT, jit_sha)] == old_aliases[(JIT, sha(restored[JIT]))], 'JITLLVM.cpp keeps the delivered effective hash'
    assert current[(COMMON, common_sha)] == old_aliases[(COMMON, sha(restored[COMMON]))], 'SPUCommonRecompiler.cpp keeps the delivered effective hash'
    assert 'else()\n        set(${output} "${actual}" PARENT_SCOPE)' in compat
    cmake_text = (source / c610.CMAKE).read_text()
    assert (source / c610.CMAKE).read_bytes() == (baseline / c610.CMAKE).read_bytes(), 'Identity recipe changed'
    without_616 = {key: value for key, value in current.items() if key not in {(JIT, jit_sha), (COMMON, common_sha)}}
    unknown = sha((source / FILES_616[JIT]).read_bytes() + b'\n// unknown future source\n')
    assert (JIT, unknown) not in current

    result, inputs = {}, {}
    for kind in ('PPU', 'SPU'):
        cand, cand_digests = identity(source, cmake_text, current, kind)
        base, base_digests = identity(baseline, cmake_text, old_aliases, kind)
        no_616, _ = identity(source, cmake_text, without_616, kind)
        future, _ = identity(source, cmake_text, current, kind, {JIT: unknown})
        changed = {name for name in cand_digests if cand_digests[name] != base_digests[name]}
        assert changed <= {THREAD, LLVM, JIT, COMMON}, ('Unreviewed codegen input changed', kind, changed)
        inputs[kind] = {'count': len(cand_digests), 'changed': sorted(changed)}
        result[kind] = {'candidate': cand, 'delivered_baseline': base, 'without_616_aliases': no_616, 'future_unknown_jitllvm': future}
    assert {k: v['candidate'] for k, v in result.items()} == {k: v['delivered_baseline'] for k, v in result.items()} == c610.DELIVERED
    for kind in ('PPU', 'SPU'):
        assert result[kind]['without_616_aliases'] != c610.DELIVERED[kind], kind + ' depends on the 616 aliases'
        assert result[kind]['future_unknown_jitllvm'] != c610.DELIVERED[kind], kind + ' rejects an unknown JITLLVM.cpp'
    assert JIT in inputs['PPU']['changed'] and COMMON in inputs['SPU']['changed']
    return dict(passed=True, aliases={'SPUThread.cpp': c610.CANDIDATE_SHA, 'SPULLVMRecompiler.cpp': llvm_sha,
                                      'JITLLVM.cpp': jit_sha, 'SPUCommonRecompiler.cpp': common_sha},
                restored_616={name: sha(raw) for name, raw in restored.items()},
                compatibility_sha256=sha(compat.encode()), baseline_compatibility_sha256=sha(old_compat.encode()),
                addition616_sha256=sha(compat[start616:end616].encode()), existing_aliases_preserved=len(old_aliases),
                new_exact_aliases=4, codegen=result, inputs=inputs, external_llvm_inputs_reused=sorted(c610.EXTERNAL),
                compiler_executed=False, cmake_executed=False, emitted_objects_compared=False,
                scope='Exact host-body restorations and the ordered CMake identity recipe; no gameplay claim')


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
