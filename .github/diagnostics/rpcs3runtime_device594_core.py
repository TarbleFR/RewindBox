"""Authenticate delivered594 and execute only the newly changed production paths.

Twenty successful Apple modes remain bound to their exact compiled programs.
Four superseded texture modes are replaced. Building still requires an explicit
dispatch or the existing dedicated commit marker.
"""
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_device594_delta as delta
import rpcs3runtime_bo2_exact_core as previous
import rpcs3runtime_bo2_warm_core as pipeline

OUT, PROOF = previous.OUT, previous.PROOF
MANIFEST, ENTRY, WORKFLOW = previous.MANIFEST, previous.ENTRY, previous.WORKFLOW
GATE = '.github/diagnostics/rpcs3runtime_device594_core.py'
HISTORY = 'docs/evidence/rpcs3-bo2-exact-20261029/'
HISTORY_INPUTS = {HISTORY + p for p in (
    'apple-core.json', 'committed-contract.json',
    'apple-core/identity.json', 'apple-core/runtime592-proof.json')}
PARENT_SOURCE = 'fe587e27fcefadaa36315a3ddc7dc1edba17b825'
PARENT_PROOF_SHA = 'f952000e1fec81251db9b95ddd9e4e3c1c59b567c25c5ce2c6c864a0c5f70a92'
PARENT_IDENTITY_SHA = '442c435372aa5930389bd6700d4bb8064fa746ca499fa181a2f82c88731b7f2a'
SUPERSEDED = {'texture-address', 'texture-exact'}
ROUTE = """    if 'runtime_device594_followup_20261029' in manifest():
        from rpcs3runtime_device594_core import main as device594_main
        device594_main(a)
        raise SystemExit
"""
TESTS = {
    'fifo-partial': ('test/rpcs3_fifo_partial_packet_test.py', ('plain', 'asan-ubsan')),
    'texture-lifecycle-address': ('test/rpcs3_texture_lifecycle_test.py', ('plain', 'asan-ubsan')),
    'texture-lifecycle-exact': ('test/rpcs3_texture_lifecycle_test.py', ('plain', 'asan-ubsan')),
    'async-upload-wait': ('test/rpcs3_async_upload_wait_test.py', ('plain', 'asan-ubsan')),
    'bx2-sampler-transition': ('test/rpcs3_bx2_sampler_transition_test.py', ('plain', 'asan-ubsan')),
}
REUSED_TEST_INPUTS = {'test/rpcs3_bo2_fragment_key_test.py'}
TEST_INPUTS = {script for script, _ in TESTS.values()} | REUSED_TEST_INPUTS | {
    'test/rpcs3_device594_delta.py', delta.FIXTURE,
    'test/native/rpcs3_texture_lifecycle.inc',
    'test/native/rpcs3_fifo_pending_wait.inc',
    'test/native/rpcs3_fifo_partial_packet.inc',
    'test/native/rpcs3_async_upload_wait.inc',
    'test/native/rpcs3_bx2_sampler_transition.inc',
}
WORKFLOW_PATHS = sorted((TEST_INPUTS - REUSED_TEST_INPUTS) | {GATE} | HISTORY_INPUTS)
sha, blob_sha, command = previous.sha, previous.blob_sha, previous.command


@lru_cache(maxsize=None)
def baseline_bytes(path):
    return delta.committed_bytes(path)


def input_bytes(path):
    if path in HISTORY_INPUTS:
        raw = baseline_bytes(path)
        if (ROOT / path).exists():
            assert (ROOT / path).is_file() and not (ROOT / path).is_symlink(), path
            assert (ROOT / path).read_bytes() == raw, path
        return raw
    return previous.input_bytes(path)


def input_paths():
    return previous.input_paths() | TEST_INPUTS | {GATE} | HISTORY_INPUTS


def inputs():
    return {path: sha(input_bytes(path)) for path in sorted(input_paths())}


