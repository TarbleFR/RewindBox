"""Authenticate the BO2 delta and prepare the next source candidate on Apple.

The cf85c52 committed source receipt authenticates the previous 160 inputs.
Its eight device593 modes still require their first Apple execution; they run
alongside the six new BO2 modes, against two explicit reconstructed baselines.
Source verification and receipt verification never compile or replay CMake.
"""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
import neo_swap_core_pin_test as pin
import rpcs3_bo2_delta as delta
import rpcs3runtime_device593_core as previous

OUT = previous.OUT
PROOF = previous.PROOF
MANIFEST = previous.MANIFEST
ENTRY = previous.ENTRY
WORKFLOW = previous.WORKFLOW
GATE = '.github/diagnostics/rpcs3runtime_bo2_core.py'
PARENT_CONTRACT = 'docs/evidence/rpcs3-device593-20261029/committed-contract.json'
PARENT_SOURCE = 'cf85c52eb29f4f7fbff4e1daa15517073c8b25f6'
ROUTE = """    if 'runtime_bo2_followup_20261029' in manifest():
        from rpcs3runtime_bo2_core import main as bo2_main
        bo2_main(a)
        raise SystemExit
"""
TESTS = {
    'bo2-admission': ('test/rpcs3_bo2_compile_admission_test.py', ('plain', 'asan-ubsan', 'tsan')),
    'bo2-fragment-key': ('test/rpcs3_bo2_fragment_key_test.py', ('plain', 'asan-ubsan', 'tsan')),
}
TEST_INPUTS = {script for script, _ in TESTS.values()} | {
    'test/rpcs3_bo2_delta.py', delta.FIXTURE,
    'test/native/rpcs3_bo2_compile_admission.inc',
    'test/native/rpcs3_bo2_fragment_key.inc',
}
HOST_INPUTS = {
    'packages/neo_swap/ios/Classes/NeoSwapCompiler.mm',
    'packages/neo_swap/ios/Classes/NeoSwapCompilerAPI.h',
    'packages/neo_swap/ios/Classes/NeoSwapCompilerBudget.h',
    'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
}
WORKFLOW_PATHS = sorted(TEST_INPUTS | HOST_INPUTS | {GATE, PARENT_CONTRACT})
# Consumers of the fragment key are read by the new test but are unchanged.
# Files outside the canonical delta are authenticated as exact upstream blobs.
FRAGMENT_INPUTS = {
    'rpcs3/Emu/RSX/Program/RSXVertexProgram.h',
    'rpcs3/Emu/RSX/Program/RSXFragmentProgram.h',
    'rpcs3/Emu/RSX/Program/program_util.h',
    'rpcs3/util/fnv_hash.hpp', 'rpcs3/util/bit_set.hpp',
    'rpcs3/Emu/RSX/Program/FragmentProgramDecompiler.cpp',
    'rpcs3/Emu/RSX/Program/FragmentProgramDecompiler.h',
    'rpcs3/Emu/RSX/Program/ShaderParam.h',
    'rpcs3/Emu/RSX/Program/Assembler/FPOpcodes.cpp',
    'rpcs3/Emu/RSX/Program/Assembler/FPOpcodes.h',
    'rpcs3/Emu/RSX/Core/RSXDriverState.h',
    'rpcs3/Emu/RSX/Program/GLSLCommon.cpp',
    'rpcs3/Emu/RSX/VK/VKFragmentProgram.cpp',
    'rpcs3/Emu/RSX/rsx_cache.h',
    'rpcs3/Emu/RSX/RSXThread.cpp',
}
BASELINE_EXTRAS = {
    'rpcs3/ios/IOSCompileAdmission.h',
    'rpcs3/Emu/RSX/rsx_cache.h', 'rpcs3/Emu/RSX/RSXThread.cpp',
}
NATIVE_EXTRAS = previous.NATIVE_EXTRAS | BASELINE_EXTRAS | FRAGMENT_INPUTS | {'rpcs3/ios/NeoSwapCompilerAPI.h'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob_sha(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


def command(*args):
    return subprocess.check_output(args, cwd=ROOT)


@lru_cache(maxsize=None)
def baseline_bytes(path):
    return delta.committed_bytes(path)


def input_bytes(path):
    if path == PARENT_CONTRACT:
        raw = baseline_bytes(path)
        if (ROOT / path).exists():
            assert (ROOT / path).is_file() and not (ROOT / path).is_symlink(), path
            assert (ROOT / path).read_bytes() == raw, path
        return raw
    return previous.input_bytes(path)


def input_paths():
    return previous.input_paths() | TEST_INPUTS | HOST_INPUTS | {GATE, PARENT_CONTRACT}


def inputs():
    return {path: sha(input_bytes(path)) for path in sorted(input_paths())}


def committed_inputs(current):
    entries = command('git', 'ls-tree', '-r', '-z', '--full-tree', 'HEAD', '--', *sorted(current))
    tree = {}
    for entry in entries.split(b'\0'):
        if entry:
            metadata, path = entry.split(b'\t', 1)
            mode, kind, digest = metadata.decode().split()
            assert kind == 'blob' and mode in ('100644', '100755'), path
            tree[path.decode()] = digest
    assert set(tree) == set(current), 'Candidate inputs must be committed'
    for path in current:
        assert blob_sha(input_bytes(path)) == tree[path], path


def parent_receipt(parent):
    raw = input_bytes(PARENT_CONTRACT)
    prior = json.loads(raw)
    assert prior['passed'] is True and prior['sourceContractExecuted'] is True
    assert prior['kind'] == 'committed-device593-source-contract'
    assert prior['source'] == PARENT_SOURCE
    assert prior['tree'] == command('git', 'rev-parse', PARENT_SOURCE + '^{tree}').decode().strip()
    command('git', 'merge-base', '--is-ancestor', PARENT_SOURCE, delta.BASELINE)
    assert prior['committedInputCount'] == len(prior['inputSHA256']) == 160
    assert set(prior['inputSHA256']) == previous.input_paths()
    assert prior['canonicalPatchSHA256'] == parent['patch_sha256'] == delta.BASELINE_PATCH
    assert prior['fixtureSHA256'] == parent[previous.delta.KEY]['fixture_sha256']
    assert prior['nativeSourceSHA256'] == parent['files_sha256']
    assert len(prior['nativeSourceSHA256']) == 311
    for field in ('nativeTestsExecuted', 'compilerOrCMakeExecuted', 'appleCoreBuilt',
                  'physicalDeviceTested', 'gameplayMeasured', 'verificationWroteRemoteRef'):
        assert prior[field] is False, field
    receipt = dict(source=PARENT_SOURCE, baselineCommit=delta.BASELINE, inputCount=160,
                   committedContractSHA256=sha(raw), sourceContractReused=True,
                   priorNativeSuitesExecutedOnApple=False,
                   deliveredCore=prior['historicalReceipt'], archiveDownloaded=False)
    return receipt, prior


def legacy_tuple(manifest):
    # This is reconstruction metadata, not a call to the obsolete source gate.
    # The BO2 delta and the previous thirteen paths are authenticated disjoint.
    return manifest, manifest[previous.delta.KEY], json.loads(previous.baseline_bytes(MANIFEST))


def source_contract(source, require_committed=True):
    """Authenticate exact current inputs and both provenances, without compiling."""
    source = Path(source)
    authenticated = delta.authenticate(source)
    manifest, record, parent = authenticated
    assert len(record['tests']) == len(TEST_INPUTS) and set(record['tests']) == TEST_INPUTS
    command('git', 'merge-base', '--is-ancestor', delta.BASELINE, 'HEAD')
    historical, prior = parent_receipt(parent)
    current = inputs()
    allowed = {ENTRY, WORKFLOW, 'test/neo_swap_core_pin_test.py', MANIFEST,
               'build-utils/rpcs3/embedded-core.patch'}
    for path in allowed:
        assert sha(baseline_bytes(path)) == prior['inputSHA256'][path], path
    for path, digest in prior['inputSHA256'].items():
        if path not in allowed:
            assert current[path] == digest, path
    for path in HOST_INPUTS:
        expected = command('git', 'rev-parse', delta.BASELINE + ':' + path).decode().strip()
        assert blob_sha(input_bytes(path)) == expected, path
    old_pin = baseline_bytes('test/neo_swap_core_pin_test.py').decode()
    old_literal = "PATCH_SHA256 = '" + parent['patch_sha256'] + "'"
    assert old_pin.count(old_literal) == 1
    assert (ROOT / 'test/neo_swap_core_pin_test.py').read_text() == old_pin.replace(
        old_literal, "PATCH_SHA256 = '" + manifest['patch_sha256'] + "'")
    entry = (ROOT / ENTRY).read_text()
    assert entry.count(ROUTE) == 1
    assert entry.replace(ROUTE, '') == baseline_bytes(ENTRY).decode()
    assert entry.index(ROUTE) < entry.index(previous.ROUTE)
    anchor = "      - '.github/diagnostics/rpcs3runtime_device593_core.py'\n"
    old_workflow = baseline_bytes(WORKFLOW).decode()
    assert old_workflow.count(anchor) == 1
    added = ''.join("      - '" + path + "'\n" for path in WORKFLOW_PATHS)
    assert (ROOT / WORKFLOW).read_text() == old_workflow.replace(anchor, anchor + added)
    if require_committed:
        committed_inputs(current)
    extras = {}
    for path in sorted(NATIVE_EXTRAS):
        raw = (source / path).read_bytes()
        if path in manifest['files_sha256']:
            assert delta.normalized_bytes_sha(raw) == manifest['files_sha256'][path], path
        else:
            expected = command('git', '-C', str(source), 'rev-parse', manifest['upstream_commit'] + ':' + path).decode().strip()
            assert blob_sha(raw) == expected, path
        extras[path] = sha(raw)
    for path, digest in prior['supplementalNativeSHA256'].items():
        assert extras[path] == digest, path
    assert extras['rpcs3/ios/NeoSwapCompilerAPI.h'] == current['packages/neo_swap/ios/Classes/NeoSwapCompilerAPI.h']
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert len(exports) == len(set(exports)) == 88
    delivered = json.loads(previous.input_bytes(previous.HISTORY_DIR + 'runtime592-proof.json'))
    assert exports == delivered['exported_symbols']
    codegen = previous.codegen_receipt(source, legacy_tuple(manifest))
    assert codegen == prior['codegenProof']
    assert codegen['codegen'] == record['codegen']
    return authenticated, current, historical, codegen, extras


def all_tests():
    return {**previous.TESTS, **TESTS}


def baselines(source, directory, authenticated):
    before_bo2 = delta.reconstruct(source, directory / 'beforeBO2', authenticated, BASELINE_EXTRAS)
    before_593 = previous.delta.reconstruct(source, directory / 'before593',
        legacy_tuple(authenticated[0]), previous.BASELINE_EXTRAS)
    return {'beforeBO2': before_bo2, 'before593': before_593}


def runner_command(name, mode, source, roots, compiler):
    if name in previous.TESTS:
        return previous.runner_command(name, mode, source, roots['before593'], compiler)
    script = TESTS[name][0]
    argv = ['python3', script]
    if name == 'bo2-admission':
        argv += ['--source', str(source)]
    else:
        argv += [str(source)]
    argv += ['--baseline', str(roots['beforeBO2']), '--compiler', compiler]
    if name == 'bo2-admission':
        argv += ['--mode', mode]
    elif mode != 'plain':
        argv += ['--sanitizer', 'address,undefined' if mode == 'asan-ubsan' else 'thread']
    option = '--output' if name == 'bo2-admission' else '--report'
    return argv + [option, str(OUT / (name + '-' + mode + '-result.json'))]


def expected_results(source, roots):
    import rpcs3_bo2_compile_admission_test as admission
    import rpcs3_bo2_fragment_key_test as fragment
    before = roots['beforeBO2']
    code, host_blob = admission.harness(source, before, ROOT / admission.HOST)
    result = previous.expected_results(source, roots['before593'])
    result['bo2-admission'] = dict(
        sourceSHA256=sha((source / admission.SOURCE).read_bytes()),
        baselineSHA256=sha((before / admission.SOURCE).read_bytes()),
        headerSHA256=sha((source / admission.HEADER).read_bytes()),
        harnessSHA256=sha(code.encode()), adapterSHA256=sha(admission.ADAPTER.read_bytes()),
        hostInputSHA256={p: sha((ROOT / p).read_bytes()) for p in (admission.HOST, *admission.HOST_HEADERS)},
        hostWrapperGitBlob=host_blob)
    assert set(fragment.SOURCE) == delta.PATHS - {admission.SOURCE}
    assert set(fragment.SUPPORT) == FRAGMENT_INPUTS and len(fragment.SUPPORT) == len(FRAGMENT_INPUTS)
    assert set(fragment.BASELINE) == set(fragment.SOURCE) | {
        'rpcs3/Emu/RSX/rsx_cache.h', 'rpcs3/Emu/RSX/RSXThread.cpp'}
    result['bo2-fragment-key'] = dict(
        harnessSHA256=sha(fragment.harness(source, before).encode()),
        sourceSHA256={p: delta.normalized_bytes_sha((source / p).read_bytes())
                      for p in fragment.SOURCE + fragment.SUPPORT},
        baselineSHA256={p: delta.normalized_bytes_sha((before / p).read_bytes()) for p in fragment.BASELINE},
        adapterSHA256=delta.normalized_bytes_sha(fragment.ADAPTER.read_bytes()))
    return result


def validate_result(name, mode, payload, expected, compiler):
    if name in previous.TESTS:
        previous.validate_result(name, mode, payload, expected, compiler)
        return
    assert payload['passed'] is True and payload['compiler'] == compiler
    assert payload['assertionsActive'] is True
    assert re.search(r'clang version 22\.', compiler)
    flags = payload['compilerFlags']
    assert '-UNDEBUG' in flags and not any(flag.startswith('-DNDEBUG') for flag in flags)
    assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
    assert ('-fsanitize=thread' in flags) == (mode == 'tsan')
    for key, value in expected[name].items():
        assert payload[key] == value, (name, key)
    assert payload['physicalDeviceTested'] is False and payload['gameplayMeasured'] is False
    if name == 'bo2-admission':
        assert payload['mode'] == mode and payload['assertionsActive'] is True
        assert payload['forcedGapCasesPerVersion'] == 32
        assert payload['baselineLostNotifications'] == 16 and payload['candidateLostNotifications'] == 0
        assert payload['fallbackLostNotifications'] == [0, 0]
        assert payload['cancellationCasesPerVersion'] == 4
        assert payload['concurrentAdmissionsPerVersion'] == 768 and payload['admissionLimit'] == 3
        assert len(payload['maximumConcurrentWork']) == 2
        assert all(1 <= value <= 3 for value in payload['maximumConcurrentWork'])
        assert payload['productionTimeoutMilliseconds'] == 20
        assert payload['timingThresholdAssertions'] is False
        assert payload['onlyReleaseCriticalSectionChanged'] is True
        assert payload['baselineSourceMutationApplied'] is False and payload['leakSanitizer'] is False
    else:
        assert payload['sanitizer'] == {'plain': None, 'asan-ubsan': 'address,undefined', 'tsan': 'thread'}[mode]
        assert payload['host'] == 'arm64' and payload['MetalCompiled'] is False
        assert '-DRPCS3_IOS' in flags and '-DARCH_ARM64' in flags
        expected_counts = dict(equivalentGeneratorVariants=5400, liveVariantsRemainDifferent=4320,
            fallbackCases=49, parserCases=28, uniqueGlsl=67,
            variantTraceBeforeCompiles=2048, variantTraceAfterCompiles=1,
            pendingPreloads=9, concurrentReadyQueries=8000)
        result = payload['results']
        for key, value in expected_counts.items():
            assert result[key] == value, key
        assert result['beforeExposedBorrowedKey'] is True and result['afterExposedBorrowedKey'] is False
        for key in ('compileOutsideLock', 'hintLifecycle', 'ownershipRehashClear', 'analysisUnchanged'):
            assert result[key] is True, key
        assert set(result) == set(expected_counts) | {
            'beforeExposedBorrowedKey', 'afterExposedBorrowedKey', 'compileOutsideLock',
            'hintLifecycle', 'ownershipRehashClear', 'analysisUnchanged'}


def prepare(source):
    assert platform.system() == 'Darwin' and platform.machine() == 'arm64'
    authenticated, current, historical, codegen, extras = source_contract(source)
    manifest, record, _ = authenticated
    OUT.mkdir(parents=True, exist_ok=True)
    compiler_command = os.environ['CXX']
    compiler = command(*shlex.split(compiler_command), '--version').decode().splitlines()[0]
    assert re.search(r'clang version 22\.', compiler)
    sdk = os.environ['HOST_MACOS_SDK']
    assert Path(sdk).is_dir()
    env = dict(os.environ, SDKROOT=sdk, ASAN_OPTIONS='detect_leaks=0',
               UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1')
    receipt = dict(schema=1, kind=delta.KEY, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
                   source_root=str(source), input_sha256=current, native_source_sha256=manifest['files_sha256'],
                   supplemental_native_sha256=extras, fixture_sha256=record['fixture_sha256'],
                   host=dict(system='Darwin', machine='arm64', compiler=compiler, compilerCommand=compiler_command),
                   baseline_commits=dict(beforeBO2=delta.BASELINE, before593=previous.delta.BASELINE),
                   exported_symbols=sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split()),
                   physical_device_tested=False, gameplay_measured=False, all_tests_passed=False,
                   historical=historical, codegen_source_proof=codegen, tests={})
    PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='runtime-bo2-before-') as temp:
        roots = baselines(source, Path(temp), authenticated)
        receipt['baseline_roots'] = {key: str(value) for key, value in roots.items()}
        expected = expected_results(source, roots)
        for name, (_, modes) in all_tests().items():
            for mode in modes:
                key = name + '-' + mode
                report = OUT / (key + '-result.json')
                report.unlink(missing_ok=True)
                argv = runner_command(name, mode, source, roots, compiler_command)
                run = subprocess.run(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, timeout=300)
                (OUT / (key + '-output.txt')).write_bytes(run.stdout)
                print(run.stdout.decode(errors='replace'), flush=True)
                state = dict(command=argv, returncode=run.returncode, output_sha256=sha(run.stdout), passed=False)
                receipt['tests'][key] = state
                PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
                assert run.returncode == 0 and report.is_file(), key
                validate_result(name, mode, json.loads(report.read_bytes()), expected, compiler)
                state.update(passed=True, report_sha256=sha(report.read_bytes()))
    assert current == inputs(), 'Build or test inputs changed during preflight'
    receipt['all_tests_passed'] = True
    PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS fourteen Apple ARM64 modes: eight pending device593 and six BO2 checks; real GCD required, CMake proof reused; no device or FPS measurement')


def verify(path, source=None):
    proof = json.loads(path.read_bytes())
    assert proof['schema'] == 1 and proof['kind'] == delta.KEY
    source = Path(source or proof['source_root'])
    authenticated, current, historical, codegen, extras = source_contract(source)
    manifest, record, _ = authenticated
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['input_sha256'] == current and proof['native_source_sha256'] == manifest['files_sha256']
    assert proof['supplemental_native_sha256'] == extras and proof['fixture_sha256'] == record['fixture_sha256']
    assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
    assert proof['gameplay_measured'] is False
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    assert re.search(r'clang version 22\.', proof['host']['compiler'])
    assert proof['baseline_commits'] == dict(beforeBO2=delta.BASELINE, before593=previous.delta.BASELINE)
    assert set(proof['baseline_roots']) == {'beforeBO2', 'before593'}
    assert proof['baseline_roots']['beforeBO2'] != proof['baseline_roots']['before593']
    assert proof['exported_symbols'] == sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert proof['historical'] == historical and proof['codegen_source_proof'] == codegen
    assert set(proof['tests']) == {name + '-' + mode for name, (_, modes) in all_tests().items() for mode in modes}
    with tempfile.TemporaryDirectory(prefix='runtime-bo2-recheck-') as temp:
        roots = baselines(source, Path(temp), authenticated)
        expected = expected_results(source, roots)
        recorded_roots = {key: Path(value) for key, value in proof['baseline_roots'].items()}
        for name, (_, modes) in all_tests().items():
            for mode in modes:
                key = name + '-' + mode
                state = proof['tests'][key]
                assert state['passed'] is True and state['returncode'] == 0
                assert state['command'] == runner_command(name, mode, Path(proof['source_root']),
                    recorded_roots, proof['host']['compilerCommand'])
                raw = (OUT / (key + '-result.json')).read_bytes()
                assert sha(raw) == state['report_sha256']
                assert sha((OUT / (key + '-output.txt')).read_bytes()) == state['output_sha256']
                validate_result(name, mode, json.loads(raw), expected, proof['host']['compiler'])
    return proof


def identity(directory):
    proof = verify(PROOF)
    manifest = json.loads((ROOT / MANIFEST).read_bytes())
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    from verify_ipa import macho
    from rpcs3runtime592_core import MARKERS
    core = directory / 'libRPCS3Core.dylib'
    data = core.read_bytes()
    image = macho(data)
    assert image['platform'] == 2
    assert len(image['definedSymbols']) == len(proof['exported_symbols']) == 88
    assert set(image['definedSymbols']) == set(proof['exported_symbols'])
    assert all(marker in data for marker in MARKERS)
    log = (OUT / 'build.log').read_text()
    actual = {kind: re.findall(r'NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log)
              for kind in ('PPU', 'SPU')}
    assert actual == {kind: [value] for kind, value in manifest[delta.KEY]['codegen'].items()}
    assert all(hook in log for hook in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'))
    archive = manifest['cell587']['moltenvk_archive']
    assert archive['input_sha256'] + ' -> ' + archive['patched_sha256'] in log
    assert not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(command('nm', '-u', str(core)).decode().split())
    assert (directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == manifest['upstream_commit']
    assert int((directory / 'RPCS3_IOS_ABI.txt').read_text().strip()) == 30
    result = dict(schema_version=1, type='rpcs3-ios-runtime-source-candidate', host_commit=proof['source'],
                  native_source_commit=proof['source'], source_commit=manifest['upstream_commit'],
                  sha256=sha(data), abi_version=30, source_patch_sha256=manifest['patch_sha256'],
                  core_input_sha256=pin.core_input_hashes(), runtime_followup_input_sha256=proof['input_sha256'],
                  native_source_sha256=manifest['files_sha256'], exported_symbols=proof['exported_symbols'],
                  physical_device_tested=False, gameplay_measured=False, public_release=False)
    for target in (directory, OUT):
        (target / 'identity.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS iPhone source candidate: fourteen ARM64 modes, ABI30/88 exports and unchanged PPU/SPU identities; no delivery number or physical-device claim')


def main(args):
    if args.write_core_identity:
        identity(args.write_core_identity)
    elif args.verify_reuse:
        verify(args.verify_reuse, args.source)
    elif args.source:
        prepare(args.source.resolve())
    else:
        raise ValueError('The BO2 source gate requires --source, --verify-reuse or --write-core-identity')
