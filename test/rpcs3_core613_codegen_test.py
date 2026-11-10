#!/usr/bin/env python3
"""Authenticate the two exact SPU codegen aliases of Core 613 (the Core 610 one and the 613 one).

Core 610 aliased one host-only SPUThread.cpp change (test/rpcs3_core610_codegen_test.py).
Core 613 adds one more exact alias: REWINDBOX_SPU_OBJECT_HIT_ADMISSION_613 changes only
where SPULLVMRecompiler.cpp compile() takes the LLVM compile admission, so emitted objects
are unchanged and that file keeps its delivered Core 612 hash (deb95e09...).

This audit reads the materialized Core 613 tree (source) and the delivered a4ae86d0 tree
(baseline) and recomputes the ordered CMake identity recipe without CMake, a compiler or
LLVM. It requires:
- JITCacheCompatibility.cmake = the baseline file plus exactly the Core 610 alias block and
  the Core 613 alias block; every baseline alias kept;
- only Cell/SPUThread.cpp and Cell/SPULLVMRecompiler.cpp differ among the codegen inputs;
- SPUThread.cpp is the reviewed Core 610 file (its change confined to process_mfc_cmd);
- SPULLVMRecompiler.cpp, with the 613 block removed and the Core 612 admission statement
  restored at its place, is the delivered Core 612 file byte for byte;
- the identities are the delivered PPU a987639e9f838d1c / SPU 477a3fa442d27917, the SPU one
  differs without the 613 alias, and an unknown future source stays unaliased.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK_613 = '    # REWINDBOX_SPU_OBJECT_HIT_ADMISSION_613:'
END_613 = '    else()\n'
LLVM = 'Cell/SPULLVMRecompiler.cpp'
THREAD = 'Cell/SPUThread.cpp'
CORE612_LLVM_SHA = 'deb95e09dfe245343b482b0b0cb4a20f69b50eb8694f838a87d2bfee193215ff'


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c610 = module('core610_codegen', ROOT / 'test/rpcs3_core610_codegen_test.py')
hit613 = module('core613_hit', ROOT / 'test/rpcs3_spu_object_hit_admission613_test.py')


def audit(source: Path, baseline: Path) -> dict:
    sha = c610.sha
    old_thread, thread = (baseline / c610.CPP).read_bytes(), (source / c610.CPP).read_bytes()
    assert sha(old_thread) == c610.BASELINE_SHA and sha(thread) == c610.CANDIDATE_SHA, 'Not the reviewed SPUThread.cpp pair'
    before = c610.braced(old_thread.decode(), 'bool spu_thread::process_mfc_cmd()')
    after = c610.braced(thread.decode(), 'bool spu_thread::process_mfc_cmd()')
    assert thread.decode().replace(after, before, 1).encode() == old_thread, 'SPUThread.cpp changes outside process_mfc_cmd'

    llvm_raw = (source / 'rpcs3/Emu' / LLVM).read_bytes()
    restored = hit613.restored_612(llvm_raw.decode())
    assert sha(restored) == CORE612_LLVM_SHA, 'SPULLVMRecompiler.cpp differs from Core 612 outside the 613 block'

    old_compat, compat = (baseline / c610.COMPAT).read_text(), (source / c610.COMPAT).read_text()
    assert compat.count(c610.ALIAS_MARK) == 1 and compat.count(MARK_613) == 1
    start610 = compat.index(c610.ALIAS_MARK)
    end610 = compat.index(c610.NEXT_MARK, start610)
    start613 = compat.index(MARK_613)
    end613 = compat.index(END_613, start613)
    assert end610 <= start613, 'the 613 block follows the 610 block'
    addition610, addition613 = compat[start610:end610], compat[start613:end613]
    stripped = compat[:start610] + compat[end610:start613] + compat[end613:]
    assert stripped == old_compat, 'Existing compatibility mappings changed'
    old_aliases, current = c610.aliases(old_compat), c610.aliases(compat)
    assert all(current.get(key) == value for key, value in old_aliases.items())
    llvm_sha = sha(llvm_raw)
    assert set(current) - set(old_aliases) == {(THREAD, c610.CANDIDATE_SHA), (LLVM, llvm_sha)}, 'Only the two reviewed SHAs may be aliased'
    assert current[(THREAD, c610.CANDIDATE_SHA)] == old_aliases[(THREAD, c610.BASELINE_SHA)]
    assert current[(LLVM, llvm_sha)] == CORE612_LLVM_SHA
    assert 'else()\n        set(${output} "${actual}" PARENT_SCOPE)' in compat
    cmake_text = (source / c610.CMAKE).read_text()
    assert (source / c610.CMAKE).read_bytes() == (baseline / c610.CMAKE).read_bytes(), 'Identity recipe changed'
    without_613 = {key: value for key, value in current.items() if key != (LLVM, llvm_sha)}
    unknown = sha(llvm_raw + b'\n// unknown future source\n')
    assert (LLVM, unknown) not in current

    def identity(tree, table, kind, replace=None):
        if replace is None:
            return c610.identity(tree, cmake_text, table, kind)
        # c610.identity replaces SPUThread.cpp only; replace SPULLVMRecompiler.cpp here.
        names = c610.re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake_text, c610.re.S).group(1).split()
        payload = ''
        for name in names:
            digest = c610.EXTERNAL[name] if name in c610.EXTERNAL else replace if name == LLVM else sha((tree / 'rpcs3/Emu' / name).read_bytes())
            payload += name + ':' + table.get((name, digest), digest) + ';'
        return sha(payload.encode())[:16], None

    result, inputs = {}, {}
    for kind in ('PPU', 'SPU'):
        cand, cand_digests = identity(source, current, kind)
        base, base_digests = identity(baseline, old_aliases, kind)
        no_613, _ = identity(source, without_613, kind)
        future, _ = identity(source, current, kind, unknown)
        changed = {name for name in cand_digests if cand_digests[name] != base_digests[name]}
        assert changed <= {THREAD, LLVM}, ('Unreviewed codegen input changed', kind, changed)
        inputs[kind] = {'count': len(cand_digests), 'changed': sorted(changed)}
        result[kind] = {'candidate': cand, 'delivered_baseline': base, 'without_613_alias': no_613, 'future_unknown_source': future}
    assert {k: v['candidate'] for k, v in result.items()} == {k: v['delivered_baseline'] for k, v in result.items()} == c610.DELIVERED
    assert result['PPU']['without_613_alias'] == c610.DELIVERED['PPU'] and result['SPU']['without_613_alias'] != c610.DELIVERED['SPU']
    assert result['PPU']['future_unknown_source'] == c610.DELIVERED['PPU'] and result['SPU']['future_unknown_source'] != c610.DELIVERED['SPU']
    return dict(passed=True, sputhread_sha256=c610.CANDIDATE_SHA, spullvm_sha256=llvm_sha,
                spullvm_restored_core612_sha256=CORE612_LLVM_SHA,
                compatibility_sha256=sha(compat.encode()), baseline_compatibility_sha256=sha(old_compat.encode()),
                addition610_sha256=sha(addition610.encode()), addition613_sha256=sha(addition613.encode()),
                existing_aliases_preserved=len(old_aliases), new_exact_aliases=2,
                codegen=result, inputs=inputs, external_llvm_inputs_reused=sorted(c610.EXTERNAL),
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
