#!/usr/bin/env python3
"""Authenticate the host-only Core 609 SPUThread.cpp change and its exact cache alias.

REWINDBOX_CORE609_LR changes only the full-MFC-queue wait inside
spu_thread::process_mfc_cmd(). SPU objects reach that host body through helper
symbols, so emitted code is unchanged, and one exact alias keeps the delivered
SPU identity. This audit reads both materialized trees and recomputes the
ordered CMake identity recipe (rpcs3/Emu/CMakeLists.txt with
JITCacheCompatibility.cmake) without running CMake, a compiler or LLVM. The
external LLVM backend input keeps its authenticated recorded digest. Unknown
future hashes must stay unaliased.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

CPP = 'rpcs3/Emu/Cell/SPUThread.cpp'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
CMAKE = 'rpcs3/Emu/CMakeLists.txt'
ALIAS_MARK = '    # Core 609 LR follow-up:'
NEXT_MARK = '    # CELL559:'
BASELINE_SHA = '84cd797c8ebd47211f97ca1bb78af6c5dd71410530aa563b08bed39545852309'
CANDIDATE_SHA = '97da453d7717a1a63cd44f58d6ae1b6c0053f1f7e3a1c1626e90c83c1cfd518d'
EXTERNAL = {'../../3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp':
            'c6ee2a2a736b72b8f9109bbe9ad82e43a84d0ca1d5e2c75670603e423fd4c507'}
DELIVERED = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def braced(text: str, marker: str) -> str:
    start = text.index(marker)
    pos = text.index('{', start)
    depth = 0
    for end in range(pos, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[start:end + 1]
    raise ValueError('Unclosed body: ' + marker)


def aliases(text: str) -> dict:
    found = re.findall(r'(?:if|elseif)\(source STREQUAL "([^"]+)" AND\s*actual STREQUAL "([0-9a-f]{64})"\)\s*'
                       r'set\(\$\{output\} "([0-9a-f]{64})" PARENT_SCOPE\)', text)
    result = {(path, actual): effective for path, actual, effective in found}
    assert len(result) == len(found), 'Duplicate aliases'
    return result


def identity(tree: Path, cmake: str, table: dict, kind: str, replacement: str | None = None) -> tuple[str, dict]:
    names = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1).split()
    payload, digests = '', {}
    for name in names:
        if name in EXTERNAL:
            digest = EXTERNAL[name]
        elif replacement and name == 'Cell/SPUThread.cpp':
            digest = replacement
        else:
            digest = sha((tree / 'rpcs3/Emu' / name).read_bytes())
        digests[name] = digest
        payload += name + ':' + table.get((name, digest), digest) + ';'
    return sha(payload.encode())[:16], digests


def audit(source: Path, baseline: Path) -> dict:
    old, now = (baseline / CPP).read_bytes(), (source / CPP).read_bytes()
    assert sha(old) == BASELINE_SHA and sha(now) == CANDIDATE_SHA, 'Not the reviewed SPUThread.cpp pair'
    before_method = braced(old.decode(), 'bool spu_thread::process_mfc_cmd()')
    after_method = braced(now.decode(), 'bool spu_thread::process_mfc_cmd()')
    assert before_method != after_method
    assert now.decode().replace(after_method, before_method, 1).encode() == old, 'Changes outside process_mfc_cmd'
    old_compat, compat = (baseline / COMPAT).read_text(), (source / COMPAT).read_text()
    assert compat.count(ALIAS_MARK) == 1
    start = compat.index(ALIAS_MARK)
    end = compat.index(NEXT_MARK, start)
    addition = compat[start:end]
    assert compat[:start] + compat[end:] == old_compat, 'Existing compatibility mappings changed'
    old_aliases, current = aliases(old_compat), aliases(compat)
    assert all(current.get(key) == value for key, value in old_aliases.items())
    assert set(current) - set(old_aliases) == {('Cell/SPUThread.cpp', CANDIDATE_SHA)}, 'Only the reviewed SHA may be aliased'
    effective = old_aliases[('Cell/SPUThread.cpp', BASELINE_SHA)]
    assert current[('Cell/SPUThread.cpp', CANDIDATE_SHA)] == effective
    assert 'else()\n        set(${output} "${actual}" PARENT_SCOPE)' in compat
    cmake_text = (source / CMAKE).read_text()
    assert (source / CMAKE).read_bytes() == (baseline / CMAKE).read_bytes(), 'Identity recipe changed'
    unknown = sha(now + b'\n// unknown future source\n')
    assert current.get(('Cell/SPUThread.cpp', unknown), unknown) == unknown
    result, inputs = {}, {}
    for kind in ('PPU', 'SPU'):
        cand, cand_digests = identity(source, cmake_text, current, kind)
        base, base_digests = identity(baseline, cmake_text, old_aliases, kind)
        no_alias, _ = identity(source, cmake_text, old_aliases, kind)
        future, _ = identity(source, cmake_text, current, kind, unknown)
        changed = {name for name in cand_digests if cand_digests[name] != base_digests[name]}
        assert changed <= {'Cell/SPUThread.cpp'}, ('Unreviewed codegen input changed', kind, changed)
        inputs[kind] = {'count': len(cand_digests), 'changed': sorted(changed)}
        result[kind] = {'candidate': cand, 'delivered_baseline': base, 'without_new_alias': no_alias,
                        'future_unknown_source': future}
    assert {k: v['candidate'] for k, v in result.items()} == {k: v['delivered_baseline'] for k, v in result.items()} == DELIVERED
    assert result['PPU']['without_new_alias'] == DELIVERED['PPU'] and result['SPU']['without_new_alias'] != DELIVERED['SPU']
    assert result['PPU']['future_unknown_source'] == DELIVERED['PPU'] and result['SPU']['future_unknown_source'] != DELIVERED['SPU']
    return dict(passed=True, source_sha256=CANDIDATE_SHA, baseline_sha256=BASELINE_SHA,
                compatibility_sha256=sha(compat.encode()), baseline_compatibility_sha256=sha(old_compat.encode()),
                addition_sha256=sha(addition.encode()), existing_aliases_preserved=len(old_aliases), new_exact_aliases=1,
                changed_host_bodies={'process_mfc_cmd': {'before': sha(before_method.encode()), 'after': sha(after_method.encode())}},
                codegen=result, inputs=inputs, external_llvm_inputs_reused=sorted(EXTERNAL),
                compiler_executed=False, cmake_executed=False, emitted_objects_compared=False,
                scope='Exact host-body restoration and the ordered CMake identity recipe; no gameplay claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
