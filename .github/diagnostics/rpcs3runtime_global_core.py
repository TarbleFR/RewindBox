"""Authenticate the global runtime delta; run only changed or pending programs.

The device594 follow-up's ten modes still await Apple execution. Sixteen
previously successful Apple modes retain identical programs; the viewport and
scoped-write programs change and their four modes are executed again. No Core,
IPA or release is scheduled by merely recording these source changes.
"""
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_global_delta as delta
import rpcs3runtime_device594_core as previous
import rpcs3runtime_bo2_warm_core as pipeline
import rpcs3runtime_global_resume as first_resume
import rpcs3runtime_global_resume2 as resume

OUT, PROOF = previous.OUT, previous.PROOF
MANIFEST, ENTRY, WORKFLOW = previous.MANIFEST, previous.ENTRY, previous.WORKFLOW
GATE = '.github/diagnostics/rpcs3runtime_global_core.py'
PIPELINE = '.github/diagnostics/rpcs3runtime_bo2_warm_core.py'
ORIGINAL_LIFECYCLE_SCRIPT_SHA256 = '5dcd5e352bcf6ff73705efea3b8f8f29bbfb4222aa59963808615468bb343c96'
APPLE_LIFECYCLE_SCRIPT_SHA256 = '34ccd7c55e304588f37652277bc13ad641fb8e51e372562ce4cd7906e94db623'
APPLE_RESUME_PIPELINE_SHA256 = '3c7df8082d7d838764daa651c56ec104d2996d26d47fe07c06672ef7ea801cc7'
APPLE_LIFECYCLE_PROGRAMS = {
    'baseline': '12f54d6a578127105a00de0fe3dde44f09f13288547948da2e1bc9e5832dadc7',
    'candidate': '09d247362b3ee392dfbf472781aa68f3bcdbf0eeef1870ea7b8597e6c81cb8c0',
}
PARENT_CONTRACT = 'docs/evidence/rpcs3-device594-20261029/committed-contract.json'
PARENT_SOURCE = '7f8391ddf64f0d6f2e6c416255b36c9e8d5e75da'
PARENT_CONTRACT_SHA = 'abcec31d855f84f40369c23b1a4b8663bc7cf4b1967a32c6c243c6408ceb266a'
CODEGEN_REPORT = 'docs/evidence/rpcs3-global-20261029/spu-cache-identity.json'
ROUTE = """    if 'runtime_global_20261029' in manifest():
        from rpcs3runtime_global_core import main as global_main
        global_main(a)
        raise SystemExit
"""
TESTS = {
    'spu-mfc': ('test/rpcs3_spu_mfc_runtime_test.py', ('plain', 'asan-ubsan')),
    'spu-timer': ('test/rpcs3_spu_timer_runtime_test.py', ('plain', 'asan-ubsan')),
    'descriptor-bind': ('test/rpcs3_descriptor_bind_cache_test.py', ('plain', 'asan-ubsan')),
    'texture-hash-reuse': ('test/rpcs3_texture_hash_reuse_test.py', ('plain', 'asan-ubsan', 'tsan')),
    'neoswap-discard': ('test/neoswap_discard_scan_test.py', ('plain', 'asan-ubsan', 'tsan')),
    'viewport-scissor': ('test/rpcs3_viewport_scissor_test.py', ('plain', 'asan-ubsan')),
    'rsx-write-sampler': ('test/rpcs3_rsx_cpu_write_test.py', ('plain', 'asan-ubsan')),
}
REUSED_TEST_INPUTS = {'test/rpcs3_texture_lifecycle_test.py',
                      'test/rpcs3_dynamic_state_retention_test.py'}
