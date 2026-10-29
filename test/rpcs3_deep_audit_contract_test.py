#!/usr/bin/env python3
"""Authenticate the final deep-audit sources and retained native evidence.

Regenerate test programs as text, including the historical MFC stages, and
compare their exact hashes with recorded executions. No compiler, native test,
Core configuration, CMake script or device workload is executed by this gate.
Withdrawn raw-preload and texture experiments are deliberately not evidence
for the final source. Recorded host timings are not gameplay measurements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import rpcs3_async_sync_pool_test as async_pool
import rpcs3_jit_arena_merge_test as arena
import rpcs3_shader_token_test as shader
import rpcs3_spu_mfc_full_irq_test as irq
import rpcs3_spu_mfc_restore_test as restore
import rpcs3_spu_snr_event_test as snr
import rpcs3_spu_runtime_cache_test as cache
import rpcs3_texture_barrier_test as barrier
import rpcs3_texture_deep_test as texture
import neoswap_trim_total_test as trim

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/rpcs3-deep-audit-20261029'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
full = irq.full
tag = full.tag


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    """Canonical postimages normalize only CRLF, as the source manifest does."""
    return digest(path.read_bytes().replace(b'\r\n', b'\n'))


def raw_sha(path):
    return digest(path.read_bytes())


def git_file(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def codegen_identity(source, baseline, manifest, old, record):
    """Reproduce CMake's digest concatenation without invoking CMake."""
    assert (source / cache.COMPAT).read_bytes() == (baseline / cache.COMPAT).read_bytes()
    assert (source / cache.CMAKE).read_bytes() == (baseline / cache.CMAKE).read_bytes()
    assert manifest['llvm_aarch64_ghc_patch'] == old['llvm_aarch64_ghc_patch']
    aliases = cache.aliases((source / cache.COMPAT).read_text())
    cmake = (source / cache.CMAKE).read_text()
    inputs, identities = {}, {'before': {}, 'after': {}}
    external = '../../3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp'
    for kind in ('PPU', 'SPU'):
        names = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1).split()
        assert 'neostation_codegen_compatible_hash("${NEOSTATION_' + kind + '_CODEGEN_SOURCE}" "${NEOSTATION_' + kind + '_CODEGEN_FILE_SHA256}" NEOSTATION_' + kind + '_CODEGEN_FILE_SHA256)' in cmake
        for label, tree in [('before', baseline), ('after', source)]:
            parts = []
            for name in names:
                value = (manifest['llvm_aarch64_ghc_patch']['postimage_sha256'] if name == external
                         else raw_sha(tree / 'rpcs3/Emu' / name))
                inputs.setdefault(name, {})[label] = value
                parts.append(f'{name}:{aliases.get((name, value), value)};')
            identities[label][kind] = digest(''.join(parts).encode())[:16]
    assert len(inputs) == 41 and external in inputs
    assert identities['before'] == cache.KNOWN_IDS
    assert identities['after']['PPU'] == identities['before']['PPU']
    assert identities['after']['SPU'] != identities['before']['SPU']
    assert identities == record['codegenIdentity']
    assert inputs == record['codegenInputs']
    assert record['compatibilityAliasUnchanged'] is True
    assert record['externalLLVMBackendMaterialized'] is False
    assert {name for name, values in inputs.items() if values['before'] != values['after']} == {
        'Cell/SPUThread.cpp', 'Cell/SPUThread.h', 'Cell/SPULLVMRecompiler.cpp'}
    return identities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    manifest = json.loads((ROOT / MANIFEST).read_text())
    record = json.loads((EVIDENCE / 'source-record.json').read_text())
    assert record == manifest['deep_audit_20261029']
    commit = record['baseline_commit']
    assert commit.startswith('a363d923')
    old = json.loads(git_file(commit, MANIFEST))
    assert digest(git_file(commit, PATCH)) == old['patch_sha256'] == record['baseline_patch_sha256']
    assert raw_sha(ROOT / PATCH) == manifest['patch_sha256']
    for tree, expected in [(source, manifest['files_sha256']), (baseline, old['files_sha256'])]:
        for path, value in expected.items():
            assert sha(tree / path) == value, path
    changed = {path for path, value in manifest['files_sha256'].items()
               if old['files_sha256'].get(path) != value}
    assert changed == set(record['changed_core_files']) == set(record['files_after_sha256']) == set(record['files_before_sha256'])
    assert len(manifest['files_sha256']) == record['canonical_postimages']
    assert sum(path not in changed for path in old['files_sha256']) == record['historical_postimages_unchanged']
    assert set(old['files_sha256']) <= set(manifest['files_sha256'])
    for path in changed:
        assert sha(source / path) == record['files_after_sha256'][path]
        assert sha(baseline / path) == record['files_before_sha256'][path]
    fixture = ROOT / record['delta_fixture']
    assert raw_sha(fixture) == record['delta_sha256']
    with tempfile.TemporaryDirectory(prefix='rpcs3-deep-inverse-') as directory:
        tree = Path(directory)
        for path in changed:
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / path, target)
        subprocess.run(['git', 'apply', '--reverse', str(fixture)], cwd=tree, check=True)
        for path in changed:
            assert (tree / path).read_bytes() == (baseline / path).read_bytes(), path
    assert record['host_files_after_sha256'] == {trim.STORE: raw_sha(ROOT / trim.STORE)}
    for name in ('ios_build_run', 'iphone_validation_run', 'fps_gain_claimed', 'game_visual_or_freeze_fix_claimed'):
        assert record[name] is False
    # SH7 was measured and withdrawn: the final cache source must be baseline.
    raw_cache = 'rpcs3/Emu/RSX/rsx_cache.h'
    assert (source / raw_cache).read_bytes() == (baseline / raw_cache).read_bytes()

    proofs = {}
    def check(filename, program, module, tree=source, *, overrides=None, scope=None, raw=False):
        path = EVIDENCE / filename
        proof = json.loads(path.read_text())
        assert proof['passed'] is True, filename
        assert proof['physicalDeviceTested'] is False and proof['gameplayMeasured'] is False
        for key in ('llvmCompiled', 'aarch64Executed', 'realDMATransfersTested',
                    'concurrentMemoryOrderingTested', 'completeSavestateFormatTested',
                    'interruptControlFlagsEmulated', 'leakSanitizer', 'leakSanitizerEnabled'):
            if key in proof:
                assert proof[key] is False, (filename, key)
        assert proof['harnessSHA256'] == digest(program.encode()), filename
        flags = proof['compilerFlags']
        assert '-UNDEBUG' in flags and '-DNDEBUG' not in flags
        assert ('-fsanitize=address,undefined' in flags) == ('asan' in filename)
        hash_path = raw_sha if raw else sha
        for key, input_tree in [('sourceSHA256', tree), ('baselineSHA256', baseline)]:
            for name, value in proof.get(key, {}).items():
                actual = (overrides or {}).get(name) if key == 'sourceSHA256' else None
                assert (actual if actual is not None else hash_path(input_tree / name)) == value, (filename, key, name)
        adapters = proof['adapterSHA256']
        if isinstance(adapters, dict):
            for name, value in adapters.items():
                assert raw_sha(ROOT / name) == value, name
        else:
            assert hash_path(module.ADAPTER) == adapters, filename
        if 'scriptSHA256' in proof:
            assert raw_sha(Path(module.__file__)) == proof['scriptSHA256'], filename
        if 'runtimeBodySHA256' in proof:
            assert proof['runtimeBodySHA256'] == {name: digest(body.encode()) for name, body in tag.bodies(source).items()}
        for key, value in (scope or {}).items():
            assert proof[key] == value, (filename, key)
        proofs[str(path.relative_to(ROOT))] = dict(evidenceSHA256=raw_sha(path), harnessSHA256=proof['harnessSHA256'])
        return proof

    # Generate these programs from final sources. SNR explicitly verifies every
    # consumed CPP body is baseline-identical; its original full-file digest is
    # the baseline, preceding the separately authenticated constructor/IRQ edits.
    program = snr.harness(source, baseline)
    final_programs = {'snr': digest(program.encode())}
    for mode in ('plain', 'asan'):
        check(f'gow3-snr-{mode}.json', program, snr, overrides={snr.CPP: sha(baseline / snr.CPP)})

    # Materialize exact historical stages as text, not binaries. Final source
    # differs from the restore/full stage only by the dedicated IRQ prefix.
    # irq.harness verifies that exact edit and authenticates full -> tag too.
    program, scope = irq.harness(source, baseline)
    final_programs['mfc-full-irq'] = digest(program.encode())
    irq_scope = scope
    for mode in ('plain', 'asan'):
        check(f'gow3-mfc-full-irq-{mode}.json', program, irq, scope=scope, raw=True)
    with tempfile.TemporaryDirectory(prefix='rpcs3-deep-proof-stages-') as directory:
        stage = Path(directory)
        names = set(restore.INPUTS) | {tag.LLVM}
        for name in names:
            contents = (source / name).read_text()
            if name == tag.runtime.CPP:
                assert contents.count(irq.prefix(source)) == 1
                contents = contents.replace(irq.prefix(source), irq.prefix(baseline), 1)
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
        program = restore.harness(source, baseline)
        final_programs['mfc-restore'] = digest(program.encode())
        assert program == restore.harness(stage, baseline)
        for mode in ('plain', 'asan'):
            check(f'gow3-mfc-restore-{mode}.json', program, restore, stage, raw=True)
        program, scope = full.harness(stage, baseline)
        for mode in ('plain', 'asan'):
            check(f'gow3-mfc-full-{mode}.json', program, full, stage, scope=scope, raw=True)
        llvm = stage / tag.LLVM
        contents = llvm.read_text()
        assert contents.count(full.guard(stage)) == 1
        llvm.write_text(contents.replace(full.guard(stage), '', 1))
        program = tag.harness(stage, baseline)
        expected = tag.identities(stage, baseline)
        for mode in ('plain', 'asan'):
            check(f'gow3-mfc-llvm-{mode}.json', program, tag, stage, scope=expected, raw=True)

    for name, module in [('shader-tokens', shader), ('texture', texture), ('async-sync-pool', async_pool)]:
        program = module.harness(source, baseline)
        for mode in ('plain', 'asan'):
            check(f'{name}-{mode}.json', program, module)
    check('texture-barriers.json', barrier.harness(source, baseline), barrier)

    # Allocator input is the whole production class. Store additionally recorded
    # the complete POSIX suite; all four compiled project inputs are rehashed.
    arena_program = arena.harness((baseline / arena.HEADER).read_text(), (source / arena.HEADER).read_text())
    host_before = {name: git_file(commit, name) for name in trim.INPUTS}
    host_after = {name: (ROOT / name).read_bytes() for name in trim.INPUTS}
    assert all(host_before[name] == host_after[name] for name in trim.INPUTS[1:])
    trim_program = trim.harness(host_before[trim.STORE].decode(), host_after[trim.STORE].decode())
    store_dependencies = None
    for name, module, program in [('cpu-jit-arena', arena, arena_program), ('cpu-neoswap-trim', trim, trim_program)]:
        for mode in ('plain', 'asan'):
            path = EVIDENCE / f'{name}-{mode}.json'
            proof = json.loads(path.read_text())
            assert proof['passed'] is True and proof['results']['passed'] is True
            assert proof['deviceTest'] is False and proof['fpsClaim'] is False
            assert proof['leakSanitizer'] is False
            assert proof['harnessSHA256'] == digest(program.encode())
            assert proof['fixtureSHA256'] == raw_sha(module.FIXTURE)
            assert '-UNDEBUG' in proof['flags'] and '-DNDEBUG' not in proof['flags']
            assert ('-fsanitize=address,undefined' in proof['flags']) == (mode == 'asan')
            if module is arena:
                assert proof['sourceSHA256'] == digest((source / arena.HEADER).read_text().encode())
                assert proof['baselineSHA256'] == digest((baseline / arena.HEADER).read_text().encode())
                assert proof['fullProductionClass'] is True and proof['generatedCodeChanged'] is False
                assert proof['results']['randomOperations'] == 240000
            else:
                assert commit.startswith(proof['baselineCommit'])
                assert proof['sourceSHA256'] == {path: digest(raw) for path, raw in host_after.items()}
                assert proof['baselineSHA256'] == {path: digest(raw) for path, raw in host_before.items()}
                assert proof['results']['cases'] == 2400
                assert proof['completeStoreResult'].startswith('PASS: real POSIX file round trips')
                dependencies = {key: proof[key] for key in ('lz4HeaderSHA256', 'lz4Library')}
                if store_dependencies is not None:
                    assert dependencies == store_dependencies
                store_dependencies = dependencies
            proofs[str(path.relative_to(ROOT))] = dict(evidenceSHA256=raw_sha(path), harnessSHA256=proof['harnessSHA256'])

    gow = json.loads((EVIDENCE / 'gow3-source-and-proof-record.json').read_text())
    for name, values in gow['files'].items():
        assert raw_sha(source / name) == values['afterSHA256']
        assert raw_sha(baseline / name) == values['beforeSHA256']
    expected_gow = {Path(name).name: dict(value, finalProgram=not any(
        Path(name).name.startswith(prefix) for prefix in ('gow3-mfc-llvm-', 'gow3-mfc-full-plain', 'gow3-mfc-full-asan')))
        for name, value in proofs.items() if Path(name).name.startswith('gow3-')}
    assert gow['authenticatedProofs'] == expected_gow
    assert gow['finalProgramHashes'] == final_programs
    assert gow['historicalStagesAuthenticatedByFinalHarness'] == irq_scope
    identities = codegen_identity(source, baseline, manifest, old, gow)
    assert len(proofs) == 21
    result = dict(passed=True, canonicalPostimages=len(manifest['files_sha256']),
                  unchangedHistoricalPostimages=record['historical_postimages_unchanged'],
                  changedCoreFiles=sorted(changed), reverseDeltaMatchesBaseline=True,
                  authenticatedNativeModes=len(proofs), finalProgramModes=17,
                  reconstructedHistoricalMFCModes=4, completePOSIXStoreModes=2,
                  authenticatedProofs=proofs, codegenIdentity=identities,
                  historicalMFCStagesReconstructed=True, snrConsumedBodiesUnchanged=True,
                  restoreConsumedBodiesUnchangedAfterIRQ=True,
                  withdrawnExperimentsExcluded=True, rawShaderCacheRestoredToBaseline=True,
                  nativeOrCmakeReexecuted=False, physicalDeviceTested=False, gameplayMeasured=False,
                  externalLLVMBackendMaterialized=False,
                  recordedStoreExternalDependencies=store_dependencies,
                  storeExternalDependenciesReexecuted=False,
                  scope='Authenticate recorded host executions against exact final or reconstructed historical inputs; no new native execution, LLVM execution, device test or FPS claim.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
