"""Private IPA611: delivered609 with only the reviewed fragmented-read MeloNX Core.

The application source is restored to delivered609 (the concurrent 610 lot is
present in the commit but not built) and differs from it only by one Core
preparation input that Xcode never compiles. RPCS3, Dolphin, ARMSX2, libretro
and the MeloNX native frameworks keep the exact bytes and original provenance
that IPA609 used; the Flutter/native test evidence is the authenticated608
record that IPA609 also reused (original 0279198 jobs). Only MeloNXCore is new.
No old suite is executed again.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import zipfile

import rewind611_baseline as tree
import rewind611_engine as engine
import rewind608_producers as producers608
import rpcs3runtime607_core as rpc
# Stateless Mach-O/container parsers already used for delivered607 to 609.
from rewind607_delivery import arm64_payload, app_payloads, zip_payloads

ROOT, BUILD = tree.ROOT, 611
OUT = ROOT / 'build/delivery'
CACHE = ROOT / 'build/components611'
IDENTITY = 'MeloNX-reads-build-identity.json'
WORKFLOW = '.github/workflows/rewind611-melonx-reads-delivery.yml'
WORKFLOW609 = '.github/workflows/rewind609-hogwarts-liveness-delivery.yml'
WORKFLOW608 = '.github/workflows/rewind608-retro-achievements-delivery.yml'
EVIDENCE608 = 'docs/evidence/rewind608'
EVIDENCE609 = 'docs/evidence/rewind609'
RPC607_FINGERPRINT = '7289ce4ef4f723d203995b4a76d5b2e1c2cd5a874e8a72c04b774c7d2dc1d22e'
REUSED = dict(source='0279198b1c33d869550cae3cf35f155b9d3a4f79', tree='67f9f0c891d86b09d04c4f273931eeb0d33f602e',
              run=41293321826, attempt=1)
REUSED_SCOPE = 'e1a10e7ac140b1c018989c59efd59cb0c301f0e460b355663a9700b78e182b1a'
# Exactly the four original successful jobs and archives consumed by delivered608.
REUSED_ARTIFACTS = {
    'flutter': dict(job=124808995458, artifact=13077931904, bytes=12621,
                    sha256='39e91ced6ab771c9a09087db9336cda93d6528ad5a356f0a810f53983f0693ff'),
    'native': dict(job=124808995448, artifact=13078266751, bytes=69659,
                   sha256='8aaf4a7c1f36c68352d143f7962998f30ad6a574c56ee0c8f71cbc5c39e044e9'),
    'dolphin': dict(job=124810929735, artifact=13078193437, bytes=11191038,
                    sha256='9d32c236c79c43cd57053b000dfaba94c4e0d6f627bd04a657f74b36dd58c064'),
    'armsx2': dict(job=124810929747, artifact=13078023872, bytes=14042625,
                   sha256='e4354b47eee93d5dc8d53be070a88cc83ceb8b31ff4f7ccdca2eb2c2067b8763'),
}
# Delivered608 signed payload fingerprints of the retained native Cores.
RETAINED_CORES = {'dolphin': '640e4389559c800087b3d4b2a2748b4c11307ae6a79bc72f59d55430ccddd6fc',
                  'armsx2': 'fab55193e509583b03c0e5b33ae8d8812745b5410d138a53e3779b6257f370d4'}
RETAINED_ARCHIVES = {
    'libretro': dict(artifact=12280822192, run=39455712245,
        source='ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
        name='LibretroCores-ab9361c29f7c9ab769c4263dd8b7427fc4f4c036',
        bytes=55566830, sha256='e06f641dd10409c815787fe1cf4ac6746920360a1023c83b23631b2bd693ba47',
        destination='dist/libretro'),
    'melonx-dependencies': dict(artifact=12458409441, run=39854858591,
        source='66737aa9c959eb5915264bf178f179bda8643314',
        name='MeloNX-native-dependencies-66737aa9c959eb5915264bf178f179bda8643314',
        bytes=49178074, sha256='12a1e4c7bf1c970c218ebddead965a51c3aa57af4d0e1fb5c0523ca8b1340261',
        destination='dist/melonx-native'),
}
sha, git, require = tree.sha, tree.git, tree.require


def save(name, value):
    return producers608.save(OUT / name, value)


def evidence608(name):
    """A committed delivered608 receipt, bound by the pinned608 delivery receipt."""
    raw = (ROOT / EVIDENCE608 / name).read_bytes()
    return raw, json.loads(raw)


def evidence609(name):
    """A committed delivered609 receipt, bound by the pinned609 delivery receipt."""
    raw = (ROOT / EVIDENCE609 / name).read_bytes()
    return raw, json.loads(raw)


def inventory():
    value = json.loads((ROOT / tree.INVENTORY).read_bytes())
    raw, reference = evidence609('signed-payload-identity.json')
    require(sha(raw) == value['inventoryReferenceSHA256'], 'Delivered609 image inventory reference changed')
    original = set(reference['images'])
    require(value['schema'] == 1 and value['build'] == BUILD and value['baselineBuild'] == 609 and
            len(original) == 90 and set(value['baselineImages']) == original and len(value['baselineImages']) == 90 and
            value['addedImages'] == [] and value['removedImages'] == [] and value['expectedImageCount'] == 90 and
            reference['ipaSha256'] == tree.BASELINE['ipaSHA256'], '611 keeps exactly the delivered609 native images')
    return original


def validate_inventory(names):
    expected_names = inventory()
    actual = set(names)
    require(actual == expected_names and len(names) == len(expected_names),
            'Native image inventory differs: missing=' + repr(sorted(expected_names - actual)) +
            ' extra=' + repr(sorted(actual - expected_names)))
    return len(actual)


def seal():
    import delivery_benchmark as benchmark
    app = ROOT / 'build/ios/dolphin-unsigned/Payload/NeoStation.app'
    before = app_payloads(app)
    validate_inventory(before)
    benchmark.seal()
    after = app_payloads(app)
    ipa = ROOT / 'dist/NeoStation.ipa'
    packaged = zip_payloads(ipa)
    require(before == after == packaged, 'Signing/export changed compiled code, data, ABI or an architecture container')
    receipt = json.loads((OUT / 'signed-payload-identity.json').read_bytes())
    complete = {name: record['fingerprint'] for name, record in before.items()}
    require(set(receipt['images']) <= set(complete) and
            all(complete[name] == digest for name, digest in receipt['images'].items()),
            'Signer receipt disagrees with the full native inventory')
    require(receipt['ipaSha256'] == sha(ipa.read_bytes()) and receipt['ipaBytes'] == ipa.stat().st_size and
            receipt['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True and
            receipt['abiMetadataUnchangedBySigning'] is True, 'Wrong signed611 export identity')
    signature = json.loads((OUT / 'signature.json').read_bytes())
    signed_targets = {'.' if name == 'Runner' else name if name.endswith('.dylib') else Path(name).parent.as_posix()
                      for name in before}
    require(len(signed_targets) == 90 and len(signature['signatures']) == 90 and
            all(item['signatureVerified'] is True for item in signature['signatures']) and
            {item['bundle'] for item in signature['signatures']} == signed_targets,
            'Missing, duplicated or failed actual macOS signature verification')
    receipt.update(build=BUILD, images=complete, imageCount=90, retainedImageNames=90, addedImageNames=0,
        architectureContainers={name: record['container'] for name, record in before.items()},
        singleArm64FatImages=sum(record['container'].startswith('single-arm64-fat') for record in before.values()),
        completeNativeInventoryCheckedBeforeAndAfterSigning=True, completeNativeInventoryCheckedInFinalZIP=True)
    return save('signed-payload-identity.json', receipt)


def contract():
    return save('rewind611-host-contract.json', tree.verify())


def baseline():
    result = contract()
    base = tree.BASELINE
    # The delivered609 IPA is attempt 1 of its run; only that attempt is its identity.
    run = engine.api(f"actions/runs/{base['run']}/attempts/{base['attempt']}")
    job = engine.api('actions/jobs/' + str(base['job']))
    require(run['head_sha'] == job['head_sha'] == tree.BASE and
            run['conclusion'] == job['conclusion'] == 'success' and
            run['run_attempt'] == job['run_attempt'] == base['attempt'] and
            job['run_id'] == run['id'] == base['run'] and run['head_branch'] == 'Claude' and
            run['path'] == WORKFLOW609, 'Wrong actual delivered609 run/job')
    return save('rewind611-baseline.json', dict(result='authenticated-run-and-reviewed-source',
        application=result, delivered609=base, previousPrivateIPADownloadedByThisRun=False,
        previousIPAMetadataOrigin='Verified delivery609 receipt committed by the integrator; the private IPA is not a runtime donor.',
        historicalTestsReexecuted=False))


@lru_cache(maxsize=None)
def reused_origin(kind):
    pin = REUSED_ARTIFACTS[kind]
    run = engine.api(f"actions/runs/{REUSED['run']}/attempts/{REUSED['attempt']}")
    require(run['id'] == REUSED['run'] and run['head_sha'] == REUSED['source'] and run['head_branch'] == 'Claude' and
            run['path'] == WORKFLOW608 and run['run_attempt'] == REUSED['attempt'] and run['status'] == 'completed' and
            run['conclusion'] == 'failure', 'The original whole 0279198 run must keep its actual failure')
    job = engine.api('actions/jobs/' + str(pin['job']))
    require(job['id'] == pin['job'] and job['run_id'] == REUSED['run'] and job['head_sha'] == REUSED['source'] and
            job['run_attempt'] == REUSED['attempt'] and job['status'] == 'completed' and job['conclusion'] == 'success' and
            job['name'] == producers608.JOBS[kind], 'Original prerequisite job changed: ' + kind)
    require(producers608.REQUIRED_STEPS[kind] <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Original prerequisite omitted a required step: ' + kind)
    name = f"RewindBox608-{kind}-{REUSED['source']}-attempt{REUSED['attempt']}"
    artifact = engine.api('actions/artifacts/' + str(pin['artifact']))
    require(artifact['id'] == pin['artifact'] and artifact['name'] == name and artifact['size_in_bytes'] == pin['bytes'] and
            artifact['digest'] == 'sha256:' + pin['sha256'] and not artifact['expired'] and
            artifact['workflow_run']['id'] == REUSED['run'] and artifact['workflow_run']['head_sha'] == REUSED['source'],
            'Original prerequisite archive changed or expired: ' + kind)
    _, delivered = evidence608('delivery.json')
    original = delivered['reusedEvidence']['originalArchives'][kind]
    require(original['job'] == pin['job'] and original['artifact'] == pin['artifact'] and
            original['archiveSHA256'] == pin['sha256'] and original['originalJobConclusion'] == 'success' and
            delivered['reusedEvidence']['execution'] == REUSED, 'Delivered608 did not consume this exact archive: ' + kind)
    return dict(result='authenticated', evidenceMode='reused', retainedFrom=608, kind=kind, execution=dict(REUSED),
                job=pin['job'], artifact=pin['artifact'], artifactName=name, archiveSHA256=pin['sha256'],
                archiveBytes=pin['bytes'], expiresAt=artifact['expires_at'])


def fetch_reused(kind):
    value = reused_origin(kind)
    path = CACHE / f'{kind}.zip'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size != value['archiveBytes'] or sha(path.read_bytes()) != value['archiveSHA256']:
        temporary = path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{value['artifact']}/zip"],
                           stdout=output, cwd=ROOT, check=True, timeout=600)
        require(temporary.stat().st_size == value['archiveBytes'] and sha(temporary.read_bytes()) == value['archiveSHA256'],
                'Retained608 prerequisite archive digest/size mismatch: ' + kind)
        temporary.replace(path)
    target = CACHE / kind
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(path) as archive:
        engine.safe_members(archive)
        archive.extractall(target)
    return value, target


def tests():
    import rewind608_checks as checks608
    _, evidence = evidence608('rewind608-tests.json')
    checked = {}
    for kind in ('flutter', 'native'):
        value, directory = fetch_reused(kind)
        receipt = json.loads((directory / 'validation.json').read_bytes())
        require(receipt['result'] == 'passed' and receipt['group'] == kind and receipt['execution'] == value['execution'],
                'Wrong retained608 test execution receipt')
        require(receipt['sourceScopeSHA256'] == REUSED_SCOPE, 'Tests were run on another original reviewed source scope')
        require(receipt['commands'] and all(c['exitCode'] == 0 for c in receipt['commands']),
                'A required retained608 test command did not succeed')
        require([c['name'] for c in receipt['commands']] == checks608.command_names(kind),
                'A required retained608 command was omitted or replaced')
        for command in receipt['commands']:
            require(sha((directory / command['log']).read_bytes()) == command['logSHA256'], 'Retained608 command log changed')
        if kind == 'native':
            require(receipt['xcodeVersion'].startswith('Xcode 16.4\n'), 'Wrong targeted native compiler')
            require('Apple Swift version 6.' in receipt['swiftVersion'], 'Translation was not compiled with Swift6')
        require(evidence[kind]['receipt'] == receipt and evidence[kind]['artifact'] == value['artifact'] and
                evidence[kind]['archiveSHA256'] == value['archiveSHA256'],
                'Delivered608 test evidence is not this exact original receipt')
        checked[kind] = dict(value, receipt=receipt, delivered608Evidence=evidence[kind],
                             testsReexecuted=False, testedInputsUnchangedSince608=True)
    return save('rewind611-tests.json', checked)


def native(kind):
    import rewind608_reuse as reuse608
    value, directory = fetch_reused(kind)
    record = json.loads((directory / 'producer608.json').read_bytes())
    original_inputs = reuse608.original_input_hashes(kind)
    require(record['schema'] == 1 and record['build'] == 608 and record['kind'] == kind and
            record['execution'] == value['execution'] and record['inputs'] == original_inputs,
            'Retained608 native compiled inputs differ')
    current = producers608.input_hashes(kind)
    recipes = {producers608.WORKFLOW, '.github/diagnostics/rewind608_producers.py'}
    require(set(current) == set(original_inputs) and
            all(current[path] == digest for path, digest in original_inputs.items() if path not in recipes),
            'A native ' + kind + ' source input changed since the retained608 Core was compiled')
    require(record['files'] == producers608.member_hashes(directory, ('producer608.json',)),
            'Retained608 native artifact member changed, missing or added')
    require(record['compiledSourcePostimages'] == producers608.member_hashes(directory / 'patched-source608'),
            'Actual patched upstream source snapshot differs')
    identity = json.loads((directory / 'identity.json').read_bytes())
    require(identity['host_commit'] == value['execution']['source'] and identity['architectures'] == ['arm64'],
            'Wrong retained608 native host/architecture')
    sys.path[:0] = [str(ROOT / 'packages/dolphin_internal_bridge/ci'), str(ROOT / 'build-utils')]
    from verify_ipa import macho
    from delivery_benchmark import payload_fingerprint
    core_name = 'DolphinCore' if kind == 'dolphin' else 'ARMSX2Core'
    raw = (directory / f'{core_name}.framework/{core_name}').read_bytes()
    require(sha(raw) == identity['sha256'], 'Native binary differs from its compiled identity')
    image = macho(raw)
    require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
            image['id'] == f'@rpath/{core_name}.framework/{core_name}', 'Wrong retained608 native Mach-O')
    fingerprint = payload_fingerprint(raw)
    require(fingerprint == RETAINED_CORES[kind], 'Retained Core differs from the delivered608 signed payload: ' + kind)
    if kind == 'dolphin':
        require(record['upstreamRevision'] == identity['source_revision'] == producers608.DOLPHIN_SOURCE and
                identity['achievement_session_policy'] == 1 and identity['achievement_presenter'] == 1 and
                identity['use_retro_achievements'] is True and identity['source_inputs'] == original_inputs,
                'Wrong retained608 Dolphin policy provenance')
        require(producers608.DOLPHIN_EXPORTS <= set(image['definedSymbols']), 'Missing additive Dolphin RA exports')
        replacements = ((directory / 'DolphinCore.framework', ROOT / 'packages/dolphin_internal_bridge/ios/Frameworks/DolphinCore.framework'),
                        (directory / 'Sys', ROOT / 'ios/Runner/Sys'))
        for source, destination in replacements:
            require(source.is_dir(), 'Dolphin runtime resource missing')
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        shutil.copy2(directory / 'cacert.pem', ROOT / 'ios/Runner/cacert.pem')
        (ROOT / 'packages/dolphin_internal_bridge/ios/Frameworks/DolphinCore.framework/DolphinCore').chmod(0o755)
    else:
        source = json.loads((ROOT / 'build-utils/armsx2/source.json').read_bytes())
        require(identity['revision'] == record['upstreamRevision'] == source['revision'] and
                identity['abi_version'] == source['abi_version'] == 9 and
                identity['release'] == source['release'] == 'iOSv2.6.0' and
                identity['shader_chains'] is True and identity['performance_overlays'] is True,
                'Wrong ARMSX2 ABI9/release/shader contract')
        require(set(image['definedSymbols']) == {'_NeoARMSX2_GetAPI'}, 'ARMSX2 exported ABI changed')
        producers608.validate_armsx2_shaders(identity, record['files'],
                                             producers608.member_hashes(directory / 'ARMSX2Core.framework/shaders'))
        destination = ROOT / 'dist/armsx2'
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(directory, destination)
        (destination / 'ARMSX2Core.framework/ARMSX2Core').chmod(0o755)
    fast_path = ROOT / 'build/fast-native/identity.json'
    fast = json.loads(fast_path.read_bytes())
    prefix = 'dolphin' if kind == 'dolphin' else 'armsx2'
    fast.update({prefix + 'CoreSha256': identity['sha256'], prefix + 'CoreHostCommit': value['execution']['source'],
                 prefix + 'CoreRunId': value['execution']['run'], prefix + 'SourceRevision': record['upstreamRevision']})
    if kind == 'dolphin':
        fast.update(dolphinAchievementPresentationVersion=1, dolphinAchievementSessionPolicyVersion=1)
    producers608.save(fast_path, fast)
    return save(f'rewind611-{kind}.json', dict(value, identity=identity, payloadFingerprint=fingerprint,
        sourceInputs=record['inputs'], candidateSourceInputs=current,
        compiledSourcePostimages=record['compiledSourcePostimages'], coreRecompiled=False, physicalDeviceTested=False))


def retained_archive_origin(kind):
    pin = RETAINED_ARCHIVES[kind]
    artifact = engine.api('actions/artifacts/' + str(pin['artifact']))
    require(artifact['id'] == pin['artifact'] and artifact['name'] == pin['name'] and
            artifact['size_in_bytes'] == pin['bytes'] and artifact['digest'] == 'sha256:' + pin['sha256'] and
            artifact['workflow_run']['id'] == pin['run'] and artifact['workflow_run']['head_sha'] == pin['source'] and
            not artifact['expired'], 'Retained608 runtime archive changed or expired: ' + kind)
    return dict(result='authenticated', **pin, expiresAt=artifact['expires_at'])


def download_retained_archive(kind):
    value = retained_archive_origin(kind)
    path = CACHE / f'retained-{kind}.zip'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size != value['bytes'] or sha(path.read_bytes()) != value['sha256']:
        temporary = path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{value['artifact']}/zip"],
                           stdout=output, cwd=ROOT, check=True, timeout=600)
        require(temporary.stat().st_size == value['bytes'] and sha(temporary.read_bytes()) == value['sha256'],
                'Downloaded retained608 runtime archive differs: ' + kind)
        temporary.replace(path)
    destination = ROOT / value['destination']
    if destination.exists():
        shutil.rmtree(destination)
    with zipfile.ZipFile(path) as archive:
        engine.safe_members(archive)
        archive.extractall(destination)
    return save('rewind611-retained-' + kind + '.json', value)


def retained_ready():
    baseline()
    return save('rewind611-retained-producers.json', dict(
        rpc=rpc.core_run(), melonx=engine.producer('core'),
        reusedPrerequisites={kind: reused_origin(kind) for kind in REUSED_ARTIFACTS},
        runtimeArchives={kind: retained_archive_origin(kind) for kind in RETAINED_ARCHIVES},
        priorNativeSuitesReexecuted=False, priorCoresRecompiled=False))


def retained(operation):
    if operation == 'download-core':
        value = rpc.download_core()
    elif operation == 'component-runs':
        value = dict(rpcs3=rpc.core_run(), melonx=engine.producer('core'))
    elif operation == 'download-components':
        value = engine.download('core')
    elif operation == 'engine-evidence':
        value = engine.engine_evidence()
    else:
        raise ValueError(operation)
    return save('rewind611-' + operation + '.json', value)


def expected():
    application = json.loads((OUT / 'rewind611-host-contract.json').read_bytes())
    require(application['source'] == git('rev-parse', 'HEAD') and application['build'] == BUILD,
            'Application checkout changed after the contract')
    tests_value = json.loads((OUT / 'rewind611-tests.json').read_bytes())
    require(set(tests_value) == {'flutter', 'native'}, 'Retained608 test evidence is absent')
    cores = {kind: json.loads((OUT / f'rewind611-{kind}.json').read_bytes()) for kind in ('dolphin', 'armsx2')}
    for kind, value in {**tests_value, **cores}.items():
        origin = reused_origin(kind)
        require(all(value.get(key) == origin[key] for key in origin if key != 'expiresAt'),
                'Retained608 evidence differs from its authenticated original producer: ' + kind)
    rpc_receipt = rpc.core_receipt()
    require(rpc_receipt['corePayloadFingerprint'] == RPC607_FINGERPRINT, '611 would replace the retained RPCS3 payload')
    return dict(schema=1, build=BUILD, application=application, testEvidence=tests_value, evidenceMode='retained608',
        **cores, retainedRPCS3=rpc_receipt, newMeloNX=engine.engine_evidence(),
        physicalDeviceTested=False, gameTested=False, fpsGainProven=False, deviceAllocationReductionProven=False)


def embed(app):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(str(info['CFBundleVersion']) == str(BUILD), 'Wrong611 embedding build')
    value = expected()
    (app / IDENTITY).write_text(json.dumps(value, indent=2) + '\n')
    for kind in ('dolphin', 'armsx2'):
        directory = CACHE / kind
        destination = app / 'Legal' / ('Dolphin-session608' if kind == 'dolphin' else 'ARMSX2-session608')
        shutil.copytree(directory / 'patched-source608', destination / 'patched-source', dirs_exist_ok=True)
        for name in ('producer608.json', 'identity.json'):
            shutil.copy2(directory / name, destination / name)
    return save('rewind611-embedded.json', dict(result='embedded', identity=value))


def structure(ipa):
    import validate_rpcs3_ipa as structural
    # Retain607's explicit recovered-identity adapter. The structural validator,
    # expected611 build, 88 exports, ABI30 and exact binary guards all still run.
    previous = structural.validate_core_identity
    structural.validate_core_identity = rpc.validate_core_identity
    try:
        value = structural.validate_ipa(Path(ipa), str(BUILD), git('rev-parse', 'HEAD'),
                    ROOT / 'dist/rpcs3-native/identity.json', rpc.CORE_SOURCE, str(rpc.CORE_RUN))
    finally:
        structural.validate_core_identity = previous
    return save('rewind611-rpcs3-structure.json', value)


def validate(ipa):
    from validate_rpcs3_core604_ipa import compare_core
    from delivery_benchmark import payload_fingerprint
    from validate_neoplay_ipa import validate as neoplay
    from validate_shader_compiler_ipa import validate as shaders
    from verify_ipa import macho
    receipt = expected()
    complete = zip_payloads(ipa)
    validate_inventory(complete)
    signature = json.loads((OUT / 'signed-payload-identity.json').read_bytes())
    require({name: record['fingerprint'] for name, record in complete.items()} == signature['images'] and
            signature['ipaSha256'] == sha(Path(ipa).read_bytes()), 'Final ZIP differs from sealed611 payloads')
    _, delivered609 = evidence609('signed-payload-identity.json')
    for name in ('Frameworks/libRPCS3Core.dylib', 'Frameworks/DolphinCore.framework/DolphinCore',
                 'Frameworks/ARMSX2Core.framework/ARMSX2Core'):
        require(complete[name]['fingerprint'] == delivered609['images'][name], 'Retained609 engine payload changed: ' + name)
    require(complete['Frameworks/MeloNXCore.framework/MeloNXCore']['fingerprint'] !=
            delivered609['images']['Frameworks/MeloNXCore.framework/MeloNXCore'], 'The MeloNX Core was not replaced')
    with zipfile.ZipFile(ipa) as archive:
        engine.safe_members(archive)
        root = 'Payload/NeoStation.app/'
        require(json.loads(archive.read(root + IDENTITY)) == receipt, 'Packaged611 identity differs')
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        require(str(info['CFBundleVersion']) == str(BUILD) and info['MinimumOSVersion'] == '18.0',
                'Wrong application version/deployment target')
        rpc_result = compare_core(archive.read(root + 'Frameworks/libRPCS3Core.dylib'), rpc.raw_core(), signed=True)
        require(complete['Frameworks/libRPCS3Core.dylib']['fingerprint'] == RPC607_FINGERPRINT,
                'Packaged RPCS3 differs from actual607 payload')
        source_record = json.loads(archive.read(root + 'Legal/RPCS3-current-core/actual-compiled-source.json'))
        source_zip = archive.read(root + 'Legal/RPCS3-current-core/compiled-host-inputs.zip')
        require(source_record['compiledInputsZipSHA256'] == sha(source_zip) and
                source_record['coreSHA256'] == rpc.CORE_SHA256 and source_record['coreSource'] == rpc.CORE_SOURCE,
                'Retained RPCS3 source notice identity differs')
        with zipfile.ZipFile(io.BytesIO(source_zip)) as sources:
            require({n: sha(sources.read(n)) for n in sources.namelist()} == source_record['inputs'] == rpc._compiled_inputs(),
                    'RPCS3 actual compiled source notice changed')
        melonx_result = engine.engine_ipa(archive, root)
        for kind, name in (('dolphin', 'DolphinCore'), ('armsx2', 'ARMSX2Core')):
            raw = archive.read(root + f'Frameworks/{name}.framework/{name}')
            image = macho(raw)
            require(payload_fingerprint(raw) == receipt[kind]['payloadFingerprint'] == RETAINED_CORES[kind] and
                    image['codeSignature'] is True, 'Signed611 native Core differs from retained608: ' + kind)
            exports = set(image['definedSymbols'])
            require(producers608.DOLPHIN_EXPORTS <= exports if kind == 'dolphin' else exports == {'_NeoARMSX2_GetAPI'},
                    'Packaged611 native exports differ: ' + kind)
            folder = 'Legal/Dolphin-session608/' if kind == 'dolphin' else 'Legal/ARMSX2-session608/'
            require(json.loads(archive.read(root + folder + 'identity.json')) == receipt[kind]['identity'],
                    'Retained608 Core source identity notice differs')
            for path, digest in receipt[kind]['compiledSourcePostimages'].items():
                require(sha(archive.read(root + folder + 'patched-source/' + path)) == digest,
                        'Retained608 patched native source notice differs: ' + path)
        plugin = archive.read(root + 'Frameworks/achievement_translation.framework/achievement_translation')
        translation = macho(plugin)
        require(translation['platform'] == 2 and translation['fileType'] == 6 and translation['minimumOS'].startswith('18.'),
                'Wrong compiled Translation plugin')
        for marker in (b'AchievementTranslationPlugin', b'RBAchievementText', b'RBAchievementToast',
                       b'rewindbox/achievement_translation', b'RBAchievementPresent'):
            require(marker in plugin, 'Missing actual Translation implementation')
        require(any('Translation.framework' in d['path'] for d in translation['dependencies']),
                'The actual Apple Translation framework is not linked')
        plugin = archive.read(root + 'Frameworks/retro_achievements_session.framework/retro_achievements_session')
        central = macho(plugin)
        require(central['platform'] == 2 and central['fileType'] == 6 and central['minimumOS'].startswith('18.') and
                central['codeSignature'] is True, 'Wrong actual central session framework')
        require({'_RBRATakeLaunchConfiguration', '_RBRAPublishSessionState', '_RBRAEndSession', '_RBRALocalizedText'} <=
                set(central['definedSymbols']), 'Central RA facade is not exported')
        for marker in (b'RetroAchievementsSessionPlugin', b'rewindbox/retro_achievements_session'):
            require(marker in plugin, 'Missing compiled central account implementation')
        for consumer in ('armsx2_internal_bridge', 'dolphin_internal_bridge', 'libretro_internal_bridge'):
            image = macho(archive.read(root + f'Frameworks/{consumer}.framework/{consumer}'))
            require(image['minimumOS'].startswith('18.') and any(d['path'] ==
                    '@rpath/retro_achievements_session.framework/retro_achievements_session' for d in image['dependencies']),
                    'Native consumer does not link the central session pod: ' + consumer)
        helper = 'PlugIns/MeloNXJITHelper.appex/melonx-universal.js'
        require(archive.read(root + helper) == (ROOT / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes(),
                'Delivered609 MeloNX helper changed')
        host = archive.read(root + 'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        for marker in (b'Hogwarts GPU policy:', b'occlusionQuerySync', b'relaxQueryFlushing',
                       b'original core SHA256 prefix', b'inspectUnreal'):
            require(marker in host, 'Delivered609 Hogwarts host behavior missing')
    return save('rewind611-ipa-validation.json', dict(result='passed', build=BUILD,
        ipaSHA256=sha(Path(ipa).read_bytes()), ipaBytes=Path(ipa).stat().st_size, identity=receipt,
        nativeImages=90, baselineImageNamesPreserved=90, addedImages=0,
        retainedRPCS3Payload=rpc_result, newMeloNXPayload=melonx_result,
        retainedDolphinAndARMSX2PayloadsVerified=True, actualTranslationAndSessionPluginsPresent=True,
        retainedNeoPlay=neoplay(Path(ipa), str(BUILD), git('rev-parse', 'HEAD')),
        shaderCompilerIsolation=shaders(Path(ipa), str(BUILD)),
        physicalDeviceTested=False, gameTested=False, fpsGainProven=False, deviceAllocationReductionProven=False))


# The delivered609 recipe, transformed exactly: names, build number, recipient and
# artifact names, the Core producer step names, and one restoration step per job.
RESTORE_STEP = (
    '    - name: Restore the delivered609 application sources the concurrent 610 lot changed\n'
    '      run: python3 -B .github/diagnostics/rewind611_baseline.py restore\n')
REPLACEMENTS = (
    ('    name: Build609 authenticate delivered608 and immutable retained engines',
     '    name: Build611 authenticate delivered609 and immutable retained engines'),
    ("'[rewind609-delivery]')) }}", "'[rewind611-delivery]')) }}"),
    ('    - name: Checkout exact609 candidate and history\n      uses: actions/checkout@v4\n      with:\n'
     '        ref: ${{ github.sha }}\n        fetch-depth: 0\n        persist-credentials: false\n',
     '    - name: Checkout exact611 candidate and history\n      uses: actions/checkout@v4\n      with:\n'
     '        ref: ${{ github.sha }}\n        fetch-depth: 0\n        persist-credentials: false\n' + RESTORE_STEP),
    ('    - name: Require reviewed608 delta and authenticated retained producer archives\n'
     '      run: python3 -B .github/diagnostics/rewind609_delivery.py retained-ready',
     '    - name: Require reviewed609 delta and authenticated retained producer archives\n'
     '      run: python3 -B .github/diagnostics/rewind609_delivery.py retained-ready'),
    ('    name: Build609 full Flutter IPA with the liveness MeloNX Core and exact608 retained engines',
     '    name: Build611 full Flutter IPA with the fragmented-read MeloNX Core and exact609 retained engines'),
    ("      BUILD_NUMBER: '609'", "      BUILD_NUMBER: '611'"),
    ('      DELIVERY_RECIPIENT: build-utils/delivery-609-recipient.pem', '      DELIVERY_RECIPIENT: build-utils/delivery-611-recipient.pem'),
    ('      ARTIFACT_NAME: RewindBox-Build609-', '      ARTIFACT_NAME: RewindBox-Build611-'),
    ('    - name: Checkout exact candidate\n      uses: actions/checkout@v4\n      with:\n        fetch-depth: 0\n'
     '        persist-credentials: false\n        ref: ${{ github.sha }}\n',
     '    - name: Checkout exact candidate\n      uses: actions/checkout@v4\n      with:\n        fetch-depth: 0\n'
     '        persist-credentials: false\n        ref: ${{ github.sha }}\n' + RESTORE_STEP),
    ('    - name: Authenticate delivered608 and the exact reviewed609 source delta',
     '    - name: Authenticate delivered609 and the exact reviewed611 source delta'),
    ('Extract authenticated donor527 resources; application product baseline remains608',
     'Extract authenticated donor527 resources; application product baseline remains609'),
    ('    - name: Download the reviewed liveness MeloNX Core producer',
     '    - name: Download the reviewed fragmented-read MeloNX Core producer'),
    ('    - name: Authenticate the liveness Core inputs, fresh gates and runtime evidence',
     '    - name: Authenticate the fragmented-read Core inputs, fresh gates and runtime evidence'),
    ("        Path('build/delivery/neoswap-host-source609.json')", "        Path('build/delivery/neoswap-host-source611.json')"),
    ('    - name: Embed609 identity, the new MeloNX Core proof and exact retained608 provenance',
     '    - name: Embed611 identity, the new MeloNX Core proof and exact retained609 provenance'),
    ('    - name: Verify all90 signed images, the new MeloNX Core and retained608 payloads',
     '    - name: Verify all90 signed images, the new MeloNX Core and retained609 payloads'),
)


def replace_once(text, before, after):
    require(text.count(before) == 1, 'The reviewed609 workflow anchor changed: ' + before[:100])
    return text.replace(before, after, 1)


def expected_workflow(original):
    """Exact text transform of the delivered609 workflow; every other byte is kept."""
    value = original
    header = value[:value.index('jobs:\n')]
    new_header = (header
        .replace('name: RewindBox private IPA609 - liveness MeloNX Core',
                 'name: RewindBox private IPA611 - fragmented-read MeloNX Core')
        .replace('run-name: RewindBox Build609 - liveness MeloNX Core - ${{ github.sha }}',
                 'run-name: RewindBox Build611 - fragmented-read MeloNX Core - ${{ github.sha }}')
        .replace('  group: rewindbox-liveness609-${{ github.ref }}', '  group: rewindbox-reads611-${{ github.ref }}')
        .replace("  BUILD_NUMBER: '609'", "  BUILD_NUMBER: '611'"))
    require(new_header.count('611') == 4 and '609' not in new_header, 'The reviewed609 workflow header changed')
    value = new_header + value[len(header):]
    for before, after in REPLACEMENTS:
        value = replace_once(value, before, after)
    require(value.count('rewind609_delivery.py') == 16, 'Unexpected609 application operation inventory')
    value = value.replace('rewind609_delivery.py', 'rewind611_delivery.py')
    require(value.count(RESTORE_STEP) == 2, 'Each job must restore before its first check')
    require('rewind609' not in value.replace('rewind609-hogwarts', '') and "'609'" not in value and 'Build609' not in value,
            'A609 recipe call remains')
    return value


def workflow():
    """Local integration only: write the reviewed transform; CI checks equality."""
    require(not os.environ.get('CI') and not os.environ.get('GITHUB_ACTIONS'), 'The workflow may not be generated in CI')
    value = expected_workflow((ROOT / WORKFLOW609).read_text())
    (ROOT / WORKFLOW).write_text(value)
    return dict(result='written', path=WORKFLOW, sha256=sha(value.encode()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['contract', 'baseline', 'retained-ready', 'tests', 'workflow',
        'download-core', 'component-runs', 'download-components', 'engine-evidence',
        'download-libretro', 'download-melonx-dependencies', 'dolphin', 'armsx2',
        'embed', 'structure', 'validate', 'seal'])
    parser.add_argument('path', nargs='?', type=Path)
    args = parser.parse_args()
    if args.operation in ('embed', 'structure', 'validate'):
        require(args.path is not None, 'Missing application or IPA path')
        result = globals()[args.operation](args.path)
    elif args.operation in ('download-libretro', 'download-melonx-dependencies'):
        result = download_retained_archive(args.operation.removeprefix('download-'))
    elif args.operation in ('download-core', 'component-runs', 'download-components', 'engine-evidence'):
        result = retained(args.operation)
    elif args.operation in ('dolphin', 'armsx2'):
        result = native(args.operation)
    elif args.operation == 'retained-ready':
        result = retained_ready()
    else:
        result = globals()[args.operation]()
    print(json.dumps(result, indent=2, default=str))