TEST_INPUTS = {script for script, _ in TESTS.values()} | REUSED_TEST_INPUTS | {
    'test/rpcs3_global_delta.py', delta.FIXTURE,
    'test/rpcs3_global_contract_test.py',
    'test/rpcs3_spu_runtime_cache_test.py',
    'test/native/rpcs3_spu_mfc_runtime.inc',
    'test/native/rpcs3_spu_timer_runtime.inc',
    'test/native/rpcs3_descriptor_bind_cache.inc',
    'test/native/rpcs3_texture_hash_reuse.inc',
    'test/rpcs3_texture_hash_reuse_benchmark.py',
    'test/native/rpcs3_texture_hash_reuse_bench.inc',
    'test/native/neoswap_discard_scan.inc',
    'test/rpcs3_prehash_admission_test.py',
    'test/native/rpcs3_prehash581.inc',
}
WORKFLOW_PATHS = sorted((TEST_INPUTS - REUSED_TEST_INPUTS) | {GATE, PARENT_CONTRACT, CODEGEN_REPORT})
sha, blob_sha, command = previous.sha, previous.blob_sha, previous.command


@lru_cache(maxsize=None)
def baseline_bytes(path):
    return delta.committed_bytes(path)


def input_bytes(path):
    if path == PARENT_CONTRACT:
        raw = baseline_bytes(path)
        assert (ROOT / path).is_file() and not (ROOT / path).is_symlink()
        assert (ROOT / path).read_bytes() == raw
        return raw
    return previous.input_bytes(path)


def input_paths():
    return (previous.input_paths() | TEST_INPUTS | {GATE, PARENT_CONTRACT, CODEGEN_REPORT}
            | first_resume.INPUT_PATHS | resume.INPUT_PATHS)


def inputs():
    return {path: sha(input_bytes(path)) for path in sorted(input_paths())}


def modules():
    import rpcs3_spu_mfc_runtime_test as mfc
    import rpcs3_spu_timer_runtime_test as timer
    import rpcs3_descriptor_bind_cache_test as descriptor
    import rpcs3_texture_hash_reuse_test as texture
    import neoswap_discard_scan_test as store
    import rpcs3_viewport_scissor_test as viewport
    return {'spu-mfc': mfc, 'spu-timer': timer, 'descriptor-bind': descriptor,
            'texture-hash-reuse': texture, 'neoswap-discard': store, 'viewport-scissor': viewport}


def parent_receipt(parent):
    raw = input_bytes(PARENT_CONTRACT)
    assert sha(raw) == PARENT_CONTRACT_SHA
    prior = json.loads(raw)
    assert prior['passed'] is True and prior['sourceContractExecuted'] is True
    assert prior['kind'] == 'committed-device594-source-contract'
    assert prior['source'] == PARENT_SOURCE
    assert prior['tree'] == command('git', 'rev-parse', PARENT_SOURCE + '^{tree}').decode().strip()
    command('git', 'merge-base', '--is-ancestor', PARENT_SOURCE, delta.BASELINE)
    assert prior['committedInputsRequired'] is True
    assert prior['committedInputCount'] == len(prior['inputSHA256']) == 206
    assert set(prior['inputSHA256']) == previous.input_paths()
    assert prior['canonicalPatchSHA256'] == parent['patch_sha256'] == delta.BASELINE_PATCH
    assert prior['fixtureSHA256'] == parent[previous.delta.KEY]['fixture_sha256']
    assert prior['nativeSourceSHA256'] == parent['files_sha256']
    assert prior['nativeReportCount'] == len(prior['nativeReports']) == 10
    for name, item in prior['nativeReports'].items():
        raw_report = baseline_bytes(item['path'])
        assert sha(raw_report) == item['sha256'] and item['passed'] is True, name
        assert (ROOT / item['path']).read_bytes() == raw_report, name
    for field in ('nativeTestsExecuted', 'compilerOrCMakeExecuted', 'appleCoreBuilt',
                  'physicalDeviceTested', 'gameplayMeasured', 'verificationWroteRemoteRef'):
        assert prior[field] is False, field
    historical = dict(source=PARENT_SOURCE, baselineCommit=delta.BASELINE,
        committedContractSHA256=sha(raw), sourceContractReused=True,
        deliveredApple=prior['historical'], priorHostModesPassed=10,
        priorHostSuitesReplayed=False, pendingDevice594AppleModes=10,
        supersededViewportAppleModes=2, supersededScopedWriteAppleModes=2,
        archiveDownloaded=False, coreBinaryReused=False)
    return historical, prior


