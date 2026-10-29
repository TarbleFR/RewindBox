"""Authenticate the next texture/FBO delta and reuse the shared Apple pipeline.

The previous twenty modes remain pending on Apple. Their unchanged extracted
programs are authenticated from the warm receipt without replaying host suites;
an explicitly requested Core adds only the four new Apple modes.
"""
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_bo2_exact_delta as delta
import rpcs3runtime_bo2_core as bo2
import rpcs3runtime_device593_core as device593
import rpcs3runtime_bo2_warm_core as previous

OUT, PROOF = previous.OUT, previous.PROOF
MANIFEST, ENTRY, WORKFLOW = previous.MANIFEST, previous.ENTRY, previous.WORKFLOW
GATE = '.github/diagnostics/rpcs3runtime_bo2_exact_core.py'
PARENT_CONTRACT = 'docs/evidence/rpcs3-bo2-warm-20261029/committed-contract.json'
PARENT_SOURCE = '64ca0a04d52636be40c78c5040f7e6933a9112c4'
ROUTE = """    if 'runtime_bo2_exact_20261029' in manifest():
        from rpcs3runtime_bo2_exact_core import main as exact_main
        exact_main(a)
        raise SystemExit
"""
TESTS = {
    'texture-exact': ('test/rpcs3_texture_exact_index_test.py', ('plain', 'asan-ubsan')),
    'framebuffer-key': ('test/rpcs3_framebuffer_key_test.py', ('plain', 'asan-ubsan')),
}
TEST_INPUTS = {script for script, _ in TESTS.values()} | {
    'test/rpcs3_bo2_exact_delta.py', delta.FIXTURE,
    'test/native/rpcs3_texture_exact_index.inc',
    'test/native/rpcs3_framebuffer_key.inc',
}
WORKFLOW_PATHS = sorted(TEST_INPUTS | {GATE, PARENT_CONTRACT})
SUPPORT = {
    'rpcs3/Emu/RSX/Common/simple_array.hpp',
    'rpcs3/Emu/RSX/Utils/rsx_utils.h',
    'rpcs3/Emu/RSX/VK/VKFramebuffer.h',
    'rpcs3/Emu/RSX/VK/vkutils/framebuffer_object.hpp',
}
NATIVE_EXTRAS = previous.NATIVE_EXTRAS | delta.PATHS | SUPPORT
BASELINE_EXTRAS = previous.NATIVE_EXTRAS | previous.BASELINE_EXTRAS | SUPPORT

sha = previous.sha
blob_sha = previous.blob_sha
command = previous.command
committed_inputs = previous.committed_inputs


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


def parent_receipt(parent):
    raw = input_bytes(PARENT_CONTRACT)
    prior = json.loads(raw)
    assert prior['passed'] is True and prior['sourceContractExecuted'] is True
    assert prior['kind'] == 'committed-bo2-warm-source-contract'
    assert prior['source'] == PARENT_SOURCE
    assert prior['tree'] == command('git', 'rev-parse', PARENT_SOURCE + '^{tree}').decode().strip()
    command('git', 'merge-base', '--is-ancestor', PARENT_SOURCE, delta.BASELINE)
    assert prior['committedInputsRequired'] is True
    assert prior['committedInputCount'] == len(prior['inputSHA256']) == 182
    assert set(prior['inputSHA256']) == previous.input_paths()
    assert prior['canonicalPatchSHA256'] == parent['patch_sha256'] == delta.BASELINE_PATCH
    assert prior['fixtureSHA256'] == parent[previous.delta.KEY]['fixture_sha256']
    assert prior['nativeSourceSHA256'] == parent['files_sha256']
    assert len(prior['nativeSourceSHA256']) == 312
    for field in ('nativeTestsExecuted', 'compilerOrCMakeExecuted', 'appleCoreBuilt',
                  'physicalDeviceTested', 'gameplayMeasured', 'verificationWroteRemoteRef'):
        assert prior[field] is False, field
    historical = dict(source=PARENT_SOURCE, baselineCommit=delta.BASELINE, inputCount=182,
                      committedContractSHA256=sha(raw), sourceContractReused=True,
                      priorNativeSuitesExecutedOnApple=False,
                      deliveredCore=prior['historical']['deliveredCore'], archiveDownloaded=False)
    return historical, prior


def baselines(source, directory, authenticated):
    """Restore warm first, then reuse the existing three baseline restorations."""
    before_exact = delta.reconstruct(source, directory / 'beforeExact', authenticated, BASELINE_EXTRAS)
    parent = authenticated[2]
    prior_tuple = (parent, parent[previous.delta.KEY], json.loads(previous.baseline_bytes(MANIFEST)))
    roots = previous.baselines(before_exact, directory, prior_tuple)
    return dict(beforeExact=before_exact, **roots)


