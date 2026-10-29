#!/usr/bin/env python3
"""Bind the new Apple gates, prepared sources, NativeAOT outputs and smoke.

Historical engine82 results are provenance, not a fresh test of changed code.
The current contract deliberately fails when the reviewed 86 preparation inputs
change: a later change must update its affected gates and source evidence.
"""
import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import zipfile

from validate_runtime_reuse import child, digest, read, require, verify_smoke_report, write


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dist/melonx'
EVIDENCE = OUT / 'core-validation'
PROOF = ROOT / 'docs/evidence/melonx-hogwarts-followup-20261029'
FOLLOWUP = ROOT / 'docs/evidence/melonx-hogwarts-timer-20261029'
CORE84 = ROOT / 'docs/evidence/melonx-hogwarts-core-20261029'
CORE84_INDEPENDENT = '93444fdee86538389ea9923c23208d79f357827dcd22cc8523d7848106bed82c'
SOURCE = ROOT / '.native-sources/MeloNX'
GATES = (
    'tracking-snapshot-checks.json', 'multirange-slice-checks.json',
    'texture-group-callbacks-checks.json', 'texture-region-cursor-checks.json',
    'auto-ownership-checks.json', 'converted-cache-checks.json',
    'kernel-wait-lifetime-checks.json', 'ipc-request-lifetime-checks.json',
    'kernel-timer-allocations-checks.json', 'allocator-blocks-checks.json',
    'indirect-cache-key-checks.json', 'texture-handle-dependencies-checks.json',
    'fragmented-upload-slice-checks.json',
    'sync-allocation-checks.json',
)
HOST_INPUTS = (
    'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift',
    'test/melonx_runtime_smoke.py',
)


def command(*args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True, timeout=60).strip()


def inputs_match(inputs):
    require(bool(inputs), 'Empty input inventory')
    for relative, expected in inputs.items():
        require(digest(child(ROOT, relative)) == expected, 'Changed input: ' + relative)


def preparation_inputs():
    baseline = read(PROOF / 'embedded-inputs.json')
    contract = read(FOLLOWUP / 'candidate.json')
    changes = contract['preparationChanges']
    require(set(changes) == {'build-utils/melonx/adapt_kernel_timer_allocations.py',
                            'build-utils/melonx/prepare_embedded.py'}, 'Unexpected preparation changes')
    for relative, change in changes.items():
        require(baseline[relative] == change['before'], 'Unexpected preparation baseline: ' + relative)
        baseline[relative] = change['after']
    added = contract['addedPreparationInputs']
    require(set(added) == {'build-utils/melonx/adapt_sync_allocations.py'} and
            not set(added) & set(baseline), 'Unexpected new preparation input')
    baseline.update(added)
    require(digest(FOLLOWUP / 'embedded-inputs.json') == contract['preparationInputsSha256'],
            'Timer preparation inventory digest changed')
    inputs = read(FOLLOWUP / 'embedded-inputs.json')
    require(inputs == baseline, 'Runtime follow-up changed unrelated preparation inputs')
    require(len(inputs) == 87, 'Unexpected reviewed preparation input count')
    inputs_match(inputs)
    return inputs


