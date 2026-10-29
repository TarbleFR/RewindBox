#!/usr/bin/env python3
"""Verify the actual private IPA595 with its unchanged committed validators.

No network, compiler, native executable, codesign or private key is used.
The source checkout is read-only: verified source bytes are copied to a
temporary mirror before importing validators with output-directory side effects.
The encrypted archive/decrypted directory relation is established by the
separate delivery decryption operation; this program never handles its key.
"""
import argparse
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
SOURCE = 'd2e5029f8d7ca33eec279546d64a7f908285e804'
RUN = 40928805790
JOB = 123641427943
BUILD = 595
VERSION = '0.0.8'
WORKFLOW = '.github/workflows/rewind595-baseline-delivery.yml'
RPC_EVIDENCE = 'docs/evidence/rpcs3-runtime-refinement-20261029/apple-core/success-f42573af'
CORE_ZIP = (29118830, '4956f76388cbe2da7eeb87f45980a91391d05e3f71af16fdb163668efe3e2cad')
CORE_DIAGNOSTICS = (207828, '0c0e01d4a75affd50dc209223f6f974c31021658db7ae62fb59a356080b6d745')
MELONX_ZIP = (87451078, 'defa8224442ccd455c7fa0542702abd2711294461818664ef168711f4baff912')
# These exact post-signing containers were observed in the authenticated IPA.
# delivery_benchmark.seal() fingerprints only thin images before/after signing;
# these hashes must not be represented as evidence of pre-signing equality.
FAT_CONTAINERS = {
    'Frameworks/App.framework/App': (23762512, '04b9a2b8ac4471a5704ae32645bc02a1ee7b981049f77370cd443b93065a05fd'),
    'Frameworks/objective_c.framework/objective_c': (165392, '76c35d43663fbcec182d307ee8c43d5a0476880745236ea1979ed3467e198d8d'),
    'Frameworks/sqlite3.framework/sqlite3': (1648496, 'b542ae8763ec8288d3c3267839da48f080aadbd8ea1ea2a0bc27d82af0f8d6c3'),
}
MACHO_MAGICS = {
    b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce',
    b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca',
}
CODE_SHA256 = {
    '.github/diagnostics/rpcs3runtime595_delivery_core.py': '3d972046396da51ed2f5a4e418ac113d902bfee92c70c42246de3b7604c53ee3',
    '.github/diagnostics/rewind595_engine.py': 'e7f7db2e8226d24d61df7f7ba768846c1b8b2c6504ca209fc07f27f99784221a',
    'build-utils/validate_rpcs3_core595_ipa.py': '9c51fd759e2ad079142db64cf58ca3404b6629df07195a0a4ffb835d8461b5f1',
    'build-utils/validate_melonx_engine595_ipa.py': 'e08d7844bafb0affee284cf1b789e5e9507f4e783c8cc0cc0e0c018422e8c3b8',
    'build-utils/delivery_benchmark.py': '00200fe0ce97eca6b2e90004a848dfe32b59d185df83a06b798dd38c67202ccb',
    'packages/dolphin_internal_bridge/ci/verify_ipa.py': '0bd457d94dfe8e54209a5d351527acf717b7ba68d1e0001b512b8f9ca7629c2c',
}
MELONX_METADATA = {
    'actions/runs/40906908049': ('run.json', '024400115b1ef7b88451e45a09c8ea4f0d33f1f44669af4686c7a7bb72c0b99c'),
    'actions/jobs/123564059910': ('job.json', '21feb9dba6c091abc85d2db3aaa7fd7238085290ef6740d4e60383d31501d102'),
    'actions/artifacts/12912462226': ('artifact.json', '754b91e6d364d43f43dd4d6f3360f33965d8370ae285948e882e9fc4c60ca200'),
}
EXTENSIONS = {
    'ARMSX2JITHelper.appex', 'DolphinJITHelper.appex', 'RPCS3JITHelper.appex',
    'MeloNXJITHelper.appex', 'MeloNXRamDonor.appex', 'NeoSwapDonor.appex',
    'NeoSwapPageRelay.appex',
}
STEPS = {
    'Verify the reviewed NeoSwap host source is the source CocoaPods will compile',
    'Compile Release device binary with measured AOT and Xcode phases',
    'Verify the signed RPCS3 runtime candidate receipt against its authenticated original payload',
    'Verify the signed MeloNX optimization engine595 against its original payload',
    'Verify final signed legal bundle and application and extension versions',
    'Upload encrypted IPA and verification reports',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Absent or linked JSON input: ' + str(path))
    return json.loads(path.read_bytes())


def safe_zip(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), 'Duplicate ZIP members')
    for name in names:
        p = PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in name,
                'Unsafe ZIP member: ' + name)
    require(archive.testzip() is None, 'ZIP CRC mismatch')
    return names


