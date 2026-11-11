#!/usr/bin/env python3
"""Offline verification of a downloaded standard delivery (manifest-driven; no network access).

Reproduces the checks of docs/evidence/rewind610/download610-verification.json for any build of the
standard recipe: the four encrypted transport parts against the saved API metadata and their own
manifest, the private recipient key (kept outside Git) against the manifest recipient, decryption,
the IPA against SHA256SUMS and the signer receipt, the native image inventory and fingerprints
against the manifest expectations (replaced engines equal their pins, retained engines the base),
the eight bundle versions, the packaged identity and the offline validators, run from an exported
copy of the build's effective tree.

    python3 build-utils/verify_downloaded_delivery.py --build 611 --parts DIR --api DIR \
        --key /private/delivery-611.key --work EMPTY_DIR --report docs/evidence/rewind611/download611-verification.json

--parts holds part00.zip .. part03.zip (the downloaded transport artifacts); --api holds the saved
run-attempt.json, jobs.json and artifacts.json of the delivery run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
for _part in ('.github/diagnostics', 'build-utils', 'packages/dolphin_internal_bridge/ci'):
    if str(ROOT / _part) not in sys.path:
        sys.path.insert(0, str(ROOT / _part))

import standard_delivery as sd  # noqa: E402
from validate_single_ipa_distribution import S2ARM_EXTENSIONS, S2ARM_IDENTITY  # noqa: E402

PART_MEMBERS = {'data.bin', 'format.json', 'password.rsa', 'manifest.json'}
FORMAT = {'cipher': 'AES-256-CBC PBKDF2 200000', 'keyEnvelope': 'RSA OAEP SHA256', 'content': 'tar',
          'publication': 'encrypted delivery only'}
PARTS = 4


def require(ok, message):
    if not ok:
        raise SystemExit('VERIFICATION FAILED: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def api_binding(api, build, repo):
    """The saved API metadata of the delivery run: a successful standard delivery requesting this build."""
    run = load(api / 'run-attempt.json')
    source = run['head_sha']
    require(run['path'] == sd.WORKFLOW and run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['head_branch'] == sd.BRANCH and sd.HEX40.fullmatch(source), 'Wrong delivery run attempt')
    require(sd.subject_build(repo.subject(source)) == build, 'The delivery commit subject does not request this build')
    jobs = load(api / 'jobs.json')
    jobs = jobs.get('jobs', jobs)
    by_name = {job['name']: job for job in jobs}
    require(set(by_name) == set(sd.JOB_NAMES) and len(jobs) == len(sd.JOB_NAMES), 'Wrong delivery jobs')
    for name, job in by_name.items():
        require(job['run_id'] == run['id'] and job['head_sha'] == source and job['run_attempt'] == run['run_attempt'],
                'Job from another run: ' + name)
    require(by_name['preflight']['conclusion'] == by_name['application']['conclusion'] == 'success',
            'The preflight or application job did not succeed')
    artifacts = load(api / 'artifacts.json')
    artifacts = artifacts.get('artifacts', artifacts)
    for item in artifacts:
        require(item['workflow_run']['id'] == run['id'] and item['workflow_run']['head_sha'] == source and
                item['expired'] is False, 'Artifact from another run or expired: ' + item['name'])
    metadata = {name: sha((api / name).read_bytes()) for name in ('run-attempt.json', 'jobs.json', 'artifacts.json')}
    return run, by_name, {item['name']: item for item in artifacts}, metadata


def read_part(path, index, record):
    raw = Path(path).read_bytes()
    require(len(raw) == record['size_in_bytes'] and record['digest'] == 'sha256:' + sha(raw),
            f'Downloaded part {index} differs from its API digest')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(set(names) == PART_MEMBERS and len(names) == len(PART_MEMBERS), f'Unexpected part {index} members')
        require(archive.testzip() is None, f'Part {index} ZIP CRC failure')
        files = {name: archive.read(name) for name in names}
    return raw, files


def transport(parts_directory, artifacts, artifact, source, run, build):
    """Four parts carrying one manifest and key envelope; returns (manifest, pieces, payload, envelope)."""
    pieces, manifest, envelope, fmt, data = [], None, None, None, []
    for index in range(PARTS):
        name = f'{artifact}-part{index:02d}'
        require(name in artifacts, 'Missing artifact ' + name)
        raw, files = read_part(Path(parts_directory) / f'part{index:02d}.zip', index, artifacts[name])
        value = json.loads(files['manifest.json'])
        manifest = manifest or value
        require(value == manifest, 'Manifests differ between parts')
        envelope = envelope or files['password.rsa']
        fmt = fmt or files['format.json']
        require(files['password.rsa'] == envelope and files['format.json'] == fmt, 'Envelope differs between parts')
        record = manifest['parts'][index]
        require(record['index'] == index and record['bytes'] == len(files['data.bin']) and
                record['sha256'] == sha(files['data.bin']), f'Part {index} payload differs from its manifest')
        pieces.append(dict(index=index, name=name, artifactId=artifacts[name]['id'], zipBytes=len(raw), zipSHA256=sha(raw),
                           bytes=record['bytes'], sha256=record['sha256']))
        data.append(files['data.bin'])
    require(manifest['schemaVersion'] == 1 and manifest['source'] == source and manifest['run'] == run and
            manifest['build'] == build and manifest['encrypted'] is True and manifest['rebuilt'] is False,
            'Wrong transport manifest identity')
    require(json.loads(fmt) == FORMAT and manifest['files']['format.json'] == dict(bytes=len(fmt), sha256=sha(fmt)) and
            manifest['files']['password.rsa'] == dict(bytes=len(envelope), sha256=sha(envelope)),
            'Wrong transport format or key envelope')
    payload = b''.join(data)
    require(manifest['files']['artifact.tar.enc'] == dict(bytes=len(payload), sha256=sha(payload)),
            'Reassembled payload differs from its manifest')
    return manifest, pieces, payload, envelope


def recipient_matches(public_key, private_key):
    committed = subprocess.check_output(['openssl', 'pkey', '-pubin', '-in', str(public_key), '-outform', 'DER'])
    derived = subprocess.check_output(['openssl', 'pkey', '-in', str(private_key), '-pubout', '-outform', 'DER'])
    require(committed == derived, 'The private key does not belong to the manifest recipient')
    return sha(committed)


def decrypt(payload, envelope, private_key, work):
    """Decrypt into work/delivery; the password never leaves a 0700 temporary directory."""
    encrypted = work / 'artifact.tar.enc'
    encrypted.write_bytes(payload)
    secret = Path(tempfile.mkdtemp(prefix='delivery-secret-', dir=work))
    os.chmod(secret, 0o700)
    tar_path = work / 'artifact.tar'
    try:
        (secret / 'password.rsa').write_bytes(envelope)
        subprocess.run(['openssl', 'pkeyutl', '-decrypt', '-inkey', str(private_key), '-in', str(secret / 'password.rsa'),
                        '-out', str(secret / 'password'), '-pkeyopt', 'rsa_padding_mode:oaep',
                        '-pkeyopt', 'rsa_oaep_md:sha256'], check=True)
        os.chmod(secret / 'password', 0o600)
        subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-d', '-pbkdf2', '-iter', '200000', '-salt',
                        '-pass', 'file:' + str(secret / 'password'), '-in', str(encrypted), '-out', str(tar_path)],
                       check=True)
    finally:
        shutil.rmtree(secret)
    encrypted.unlink()
    destination = work / 'delivery'
    members = []
    with tarfile.open(tar_path) as archive:
        for member in archive.getmembers():
            if member.name in ('.', './'):
                require(member.isdir(), 'Unexpected root entry')
                continue
            name = member.name[2:] if member.name.startswith('./') else member.name
            require(member.isfile() and name and '/' not in name and name not in ('.', '..'),
                    'Unsafe delivery tar member: ' + member.name)
            members.append(member)
        destination.mkdir(parents=True, exist_ok=False)
        for member in members:
            member.name = member.name[2:] if member.name.startswith('./') else member.name
            archive.extract(member, destination, filter='data')
    tar_path.unlink()
    return destination, sorted(member.name for member in members), not secret.exists()


def run_validator(name, arguments, cwd, logs):
    log = logs / (name + '.log')
    with open(log, 'wb') as handle:
        code = subprocess.run([sys.executable, '-E', '-s', *map(str, arguments)], cwd=cwd, stdout=handle,
                              stderr=subprocess.STDOUT, timeout=1800).returncode
    return dict(name=name, exitCode=code, logSHA256=sha(log.read_bytes()))


def effective_checkout(repo, manifest, source, target):
    """An exported copy of the build's effective tree at the delivered source (product effective, recipe at source)."""
    entries = repo.entries(source)
    for path, entry in manifest['product']['restore'].items():
        if entry is None:
            entries.pop(path, None)
        else:
            entries[path] = (entry['mode'], entry['gitBlob'])
    repo.export(entries, target)
    return target


