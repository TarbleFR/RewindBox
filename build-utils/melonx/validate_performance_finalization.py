#!/usr/bin/env python3
"""Validate unchanged, already executed Core bytes after a Python schema fix.

The original producer remains failed. This job executes no native compilation,
fixture or simulator session; its result records a separate validation identity.
"""
import argparse
import copy
import functools
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

import verify_performance_core as performance
from validate_runtime_reuse import verify_smoke_report

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = None
CONFIG = 'build-utils/melonx/finalization-recovery.json'
OUTPUT = 'dist/melonx-finalization'
ARCHIVE = '.native-sources/melonx-ae78-finalize.zip'
PREFIX = 'finalization-validation/'
VERIFIERS = {'build-utils/melonx/verify_performance_core.py',
             'test/melonx_performance_core_contract_test.py'}
REQUIRED_STEPS = {
    'Verify Apple ARM64, exact SDK and reviewed performance Core inputs',
    'Run four affected final-source gates and authenticate scoped Ada runtime evidence',
    'Compile NativeAOT library and verify exported ABI',
    'Bind both new libraries to reviewed sources and gate receipts',
    'Authenticate unchanged native frameworks',
    'Exercise this exact rebuilt engine in an ARM64 iOS app',
    'Preserve the current runtime result including failures',
    'Run actions/upload-artifact@v4',
}
VALIDATION_INPUTS = ('build-utils/melonx/validate_performance_finalization.py', CONFIG,
    'build-utils/melonx/verify_performance_core.py', 'test/melonx_performance_core_contract_test.py',
    'test/melonx_performance_finalization_test.py', '.github/workflows/melonx-performance-finalize.yml')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def current(path):
    if OVERLAY is not None and (OVERLAY / path).is_file():
        return (OVERLAY / path).read_bytes()
    return (ROOT / path).read_bytes()


@functools.lru_cache(maxsize=None)
def original(source, path):
    require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unsafe source input')
    return subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT, timeout=30)


def configuration():
    config = json.loads(current(CONFIG))
    require(config['schemaVersion'] == 1 and set(config['verifierChanges']) == VERIFIERS,
            'Unexpected finalizer-only correction scope')
    source = config['originalProducer']['source']
    raw = original(source, config['contractPath'])
    require(sha(raw) == config['contractSha256'], 'Original compiled contract changed')
    frozen = json.loads(raw)
    updated = copy.deepcopy(frozen)
    for path, change in config['verifierChanges'].items():
        require(frozen['inputs'][path] == change['before'] == sha(original(source, path)) and
                sha(current(path)) == change['after'] and change['before'] != change['after'],
                'Unreviewed finalizer pre/postimage: ' + path)
        updated['inputs'][path] = change['after']
    require(sha(current(config['contractPath'])) == config['currentContractSha256'] and
            json.loads(current(config['contractPath'])) == updated,
            'Current contract changed beyond two verification input hashes')
    for path, expected in {**frozen['inputs'], **frozen['preparationInputs']}.items():
        require(sha(original(source, path)) == expected, 'Original contract source differs: ' + path)
        wanted = config['verifierChanges'].get(path, {}).get('after', expected)
        require(sha(current(path)) == wanted, 'Native, fixture or other reviewed input changed: ' + path)
    require(len(frozen['preparationInputs']) == 125 and len(frozen['preparedMembers']) == 163,
            'Wrong unchanged production composition')
    return config, frozen


def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint],
                                             cwd=ROOT, timeout=120))


