#!/usr/bin/env python3
"""Authenticate engine 82 and add a runtime proof without recompiling the engine.

The original run failed only its smoke test after successful NativeAOT/ABI and
five new gates. Its immutable ZIP digest authenticates both compiled identities.
Do not rewrite their host/source fields: this workflow is a later validation,
not another engine build. The original failed smoke remains in the artifact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'build-utils/melonx/runtime-validation.json'
CORE = ROOT / 'dist/melonx'
EVIDENCE = CORE / 'runtime-validation'
OLD_SMOKE = 'runtime-smoke-engine82-original-failure'
HOST_INPUTS = (
    'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift',
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def child(root, relative):
    path = PurePosixPath(relative)
    require(relative and '\\' not in relative and not path.is_absolute() and
            '..' not in path.parts, 'Unsafe artifact path: ' + relative)
    target = root.joinpath(*path.parts)
    require(target.resolve().is_relative_to(root.resolve()), 'Path escapes root: ' + relative)
    return target


def api(pin, endpoint):
    return json.loads(subprocess.check_output(
        ['gh', 'api', f"repos/{pin['repository']}/{endpoint}"], text=True, timeout=60))


def authenticate_metadata(pin, run, job, artifact):
    require(run['id'] == pin['run'] and run['head_sha'] == pin['source'] and
            run['head_branch'] == 'Claude' and run['event'] == 'push' and
            run['path'] == '.github/workflows/melonx-core.yml' and
            run['run_attempt'] == pin['runAttempt'] and run['status'] == 'completed' and
            run['conclusion'] == 'failure', 'Unexpected original engine run')
    require(job['id'] == pin['job'] and job['run_id'] == pin['run'] and
            job['head_sha'] == pin['source'] and job['run_attempt'] == pin['runAttempt'] and
            job['name'] == 'core' and job['status'] == 'completed' and
            job['conclusion'] == 'failure', 'Unexpected original engine job')
    steps = job['steps']
    require([step['name'] for step in steps if step['conclusion'] == 'failure'] == [pin['failedStep']],
            'Original failure was not limited to the smoke test')
    require(all(step['status'] == 'completed' and step['conclusion'] in ('success', 'failure', 'skipped')
                for step in steps), 'Original job contains another incomplete or failed step')
    for name in pin['requiredSuccessfulSteps']:
        found = [step for step in steps if step['name'] == name]
        require(len(found) == 1 and found[0]['conclusion'] == 'success', 'Missing prior successful gate: ' + name)
    require(artifact['id'] == pin['artifact'] and artifact['name'] == pin['artifactName'] and
            not artifact['expired'] and artifact['workflow_run']['id'] == pin['run'] and
            artifact['workflow_run']['head_sha'] == pin['source'] and
            artifact['size_in_bytes'] == pin['archiveBytes'] and
            artifact['digest'] == 'sha256:' + pin['archiveSha256'], 'Unexpected engine artifact provenance')


def extract_verified(archive_path, target, pin):
    # Authenticate all bytes before creating or extracting any archive member.
    require(archive_path.stat().st_size == pin['archiveBytes'] and
            digest(archive_path) == pin['archiveSha256'], 'Engine ZIP digest/size mismatch')
    with zipfile.ZipFile(archive_path) as archive:
        seen = set()
        for member in archive.infolist():
            path = child(target, member.filename)
            require(str(path) not in seen, 'Duplicate ZIP member: ' + member.filename)
            seen.add(str(path))
            mode = member.external_attr >> 16
            require(not stat.S_ISLNK(mode), 'ZIP symlink is not permitted: ' + member.filename)
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), 'Unsupported ZIP member type')
        archive.extractall(target)


def verify_engine(directory, pin):
    # These four build inputs are outside prepare_embedded's adaptation map.
    # Their pins were authenticated against the original source's Git blobs.
    for relative, expected in pin['buildInputs'].items():
        require(digest(child(ROOT, relative)) == expected, 'Compiled build recipe changed: ' + relative)
    embedded = read(directory / 'embedded-inputs.json')
    require(len(embedded) == pin['adaptationCount'], 'Unexpected compiled adaptation inventory')
    for relative, expected in embedded.items():
        require(digest(child(ROOT, relative)) == expected, 'Compiled adaptation changed: ' + relative)
    expected_source = read(ROOT / 'build-utils/melonx/source.json')
    identities, binaries = {}, {}
    for runtime in ('ios-arm64', 'iossimulator-arm64'):
        identity_path = directory / runtime / 'identity.json'
        identity = read(identity_path)
        binary = directory / runtime / 'Ryujinx.Library.dylib'
        require(identity['host'] == pin['source'] and identity['source'] == expected_source and
                identity['runtimeIdentifier'] == runtime and identity['adaptations'] == embedded,
                'Compiled identity/source mismatch: ' + runtime)
        require(identity['status'] == 'compiled-not-gameplay-tested' and
                identity['embeddedSessionDeviceVerified'] is False, 'Unexpected device validation claim')
        require(binary.stat().st_size == identity['size'] and digest(binary) == identity['sha256'],
                'Compiled binary digest/size mismatch: ' + runtime)
        identities[runtime] = digest(identity_path)
        binaries[runtime] = identity['sha256']
    require(binaries['iossimulator-arm64'] == pin['simulatorSha256'], 'Wrong simulator engine')
    return {'identitySha256': identities, 'binarySha256': binaries,
            'adaptationCount': len(embedded), 'adaptationsSha256': digest(directory / 'embedded-inputs.json')}


def verify_dependencies(pin):
    directory = ROOT / 'dist/melonx-native'
    identity = read(directory / 'identity.json')
    require(identity['pins'] == read(ROOT / 'build-utils/melonx/native-dependencies.json'),
            'Native dependency source pins changed')
    binaries = {}
    for entry in identity['binaries']:
        require(entry['path'] not in binaries, 'Duplicate native dependency')
        require(digest(child(directory, entry['path'])) == entry['sha256'], 'Native dependency digest mismatch')
        binaries[entry['path']] = entry['sha256']
    names = {'MeloNXMoltenVK', 'MeloNXSDL3', 'MeloNXAvUtil', 'MeloNXAvCodec', 'MeloNXJitSupport'}
    require(set(binaries) == {f'{platform}/{name}.framework/{name}'
                             for platform in ('ios', 'iossimulator') for name in names},
            'Unexpected native dependency inventory')
    return dict(pin['nativeDependencies'], identitySha256=digest(directory / 'identity.json'), binaries=binaries)


def validation_identity(pin):
    checkout = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(os.environ['GITHUB_REPOSITORY'] == pin['repository'] and
            os.environ['GITHUB_SHA'] == checkout, 'Validation checkout identity mismatch')
    return {'source': checkout, 'run': int(os.environ['GITHUB_RUN_ID']),
            'runAttempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
            'url': f"https://github.com/{pin['repository']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
            'purpose': 'runtime validation only; original engine was not recompiled'}


def prepare(pin):
    require(not CORE.exists(), 'Refusing to mix the reused engine with an existing output directory')
    require(not (ROOT / 'dist/melonx-smoke').exists(), 'Refusing stale runtime smoke output')
    require(digest(child(ROOT, pin['smoke']['path'])) == pin['smoke']['sha256'], 'Corrected smoke input changed')
    run = api(pin, f"actions/runs/{pin['run']}")
    job = api(pin, f"actions/jobs/{pin['job']}")
    artifact = api(pin, f"actions/artifacts/{pin['artifact']}")
    authenticate_metadata(pin, run, job, artifact)
    dependencies = verify_dependencies(pin)
    validation = validation_identity(pin)
    with tempfile.TemporaryDirectory(prefix='melonx-engine82-reuse-') as temporary:
        archive_path = Path(temporary) / 'engine82.zip'
        with archive_path.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/{pin['repository']}/actions/artifacts/{pin['artifact']}/zip"],
                           stdout=output, check=True, timeout=300)
        staged = Path(temporary) / 'engine'
        extract_verified(archive_path, staged, pin)
        engine = verify_engine(staged, pin)
        old = read(staged / 'runtime-smoke/actual-runtime.json')
        require(old['result'] == 'failed' and old['coreSha256'] == pin['simulatorSha256'] and
                'homebrew-guest-svc-unconfirmed' in old['diagnostic'], 'Unexpected original smoke failure')
        require(set(old['inputs']) == {*HOST_INPUTS, pin['smoke']['path']}, 'Unexpected smoke host input inventory')
        for relative in HOST_INPUTS:
            require(digest(ROOT / relative) == old['inputs'][relative], 'Smoke host changed: ' + relative)
        require(not (staged / OLD_SMOKE).exists() and not (staged / 'runtime-validation').exists(),
                'Original artifact already contains a reuse validation')
        (staged / 'runtime-smoke').rename(staged / OLD_SMOKE)
        CORE.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), CORE)
    write(EVIDENCE / 'original-run.json', run)
    write(EVIDENCE / 'original-job.json', job)
    write(EVIDENCE / 'original-artifact.json', artifact)
    write(EVIDENCE / 'preparation.json', {
        'result': 'authenticated', 'engineSource': pin['source'], 'originalRun': pin['run'],
        'originalJob': pin['job'], 'originalArtifact': pin['artifact'],
        'archiveSha256': pin['archiveSha256'], 'originalRunConclusion': 'failure',
        'originalFailedStep': pin['failedStep'], 'originalSmoke': OLD_SMOKE + '/actual-runtime.json',
        'priorSuccessfulStepsReused': pin['requiredSuccessfulSteps'], 'engine': engine,
        'buildRecipeSource': pin['source'], 'unchangedBuildInputs': pin['buildInputs'],
        'nativeDependencies': dependencies, 'validation': validation,
        'engineRecompiled': False, 'nativeDependenciesRecompiled': False,
        'priorGatesReexecuted': False,
        'inputs': {relative: digest(ROOT / relative) for relative in (*HOST_INPUTS, pin['smoke']['path'],
            'build-utils/melonx/validate_runtime_reuse.py', 'build-utils/melonx/runtime-validation.json',
            '.github/workflows/melonx-runtime-validation.yml', *pin['buildInputs'])},
    })
    print('Authenticated engine 82 iOS and simulator binaries, original successful gates and 74 unchanged adaptations.')


def verify_smoke_report(report, pin, inputs):
    require(report['result'] == 'passed' and report['coreSha256'] == pin['simulatorSha256'],
            'Corrected smoke did not pass on the authenticated engine')
    require(report['inputs'] == inputs, 'Corrected smoke tested different inputs')
    sessions = report['homebrewGuestSvcSessions']
    require(report['homebrewSimulatorSessions'] == 2 and report['originalHomebrewGuestSvcConfirmed'] is True and
            report['actualCoreDonatedBackingSessions'] == 2 and
            len(sessions) == 2 and [entry['session'] for entry in sessions] == [1, 2] and
            len({entry['svcSequence'] for entry in sessions}) == 2 and
            len({entry['generation'] for entry in sessions}) == 2 and
            sessions[1]['afterSequence'] >= sessions[0]['svcSequence'] and
            all(entry['svcSequence'] > entry['afterSequence'] and entry['generation'] > 0 for entry in sessions),
            'Missing separate SVC evidence for both sessions')


def finalize(pin):
    preparation = read(EVIDENCE / 'preparation.json')
    require(verify_engine(CORE, pin) == preparation['engine'], 'Engine identity changed during smoke')
    require(verify_dependencies(pin) == preparation['nativeDependencies'], 'Native dependencies changed during smoke')
    require(validation_identity(pin) == preparation['validation'], 'Validation run changed')
    for relative, expected in preparation['inputs'].items():
        require(digest(ROOT / relative) == expected, 'Validation input changed: ' + relative)
    output = ROOT / 'dist/melonx-smoke'
    if output.exists():
        shutil.copytree(output, CORE / 'runtime-smoke')
    smoke = CORE / 'runtime-smoke/actual-runtime.json'
    problem = None
    try:
        require(os.environ['MELONX_SMOKE_OUTCOME'] == 'success', 'Corrected smoke step did not succeed')
        report = read(smoke)
        verify_smoke_report(report, pin, {relative: digest(ROOT / relative)
                                         for relative in (*HOST_INPUTS, pin['smoke']['path'])})
    except (RuntimeError, OSError, KeyError, TypeError, ValueError) as error:
        problem = str(error)
    receipt = dict(preparation, result='failed' if problem else 'passed',
        smokeStepOutcome=os.environ.get('MELONX_SMOKE_OUTCOME'), validationError=problem,
        correctedSmoke='runtime-smoke/actual-runtime.json',
        correctedSmokeSha256=digest(smoke) if smoke.exists() else None,
        physicalDeviceTested=False, gameplayTested=False,
        newArtifactPurpose='unchanged engine 82 plus a separate runtime validation; original source identities preserved')
    write(EVIDENCE / 'result.json', receipt)
    # The upload is allowed only after both original binaries and identities
    # have been verified again, even when retaining a failed new smoke.
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output_file:
        output_file.write('verified=true\n')
    require(problem is None, problem)
    print('PASS runtime validation of unchanged engine 82; original failed smoke retained separately.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'finalize'))
    args = parser.parse_args()
    pin = read(CONFIG)
    (prepare if args.phase == 'prepare' else finalize)(pin)


if __name__ == '__main__':
    main()
