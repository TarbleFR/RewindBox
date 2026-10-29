#!/usr/bin/env python3
"""Authenticate engine82 history and its LibHac package without rerunning it.

Old results stay under baseline-engine82 with their original identities. They
are historical evidence, not execution of the new production bodies. The new
gates, NativeAOT binaries and smoke are produced and verified separately.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from validate_runtime_reuse import child, digest, extract_verified, require


ROOT = Path(__file__).resolve().parents[2]
RECIPE = 'build-utils/melonx/prepare_embedded.py'
ARCHIVE = '.native-sources/melonx-engine82.zip'
LIBHAC_SOURCE = '.native-sources/LibHac'
OUTPUT = 'dist/melonx'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def configuration():
    pin = read(ROOT / 'build-utils/melonx/core-baseline.json')
    require(pin['schemaVersion'] == 1, 'Unsupported baseline schema')
    require(digest(ROOT / 'build-utils/melonx/validate_runtime_reuse.py') ==
            pin['validationHelperSha256'], 'Archive validation helper changed')
    return pin


def api(pin, endpoint):
    return json.loads(subprocess.check_output(
        ['gh', 'api', f"repos/{pin['repository']}/{endpoint}"], text=True, timeout=60))


def authenticate_metadata(pin, run, job, artifact):
    require(run['id'] == pin['run'] and run['head_sha'] == pin['source'] and
            run['head_branch'] == pin['branch'] and run['event'] == 'push' and
            run['path'] == pin['workflow'] and run['run_attempt'] == pin['runAttempt'] and
            run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['repository']['id'] == pin['repositoryId'], 'Unexpected baseline validation run')
    require(job['id'] == pin['job'] and job['run_id'] == pin['run'] and
            job['head_sha'] == pin['source'] and job['run_attempt'] == pin['runAttempt'] and
            job['name'] == pin['jobName'] and job['status'] == 'completed' and
            job['conclusion'] == 'success', 'Unexpected baseline validation job')
    for name in pin['requiredSuccessfulSteps']:
        found = [s for s in job['steps'] if s['name'] == name]
        require(len(found) == 1 and found[0]['status'] == 'completed' and
                found[0]['conclusion'] == 'success', 'Missing baseline validation step: ' + name)
    origin = artifact['workflow_run']
    require(artifact['id'] == pin['artifact'] and artifact['name'] == pin['artifactName'] and
            artifact['expired'] is False and artifact['size_in_bytes'] == pin['archiveBytes'] and
            artifact['digest'] == 'sha256:' + pin['archiveSha256'] and
            origin['id'] == pin['run'] and origin['head_sha'] == pin['source'] and
            origin['head_branch'] == pin['branch'] and origin['repository_id'] == pin['repositoryId'],
            'Unexpected baseline artifact')


def verified_zip(pin):
    path = child(ROOT, ARCHIVE)
    require(path.stat().st_size == pin['archiveBytes'] and digest(path) == pin['archiveSha256'],
            'Baseline ZIP size/digest mismatch')
    return zipfile.ZipFile(path)


def verify_inputs(old, pin):
    expected_path = child(ROOT, pin['expectedInputs'])
    require(digest(expected_path) == pin['expectedInputsSha256'], 'Expected preparation receipt changed')
    expected = read(expected_path)
    require(len(old) == 74 and len(expected) == 86 and
            set(expected) == set(old) | set(pin['newAdapters']) and
            len(set(pin['newAdapters'])) == 12 and not set(old) & set(pin['newAdapters']),
            'Preparation inventory is not engine82 plus the twelve adapters')
    require(old[RECIPE] == pin['oldPreparationSha256'] and
            expected[RECIPE] == pin['newPreparationSha256'], 'Unexpected preparation composition')
    for relative, value in old.items():
        if relative != RECIPE:
            require(expected[relative] == value and digest(child(ROOT, relative)) == value,
                    'Existing preparation input changed: ' + relative)
    for relative, value in expected.items():
        require(digest(child(ROOT, relative)) == value, 'Candidate preparation input changed: ' + relative)
    return expected


def verify_history(stage, pin):
    old = read(stage / 'embedded-inputs.json')
    expected = verify_inputs(old, pin)
    proof = read(stage / 'runtime-validation/result.json')
    require(proof['result'] == 'passed' and proof['engineSource'] == pin['engineSource'] and
            proof['validation']['source'] == pin['source'] and proof['validation']['run'] == pin['run'] and
            proof['validation']['runAttempt'] == pin['runAttempt'] and proof['smokeStepOutcome'] == 'success' and
            proof['originalRunConclusion'] == 'failure' and proof['engineRecompiled'] is False,
            'Baseline validation provenance changed')
    for runtime, expected_binary in pin['binarySha256'].items():
        identity_path = stage / runtime / 'identity.json'
        identity = read(identity_path)
        binary = stage / runtime / 'Ryujinx.Library.dylib'
        require(identity['host'] == pin['engineSource'] and identity['runtimeIdentifier'] == runtime and
                identity['source'] == read(ROOT / 'build-utils/melonx/source.json') and
                identity['adaptations'] == old and digest(binary) == expected_binary == identity['sha256'] and
                binary.stat().st_size == identity['size'] and
                digest(identity_path) == proof['engine']['identitySha256'][runtime],
                'Original compiled identity mismatch: ' + runtime)
    smoke = stage / 'runtime-smoke/actual-runtime.json'
    old_smoke = read(stage / 'runtime-smoke-engine82-original-failure/actual-runtime.json')
    require(digest(smoke) == proof['correctedSmokeSha256'] and read(smoke)['result'] == 'passed' and
            read(smoke)['coreSha256'] == pin['binarySha256']['iossimulator-arm64'] and
            old_smoke['result'] == 'failed', 'Missing separate original and corrected smoke proofs')
    return expected


def libhac_members(archive, pin):
    lock = read(ROOT / 'build-utils/melonx/source.json')['libHac']
    identity = json.loads(archive.read('libhac-identity.json'))
    previous = json.loads(archive.read('libhac-reuse.json'))
    package = 'libhac-feed/' + lock['package'] + '.' + lock['version'] + '.nupkg'
    require(identity['source'] == lock and identity['reconstructed'] is True and
            identity['originalPackageRecovered'] is False and
            sha(archive.read(package)) == identity['packageSha256'] == pin['libHac']['packageSha256'] and
            len(archive.read(package)) == identity['packageBytes'] and
            sha(archive.read('libhac-upstream-source.tar')) == identity['upstreamSourceSha256'] == pin['libHac']['sourceSha256'] and
            sha(archive.read('libhac-generated-source.zip')) == pin['libHac']['generatedSha256'],
            'LibHac package/source identity mismatch')
    require(previous['run'] == pin['libHac']['layoutRun'] and previous['job'] == pin['libHac']['layoutJob'] and
            previous['layoutTestsPassed'] == pin['libHac']['layoutTestsPassed'] == 5 and
            previous['libHacSource'] == lock['revision'] and
            previous['packageSha256'] == pin['libHac']['packageSha256'] and
            previous['runConclusion'] == 'failure' and previous['reused'] is True and
            previous['testsReexecuted'] is False, 'LibHac five-test historical proof changed')
    with zipfile.ZipFile(io.BytesIO(archive.read('libhac-generated-source.zip'))) as generated:
        require(len(generated.namelist()) == len(identity['generatedInputs']) and
                set(generated.namelist()) == set(identity['generatedInputs']), 'LibHac generated inventory changed')
        for relative, value in identity['generatedInputs'].items():
            require(sha(generated.read(relative)) == value, 'LibHac generated source mismatch: ' + relative)
    return (package, 'libhac-identity.json', 'libhac-upstream-source.tar', 'libhac-generated-source.zip'), lock


def libhac_source(tar_path, target, extract=False):
    """Read regular files/directories only, with no links or artificial Git state."""
    require(not (target / '.git').exists(), 'LibHac reuse must not fabricate a Git checkout')
    seen, files = set(), set()
    with tarfile.open(tar_path, 'r:') as archive:
        entries = []
        for member in archive.getmembers():
            path = child(target, member.name)
            require(path != target and path not in seen and (member.isfile() or member.isdir()) and
                    '.git' not in Path(member.name).parts, 'Unsafe LibHac source member: ' + member.name)
            seen.add(path)
            entries.append((member, path))
        for member, path in entries:
            if member.isdir():
                if extract:
                    path.mkdir(parents=True, exist_ok=True)
                continue
            files.add(path.relative_to(target).as_posix())
            with archive.extractfile(member) as incoming:
                if extract:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open('xb') as output:
                        shutil.copyfileobj(incoming, output)
                    path.chmod(0o644 | (member.mode & 0o111))
                else:
                    require(path.is_file() and not path.is_symlink() and
                            digest(path) == hashlib.file_digest(incoming, 'sha256').hexdigest(),
                            'Extracted LibHac source changed: ' + member.name)
    require({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file() or p.is_symlink()} == files,
            'Unexpected extracted LibHac source files')


def retain_history(stage, destination):
    retained = {}
    for path in sorted(stage.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(stage).as_posix()
        top = '/' not in relative and path.suffix in ('.json', '.log', '.txt')
        reports = relative.startswith(('runtime-validation/', 'runtime-smoke/', 'runtime-smoke-engine82-original-failure/'))
        identity = relative.startswith(('ios-arm64/', 'iossimulator-arm64/')) and path.suffix in ('.json', '.txt')
        if top or reports or identity or relative == 'embedded-adapted-source.zip':
            target = child(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            retained[relative] = digest(target)
    return retained


def prepare():
    pin = configuration()
    output = child(ROOT, OUTPUT)
    baseline = output / 'baseline-engine82'
    source = child(ROOT, LIBHAC_SOURCE)
    require(not baseline.exists() and not source.exists() and not (ROOT / 'dist/melonx-smoke').exists(),
            'Refusing an existing baseline, LibHac source or smoke output')
    for name in ('ios-arm64', 'iossimulator-arm64', 'identity.json', 'Ryujinx.Library.dylib', 'runtime-smoke', 'runtime-validation'):
        require(not (output / name).exists(), 'Refusing stale native output: ' + name)
    run = api(pin, f"actions/runs/{pin['run']}")
    job = api(pin, f"actions/jobs/{pin['job']}")
    artifact = api(pin, f"actions/artifacts/{pin['artifact']}")
    authenticate_metadata(pin, run, job, artifact)
    archive_path = child(ROOT, ARCHIVE)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists():
        with tempfile.NamedTemporaryFile(dir=archive_path.parent, suffix='.download') as temporary:
            subprocess.run(['gh', 'api', f"repos/{pin['repository']}/actions/artifacts/{pin['artifact']}/zip"],
                           stdout=temporary, check=True, timeout=300)
            temporary.flush()
            candidate = Path(temporary.name)
            require(candidate.stat().st_size == pin['archiveBytes'] and digest(candidate) == pin['archiveSha256'],
                    'Downloaded baseline ZIP failed authentication')
            shutil.copyfile(candidate, archive_path)
    with tempfile.TemporaryDirectory(prefix='melonx-core-baseline-') as temporary:
        stage = Path(temporary).resolve() / 'engine82'
        extract_verified(archive_path, stage, pin)
        expected = verify_history(stage, pin)
        with verified_zip(pin) as archive:
            copied, _ = libhac_members(archive, pin)
            for relative in copied:
                target = child(output, relative)
                require(not target.exists(), 'Refusing existing LibHac output: ' + relative)
            for relative in copied:
                target = child(output, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(relative))
        libhac_source(output / 'libhac-upstream-source.tar', source, extract=True)
        retained = retain_history(stage, baseline)
    for name, document in [('run', run), ('job', job), ('artifact', artifact)]:
        write(baseline / 'authentication' / (name + '.json'), document)
    write(baseline / 'authentication/result.json', dict(result='authenticated', repository=pin['repository'],
        run=pin['run'], job=pin['job'], artifact=pin['artifact'], archiveSha256=pin['archiveSha256'],
        engineSource=pin['engineSource'], historicalReports=retained, copiedLibHacFiles=list(copied),
        unchangedPreparationInputs=73, expectedCandidateInputs=expected,
        oldPreparationInputs=74, candidatePreparationInputs=86, newAdapters=pin['newAdapters'],
        historicalTestsReexecuted=False, historicalResultsCoverNewBodies=False,
        scope='Authenticated history only; new gates, composition, NativeAOT and smoke require separate proof.'))
    print('Authenticated engine82 history, 73 retained inputs, 86 candidate inputs and the original LibHac package.')


def reuse_libhac(engine, source):
    """Return (feed, package ID) only after reauthenticating every reused byte."""
    pin = configuration()
    require(Path(os.environ['MELONX_AUTHENTICATED_BASELINE']).resolve() == child(ROOT, ARCHIVE).resolve(),
            'Unexpected authenticated baseline path')
    require(Path(engine).is_dir() and Path(source).resolve() == child(ROOT, LIBHAC_SOURCE).resolve(),
            'Unexpected engine or LibHac source directory')
    output = child(ROOT, OUTPUT)
    with verified_zip(pin) as archive:
        members, lock = libhac_members(archive, pin)
        for relative in members:
            require(digest(child(output, relative)) == sha(archive.read(relative)),
                    'Copied LibHac input changed: ' + relative)
        previous = json.loads(archive.read('libhac-reuse.json'))
    libhac_source(output / 'libhac-upstream-source.tar', Path(source).resolve())
    write(output / 'libhac-authenticated-reuse.json', dict(result='authenticated',
        baselineArtifact=pin['artifact'], baselineRun=pin['run'], archiveSha256=pin['archiveSha256'],
        source=lock, packageSha256=pin['libHac']['packageSha256'], originalLayoutProof=previous,
        testsReexecuted=False, dependencyRecompiled=False, originalPackageRecovered=False))
    return output / 'libhac-feed', lock['package']


def dependencies():
    pin = configuration()
    with verified_zip(pin) as archive:
        expected = json.loads(archive.read('runtime-validation/result.json'))['nativeDependencies']
    directory = ROOT / 'dist/melonx-native'
    identity_path = directory / 'identity.json'
    require(digest(identity_path) == expected['identitySha256'], 'Native dependency identity changed')
    identity = read(identity_path)
    sources = [ROOT / 'build-utils/melonx' / name for name in ('native-sources.json', 'native-dependencies.json')]
    require(any(p.is_file() for p in sources), 'Missing current native dependency source pins')
    for path in sources:
        if path.is_file():
            require(identity['pins'] == read(path), 'Native dependency source pins changed: ' + path.name)
    names = {'MeloNXMoltenVK', 'MeloNXSDL3', 'MeloNXAvUtil', 'MeloNXAvCodec', 'MeloNXJitSupport'}
    required = {f'{platform}/{name}.framework/{name}' for platform in ('ios', 'iossimulator') for name in names}
    binaries = {entry['path']: entry['sha256'] for entry in identity['binaries']}
    require(len(identity['binaries']) == 10 and set(binaries) == required and binaries == expected['binaries'],
            'Native dependency inventory changed')
    for relative, value in binaries.items():
        require(digest(child(directory, relative)) == value, 'Native dependency bytes changed: ' + relative)
    write(ROOT / OUTPUT / 'native-dependencies-reused.json', dict(result='authenticated',
        baselineArtifact=pin['artifact'], archiveSha256=pin['archiveSha256'],
        nativeDependencies=expected, nativeDependenciesRecompiled=False))
    print('Authenticated all ten original iOS and simulator framework binaries; no rebuild.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'dependencies'))
    args = parser.parse_args()
    (prepare if args.phase == 'prepare' else dependencies)()


if __name__ == '__main__':
    main()
