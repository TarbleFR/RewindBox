#!/usr/bin/env python3
"""Build a reviewed performance delta on the delivered Ada/510 Core.

The failed original producer and successful later runtime validation retain
separate identities. Unchanged scoped historical evidence is authenticated,
never silently promoted to a new execution or a proof for changed inputs.
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
from validate_runtime_reuse import child, digest, read, require, write

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dist/melonx'
EVIDENCE = OUT / 'core-validation'
SOURCE = ROOT / '.native-sources/MeloNX'
CONTROL = ROOT / '.native-sources/MeloNX-performance-control'
CANDIDATE = ROOT / '.native-sources/MeloNX-performance-candidate'
CONTRACT = ROOT / 'build-utils/melonx/performance-core-contract.json'
BASELINE = dict(
    source='ada4058f5738465ac882934bb87224b637bcd0a1',
    validationSource='510e683a149e811e68ea6ab5e766e85c44ab1057',
    run=41121572662, job=124288787086, artifact=13009521221,
    artifactName='MeloNX-ada4058-runtime-validation-41121572662',
    bytes=87656173,
    sha256='ed70ba31b1b52fc0fbd55e695b25cc4254d5f90c4f86b930d8bf2958235ac278',
    runtimeResultSha256='3d56f23c61d379728eb62d514449c7ce20d02c5d95f22551a44b44f84efea6c3',
    producerRun=41118873328, producerJob=124280125758, producerArtifact=13007577275,
    producerArchiveSha256='93771c1ff47396f841534463ec6ea49ad3657d8a815e8c39c3d63e138c926395',
)
BASELINE_EVIDENCE = (
    'runtime-validation/result.json', 'runtime-validation/preparation.json',
    'runtime-validation/original-run.json', 'runtime-validation/original-job.json',
    'runtime-validation/original-artifact.json', 'runtime-smoke/actual-runtime.json',
    'core-validation/preflight.json', 'core-validation/compiled.json',
    'core-validation/gates.json', 'embedded-inputs.json', 'embedded-adapted-source.zip',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), 'Duplicate prepared source path')
    for name in names:
        require(name.startswith('src/') and '..' not in Path(name).parts and not Path(name).is_absolute(), 'Unsafe prepared path')
    return {name: sha(archive.read(name)) for name in names}


def contract():
    value = read(CONTRACT)
    require(value['schemaVersion'] == 1 and value['baseline'] == BASELINE, 'Wrong performance contract baseline')
    require(value['freshAppleGates'] == len(value['gates']) == 4, 'Wrong fresh gate scope')
    require(len(value['baselineReceipts']) == value['historicalAppleReceipts'] == 40, 'Wrong historical receipt inventory')
    common.inputs_match(value['inputs'])
    common.inputs_match(value['preparationInputs'])
    return value


def authenticate_archive(path, frozen=None):
    require(path.stat().st_size == BASELINE['bytes'] and digest(path) == BASELINE['sha256'], 'Wrong delivered runtime archive')
    with zipfile.ZipFile(path) as archive:
        raw = archive.read('runtime-validation/result.json')
        require(sha(raw) == BASELINE['runtimeResultSha256'], 'Changed baseline runtime result')
        result = json.loads(raw)
        require(result['result'] == 'passed' and result['engineSource'] == BASELINE['source'], 'Wrong baseline runtime outcome')
        require(result['originalRunConclusion'] == 'failure' and result['originalRun'] == BASELINE['producerRun'], 'Original failure relabeled')
        require(result['validation']['source'] == BASELINE['validationSource'] and result['validation']['run'] == BASELINE['run'], 'Wrong separate runtime validation')
        require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] == 2 and not result['engineRecompiled'] and not result['priorGatesReexecuted'], 'Wrong baseline validation scope')
        require(sha(archive.read(result['correctedSmoke'])) == result['correctedSmokeSha256'], 'Changed baseline runtime smoke')
        original_run = json.loads(archive.read('runtime-validation/original-run.json'))
        original_job = json.loads(archive.read('runtime-validation/original-job.json'))
        original_artifact = json.loads(archive.read('runtime-validation/original-artifact.json'))
        require(original_run['id'] == BASELINE['producerRun'] and original_run['head_sha'] == BASELINE['source'] and original_run['conclusion'] == 'failure' and original_run['run_attempt'] == 1 and original_run['path'] == '.github/workflows/melonx-core.yml', 'Changed original producer identity')
        require(original_job['id'] == BASELINE['producerJob'] and original_job['run_id'] == BASELINE['producerRun'] and original_job['head_sha'] == BASELINE['source'] and original_job['conclusion'] == 'failure', 'Changed original job identity')
        steps = {step['name'] for step in original_job['steps'] if step['conclusion'] == 'success'}
        require(set(result['priorSuccessfulStepsReused']) <= steps and any(step['name'] == result['originalFailedStep'] and step['conclusion'] == 'failure' for step in original_job['steps']), 'Original compilation/smoke conclusions changed')
        require(original_artifact['id'] == BASELINE['producerArtifact'] and original_artifact['digest'] == 'sha256:' + BASELINE['producerArchiveSha256'] and original_artifact['workflow_run']['id'] == BASELINE['producerRun'] and original_artifact['workflow_run']['head_sha'] == BASELINE['source'], 'Changed original artifact origin')
        require('core-validation/result.json' not in archive.namelist(), 'Failed original producer falsely has a successful final result')
        for name, expected in result['compileProofSha256'].items():
            require(sha(archive.read(name)) == expected, 'Changed original compile proof: ' + name)
        compiled = json.loads(archive.read('core-validation/compiled.json'))
        gates = json.loads(archive.read('core-validation/gates.json'))
        for runtime, binary in compiled['binaries'].items():
            raw = archive.read(runtime + '/Ryujinx.Library.dylib')
            require(len(raw) == binary['bytes'] and sha(raw) == binary['sha256'], 'Changed original binary')
            require(sha(archive.read(runtime + '/identity.json')) == compiled['identities'][runtime], 'Changed original binary identity')
        before = json.loads(archive.read('embedded-inputs.json'))
        with zipfile.ZipFile(io.BytesIO(archive.read('embedded-adapted-source.zip'))) as prepared:
            members = inventory(prepared)
        require(len(before) == 120 and len(members) == 160, 'Wrong original source composition')
        receipts = {**gates['receipts'], **gates['retainedReceipts']}
        require(len(receipts) == 40, 'Wrong historical gate inventory')
        for name, expected in receipts.items():
            require(sha(archive.read(name)) == expected and json.loads(archive.read(name))['result'] == 'passed', 'Changed historical receipt: ' + name)
        for name, scope in gates['auxiliaryHistoricalReceipts'].items():
            require(sha(archive.read(name)) == scope['sha256'] and scope['currentFullFixtureProof'] is False, 'Changed historical GAL scope')
        if frozen is not None:
            require(before == frozen['baselinePreparationInputs'] and members == frozen['baselinePreparedMembers'], 'Contract differs from actual delivered baseline')
            require(receipts == frozen['baselineReceipts'] and gates['auxiliaryHistoricalReceipts'] == frozen['baselineAuxiliaryReceipts'], 'Contract historical receipts differ')
        return before, members, gates


def prior_archive():
    frozen = contract()
    api = dict(repository='TarbleFR/RewindBox')
    run = dependencies.api(api, 'actions/runs/' + str(BASELINE['run']))
    job = dependencies.api(api, 'actions/jobs/' + str(BASELINE['job']))
    artifact = dependencies.api(api, 'actions/artifacts/' + str(BASELINE['artifact']))
    require(run['id'] == BASELINE['run'] and run['head_sha'] == BASELINE['validationSource'] and run['status'] == 'completed' and run['conclusion'] == 'success' and run['run_attempt'] == 1 and run['path'] == '.github/workflows/melonx-guard-runtime-validation.yml', 'Wrong baseline runtime run')
    require(job['id'] == BASELINE['job'] and job['head_sha'] == BASELINE['validationSource'] and job['run_id'] == BASELINE['run'] and job['conclusion'] == 'success' and job['run_attempt'] == 1, 'Wrong baseline runtime job')
    require(artifact['id'] == BASELINE['artifact'] and artifact['name'] == BASELINE['artifactName'] and artifact['digest'] == 'sha256:' + BASELINE['sha256'] and artifact['size_in_bytes'] == BASELINE['bytes'] and not artifact['expired'] and artifact['workflow_run']['id'] == BASELINE['run'] and artifact['workflow_run']['head_sha'] == BASELINE['validationSource'], 'Wrong baseline runtime artifact')
    path = ROOT / '.native-sources/melonx-ada4058-runtime510.zip'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open('xb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{BASELINE['artifact']}/zip"], stdout=output, check=True, timeout=300)
    authenticate_archive(path, frozen)
    write(EVIDENCE / 'baseline-origin.json', dict(result='authenticated', baseline=BASELINE, run=run, job=job, artifact=artifact, historicalGatesReexecuted=False))
    return path


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
    require(common.command('git', 'rev-parse', 'HEAD^{tree}', cwd=SOURCE) == '82a29e6f593f6244869481e9a489b8d5154175fe' and not common.command('git', 'status', '--porcelain', cwd=SOURCE), 'Upstream not pristine')
    write(EVIDENCE / 'preflight.json', dict(result='passed', execution=common.execution(), system='Darwin', architecture='arm64', preparationInputs=frozen['preparationInputs'], contractSha256=digest(CONTRACT), smokeInputs={path: digest(ROOT / path) for path in common.HOST_INPUTS}))


def value_at(value, path):
    # A filename can contain dots; structured key paths must stay structured.
    for component in (path.split('.') if isinstance(path, str) else path):
        value = value[component]
    return value


def validate_gate(data, gate, frozen):
    require(data['result'] == 'passed' and data['physicalDeviceTested'] is False, 'Affected fixture scope drift')
    common.inputs_match(data['inputs'])
    for path, expected in gate.get('assertions', {}).items():
        require(value_at(data, path) == expected, 'Affected fixture assertion failed: ' + path)
    for name, expected in data.get('upstreamInputs', {}).items():
        require(digest(child(CONTROL, name)) == expected, 'Changed control dependency: ' + name)
    for name, expected in data.get('preimages', {}).items():
        require(digest(child(CONTROL, name)) == expected, 'Changed control preimage: ' + name)
    for name, expected in data.get('postimages', {}).items():
        require(digest(child(CANDIDATE, name)) == expected, 'Fixture did not compile the final source: ' + name)
    for binding in gate.get('compiledBindings', []):
        expected = frozen['preparedMembers'].get(binding['productionPath'], frozen['untouchedFixtureMembers'].get(binding['productionPath']))
        require(expected is not None and value_at(data, binding['reportPath']) == expected, 'Wrong compiled production binding')
    require(set(gate['requiredPostimages']) <= set(data.get('postimages', {})), 'Missing final source postimage')


def run_gates():
    frozen = contract()
    require(read(EVIDENCE / 'preflight.json')['execution'] == common.execution(), 'Wrong preflight execution')
    archive_path = prior_archive()
    require(not CONTROL.exists() and not CANDIDATE.exists(), 'Stale performance gate sources')
    for path in (CONTROL, CANDIDATE):
        shutil.copytree(SOURCE, path, ignore=shutil.ignore_patterns('.git'))
    historical, auxiliary, baseline_evidence = {}, {}, {}
    with zipfile.ZipFile(archive_path) as archive:
        with zipfile.ZipFile(io.BytesIO(archive.read('embedded-adapted-source.zip'))) as prepared:
            for name in prepared.namelist():
                path = child(CONTROL, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(prepared.read(name))
        for name, expected in frozen['baselineReceipts'].items():
            relative = 'historical-ada4058/' + name
            path = child(OUT, relative); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name)); historical[relative] = expected
        for name, scope in frozen['baselineAuxiliaryReceipts'].items():
            relative = 'historical-ada4058/' + name
            path = child(OUT, relative); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name)); auxiliary[relative] = scope
        for name in BASELINE_EVIDENCE:
            relative = 'baseline-ada4058/' + name
            path = child(OUT, relative); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name)); baseline_evidence[relative] = digest(path)
    subprocess.run([sys.executable, str(ROOT / 'build-utils/melonx/prepare_embedded.py'), str(CANDIDATE)], check=True, timeout=300)
    require(read(OUT / 'embedded-inputs.json') == frozen['preparationInputs'], 'Gate preparation drift')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        require(inventory(archive) == frozen['preparedMembers'], 'Gate final source composition drift')
    for name, expected in frozen['untouchedFixtureMembers'].items():
        require(digest(child(CONTROL, name)) == digest(child(CANDIDATE, name)) == expected, 'Changed unadapted production dependency: ' + name)
    receipts = {}
    for gate in frozen['gates']:
        target = child(OUT, gate['report'])
        require(not target.exists(), 'Stale affected receipt: ' + gate['report'])
        argv = [arg.replace('{baseline}', str(CONTROL)).replace('{candidate}', str(CANDIDATE)) for arg in gate['arguments']]
        subprocess.run([sys.executable, str(ROOT / gate['script']), *argv], check=True, timeout=gate['timeoutSeconds'])
        validate_gate(read(target), gate, frozen)
        receipts[gate['report']] = digest(target)
    require(all(digest(child(CANDIDATE, path)) == expected for path, expected in frozen['preparedMembers'].items()), 'Fixture modified final candidate')
    write(EVIDENCE / 'gates.json', dict(result='passed', execution=common.execution(), receipts=receipts, freshAppleGates=len(receipts), reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=40, historicalGatesReexecuted=False, retainedReceipts=historical, retainedDisposition=frozen['retainedDisposition'], retainedChangedDependencies=frozen['retainedChangedDependencies'], auxiliaryHistoricalReceipts=auxiliary, baselineEvidenceSha256=baseline_evidence, physicalDeviceTested=False, retainedScope='Authentic delivered Ada/510 evidence. Changed declared production/preparation dependencies remain historical-only; fresh affected fixtures bind the exact new prepared source.'))


def compiled():
    frozen = contract(); gates = read(EVIDENCE / 'gates.json')
    require(gates['execution'] == common.execution(), 'Gate execution changed')
    require(read(OUT / 'embedded-inputs.json') == frozen['preparationInputs'], 'Compiled preparation changed')
    with zipfile.ZipFile(OUT / 'embedded-adapted-source.zip') as archive:
        require(inventory(archive) == frozen['preparedMembers'], 'Compiled source composition changed')
        require(all(archive.read(name) == child(SOURCE, name).read_bytes() for name in archive.namelist()), 'Archive differs from compiled source')
    for name, expected in {**gates['receipts'], **gates['retainedReceipts'], **gates['baselineEvidenceSha256']}.items():
        require(digest(child(OUT, name)) == expected, 'Gate/provenance receipt changed: ' + name)
    for name, scope in gates['auxiliaryHistoricalReceipts'].items():
        require(digest(child(OUT, name)) == scope['sha256'], 'Changed auxiliary historical proof')
    identities, binaries = {}, {}
    for runtime in ('ios-arm64', 'iossimulator-arm64'):
        directory = OUT / runtime
        identity = read(directory / 'identity.json'); binary = directory / 'Ryujinx.Library.dylib'
        require(identity['host'] == common.execution()['source'] and identity['adaptations'] == frozen['preparationInputs'] and identity['runtimeIdentifier'] == runtime and identity['source'] == read(ROOT / 'build-utils/melonx/source.json'), 'Wrong compiled identity')
        require(digest(binary) == identity['sha256'] and binary.stat().st_size == identity['size'] and len(identity['exports']) == 47 and identity['embeddedLibraryAbi'] == 2, 'Wrong binary or ABI')
        require(identity['status'] == 'compiled-not-gameplay-tested' and identity['embeddedSessionDeviceVerified'] is False, 'Unexpected compiled gameplay claim')
        symbols = {line.split()[-1] for line in (directory / 'exports.txt').read_text().splitlines() if line.split()}
        require(all('_' + name in symbols for name in identity['exports']), 'Missing native export')
        require('platform ' + ('IOS' if runtime == 'ios-arm64' else 'IOSSIMULATOR') + '\n' in (directory / 'platform.txt').read_text(), 'Wrong native platform')
        common.command('xcrun', 'lipo', str(binary), '-verify_arch', 'arm64')
        identities[runtime] = digest(directory / 'identity.json')
        binaries[runtime] = dict(sha256=digest(binary), bytes=binary.stat().st_size)
    write(EVIDENCE / 'compiled.json', dict(result='passed', execution=common.execution(), identities=identities, binaries=binaries, adaptationCount=len(frozen['preparationInputs']), preparedMembers=len(frozen['preparedMembers']), freshAppleGates=frozen['freshAppleGates'], reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=40, embeddedArchiveSha256=digest(OUT / 'embedded-adapted-source.zip'), physicalDeviceTested=False, gameplayTested=False))



def verify_performance_smoke(report):
    """Recheck complete final collector events from the two real guest sessions."""
    require(report.get('performanceDiagnosticsRequired') is True, 'Current runtime omitted required diagnostics')
    sessions = report['homebrewGuestSvcSessions']
    finals = report['performanceDiagnosticsFinalSessions']
    require(len(sessions) == len(finals) == 2, 'Missing final diagnostic sessions')
    previous_sequence = 0
    for index, (session, final) in enumerate(zip(sessions, finals, strict=True), 1):
        generation = session['generation']
        require(type(generation) is int and generation > 0 and final['session'] == session['session'] == index and
                final['generation'] == generation, 'Wrong final diagnostic generation')
        event = final['event']
        require(event['stage'] == 'performance' and event['status'] == 'final' and event['nativeStatus'] == 0 and
                event['generation'] == generation and type(event['sequence']) is int and
                event['sequence'] > max(previous_sequence, session['svcSequence']), 'Stale or failed final diagnostic event')
        require(type(event['pid']) is int and event['pid'] > 0 and isinstance(event['timestamp'], str) and
                bool(event['timestamp']) and isinstance(event['diagnostic'], str), 'Incomplete final diagnostic event')
        value = json.loads(event['diagnostic'])
        require(value['schema'] == 1 and value['generation'] == generation and value['final'] is True,
                'Wrong final diagnostic payload')
        def nonnegative(number):
            return type(number) in (int, float) and math.isfinite(number) and number >= 0
        require(nonnegative(value['windowMs']), 'Invalid final diagnostic window')
        require(isinstance(value['phases'], dict) and bool(value['phases']) and
                all(isinstance(row, list) and len(row) == 3 and all(nonnegative(number) for number in row)
                    for row in value['phases'].values()), 'Invalid final phase metrics')
        for key in ('counts', 'managed'):
            require(isinstance(value[key], dict) and bool(value[key]) and all(nonnegative(number) for number in value[key].values()),
                    'Invalid final ' + key + ' metrics')
        previous_sequence = event['sequence']
    require(sessions[0]['generation'] != sessions[1]['generation'], 'Repeated diagnostic generation')
    return len(finals)


def finalize():
    frozen = contract()
    final_sessions = verify_performance_smoke(read(OUT / 'runtime-smoke/actual-runtime.json'))
    common.finalize()
    path = EVIDENCE / 'result.json'; result = read(path)
    result.update(performanceCoreContractSha256=digest(CONTRACT), freshAppleGates=frozen['freshAppleGates'], reusedAppleGates=frozen['reusedAppleGates'], historicalAppleReceipts=40, deliveredBaseline=BASELINE, performanceDiagnosticsFinalSessions=final_sessions, fpsGainProven=False)
    for name in ('build-utils/melonx/verify_performance_core.py', 'build-utils/melonx/performance-core-contract.json'):
        result['inputs'][name] = digest(ROOT / name)
    write(path, result)
    (OUT / 'CORE_DELIVERY.md').write_text('# RewindBox Hogwarts performance Core\n\n' + json.dumps(dict(execution=common.execution(), binaries=result['binaries'], freshAppleGates=frozen['freshAppleGates'], reusedScopedAppleReceipts=frozen['reusedAppleGates'], historicalAppleReceipts=40, physicalDeviceTested=False, fpsGainProven=False), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare_dependencies', 'preflight', 'run_gates', 'compiled', 'finalize'))
    globals()[parser.parse_args().phase]()