def reuse_gates():
    """Authenticate twelve unchanged Apple results without executing them again."""
    preparation_inputs()
    contract = read(FOLLOWUP / 'candidate.json')
    proof_path = CORE84 / 'independent-apple-verification.json'
    require(digest(proof_path) == CORE84_INDEPENDENT == contract['baselineIndependentSha256'],
            'Core84 independent evidence changed')
    proof = read(proof_path)
    require(proof['result'] == 'passed' and proof['source'] == contract['baselineSource'] and
            proof['run'] == contract['baselineRun'] == 40895446303, 'Wrong historical Apple execution')
    old_gates = CORE84 / 'apple-core/core-validation/gates.json'
    require(digest(old_gates) == proof['coreValidationSha256']['gates'], 'Core84 gate index changed')
    historical = read(old_gates)
    require(set(historical['receipts']) == set(GATES) - {'sync-allocation-checks.json'}, 'Historical gate inventory changed')
    require(historical['execution']['source'] == contract['baselineSource'] and
            historical['execution']['run'] == contract['baselineRun'], 'Historical gate origin changed')
    receipts = {}
    for name in GATES:
        if name in contract['freshGates']:
            continue
        path = CORE84 / 'apple-core' / name
        require(digest(path) == historical['receipts'][name], 'Historical gate changed: ' + name)
        report = read(path)
        require(report['result'] == 'passed' and report['physicalDeviceTested'] is False and
                report['upstreamRevision'] == read(ROOT / 'build-utils/melonx/source.json')['revision'],
                'Failed or foreign historical gate: ' + name)
        inputs_match(report['inputs'])
        for relative, expected in report.get('upstreamInputs', {}).items():
            require(digest(child(SOURCE, relative)) == expected, 'Wrong historical upstream input: ' + relative)
        target = OUT / name
        require(not target.exists(), 'Refusing existing historical gate output: ' + name)
        receipts[name] = {'sha256': digest(path), 'source': contract['baselineSource'],
                          'run': contract['baselineRun'], 'reexecuted': False}
    require(len(receipts) == 12 and set(contract['freshGates']) ==
            {'kernel-timer-allocations-checks.json', 'sync-allocation-checks.json'},
            'Wrong reuse/fresh split')
    # Publish only after every source, receipt and output path passes.
    OUT.mkdir(parents=True, exist_ok=True)
    for name in receipts:
        shutil.copyfile(CORE84 / 'apple-core' / name, OUT / name)
    write(EVIDENCE / 'reused-core84-gates.json', {'result': 'authenticated', 'receipts': receipts,
          'independentProofSha256': CORE84_INDEPENDENT, 'testsExecuted': 0})
    print('Authenticated twelve unchanged Core84 Apple receipts; no historical suite was replayed.')


def execution():
    source = command('git', 'rev-parse', 'HEAD')
    require(os.environ['GITHUB_REPOSITORY'] == 'TarbleFR/RewindBox' and
            os.environ['GITHUB_SHA'] == source, 'Unexpected checkout identity')
    return {'source': source, 'run': int(os.environ['GITHUB_RUN_ID']),
            'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
            'url': 'https://github.com/TarbleFR/RewindBox/actions/runs/' + os.environ['GITHUB_RUN_ID']}


def preflight():
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64',
            'The new Apple gates require macOS ARM64')
    require(command('dotnet', '--version') == '10.0.100', 'Wrong selected SDK')
    info = command('dotnet', '--info')
    require('osx-arm64' in info, 'SDK is not running as osx-arm64')
    pin = read(ROOT / 'build-utils/melonx/source.json')
    require(command('git', 'rev-parse', 'HEAD', cwd=SOURCE) == pin['revision'], 'Wrong upstream commit')
    require(command('git', 'rev-parse', 'HEAD^{tree}', cwd=SOURCE) ==
            '82a29e6f593f6244869481e9a489b8d5154175fe', 'Wrong upstream tree')
    require(not command('git', 'status', '--porcelain', cwd=SOURCE), 'Upstream is not pristine')
    inputs = preparation_inputs()
    write(EVIDENCE / 'preflight.json', {
        'result': 'passed', 'execution': execution(), 'system': platform.system(),
        'architecture': platform.machine(), 'dotnet': '10.0.100', 'dotnetInfo': info,
        'upstreamRevision': pin['revision'], 'preparationInputs': inputs,
        'smokeInputs': {relative: digest(ROOT / relative) for relative in HOST_INPUTS},
    })
    print('Pinned Apple ARM64 checkout, SDK 10.0.100, pristine upstream and 87 preparation inputs.')