def native_extras():
    import rpcs3_spu_runtime_cache_test as cache
    prior = json.loads(input_bytes(PARENT_CONTRACT))
    paths = previous.native_extras() | delta.PATHS | set(prior['codegenProof']['directlyAuthenticatedInputs'])
    paths |= set(cache.SOURCE) | set(cache.SUPPORT)
    for module in modules().values():
        paths |= set(module.SOURCE) | set(module.SUPPORT)
    return paths


def baselines(source, directory, authenticated):
    before = delta.reconstruct(source, directory / 'beforeGlobal', authenticated,
                               native_extras() | previous.previous.BASELINE_EXTRAS)
    parent = authenticated[2]
    prior = (parent, parent[previous.delta.KEY], json.loads(previous.baseline_bytes(MANIFEST)))
    roots = previous.baselines(before, directory, prior)
    return dict(beforeGlobal=before, **roots)


def rehash_metadata(current, old, before, paths=None):
    """Only file digests may change outside the exact compiled programs."""
    old = json.loads(json.dumps(old))
    paths = delta.PATHS if paths is None else paths
    changed = []
    for field in ('sourceSHA256', 'sourceInputs'):
        if isinstance(old.get(field), dict):
            assert set(old[field]) == set(current[field]), field
            for path, digest in old[field].items():
                if digest == current[field][path]:
                    continue
                assert path in paths, (field, path)
                raw = (before / path).read_bytes()
                assert digest in (sha(raw), delta.normalized_bytes_sha(raw)), path
                old[field][path] = current[field][path]
                changed.append(path)
    assert current == old, 'A purportedly unchanged production program changed'
    return changed


def passed_programs(source, roots):
    import rpcs3_framebuffer_key_test as framebuffer
    import rpcs3_submit_wake_test as wake
    result = previous.previous.bo2.expected_results(source, roots)
    result.pop('rsx-write-sampler')
    result['submit-wake'] = wake.expected(source, roots['beforeWarm'])
    result['framebuffer-key'] = framebuffer.expected(source, roots['beforeExact'])
    assert len(result) == 7
    return result


def preserved_programs(source, roots, prior):
    # Authenticate the old successful Apple programs with the frozen new
    # baseline first. No historical executable or compiler is run here.
    parent_manifest = json.loads(previous.baseline_bytes(MANIFEST))
    delivered, proof, contract = previous.parent_receipt(parent_manifest)
    baseline_programs = passed_programs(roots['beforeGlobal'], roots)
    old = {name: values for name, values in contract['expectedResults'].items()
           if name not in previous.SUPERSEDED | {'viewport-scissor', 'rsx-write-sampler'}}
    assert set(baseline_programs) == set(old)
    for name, expected in baseline_programs.items():
        rehash_metadata(expected, old[name], roots['before594'], previous.delta.PATHS)
    current_programs = passed_programs(source, roots)
    assert set(current_programs) == set(baseline_programs)
    changed = {name: rehash_metadata(expected, baseline_programs[name], roots['beforeGlobal'])
               for name, expected in current_programs.items()}
    pending = previous.expected_results(source, roots)
    for name, expected in pending.items():
        if name == 'texture-lifecycle-exact':
            # The Apple test observes the unordered-set rank instead of assuming
            # one allocator's pointer order. Only these pending test programs
            # change; all production bodies and semantic checks stay intact.
            assert prior['expectedResults'][name]['harnessesSHA256'] == {
                'baseline': '1d6d3f409d040caf3a87899f1905c14f9af25d123db19334120ad2a7d41d9bbb',
                'candidate': '621c759fe00bb0c6388b03898900b9d7f4c186257f120933202bcdf6f2ad88df',
            }
            assert expected['harnessesSHA256'] == APPLE_LIFECYCLE_PROGRAMS
            expected = json.loads(json.dumps(expected))
            expected['harnessesSHA256'] = prior['expectedResults'][name]['harnessesSHA256']
        changed[name] = rehash_metadata(expected, prior['expectedResults'][name], roots['beforeGlobal'])
    reused = [name for name in delivered['reusedAppleModes']
              if not name.startswith(('viewport-scissor-', 'rsx-write-sampler-'))]
    assert len(reused) == 16
    return dict(reusedAppleModes=reused, unchangedPassedPrograms=7,
                unchangedPendingPrograms=4, correctedPendingPrograms=['texture-lifecycle-exact'],
                wholeFileRehashesOutsidePrograms=changed), proof