def authenticate_origin(config, run, job, artifact):
    pin = config['originalProducer']
    require(run['id'] == pin['run'] and run['head_sha'] == pin['source'] and
            run['head_branch'] == 'Claude' and run['path'] == pin['workflow'] and
            run['run_attempt'] == pin['attempt'] and run['status'] == 'completed' and
            run['conclusion'] == 'failure', 'Original failed run identity changed')
    require(job['id'] == pin['job'] and job['run_id'] == pin['run'] and job['head_sha'] == pin['source'] and
            job['run_attempt'] == pin['attempt'] and job['conclusion'] == 'failure', 'Original job identity changed')
    require([s['name'] for s in job['steps'] if s['conclusion'] == 'failure'] == [config['originalFailedStep']],
            'Original job failed beyond the known Python finalizer')
    require(REQUIRED_STEPS <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Missing successful original compilation, fixtures or real smoke')
    require(artifact['id'] == pin['artifact'] and artifact['name'] == pin['name'] and
            artifact['size_in_bytes'] == pin['bytes'] and artifact['digest'] == 'sha256:' + pin['sha256'] and
            not artifact['expired'] and artifact['workflow_run']['id'] == pin['run'] and
            artifact['workflow_run']['head_sha'] == pin['source'], 'Original artifact origin changed')


def inventory(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), 'Duplicate artifact member')
    for name in names:
        path = PurePosixPath(name)
        require(name and not path.is_absolute() and '..' not in path.parts and '\\' not in name and
                ':' not in path.parts[0] and not name.startswith(PREFIX), 'Unsafe artifact path')
        require(archive.getinfo(name).external_attr >> 16 & 0o170000 != 0o120000, 'Artifact symlink')
    require(archive.testzip() is None, 'Original artifact CRC failed')
    return {name: sha(archive.read(name)) for name in names if not archive.getinfo(name).is_dir()}


def verify_archive(path, config, frozen):
    pin = config['originalProducer']
    require(path.stat().st_size == pin['bytes'] and sha(path.read_bytes()) == pin['sha256'], 'Wrong original ZIP bytes')
    with zipfile.ZipFile(path) as archive:
        members = inventory(archive)
        require('core-validation/result.json' not in members, 'Failed producer falsely has a final result')
        for name, expected in config['compileProofSha256'].items():
            require(members[name] == expected, 'Original compile/runtime proof changed: ' + name)
        load = lambda name: json.loads(archive.read(name))
        preflight, compiled, gates = (load('core-validation/' + name + '.json') for name in ('preflight', 'compiled', 'gates'))
        for record in (preflight, compiled, gates):
            execution = record['execution']
            require(record['result'] == 'passed' and execution['source'] == pin['source'] and
                    execution['run'] == pin['run'] and execution['attempt'] == pin['attempt'], 'Original proof execution drift')
        require(preflight['system'] == 'Darwin' and preflight['architecture'] == 'arm64' and
                preflight['contractSha256'] == config['contractSha256'] and
                preflight['preparationInputs'] == frozen['preparationInputs'], 'Wrong original Apple preflight')
        require(compiled['binaries'] == config['binaries'] and compiled['identities'] == config['identities'] and
                compiled['embeddedArchiveSha256'] == members['embedded-adapted-source.zip'], 'Compiled proof differs')
        require(load('embedded-inputs.json') == frozen['preparationInputs'], 'Prepared input inventory differs')
        with zipfile.ZipFile(io.BytesIO(archive.read('embedded-adapted-source.zip'))) as prepared:
            require(performance.inventory(prepared) == frozen['preparedMembers'], 'Original compiled source differs')
        for runtime, expected in config['binaries'].items():
            binary = archive.read(runtime + '/Ryujinx.Library.dylib')
            identity_raw = archive.read(runtime + '/identity.json'); identity = json.loads(identity_raw)
            require(len(binary) == expected['bytes'] and sha(binary) == expected['sha256'] and
                    sha(identity_raw) == config['identities'][runtime], 'Original binary or identity changed')
            require(identity['host'] == pin['source'] and identity['runtimeIdentifier'] == runtime and
                    identity['adaptations'] == frozen['preparationInputs'] and identity['embeddedLibraryAbi'] == 2 and
                    len(identity['exports']) == 47 and identity['embeddedSessionDeviceVerified'] is False,
                    'Original compiled provenance differs')
        require(set(gates['receipts']) == {gate['report'] for gate in frozen['gates']} and
                gates['freshAppleGates'] == 4 and gates['reusedAppleGates'] == frozen['reusedAppleGates'] == 32 and
                gates['historicalAppleReceipts'] == 40 and gates['historicalGatesReexecuted'] is False,
                'Original gate scopes changed')
        before = {**frozen['baselinePreparedMembers'], **frozen['baselineUnadaptedMembers'], **frozen['untouchedFixtureMembers']}
        after = {**frozen['untouchedFixtureMembers'], **frozen['preparedMembers']}
        for gate in frozen['gates']:
            report = load(gate['report'])
            require(report['result'] == 'passed' and report['physicalDeviceTested'] is False, 'Failed original fixture')
            for name, expected in report['inputs'].items():
                require(sha(original(pin['source'], name)) == sha(current(name)) == expected, 'Fixture input changed')
            for name, expected in gate['assertions'].items():
                require(performance.value_at(report, name) == expected, 'Original fixture assertion changed')
            for name, expected in {**report.get('preimages', {}), **report.get('upstreamInputs', {})}.items():
                require(before.get(name) == expected, 'Original fixture control changed')
            for name, expected in report['postimages'].items():
                require(after.get(name) == expected, 'Original fixture final source changed')
            require(set(gate['requiredPostimages']) <= set(report['postimages']), 'Missing original final postimage')
            for binding in gate['compiledBindings']:
                require(binding['productionPath'] in after and performance.value_at(report, binding['reportPath']) == after[binding['productionPath']], 'Compiled fixture binding changed')
        historical = {'historical-ada4058/' + name: value for name, value in frozen['baselineReceipts'].items()}
        require(gates['retainedReceipts'] == historical and gates['retainedDisposition'] == frozen['retainedDisposition'] and
                gates['retainedChangedDependencies'] == frozen['retainedChangedDependencies'], 'Historical proof scopes changed')
        auxiliary = {'historical-ada4058/' + name: scope for name, scope in frozen['baselineAuxiliaryReceipts'].items()}
        require(gates['auxiliaryHistoricalReceipts'] == auxiliary, 'Auxiliary history changed')
        proofs = {**gates['receipts'], **historical, **gates['baselineEvidenceSha256'],
                  **{name: scope['sha256'] for name, scope in auxiliary.items()}}
        for name, expected in proofs.items():
            require(members[name] == expected, 'Original evidence byte changed: ' + name)
        smoke = load('runtime-smoke/actual-runtime.json')
        for name, expected in preflight['smokeInputs'].items():
            require(sha(current(name)) == sha(original(pin['source'], name)) == expected, 'Original smoke input changed')
        verify_smoke_report(smoke, {'simulatorSha256': config['binaries']['iossimulator-arm64']['sha256']}, preflight['smokeInputs'])
        require(smoke['actualNativeAOT'] is True and smoke['gameplayTested'] is False and smoke['iphoneGuestExecutionTested'] is False,
                'Original smoke scope inflated')
        require(performance.verify_performance_smoke(smoke) == 2, 'Missing original final metrics')
        reused = {}
        for name in ('baseline-engine82/authentication/result.json', 'libhac-authenticated-reuse.json', 'native-dependencies-reused.json'):
            require(load(name)['result'] == 'authenticated', 'Original dependency evidence missing')
            reused[name] = members[name]
    return dict(members=members, compiled=compiled, smoke=smoke, reusedEvidenceSha256=reused)


