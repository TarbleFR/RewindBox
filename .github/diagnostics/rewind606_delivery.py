"""Private IPA606: exact delivered605 plus reviewed current Hogwarts changes.

The fresh Core and host proof belong to their own successful producers. The
achievement suite and retained engines keep historical attribution.
"""
import argparse
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for folder in ('build-utils', 'packages/dolphin_internal_bridge/ci', 'test'):
    sys.path.insert(0, str(ROOT / folder))
import rewind606_baseline as tree
import rewind606_engine as engine
import rpcs3runtime606_core as rpc

BUILD = 606
OUT = ROOT / 'build/delivery'
IDENTITY = 'Hogwarts-performance-build-identity.json'
VALIDATION605 = 'docs/evidence/achievement-translation-ipa/achievement-ipa-validation.json'
VALIDATION605_SHA = 'a27311940fb3cf8dc056ce3f0e971d0aaf9f66cff186c1b669a454953a332139'
TESTS605 = 'docs/evidence/achievement-translation-ipa/achievement-tests.json'
TESTS605_SHA = 'd508f3e4accb2a0484da141c80987864a099dfed1e4ce720382c346168fca63b'
sha = tree.sha
git = tree.git
api = engine.api
require = tree.require
MACHO_MAGICS = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe',
                b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf',
                b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'}


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')
    return value


def arm64_payload(raw):
    """Validate one arm64 image, including a possible single-slice fat wrapper."""
    data = raw
    container = 'thin-arm64'
    if raw[:4] in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        wide = raw[:4] == b'\xca\xfe\xba\xbf'
        stride = 32 if wide else 20
        require(len(raw) >= 8 + stride and struct.unpack_from('>I', raw, 4)[0] == 1,
                'Delivery requires exactly one complete arm64 architecture record')
        cpu, subtype = struct.unpack_from('>II', raw, 8)
        require(cpu == 0x0100000C, 'Fat wrapper contains a non-arm64 architecture')
        offset, size = struct.unpack_from('>QQ' if wide else '>II', raw, 16)
        alignment = struct.unpack_from('>I', raw, 32 if wide else 24)[0]
        require(alignment <= 31 and offset % (1 << alignment) == 0 and
                offset >= 8 + stride and size >= 32 and offset + size == len(raw),
                'Invalid single-arm64 slice alignment or bounds')
        if wide:
            require(struct.unpack_from('>I', raw, 36)[0] == 0, 'Unexpected fat64 reserved metadata')
        data = raw[offset:offset + size]
        require(len(data) >= 32 and struct.unpack_from('<II', data, 4) == (cpu, subtype),
                'Fat architecture differs from the inner image')
        container = 'single-arm64-fat64' if wide else 'single-arm64-fat32'
    require(len(data) >= 32 and data[:4] == b'\xcf\xfa\xed\xfe', 'Expected a complete little-endian Mach-O64 image')
    _, cpu, _, kind, count, command_bytes, _, _ = struct.unpack_from('<8I', data)
    require(cpu == 0x0100000C and kind in (2, 6), 'Expected arm64 executable or dylib')
    require(0 < count <= 65536 and 32 + command_bytes <= len(data), 'Truncated Mach-O command table')
    cursor, end = 32, 32 + command_bytes
    for _ in range(count):
        require(cursor + 8 <= end, 'Truncated Mach-O load command')
        _, length = struct.unpack_from('<II', data, cursor)
        require(length >= 8 and length % 8 == 0 and cursor + length <= end, 'Invalid Mach-O command length')
        cursor += length
    require(cursor == end, 'Mach-O command count and byte size disagree')
    return data, container


def payload_record(raw):
    from verify_ipa import macho
    from delivery_benchmark import payload_fingerprint
    data, container = arm64_payload(raw)
    image = macho(data)
    require(image['architecture'] == 'arm64' and image['platform'] == 2,
            'Signing inventory contains a non-iPhone image')
    return dict(fingerprint=payload_fingerprint(data), container=container)


def app_payloads(app):
    records = {}
    for path in app.rglob('*'):
        if not path.is_file():
            continue
        with path.open('rb') as source:
            magic = source.read(4)
        if magic in MACHO_MAGICS:
            records[path.relative_to(app).as_posix()] = payload_record(path.read_bytes())
    return records


def zip_payloads(ipa):
    records = {}
    with zipfile.ZipFile(ipa) as archive:
        engine.safe_members(archive)
        root = 'Payload/NeoStation.app/'
        for entry in archive.infolist():
            if entry.is_dir() or entry.file_size < 4:
                continue
            with archive.open(entry) as source:
                magic = source.read(4)
            if magic in MACHO_MAGICS:
                require(entry.filename.startswith(root), 'Mach-O outside the single application')
                records[entry.filename[len(root):]] = payload_record(archive.read(entry))
    return records