def source_contract(source, require_committed=True):
    source = Path(source)
    authenticated = delta.authenticate(source)
    manifest, record, parent = authenticated
    assert len(record['tests']) == len(TEST_INPUTS) and set(record['tests']) == TEST_INPUTS
    historical, prior = parent_receipt(parent)
    current = inputs()
    allowed = {ENTRY, WORKFLOW, PIPELINE, 'test/neo_swap_core_pin_test.py', MANIFEST,
               'build-utils/rpcs3/embedded-core.patch'} | REUSED_TEST_INPUTS | delta.HOST_PATHS
    for path, digest in prior['inputSHA256'].items():
        assert sha(baseline_bytes(path)) == digest, path
        if path not in allowed:
            assert current[path] == digest, path
    # Constrain the old lifecycle guard to exactly the independently tested sync.
    guard_path = 'test/rpcs3_texture_lifecycle_test.py'
    old_guard = '    for path in [CACHE] + SUPPORT:\n        assert sha(source / path) == sha(baseline / path), path\n'
    new_guard = (
        '    for path in [CACHE] + [p for p in SUPPORT if p != CPP]:\n'
        '        assert sha(source / path) == sha(baseline / path), path\n'
        '    # The global follow-up changes only sync(), which this lifecycle harness\n'
        '    # never extracts. Its publication/concurrency has a separate native test.\n'
        '    current_cpp, old_cpp = (source / CPP).read_text(), (baseline / CPP).read_text()\n'
        "    sync = 'bool buffered_section::sync() const'\n"
        "    assert current_cpp.replace(braced(current_cpp, sync), '@SYNC@', 1) == old_cpp.replace(braced(old_cpp, sync), '@SYNC@', 1)\n")
    assert baseline_bytes(guard_path).decode().count(old_guard) == 1
    original_guard = baseline_bytes(guard_path).decode().replace(old_guard, new_guard)
    assert sha(original_guard.encode()) == ORIGINAL_LIFECYCLE_SCRIPT_SHA256
    assert sha((ROOT / guard_path).read_bytes()) == APPLE_LIFECYCLE_SCRIPT_SHA256
    assert sha((ROOT / PIPELINE).read_bytes()) == APPLE_RESUME_PIPELINE_SHA256
    descriptor_adapter = 'test/native/rpcs3_descriptor_bind_cache.inc'
    original_descriptor = command('git', 'show', resume.SOURCE + ':' + descriptor_adapter).decode()
    unused_mock = '    constexpr int cb_reuse = 1;'
    assert original_descriptor.count(unused_mock) == 1
    assert (ROOT / descriptor_adapter).read_text() == original_descriptor.replace(
        unused_mock, '    [[maybe_unused]] constexpr int cb_reuse = 1;')
    dynamic_path = 'test/rpcs3_dynamic_state_retention_test.py'
    old_declaration = "    result+='bool is_open=true; Driver* commands; mutable std::array<VkDescriptorSet,2> m_bound_descriptor_sets{}; mutable std::array<VkPipeline,2> m_bound_pipelines{}; mutable dynamic_state_cache m_dynamic_state;\\n'\n"
    new_declaration = """    header=(core/PATHS[2]).read_text()
    if 'm_descriptor_bindings' in header:
        # clear_state_cache now resets both descriptor bind points. Extract its
        # native fields; keep the historical stimulus and old-source output.
        result+='bool is_open=true; Driver* commands; using VkPipelineLayout = VkPipeline;\\n'
        result+=definition(header,'struct descriptor_binding_state')+';\\n'
        binding_array=next(line.strip() for line in header.splitlines() if 'mutable std::array<descriptor_binding_state' in line)
        result+=binding_array+'\\nmutable std::array<VkPipeline,2> m_bound_pipelines{}; mutable dynamic_state_cache m_dynamic_state;\\n'
    else:
        result+='bool is_open=true; Driver* commands; mutable std::array<VkDescriptorSet,2> m_bound_descriptor_sets{}; mutable std::array<VkPipeline,2> m_bound_pipelines{}; mutable dynamic_state_cache m_dynamic_state;\\n'
"""
    assert baseline_bytes(dynamic_path).decode().count(old_declaration) == 1
    assert (ROOT / dynamic_path).read_text() == baseline_bytes(dynamic_path).decode().replace(old_declaration, new_declaration)
    pin = baseline_bytes('test/neo_swap_core_pin_test.py').decode()
    old_literal = "PATCH_SHA256 = '" + parent['patch_sha256'] + "'"
    assert pin.count(old_literal) == 1
    assert (ROOT / 'test/neo_swap_core_pin_test.py').read_text() == pin.replace(
        old_literal, "PATCH_SHA256 = '" + manifest['patch_sha256'] + "'")
    entry = (ROOT / ENTRY).read_text()
    assert entry.count(ROUTE) == 1 and entry.replace(ROUTE, '') == baseline_bytes(ENTRY).decode()
    assert entry.index(ROUTE) < entry.index(previous.ROUTE)
    anchor = "      - '.github/diagnostics/rpcs3runtime_device594_core.py'\n"
    workflow = baseline_bytes(WORKFLOW).decode()
    assert workflow.count(anchor) == 1
    added = ''.join("      - '" + path + "'\n" for path in WORKFLOW_PATHS)
    assert (ROOT / WORKFLOW).read_text() == workflow.replace(anchor, anchor + added)
    if require_committed:
        command('git', 'merge-base', '--is-ancestor', delta.BASELINE, 'HEAD')
        previous.previous.committed_inputs(current)
    extras = {}
    for path in sorted(native_extras()):
        raw = (source / path).read_bytes()
        if path in manifest['files_sha256']:
            assert delta.normalized_bytes_sha(raw) == manifest['files_sha256'][path], path
        else:
            expected = command('git', '-C', str(source), 'rev-parse', manifest['upstream_commit'] + ':' + path).decode().strip()
            assert blob_sha(raw) == expected, path
        extras[path] = sha(raw)
    with tempfile.TemporaryDirectory(prefix='global-runtime-contract-') as temporary:
        roots = baselines(source, Path(temporary), authenticated)
        for path, digest in prior['supplementalNativeSHA256'].items():
            assert sha((roots['beforeGlobal'] / path).read_bytes()) == digest, path
        programs, delivered = preserved_programs(source, roots, prior)
        historical.update(programs)
        import rpcs3_spu_runtime_cache_test as cache
        codegen = cache.source_proof(source, roots['beforeGlobal'])
        assert codegen['codegen'] == record['codegen']
        cached = json.loads(input_bytes(CODEGEN_REPORT))
        assert cached['passed'] is True and cached['physicalDeviceTested'] is False
        assert cached['generatedObjectsRecompiled'] is False and cached['historicalNativeSuitesReplayed'] is False
        cache.verify_counts(cached['results'])
        for key, value in cache.expected(source, roots['beforeGlobal']).items():
            assert cached[key] == value, key
        codegen = dict(codegen, cmakeReceiptSHA256=sha(input_bytes(CODEGEN_REPORT)),
                       cmakeVerificationReused=True, cmakeReexecuted=False)
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert exports == delivered['exported_symbols'] and len(set(exports)) == 88
    return authenticated, current, historical, codegen, extras


