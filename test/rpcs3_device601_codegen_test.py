#!/usr/bin/env python3
"""Authenticate host-only decrementer changes and the exact cache alias.

No CMake, compiler, LLVM object, network, Core or iPhone execution occurs.
All physical identity inputs are read; the unchanged external LLVM backend
retains its authenticated old digest. Unknown future hashes remain unaliased.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

CPP = 'rpcs3/Emu/Cell/SPUThread.cpp'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
CMAKE = 'rpcs3/Emu/CMakeLists.txt'
HISTORY = 'docs/evidence/rpcs3-device597-20261030/cpu/codegen-review-final.json'
ALIAS_MARK = '    # Device601 decrementer follow-up:'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def braced(text, marker):
    start = text.index(marker)
    pos = text.index('{', start)
    depth = 0
    for end in range(pos, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[start:end + 1]
    raise ValueError('Unclosed body: ' + marker)


def aliases(text):
    found = re.findall(r'(?:if|elseif)\(source STREQUAL "([^"]+)" AND\s*actual STREQUAL "([0-9a-f]{64})"\)\s*'
                       r'set\(\$\{output\} "([0-9a-f]{64})" PARENT_SCOPE\)', text)
    result = {(path, actual): effective for path, actual, effective in found}
    assert len(result) == len(found), 'Duplicate aliases'
    return result


def audit(source, baseline, repo):
    old, now = (baseline / CPP).read_bytes(), (source / CPP).read_bytes()
    old_text, current = old.decode(), now.decode()
    assert old != now
    # Replace precisely the changed owner method and timer callback; every
    # declaration, field, layout, signature and other helper byte must match.
    before_method = braced(old_text, 'bool spu_thread::process_mfc_cmd()')
    after_method = braced(current, 'bool spu_thread::process_mfc_cmd()')
    assert before_method != after_method
    restored = current.replace(after_method, before_method, 1)
    before_timer = braced(old_text, 'struct spu_dec_intr_timer')
    after_timer = braced(restored, 'struct spu_dec_intr_timer')
    before_callback = braced(before_timer, 'void operator()()')
    after_callback = braced(after_timer, 'void operator()()')
    assert before_callback != after_callback
    assert after_timer.replace(after_callback, before_callback, 1) == before_timer, 'Timer layout or another timer method changed'
    restored = restored.replace(after_timer, before_timer, 1)
    assert restored.encode() == old, 'Changes outside two host bodies'
    old_compat, compat = (baseline / COMPAT).read_text(), (source / COMPAT).read_text()
    assert compat.count(ALIAS_MARK) == 1
    start = compat.index(ALIAS_MARK)
    end = compat.index('    # CELL559:', start)
    addition = compat[start:end]
    assert compat[:start] + compat[end:] == old_compat, 'Existing compatibility mappings changed'
    old_aliases, current_aliases = aliases(old_compat), aliases(compat)
    new_hash, old_hash = sha(now), sha(old)
    assert all(current_aliases.get(key) == value for key, value in old_aliases.items())
    assert set(current_aliases) - set(old_aliases) == {('Cell/SPUThread.cpp', new_hash)}
    assert old_hash == '254336c40c34189064bea97d4ab25021929b763f8c9f60ff72b433196cb61440'
    effective = old_aliases[('Cell/SPUThread.cpp', old_hash)]
    assert current_aliases[('Cell/SPUThread.cpp', new_hash)] == effective
    assert 'else()\n        set(${output} "${actual}" PARENT_SCOPE)' in compat
    cmake = (source / CMAKE).read_bytes()
    assert cmake == (baseline / CMAKE).read_bytes()
    history_raw = (repo / HISTORY).read_bytes()
    history = json.loads(history_raw)
    inputs, external, historical_baselines = {}, [], []
    for name, item in history['inputs'].items():
        if name in history['externalInputs']:
            assert item['before'] == item['after']
            before = after = item['after']
            external.append(name)
        else:
            prior = baseline / 'rpcs3/Emu' / name
            if name == 'Cell/SPUThread.cpp':
                before = sha(prior.read_bytes())
            else:
                # The small inverse tree may omit unchanged upstream support.
                # Its baseline digest is the authenticated old proof; the
                # actual candidate is still read and checked below. If an old
                # physical file is supplied, independently check it as well.
                before = item['after']
                historical_baselines.append(name)
                if prior.is_file():
                    assert sha(prior.read_bytes()) == before, ('baseline input', name)
            after = sha((source / 'rpcs3/Emu' / name).read_bytes())
            assert before == item['after'], ('historical input', name)
            assert after == (new_hash if name == 'Cell/SPUThread.cpp' else before), ('unreviewed input', name)
        inputs[name] = {'before': before, 'after': after}
    identities = {}
    no_alias = {}
    future = {}
    unknown_hash = sha(now + b'\n// unknown future source\n')
    assert current_aliases.get(('Cell/SPUThread.cpp', unknown_hash), unknown_hash) == unknown_hash
    assert current_aliases.get(('Cell/SPUThread.cpp.future', new_hash), new_hash) == new_hash
    for kind in ('PPU', 'SPU'):
        names = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake.decode(), re.S).group(1).split()
        assert f'neostation_codegen_compatible_hash("${{NEOSTATION_{kind}_CODEGEN_SOURCE}}" "${{NEOSTATION_{kind}_CODEGEN_FILE_SHA256}}" NEOSTATION_{kind}_CODEGEN_FILE_SHA256)' in cmake.decode()
        def identity(table, replacement=None):
            payload = ''
            for name in names:
                digest = replacement if replacement and name == 'Cell/SPUThread.cpp' else inputs[name]['after']
                payload += name + ':' + table.get((name, digest), digest) + ';'
            return sha(payload.encode())[:16]
        identities[kind] = identity(current_aliases)
        no_alias[kind] = identity(old_aliases)
        future[kind] = identity(current_aliases, unknown_hash)
    assert identities == history['candidateWithExactAlias'] == {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
    assert no_alias['PPU'] == identities['PPU'] and no_alias['SPU'] != identities['SPU']
    assert future['PPU'] == identities['PPU'] and future['SPU'] != identities['SPU']
    return dict(passed=True, source_sha256=new_hash, baseline_sha256=old_hash,
                compatibility_sha256=sha(compat.encode()), baseline_compatibility_sha256=sha(old_compat.encode()),
                addition_sha256=sha(addition.encode()), existing_aliases_preserved=len(old_aliases), new_exact_aliases=1,
                changed_host_bodies={'process_mfc_cmd': {'before': sha(before_method.encode()), 'after': sha(after_method.encode())},
                                     'decrementer_callback': {'before': sha(before_callback.encode()), 'after': sha(after_callback.encode())}},
                physical_codegen_inputs_checked=len(inputs) - len(external), external_llvm_inputs_reused=external,
                unchanged_baseline_digests_reused=historical_baselines,
                inputs=inputs, codegen=identities, without_new_alias=no_alias, future_unknown_source=future,
                history_sha256=sha(history_raw), script_sha256=sha(Path(__file__).read_bytes()),
                compiler_executed=False, cmake_executed=False, emitted_objects_compared=False,
                scope='Exact host-body restoration and existing ordered CMake identity recipe; no physical gameplay claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.source.resolve(), args.baseline.resolve(), args.repo.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'inputs'}, indent=2))


if __name__ == '__main__':
    main()
