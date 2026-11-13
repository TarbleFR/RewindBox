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
import tarfile
import tempfile
import zipfile

import recover_core_archive as recovery

from validate_runtime_reuse import child, digest, extract_verified, require


ROOT = Path(__file__).resolve().parents[2]
RECIPE = 'build-utils/melonx/prepare_embedded.py'
ARCHIVE = '.native-sources/melonx-core743-recovery.zip'
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


def verified_zip(pin):
    path = child(ROOT, ARCHIVE)
    origin = pin['recovery']['743']['origin']
    require(path.stat().st_size == origin['bytes'] and digest(path) == origin['sha256'],
            'Recovered Core 743 ZIP size/digest mismatch')
    archive = zipfile.ZipFile(path)
    try:
        verify_recovered_inventory(archive, pin)
    except Exception:
        archive.close()
        raise
    return archive


def verify_recovered_inventory(archive, pin):
    # Validate all paths and types before reading/copying any selected member.
    from rewind606_engine import safe_members
    safe_members(archive)
    prefix = 'baseline-engine82/'
    raw = archive.read(prefix + 'authentication/result.json')
    require(sha(raw) == pin['recovery']['historyAuthenticationSha256'],
            'Changed historical authentication receipt')
    receipt = json.loads(raw)
    require(receipt['result'] == 'authenticated' and receipt['repository'] == pin['repository'] and
            receipt['run'] == pin['run'] and receipt['job'] == pin['job'] and
            receipt['artifact'] == pin['artifact'] and receipt['archiveSha256'] == pin['archiveSha256'] and
            receipt['engineSource'] == pin['engineSource'] and
            receipt['historicalTestsReexecuted'] is False and receipt['historicalResultsCoverNewBodies'] is False,
            'Changed engine82 historical scope')
    expected = receipt['historicalReports']
    require(len(expected) == 71, 'Changed retained history inventory')
    actual = {name[len(prefix):] for name in archive.namelist()
              if name.startswith(prefix) and not name.endswith('/')}
    require(actual == set(expected) | {'authentication/' + name + '.json'
            for name in ('run', 'job', 'artifact', 'result')}, 'Unexpected retained history members')
    for name, value in expected.items():
        require(sha(archive.read(prefix + name)) == value, 'Changed retained historical byte: ' + name)
    return receipt


def verify_inputs(old, pin):
    expected_path = child(ROOT, pin['expectedInputs'])
    require(digest(expected_path) == pin['expectedInputsSha256'], 'Expected preparation receipt changed')
    expected = read(expected_path)
    require(len(old) == 74 and len(expected) == 87 and
            set(expected) == set(old) | set(pin['newAdapters']) and
            len(set(pin['newAdapters'])) == 13 and not set(old) & set(pin['newAdapters']),
            'Preparation inventory is not engine82 plus the thirteen adapters')
    require(old[RECIPE] == pin['oldPreparationSha256'] and
            expected[RECIPE] == pin['newPreparationSha256'], 'Unexpected preparation composition')
    for relative, value in old.items():
        if relative != RECIPE:
            require(expected[relative] == value and digest(child(ROOT, relative)) == value,
                    'Existing preparation input changed: ' + relative)
    for relative, value in expected.items():
        require(digest(child(ROOT, relative)) == value, 'Candidate preparation input changed: ' + relative)
    return expected


def verify_retained_history(stage, pin):
    """Check retained identities/proofs; original engine binaries are unavailable."""
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
        require(identity['host'] == pin['engineSource'] and identity['runtimeIdentifier'] == runtime and
                identity['source'] == read(ROOT / 'build-utils/melonx/source.json') and
                identity['adaptations'] == old and expected_binary == identity['sha256'] and
                proof['engine']['binarySha256'][runtime] == expected_binary and
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
    previous = json.loads(archive.read('baseline-engine82/libhac-reuse.json'))
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


def prepare():
    pin = configuration()
    output = child(ROOT, OUTPUT)
    baseline = output / 'baseline-engine82'
    source = child(ROOT, LIBHAC_SOURCE)
    require(not baseline.exists() and not source.exists() and not (ROOT / 'dist/melonx-smoke').exists(),
            'Refusing an existing baseline, LibHac source or smoke output')
    for name in ('ios-arm64', 'iossimulator-arm64', 'identity.json', 'Ryujinx.Library.dylib', 'runtime-smoke', 'runtime-validation'):
        require(not (output / name).exists(), 'Refusing stale native output: ' + name)
    archive_path = child(ROOT, ARCHIVE)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    recovered = recovery.recover(743, archive_path)
    with tempfile.TemporaryDirectory(prefix='melonx-core-baseline-') as temporary:
        stage = Path(temporary).resolve() / 'core743'
        origin = pin['recovery']['743']['origin']
        # This extracts the authenticated Core743 ZIP, never a reconstructed engine82 ZIP.
        with verified_zip(pin):
            pass
        extract_verified(archive_path, stage, dict(archiveBytes=origin['bytes'], archiveSha256=origin['sha256']))
        history = stage / 'baseline-engine82'
        expected = verify_retained_history(history, pin)
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
        shutil.copytree(history, baseline)
    write(output / 'baseline-recovery.json', dict(result='authenticated', recovery=recovered,
        historicalBaselineArtifact=pin['artifact'], historicalBaselineArchiveSha256=pin['archiveSha256'],
        recoveredCoreArchiveSha256=origin['sha256'], copiedLibHacFiles=list(copied),
        expectedCandidateInputs=expected, originalEngine82ArchiveRecovered=False,
        originalEngine82BinariesRecovered=False, historicalTestsReexecuted=False,
        historicalResultsCoverNewBodies=False, republicationRetentionDays=90,
        scope='Retained engine82 history and exact LibHac inputs recovered from Core743; new Core proof is separate.'))
    print('Recovered authenticated engine82 history and exact LibHac inputs from Core743; no historical tests rerun.')


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
        previous = json.loads(archive.read('baseline-engine82/libhac-reuse.json'))
    libhac_source(output / 'libhac-upstream-source.tar', Path(source).resolve())
    write(output / 'libhac-authenticated-reuse.json', dict(result='authenticated',
        baselineArtifact=pin['artifact'], baselineRun=pin['run'], historicalArchiveSha256=pin['archiveSha256'],
        recoveredCoreArchiveSha256=pin['recovery']['743']['origin']['sha256'],
        source=lock, packageSha256=pin['libHac']['packageSha256'], originalLayoutProof=previous,
        testsReexecuted=False, dependencyRecompiled=False, originalPackageRecovered=False))
    return output / 'libhac-feed', lock['package']


def dependencies():
    pin = configuration()
    with verified_zip(pin) as archive:
        expected = json.loads(archive.read('baseline-engine82/runtime-validation/result.json'))['nativeDependencies']
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
        baselineArtifact=pin['artifact'], historicalArchiveSha256=pin['archiveSha256'],
        recoveredCoreArchiveSha256=pin['recovery']['743']['origin']['sha256'],
        nativeDependencies=expected, nativeDependenciesRecompiled=False))
    print('Authenticated all ten original iOS and simulator framework binaries; no rebuild.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'dependencies'))
    args = parser.parse_args()
    (prepare if args.phase == 'prepare' else dependencies)()


if __name__ == '__main__':
    main()