def seal():
    """Keep the existing signer/export checks and also bind all fat arm64 images."""
    import delivery_benchmark as benchmark
    app = ROOT / 'build/ios/dolphin-unsigned/Payload/NeoStation.app'
    before = app_payloads(app)
    require(len(before) == 89, 'Expected the complete delivered605 native image inventory')
    # This retains macOS codesign checks, ad-hoc sealing, final ZIP export and
    # structural validation. Its historical thin-only receipt is checked below.
    benchmark.seal()
    after = app_payloads(app)
    ipa = ROOT / 'dist/NeoStation.ipa'
    packaged = zip_payloads(ipa)
    require(before == after == packaged, 'Signing or ZIP export changed a compiled payload or its architecture container')
    receipt = json.loads((OUT / 'signed-payload-identity.json').read_bytes())
    complete = {name: record['fingerprint'] for name, record in before.items()}
    require(set(receipt['images']) <= set(complete) and
            all(complete[name] == digest for name, digest in receipt['images'].items()),
            'Historical signer receipt disagrees with complete native inventory')
    require(receipt['ipaSha256'] == sha(ipa.read_bytes()) and receipt['ipaBytes'] == ipa.stat().st_size and
            receipt['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True and
            receipt['abiMetadataUnchangedBySigning'] is True, 'Wrong signed export identity')
    signature = json.loads((OUT / 'signature.json').read_bytes())
    require(len(signature['signatures']) == 89 and all(item['signatureVerified'] is True for item in signature['signatures']),
            'Missing actual macOS signature checks')
    signed_targets = {'.' if name == 'Runner' else name if name.endswith('.dylib') else Path(name).parent.as_posix()
                      for name in before}
    require(len(signed_targets) == 89 and {item['bundle'] for item in signature['signatures']} == signed_targets,
            'macOS signature receipt omitted or duplicated a native image')
    receipt.update(images=complete, imageCount=len(complete),
        architectureContainers={name: record['container'] for name, record in before.items()},
        singleArm64FatImages=sum(record['container'].startswith('single-arm64-fat') for record in before.values()),
        completeNativeInventoryCheckedBeforeAndAfterSigning=True,
        completeNativeInventoryCheckedInFinalZIP=True)
    return save('signed-payload-identity.json', receipt)


def contract():
    return save('rewind606-host-contract.json', tree.verify())


def baseline():
    result = contract()
    pin = tree.pins()['baseline']
    run, job = api('actions/runs/' + str(pin['run'])), api('actions/jobs/' + str(pin['job']))
    require(run['id'] == pin['run'] and job['id'] == pin['job'] and
            run['head_sha'] == job['head_sha'] == pin['source'] and
            run['conclusion'] == job['conclusion'] == 'success' and
            run['run_attempt'] == job['run_attempt'] == pin['attempt'] and job['run_id'] == pin['run'],
            'Wrong actual delivered605 run/job')
    return save('rewind606-baseline.json', dict(result='authenticated', application=result,
        delivered605=pin, historicalChecksReexecuted=False))


def retained_translation():
    validation_raw = (ROOT / VALIDATION605).read_bytes()
    tests_raw = (ROOT / TESTS605).read_bytes()
    require(sha(validation_raw) == VALIDATION605_SHA and sha(tests_raw) == TESTS605_SHA,
            'Actual605 achievement proof changed')
    original = json.loads(validation_raw)['identity']['translationTests']
    require(original == json.loads(tests_raw) and original['source'] == tree.BASE and
            original['run'] == 41216465837 and original['attempt'] == 1 and
            original['jobs'] == [124581910401, 124581910595], 'Wrong historical achievement test origin')
    scope = json.loads((ROOT / 'docs/evidence/achievement-translation-scope.json').read_bytes())
    unchanged = {}
    reviewed = tree.pins()['productDelta']
    for path in scope['productDelta']:
        current = (ROOT / path).read_bytes()
        previous = tree.original(tree.BASE, path)
        if current == previous:
            unchanged[path] = sha(current)
        else:
            require(path in reviewed and reviewed[path]['before'] == sha(previous) and
                    reviewed[path]['after'] == sha(current), 'Unreviewed605 achievement consumer change: ' + path)
    require(not git('diff', '--name-only', tree.BASE, 'HEAD', '--', 'packages/achievement_translation'),
            'Delivered achievement plugin changed')
    return dict(result='authenticated-historical', originalResult=original,
        originalResultSHA256=TESTS605_SHA, originalIPAValidationSHA256=VALIDATION605_SHA,
        unchangedImplementationInputs=unchanged, historicalTestsReexecuted=False,
        currentWholeApplicationInputsIdentical=False,
        scope='Original605 proof; changed native consumers receive current host integration and signed IPA checks.',
        physicalDeviceTested=False)


def dolphin_ready():
    for name in ('DOLPHIN_CORE_HOST_SHA', 'DOLPHIN_CORE_RUN_ID'):
        require(os.environ[name] == tree.COMPONENTS[name], 'Changed retained Dolphin selection')
    import achievement_translation_delivery as delivered
    run = delivered.dolphin_run()
    require(run['id'] == 41209480072 and run['run_attempt'] == 1, 'Wrong retained Dolphin run')
    artifact = api('actions/artifacts/13046204173')
    require(artifact['digest'] == 'sha256:fdd13623b859dbd57315974c47c8fb06916a5b141c93f7fe8d464b4486bb86fb' and
            artifact['workflow_run']['id'] == run['id'] and artifact['workflow_run']['head_sha'] == run['head_sha'] and
            not artifact['expired'], 'Changed delivered605 Dolphin artifact')
    return dict(result='authenticated', producer=run['head_sha'], run=run['id'], artifact=artifact['id'],
                compilationReexecuted=False, retainedFromBuild=605)


def dolphin():
    dolphin_ready()
    import achievement_translation_delivery as delivered
    actual = delivered.dolphin()
    raw = (ROOT / VALIDATION605).read_bytes()
    require(sha(raw) == VALIDATION605_SHA, 'Wrong605 Dolphin receipt')
    require(actual == json.loads(raw)['identity']['dolphin'], 'Installed Dolphin differs from delivered605 presentation Core')
    return save('rewind606-dolphin.json', actual)


def tests():
    engine.download('host')
    value = engine.host_evidence()
    return save('rewind606-host-checks.json', value)


def producers():
    baseline()
    return save('rewind606-producers.json', dict(core=engine.producer('core'),
        host=tests(), dolphin=dolphin_ready(), rpc=rpc.core_run(), historicalTestsReexecuted=False))


def retained(operation):
    if operation == 'download-core':
        result = rpc.download_core()
    elif operation == 'component-runs':
        result = dict(rpcs3=rpc.core_run(), melonx=engine.producer('core'))
    elif operation == 'download-components':
        result = engine.download('core')
    elif operation == 'engine-evidence':
        result = engine.engine_evidence()
    else:
        raise ValueError(operation)
    return save('rewind606-' + operation + '.json', result)


def expected():
    application = json.loads((OUT / 'rewind606-host-contract.json').read_bytes())
    require(application['source'] == git('rev-parse', 'HEAD') and application['build'] == BUILD,
            'Application checkout changed')
    return dict(schema=1, build=BUILD, application=application,
        translationTests=retained_translation(), hostChecks=engine.host_evidence(),
        dolphin=json.loads((OUT / 'rewind606-dolphin.json').read_bytes()),
        retainedRPCS3=rpc.core_receipt(), newMeloNX=engine.engine_evidence(),
        priorTestsReexecuted=False, translationModelsTestedOnDevice=False,
        physicalDeviceTested=False, gameTested=False, fpsGainProven=False)


def embed(app):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(str(info['CFBundleVersion']) == str(BUILD), 'Wrong embedding build')
    value = expected()
    (app / IDENTITY).write_text(json.dumps(value, indent=2) + '\n')
    target = app / 'Legal/Dolphin-achievement-presentation'
    shutil.copytree(ROOT / 'dist/dolphin-achievement/patched-source', target, dirs_exist_ok=True)
    shutil.copy2(ROOT / 'dist/dolphin-achievement/identity.json', target / 'identity.json')
    return save('rewind606-embedded.json', dict(result='embedded', identity=value))


def structure(ipa):
    import rpcs3runtime606_core as rpc
    import validate_rpcs3_ipa as structural
    # Same explicit identity adaptation as604. Every structural/ABI guard runs;
    # no historical build number or test result is modified.
    previous = structural.validate_core_identity
    structural.validate_core_identity = rpc.validate_core_identity
    try:
        value = structural.validate_ipa(Path(ipa), str(BUILD), git('rev-parse', 'HEAD'),
                    ROOT / 'dist/rpcs3-native/identity.json', rpc.CORE_SOURCE, str(rpc.CORE_RUN))
    finally:
        structural.validate_core_identity = previous
    return save('rewind606-rpcs3-structure.json', value)


def validate(ipa):
    import io
    import plistlib
    import rpcs3runtime606_core as rpc
    from validate_rpcs3_core604_ipa import compare_core
    from rewind606_engine import engine_ipa
    from delivery_benchmark import payload_fingerprint
    from validate_neoplay_ipa import validate as neoplay
    from validate_shader_compiler_ipa import validate as shaders
    from verify_ipa import macho
    receipt = expected()
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        assert len(names) == len(set(names)) and z.testzip() is None
        root = 'Payload/NeoStation.app/'
        assert json.loads(z.read(root + IDENTITY)) == receipt
        info = plistlib.loads(z.read(root + 'Info.plist'))
        assert str(info['CFBundleVersion']) == str(BUILD) and info['MinimumOSVersion'] == '18.0'
        core_result = compare_core(z.read(root + 'Frameworks/libRPCS3Core.dylib'), rpc.raw_core(), signed=True)
        source_record = json.loads(z.read(root + 'Legal/RPCS3-current-core/actual-compiled-source.json'))
        source_zip = z.read(root + 'Legal/RPCS3-current-core/compiled-host-inputs.zip')
        assert source_record['compiledInputsZipSHA256'] == sha(source_zip)
        assert source_record['coreSHA256'] == rpc.CORE_SHA256 and source_record['coreSource'] == rpc.CORE_SOURCE
        with zipfile.ZipFile(io.BytesIO(source_zip)) as sources:
            assert {n: sha(sources.read(n)) for n in sources.namelist()} == source_record['inputs'] == rpc._core_contract()[1]
        melonx_result = engine_ipa(z, root)
        dolphin_raw = z.read(root + 'Frameworks/DolphinCore.framework/DolphinCore')
        assert payload_fingerprint(dolphin_raw) == receipt['dolphin']['payloadFingerprint']
        assert '_neostation_dolphin_set_achievement_presenter' in macho(dolphin_raw)['definedSymbols']
        assert macho(dolphin_raw)['codeSignature'] is True
        plugin = z.read(root + 'Frameworks/achievement_translation.framework/achievement_translation')
        image = macho(plugin)
        assert image['platform'] == 2 and image['fileType'] == 6 and image['minimumOS'].startswith('18.')
        for marker in (b'AchievementTranslationPlugin', b'RBAchievementText', b'RBAchievementToast',
                       b'rewindbox/achievement_translation', b'RBAchievementPresent'):
            assert marker in plugin, 'Missing compiled translation implementation: ' + repr(marker)
        assert any('Translation.framework' in d['path'] for d in image['dependencies'])
        # Every direct native consumer must declare the same deployment floor;
        # otherwise ld warns about linking an iOS18 translation dylib from17.4.
        for consumer in ('armsx2_internal_bridge', 'dolphin_internal_bridge', 'libretro_internal_bridge'):
            consumer_image = macho(z.read(root + f'Frameworks/{consumer}.framework/{consumer}'))
            assert consumer_image['minimumOS'].startswith('18.'), consumer
        helper_path = 'PlugIns/MeloNXJITHelper.appex/melonx-universal.js'
        assert z.read(root + helper_path) == (ROOT / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes()
        host = z.read(root + 'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        for marker in (b'Hogwarts GPU policy:', b'occlusionQuerySync', b'relaxQueryFlushing',
                       b'original core SHA256 prefix', b'inspectUnreal'):
            assert marker in host, 'Current Hogwarts host marker missing: ' + repr(marker)
    neoplay_result = neoplay(Path(ipa), str(BUILD), git('rev-parse', 'HEAD'))
    shader_result = shaders(Path(ipa), str(BUILD))
    return save('rewind606-ipa-validation.json', dict(result='passed', build=BUILD,
                ipaSHA256=sha(Path(ipa).read_bytes()), ipaBytes=Path(ipa).stat().st_size,
                identity=receipt, retainedRPCS3Payload=core_result, newMeloNXPayload=melonx_result,
                retained605DolphinPayloadPreserved=True, actualTranslationPluginPresent=True,
                retainedNeoPlay=neoplay_result, shaderCompilerIsolation=shader_result,
                physicalDeviceTested=False, gameTested=False, fpsGainProven=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['contract', 'baseline', 'producers', 'tests', 'dolphin', 'dolphin-ready',
        'download-core', 'component-runs', 'download-components', 'engine-evidence', 'embed', 'structure', 'validate', 'seal'])
    parser.add_argument('path', nargs='?', type=Path)
    args = parser.parse_args()
    if args.operation in ('embed', 'structure', 'validate'):
        require(args.path is not None, 'Missing application or IPA path')
        result = globals()[args.operation](args.path)
    elif args.operation in ('download-core', 'component-runs', 'download-components', 'engine-evidence'):
        result = retained(args.operation)
    elif args.operation == 'dolphin-ready':
        result = dolphin_ready()
    else:
        result = globals()[args.operation]()
    print(json.dumps(result, indent=2))