def modules():
    import rpcs3_fifo_partial_packet_test as fifo
    import rpcs3_texture_lifecycle_test as texture
    import rpcs3_async_upload_wait_test as upload
    import rpcs3_bx2_sampler_transition_test as sampler
    return {'fifo-partial': fifo, 'texture-lifecycle-address': texture,
            'texture-lifecycle-exact': texture, 'async-upload-wait': upload,
            'bx2-sampler-transition': sampler}


def native_extras():
    result = previous.NATIVE_EXTRAS | delta.PATHS
    for module in modules().values():
        result |= set(module.SOURCE) | set(module.SUPPORT)
    return result


def parent_receipt(parent):
    raw = input_bytes(HISTORY + 'apple-core/runtime592-proof.json')
    identity_raw = input_bytes(HISTORY + 'apple-core/identity.json')
    assert sha(raw) == PARENT_PROOF_SHA and sha(identity_raw) == PARENT_IDENTITY_SHA
    proof, identity = json.loads(raw), json.loads(identity_raw)
    receipt = json.loads(input_bytes(HISTORY + 'apple-core.json'))
    contract = json.loads(input_bytes(HISTORY + 'committed-contract.json'))
    assert proof['source'] == identity['host_commit'] == receipt['source'] == PARENT_SOURCE
    assert proof['all_tests_passed'] is True
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    assert re.search(r'clang version 22\.', proof['host']['compiler'])
    assert proof['native_source_sha256'] == identity['native_source_sha256'] == parent['files_sha256']
    assert identity['source_patch_sha256'] == parent['patch_sha256'] == delta.BASELINE_PATCH
    assert contract['passed'] is True and contract['sourceContractExecuted'] is True
    assert contract['inputSHA256'] == proof['input_sha256']
    assert contract['nativeSourceSHA256'] == parent['files_sha256']
    assert contract['codegenProof'] == proof['codegen_source_proof']
    assert len(proof['input_sha256']) == 190 and set(proof['input_sha256']) == previous.input_paths()
    names = {name + '-' + mode for name, (_, modes) in previous.all_tests().items() for mode in modes}
    assert len(names) == 24 and set(proof['tests']) == names
    assert all(item['passed'] is True and item['returncode'] == 0 for item in proof['tests'].values())
    assert receipt['run']['id'] == 40839976736 and receipt['run']['conclusion'] == 'success'
    assert receipt['core']['sha256'] == identity['sha256'] == '13b4c505434a7a0291abad47fa157ce0c9e20741e297f24dc2575e760e0e691b'
    command('git', 'merge-base', '--is-ancestor', PARENT_SOURCE, delta.BASELINE)
    reused = sorted(name + '-' + mode for name, (_, modes) in previous.all_tests().items()
                    if name not in SUPERSEDED for mode in modes)
    assert len(reused) == 20
    historical = dict(source=PARENT_SOURCE, baselineCommit=delta.BASELINE,
                      run=40839976736, coreSHA256=identity['sha256'], proofSHA256=sha(raw),
                      identitySHA256=sha(identity_raw), priorAppleModesPassed=24,
                      reusedAppleModes=reused, supersededTextureModes=4,
                      historicalSuitesReplayed=False, archiveDownloaded=False,
                      coreBinaryReused=False)
    return historical, proof, contract


def baselines(source, directory, authenticated):
    extra = native_extras() | previous.BASELINE_EXTRAS
    before = delta.reconstruct(source, directory / 'before594', authenticated, extra)
    parent = authenticated[2]
    old_tuple = (parent, parent[previous.delta.KEY], json.loads(previous.baseline_bytes(MANIFEST)))
    roots = previous.baselines(before, directory, old_tuple)
    return dict(before594=before, **roots)


