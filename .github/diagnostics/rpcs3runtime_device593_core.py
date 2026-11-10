"""Gate only the source changes after the Core delivered in private IPA 593.

The delivered c143be63 receipt is authenticated from local immutable Git blobs.
Its native suites and artifact download are not repeated. Eight new native modes
run on Apple ARM64, including real GCD; the existing recipe rechecks their exact
inputs before compiling one iPhone Core. No delivery number is assigned.
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
import rpcs3_device593_delta as delta

OUT = ROOT / 'build/rpcs3-core-diagnostics'
# This is the existing recipe hook, not a new Core or application version.
PROOF = OUT / 'runtime592-proof.json'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
ENTRY = '.github/diagnostics/rpcs3runtime592_core.py'
GATE = '.github/diagnostics/rpcs3runtime_device593_core.py'
WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
HISTORY = 'docs/evidence/rpcs3-runtime-20261029b/apple-core.json'
HISTORY_DIR = 'docs/evidence/rpcs3-runtime-20261029b/apple-core/'
HISTORY_FILES = {HISTORY, HISTORY_DIR + 'identity.json', HISTORY_DIR + 'runtime592-proof.json'}
CODEGEN_REPORT = 'docs/evidence/rpcs3-device593-20261029/codegen-identity.json'
CODEGEN_REPORT_SHA = '6e3e9f2306d1e80bd7b3c945d751445f37f051ee6bcf4c4f00bb40661d23c52b'
CODEGEN_RUNNER = 'test/rpcs3_codegen_593_identity_test.py'
CODEGEN_RUNNER_SHA = 'c56dc4981bca5f450b31033e5b8f4b8acb82d036eb6d739536ef8d87416b3d83'
ROUTE = """    if 'runtime_device593_followup_20261029' in manifest():
        from rpcs3runtime_device593_core import main as device593_main
        device593_main(a)
        raise SystemExit