def all_tests():
    return {**previous.all_tests(), **TESTS}


def baseline_commits():
    return dict(beforeGlobal=delta.BASELINE, **previous.baseline_commits())


def runner_command(name, mode, source, roots, compiler):
    if name in previous.all_tests():
        return previous.runner_command(name, mode, source, roots, compiler)
    if name == 'rsx-write-sampler':
        return previous.previous.device593.runner_command(name, mode, source, roots['before593'], compiler)
    before = roots['beforeWarm'] if name == 'viewport-scissor' else roots['beforeGlobal']
    argv = ['python3', TESTS[name][0], str(source), '--baseline', str(before), '--compiler', compiler]
    if mode != 'plain':
        argv += ['--sanitizer', 'thread' if mode == 'tsan' else 'address,undefined']
    if mode == 'plain' and name in ('descriptor-bind', 'texture-hash-reuse', 'neoswap-discard'):
        argv += ['--benchmark']
    if mode == 'plain' and name == 'texture-hash-reuse':
        argv += ['--mutations']
    return argv + ['--report', str(OUT / (name + '-' + mode + '-result.json'))]


def expected_results(source, roots):
    result = previous.expected_results(source, roots)
    result['rsx-write-sampler'] = previous.previous.bo2.expected_results(source, roots)['rsx-write-sampler']
    for name, module in modules().items():
        before = roots['beforeWarm'] if name == 'viewport-scissor' else roots['beforeGlobal']
        result[name] = module.expected(source, before)
    return result