def preserved_harnesses(source, roots, contract):
    # The old texture generators require their old lifecycle. Construct only
    # unchanged programs; authenticate their precise executable digests.
    import rpcs3_framebuffer_key_test as framebuffer
    import rpcs3_viewport_scissor_test as viewport
    import rpcs3_submit_wake_test as wake
    current = previous.bo2.expected_results(source, roots)
    current['viewport-scissor'] = viewport.expected(source, roots['beforeWarm'])
    current['submit-wake'] = wake.expected(source, roots['beforeWarm'])
    current['framebuffer-key'] = framebuffer.expected(source, roots['beforeExact'])
    old = {name: values for name, values in contract['expectedResults'].items() if name not in SUPERSEDED}
    assert set(current) == set(old) and len(current) == 9
    changed = {}
    for name, expected in current.items():
        prior = json.loads(json.dumps(old[name]))
        for field in ('sourceSHA256', 'sourceInputs'):
            if isinstance(prior.get(field), dict):
                assert set(prior[field]) == set(expected[field]), (name, field)
                for path, digest in prior[field].items():
                    if path in delta.PATHS and digest != expected[field][path]:
                        raw = (roots['before594'] / path).read_bytes()
                        assert digest in (sha(raw), delta.normalized_bytes_sha(raw)), path
                        prior[field][path] = expected[field][path]
                        changed.setdefault(name, []).append(path)
        assert expected == prior, name + ' changed a reused production program'
    return current, changed


def source_contract(source, require_committed=True):
    source = Path(source)
    authenticated = delta.authenticate(source)
    manifest, record, parent = authenticated
    assert len(record['tests']) == len(TEST_INPUTS) and set(record['tests']) == TEST_INPUTS
    historical, proof, contract = parent_receipt(parent)
    current = inputs()
    allowed = {ENTRY, WORKFLOW, 'test/neo_swap_core_pin_test.py', MANIFEST,
               'build-utils/rpcs3/embedded-core.patch'} | REUSED_TEST_INPUTS
    for path, digest in proof['input_sha256'].items():
        assert sha(baseline_bytes(path)) == digest, path
        if path not in allowed:
            assert current[path] == digest, path
    guard_path = 'test/rpcs3_bo2_fragment_key_test.py'
    old_guard = '    assert sha(source / THREAD) == sha(baseline / THREAD)\n'
    new_guard = (
        '    # The device594 follow-up changes prefetch invalidation, covered by its\n'
        '    # own native test. The caller, its ordering and every other body stay exact.\n'
        '    thread_text, old_thread = read(THREAD), (baseline / THREAD).read_text()\n'
        "    prefetch = 'void thread::prefetch_fragment_program()'\n"
        "    assert thread_text.replace(braced(thread_text, prefetch), '@PREFETCH@', 1) == old_thread.replace(braced(old_thread, prefetch), '@PREFETCH@', 1)\n")
    old_runner = baseline_bytes(guard_path).decode()
    assert old_runner.count(old_guard) == 1
    assert (ROOT / guard_path).read_text() == old_runner.replace(old_guard, new_guard)
    pin = baseline_bytes('test/neo_swap_core_pin_test.py').decode()
    old_literal = "PATCH_SHA256 = '" + parent['patch_sha256'] + "'"
    assert pin.count(old_literal) == 1
    assert (ROOT / 'test/neo_swap_core_pin_test.py').read_text() == pin.replace(
        old_literal, "PATCH_SHA256 = '" + manifest['patch_sha256'] + "'")
    entry = (ROOT / ENTRY).read_text()
    assert entry.count(ROUTE) == 1 and entry.replace(ROUTE, '') == baseline_bytes(ENTRY).decode()
    assert entry.index(ROUTE) < entry.index(previous.ROUTE)
    anchor = "      - '.github/diagnostics/rpcs3runtime_bo2_exact_core.py'\n"
    workflow = baseline_bytes(WORKFLOW).decode()
    assert workflow.count(anchor) == 1
    added = ''.join("      - '" + path + "'\n" for path in WORKFLOW_PATHS)
    assert (ROOT / WORKFLOW).read_text() == workflow.replace(anchor, anchor + added)
    if require_committed:
        command('git', 'merge-base', '--is-ancestor', delta.BASELINE, 'HEAD')
        previous.committed_inputs(current)
    extras = {}
    for path in sorted(native_extras()):
        raw = (source / path).read_bytes()
        if path in manifest['files_sha256']:
            assert delta.normalized_bytes_sha(raw) == manifest['files_sha256'][path], path
        else:
            expected = command('git', '-C', str(source), 'rev-parse', manifest['upstream_commit'] + ':' + path).decode().strip()
            assert blob_sha(raw) == expected, path
        extras[path] = sha(raw)
    with tempfile.TemporaryDirectory(prefix='device594-provenance-') as temp:
        roots = baselines(source, Path(temp), authenticated)
        for path, digest in proof['supplemental_native_sha256'].items():
            assert sha((roots['before594'] / path).read_bytes()) == digest, path
        _, rehashed = preserved_harnesses(source, roots, contract)
        historical['wholeFileRehashesOutsideReusedPrograms'] = rehashed
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert exports == proof['exported_symbols'] and len(set(exports)) == 88
    codegen = previous.device593.codegen_receipt(source, previous.bo2.legacy_tuple(parent))
    assert codegen == proof['codegen_source_proof'] and codegen['codegen'] == record['codegen']
    return authenticated, current, historical, codegen, extras