def verify(args):
    repo = sd.Repo(ROOT)
    require(args.work.is_dir() and not any(args.work.iterdir()), 'The work directory must exist and be empty')
    run, jobs, artifacts, metadata = api_binding(args.api, args.build, repo)
    source, run_id, attempt = run['head_sha'], run['id'], run['run_attempt']
    manifest = json.loads(repo.show(source, sd.manifest_path(args.build)))
    require(manifest['status'] == 'frozen' and not sd.manifest_errors(manifest), 'The delivered manifest is not frozen')
    for group in sd.TEST_GROUPS:
        expected = 'success' if manifest['tests'][group]['mode'] == 'fresh' else 'skipped'
        require(jobs[group]['conclusion'] == expected, f'The {group} job conclusion contradicts the manifest')
    artifact = sd.artifact_name(args.build, source, attempt, 'cold')
    transport_manifest, pieces, payload, envelope = transport(args.parts, artifacts, artifact, source, run_id, args.build)
    recipient = manifest['recipient']
    public_raw = repo.show(source, recipient['path'])
    require(sha(public_raw) == recipient['sha256'], 'The committed recipient differs from the manifest')
    public_key = args.work / 'recipient.pem'
    public_key.write_bytes(public_raw)
    recipient_der = recipient_matches(public_key, args.key)
    delivery, members, secret_removed = decrypt(payload, envelope, args.key, args.work)
    del payload
    ipa_name = f'RewindBox-Build{args.build}-{source}-cold.ipa'
    ipa = delivery / ipa_name
    require(ipa.is_file(), 'Missing ' + ipa_name)
    sums = (delivery / 'SHA256SUMS').read_text().splitlines()
    require(len(sums) == 1, 'Unexpected SHA256SUMS')
    digest, _, listed = sums[0].partition('  ')
    ipa_sha = sd.sha_file(ipa)
    require(Path(listed).name == ipa_name and digest == ipa_sha, 'The IPA differs from SHA256SUMS')
    signed = load(delivery / 'signed-payload-identity.json')
    validation = load(delivery / 'standard-ipa-validation.json')
    require(signed['ipaSha256'] == ipa_sha and signed['ipaBytes'] == ipa.stat().st_size and signed['build'] == args.build,
            'The signer receipt is not bound to these bytes')
    require(validation['result'] == 'passed' and validation['ipaSHA256'] == ipa_sha and
            validation['ipaBytes'] == ipa.stat().st_size, 'The CI validation receipt is not bound to these bytes')
    from rewind607_delivery import zip_payloads
    from verify_ipa import macho
    complete = zip_payloads(ipa)
    actual = {name: record['fingerprint'] for name, record in complete.items()}
    require(actual == signed['images'], 'Final ZIP images differ from the sealed receipt')

    def read_source(path):
        return repo.show(source, path)
    base = sd.verify_base(manifest, read_source)
    images = sd.check_images(actual, base, manifest)
    pubspec = read_source('pubspec.yaml').decode()
    version = next(line.partition(':')[2].strip().strip('"\'').split('+')[0]
                   for line in pubspec.splitlines() if line.startswith('version:'))
    root = sd.APP_ROOT
    melonx_pin = json.loads(read_source(manifest['components']['melonx']['pin']))
    with zipfile.ZipFile(ipa) as archive:
        require(archive.testzip() is None, 'IPA ZIP CRC failure')
        names = archive.namelist()
        plists = sorted(n for n in names if n == root + 'Info.plist' or
                        (n.startswith(root + 'PlugIns/') and n.endswith('.appex/Info.plist') and n.count('/') == 4))
        bundles = {}
        for name in plists:
            info = plistlib.loads(archive.read(name))
            bundles[name[len(root):]] = dict(CFBundleIdentifier=info['CFBundleIdentifier'],
                CFBundleVersion=str(info['CFBundleVersion']), CFBundleShortVersionString=info['CFBundleShortVersionString'],
                MinimumOSVersion=info.get('MinimumOSVersion'))
        if root + S2ARM_IDENTITY in names:
            # Switch 2 (S2Arm) private test IPA only, never the common IPA: S2ArmJITHelper.appex is the eighth extension.
            s2arm = {f'PlugIns/{name}/Info.plist' for name in S2ARM_EXTENSIONS}
            require(s2arm <= set(bundles) and len(bundles) == 8 + len(s2arm) and all(
                b['CFBundleVersion'] == str(args.build) and b['CFBundleShortVersionString'] == version
                for b in bundles.values()), 'Wrong bundle versions (S2Arm identity: the application and its eight '
                'extensions, S2ArmJITHelper.appex included)')
        else:
            require(len(bundles) == 8 and all(b['CFBundleVersion'] == str(args.build) and
                    b['CFBundleShortVersionString'] == version for b in bundles.values()), 'Wrong bundle versions')
        identity_raw = archive.read(root + sd.IDENTITY)
        identity = json.loads(identity_raw)
        require(identity == validation['identity'] and identity['build'] == args.build and
                identity['application']['source'] == source and identity['physicalDeviceTested'] is False,
                'The packaged identity differs from the CI receipt')
        native = json.loads(archive.read(root + 'MeloNX-native-identity.json'))
        require(native['sourceCoreIdentity']['host'] == melonx_pin['source'] and
                native['sourceCoreIdentity']['sha256'] == melonx_pin['binaries']['ios-arm64']['sha256'] and
                native['compiledPayloadFingerprints']['MeloNXCore'] == melonx_pin['packagedFingerprint'],
                'The packaged MeloNX Core is not the pinned replaced Core')
        engines = {}
        for kind in ('dolphin', 'armsx2'):
            name = manifest['components'][kind]['image']
            image = macho(archive.read(root + name))
            require(image['codeSignature'] is True, 'Unsigned retained engine: ' + kind)
            engines[kind] = dict(fingerprint=actual[name], exports=len(image['definedSymbols']))
        rpcs3_image = macho(archive.read(root + manifest['components']['rpcs3']['image']))
        pin = json.loads(read_source(manifest['components']['rpcs3']['pin']))
        added = sorted('_' + n for n in pin['exports']['added'])
        require(set(added) <= set(rpcs3_image['definedSymbols']), 'The replaced RPCS3 Core lacks its added exports')
        effective = effective_checkout(repo, manifest, source, args.work / 'effective-tree')
        helper = archive.read(root + 'PlugIns/MeloNXJITHelper.appex/melonx-universal.js')
        require(helper == (effective / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes(),
                'The MeloNX JIT helper differs from the effective source')
    logs = args.work / 'validator-logs'
    logs.mkdir()
    reports = args.work / 'validator-reports'
    reports.mkdir()
    validators = [
        run_validator('melonx', ['build-utils/validate_melonx_ipa.py', ipa, '--report', reports / 'melonx.json'], effective, logs),
        run_validator('neoplay', ['build-utils/validate_neoplay_ipa.py', ipa, '--build-number', args.build,
                                  '--commit', source, '--report', reports / 'neoplay.json'], effective, logs),
        run_validator('shaders', ['build-utils/validate_shader_compiler_ipa.py', ipa, '--build-number', args.build,
                                  '--report', reports / 'shaders.json'], effective, logs),
        run_validator('legal', ['build-utils/validate_legal_bundle_ipa.py', ipa, '--build-number', args.build,
                                '--commit', source], effective, logs),
        run_validator('no-kartpad', ['build-utils/validate_no_kartpad_ipa.py', ipa, '--build-number', args.build,
                                     '--report', reports / 'no-kartpad.json'], effective, logs),
        run_validator('no-dusklight', ['build-utils/validate_no_dusklight_ipa.py', ipa, '--build-number', args.build,
                                       '--report', reports / 'no-dusklight.json'], effective, logs),
    ]
    require(all(v['exitCode'] == 0 for v in validators), 'Offline validator failure: ' + json.dumps(validators))
    report = dict(schema=1, result='passed-offline-checks', build=args.build, version=version,
        execution=dict(source=source, tree=repo.tree_of(source), run=run_id, attempt=attempt, conclusion=run['conclusion']),
        jobs={name: dict(id=job['id'], conclusion=job['conclusion']) for name, job in sorted(jobs.items())},
        apiMetadataSHA256=metadata, manifest=dict(path=sd.manifest_path(args.build),
                                                  sha256=sha(read_source(sd.manifest_path(args.build)))),
        transport=dict(manifest=transport_manifest, pieces=pieces),
        decryptedRegularFiles=len(members), decryptedFiles=members, secretFilesRemoved=secret_removed,
        recipientPublicKeyDER_SHA256=recipient_der, privateKeyMatchesRecipient=True,
        ipa=dict(name=ipa_name, bytes=ipa.stat().st_size, sha256=ipa_sha, sha256sumsMatched=True,
                 signerReceiptMatched=True),
        binaryValidation=dict(versions=bundles, bundleCount=len(bundles), nativeImageCount=len(actual),
                              imagesChangedFromBase=images['changedFromBase'],
                              undeclaredImageChanges=images['undeclaredChanges'],
                              replacedFingerprints=manifest['images']['replacedFingerprints'],
                              retainedFingerprintsVerified=images['retainedVerified'], engines=engines,
                              packagedIdentity=sd.IDENTITY, packagedIdentityBuild=identity['build'],
                              packagedIdentitySHA256=sha(identity_raw)),
        validators=validators, sourceCheckoutModified=False, compilationPerformedHere=False,
        networkCallsPerformed=False, cryptographicSignatureVerificationPerformedHere=False,
        physicalDeviceTested=False, gameplayTested=False, appleProvisioningVerified=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=1) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--build', type=int, required=True)
    parser.add_argument('--parts', type=Path, required=True)
    parser.add_argument('--api', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    require(not str(args.key.resolve()).startswith(str(ROOT.resolve()) + os.sep),
            'Keep the private recipient key outside the repository')
    report = verify(args)
    print(json.dumps(dict(result=report['result'], ipa=report['ipa'], changed=report['binaryValidation']['imagesChangedFromBase'],
                          validators=[(v['name'], v['exitCode']) for v in report['validators']]), indent=2))


if __name__ == '__main__':
    main()
