#!/usr/bin/env python3
"""Bind the exact global source commit to its already executed host reports.

This command authenticates sources, reconstructs baselines and validates
receipts. It runs no compiler, CMake, native executable, historical suite,
Core build, workflow dispatch, release or remote mutation.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3runtime_global_core as gate
import rpcs3_texture_hash_reuse_benchmark as benchmark

DIRECTORY = 'docs/evidence/rpcs3-global-20261029/'


def report_paths():
    paths = {}
    for name, (_, modes) in gate.TESTS.items():
        directory = 'docs/evidence/rpcs3-rsx-bind-20261029/' if name in ('descriptor-bind', 'viewport-scissor') else DIRECTORY
        for mode in modes:
            suffix = 'asan' if name == 'neoswap-discard' and mode == 'asan-ubsan' else mode
            paths[(name, mode)] = directory + name + '-' + suffix + '.json'
    assert len(paths) == 16
    return paths


def reject_invalid(payloads, expected):
    cases = [
        ('false-success', 'descriptor-bind', 'plain', lambda p: p.update(passed=False)),
        ('disabled-assertions', 'descriptor-bind', 'plain', lambda p: p['compilerFlags'].append('-DNDEBUG')),
        ('missing-sanitizer', 'neoswap-discard', 'asan-ubsan', lambda p: p['compilerFlags'].remove('-fsanitize=address,undefined')),
        ('wrong-program', 'descriptor-bind', 'plain', lambda p: p['programSHA256'].update(candidate='0' * 64)),
        ('invented-gpu-execution', 'descriptor-bind', 'plain', lambda p: p.update(gpuExecuted=True)),
        ('missing-bind-benchmark', 'descriptor-bind', 'plain', lambda p: p['results']['candidate-ios'].update(benchmark=[])),
        ('texture-empty-concurrent-hits', 'texture-hash-reuse', 'tsan', lambda p: p['candidate'].update(stressAcceptedMatches=0)),
        ('texture-masked-race', 'texture-hash-reuse', 'tsan', lambda p: p['tsanSuppressions'].append('race:*')),
        ('texture-epoch-control-missing', 'texture-hash-reuse', 'plain', lambda p: p['candidate'].update(epochDuringHash=False)),
        ('texture-mutation-unchecked', 'texture-hash-reuse', 'plain', lambda p: p['mutations'].pop('single_writer')),
        ('mfc-clock-not-eliminated', 'spu-mfc', 'plain', lambda p: p['results'].update(candidateZeroLimitQueueClockReads=1)),
        ('timer-notifications-lost', 'spu-timer', 'plain', lambda p: p['results'].update(notifications=0)),
        ('neoswap-missing-collection', 'neoswap-discard', 'plain', lambda p: p['results'].update(collectCallsPerVersion=0)),
        ('neoswap-no-real-io', 'neoswap-discard', 'plain', lambda p: p.update(realPOSIXFileRoundTrips=False)),
        ('viewport-draws-missing', 'viewport-scissor', 'plain', lambda p: p['results'].update(randomDraws=0)),
        ('rsx-missing-writes', 'rsx-write-sampler', 'plain', lambda p: p.update(cpuWrites=0)),
        ('rsx-missing-bound-draws', 'rsx-write-sampler', 'plain', lambda p: p['samplerBindings'].update(boundDrawScenarios=0)),
        ('rsx-stale-gpu-payload', 'rsx-write-sampler', 'plain', lambda p: p['samplerBindings'].update(candidateStaleGpuPayloads=1)),
        ('invented-device-result', 'spu-timer', 'plain', lambda p: p.update(physicalDeviceTested=True)),
    ]
    rejected = []
    for label, name, mode, mutate in cases:
        payload = copy.deepcopy(payloads[(name, mode)])
        mutate(payload)
        try:
            gate.validate_delta_result(name, mode, payload, expected)
        except (AssertionError, KeyError, ValueError):
            rejected.append(label)
        else:
            raise AssertionError('Invalid receipt accepted: ' + label)
    return rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--uncommitted', action='store_true')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    authenticated, inputs, history, codegen, extras = gate.source_contract(source, require_committed=not args.uncommitted)
    manifest, record, _ = authenticated
    payloads, receipts = {}, {}
    with tempfile.TemporaryDirectory(prefix='global-receipts-') as temporary:
        roots = gate.baselines(source, Path(temporary), authenticated)
        expected = gate.expected_results(source, roots)
        for (name, mode), path in report_paths().items():
            raw = (ROOT / path).read_bytes()
            payload = json.loads(raw)
            gate.validate_delta_result(name, mode, payload, expected)
            payloads[(name, mode)] = payload
            receipts[name + '-' + mode] = dict(path=path, sha256=gate.sha(raw), passed=True,
                compiler=payload['compiler'], sanitizer=payload['sanitizer'])
        rejected = reject_invalid(payloads, expected)
        bench_path = DIRECTORY + 'texture-hash-reuse-benchmark.json'
        bench_raw = (ROOT / bench_path).read_bytes()
        bench = json.loads(bench_raw)
        for key, value in benchmark.expected(source, roots['beforeGlobal']).items():
            assert bench[key] == value, key
        benchmark.verify_counts(bench)
        assert bench['physicalDeviceTested'] is False and bench['gameplayMeasured'] is False
    integration_path = DIRECTORY + 'canonical-integration.json'
    integration = json.loads((ROOT / integration_path).read_bytes())
    assert integration['passed'] is True and integration['coreBuilt'] is False
    assert integration['canonicalPatchSHA256'] == manifest['patch_sha256']
    assert integration['canonicalPostimages'] == 313 and integration['changedPostimages'] == 6
    static_path = DIRECTORY + 'static-source-checks.json'
    static = json.loads((ROOT / static_path).read_bytes())
    assert static['passed'] is True and static['coreBuilt'] is False
    assert static['canonicalPatchSHA256'] == manifest['patch_sha256']
    assert static['abi'] == 30 and static['exports'] == 88
    assert gate.inputs() == inputs, 'Inputs changed during verification'
    result = dict(schema=1, kind=('uncommitted-' if args.uncommitted else 'committed-') + 'global-runtime-source-contract',
        passed=True, baselineCommit=gate.delta.BASELINE, canonicalPatchSHA256=manifest['patch_sha256'],
        fixtureSHA256=record['fixture_sha256'], sourceContractExecuted=True,
        committedInputsRequired=not args.uncommitted,
        source=None if args.uncommitted else gate.command('git', 'rev-parse', 'HEAD').decode().strip(),
        tree=None if args.uncommitted else gate.command('git', 'rev-parse', 'HEAD^{tree}').decode().strip(),
        inputCount=len(inputs), inputSHA256=inputs, nativeSourceSHA256=manifest['files_sha256'],
        supplementalNativeSHA256=extras, codegenProof=codegen, historical=history,
        expectedResults=expected, nativeReports=receipts, nativeReportCount=len(receipts),
        rejectedInvalidReceipts=rejected,
        textureBenchmark=dict(path=bench_path, sha256=gate.sha(bench_raw)),
        canonicalRematerialization=integration, staticSourceChecks=static,
        compilerOrCMakeExecuted=False, nativeTestsExecuted=False,
        historicalNativeSuitesReplayed=False, appleCoreBuilt=False,
        physicalDeviceTested=False, gameplayMeasured=False, releaseCreated=False,
        verificationWroteRemoteRef=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=True, source=result['source'], inputs=len(inputs),
        nativeSupplements=len(extras), nativeReports=len(receipts),
        invalidReceiptsRejected=len(rejected), reusedAppleModes=len(history['reusedAppleModes']),
        pendingAppleModes=sum(len(modes) for _, modes in gate.all_tests().values()),
        compilerOrNativeTestExecuted=False)))


if __name__ == '__main__':
    main()