def all_tests():
    return TESTS


def baseline_commits():
    return dict(before594=delta.BASELINE, **previous.baseline_commits())


def runner_command(name, mode, source, roots, compiler):
    argv = ['python3', TESTS[name][0], str(source), '--baseline', str(roots['before594']),
            '--compiler', compiler]
    if name.startswith('texture-lifecycle-'):
        argv += ['--case', name.removeprefix('texture-lifecycle-')]
    if mode == 'asan-ubsan':
        argv += ['--sanitizer', 'address,undefined']
    if name == 'texture-lifecycle-address' and mode == 'plain':
        argv += ['--benchmark']
    return argv + ['--report', str(OUT / (name + '-' + mode + '-result.json'))]


def expected_results(source, roots):
    result = {}
    for name, module in modules().items():
        kwargs = {'case': name.removeprefix('texture-lifecycle-')} if name.startswith('texture-lifecycle-') else {}
        result[name] = module.expected(source, roots['before594'], **kwargs)
    return result


def validate_delta_result(name, mode, payload, expected):
    """Validate host reports independently of the subsequent Apple envelope."""
    assert name in TESTS and mode in TESTS[name][1]
    assert payload['passed'] is True and payload['assertionsActive'] is True
    assert payload['compiler']
    flags = payload['compilerFlags']
    assert '-UNDEBUG' in flags and not any(flag.startswith('-DNDEBUG') for flag in flags)
    if name == 'fifo-partial' or name.startswith('texture-lifecycle-'):
        assert '-DRPCS3_IOS' in flags
    assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
    assert payload['sanitizer'] in ((None, '') if mode == 'plain' else ('address,undefined',))
    assert payload['physicalDeviceTested'] is False and payload['gameplayMeasured'] is False
    for key, value in expected[name].items():
        assert payload[key] == value, (name, key)
    module = modules()[name]
    if name == 'fifo-partial':
        assert payload['fullSavestateSerializationTested'] is False
        assert payload['concurrentMemoryOrderingTested'] is False
    if name in ('async-upload-wait', 'bx2-sampler-transition'):
        assert payload['gpuExecuted'] is False
    if name.startswith('texture-lifecycle-'):
        module.verify_counts(payload['results'], case=name.removeprefix('texture-lifecycle-'))
        if name == 'texture-lifecycle-address' and mode == 'plain':
            benchmarks = payload['results']['benchmarks']
            assert [item['sections'] for item in benchmarks] == [8, 16, 17, 64, 256, 1024]
            assert all(item['lookupAllocations'] == 0 for item in benchmarks)
        else:
            assert 'benchmarks' not in payload['results']
    else:
        module.verify_counts(payload['results'])


def validate_result(name, mode, payload, expected, compiler):
    assert payload['compiler'] == compiler and re.search(r'clang version 22\.', compiler)
    validate_delta_result(name, mode, payload, expected)


def main(args):
    gate = sys.modules[__name__]
    if args.write_core_identity:
        pipeline.identity(args.write_core_identity, gate=gate)
    elif args.verify_reuse:
        pipeline.verify(args.verify_reuse, args.source, gate=gate)
    elif args.source:
        pipeline.prepare(args.source.resolve(), gate=gate)
    else:
        raise ValueError('The device594 gate requires --source, --verify-reuse or --write-core-identity')