def preserved_harnesses(source, roots, prior):
    """Only whole-file hashes may change; all earlier test programs stay exact."""
    now = previous.expected_results(source, roots)
    assert set(now) == set(prior['expectedResults'])
    changed_source_hashes = {'rsx-write-sampler': 'sourceSHA256', 'texture-address': 'sourceSHA256'}
    for name, expected in now.items():
        old = json.loads(json.dumps(prior['expectedResults'][name]))
        if name in changed_source_hashes:
            field = changed_source_hashes[name]
            assert set(old[field]) == set(expected[field]), name
            for path, digest in old[field].items():
                if path in delta.PATHS:
                    raw = (roots['beforeExact'] / path).read_bytes()
                    before_digest = delta.normalized_bytes_sha(raw) if name == 'texture-address' else sha(raw)
                    assert before_digest == digest, path
                else:
                    assert expected[field][path] == digest, path
            old[field] = expected[field]
        assert expected == old, name + ' changed a previously verified production harness'
    return now


def source_contract(source, require_committed=True):
    """Check the new source delta and preserved evidence without running code."""
    source = Path(source)
    authenticated = delta.authenticate(source)
    manifest, record, parent = authenticated
    assert len(record['tests']) == len(TEST_INPUTS) and set(record['tests']) == TEST_INPUTS
    command('git', 'merge-base', '--is-ancestor', delta.BASELINE, 'HEAD')
    historical, prior = parent_receipt(parent)
    current = inputs()
    allowed = {ENTRY, WORKFLOW, previous.GATE, 'test/neo_swap_core_pin_test.py',
               MANIFEST, 'build-utils/rpcs3/embedded-core.patch'}
    for path in allowed:
        assert sha(baseline_bytes(path)) == prior['inputSHA256'][path], path
    for path, digest in prior['inputSHA256'].items():
        if path not in allowed:
            assert current[path] == digest, path
    old_pin = baseline_bytes('test/neo_swap_core_pin_test.py').decode()
    old_literal = "PATCH_SHA256 = '" + parent['patch_sha256'] + "'"
    assert old_pin.count(old_literal) == 1
    assert (ROOT / 'test/neo_swap_core_pin_test.py').read_text() == old_pin.replace(
        old_literal, "PATCH_SHA256 = '" + manifest['patch_sha256'] + "'")
    entry = (ROOT / ENTRY).read_text()
    assert entry.count(ROUTE) == 1
    assert entry.replace(ROUTE, '') == baseline_bytes(ENTRY).decode()
    assert entry.index(ROUTE) < entry.index(previous.ROUTE)
    anchor = "      - '.github/diagnostics/rpcs3runtime_bo2_warm_core.py'\n"
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
    with tempfile.TemporaryDirectory(prefix='bo2-exact-provenance-') as temp:
        roots = baselines(source, Path(temp), authenticated)
        for path, digest in prior['supplementalNativeSHA256'].items():
            tree = roots['beforeExact'] if path in delta.PATHS else source
            assert sha((tree / path).read_bytes()) == digest, path
        preserved_harnesses(source, roots, prior)
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert len(exports) == len(set(exports)) == 88
    delivered = json.loads(device593.input_bytes(device593.HISTORY_DIR + 'runtime592-proof.json'))
    assert exports == delivered['exported_symbols']
    codegen = device593.codegen_receipt(source, bo2.legacy_tuple(parent))
    assert codegen == prior['codegenProof']
    assert codegen['codegen'] == record['codegen']
    return authenticated, current, historical, codegen, extras


def all_tests():
    return {**previous.all_tests(), **TESTS}


def baseline_commits():
    return dict(beforeExact=delta.BASELINE, **previous.baseline_commits())


def runner_command(name, mode, source, roots, compiler):
    if name in previous.all_tests():
        return previous.runner_command(name, mode, source, roots, compiler)
    argv = ['python3', TESTS[name][0], str(source), '--baseline', str(roots['beforeExact']),
            '--compiler', compiler]
    if mode == 'asan-ubsan':
        argv += ['--sanitizer', 'address,undefined']
    if name == 'texture-exact' and mode == 'plain':
        argv += ['--benchmark']
    return argv + ['--report', str(OUT / (name + '-' + mode + '-result.json'))]