def verified_zip(path, contract):
    path = Path(path)
    size, digest = contract
    require(path.stat().st_size == size and file_sha(path) == digest,
            'Archive differs from its fixed metadata: ' + str(path))
    with zipfile.ZipFile(path) as archive:
        names = safe_zip(archive)
    return dict(bytes=size, sha256=digest, members=len(names), crcValid=True)


def api_map(replies):
    def call(endpoint):
        require(endpoint in replies, 'Unexpected offline API endpoint: ' + endpoint)
        return json.loads(json.dumps(replies[endpoint]))
    return call


def delivery_metadata(directory, encrypted_zip):
    directory = Path(directory)
    run, job, artifact = (read_json(directory / name) for name in ('run.json', 'job.json', 'artifact.json'))
    require(run['id'] == RUN and run['head_sha'] == SOURCE and run['path'] == WORKFLOW and
            run['run_attempt'] == 1 and run['status'] == 'completed' and run['conclusion'] == 'success',
            'Private delivery has not succeeded on the reviewed source')
    require(run['repository']['full_name'] == 'TarbleFR/RewindBox', 'Wrong delivery repository')
    require(job['id'] == JOB and job['run_id'] == RUN and job['head_sha'] == SOURCE and
            job['run_attempt'] == 1 and job['status'] == 'completed' and job['conclusion'] == 'success',
            'Wrong or unsuccessful delivery job')
    require(not any(x['conclusion'] == 'failure' for x in job['steps']), 'Failed delivery step')
    passed = {x['name'] for x in job['steps'] if x['conclusion'] == 'success'}
    require(STEPS <= passed, 'Required delivery steps absent: ' + repr(STEPS - passed))
    require(artifact['name'] == f'RewindBox-Build{BUILD}-{SOURCE}-cold' and not artifact['expired'] and
            artifact['workflow_run']['id'] == RUN and artifact['workflow_run']['head_sha'] == SOURCE,
            'Wrong encrypted delivery artifact')
    require(artifact['digest'].startswith('sha256:'), 'Missing delivery digest')
    transport = verified_zip(encrypted_zip, (artifact['size_in_bytes'], artifact['digest'][7:]))
    with zipfile.ZipFile(encrypted_zip) as archive:
        require(set(archive.namelist()) == {'artifact.tar.enc', 'format.json', 'password.rsa'},
                'Unexpected private delivery envelope')
        envelope = json.loads(archive.read('format.json'))
        require(envelope == dict(cipher='AES-256-CBC PBKDF2 200000', keyEnvelope='RSA OAEP SHA256',
                                 content='tar', publication='encrypted delivery only'),
                'Wrong private delivery envelope format')
    return dict(run=RUN, job=JOB, source=SOURCE, attempt=1, artifact=artifact['id'],
                encryptedArchive=transport, savedMetadataSHA256={
                    name: file_sha(directory / name) for name in ('run.json', 'job.json', 'artifact.json')},
                decryptionPerformedSeparately=True)