def gates():
    preparation_inputs()
    require(read(EVIDENCE / 'preflight.json')['execution'] == execution(), 'Gate execution changed')
    revision = read(ROOT / 'build-utils/melonx/source.json')['revision']
    receipts = {}
    for name in GATES:
        path = OUT / name
        report = read(path)
        require(report['result'] == 'passed' and report['upstreamRevision'] == revision,
                'Failed or foreign gate: ' + name)
        inputs_match(report['inputs'])
        require(report.get('physicalDeviceTested') is False, 'Unexpected device claim: ' + name)
        for relative, expected in report.get('upstreamInputs', {}).items():
            require(digest(child(SOURCE, relative)) == expected, 'Wrong gate upstream input: ' + relative)
        receipts[name] = digest(path)
    reused = read(EVIDENCE / 'reused-core84-gates.json')
    require(reused['result'] == 'authenticated' and reused['testsExecuted'] == 0 and
            len(reused['receipts']) == 12, 'Missing Core84 reuse proof')
    for name, origin in reused['receipts'].items():
        require(receipts[name] == origin['sha256'] and origin['reexecuted'] is False,
                'Reused receipt changed: ' + name)
    write(EVIDENCE / 'gates.json', {
        'result': 'passed', 'execution': execution(), 'receipts': receipts,
        'targetedGateCount': 14, 'freshAppleGates': 2, 'reusedAppleGates': 12,
        'historicalGatesReexecuted': False, 'physicalDeviceTested': False,
    })
    print('Authenticated two fresh runtime gates and twelve unchanged Core84 Apple gates.')


def compiled():
    inputs = preparation_inputs()
    require(read(OUT / 'embedded-inputs.json') == inputs, 'Compiled adaptation inventory changed')
    prior = read(EVIDENCE / 'gates.json')
    require(prior['execution'] == execution(), 'Compilation execution changed')
    for name, expected in prior['receipts'].items():
        require(digest(OUT / name) == expected, 'Gate receipt changed after compilation: ' + name)
    integration = read(PROOF / 'integration.json')
    changes = read(FOLLOWUP / 'candidate.json')['changedSources']
    timer = 'src/Ryujinx.HLE/HOS/Kernel/Common/KTimeManager.cs'
    require(set(changes) == {timer, 'src/Ryujinx.Graphics.Vulkan/SyncManager.cs',
                            'src/Ryujinx.Graphics.Vulkan/BufferUsageBitmap.cs'} and
            integration['sourceDelta'][timer]['after'] == changes[timer]['before'],
            'Unexpected runtime production baseline')
    for relative, change in changes.items():
        if relative == timer:
            integration['sourceDelta'][relative]['after'] = change['after']
        else:
            require(relative not in integration['sourceDelta'], 'Unexpected overlap: ' + relative)
            integration['sourceDelta'][relative] = change
    require(integration['result'] == 'passed' and len(integration['sourceDelta']) == 19,
            'Unexpected source integration evidence')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        paths = archive.namelist()
        require(len(paths) == len(set(paths)), 'Duplicate prepared source member')
        for relative in paths:
            data = archive.read(relative)
            require(data == child(SOURCE, relative).read_bytes(), 'Archived source differs: ' + relative)
        for relative, delta in integration['sourceDelta'].items():
            require(relative in paths and digest(child(SOURCE, relative)) == delta['after'],
                    'Reviewed production postimage differs: ' + relative)
    exceptions = {(item['receipt'], item['path']): item
                  for item in integration['postimageCompositionExceptions']}
    postimages = 0
    for name in GATES:
        receipt = read(OUT / name)
        images = receipt.get('postimages', {})
        images = images.get('candidate', images)
        require(bool(images), 'Gate did not record compiled postimages: ' + name)
        for relative, expected in images.items():
            actual = digest(child(SOURCE, relative))
            if actual != expected:
                exception = exceptions.get((name, relative))
                require(exception is not None and expected == exception['fixturePostimage'] and
                        actual == exception['finalPostimage'],
                        'Unreviewed fixture/production composition: ' + name + ' / ' + relative)
            postimages += 1
    identities, binaries = {}, {}
    expected_pin = read(ROOT / 'build-utils/melonx/source.json')
    for runtime in ('ios-arm64', 'iossimulator-arm64'):
        directory = OUT / runtime
        identity = read(directory / 'identity.json')
        core = directory / 'Ryujinx.Library.dylib'
        require(identity['host'] == execution()['source'] and identity['source'] == expected_pin and
                identity['runtimeIdentifier'] == runtime and identity['adaptations'] == inputs,
                'Wrong compiled source identity: ' + runtime)
        require(digest(core) == identity['sha256'] and core.stat().st_size == identity['size'],
                'Compiled binary digest/size mismatch: ' + runtime)
        require(identity['status'] == 'compiled-not-gameplay-tested' and
                identity['embeddedSessionDeviceVerified'] is False and
                identity['embeddedLibraryAbi'] == 2, 'Wrong engine status/ABI')
        require(len(identity['exports']) == 47, 'Wrong required export inventory')
        symbols = {line.split()[-1] for line in (directory / 'exports.txt').read_text().splitlines() if line.split()}
        require(all('_' + name in symbols for name in identity['exports']), 'Missing native ABI export')
        target = 'IOS' if runtime == 'ios-arm64' else 'IOSSIMULATOR'
        require('platform ' + target + '\n' in (directory / 'platform.txt').read_text(), 'Wrong Mach-O platform')
        command('xcrun', 'lipo', str(core), '-verify_arch', 'arm64')
        identities[runtime] = digest(directory / 'identity.json')
        binaries[runtime] = {'sha256': identity['sha256'], 'bytes': identity['size']}
    write(EVIDENCE / 'compiled.json', {
        'result': 'passed', 'execution': execution(), 'identities': identities, 'binaries': binaries,
        'adaptationCount': len(inputs), 'reviewedChangedSources': 19,
        'verifiedGatePostimages': postimages, 'compositionExceptions': list(exceptions.values()),
        'embeddedArchiveSha256': digest(OUT / 'embedded-adapted-source.zip'),
        'physicalDeviceTested': False, 'gameplayTested': False,
    })
    print('Both fresh NativeAOT libraries match the 87 inputs, 19 source changes and 47-export ABI.')