def expected_results(source, roots):
    import rpcs3_texture_exact_index_test as texture
    import rpcs3_framebuffer_key_test as framebuffer
    before = roots['beforeExact']
    result = previous.expected_results(source, roots)
    assert set(texture.SOURCE) == {'rpcs3/Emu/RSX/Common/texture_cache.h'}
    assert set(texture.SUPPORT) == {
        'rpcs3/Emu/RSX/Common/texture_cache_utils.h', 'rpcs3/Emu/RSX/Common/texture_cache.cpp',
        'Utilities/address_range.h', 'rpcs3/Emu/RSX/Utils/rsx_utils.h',
        'rpcs3/Emu/RSX/Common/simple_array.hpp'}
    result['texture-exact'] = dict(
        sourceSHA256={p: delta.normalized_sha(source / p) for p in texture.SOURCE + texture.SUPPORT},
        baselineSHA256={p: delta.normalized_sha(before / p) for p in texture.SOURCE + texture.SUPPORT},
        harnessSHA256=sha(texture.harness(source, before).encode()),
        adapterSHA256=delta.normalized_sha(texture.ADAPTER))
    assert set(framebuffer.SOURCE) == delta.NEW_DELTA_PATHS
    assert set(framebuffer.SUPPORT) == SUPPORT - {'rpcs3/Emu/RSX/Common/simple_array.hpp'}
    result['framebuffer-key'] = framebuffer.expected(source, before)
    return result


def validate_delta_result(name, mode, payload, expected):
    assert name in TESTS and mode in TESTS[name][1]
    assert payload['passed'] is True and payload['assertionsActive'] is True and payload['compiler']
    flags = payload['compilerFlags']
    assert '-UNDEBUG' in flags and not any(flag.startswith('-DNDEBUG') for flag in flags)
    assert '-DRPCS3_IOS' in flags
    assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
    if mode == 'plain':
        assert payload['sanitizer'] in (None, '')
    else:
        assert payload['sanitizer'] == 'address,undefined'
    for key, value in expected[name].items():
        assert payload[key] == value, (name, key)
    assert payload['physicalDeviceTested'] is False and payload['gameplayMeasured'] is False
    result = payload['results']
    if name == 'framebuffer-key':
        counts = dict(keyConstructionsPerVersion=103936, fieldCases=405,
                      productionCacheQueries=1026, productionCacheHits=1011,
                      productionFBOCreations=15, productionFBODestructions=15,
                      imageInvalidations=3, ownershipCases=2, controlledFixedKeyBuckets=1)
        for key, value in counts.items():
            assert result[key] == value, key
        for key in ('allDefinedKeyBitsPreserved', 'bothLookupOverloadsExecuted',
                    'attachmentPredicateOrderPreserved'):
            assert result[key] is True, key
        assert result['physicalDeviceCacheMissesMeasured'] is False
        # An optimizing compiler may independently zero the old padding. The
        # candidate is deterministic regardless of that baseline manifestation.
        assert 0 <= result['preimageCasesVaryingWithPriorBytes'] <= result['fieldCases']
        assert 1 <= result['controlledPreimageKeyBuckets'] <= 256
    else:
        for key, value in dict(queries=13492, debugQueries=3365, mutations=4036).items():
            assert result[key] == value, key
        for key in ('sameFirstMatch', 'sameValidationOrder', 'sameMergeOrder', 'sameMutationState',
                    'sameInvalidViewSelection', 'confirmedRangeDebugCovered', 'realStorageAndPitch'):
            assert result[key] is True, key
        if mode == 'plain':
            assert [item['sections'] for item in result['benchmarks']] == [8, 16, 17, 64, 256, 1024]
            for item in result['benchmarks']:
                if item['sections'] > 16:
                    assert item['allocationsFor1000PrefixHitsAfter'] == 0
                if item['sections'] > 8:
                    assert item['allocationsFor1000PrefixHitsBefore'] > 0
        else:
            assert 'benchmarks' not in result


def validate_result(name, mode, payload, expected, compiler):
    if name in previous.all_tests():
        previous.validate_result(name, mode, payload, expected, compiler)
        return
    assert payload['compiler'] == compiler and re.search(r'clang version 22\.', compiler)
    validate_delta_result(name, mode, payload, expected)


def main(args):
    gate = sys.modules[__name__]
    if args.write_core_identity:
        previous.identity(args.write_core_identity, gate=gate)
    elif args.verify_reuse:
        previous.verify(args.verify_reuse, args.source, gate=gate)
    elif args.source:
        previous.prepare(args.source.resolve(), gate=gate)
    else:
        raise ValueError('The exact texture/FBO gate requires --source, --verify-reuse or --write-core-identity')
