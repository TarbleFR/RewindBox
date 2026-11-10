#!/usr/bin/env python3
"""Validate the existing ada4058 binaries without replaying gates or compilation."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import validate_runtime_reuse as reuse
from validate_runtime_reuse import child, digest, read, require, write

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'build-utils/melonx/guard-runtime-validation.json'
CORE = ROOT / 'dist/melonx'
EVIDENCE = CORE / 'runtime-validation'
OLD_SMOKE = 'runtime-smoke-ada4058-original-failure'


def inputs_match(pin):
    for path, expected in pin['validationInputs'].items():
        require(digest(child(ROOT, path)) == expected, 'Changed runtime validation input: ' + path)


def verify_original(directory, pin, old_smoke):
    engine = reuse.verify_engine(directory, pin)
    require(engine['binarySha256'] == pin['binarySha256'] and engine['identitySha256'] == pin['identitySha256'], 'Original compiled bytes changed')
    contract_path = ROOT / 'build-utils/melonx/guard-core-contract.json'
    require(digest(contract_path) == pin['coreContractSha256'], 'Changed original Core contract')
    contract = read(contract_path)
    for path, expected in contract['inputs'].items():
        require(digest(child(ROOT, path)) == expected, 'Changed original gate input: ' + path)
    require(read(directory / 'embedded-inputs.json') == contract['preparationInputs'], 'Changed original preparation map')
    for path, expected in pin['compileProofSha256'].items():
        require(digest(child(directory, path)) == expected, 'Changed original compile proof: ' + path)
    preflight = read(directory / 'core-validation/preflight.json')
    gates = read(directory / 'core-validation/gates.json')
    compiled = read(directory / 'core-validation/compiled.json')
    for report in (preflight, gates, compiled):
        require(report['result'] == 'passed' and report['execution']['source'] == pin['source'] and
                report['execution']['run'] == pin['run'] and report['execution']['attempt'] == 1, 'Wrong original proof execution')
    require(compiled['adaptationCount'] == 120 and compiled['preparedMembers'] == 160, 'Wrong compiled source scope')
    require((gates['freshAppleGates'], gates['reusedAppleGates'], gates['historicalAppleReceipts']) == (3, 36, 37), 'Wrong original gate scope')
    archive = directory / 'embedded-adapted-source.zip'
    require(digest(archive) == compiled['embeddedArchiveSha256'], 'Changed prepared source archive')
    with zipfile.ZipFile(archive) as z:
        require(len(z.namelist()) == len(set(z.namelist())) == 160 and
                {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()} == contract['preparedMembers'], 'Changed prepared source inventory')
    require(set(gates['receipts']) == {g['report'] for g in contract['gates']}, 'Wrong original fresh receipt set')
    for path, expected in gates['receipts'].items():
        require(digest(child(directory, path)) == expected, 'Changed original gate receipt: ' + path)
        report = read(child(directory, path))
        require(report['result'] == 'passed' and report['physicalDeviceTested'] is False, 'Wrong gate result/scope')
        require(all(contract['preparedMembers'][n] == h for n, h in report['postimages'].items()), 'Gate/compiled postimage mismatch')
        for n, h in report['inputs'].items():
            require(digest(child(ROOT, n)) == h, 'Changed original fixture input: ' + n)
    require(gates['retainedReceipts'] == {'historical-1630/' + n: h for n, h in contract['baselineReceipts'].items()}, 'Historical receipt scope changed')
    for path, expected in gates['retainedReceipts'].items():
        require(digest(child(directory, path)) == expected, 'Changed historical receipt: ' + path)
    require(gates['auxiliaryHistoricalReceipts'] == {'historical-1630/' + n: s for n, s in contract['auxiliaryHistoricalReceipts'].items()}, 'Historical GAL scope changed')
    for path, scope in gates['auxiliaryHistoricalReceipts'].items():
        require(digest(child(directory, path)) == scope['sha256'] and scope['currentFullFixtureProof'] is False, 'Changed or overstated historical GAL proof')
    for runtime in ('ios-arm64', 'iossimulator-arm64'):
        identity = read(directory / runtime / 'identity.json')
        require(compiled['binaries'][runtime] == dict(sha256=identity['sha256'], bytes=identity['size']) and
                compiled['identities'][runtime] == engine['identitySha256'][runtime], 'Wrong compile/binary binding')
        require(identity['embeddedLibraryAbi'] == 2 and len(identity['exports']) == 47, 'Wrong compiled ABI')
        symbols = {line.split()[-1] for line in (directory / runtime / 'exports.txt').read_text().splitlines() if line.split()}
        require(all('_' + name in symbols for name in identity['exports']), 'Missing compiled export')
    require(not (directory / 'core-validation/result.json').exists(), 'Original failed producer cannot have a final success receipt')
    require(not (directory / old_smoke / 'actual-runtime.json').exists() and
            digest(directory / old_smoke / 'native-runtime.log') == pin['originalNativeLogSha256'], 'Changed original incomplete smoke evidence')
    # Runtime API and owner remain those tested by the original compile source;
    # only the bounded smoke harness changes for this separate validation.
    require(set(preflight['smokeInputs']) == {*reuse.HOST_INPUTS, pin['smoke']['path']}, 'Wrong original smoke input scope')
    for path in reuse.HOST_INPUTS:
        require(digest(ROOT / path) == preflight['smokeInputs'][path], 'Changed original native smoke host: ' + path)
    engine['binaryBytes'] = {r: compiled['binaries'][r]['bytes'] for r in compiled['binaries']}
    return engine


def prepare(pin):
    inputs_match(pin)
    require(not CORE.exists() and not (ROOT / 'dist/melonx-smoke').exists(), 'Refusing stale engine or smoke output')
    run = reuse.api(pin, f"actions/runs/{pin['run']}")
    job = reuse.api(pin, f"actions/jobs/{pin['job']}")
    artifact = reuse.api(pin, f"actions/artifacts/{pin['artifact']}")
    reuse.authenticate_metadata(pin, run, job, artifact)
    dependencies = reuse.verify_dependencies(pin)
    validation = reuse.validation_identity(pin)
    with tempfile.TemporaryDirectory(prefix='melonx-ada4058-reuse-') as temporary:
        archive = Path(temporary) / 'core.zip'
        with archive.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/{pin['repository']}/actions/artifacts/{pin['artifact']}/zip"], stdout=output, check=True, timeout=300)
        staged = Path(temporary) / 'engine'
        reuse.extract_verified(archive, staged, pin)
        engine = verify_original(staged, pin, 'runtime-smoke')
        require(not (staged / OLD_SMOKE).exists() and not (staged / 'runtime-validation').exists(), 'Original artifact already validated')
        (staged / 'runtime-smoke').rename(staged / OLD_SMOKE)
        CORE.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), CORE)
    write(EVIDENCE / 'original-run.json', run)
    write(EVIDENCE / 'original-job.json', job)
    write(EVIDENCE / 'original-artifact.json', artifact)
    write(EVIDENCE / 'preparation.json', dict(
        result='authenticated', engineSource=pin['source'], originalRun=pin['run'], originalJob=pin['job'],
        originalArtifact=pin['artifact'], archiveSha256=pin['archiveSha256'], originalRunConclusion='failure',
        originalFailedStep=pin['failedStep'], originalSmoke=OLD_SMOKE,
        originalSmokeStructuredResultAvailable=False, priorSuccessfulStepsReused=pin['requiredSuccessfulSteps'],
        engine=engine, coreContractSha256=pin['coreContractSha256'], compileProofSha256=pin['compileProofSha256'],
        freshAppleGates=3, reusedAppleGates=36, historicalAppleReceipts=37,
        nativeDependencies=dependencies, validation=validation, engineRecompiled=False,
        nativeDependenciesRecompiled=False, priorGatesReexecuted=False,
        inputs={**pin['validationInputs'], 'build-utils/melonx/guard-runtime-validation.json': digest(CONFIG)}))
    print('Authenticated unchanged ada4058 binaries, 120 preparation inputs, 160 prepared members and the three successful Apple gates.')


def finalize(pin):
    inputs_match(pin)
    preparation = read(EVIDENCE / 'preparation.json')
    require(verify_original(CORE, pin, OLD_SMOKE) == preparation['engine'], 'Compiled engine changed during validation')
    require(reuse.verify_dependencies(pin) == preparation['nativeDependencies'], 'Native dependencies changed')
    require(reuse.validation_identity(pin) == preparation['validation'], 'Validation identity changed')
    for path, expected in preparation['inputs'].items():
        require(digest(child(ROOT, path)) == expected, 'Validation input changed: ' + path)
    output = ROOT / 'dist/melonx-smoke'
    if output.exists():
        shutil.copytree(output, CORE / 'runtime-smoke')
    smoke = CORE / 'runtime-smoke/actual-runtime.json'
    problem = None
    report = {}
    try:
        require(os.environ['MELONX_SMOKE_OUTCOME'] == 'success', 'Corrected smoke step did not succeed')
        report = read(smoke)
        reuse.verify_smoke_report(report, pin, {path: digest(ROOT / path) for path in (*reuse.HOST_INPUTS, pin['smoke']['path'])})
        require(report['actualNativeAOT'] is True and report['gameplayTested'] is False and report['iphoneGuestExecutionTested'] is False, 'Unexpected runtime proof scope')
    except (RuntimeError, OSError, KeyError, TypeError, ValueError) as error:
        problem = str(error)
    result = dict(preparation, result='failed' if problem else 'passed',
                  smokeStepOutcome=os.environ.get('MELONX_SMOKE_OUTCOME'), validationError=problem,
                  correctedSmoke='runtime-smoke/actual-runtime.json',
                  correctedSmokeSha256=digest(smoke) if smoke.exists() else None,
                  homebrewSimulatorSessions=report.get('homebrewSimulatorSessions'),
                  releasedBackingSessions=report.get('actualCoreDonatedBackingSessions'),
                  physicalDeviceTested=False, gameplayTested=False,
                  newArtifactPurpose='unchanged ada4058 Core plus separate runtime validation; original failed producer and compiled identities preserved')
    write(EVIDENCE / 'result.json', result)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write('verified=true\n')
    require(problem is None, problem)
    print('Validated the same compiled binaries with two distinct guest SVC sessions, clean session teardown and backing release.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'finalize'))
    args = parser.parse_args()
    globals()[args.phase](read(CONFIG))