def prepare():
    config, frozen = configuration(); pin = config['originalProducer']
    records = {name: api(endpoint) for name, endpoint in (
        ('run', 'actions/runs/' + str(pin['run'])), ('job', 'actions/jobs/' + str(pin['job'])),
        ('artifact', 'actions/artifacts/' + str(pin['artifact'])))}
    authenticate_origin(config, records['run'], records['job'], records['artifact'])
    path = ROOT / ARCHIVE; path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists() and not (ROOT / OUTPUT).exists(), 'Refusing stale validation output')
    with path.open('xb') as output:
        subprocess.run(['gh', 'api', 'repos/TarbleFR/RewindBox/actions/artifacts/' + str(pin['artifact']) + '/zip'],
                       stdout=output, check=True, timeout=300)
    proof = verify_archive(path, config, frozen)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(ROOT / OUTPUT)
    for name, value in records.items():
        write(ROOT / OUTPUT / PREFIX / ('original-' + name + '.json'), value)
    write(ROOT / OUTPUT / PREFIX / 'original-members.json', proof['members'])
    print('Authenticated original failed producer, exact ZIP and all successful compiled/runtime evidence; no execution replayed.')


def finalize():
    config, frozen = configuration(); directory = ROOT / OUTPUT
    authenticate_origin(config, *(read(directory / PREFIX / ('original-' + name + '.json')) for name in ('run', 'job', 'artifact')))
    proof = verify_archive(ROOT / ARCHIVE, config, frozen)
    require(read(directory / PREFIX / 'original-members.json') == proof['members'], 'Original member inventory changed')
    for name, expected in proof['members'].items():
        require(sha((directory / name).read_bytes()) == expected, 'Original extracted member changed: ' + name)
    regression = directory / PREFIX / 'regression.json'; tested = read(regression)
    require(tested['result'] == 'passed' and tested['checks'] == 26 and tested['originalFailureReproduced'] is True and
            tested['originalFailure'] == config['originalFailure'] and tested['actualRuntimeSha256'] == config['compileProofSha256']['runtime-smoke/actual-runtime.json'] and
            tested['correctedVerifierSha256'] == config['verifierChanges']['build-utils/melonx/verify_performance_core.py']['after'] and
            tested['testSha256'] == sha(current('test/melonx_performance_finalization_test.py')) and
            all(tested[key] is False for key in ('engineExecuted', 'nativeCodeCompiled', 'historicalGatesReexecuted', 'physicalDeviceTested')),
            'Missing current regression of actual saved runtime report')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(os.environ['GITHUB_REPOSITORY'] == 'TarbleFR/RewindBox' and os.environ['GITHUB_SHA'] == source, 'Wrong validation checkout')
    validation = dict(source=source, run=int(os.environ['GITHUB_RUN_ID']), attempt=int(os.environ['GITHUB_RUN_ATTEMPT']),
                      url='https://github.com/TarbleFR/RewindBox/actions/runs/' + os.environ['GITHUB_RUN_ID'])
    result = dict(result='passed', schemaVersion=1, engineSource=config['originalProducer']['source'],
        originalProducer=config['originalProducer'], originalRunConclusion='failure', originalFailedStep=config['originalFailedStep'],
        originalFailure=config['originalFailure'], validation=validation, contractSha256=config['contractSha256'],
        currentContractSha256=config['currentContractSha256'], verifierChanges=config['verifierChanges'],
        compileProofSha256=config['compileProofSha256'], binaries=config['binaries'], identities=config['identities'],
        originalMembersSha256=sha((directory / PREFIX / 'original-members.json').read_bytes()),
        originalMemberCount=len(proof['members']), regressionSha256=sha(regression.read_bytes()),
        guestSvcSessions=proof['smoke']['homebrewGuestSvcSessions'], homebrewSimulatorSessions=2,
        releasedBackingSessions=2, performanceDiagnosticsFinalSessions=2, freshAppleGatesInOriginalProducer=4,
        reusedAppleGatesInOriginalProducer=32, historicalAppleReceipts=40,
        reusedEvidenceSha256=proof['reusedEvidenceSha256'],
        inputs={name: sha(current(name)) for name in (*VALIDATION_INPUTS, config['contractPath'])},
        engineRecompiled=False, priorGatesReexecuted=False, smokeReexecuted=False, physicalDeviceTested=False,
        gameplayTested=False, fpsGainProven=False,
        scope='Separate validation of unchanged successful Apple compilation, fixtures and two actual NativeAOT sessions. Original failed finalizer remains failed.')
    write(directory / PREFIX / 'result.json', result)
    print(json.dumps(dict(result='passed', validation=validation, originalProducer=config['originalProducer'], engineRecompiled=False, priorGatesReexecuted=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'finalize', 'check'))
    parser.add_argument('--repository-root', type=Path)
    parser.add_argument('--overlay', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--metadata-dir', type=Path)
    args = parser.parse_args()
    if args.repository_root or args.overlay or args.archive or args.metadata_dir:
        require(args.phase == 'check', 'Overrides are only for read-only local checks')
    ROOT = args.repository_root.resolve() if args.repository_root else ROOT
    OVERLAY = args.overlay.resolve() if args.overlay else None
    if args.phase == 'check':
        config, frozen = configuration()
        require(args.archive and args.metadata_dir, 'Local check needs actual archive and API metadata')
        authenticate_origin(config, *(read(args.metadata_dir / ('core-' + name + '.json')) for name in ('run', 'job', 'artifact')))
        proof = verify_archive(args.archive, config, frozen)
        print(json.dumps(dict(result='passed-local-read-only', originalMembers=len(proof['members']),
            originalRunConclusion='failure', validatedOriginalSessions=2, engineRecompiled=False, priorGatesReexecuted=False)))
    else:
        globals()[args.phase]()