def literal_maps(script, names):
    result = {}
    for node in ast.parse(script).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in names:
                result[name] = ast.literal_eval(node.value)
    require(set(result) == set(names), 'Missing literal engine source contracts')
    return result


def source_mirror(repo, mirror, core_zip, melonx_zip):
    """Copy only exact committed bytes; never run a checkout hook or fetch."""
    paths = set(CODE_SHA256)
    with zipfile.ZipFile(core_zip) as archive:
        identity = json.loads(archive.read('identity.json'))
        paths.update(identity['runtime_followup_input_sha256'])
        paths.update(identity['core_input_sha256'])
    maps = literal_maps((repo / '.github/diagnostics/rewind595_engine.py').read_text(),
                        ('INPUT_SHA256', 'RECIPE_SHA256', 'RUNTIME_SHA256', 'SOURCE_CONTRACT_SHA256'))
    for values in maps.values():
        paths.update(values)
    paths.update(RPC_EVIDENCE + '/' + name for name in (
        'artifact-verification.json', 'reuse-verification.json', 'github-metadata.json',
        'core/identity.json', 'diagnostics/runtime592-proof.json'))
    paths.update((
        'build-utils/melonx/source.json',
        'docs/evidence/melonx-hogwarts-timer-20261029/candidate.json',
        'docs/evidence/melonx-hogwarts-core-20261029/independent-apple-verification.json',
        'docs/evidence/melonx-hogwarts-followup-20261029/integration.json'))
    with zipfile.ZipFile(melonx_zip) as archive:
        gates = json.loads(archive.read('core-validation/gates.json'))
        for name in gates['receipts']:
            paths.update(json.loads(archive.read(name))['inputs'])
        reused = json.loads(archive.read('core-validation/reused-core84-gates.json'))
        paths.update('docs/evidence/melonx-hogwarts-core-20261029/apple-core/' + name
                     for name in reused['receipts'])
    # Copy transitive repository-local Python imports unchanged, including the
    # independent distribution/entitlement parser used by verify_ipa.validate().
    searched = set()
    while True:
        todo = sorted(p for p in paths if p.endswith('.py') and p not in searched)
        if not todo:
            break
        for path in todo:
            searched.add(path)
            tree = ast.parse((repo / path).read_text())
            for node in ast.walk(tree):
                modules = ([x.name for x in node.names] if isinstance(node, ast.Import) else
                           [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                for module in modules:
                    for prefix in ('build-utils', '.github/diagnostics', 'packages/dolphin_internal_bridge/ci'):
                        relative = prefix + '/' + module.replace('.', '/') + '.py'
                        if (repo / relative).is_file():
                            paths.add(relative)
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
    raw_tree = subprocess.check_output(['git', 'ls-tree', '-rz', SOURCE, '--', *sorted(paths)], cwd=repo, env=env)
    blobs = {}
    for record in raw_tree.split(b'\0'):
        if not record:
            continue
        meta, name = record.split(b'\t', 1)
        mode, kind, digest = meta.decode().split()
        require(kind == 'blob' and mode in ('100644', '100755'), 'Unexpected source object type')
        blobs[name.decode()] = digest
    require(set(blobs) == paths, 'Some validator/source inputs are absent from the delivery commit')
    hashes = {}
    for name in sorted(paths):
        source = repo / name
        require(source.is_file() and not source.is_symlink(), 'Missing/linked source: ' + name)
        data = source.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        require(blob == blobs[name], 'Current source differs from the delivery commit: ' + name)
        hashes[name] = sha(data)
        if name in CODE_SHA256:
            require(hashes[name] == CODE_SHA256[name], 'Reviewed validator changed: ' + name)
        target = mirror / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return hashes


def load_validators(mirror, core_zip, diagnostics_zip, melonx_zip, melonx_metadata, temporary):
    for relative in ('build-utils', '.github/diagnostics', 'packages/dolphin_internal_bridge/ci'):
        sys.path.insert(0, str(mirror / relative))
    candidate = importlib.import_module('rpcs3runtime595_delivery_core')
    require(candidate.ROOT == mirror, 'RPCS3 module was not loaded from the isolated source mirror')
    metadata = read_json(mirror / RPC_EVIDENCE / 'github-metadata.json')
    replies = {f'actions/runs/{candidate.CORE_RUN}': metadata['run'],
               f'actions/runs/{candidate.CORE_RUN}/jobs?per_page=100': metadata['jobs']}
    replies.update({f"actions/artifacts/{x['id']}": x for x in metadata['artifacts']['artifacts']})
    candidate.api = api_map(replies)
    archives = {'artifact': core_zip, 'diagnosticsArtifact': diagnostics_zip}
    def archive_path(key):
        require(key in archives, 'Unexpected offline RPCS3 archive request: ' + key)
        candidate.core_run()
        return archives[key]
    candidate._archive = archive_path
    rpc = importlib.import_module('validate_rpcs3_core595_ipa')
    engine = importlib.import_module('rewind595_engine')
    require(engine.ROOT == mirror and rpc.ROOT == mirror, 'Validator module location changed')
    engine.NEW = temporary / 'melonx-engine'
    engine.NEW.mkdir()
    with zipfile.ZipFile(melonx_zip) as archive:
        archive.extractall(engine.NEW)  # names/CRC were verified before any extraction
    engine_replies = {}
    for endpoint, (name, digest) in MELONX_METADATA.items():
        path = melonx_metadata / name
        require(file_sha(path) == digest, 'Saved MeloNX API response changed: ' + name)
        engine_replies[endpoint] = read_json(path)
    engine.api = api_map(engine_replies)
    melon = importlib.import_module('validate_melonx_engine595_ipa')
    require(melon.ROOT == mirror, 'MeloNX validator was not loaded from the source mirror')
    identity = temporary / 'rpcs3-core-identity.json'
    with zipfile.ZipFile(core_zip) as archive:
        identity.write_bytes(archive.read('identity.json'))
    return rpc, melon, identity


def evidence_report(directory, name, hashes):
    path = directory / name
    data = read_json(path)
    hashes[name] = file_sha(path)
    return data


def fat_image(data, name, benchmark):
    """Account for each exact mono-ARM64 fat file, without inventing a CI seal."""
    require(name in FAT_CONTAINERS, 'Unexpected fat Mach-O location: ' + name)
    expected_size, expected_sha = FAT_CONTAINERS[name]
    require(len(data) == expected_size and sha(data) == expected_sha,
            'Post-signing fat Mach-O differs from the authenticated IPA: ' + name)
    magic, count, cpu, subtype, offset, length, alignment = struct.unpack_from('>7I', data)
    require((magic, count, cpu, subtype, offset, alignment) ==
            (0xcafebabe, 1, 0x0100000c, 0, 16384, 14) and
            offset + length == len(data) and data[28:offset] == bytes(offset - 28),
            'Unexpected fat Mach-O architecture table or padding: ' + name)
    payload = data[offset:offset + length]
    require(payload[:4] == b'\xcf\xfa\xed\xfe', 'Fat slice is not thin ARM64: ' + name)
    image = importlib.import_module('verify_ipa').macho(data)
    require(image['architecture'] == 'arm64' and image['fileType'] == 6 and
            image['platform'] == 2 and image['codeSignature'] is True and
            image['id'] == '@rpath/' + name.removeprefix('Frameworks/'),
            'Unexpected fat slice identity, platform or signature payload: ' + name)
    return dict(container='fat32', bytes=len(data), sha256=sha(data),
                architectureCount=count, architecture='arm64', cpuSubtype=subtype,
                sliceOffset=offset, sliceBytes=length, sliceAlignmentExponent=alignment,
                sliceSHA256=sha(payload), paddingZero=True, trailingBytes=0,
                postSigningPayloadFingerprint=benchmark.payload_fingerprint(payload),
                codeSignaturePayloadPresent=True, preSigningComparisonAvailable=False,
                coveredByCISigningPreservationReport=False)


def verify_payload(args, mirror, rpc, melon, identity, source_hashes, transport):
    artifact = args.artifact_root
    report_hashes = {}
    ipa_sha, ipa_bytes = file_sha(args.ipa), args.ipa.stat().st_size
    checksums = (artifact / 'SHA256SUMS').read_text().splitlines()
    require(len(checksums) == 1, 'Expected exactly one delivered IPA checksum')
    match = re.fullmatch(r'([0-9a-f]{64})\s+\*?(.+)', checksums[0])
    require(match is not None and match.group(1) == ipa_sha and
            PurePosixPath(match.group(2)).name == f'RewindBox-Build{BUILD}-{SOURCE}-cold.ipa',
            'IPA does not match the decrypted delivery checksum')
    report_hashes['SHA256SUMS'] = file_sha(artifact / 'SHA256SUMS')
    with zipfile.ZipFile(args.ipa) as archive:
        names = safe_zip(archive)
        roots = {name[:-10] for name in names if name.startswith('Payload/') and
                 len(name.split('/')) == 3 and name.endswith('.app/Info.plist')}
        require(roots == {'Payload/NeoStation.app/'}, 'Wrong application root')
        root = next(iter(roots))
        infos = {name: plistlib.loads(archive.read(name)) for name in names
                 if name == root + 'Info.plist' or
                 (name.startswith(root + 'PlugIns/') and name.endswith('.appex/Info.plist'))}
        require(len(infos) == 8 and {PurePosixPath(name).parent.name for name in infos if '.appex/' in name} == EXTENSIONS,
                'Expected the main application and exactly seven helpers')
        for name, info in infos.items():
            require(str(info['CFBundleVersion']) == str(BUILD) and info['CFBundleShortVersionString'] == VERSION,
                    'Wrong application/helper version: ' + name)
        main = infos[root + 'Info.plist']
        require(main['CFBundleIdentifier'] == 'com.neogamelab.neostation' and
                main['CFBundleDisplayName'] == 'RewindBox' and main['CFBundleSupportedPlatforms'] == ['iPhoneOS'],
                'Wrong application identity/platform')
        legal = json.loads(archive.read(root + 'Legal/BUILD_SOURCE_IDENTITY.json'))
        require(legal['host_commit'] == SOURCE and legal['build_number'] == str(BUILD),
                'Wrong embedded legal source identity')
        require(sha(archive.read(root + 'Legal/Sources/BUILD_SOURCE_EVIDENCE.json')) == legal['build_source_evidence_sha256'],
                'Packaged source evidence does not match the legal identity')
        signed = evidence_report(artifact, 'signed-payload-identity.json', report_hashes)
        require(signed['ipaSha256'] == ipa_sha and signed['ipaBytes'] == ipa_bytes and
                signed['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True and
                signed['abiMetadataUnchangedBySigning'] is True and signed['sideStoreAppleReSigningRequired'] is True,
                'Signing preservation receipt does not match this IPA')
        benchmark = importlib.import_module('delivery_benchmark')
        actual_images = {}
        fat_images = {}
        for name in names:
            if name.endswith('/'):
                continue
            with archive.open(name) as stream:
                magic = stream.read(4)
            if magic in MACHO_MAGICS:
                require(name.startswith(root), 'Unexpected Mach-O location: ' + name)
                relative = name[len(root):]
                if magic == b'\xcf\xfa\xed\xfe':
                    actual_images[relative] = benchmark.payload_fingerprint(archive.read(name))
                else:
                    require(magic == b'\xca\xfe\xba\xbe', 'Unexpected Mach-O format: ' + name)
                    fat_images[relative] = fat_image(archive.read(name), relative, benchmark)
        require(len(actual_images) == 85 and actual_images == signed['images'],
                'Actual signed thin Mach-O payloads differ from the CI preservation report')
        require(set(fat_images) == set(FAT_CONTAINERS) and not set(fat_images) & set(actual_images),
                'Unexpected inventory of the three post-signing fat containers')
        actual_image_paths = set(actual_images) | set(fat_images)
        signatures = evidence_report(artifact, 'signature.json', report_hashes)
        require(str(signatures['build']) == str(BUILD) and signatures['version'] == VERSION and
                signatures['bundleIdentifier'] == main['CFBundleIdentifier'] and
                signatures['minimumIOS'] == main['MinimumOSVersion'] and signatures['architectures'] == ['arm64'] and
                signatures['installationMethod'] == 'SideStore re-signing' and
                signatures['directAppleInstallationReady'] is False and signatures['deviceInstallationTested'] is False,
                'Wrong Apple signing-report identity')
        targets = {'.'}
        for name in names:
            if not name.startswith(root):
                continue
            rel = name[len(root):]
            parts = PurePosixPath(rel).parts
            for index, part in enumerate(parts):
                if part.endswith(('.framework', '.appex', '.app')):
                    targets.add('/'.join(parts[:index + 1]))
            if rel.endswith('.dylib') and not any(part.endswith('.framework') for part in parts[:-1]):
                targets.add(rel)
        records = signatures['signatures']
        require(len(records) == len({x['bundle'] for x in records}) == len(targets) == 88 and
                {x['bundle'] for x in records} == targets,
                'Wrong signed-component inventory')
        require(all(x['signatureVerified'] is True and x['signature'] == 'adhoc' and
                    x['appleProvisioningVerified'] is False for x in records),
                'Apple signing report does not contain all successful ad hoc checks')
    version = evidence_report(artifact, 'version-validation.json', report_hashes)
    require(version['result'] == 'passed' and version['build'] == BUILD and version['version'] == VERSION and
            set(version['bundles']) == set(infos), 'CI version inventory differs')
    store = evidence_report(artifact, 'neoswap-host-source595.json', report_hashes)
    store_bytes = (mirror / 'native/neoswap-storage/Store.cpp').read_bytes()
    require(store == dict(result='passed', source='native/neoswap-storage/Store.cpp',
                          compiledSource='packages/neo_swap/ios/Classes/Storage/Store.cpp',
                          sha256=sha(store_bytes), bytes=len(store_bytes),
                          cocoaPodsSourcesEntryPresent=True, nativeSuitesReplayed=False),
            'CI did not compile the reviewed host Store.cpp')
    rpc_result = rpc.validate(args.ipa, BUILD, identity)
    melon_result = melon.validate(args.ipa, BUILD)
    require(rpc_result == evidence_report(artifact, 'rpcs3-runtime-candidate-ipa-validation.json', report_hashes),
            'RPCS3 signed validation differs from the CI receipt')
    require(melon_result == evidence_report(artifact, 'melonx-engine595-ipa-validation.json', report_hashes),
            'MeloNX signed validation differs from the CI receipt')
    structural = importlib.import_module('verify_ipa').validate(args.ipa)
    ci_structure = evidence_report(artifact, 'final-structure.json', report_hashes)
    require({k: v for k, v in structural.items() if k != 'ipa'} ==
            {k: v for k, v in ci_structure.items() if k != 'ipa'},
            'Actual IPA structure differs from the CI receipt')
    require(len(structural['machOImages']) == 88 and
            set(structural['machOImages']) == {root + name for name in actual_image_paths} and all(
                value['codeSignature'] is True and value['architecture'] == 'arm64'
                for value in structural['machOImages'].values()),
            'The exhaustive 88-image inventory, architecture or signature payload differs')
    return dict(result='passed', build=BUILD, version=VERSION, source=SOURCE, run=RUN, job=JOB,
                ipa=dict(name=args.ipa.name, sha256=ipa_sha, bytes=ipa_bytes, zipEntries=len(names), crcValid=True),
                transport=transport, applicationAndExtensions={name:dict(build=str(info['CFBundleVersion']),
                    version=info['CFBundleShortVersionString']) for name, info in infos.items()},
                actualMachOImages=88, thinMachOImages=85, fatMachOContainers=3, signingReportRecords=88,
                thinImagesFingerprint=actual_images, fatImages=fat_images,
                actualThinPayloadsMatchCISigningPreservationReport=True,
                signingPreservationCoverage=dict(thinImagesComparedBeforeAfterSigning=85,
                                                fatImagesWithoutBeforeAfterFingerprints=3),
                signaturesReportedVerifiedByAppleCI=True, signatureCryptographicallyVerifiedHere=False,
                rpcS3=rpc_result, melonx=melon_result, hostStore=store,
                structuralValidation=structural['structuralValidation'],
                sourceFilesSHA256=source_hashes, deliveryEvidenceSHA256=report_hashes,
                committedValidatorFunctionsUnmodified=True, sourceCheckoutModified=False,
                subprocessesAfterSourceSnapshot=False, networkUsed=False, nativeTestsExecuted=False,
                nativeBinaryExecuted=False, compilerExecuted=False, physicalDeviceTested=False,
                gameplayMeasured=False, publicRelease=False,
                scope='Actual IPA structure and both signed cores compared with authenticated original archives. '
                      'All 85 thin-image code/data/ABI fingerprints match the Apple preservation receipt. '
                      'The three exact fat containers have one ARM64 slice each and are included in the '
                      'exhaustive 88-image structural inventory; their post-signing hashes and fingerprints '
                      'are recorded, but no before/after-signing comparison exists for them. '
                      'The 88 ad hoc signature checks remain Apple CI evidence; no local cryptographic codesign claim.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'ipa', 'artifact-root', 'core-zip', 'core-diagnostics-zip', 'melonx-zip',
                 'melonx-metadata-dir', 'delivery-metadata-dir', 'delivery-archive', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    for name, value in vars(args).items():
        setattr(args, name, value.resolve())
    require(sys.flags.optimize == 0, 'Run without Python -O: source assertions must remain enabled')
    transport = delivery_metadata(args.delivery_metadata_dir, args.delivery_archive)
    archives = dict(rpcs3=verified_zip(args.core_zip, CORE_ZIP),
                    rpcs3Diagnostics=verified_zip(args.core_diagnostics_zip, CORE_DIAGNOSTICS),
                    melonx=verified_zip(args.melonx_zip, MELONX_ZIP))
    with tempfile.TemporaryDirectory(prefix='rewind595-offline-') as directory:
        temporary = Path(directory)
        mirror = temporary / 'source'
        hashes = source_mirror(args.repo, mirror, args.core_zip, args.melonx_zip)
        rpc, melon, identity = load_validators(mirror, args.core_zip, args.core_diagnostics_zip,
                                             args.melonx_zip, args.melonx_metadata_dir, temporary)
        # All Git reads are finished. A forgotten gh/codesign/compiler fallback
        # must fail visibly instead of making the offline checker run anything.
        def no_process(*unused, **kwargs):
            raise RuntimeError('External process forbidden after offline source authentication')
        subprocess.run = no_process
        subprocess.check_output = no_process
        result = verify_payload(args, mirror, rpc, melon, identity, hashes, transport)
    result['originalArchives'] = archives
    result['verificationScriptSHA256'] = file_sha(Path(__file__))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: result[key] for key in ('result', 'build', 'source', 'ipa',
        'actualMachOImages', 'signingReportRecords', 'signatureCryptographicallyVerifiedHere')}, indent=2))


if __name__ == '__main__':
    main()