def validate_delta_result(name, mode, payload, expected):
    if name in previous.all_tests():
        return previous.validate_delta_result(name, mode, payload, expected)
    if name == 'viewport-scissor':
        return pipeline.validate_delta_result(name, mode, payload, expected)
    assert name in TESTS and mode in TESTS[name][1]
    assert payload['passed'] is True
    assert payload['compiler']
    assert payload['physicalDeviceTested'] is False and payload['gameplayMeasured'] is False
    for key, value in expected[name].items():
        assert payload[key] == value, (name, key)
    if name == 'texture-hash-reuse':
        assert payload['fullCoreBuilt'] is False and payload['tsanSuppressions'] == []
        assert payload['hybridHashExecuted'] is False
        assert payload['sanitizer'] == ('' if mode == 'plain' else 'thread' if mode == 'tsan' else 'address,undefined')
        for version in ('baseline', 'candidate'):
            flags = payload[version]['compilerFlags']
            assert '-UNDEBUG' in flags and '-DRPCS3_IOS=1' in flags
            assert not any(flag.startswith('-DNDEBUG') for flag in flags)
            assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
            assert ('-fsanitize=thread' in flags) == (mode == 'tsan')
        if mode == 'plain':
            assert set(payload['mutations']) == {'no_reuse', 'no_bypass', 'no_epoch', 'single_writer'}
            assert all(case['rejected'] is True for case in payload['mutations'].values())
        modules()[name].verify_counts(payload)
        return
    if name == 'rsx-write-sampler':
        flags = payload['compilerFlags']
        assert '-UNDEBUG' in flags and not any(flag.startswith('-DNDEBUG') for flag in flags)
        assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
        assert payload['sanitizer'] == ('address,undefined' if mode == 'asan-ubsan' else '')
        counts = dict(cpuWrites=2808, inlineWrites=1296, dmaWrites=360,
            blitDispatchWrites=1152, noopsAndGpuReturns=30, baselineStaleAccepted=234,
            candidateStaleAccepted=0, baselineValidationHashes=702,
            candidateValidationHashes=936, unchangedEpochSkipsPreserved=1404,
            oldPrehashResultsRejected=468, notificationsAfterFinalBytes=468,
            desktopPathIdentical=True, epochDisabledIdentical=True)
        for key, value in counts.items():
            assert payload[key] == value, key
        assert payload['samplerBindings'] == dict(passed=True,
            boundDrawScenarios=96, baselineStaleGpuPayloads=48, candidateStaleGpuPayloads=0,
            unchangedBindingFastpaths=19200, scopedUntouchedBindingChecks=16,
            disjointScopedDrawsWithoutLookupHashOrUpload=4000, rangeAndDisabledCases=13,
            registrationWriteRaceCases=200, rangeStorageHasNoSectionPointers=True,
            physicalGpuModelled=True)
        assert payload['adapterSHA256'] == sha((ROOT / 'test/native/rpcs3_rsx_cpu_write.inc').read_bytes())
        assert payload['bindingAdapterSHA256'] == sha((ROOT / 'test/native/rpcs3_rsx_cpu_write_bindings.inc').read_bytes())
        return
    assert payload['assertionsActive'] is True
    flags = payload['compilerFlags']
    assert '-UNDEBUG' in flags and not any(flag.startswith('-DNDEBUG') for flag in flags)
    assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
    assert ('-fsanitize=thread' in flags) == (mode == 'tsan')
    assert payload['sanitizer'] in ((None, '') if mode == 'plain' else ('thread' if mode == 'tsan' else 'address,undefined',))
    modules()[name].verify_counts(payload['results'])
    if name == 'spu-mfc':
        fixed = dict(baselineZeroLimitQueueClockReads=13824, candidateZeroLimitQueueClockReads=0,
            emptyQueueInterruptEscapes=4944, deliveredTags=48960, executedBarriers=113832,
            stepDeferrals=12450, listResumptions=85779)
        assert payload['realDMATransfersTested'] is False
        assert payload['concurrentMemoryOrderingTested'] is False
        timing = payload['hostMaskTiming']
        assert (timing is None) == (mode != 'plain')
        if mode == 'plain':
            assert timing['samples'] == 7 and timing['iterationsPerSample'] == 1000000
            assert [(c['shuffle'], c['queueSize']) for c in timing['cases']] == [(0,16),(0,0),(1,16),(16,16)]
    elif name == 'spu-timer':
        fixed = dict(baselineNonemptyErases=10357, candidateNonemptyErases=277,
            baselineShiftedSlots=960340, candidateShiftedSlots=0,
            baselineDueAllocations=1065, candidateDueAllocations=277,
            obsoleteTokensRejected=6145, notifications=2172,
            pendingOrderComparisons=636, waitDeadlineComparisons=636)
        assert payload['concurrentMemoryOrderingTested'] is False
        timing = payload['hostSweepTiming']
        assert (timing is None) == (mode != 'plain')
        if mode == 'plain':
            assert timing['samples'] == 7 and len(timing['cases']) == 12
    else:
        fixed = {}
    for key, value in fixed.items():
        assert payload['results'][key] == value, key
    if name == 'neoswap-discard':
        assert payload['realStoreCases'] == 11 and payload['realPOSIXFileRoundTrips'] is True
        if mode == 'plain':
            assert len(payload['results']['benchmarks']) == 10
    if name == 'descriptor-bind':
        assert payload['gpuExecuted'] is False
        for result in payload['results'].values():
            assert {b['name'] for b in result['benchmark']} == (
                {'graphics_hits', 'changing_sets', 'alternating_bind_points'} if mode == 'plain' else set())


def validate_result(name, mode, payload, expected, compiler):
    assert payload['compiler'] == compiler and re.search(r'clang version 22\.', compiler)
    validate_delta_result(name, mode, payload, expected)


def reuse_result(name, mode, receipt, expected, compiler):
    return resume.reuse_result(name, mode, receipt, expected, compiler, gate=sys.modules[__name__])


def verify_reused_result(name, mode, state, proof, expected):
    return resume.verify_reused_result(name, mode, state, proof, expected, gate=sys.modules[__name__])


def main(args):
    gate = sys.modules[__name__]
    if args.write_core_identity:
        pipeline.identity(args.write_core_identity, gate=gate)
    elif args.verify_reuse:
        pipeline.verify(args.verify_reuse, args.source, gate=gate)
    elif args.source:
        pipeline.prepare(args.source.resolve(), gate=gate)
    else:
        raise ValueError('Global gate requires --source, --verify-reuse or --write-core-identity')
