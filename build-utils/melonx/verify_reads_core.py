#!/usr/bin/env python3
"""Build the reviewed fragmented-read and GPU-work delta on the delivered 609 Core.

The baseline is the MeloNX engine embedded in IPA 609: the liveness Core of run
41323968050 on source 1f12796c, whose own gates bound 126 preparation inputs and
163 prepared members. The historical Ada control comes from the ae78b4b
finalization archive that this Core authenticated, checked against the committed
liveness contract that the baseline result names by digest. Unchanged historical
evidence is authenticated, never promoted to a new execution or a proof for
changed inputs. No device, gameplay or FPS claim.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

import reuse_core_baseline as dependencies
import verify_core_candidate as common
import verify_liveness_core as liveness
from validate_runtime_reuse import child, digest, read, require, write

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dist/melonx'
EVIDENCE = OUT / 'core-validation'
SOURCE = ROOT / '.native-sources/MeloNX'
CONTROL = ROOT / '.native-sources/MeloNX-reads-control'
ADA_CONTROL = ROOT / '.native-sources/MeloNX-reads-ada-control'
CANDIDATE = ROOT / '.native-sources/MeloNX-reads-candidate'
CONTRACT = ROOT / 'build-utils/melonx/reads-core-contract.json'
LIVENESS_CONTRACT = ROOT / 'build-utils/melonx/liveness-core-contract.json'
ARCHIVE = ROOT / '.native-sources/melonx-1f12796c-liveness.zip'
HISTORICAL = 'historical-1f12796c/'
EVIDENCE_PREFIX = 'baseline-1f12796c/'
BASELINE = dict(
    source='1f12796c6b8c3d509bc203e52c561e0d345e7bfc',
    workflow='.github/workflows/melonx-core.yml',
    run=41323968050, job=124899905807, artifact=13090479414,
    artifactName='MeloNX-engine-1f12796c6b8c3d509bc203e52c561e0d345e7bfc',
    bytes=88300108,
    sha256='83827a94d5812a4dd85d83501d2bee5e31879e1c6961bb1043605ee90b7957fb',
    resultSha256='0f5121087e57b60a35351b616e0e564c01e698ebd3fbf626245f3e6690261672',
    gatesSha256='2aabb3290ee875a68ad82a198e64a6ae25d0603d4174226390e5637a96522ccf',
    livenessContractSha256='4e899e791d30ebd8e9f6a7183093aa5d51c6a7414f2b53642c5726c47ed55006',
    deliveredBuild=609,
)
BASELINE_EVIDENCE = (
    'core-validation/result.json', 'core-validation/compiled.json', 'core-validation/gates.json',
    'core-validation/preflight.json', 'core-validation/baseline-origin.json', 'runtime-smoke/actual-runtime.json',
    'ios-arm64/identity.json', 'iossimulator-arm64/identity.json', 'embedded-inputs.json', 'embedded-adapted-source.zip',
    # Binds the Ada-era performance contract (its unadapted members) for later deliveries.
    'baseline-ae78b4be/finalization-validation/result.json',
)
# Final payload rows the new collector must emit in both fresh NativeAOT sessions.
GPU_WORK = ('draw', 'compute', 'dma', 'i2m', 'texSync', 'texFlush', 'texFlushAction',
            'bufLoad', 'bufFlush', 'poolSync', 'shader', 'bindings')
READ_COUNTERS = ('readCopies', 'readCopyBytes', 'pooledReads', 'pooledReadBytes')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def contract():
    value = read(CONTRACT)
    require(value['schemaVersion'] == 1 and value['baseline'] == BASELINE, 'Wrong reads contract baseline')
    require(value['freshAppleGates'] == len(value['gates']) == 5, 'Wrong fresh gate scope')
    require(len(value['baselineReceipts']) == value['historicalAppleReceipts'] == 49, 'Wrong historical receipt inventory')
    common.inputs_match(value['inputs'])
    common.inputs_match(value['preparationInputs'])
    return value


def liveness_contract():
    require(digest(LIVENESS_CONTRACT) == BASELINE['livenessContractSha256'], 'Changed liveness contract')
    return read(LIVENESS_CONTRACT)


def authenticate_archive(path, frozen=None):
    require(path.stat().st_size == BASELINE['bytes'] and digest(path) == BASELINE['sha256'], 'Wrong delivered 609 Core archive')
    execution = dict(source=BASELINE['source'], run=BASELINE['run'], attempt=1,
                     url='https://github.com/TarbleFR/RewindBox/actions/runs/' + str(BASELINE['run']))
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and archive.testzip() is None, 'Damaged 609 Core archive')
        raw = archive.read('core-validation/result.json')
        require(sha(raw) == BASELINE['resultSha256'], 'Changed 609 Core result')
        result = json.loads(raw)
        require(result['result'] == 'passed' and result['execution'] == execution and
                result['status'] == 'compiled-and-simulator-validated-not-gameplay-tested', 'Wrong 609 Core outcome')
        require(result['physicalDeviceTested'] is False and result['gameplayTested'] is False and
                result['fpsGainProven'] is False, '609 Core claims untested scope')
        require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] ==
                result['performanceDiagnosticsFinalSessions'] == 2, 'Wrong 609 Core runtime scope')
        require(result['livenessCoreContractSha256'] == BASELINE['livenessContractSha256'] and
                result['deliveredBaseline'] == liveness.BASELINE, 'Wrong 609 Core contract or baseline')
        require(result['adaptationCount'] == 126 and result['preparedMembers'] == 163 and
                result['freshAppleGates'] == 5 and result['historicalAppleReceipts'] == 44, 'Wrong 609 Core composition')
        raw = archive.read('core-validation/gates.json')
        require(sha(raw) == BASELINE['gatesSha256'] == result['gateReceiptSha256'], 'Changed 609 Core gate inventory')
        gates = json.loads(raw)
        require(gates['result'] == 'passed' and gates['execution'] == execution and len(gates['receipts']) == 5 and
                len(gates['retainedReceipts']) == 44 and gates['historicalGatesReexecuted'] is False, 'Wrong 609 Core gates')
        compiled = json.loads(archive.read('core-validation/compiled.json'))
        require(compiled['result'] == 'passed' and compiled['execution'] == execution and
                compiled['binaries'] == result['binaries'] and compiled['identities'] == result['identities'],
                'Compiled 609 identity mismatch')
        before = json.loads(archive.read('embedded-inputs.json'))
        for runtime, binary in compiled['binaries'].items():
            raw = archive.read(runtime + '/Ryujinx.Library.dylib')
            require(len(raw) == binary['bytes'] and sha(raw) == binary['sha256'], 'Changed 609 binary')
            raw = archive.read(runtime + '/identity.json')
            require(sha(raw) == compiled['identities'][runtime], 'Changed 609 identity')
            identity = json.loads(raw)
            require(identity['sha256'] == binary['sha256'] and identity['adaptations'] == before and
                    identity['host'] == BASELINE['source'] and identity['runtimeIdentifier'] == runtime, 'Wrong 609 binary provenance')
        require(sha(archive.read('runtime-smoke/actual-runtime.json')) == result['runtimeSmokeSha256'], 'Changed 609 smoke')
        raw = archive.read('embedded-adapted-source.zip')
        require(sha(raw) == result['embeddedArchiveSha256'] == compiled['embeddedArchiveSha256'], 'Changed 609 prepared source')
        with zipfile.ZipFile(io.BytesIO(raw)) as prepared:
            members = liveness.inventory(prepared)
        require(len(before) == 126 and len(members) == 163, 'Wrong delivered source composition')
        receipts = {**gates['receipts'], **gates['retainedReceipts']}
        for name, expected in receipts.items():
            require(sha(archive.read(name)) == expected and json.loads(archive.read(name))['result'] == 'passed',
                    'Changed 609 receipt: ' + name)
        for name, scope in gates['auxiliaryHistoricalReceipts'].items():
            require(sha(archive.read(name)) == scope['sha256'] and scope['currentFullFixtureProof'] is False,
                    'Changed historical auxiliary scope')
        for name, expected in gates['baselineEvidenceSha256'].items():
            require(sha(archive.read(name)) == expected, 'Changed retained ae78b4b evidence: ' + name)
        if frozen is not None:
            require(before == frozen['baselinePreparationInputs'] and members == frozen['baselinePreparedMembers'],
                    'Contract differs from the delivered baseline')
            require(receipts == frozen['baselineReceipts'] and gates['auxiliaryHistoricalReceipts'] == frozen['baselineAuxiliaryReceipts'],
                    'Contract historical receipts differ')
        return before, members, gates


def metadata(run_id, job_id, artifact_id, run_sha, workflow, name, size, archive_sha):
    api = dict(repository='TarbleFR/RewindBox')
    run = dependencies.api(api, 'actions/runs/' + str(run_id))
    job = dependencies.api(api, 'actions/jobs/' + str(job_id))
    artifact = dependencies.api(api, 'actions/artifacts/' + str(artifact_id))
    require(run['id'] == run_id and run['head_sha'] == run_sha and run['status'] == 'completed' and
            run['conclusion'] == 'success' and run['run_attempt'] == 1 and run['path'] == workflow, 'Wrong baseline run')
    require(job['id'] == job_id and job['head_sha'] == run_sha and job['run_id'] == run_id and
            job['conclusion'] == 'success' and job['run_attempt'] == 1, 'Wrong baseline job')
    require(artifact['id'] == artifact_id and artifact['name'] == name and artifact['digest'] == 'sha256:' + archive_sha and
            artifact['size_in_bytes'] == size and not artifact['expired'] and artifact['workflow_run']['id'] == run_id and
            artifact['workflow_run']['head_sha'] == run_sha, 'Wrong baseline artifact')
    return run, job, artifact


def download(path, artifact_id):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open('xb') as output:
            subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{artifact_id}/zip'],
                           stdout=output, check=True, timeout=300)


def prior_archive():
    frozen = contract()
    run, job, artifact = metadata(BASELINE['run'], BASELINE['job'], BASELINE['artifact'], BASELINE['source'],
                                  BASELINE['workflow'], BASELINE['artifactName'], BASELINE['bytes'], BASELINE['sha256'])
    download(ARCHIVE, BASELINE['artifact'])
    authenticate_archive(ARCHIVE, frozen)
    old = liveness.BASELINE
    ada_run, ada_job, ada_artifact = metadata(old['run'], old['job'], old['artifact'], old['validationSource'],
                                              old['workflow'], old['artifactName'], old['bytes'], old['sha256'])
    download(liveness.ARCHIVE, old['artifact'])
    _, _, _, ada_members = liveness.authenticate_archive(liveness.ARCHIVE, liveness_contract())
    require(ada_members == frozen['adaControlMembers'], 'Contract Ada control differs from the liveness contract')
    write(EVIDENCE / 'baseline-origin.json', dict(result='authenticated', baseline=BASELINE, run=run, job=job, artifact=artifact,
        adaControlArchive=dict(baseline=old, run=ada_run, job=ada_job, artifact=ada_artifact),
        historicalGatesReexecuted=False))
    return ARCHIVE, liveness.ARCHIVE


def prepare_dependencies():
    frozen = contract()
    def reviewed_inputs(old, pin):
        expected = read(ROOT / pin['expectedInputs'])
        require(digest(ROOT / pin['expectedInputs']) == pin['expectedInputsSha256'], 'Dependency input inventory drift')
        require(len(old) == 74 and len(expected) == 87 and set(expected) == set(old) | set(pin['newAdapters']), 'Dependency historical composition drift')
        require(all(expected[path] == value for path, value in old.items() if path != dependencies.RECIPE), 'Changed original dependency input')
        return frozen['preparationInputs']
    dependencies.verify_inputs = reviewed_inputs
    dependencies.prepare()
    write(EVIDENCE / 'dependency-scope.json', dict(result='authenticated', scope='Unchanged LibHac and source-built native dependencies only', oldCoreGatesReexecuted=False))


def preflight():
    frozen = contract()
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Apple ARM64 required')
    require(common.command('dotnet', '--version') == '10.0.100', 'Wrong selected SDK')
    pin = read(ROOT / 'build-utils/melonx/source.json')
    require(common.command('git', 'rev-parse', 'HEAD', cwd=SOURCE) == pin['revision'], 'Wrong engine source')
    require(common.command('git', 'rev-parse', 'HEAD^{tree}', cwd=SOURCE) == '82a29e6f593f6244869481e9a489b8d5154175fe' and
            not common.command('git', 'status', '--porcelain', cwd=SOURCE), 'Upstream not pristine')
    write(EVIDENCE / 'preflight.json', dict(result='passed', execution=common.execution(), system='Darwin', architecture='arm64',
                                            preparationInputs=frozen['preparationInputs'], contractSha256=digest(CONTRACT),
                                            smokeInputs={path: digest(ROOT / path) for path in common.HOST_INPUTS}))


def validate_gate(data, gate, frozen):
    control = {'delivered': CONTROL, 'ada': ADA_CONTROL}[gate['control']]
    require(data['result'] == 'passed' and data['physicalDeviceTested'] is False, 'Affected fixture scope drift')
    common.inputs_match(data['inputs'])
    for path, expected in gate.get('assertions', {}).items():
        require(liveness.value_at(data, path) == expected, 'Affected fixture assertion failed: ' + path)
    for name, expected in data.get('upstreamInputs', {}).items():
        require(digest(child(control, name)) == expected, 'Changed control dependency: ' + name)
    for name, expected in data.get('preimages', {}).items():
        require(digest(child(control, name)) == expected, 'Changed control preimage: ' + name)
    for name, expected in data.get('postimages', {}).items():
        require(digest(child(CANDIDATE, name)) == expected, 'Fixture did not compile the final source: ' + name)
    for binding in gate.get('compiledBindings', []):
        expected = frozen['preparedMembers'].get(binding['productionPath'], frozen['untouchedFixtureMembers'].get(binding['productionPath']))
        require(expected is not None and liveness.value_at(data, binding['reportPath']) == expected, 'Wrong compiled production binding')
    require(set(gate['requiredPostimages']) <= set(data.get('postimages', {})), 'Missing final source postimage')


def copy_member(archive, name, relative):
    path = child(OUT, relative)
    require(not path.exists(), 'Refusing stale retained evidence: ' + relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(archive.read(name))
    return digest(path)


def run_gates():
    frozen = contract()
    require(read(EVIDENCE / 'preflight.json')['execution'] == common.execution(), 'Wrong preflight execution')
    archive_path, ada_path = prior_archive()
    require(not CONTROL.exists() and not ADA_CONTROL.exists() and not CANDIDATE.exists(), 'Stale reads gate sources')
    shutil.copytree(SOURCE, CANDIDATE, ignore=shutil.ignore_patterns('.git'))
    historical, auxiliary, baseline_evidence = {}, {}, {}
    with zipfile.ZipFile(archive_path) as archive:
        liveness.materialize(CONTROL, archive.read('embedded-adapted-source.zip'))
        for name, expected in frozen['baselineReceipts'].items():
            require(copy_member(archive, name, HISTORICAL + name) == expected, 'Changed retained receipt: ' + name)
            historical[HISTORICAL + name] = expected
        for name, scope in frozen['baselineAuxiliaryReceipts'].items():
            require(copy_member(archive, name, HISTORICAL + name) == scope['sha256'], 'Changed auxiliary receipt: ' + name)
            auxiliary[HISTORICAL + name] = scope
        for name in BASELINE_EVIDENCE:
            baseline_evidence[EVIDENCE_PREFIX + name] = copy_member(archive, name, EVIDENCE_PREFIX + name)
    with zipfile.ZipFile(ada_path) as archive:
        liveness.materialize(ADA_CONTROL, archive.read(liveness.ADA_PREPARED))
    for path, expected in frozen['baselinePreparedMembers'].items():
        require(digest(child(CONTROL, path)) == expected, 'Delivered control source differs: ' + path)
    for path, expected in frozen['adaControlMembers'].items():
        require(digest(child(ADA_CONTROL, path)) == expected, 'Historical Ada control source differs: ' + path)
    subprocess.run([sys.executable, str(ROOT / 'build-utils/melonx/prepare_embedded.py'), str(CANDIDATE)], check=True, timeout=300)
    require(read(OUT / 'embedded-inputs.json') == frozen['preparationInputs'], 'Gate preparation drift')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        require(liveness.inventory(archive) == frozen['preparedMembers'], 'Gate final source composition drift')
    for name, expected in frozen['untouchedFixtureMembers'].items():
        require(digest(child(CONTROL, name)) == digest(child(CANDIDATE, name)) == expected, 'Changed unadapted production dependency: ' + name)
    receipts = {}
    for gate in frozen['gates']:
        target = child(OUT, gate['report'])
        require(not target.exists(), 'Stale affected receipt: ' + gate['report'])
        control = {'delivered': CONTROL, 'ada': ADA_CONTROL}[gate['control']]
        argv = [arg.replace('{baseline}', str(control)).replace('{candidate}', str(CANDIDATE)) for arg in gate['arguments']]
        subprocess.run([sys.executable, str(ROOT / gate['script']), *argv], check=True, timeout=gate['timeoutSeconds'])
        validate_gate(read(target), gate, frozen)
        receipts[gate['report']] = digest(target)
    require(all(digest(child(CANDIDATE, path)) == expected for path, expected in frozen['preparedMembers'].items()), 'Fixture modified final candidate')
    write(EVIDENCE / 'gates.json', dict(result='passed', execution=common.execution(), receipts=receipts, freshAppleGates=len(receipts),
        reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=49, historicalGatesReexecuted=False,
        retainedReceipts=historical, retainedDisposition=frozen['retainedDisposition'],
        retainedChangedDependencies=frozen['retainedChangedDependencies'], auxiliaryHistoricalReceipts=auxiliary,
        baselineEvidenceSha256=baseline_evidence, physicalDeviceTested=False,
        retainedScope='Authentic delivered 609 Core evidence. Changed declared production/preparation dependencies remain historical-only; fresh affected fixtures bind the exact new prepared source.'))


def compiled():
    frozen = contract(); gates = read(EVIDENCE / 'gates.json')
    require(gates['execution'] == common.execution(), 'Gate execution changed')
    require(read(OUT / 'embedded-inputs.json') == frozen['preparationInputs'], 'Compiled preparation changed')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        require(liveness.inventory(archive) == frozen['preparedMembers'], 'Compiled source composition changed')
        require(all(archive.read(name) == child(SOURCE, name).read_bytes() for name in archive.namelist()), 'Archive differs from compiled source')
    for name, expected in {**gates['receipts'], **gates['retainedReceipts'], **gates['baselineEvidenceSha256']}.items():
        require(digest(child(OUT, name)) == expected, 'Gate/provenance receipt changed: ' + name)
    for name, scope in gates['auxiliaryHistoricalReceipts'].items():
        require(digest(child(OUT, name)) == scope['sha256'], 'Changed auxiliary historical proof')
    identities, binaries = {}, {}
    for runtime in ('ios-arm64', 'iossimulator-arm64'):
        directory = OUT / runtime
        identity = read(directory / 'identity.json'); binary = directory / 'Ryujinx.Library.dylib'
        require(identity['host'] == common.execution()['source'] and identity['adaptations'] == frozen['preparationInputs'] and
                identity['runtimeIdentifier'] == runtime and identity['source'] == read(ROOT / 'build-utils/melonx/source.json'), 'Wrong compiled identity')
        require(digest(binary) == identity['sha256'] and binary.stat().st_size == identity['size'] and len(identity['exports']) == 47 and
                identity['embeddedLibraryAbi'] == 2, 'Wrong binary or ABI')
        require(identity['status'] == 'compiled-not-gameplay-tested' and identity['embeddedSessionDeviceVerified'] is False, 'Unexpected compiled gameplay claim')
        symbols = {line.split()[-1] for line in (directory / 'exports.txt').read_text().splitlines() if line.split()}
        require(all('_' + name in symbols for name in identity['exports']), 'Missing native export')
        require('platform ' + ('IOS' if runtime == 'ios-arm64' else 'IOSSIMULATOR') + '\n' in (directory / 'platform.txt').read_text(), 'Wrong native platform')
        common.command('xcrun', 'lipo', str(binary), '-verify_arch', 'arm64')
        identities[runtime] = digest(directory / 'identity.json')
        binaries[runtime] = dict(sha256=digest(binary), bytes=binary.stat().st_size)
    write(EVIDENCE / 'compiled.json', dict(result='passed', execution=common.execution(), identities=identities, binaries=binaries,
        adaptationCount=len(frozen['preparationInputs']), preparedMembers=len(frozen['preparedMembers']),
        freshAppleGates=frozen['freshAppleGates'], reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=49,
        embeddedArchiveSha256=digest(OUT / 'embedded-adapted-source.zip'), physicalDeviceTested=False, gameplayTested=False))


def verify_diagnostics_smoke(report):
    """The liveness checks, plus the GPU work rows and read counters of the new collector."""
    count = liveness.verify_diagnostics_smoke(report)
    def nonnegative(number):
        return type(number) in (int, float) and math.isfinite(number) and number >= 0
    for final in report['performanceDiagnosticsFinalSessions']:
        value = json.loads(final['event']['diagnostic'])
        rows = value['gpuWork']
        require(isinstance(rows, dict) and tuple(rows) == GPU_WORK and value['gpuWorkColumns'] == 'completedCalls,wallMs,allocatedKiB',
                'Missing final GPU work rows')
        require(all(isinstance(row, list) and len(row) == 3 and all(nonnegative(number) for number in row) and
                    type(row[0]) is int and type(row[2]) is int for row in rows.values()), 'Invalid final GPU work row')
        require(all(type(value['counts'].get(name)) is int and value['counts'][name] >= 0 for name in READ_COUNTERS),
                'Missing final read counters')
    return count


def finalize():
    frozen = contract()
    final_sessions = verify_diagnostics_smoke(read(OUT / 'runtime-smoke/actual-runtime.json'))
    common.finalize()
    path = EVIDENCE / 'result.json'; result = read(path)
    result.update(readsCoreContractSha256=digest(CONTRACT), freshAppleGates=frozen['freshAppleGates'],
                  reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=49, deliveredBaseline=BASELINE,
                  performanceDiagnosticsFinalSessions=final_sessions, gpuWorkRows=len(GPU_WORK),
                  fpsGainProven=False, deviceAllocationReductionProven=False)
    for name in ('build-utils/melonx/verify_reads_core.py', 'build-utils/melonx/reads-core-contract.json',
                 'build-utils/melonx/verify_liveness_core.py', 'build-utils/melonx/liveness-core-contract.json'):
        result['inputs'][name] = digest(ROOT / name)
    write(path, result)
    (OUT / 'CORE_DELIVERY.md').write_text('# RewindBox fragmented-read MeloNX Core\n\n' + json.dumps(dict(
        execution=common.execution(), binaries=result['binaries'], deliveredBaseline=BASELINE['source'],
        freshAppleGates=frozen['freshAppleGates'], reusedScopedAppleReceipts=frozen['reusedAppleGates'],
        historicalAppleReceipts=49, physicalDeviceTested=False, fpsGainProven=False), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare_dependencies', 'preflight', 'run_gates', 'compiled', 'finalize'))
    globals()[parser.parse_args().phase]()
