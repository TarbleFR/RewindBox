#!/usr/bin/env python3
"""Prove the exact runtime-only SPU delta and verify cache IDs in CMake script mode.

No Core configuration, compiler or historical native suite is run. All physical
codegen inputs are hashed from both trees; the external LLVM backend digest is
the same pinned manifest postimage used by the existing source-contract proof.
Only the exact reviewed SPUThread snapshot is aliased. An appended future edit
and a wrong source path remain unrecognized and invalidate normally.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from rpcs3_spu_timer_runtime_test import scope_proof
from rpcs3_texture_address_index_test import braced

ROOT = Path(__file__).resolve().parents[1]
CPP = 'rpcs3/Emu/Cell/SPUThread.cpp'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
CMAKE = 'rpcs3/Emu/CMakeLists.txt'
SPULLVM = 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'
SOURCE = (CPP, COMPAT)
SUPPORT = (CMAKE, SPULLVM, 'rpcs3/Emu/Cell/SPUThread.h', 'rpcs3/Emu/CPU/CPUThread.h')
COMMENT = '''    # Runtime MFC/timer follow-up: only do_mfc's host clock mask and the
    # decrementer timer worker change. SPU layout, translator, helper symbols,
    # relocation targets and every other SPUThread.cpp body remain identical.
'''
KNOWN_IDS = dict(PPU='a987639e9f838d1c', SPU='d070cb361bdef607')
SPU_EQUIVALENT = '9d0a2e1fedc6f3ee5a1e0888b40522d6517ecee96d6d57d015f15dcff319eb3c'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def aliases(text):
    matches = re.findall(r'(?:if|elseif)\(source STREQUAL "([^"]+)" AND\s+'
                         r'actual STREQUAL "([a-f0-9]{64})"\)\s+'
                         r'set\(\$\{output\} "([a-f0-9]{64})" PARENT_SCOPE\)', text)
    assert len(matches) == 4, 'Unrecognized compatibility function shape'
    assert 'else()\n        set(${output} "${actual}" PARENT_SCOPE)\n    endif()' in text
    return {(path, actual): compatible for path, actual, compatible in matches}


def source_proof(source, baseline):
    """Read-only, compiler-free proof usable by the new aggregate source gate."""
    source, baseline = Path(source), Path(baseline)
    runtime = scope_proof(source, baseline)
    before_hash, after_hash = (sha((tree / CPP).read_bytes()) for tree in (baseline, source))
    old_compat, new_compat = ((tree / COMPAT).read_text() for tree in (baseline, source))
    assert new_compat.count(COMMENT) == 1
    assert new_compat.replace(COMMENT, '', 1).replace(after_hash, before_hash, 1) == old_compat
    old_aliases, new_aliases = aliases(old_compat), aliases(new_compat)
    assert old_aliases[('Cell/SPUThread.cpp', before_hash)] == SPU_EQUIVALENT
    assert new_aliases[('Cell/SPUThread.cpp', after_hash)] == SPU_EQUIVALENT
    assert ('Cell/SPUThread.cpp', before_hash) not in new_aliases
    cmake = (source / CMAKE).read_text()
    assert cmake == (baseline / CMAKE).read_text()
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_text())
    llvm_digest = manifest['llvm_aarch64_ghc_patch']['postimage_sha256']
    assert re.fullmatch('[a-f0-9]{64}', llvm_digest)
    inputs, names, mapped, identities, raw_identities = {}, {}, {}, {}, {}
    changed = set()
    for kind in ('PPU', 'SPU'):
        names[kind] = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1).split()
        assert f'neostation_codegen_compatible_hash("${{NEOSTATION_{kind}_CODEGEN_SOURCE}}" "${{NEOSTATION_{kind}_CODEGEN_FILE_SHA256}}" NEOSTATION_{kind}_CODEGEN_FILE_SHA256)' in cmake
        mapped[kind] = {}
        baseline_parts, candidate_parts, unaliased_parts = [], [], []
        for name in names[kind]:
            if name.endswith('/AArch64FrameLowering.cpp'):
                old = new = llvm_digest
                external = True
            else:
                old, new = (sha((tree / 'rpcs3/Emu' / name).read_bytes()) for tree in (baseline, source))
                external = False
            if old != new:
                changed.add(name)
            inputs[name] = dict(baselineSHA256=old, sourceSHA256=new, externalManifestPostimage=external)
            b = old_aliases.get((name, old), old)
            a = new_aliases.get((name, new), new)
            without = old_aliases.get((name, new), new)
            mapped[kind][name] = a
            baseline_parts.append(f'{name}:{b};')
            candidate_parts.append(f'{name}:{a};')
            unaliased_parts.append(f'{name}:{without};')
        old_id = sha(''.join(baseline_parts).encode())[:16]
        new_id = sha(''.join(candidate_parts).encode())[:16]
        assert old_id == new_id == KNOWN_IDS[kind], (kind, old_id, new_id)
        identities[kind] = new_id
        raw_identities[kind] = sha(''.join(unaliased_parts).encode())[:16]
    assert changed == {'Cell/SPUThread.cpp'}
    assert len(inputs) == 41 and sum(not v['externalManifestPostimage'] for v in inputs.values()) == 40
    assert raw_identities['PPU'] == identities['PPU'] and raw_identities['SPU'] != identities['SPU']
    llvm = (source / SPULLVM).read_text()
    assert llvm == (baseline / SPULLVM).read_text()
    helper = braced(llvm, 'static void exec_list_unstall(spu_thread* _spu, u32 tag)')
    assert '_spu->do_mfc();' in helper
    return dict(runtimeScope=runtime, codegen=identities, withoutUpdatedExactAlias=raw_identities,
                codegenInputPaths=41, physicalCodegenInputs=40, changedCodegenInputs=sorted(changed),
                inputs=inputs, sourceLists=names, mappedSHA256=mapped,
                alias=dict(path='Cell/SPUThread.cpp', baselineSHA256=before_hash,
                           actualSHA256=after_hash, compatibleSHA256=SPU_EQUIVALENT),
                unchangedHostCallWrapperSHA256=sha(helper.encode()),
                unchangedAllOtherEmissionInputs=True, coldCompileRequiredByThisChange=False,
                externalLLVMBackendMaterialized=False)


def cmake_script(source, baseline, proof):
    source, baseline = Path(source), Path(baseline)
    script = ''
    future = sha((source / CPP).read_bytes() + b'\n// unreviewed future edit\n')
    for mode, compat, key in (
            ('baseline', baseline / COMPAT, 'baselineSHA256'),
            ('unaliased', baseline / COMPAT, 'sourceSHA256'),
            ('candidate', source / COMPAT, 'sourceSHA256'),
            ('future', source / COMPAT, 'sourceSHA256')):
        script += f'include("{compat}")\n'
        for kind in ('PPU', 'SPU'):
            script += 'set(parts "")\n'
            for path in proof['sourceLists'][kind]:
                digest = future if mode == 'future' and path == 'Cell/SPUThread.cpp' else proof['inputs'][path][key]
                script += (f'neostation_codegen_compatible_hash("{path}" "{digest}" mapped)\n'
                           f'string(APPEND parts "{path}:${{mapped}};")\n')
            script += ('string(SHA256 result "${parts}")\nstring(SUBSTRING "${result}" 0 16 result)\n'
                       f'message("{mode}_{kind}=${{result}}")\n')
    actual = proof['alias']['actualSHA256']
    script += f'''neostation_codegen_compatible_hash("Cell/SPUThread.cpp.future" "{actual}" wrong_path)
if(NOT wrong_path STREQUAL "{actual}")
  message(FATAL_ERROR "wrong source path was aliased")
endif()
neostation_codegen_compatible_hash("Cell/SPUThread.cpp" "{future}" future_hash)
if(NOT future_hash STREQUAL "{future}")
  message(FATAL_ERROR "unreviewed future source was aliased")
endif()
message("wrong_path_and_future_rejected=1")
'''
    return script


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    proof = source_proof(source, baseline)
    script = cmake_script(source, baseline, proof)
    # A gate may reconstruct the same baseline in another temporary directory.
    script = script.replace(str(source / COMPAT), '@SOURCE_COMPAT@').replace(str(baseline / COMPAT), '@BASELINE_COMPAT@')
    return dict(sourceSHA256={p: sha((source / p).read_bytes()) for p in SOURCE + SUPPORT},
                baselineSHA256={p: sha((baseline / p).read_bytes()) for p in SOURCE + SUPPORT},
                sourceProof=proof,
                harnessSHA256=sha(script.encode()))


def verify_counts(result):
    assert result['passed'] is True
    assert result['baseline'] == result['candidate'] == KNOWN_IDS
    assert result['unaliased']['PPU'] == KNOWN_IDS['PPU']
    assert result['unaliased']['SPU'] != KNOWN_IDS['SPU']
    assert result['future']['SPU'] != KNOWN_IDS['SPU']
    assert result['future']['PPU'] == KNOWN_IDS['PPU']
    assert result['wrongPathAndFutureRejected'] is True
    assert result['cmakeScriptInvocations'] == 1 and result['coreConfigured'] is False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--cmake', default=os.environ.get('CMAKE', 'cmake'))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    identities = expected(args.source, args.baseline)
    script = cmake_script(args.source, args.baseline, identities['sourceProof'])
    with tempfile.TemporaryDirectory(prefix='rpcs3-spu-runtime-cache-') as directory:
        path = Path(directory) / 'verify.cmake'
        path.write_text(script)
        output = subprocess.check_output([args.cmake, '-P', str(path)], text=True, stderr=subprocess.STDOUT)
    result = {mode: dict(re.findall(mode + r'_(PPU|SPU)=([a-f0-9]{16})', output))
              for mode in ('baseline', 'unaliased', 'candidate', 'future')}
    result.update(passed=True, wrongPathAndFutureRejected='wrong_path_and_future_rejected=1' in output,
                  cmakeScriptInvocations=1, coreConfigured=False)
    verify_counts(result)
    assert identities == expected(args.source, args.baseline)
    report = dict(passed=True, results=result, **identities,
                  cmake=subprocess.check_output([args.cmake, '--version'], text=True).splitlines()[0],
                  generatedObjectsRecompiled=False, historicalNativeSuitesReplayed=False,
                  physicalDeviceTested=False, scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=True, results=result, codegen=identities['sourceProof']['codegen'],
                          sourceSHA256=identities['sourceSHA256']), indent=2))


if __name__ == '__main__':
    main()