def finalize():
    result = read(EVIDENCE / 'compiled.json')
    require(result['execution'] == execution(), 'Smoke execution changed')
    for runtime, binary in result['binaries'].items():
        require(digest(OUT / runtime / 'Ryujinx.Library.dylib') == binary['sha256'] and
                digest(OUT / runtime / 'identity.json') == result['identities'][runtime],
                'Compiled binary or identity changed during smoke')
    preflight = read(EVIDENCE / 'preflight.json')
    inputs_match(preflight['smokeInputs'])
    smoke_path = OUT / 'runtime-smoke/actual-runtime.json'
    report = read(smoke_path)
    verify_smoke_report(report, {'simulatorSha256': result['binaries']['iossimulator-arm64']['sha256']},
                        preflight['smokeInputs'])
    require(report['actualNativeAOT'] is True and report['gameplayTested'] is False and
            report['iphoneGuestExecutionTested'] is False, 'Unexpected smoke scope')
    reuse_receipts = ('baseline-engine82/authentication/result.json',
                      'libhac-authenticated-reuse.json', 'native-dependencies-reused.json')
    for relative in reuse_receipts:
        require(read(OUT / relative)['result'] == 'authenticated', 'Missing reuse proof: ' + relative)
    result.update({
        'result': 'passed', 'runtimeSmokeSha256': digest(smoke_path),
        'guestSvcSessions': report['homebrewGuestSvcSessions'],
        'homebrewSimulatorSessions': report['homebrewSimulatorSessions'],
        'releasedBackingSessions': report['actualCoreDonatedBackingSessions'],
        'gateReceiptSha256': digest(EVIDENCE / 'gates.json'),
        'reusedEvidenceSha256': {relative: digest(OUT / relative) for relative in reuse_receipts},
        'historicalGatesReexecuted': False, 'nativeDependenciesRecompiled': False,
        'status': 'compiled-and-simulator-validated-not-gameplay-tested',
        'inputs': {path: digest(ROOT / path) for path in (
            '.github/workflows/melonx-core.yml', 'build-utils/melonx/build_core.sh',
            'build-utils/melonx/build_libhac.py', 'build-utils/melonx/reuse_core_baseline.py',
            'build-utils/melonx/core-baseline.json', 'build-utils/melonx/verify_core_candidate.py')},
    })
    write(EVIDENCE / 'result.json', result)
    print('Verified fresh core, two separate guest SVC sessions, closed sessions and released backing.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('preflight', 'reuse_gates', 'gates', 'compiled', 'finalize'))
    args = parser.parse_args()
    globals()[args.phase]()
