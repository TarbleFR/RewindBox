"""Authenticate the BO2 recurring-cost delta without replaying verified history.

The eight device593 and six shader follow-up modes still await Apple execution.
Their unchanged production bodies and exact source receipts are reused locally;
the next explicitly requested Core also runs the new targeted native modes.
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
import rpcs3_bo2_warm_delta as delta
import rpcs3runtime_bo2_core as previous

OUT, PROOF = previous.OUT, previous.PROOF
MANIFEST, ENTRY, WORKFLOW = previous.MANIFEST, previous.ENTRY, previous.WORKFLOW
GATE = '.github/diagnostics/rpcs3runtime_bo2_warm_core.py'
PARENT_CONTRACT = 'docs/evidence/rpcs3-bo2-20261029/committed-contract.json'
PARENT_SOURCE = 'a732853dd445426bb6fe780c1e84a3fab452fcde'
ROUTE = """    if 'runtime_bo2_warm_20261029' in manifest():
        from rpcs3runtime_bo2_warm_core import main as warm_main
        warm_main(a)
        raise SystemExit
"""
TESTS = {
    'texture-address': ('test/rpcs3_texture_address_index_test.py', ('plain', 'asan-ubsan')),
    'viewport-scissor': ('test/rpcs3_viewport_scissor_test.py', ('plain', 'asan-ubsan')),
    'submit-wake': ('test/rpcs3_submit_wake_test.py', ('plain', 'tsan')),
}
REUSED_TEST_INPUTS = {
    'test/rpcs3_dynamic_state_retention_test.py',
    'test/native/rpcs3_dynamic_state_retention.inc',
}
TEST_INPUTS = {script for script, _ in TESTS.values()} | REUSED_TEST_INPUTS | {
    'test/rpcs3_bo2_warm_delta.py', delta.FIXTURE,
    'test/native/rpcs3_texture_address_index.inc',
    'test/native/rpcs3_viewport_scissor.inc',
    'test/native/rpcs3_submit_wake.inc',
}
WORKFLOW_PATHS = sorted((TEST_INPUTS - REUSED_TEST_INPUTS) | {GATE, PARENT_CONTRACT})
NATIVE_EXTRAS = previous.NATIVE_EXTRAS | delta.PATHS | {
    'Utilities/address_range.h', 'rpcs3/util/atomic.hpp',
    'rpcs3/Emu/RSX/VK/VKCommandStream.h',
    'rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp', 'rpcs3/Emu/RSX/VK/VKProgramPipeline.h',
}
BASELINE_EXTRAS = (previous.delta.PATHS | previous.BASELINE_EXTRAS |
                   previous.previous.delta.PATHS | previous.previous.BASELINE_EXTRAS |
                   {'rpcs3/Emu/RSX/Common/texture_cache.cpp', 'Utilities/address_range.h',
                    'rpcs3/util/atomic.hpp', 'rpcs3/Emu/RSX/VK/VKCommandStream.h',
                    'rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp', 'rpcs3/Emu/RSX/VK/VKProgramPipeline.h'})

sha = previous.sha
blob_sha = previous.blob_sha
command = previous.command


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
    return previous.input_paths() | TEST_INPUTS | {GATE, PARENT_CONTRACT}


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
    assert prior['kind'] == 'committed-bo2-source-contract'
    assert prior['source'] == PARENT_SOURCE
    assert prior['tree'] == command('git', 'rev-parse', PARENT_SOURCE + '^{tree}').decode().strip()
    command('git', 'merge-base', '--is-ancestor', PARENT_SOURCE, delta.BASELINE)
    assert prior['committedInputCount'] == len(prior['inputSHA256']) == 170
    assert set(prior['inputSHA256']) == previous.input_paths()
    assert prior['canonicalPatchSHA256'] == parent['patch_sha256'] == delta.BASELINE_PATCH
    assert prior['fixtureSHA256'] == parent[previous.delta.KEY]['fixture_sha256']
    assert prior['nativeSourceSHA256'] == parent['files_sha256']
    assert len(prior['nativeSourceSHA256']) == 311
    for field in ('nativeTestsExecuted', 'compilerOrCMakeExecuted', 'appleCoreBuilt',
                  'physicalDeviceTested', 'gameplayMeasured', 'verificationWroteRemoteRef'):
        assert prior[field] is False, field
    historical = dict(source=PARENT_SOURCE, baselineCommit=delta.BASELINE, inputCount=170,
                      committedContractSHA256=sha(raw), sourceContractReused=True,
                      priorNativeSuitesExecutedOnApple=False,
                      deliveredCore=prior['historical']['deliveredCore'], archiveDownloaded=False)
    return historical, prior


def baselines(source, directory, authenticated):
    """Reverse the newest overlapping edits first, then the older fixtures."""
    before_warm = delta.reconstruct(source, directory / 'beforeWarm', authenticated, BASELINE_EXTRAS)
    parent = authenticated[2]
    prior_tuple = (parent, parent[previous.delta.KEY], json.loads(previous.baseline_bytes(MANIFEST)))
    roots = previous.baselines(before_warm, directory, prior_tuple)
    return dict(beforeWarm=before_warm, **roots)


def preserved_harnesses(source, roots, prior):
    """Old production extractions must remain identical; only file hashes move."""
    now = previous.expected_results(source, roots)
    assert set(now) == set(prior['expectedResults'])
    changed_source_hashes = {'rsx-write-sampler': 'sourceSHA256', 'submit-lifetime': 'sourceInputs'}
    for name, expected in now.items():
        old = dict(prior['expectedResults'][name])
        if name in changed_source_hashes:
            key = changed_source_hashes[name]
            assert set(old[key]) == set(expected[key]), name
            for path, digest in old[key].items():
                if path in delta.PATHS:
                    assert sha((roots['beforeWarm'] / path).read_bytes()) == digest, path
                else:
                    assert expected[key][path] == digest, path
            old[key] = expected[key]
        assert expected == old, name + ' changed a previously verified production harness'
    return now


def source_contract(source, require_committed=True):
    """Authenticate sources and prior receipts; execute no native code or CMake."""
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
    for path in REUSED_TEST_INPUTS:
        assert input_bytes(path) == baseline_bytes(path), path
    old_pin = baseline_bytes('test/neo_swap_core_pin_test.py').decode()
    old_literal = "PATCH_SHA256 = '" + parent['patch_sha256'] + "'"
    assert old_pin.count(old_literal) == 1
    assert (ROOT / 'test/neo_swap_core_pin_test.py').read_text() == old_pin.replace(
        old_literal, "PATCH_SHA256 = '" + manifest['patch_sha256'] + "'")
    entry = (ROOT / ENTRY).read_text()
    assert entry.count(ROUTE) == 1
    assert entry.replace(ROUTE, '') == baseline_bytes(ENTRY).decode()
    assert entry.index(ROUTE) < entry.index(previous.ROUTE)
    anchor = "      - '.github/diagnostics/rpcs3runtime_bo2_core.py'\n"
    old_workflow = baseline_bytes(WORKFLOW).decode()
    assert old_workflow.count(anchor) == 1
    for path in REUSED_TEST_INPUTS:
        assert "      - '" + path + "'\n" in old_workflow, path
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
    with tempfile.TemporaryDirectory(prefix='bo2-warm-provenance-') as temp:
        roots = baselines(source, Path(temp), authenticated)
        for path, digest in prior['supplementalNativeSHA256'].items():
            tree = roots['beforeWarm'] if path in delta.PATHS else source
            assert sha((tree / path).read_bytes()) == digest, path
        preserved_harnesses(source, roots, prior)
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert len(exports) == len(set(exports)) == 88
    delivered = json.loads(previous.previous.input_bytes(previous.previous.HISTORY_DIR + 'runtime592-proof.json'))
    assert exports == delivered['exported_symbols']
    codegen = previous.previous.codegen_receipt(source, previous.legacy_tuple(parent))
    assert codegen == prior['codegenProof']
    assert codegen['codegen'] == record['codegen']
    return authenticated, current, historical, codegen, extras


def all_tests():
    return {**previous.all_tests(), **TESTS}


def runner_command(name, mode, source, roots, compiler):
    if name in previous.all_tests():
        return previous.runner_command(name, mode, source, roots, compiler)
    argv = ['python3', TESTS[name][0], str(source), '--baseline', str(roots['beforeWarm']),
            '--compiler', compiler]
    if mode != 'plain':
        argv += ['--sanitizer', 'address,undefined' if mode == 'asan-ubsan' else 'thread']
    if name == 'texture-address' and mode == 'plain':
        argv += ['--benchmark']
    return argv + ['--report', str(OUT / (name + '-' + mode + '-result.json'))]


def expected_results(source, roots):
    import rpcs3_texture_address_index_test as texture
    import rpcs3_viewport_scissor_test as viewport
    import rpcs3_submit_wake_test as wake
    before = roots['beforeWarm']
    result = previous.expected_results(source, roots)
    assert set(texture.SOURCE) == {
        'rpcs3/Emu/RSX/Common/texture_cache.h', 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'}
    assert set(texture.SUPPORT) == {'rpcs3/Emu/RSX/Common/texture_cache.cpp', 'Utilities/address_range.h'}
    result['texture-address'] = dict(
        sourceSHA256={p: delta.normalized_sha(source / p) for p in texture.SOURCE + texture.SUPPORT},
        baselineSHA256={p: delta.normalized_sha(before / p) for p in texture.SOURCE},
        harnessSHA256=sha(texture.harness(source, before).encode()),
        adapterSHA256=delta.normalized_sha(texture.ADAPTER))
    result['viewport-scissor'] = viewport.expected(source, before)
    result['submit-wake'] = wake.expected(source, before)
    return result


def validate_delta_result(name, mode, payload, expected):
    """Validate new native evidence independently of the Apple host envelope."""
    assert name in TESTS and mode in TESTS[name][1]
    assert payload['passed'] is True and payload['compiler']
    assert payload['assertionsActive'] is True
    flags = payload['compilerFlags']
    assert '-UNDEBUG' in flags and not any(flag.startswith('-DNDEBUG') for flag in flags)
    assert '-DRPCS3_IOS' in flags
    assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
    assert ('-fsanitize=thread' in flags) == (mode == 'tsan')
    if mode == 'plain':
        assert payload['sanitizer'] in (None, '')
    else:
        assert payload['sanitizer'] == ('address,undefined' if mode == 'asan-ubsan' else 'thread')
    for key, value in expected[name].items():
        assert payload[key] == value, (name, key)
    assert payload['physicalDeviceTested'] is False and payload['gameplayMeasured'] is False
    result = payload['results']
    if name == 'texture-address':
        counts = dict(queries=22753, mutations=8618,
                      baselineDirtyPredicateCalls=4714944, indexedDirtyPredicateCalls=26629)
        for key, value in counts.items():
            assert result[key] == value, key
        for key in ('sameFirstMatch', 'sameValidationOrder', 'sameOverlapMembership',
                    'clearAndResourceLessRetags', 'sectionLayoutUnchanged', 'presentationWalkUnchanged'):
            assert result[key] is True, key
        if mode == 'plain':
            assert [item['sections'] for item in result['benchmarks']] == [8, 16, 17, 64, 256, 1024]
            assert all(item['lookupAllocations'] == 0 for item in result['benchmarks'])
        else:
            assert 'benchmarks' not in result
    elif name == 'submit-wake':
        assert result == dict(passed=True, assertionsActive=True,
            sequenceCalls=13, sequenceBaselineWakes=13, sequenceCandidateWakes=4,
            lateCompletionCalls=1024, lateBaselineWakes=1024, lateCandidateWakes=128,
            casRetryCases=2, wakeBoundaryCases=4, explicitDrainCases=2,
            concurrentProducerCallsPerVersion=16384, abortDrainCases=2)
    else:
        assert result == dict(passed=True, assertionsActive=True,
            maskCases=514, identicalDraws=10000,
            baselineViewportCommands=10000, candidateViewportCommands=1,
            baselineScissorCommands=10000, candidateScissorCommands=1,
            bitPatternCases=56, staticTransitionCases=3, overlayReturnCases=3,
            recordingReuseCases=3, randomDraws=20000,
            randomBaselineViewportCommands=20000, randomCandidateViewportCommands=9718,
            randomBaselineScissorCommands=20000, randomCandidateScissorCommands=9897,
            boundsAndDepthIndependent=True, independentBuffers=True,
            computeRetainsGraphics=True, unknownMaskInvalidates=True, lifetimeTraceEqual=True)


def validate_result(name, mode, payload, expected, compiler):
    if name in previous.all_tests():
        previous.validate_result(name, mode, payload, expected, compiler)
        return
    assert payload['compiler'] == compiler and re.search(r'clang version 22\.', compiler)
    validate_delta_result(name, mode, payload, expected)


def baseline_commits():
    return dict(beforeWarm=delta.BASELINE, beforeBO2=previous.delta.BASELINE,
                before593=previous.previous.delta.BASELINE)


def prepare(source, *, gate=None):
    """Run the pending Apple checks using an explicitly supplied delta gate."""
    gate = sys.modules[__name__] if gate is None else gate
    assert platform.system() == 'Darwin' and platform.machine() == 'arm64'
    authenticated, current, historical, codegen, extras = gate.source_contract(source)
    manifest, record, _ = authenticated
    OUT.mkdir(parents=True, exist_ok=True)
    compiler_command = os.environ['CXX']
    compiler = command(*shlex.split(compiler_command), '--version').decode().splitlines()[0]
    assert re.search(r'clang version 22\.', compiler)
    sdk = os.environ['HOST_MACOS_SDK']
    assert Path(sdk).is_dir()
    env = dict(os.environ, SDKROOT=sdk, ASAN_OPTIONS='detect_leaks=0',
               UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1')
    receipt = dict(schema=1, kind=gate.delta.KEY, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
                   source_root=str(source), input_sha256=current, native_source_sha256=manifest['files_sha256'],
                   supplemental_native_sha256=extras, fixture_sha256=record['fixture_sha256'],
                   host=dict(system='Darwin', machine='arm64', compiler=compiler, compilerCommand=compiler_command),
                   baseline_commits=gate.baseline_commits(),
                   exported_symbols=sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split()),
                   physical_device_tested=False, gameplay_measured=False, all_tests_passed=False,
                   historical=historical, codegen_source_proof=codegen, tests={})
    PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='runtime-bo2-warm-before-') as temp:
        roots = gate.baselines(source, Path(temp), authenticated)
        receipt['baseline_roots'] = {key: str(value) for key, value in roots.items()}
        expected = gate.expected_results(source, roots)
        for name, (_, modes) in gate.all_tests().items():
            for mode in modes:
                key = name + '-' + mode
                reuse = getattr(gate, 'reuse_result', None)
                retained = reuse(name, mode, receipt, expected, compiler) if reuse else None
                if retained is not None:
                    receipt['tests'][key] = retained
                    PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
                    print(f'REUSE {key} from Apple run {retained["reused_from"]["run_id"]}; not executed again', flush=True)
                    continue
                report = OUT / (key + '-result.json')
                report.unlink(missing_ok=True)
                argv = gate.runner_command(name, mode, source, roots, compiler_command)
                run = subprocess.run(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, timeout=300)
                (OUT / (key + '-output.txt')).write_bytes(run.stdout)
                print(run.stdout.decode(errors='replace'), flush=True)
                state = dict(command=argv, returncode=run.returncode, output_sha256=sha(run.stdout), passed=False)
                receipt['tests'][key] = state
                PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
                assert run.returncode == 0 and report.is_file(), key
                gate.validate_result(name, mode, json.loads(report.read_bytes()), expected, compiler)
                state.update(passed=True, report_sha256=sha(report.read_bytes()))
    assert current == gate.inputs(), 'Build or test inputs changed during preflight'
    receipt['all_tests_passed'] = True
    PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
    modes = sum(len(modes) for _, modes in gate.all_tests().values())
    reused = sum('reused_from' in state for state in receipt['tests'].values())
    print(f'PASS {modes} Apple ARM64 modes ({modes - reused} executed, {reused} reused); GCD required, CMake proof reused; no device or FPS measurement')


def verify(path, source=None, *, gate=None):
    gate = sys.modules[__name__] if gate is None else gate
    proof = json.loads(path.read_bytes())
    assert proof['schema'] == 1 and proof['kind'] == gate.delta.KEY
    source = Path(source or proof['source_root'])
    authenticated, current, historical, codegen, extras = gate.source_contract(source)
    manifest, record, _ = authenticated
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['input_sha256'] == current and proof['native_source_sha256'] == manifest['files_sha256']
    assert proof['supplemental_native_sha256'] == extras and proof['fixture_sha256'] == record['fixture_sha256']
    assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
    assert proof['gameplay_measured'] is False
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    assert re.search(r'clang version 22\.', proof['host']['compiler'])
    assert proof['baseline_commits'] == gate.baseline_commits()
    assert set(proof['baseline_roots']) == set(gate.baseline_commits())
    assert len(set(proof['baseline_roots'].values())) == len(gate.baseline_commits())
    assert proof['exported_symbols'] == sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert proof['historical'] == historical and proof['codegen_source_proof'] == codegen
    assert set(proof['tests']) == {name + '-' + mode for name, (_, modes) in gate.all_tests().items() for mode in modes}
    with tempfile.TemporaryDirectory(prefix='runtime-bo2-warm-recheck-') as temp:
        roots = gate.baselines(source, Path(temp), authenticated)
        expected = gate.expected_results(source, roots)
        recorded_roots = {key: Path(value) for key, value in proof['baseline_roots'].items()}
        for name, (_, modes) in gate.all_tests().items():
            for mode in modes:
                key = name + '-' + mode
                state = proof['tests'][key]
                assert state['passed'] is True and state['returncode'] == 0
                if 'reused_from' in state:
                    reuse = getattr(gate, 'verify_reused_result', None)
                    assert reuse is not None, 'This gate has no authenticated partial-result reuse'
                    reuse(name, mode, state, proof, expected)
                else:
                    assert state['command'] == gate.runner_command(name, mode, Path(proof['source_root']),
                        recorded_roots, proof['host']['compilerCommand'])
                raw = (OUT / (key + '-result.json')).read_bytes()
                assert sha(raw) == state['report_sha256']
                assert sha((OUT / (key + '-output.txt')).read_bytes()) == state['output_sha256']
                gate.validate_result(name, mode, json.loads(raw), expected, proof['host']['compiler'])
    return proof


def identity(directory, *, gate=None):
    gate = sys.modules[__name__] if gate is None else gate
    proof = verify(PROOF, gate=gate)
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
    assert actual == {kind: [value] for kind, value in manifest[gate.delta.KEY]['codegen'].items()}
    assert all(hook in log for hook in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'))
    archive = manifest['cell587']['moltenvk_archive']
    assert archive['input_sha256'] + ' -> ' + archive['patched_sha256'] in log
    assert not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(command('nm', '-u', str(core)).decode().split())
    assert (directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == manifest['upstream_commit']
    assert int((directory / 'RPCS3_IOS_ABI.txt').read_text().strip()) == 30
    result = dict(schema_version=1, type='rpcs3-ios-runtime-source-candidate', host_commit=proof['source'],
                  native_source_commit=proof['source'], source_commit=manifest['upstream_commit'],
                  sha256=sha(data), abi_version=30, source_patch_sha256=manifest['patch_sha256'],
                  core_input_sha256=previous.pin.core_input_hashes(), runtime_followup_input_sha256=proof['input_sha256'],
                  native_source_sha256=manifest['files_sha256'], exported_symbols=proof['exported_symbols'],
                  physical_device_tested=False, gameplay_measured=False, public_release=False)
    for target in (directory, OUT):
        (target / 'identity.json').write_text(json.dumps(result, indent=2) + '\n')
    modes = sum(len(modes) for _, modes in gate.all_tests().values())
    print(f'PASS iPhone source candidate: {modes} ARM64 modes, ABI30/88 exports and unchanged PPU/SPU identities; no delivery number or physical-device claim')


def main(args):
    if args.write_core_identity:
        identity(args.write_core_identity)
    elif args.verify_reuse:
        verify(args.verify_reuse, args.source)
    elif args.source:
        prepare(args.source.resolve())
    else:
        raise ValueError('The BO2 recurring-cost gate requires --source, --verify-reuse or --write-core-identity')