"""
TESTS = {
    'jit-io': ('test/rpcs3_jit_cache_io_test.py', ('plain', 'asan-ubsan')),
    'mvk-present': ('test/rpcs3_mvk_present_queue_test.py', ('plain', 'asan-ubsan', 'tsan')),
    'rsx-write-sampler': ('test/rpcs3_rsx_cpu_write_test.py', ('plain', 'asan-ubsan')),
    'submit-lifetime': ('test/rpcs3_submit_packet_lifetime_test.py', ('asan-ubsan',)),
}
TEST_INPUTS = {script for script, _ in TESTS.values()} | {
    'test/rpcs3_device593_delta.py', delta.FIXTURE, CODEGEN_RUNNER,
    'test/native/rpcs3_jit_cache_io.inc',
    'test/native/rpcs3_mvk_present_queue_test.cpp',
    'test/native/rpcs3_mvk_present_queue_baseline.cpp',
    'test/native/rpcs3_mvk_present_queue_mock/dispatch/dispatch.h',
    'test/native/rpcs3_rsx_cpu_write.inc',
    'test/native/rpcs3_rsx_cpu_write_bindings.inc',
    'test/native/rpcs3_submit_packet_lifetime_test.cpp.in',
}
# These imports/generators are reused byte-for-byte. Their old main functions
# and historical scenarios are never executed by this gate.
REUSED_INPUTS = {
    'test/rpcs3_hotpaths_test.py', 'test/rpcs3_clock_scale_test.py',
    'test/rpcs3_memory523_test.py', 'test/rpcs3_cell559_test.py',
    'test/rpcs3_runtime_log_followup.py', 'test/rpcs3_prehash_admission_test.py',
    'test/native/rpcs3_prehash581.inc', 'test/native/rpcs3_prehash_admission.inc',
    'packages/dolphin_internal_bridge/ci/verify_ipa.py',
}
# Imported by the existing Mach-O reader. Its delivered Git blob predates this
# gate but was not included in the older native receipt's input dictionary.
AUXILIARY_BASELINE_INPUTS = {'build-utils/validate_single_ipa_distribution.py'}
WORKFLOW_PATHS = sorted(TEST_INPUTS | {GATE, CODEGEN_REPORT})
BASELINE_EXTRAS = {
    'Utilities/JITObjectBuffer.h', 'rpcs3/Emu/RSX/VK/vkutils/commands.h',
    'rpcs3/Emu/RSX/VK/VKCommandStream.cpp',
}
NATIVE_EXTRAS = BASELINE_EXTRAS | {
    'rpcs3/Emu/RSX/Common/texture_cache.cpp',
    'rpcs3/Emu/RSX/Common/texture_cache_utils.h',
    'rpcs3/ios/IOSTexturePrehash.h', 'rpcs3/ios/IOSThreadQoS.h',
    'Utilities/xxhash3.h', 'rpcs3/Emu/RSX/Common/texture_cache_protection_policy.h',
    'rpcs3/ios/RPCS3IOS.exports',
}


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
    if path in HISTORY_FILES:
        # A sparse checkout need not materialize these immutable receipts.
        raw = baseline_bytes(path)
        if (ROOT / path).exists():
            assert (ROOT / path).is_file() and not (ROOT / path).is_symlink(), path
            assert (ROOT / path).read_bytes() == raw, path
        return raw
    target = ROOT / path
    assert target.is_file() and not target.is_symlink(), path
    return target.read_bytes()


def history(parent):
    summary = json.loads(input_bytes(HISTORY))
    identity_raw = input_bytes(HISTORY_DIR + 'identity.json')
    proof_raw = input_bytes(HISTORY_DIR + 'runtime592-proof.json')
    assert sha(identity_raw) == summary['filesSHA256']['identity.json']
    assert sha(proof_raw) == summary['filesSHA256']['runtime592-proof.json']
    identity, proof = json.loads(identity_raw), json.loads(proof_raw)
    assert summary['result'] == 'passed' and summary['postimages'] == len(parent['files_sha256']) == 308
    assert summary['source'] == identity['host_commit'] == identity['native_source_commit'] == proof['source']
    assert summary['source'] == 'c143be63f95751616f98d7bf9f1f34f297862df2'
    assert summary['run']['id'] == 40814736023
    assert summary['run']['status'] == 'completed' and summary['run']['conclusion'] == 'success'
    assert identity['sha256'] == summary['core']['sha256']
    assert identity['abi_version'] == summary['core']['abi'] == 30
    assert identity['source_patch_sha256'] == summary['sourcePatchSHA256'] == parent['patch_sha256'] == delta.BASELINE_PATCH
    assert identity['native_source_sha256'] == proof['native_source_sha256'] == parent['files_sha256']
    assert identity['runtime_followup_input_sha256'] == proof['input_sha256']
    assert len(proof['input_sha256']) == summary['inputCount'] == 161
    assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
    assert proof['gameplay_measured'] is False
    assert proof['exported_symbols'] == identity['exported_symbols']
    assert len(set(proof['exported_symbols'])) == len(proof['exported_symbols']) == 88
    assert set(proof['tests']) == set(summary['tests'])
    for name, result in proof['tests'].items():
        assert result['passed'] is True and result['returncode'] == 0
        assert summary['tests'][name]['passed'] is True
        assert result['report_sha256'] == summary['tests'][name]['reportSHA256']
    assert summary['codegen'] == parent['runtime_log_followup_20261029']['codegen']
    receipt = dict(source=summary['source'], run=summary['run']['id'],
                   coreSHA256=identity['sha256'], identitySHA256=sha(identity_raw), proofSHA256=sha(proof_raw),
                   historicalResults=True, historicalTestsReplayed=False, archiveDownloaded=False,
                   coreBinaryReused=False)
    return receipt, proof


def input_paths():
    paths = set(pin.CORE_INPUTS) | REUSED_INPUTS | AUXILIARY_BASELINE_INPUTS | TEST_INPUTS | HISTORY_FILES | {
        ENTRY, GATE, WORKFLOW, CODEGEN_REPORT,
    }
    for directory in ('native/neoswap-storage', 'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan'):
        paths.update(command('git', 'ls-files', '--', directory).decode().splitlines())
    return paths


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


def codegen_receipt(source, authenticated):
    """Bind the already executed CMake proof to these exact current inputs."""
    manifest, record, parent = authenticated
    raw = (ROOT / CODEGEN_REPORT).read_bytes()
    assert sha(raw) == CODEGEN_REPORT_SHA
    proof = json.loads(raw)
    assert proof['passed'] is True
    assert sha((ROOT / CODEGEN_RUNNER).read_bytes()) == proof['scriptSHA256'] == CODEGEN_RUNNER_SHA
    assert proof['publication']['runnerSHA256'] == CODEGEN_RUNNER_SHA
    assert proof['publication']['runner'] == CODEGEN_RUNNER
    assert proof['publication']['runnerByteIdenticalToExecutedScript'] is True
    assert proof['upstreamCommit'] == manifest['upstream_commit']
    assert proof['upstreamTree'] == command('git', '-C', str(source), 'rev-parse', manifest['upstream_commit'] + '^{tree}').decode().strip()
    # This proof was executed before the new manifest was generated. Its origin
    # is the delivered manifest; it does not claim to hash the current one.
    assert proof['baselineManifestSHA256'] == proof['currentManifestSHA256'] == sha(baseline_bytes(MANIFEST))
    assert proof['expectedCodegen'] == record['codegen'] == parent['runtime_log_followup_20261029']['codegen']
    assert proof['baselineCMake']['identities'] == proof['candidateCMake']['identities'] == record['codegen']
    assert proof['uniqueInputCount'] == len(proof['authenticatedInputs']) == 41
    assert proof['directlyReadUniqueInputCount'] == 40
    assert proof['changedCodegenInputs'] == ['Utilities/JITLLVM.cpp']
    assert len(proof['candidateCMake']['aliasCases']) == 14
    assert all(case['passed'] is True for case in proof['candidateCMake']['aliasCases'])
    assert proof['negativeCaseCount'] == 10
    seen, direct = set(), {}
    backend = manifest['llvm_aarch64_ghc_patch']
    assert backend == parent['llvm_aarch64_ghc_patch']
    assert all(proof['llvmBackendDigestReuse'][key] == value for key, value in backend.items())
    assert proof['llvmBackendDigestReuse']['currentPinAndPatchMetadataEqualBaseline'] is True
    assert proof['llvmBackendDigestReuse']['backendSourceBytesReadOrRebuilt'] is False
    assert sha((ROOT / 'build-utils/rpcs3/llvm-aarch64-ghc-emergency-spill.patch').read_bytes()) == backend['patch_sha256']
    for item in proof['authenticatedInputs']:
        path = item['path']
        assert path not in seen
        seen.add(path)
        if not item['bytesRead']:
            assert path == '3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp'
            assert item['baselineSHA256'] == item['candidateSHA256'] == backend['postimage_sha256']
            assert item['equal'] is True
            continue
        data = (source / path).read_bytes()
        assert sha(data) == item['candidateSHA256'] and len(data) == item['candidateBytes'], path
        assert item['equal'] == (item['baselineSHA256'] == item['candidateSHA256'])
        if path in parent['files_sha256']:
            assert item['baselineSHA256'] == parent['files_sha256'][path], path
            assert delta.normalized_bytes_sha(data) == manifest['files_sha256'][path], path
        else:
            expected = command('git', '-C', str(source), 'rev-parse', manifest['upstream_commit'] + ':' + path).decode().strip()
            assert blob_sha(data) == item['gitBlobSHA1'] == expected, path
            assert item['equal'] is True
        direct[path] = sha(data)
    assert len(direct) == 40
    cmake = 'rpcs3/Emu/CMakeLists.txt'
    compat = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
    jit = 'Utilities/JITLLVM.cpp'
    assert sha((source / cmake).read_bytes()) == proof['cmakeInputListSHA256'] == parent['files_sha256'][cmake]
    assert sha((source / compat).read_bytes()) == proof['compatibilityModule']['candidateSHA256']
    assert proof['compatibilityModule']['baselineSHA256'] == record['before_sha256'][compat]
    assert proof['compatibilityModule']['onlySemanticChangeIsExactJITSourceHash'] is True
    assert sha((source / jit).read_bytes()) == proof['jitLLVM']['candidateSHA256'] == direct[jit]
    assert proof['jitLLVM']['baselineSHA256'] == record['before_sha256'][jit]
    assert proof['jitLLVM']['changedMethodCount'] == 3
    assert proof['jitLLVM']['entireFileOutsideThoseBodiesByteIdentical'] is True
    return dict(passed=True, sourceProofReused=True, testsExecuted=False, cmakeReexecuted=False,
                proofSHA256=sha(raw), runnerSHA256=CODEGEN_RUNNER_SHA, codegen=record['codegen'],
                directlyAuthenticatedInputs=direct, unchangedLLVMBackendSHA256=backend['postimage_sha256'],
                cmakeInputListSHA256=proof['cmakeInputListSHA256'],
                compatibilityModuleSHA256=proof['compatibilityModule']['candidateSHA256'])


def source_contract(source):
    source = Path(source)
    authenticated = delta.authenticate(source)
    manifest, record, parent = authenticated
    assert len(record['tests']) == len(TEST_INPUTS) and set(record['tests']) == TEST_INPUTS
    command('git', 'merge-base', '--is-ancestor', delta.BASELINE, 'HEAD')
    historical, prior = history(parent)
    current = inputs()
    allowed = {ENTRY, WORKFLOW, 'test/neo_swap_core_pin_test.py', MANIFEST,
               'build-utils/rpcs3/embedded-core.patch'}
    old_paths = set(current) - TEST_INPUTS - HISTORY_FILES - {GATE, CODEGEN_REPORT}
    for path in old_paths - allowed - AUXILIARY_BASELINE_INPUTS:
        assert current[path] == prior['input_sha256'][path], path
    for path in AUXILIARY_BASELINE_INPUTS:
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
    assert entry.index(ROUTE) < entry.index("    if 'runtime_log_followup_20261029' in manifest():")
    anchor = "      - '.github/diagnostics/rpcs3runtime_log_followup_core.py'\n"
    old_workflow = baseline_bytes(WORKFLOW).decode()
    assert old_workflow.count(anchor) == 1
    added = ''.join("      - '" + path + "'\n" for path in WORKFLOW_PATHS)
    assert (ROOT / WORKFLOW).read_text() == old_workflow.replace(anchor, anchor + added)
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
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert exports == prior['exported_symbols']
    reused = codegen_receipt(source, authenticated)
    return authenticated, current, historical, reused, extras


def runner_command(name, mode, source, baseline, compiler):
    script = TESTS[name][0]
    argv = ['python3', script]
    if name in ('mvk-present', 'submit-lifetime'):
        argv += ['--source', str(source)]
    else:
        argv += [str(source)]
    # The two-queue fallback is a deterministic baseline control. Compile it
    # once; only the changed queue implementation needs all three modes.
    if name != 'mvk-present' or mode == 'plain':
        argv += ['--baseline', str(baseline)]
    argv += ['--compiler', compiler]
    if name == 'mvk-present':
        argv += ['--require-gcd', '--mode', mode]
    elif name == 'jit-io' and mode == 'asan-ubsan':
        argv += ['--sanitize']
    elif name == 'rsx-write-sampler' and mode == 'asan-ubsan':
        argv += ['--sanitizer', 'address,undefined']
    option = '--output' if name in ('mvk-present', 'submit-lifetime') else '--report'
    return argv + [option, str(OUT / (name + '-' + mode + '-result.json'))]


def expected_results(source, baseline):
    # Only pure production extraction runs here. No compiler, executable, old
    # main function, timing loop or CMake proof is invoked during verification.
    import rpcs3_jit_cache_io_test as jit
    import rpcs3_mvk_present_queue_test as mvk
    import rpcs3_rsx_cpu_write_test as rsx
    import rpcs3_submit_packet_lifetime_test as packet
    before = (baseline / 'Utilities/JITLLVM.cpp').read_text()
    after = (source / 'Utilities/JITLLVM.cpp').read_text()
    code = (ROOT / 'test/native/rpcs3_jit_cache_io.inc').read_text().replace(
        '// @PRODUCTION_BODIES@', jit.production(before, 'before') + jit.production(after, 'after'))
    packet_code, packet_inputs = packet.extract(source)
    packet_before, packet_baseline = packet.extract(baseline)
    rsx_paths = {rsx.HANDLERS + path for path in rsx.UPSTREAM} | {
        rsx.prehash.CACHE, rsx.prehash.HEADER, rsx.prehash.UTILS,
        rsx.TEXTURES, rsx.DRAWS, 'rpcs3/ios/IOSTextureValidationProfile.h',
    }
    return {
        'jit-io': dict(generated_cpp_sha256=sha(code.encode()), source_sha256=sha((source / 'Utilities/JITLLVM.cpp').read_bytes()),
                       baseline_sha256=sha((baseline / 'Utilities/JITLLVM.cpp').read_bytes())),
        'mvk-present': dict(harness_sha256=sha(mvk.HARNESS.read_bytes()),
                            sourceInputs={p: sha((source / p).read_bytes()) for p in mvk.SOURCE_INPUTS},
                            baselineInputs={p: sha((baseline / p).read_bytes()) for p in mvk.SOURCE_INPUTS[:2]}),
        'rsx-write-sampler': dict(harnessSHA256=sha(rsx.make_harness(source, baseline).encode()),
                                  sourceSHA256={p: sha((source / p).read_bytes()) for p in rsx_paths},
                                  baselineGitBlobs={rsx.HANDLERS + p: digest for p, digest in rsx.UPSTREAM.items()}),
        'submit-lifetime': dict(harness_sha256=sha(packet_code.encode()), sourceInputs=packet_inputs,
                                baselineHarnessSHA256=sha(packet_before.encode()), baselineSourceInputs=packet_baseline),
    }


def validate_result(name, mode, payload, expected, compiler):
    assert payload['passed'] is True and payload['compiler'] == compiler
    assert re.search(r'clang version 22\.', compiler)
    flags = payload['compilerFlags']
    assert '-UNDEBUG' in flags and not any(flag.startswith('-DNDEBUG') for flag in flags)
    assert ('-fsanitize=address,undefined' in flags) == (mode == 'asan-ubsan')
    assert ('-fsanitize=thread' in flags) == (mode == 'tsan')
    if name == 'mvk-present':
        assert payload['mode'] == mode and payload['backend'] == 'libdispatch'
        assert payload['nativeLibdispatchTested'] is True and payload['adapter_sha256'] is None
    values = expected[name]
    for key, value in values.items():
        if name == 'mvk-present' and key == 'baselineInputs' and mode != 'plain':
            continue
        if not key.startswith('baselineHarness') and not key.startswith('baselineSource'):
            assert payload[key] == value, (name, key)
    if name == 'jit-io':
        assert payload['cases'] > 0
        assert payload['sanitizers'] == (['address', 'undefined'] if mode == 'asan-ubsan' else [])
        assert payload['non_ios_read_bodies_unchanged'] is True
        assert payload['emission_and_relocation_code_unchanged'] is True
        assert payload['physical_device_tested'] is False
    elif name == 'mvk-present':
        assert payload['assertionsActive'] is True and payload['checks'] > 0
        assert payload['metalOrDeviceTested'] is False and payload['leakSanitizer'] is False
        assert '-DRPCS3_MVK_USE_REAL_GCD=1' in flags
        if mode == 'plain':
            assert payload['baselineControl'] == dict(passed=True, assertionsActive=True,
                deliveredTwoQueueFallbackReproduced=True, queueCount=2, presentTicket=0)
        else:
            assert 'baselineControl' not in payload and 'baselineInputs' not in payload
        expected_tests = {'test/rpcs3_mvk_present_queue_test.py',
                          'test/native/rpcs3_mvk_present_queue_test.cpp',
                          'test/native/rpcs3_mvk_present_queue_baseline.cpp'}
        assert payload['testInputs'] == {p: sha((ROOT / p).read_bytes()) for p in expected_tests}
        assert payload['compiledSourceInputs'] == list(values['sourceInputs'])[:2]
        assert payload['integrationSourceInputs'] == list(values['sourceInputs'])[2:]
    elif name == 'rsx-write-sampler':
        assert payload['sanitizer'] == ('address,undefined' if mode == 'asan-ubsan' else '')
        assert payload['baselineStaleAccepted'] > 0 and payload['candidateStaleAccepted'] == 0
        assert payload['samplerBindings']['passed'] is True
        assert payload['physicalDeviceTested'] is False and payload['gameplayMeasured'] is False
        assert payload['adapterSHA256'] == sha((ROOT / 'test/native/rpcs3_rsx_cpu_write.inc').read_bytes())
        assert payload['bindingAdapterSHA256'] == sha((ROOT / 'test/native/rpcs3_rsx_cpu_write_bindings.inc').read_bytes())
    else:
        assert payload['mode'] == 'asan-ubsan' and payload['assertionsActive'] is True and payload['checks'] == 6
        assert payload['exitCode'] == 0 and not payload['testStderr']
        assert payload['leakSanitizer'] is False and payload['fullEngineCompiled'] is False
        assert payload['metalOrDeviceTested'] is False
        baseline = payload['baselineControl']
        assert baseline['passed'] is True and baseline['expectedMismatchReproduced'] is True
        assert baseline['sourceMutationApplied'] is False and baseline['exitCode'] != 0
        assert 'alloc-dealloc-mismatch (operator new vs free)' in baseline['testStderr']
        assert baseline['sourceInputs'] == values['baselineSourceInputs']
        assert baseline['harness_sha256'] == values['baselineHarnessSHA256']
        assert payload['adapter_sha256'] == sha((ROOT / 'test/native/rpcs3_submit_packet_lifetime_test.cpp.in').read_bytes())
        expected_tests = {'test/rpcs3_submit_packet_lifetime_test.py',
                          'test/native/rpcs3_submit_packet_lifetime_test.cpp.in'}
        assert payload['testInputs'] == {p: sha((ROOT / p).read_bytes()) for p in expected_tests}
        assert payload['compiledSourceInputs'] == list(values['sourceInputs'])


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
    env = dict(os.environ, SDKROOT=sdk, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1')
    receipt = dict(schema=1, kind=delta.KEY, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
                   source_root=str(source), input_sha256=current, native_source_sha256=manifest['files_sha256'],
                   supplemental_native_sha256=extras, fixture_sha256=record['fixture_sha256'],
                   host=dict(system='Darwin', machine='arm64', compiler=compiler, compilerCommand=compiler_command),
                   exported_symbols=sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split()),
                   physical_device_tested=False, gameplay_measured=False, all_tests_passed=False,
                   historical=historical, codegen_source_proof=codegen, tests={})
    PROOF.write_text(json.dumps(receipt, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='runtime-device593-before-') as temp:
        baseline = delta.reconstruct(source, Path(temp) / 'before', authenticated, BASELINE_EXTRAS)
        receipt['baseline_root'] = str(baseline)
        expected = expected_results(source, baseline)
        for name, (_, modes) in TESTS.items():
            for mode in modes:
                key = name + '-' + mode
                report = OUT / (key + '-result.json')
                report.unlink(missing_ok=True)
                argv = runner_command(name, mode, source, baseline, compiler_command)
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
    print('PASS eight new Apple ARM64 modes, including real GCD; CMake source proof reused, historical suites not replayed; no Metal, iPhone gameplay or FPS measurement')


def verify(path, source=None):
    proof = json.loads(path.read_bytes())
    assert proof['schema'] == 1 and proof['kind'] == delta.KEY
    source = Path(source or proof['source_root'])
    authenticated, current, historical, codegen, extras = source_contract(source)
    manifest, record, _ = authenticated
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['input_sha256'] == current and proof['native_source_sha256'] == manifest['files_sha256']
    assert proof['supplemental_native_sha256'] == extras
    assert proof['fixture_sha256'] == record['fixture_sha256']
    assert proof['all_tests_passed'] is True and proof['physical_device_tested'] is False
    assert proof['gameplay_measured'] is False
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    assert re.search(r'clang version 22\.', proof['host']['compiler'])
    assert proof['exported_symbols'] == sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert proof['historical'] == historical and proof['codegen_source_proof'] == codegen
    assert set(proof['tests']) == {name + '-' + mode for name, (_, modes) in TESTS.items() for mode in modes}
    with tempfile.TemporaryDirectory(prefix='runtime-device593-recheck-') as temp:
        baseline = delta.reconstruct(source, Path(temp) / 'before', authenticated, BASELINE_EXTRAS)
        expected = expected_results(source, baseline)
        for name, (_, modes) in TESTS.items():
            for mode in modes:
                key = name + '-' + mode
                state = proof['tests'][key]
                assert state['passed'] is True and state['returncode'] == 0
                assert state['command'] == runner_command(name, mode, Path(proof['source_root']),
                    Path(proof['baseline_root']), proof['host']['compilerCommand'])
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
    print('PASS iPhone source candidate: eight targeted ARM64 checks, exact ABI30/88 exports and unchanged PPU/SPU identities; no delivery number assigned or physical-device test')


def main(args):
    if args.write_core_identity:
        identity(args.write_core_identity)
    elif args.verify_reuse:
        verify(args.verify_reuse, args.source)
    elif args.source:
        prepare(args.source.resolve())
    else:
        raise ValueError('The device593 source gate requires --source, --verify-reuse or --write-core-identity')
