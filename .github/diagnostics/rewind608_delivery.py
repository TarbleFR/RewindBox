"""Private IPA608: delivered607 with the reviewed central RA session changes.

Fresh Dolphin/ARMSX2 artifacts and tests come from prerequisite jobs in this
same run. RPCS3 and MeloNX retain their exact607 bytes and original provenance.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import plistlib
import shutil
import sys
import zipfile

import rewind608_baseline as tree
import rewind608_producers as producers
import rewind606_engine as engine
import rpcs3runtime607_core as rpc
# Stateless Mach-O/container parsers already used for delivered607. No old
# source contract, historical build number or test result is altered or replayed.
from rewind607_delivery import arm64_payload, app_payloads, zip_payloads

ROOT, BUILD = tree.ROOT, 608
OUT = ROOT / 'build/delivery'
IDENTITY = 'RetroAchievements-session-build-identity.json'
BASE_INVENTORY_SHA = 'b088b71dadf923a302cb1bd174f2999db33f7d52d5f9020708e55abaf6272ad6'
RPC607_FINGERPRINT = '7289ce4ef4f723d203995b4a76d5b2e1c2cd5a874e8a72c04b774c7d2dc1d22e'
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
    return producers.save(OUT / name, value)


def inventory():
    value = json.loads((ROOT / tree.INVENTORY).read_bytes())
    reference = (ROOT / 'docs/evidence/rewind606/signed-payload-identity.json').read_bytes()
    require(sha(reference) == value['inventoryReferenceSHA256'] == BASE_INVENTORY_SHA,
            'Original89-image inventory reference changed')
    original = set(json.loads(reference)['images'])
    added = {'Frameworks/retro_achievements_session.framework/retro_achievements_session'}
    require(value['schema'] == 1 and value['build'] == BUILD and value['baselineBuild'] == 607 and
            len(original) == 89 and set(value['baselineImages']) == original and
            len(value['baselineImages']) == 89 and set(value['addedImages']) == added and
            value['removedImages'] == [] and value['expectedImageCount'] == 90,
            '608 may add only the one central session native image')
    return original | added


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
    require(before == after == packaged,
            'Signing/export changed compiled code, data, ABI or an architecture container')
    receipt = json.loads((OUT / 'signed-payload-identity.json').read_bytes())
    complete = {name: record['fingerprint'] for name, record in before.items()}
    require(set(receipt['images']) <= set(complete) and
            all(complete[name] == digest for name, digest in receipt['images'].items()),
            'Signer receipt disagrees with the full native inventory')
    require(receipt['ipaSha256'] == sha(ipa.read_bytes()) and receipt['ipaBytes'] == ipa.stat().st_size and
            receipt['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True and
            receipt['abiMetadataUnchangedBySigning'] is True, 'Wrong signed608 export identity')
    signature = json.loads((OUT / 'signature.json').read_bytes())
    signed_targets = {'.' if name == 'Runner' else name if name.endswith('.dylib') else Path(name).parent.as_posix()
                      for name in before}
    require(len(signed_targets) == 90 and len(signature['signatures']) == 90 and
            all(item['signatureVerified'] is True for item in signature['signatures']) and
            {item['bundle'] for item in signature['signatures']} == signed_targets,
            'Missing, duplicated or failed actual macOS signature verification')
    receipt.update(build=BUILD, images=complete, imageCount=90, retainedImageNames=89, addedImageNames=1,
        architectureContainers={name: record['container'] for name, record in before.items()},
        singleArm64FatImages=sum(record['container'].startswith('single-arm64-fat') for record in before.values()),
        completeNativeInventoryCheckedBeforeAndAfterSigning=True,
        completeNativeInventoryCheckedInFinalZIP=True)
    return save('signed-payload-identity.json', receipt)


def contract():
    return save('rewind608-host-contract.json', tree.verify())


def baseline():
    result = contract()
    base = tree.BASELINE
    run = engine.api('actions/runs/' + str(base['run']))
    job = engine.api('actions/jobs/' + str(base['job']))
    require(run['head_sha'] == job['head_sha'] == tree.BASE and
            run['conclusion'] == job['conclusion'] == 'success' and
            run['run_attempt'] == job['run_attempt'] == base['attempt'] and
            job['run_id'] == run['id'] == base['run'] and run['head_branch'] == 'Claude' and
            run['path'] == '.github/workflows/rewind607-rpcs3-core-delivery.yml',
            'Wrong actual delivered607 run/job')
    return save('rewind608-baseline.json', dict(result='authenticated-run-and-reviewed-source',
        application=result, delivered607=base, previousPrivateIPADownloadedByThisRun=False,
        previousIPAMetadataOrigin='Verified delivery607 reported by the integrator; previous private IPA is not a runtime donor.',
        historicalTestsReexecuted=False))


def retained_ready():
    baseline()
    return save('rewind608-retained-producers.json', dict(
        rpc=rpc.core_run(), melonx=engine.producer('core'),
        runtimeArchives={kind: retained_archive_origin(kind) for kind in RETAINED_ARCHIVES},
        priorNativeSuitesReexecuted=False, priorCoresRecompiled=False))


def retained_archive_origin(kind):
    pin = RETAINED_ARCHIVES[kind]
    artifact = engine.api('actions/artifacts/' + str(pin['artifact']))
    require(artifact['id'] == pin['artifact'] and artifact['name'] == pin['name'] and
            artifact['size_in_bytes'] == pin['bytes'] and artifact['digest'] == 'sha256:' + pin['sha256'] and
            artifact['workflow_run']['id'] == pin['run'] and artifact['workflow_run']['head_sha'] == pin['source'] and
            not artifact['expired'], 'Retained607 runtime archive changed or expired: ' + kind)
    return dict(result='authenticated', **pin, expiresAt=artifact['expires_at'])


def download_retained_archive(kind):
    import subprocess
    value = retained_archive_origin(kind)
    path = ROOT / f'build/components608/retained-{kind}.zip'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size != value['bytes'] or sha(path.read_bytes()) != value['sha256']:
        temporary = path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{value['artifact']}/zip"],
                           stdout=output, cwd=ROOT, check=True, timeout=600)
        require(temporary.stat().st_size == value['bytes'] and sha(temporary.read_bytes()) == value['sha256'],
                'Downloaded retained607 runtime archive differs: ' + kind)
        temporary.replace(path)
    destination = ROOT / value['destination']
    if destination.exists():
        shutil.rmtree(destination)
    with zipfile.ZipFile(path) as archive:
        engine.safe_members(archive)
        archive.extractall(destination)
    return save('rewind608-retained-' + kind + '.json', value)


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
    return save('rewind608-' + operation + '.json', value)


def expected():
    application = json.loads((OUT / 'rewind608-host-contract.json').read_bytes())
    require(application['source'] == git('rev-parse', 'HEAD') and application['build'] == BUILD,
            'Application checkout changed after the contract')
    tests = json.loads((OUT / 'rewind608-tests.json').read_bytes())
    require(set(tests) == {'flutter', 'native'} and
            all(t['execution'] == producers.execution() for t in tests.values()),
            'Fresh608 prerequisite test evidence is absent')
    cores = {kind: json.loads((OUT / f'rewind608-{kind}.json').read_bytes()) for kind in ('dolphin', 'armsx2')}
    require(all(c['execution'] == producers.execution() for c in cores.values()), 'Wrong608 native producer')
    rpc_receipt = rpc.core_receipt()
    require(rpc_receipt['corePayloadFingerprint'] == RPC607_FINGERPRINT,
            '608 would replace the actual recovered607 RPCS3 payload')
    return dict(schema=1, build=BUILD, application=application, freshTests=tests,
        **cores, retainedRPCS3=rpc_receipt, retainedMeloNX=engine.engine_evidence(),
        physicalDeviceTested=False, translationModelsTestedOnDevice=False,
        gameTested=False, fpsGainProven=False)


def embed(app):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(str(info['CFBundleVersion']) == str(BUILD), 'Wrong608 embedding build')
    value = expected()
    (app / IDENTITY).write_text(json.dumps(value, indent=2) + '\n')
    for kind in ('dolphin', 'armsx2'):
        directory = ROOT / f'build/components608/{kind}'
        destination = app / 'Legal' / ('Dolphin-session608' if kind == 'dolphin' else 'ARMSX2-session608')
        shutil.copytree(directory / 'patched-source608', destination / 'patched-source', dirs_exist_ok=True)
        for name in ('producer608.json', 'identity.json'):
            shutil.copy2(directory / name, destination / name)
    return save('rewind608-embedded.json', dict(result='embedded', identity=value))


def structure(ipa):
    import validate_rpcs3_ipa as structural
    # Retain607's explicit recovered-identity adapter. The structural validator,
    # expected608 build,88 exports,ABI30 and exact binary guards all still run.
    previous = structural.validate_core_identity
    structural.validate_core_identity = rpc.validate_core_identity
    try:
        value = structural.validate_ipa(Path(ipa), str(BUILD), git('rev-parse', 'HEAD'),
                    ROOT / 'dist/rpcs3-native/identity.json', rpc.CORE_SOURCE, str(rpc.CORE_RUN))
    finally:
        structural.validate_core_identity = previous
    return save('rewind608-rpcs3-structure.json', value)


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
            signature['ipaSha256'] == sha(Path(ipa).read_bytes()), 'Final ZIP differs from sealed608 payloads')
    with zipfile.ZipFile(ipa) as archive:
        engine.safe_members(archive)
        root = 'Payload/NeoStation.app/'
        require(json.loads(archive.read(root + IDENTITY)) == receipt, 'Packaged608 identity differs')
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
            require(payload_fingerprint(raw) == receipt[kind]['payloadFingerprint'] and image['codeSignature'] is True,
                    'Signed608 native Core differs from its producer: ' + kind)
            exports = set(image['definedSymbols'])
            require(producers.DOLPHIN_EXPORTS <= exports if kind == 'dolphin' else exports == {'_NeoARMSX2_GetAPI'},
                    'Packaged608 native exports differ: ' + kind)
            folder = 'Legal/Dolphin-session608/' if kind == 'dolphin' else 'Legal/ARMSX2-session608/'
            require(json.loads(archive.read(root + folder + 'identity.json')) == receipt[kind]['identity'],
                    '608 Core source identity notice differs')
            for path, digest in receipt[kind]['compiledSourcePostimages'].items():
                require(sha(archive.read(root + folder + 'patched-source/' + path)) == digest,
                        'Patched608 native source notice differs: ' + path)
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
                'Delivered607 MeloNX helper changed')
        host = archive.read(root + 'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        for marker in (b'Hogwarts GPU policy:', b'occlusionQuerySync', b'relaxQueryFlushing',
                       b'original core SHA256 prefix', b'inspectUnreal'):
            require(marker in host, 'Delivered607 Hogwarts host behavior missing')
    return save('rewind608-ipa-validation.json', dict(result='passed', build=BUILD,
        ipaSHA256=sha(Path(ipa).read_bytes()), ipaBytes=Path(ipa).stat().st_size, identity=receipt,
        nativeImages=90, baselineImageNamesPreserved=89, centralSessionImagesAdded=1,
        retained607RPCS3Payload=rpc_result, retained607MeloNXPayload=melonx_result,
        rebuiltDolphinAndARMSX2PayloadsVerified=True, actualTranslationAndSessionPluginsPresent=True,
        retainedNeoPlay=neoplay(Path(ipa), str(BUILD), git('rev-parse', 'HEAD')),
        shaderCompilerIsolation=shaders(Path(ipa), str(BUILD)),
        physicalDeviceTested=False, gameTested=False, fpsGainProven=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['contract', 'baseline', 'retained-ready', 'tests',
        'download-core', 'component-runs', 'download-components', 'engine-evidence',
        'download-libretro', 'download-melonx-dependencies',
        'dolphin', 'armsx2', 'embed', 'structure', 'validate', 'seal'])
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
        result = producers.native(args.operation)
    elif args.operation == 'tests':
        result = producers.tests()
    elif args.operation == 'retained-ready':
        result = retained_ready()
    else:
        result = globals()[args.operation]()
    print(json.dumps(result, indent=2))
