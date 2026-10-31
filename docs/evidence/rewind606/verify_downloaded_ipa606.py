#!/usr/bin/env python3
"""Offline verification of downloaded606 against the actual delivered605 IPA.

This reads final ZIP bytes, immutable producer archives and CI receipts. It
does not run compilers, tests, codesign, a simulator, or a physical device.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import plistlib
import re
import struct
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
BASE_SOURCE = '5de451091208c13926ccdb373a0a34f35ec2ee2d'
BASE_SHA = 'd51a4b138f54f5bbf88ab00a09856e3915a30ab71d9849b8aeaa9a7d8fb35337'
BASE_BYTES = 189643236
BASE_ENTRIES = 5363
EXPECTED_IMAGES = 89
EXPECTED_BUNDLES = 8
ROOT = 'Payload/NeoStation.app/'
IDENTITY = 'Hogwarts-performance-build-identity.json'
MAGICS = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe',
          b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf',
          b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'}
RETAINED_IMAGES = {
    'Frameworks/libRPCS3Core.dylib', 'Frameworks/DolphinCore.framework/DolphinCore',
    'Frameworks/ARMSX2Core.framework/ARMSX2Core', 'Frameworks/MoltenVK.framework/MoltenVK',
    'Frameworks/MeloNXMoltenVKStandalone.framework/MeloNXMoltenVKStandalone',
    'Frameworks/StikJIT.framework/StikJIT', 'Frameworks/Flutter.framework/Flutter',
    *('Frameworks/' + name + '.framework/' + name for name in
      ('MeloNXMoltenVK', 'MeloNXSDL3', 'MeloNXAvCodec', 'MeloNXAvUtil', 'MeloNXJitSupport')),
}
FLOOR18 = ('achievement_translation', 'armsx2_internal_bridge', 'dolphin_internal_bridge', 'libretro_internal_bridge')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            value.update(chunk)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def version(value):
    parts = tuple(int(p) for p in value.split('.'))
    return (parts + (0, 0, 0))[:3]


def arm64_slice(raw):
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


def load_modules(repository):
    sys.path[:0] = [str(repository / part) for part in
        ('build-utils', '.github/diagnostics', 'build-utils/melonx', 'packages/dolphin_internal_bridge/ci')]
    import verify_ipa
    import delivery_benchmark
    import rewind606_engine
    import hogwarts606_host
    import validate_no_kartpad_ipa
    import validate_no_dusklight_ipa
    import validate_melonx_ipa
    import validate_neoplay_ipa
    import validate_shader_compiler_ipa
    from embed_rpcs3_host_entitlements import embedded_entitlements, FORBIDDEN_NETWORK_ENTITLEMENTS
    from validate_rpcs3_core604_ipa import compare_core
    return dict(macho=verify_ipa.macho, fingerprint=delivery_benchmark.payload_fingerprint,
        engine=rewind606_engine, host=hogwarts606_host, kartpad=validate_no_kartpad_ipa.validate,
        dusklight=validate_no_dusklight_ipa.validate, melonx=validate_melonx_ipa.validate,
        neoplay=validate_neoplay_ipa.validate, shaders=validate_shader_compiler_ipa.validate,
        entitlements=embedded_entitlements, forbiddenEntitlements=FORBIDDEN_NETWORK_ENTITLEMENTS,
        compareRPC=compare_core)


def archive_inventory(archive, build, modules):
    names = modules['engine'].safe_members(archive)
    roots = [name for name in names if name.startswith('Payload/') and
             name.endswith('.app/Info.plist') and name.count('/') == 2]
    require(roots == [ROOT + 'Info.plist'], 'Expected the single retained app bundle')
    require(not any('.app/' in name[len(ROOT):] for name in names if name.startswith(ROOT)), 'Nested app is forbidden')
    info = plistlib.loads(archive.read(ROOT + 'Info.plist'))
    require(info['CFBundleDisplayName'] == info['CFBundleName'] == 'RewindBox', 'Wrong user-facing app name')
    require(info['CFBundleIdentifier'] == 'com.neogamelab.neostation', 'Compatibility bundle identifier changed')
    require(info['MinimumOSVersion'] == '18.0', 'Wrong application deployment floor')
    require(str(info['CFBundleVersion']) == str(build), 'Wrong downloaded build')
    bundles = {name[len(ROOT):]: plistlib.loads(archive.read(name)) for name in names
        if name == ROOT + 'Info.plist' or (name.startswith(ROOT + 'PlugIns/') and name.endswith('.appex/Info.plist'))}
    require(len(bundles) == EXPECTED_BUNDLES, 'Wrong app/extension count')
    for name, bundle in bundles.items():
        require(str(bundle['CFBundleVersion']) == str(build) and
                bundle['CFBundleShortVersionString'] == info['CFBundleShortVersionString'], 'Version mismatch: ' + name)
        require(version(bundle['MinimumOSVersion']) <= (18, 0, 0), 'Extension incompatible with iOS18: ' + name)
        point = bundle.get('NSExtension', {}).get('NSExtensionPointIdentifier')
        require(point != 'com.apple.networkextension.packet-tunnel', 'Retired VPN extension: ' + name)
    images, fingerprints = {}, {}
    for entry in archive.infolist():
        if entry.is_dir() or entry.file_size < 4:
            continue
        with archive.open(entry) as source:
            magic = source.read(4)
        if magic not in MAGICS:
            continue
        require(entry.filename.startswith(ROOT), 'Mach-O outside the single app')
        relative = entry.filename[len(ROOT):]
        raw = archive.read(entry)
        thin, container = arm64_slice(raw)
        image = modules['macho'](thin)
        require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] in (2, 6),
                'Non-device image: ' + relative)
        require(image['codeSignature'] is True, 'Missing signature blob: ' + relative)
        require(version(image['minimumOS']) <= (18, 0, 0), 'Mach-O incompatible with iOS18: ' + relative)
        if image['fileType'] == 2:
            entitlements = modules['entitlements'](thin)
            require(not set(entitlements) & set(modules['forbiddenEntitlements']), 'Retired VPN entitlement: ' + relative)
        images[relative] = {key: image[key] for key in ('architecture', 'platform', 'fileType', 'minimumOS', 'codeSignature')}
        images[relative]['container'] = container
        fingerprints[relative] = modules['fingerprint'](thin)
    require(len(images) == EXPECTED_IMAGES, 'Unexpected Mach-O inventory; explicit review is required')
    for name in FLOOR18:
        require(version(images['Frameworks/' + name + '.framework/' + name]['minimumOS']) == (18, 0, 0),
                'Translation consumer lost its iOS18 floor: ' + name)
    require(not any('BreakpointJIT.framework/' in name or 'NeoStationLocalTunnel' in name for name in names),
            'Retired JIT or VPN component present')
    return dict(entries=len(names), info=info, bundles=bundles, images=images, fingerprints=fingerprints)


def baseline(path, modules):
    require(path.stat().st_size == BASE_BYTES and digest(path) == BASE_SHA, 'This is not the actual delivered605 IPA')
    with zipfile.ZipFile(path) as archive:
        value = archive_inventory(archive, 605, modules)
        require(value['entries'] == BASE_ENTRIES, 'Delivered605 ZIP inventory changed')
        identity = json.loads(archive.read(ROOT + 'Achievement-translation-build-identity.json'))
        require(identity['application']['source'] == BASE_SOURCE and identity['build'] == 605, 'Wrong605 app identity')
    return value


def bind_artifact(path, pin, modules):
    require(path.stat().st_size == pin['bytes'] and digest(path) == pin['sha256'], 'Wrong exact producer archive: ' + path.name)
    archive = zipfile.ZipFile(path)
    modules['engine'].safe_members(archive)
    return archive


def core_producer(args, core_pin, modules):
    engine = modules['engine']
    if 'validation' in core_pin:
        require(args.original_core_archive is not None, 'Recovered producer needs --original-core-archive')
        helper, config, contract = engine.recovery_configuration(core_pin)
        proof = helper.verify_archive(args.original_core_archive, config, contract)
        with bind_artifact(args.core_archive, core_pin['validation'], modules) as core:
            names = {entry.filename for entry in core.infolist() if not entry.is_dir()}
            result = engine.validate_recovered_members(core_pin, core.read, names, proof, config, contract, helper)
            identities = {}
            for runtime in engine.RUNTIMES:
                raw = core.read(runtime + '/identity.json')
                require(sha(raw) == core_pin['identities'][runtime], 'Recovered identity changed')
                identity = json.loads(raw)
                binary = core.read(runtime + '/Ryujinx.Library.dylib')
                require(len(binary) == core_pin['binaries'][runtime]['bytes'] and
                        sha(binary) == core_pin['binaries'][runtime]['sha256'] == identity['sha256'], 'Recovered binary changed')
                require(identity['host'] == core_pin['source'] and identity['adaptations'] == contract['preparationInputs'] and
                        identity['embeddedLibraryAbi'] == 2 and sorted(identity['exports']) == sorted(engine.EXPORTS), 'Recovered Core source/ABI changed')
                engine.inputs_match(identity['adaptations'], core_pin['source'])
                engine.check_image(binary, runtime)
                identities[runtime] = identity
                if runtime == 'ios-arm64':
                    require(engine.normalized_payload_fingerprint(binary) == core_pin['packagedFingerprint'], 'Recovered original fingerprint differs')
        return result, identities
    with bind_artifact(args.core_archive, core_pin, modules) as core:
        raw = core.read('core-validation/result.json')
        require(sha(raw) == core_pin['resultSha256'], 'Wrong exact Core result')
        result = json.loads(raw)
        engine.verify_execution(result, core_pin, 'downloaded Core')
        require(result['result'] == 'passed' and result['binaries'] == core_pin['binaries'] and
                result['identities'] == core_pin['identities'], 'Core result did not validate the pinned binary')
        contract_raw = (args.repository / engine.CONTRACT).read_bytes()
        require(sha(contract_raw) == core_pin['contractSha256'] == result['performanceCoreContractSha256'], 'Wrong Core contract')
        contract = json.loads(contract_raw)
        engine.inputs_match(contract['inputs'], core_pin['source'])
        engine.inputs_match(contract['preparationInputs'], core_pin['source'])
        engine.inputs_match(result['inputs'], core_pin['source'])
        identities = {}
        for runtime in ('ios-arm64', 'iossimulator-arm64'):
            identity_raw = core.read(runtime + '/identity.json')
            require(sha(identity_raw) == core_pin['identities'][runtime], 'Producer identity bytes changed')
            identity = json.loads(identity_raw)
            raw_binary = core.read(runtime + '/Ryujinx.Library.dylib')
            require(len(raw_binary) == core_pin['binaries'][runtime]['bytes'] and
                    sha(raw_binary) == core_pin['binaries'][runtime]['sha256'] == identity['sha256'], 'Producer binary changed')
            require(identity['host'] == core_pin['source'] and identity['adaptations'] == contract['preparationInputs'] and
                    identity['embeddedLibraryAbi'] == 2 and sorted(identity['exports']) == sorted(engine.EXPORTS), 'Core source/ABI changed')
            engine.check_image(raw_binary, runtime)
            identities[runtime] = identity
            if runtime == 'ios-arm64':
                require(engine.normalized_payload_fingerprint(raw_binary) == core_pin['packagedFingerprint'], 'Original Core fingerprint differs')
        prepared_raw = core.read('embedded-adapted-source.zip')
        require(sha(prepared_raw) == result['embeddedArchiveSha256'], 'Prepared source archive changed')
        with zipfile.ZipFile(io.BytesIO(prepared_raw)) as prepared:
            names = engine.safe_members(prepared)
            require({name: sha(prepared.read(name)) for name in names} == contract['preparedMembers'], 'Wrong final compiled sources')
        gates_raw = core.read('core-validation/gates.json')
        require(sha(gates_raw) == result['gateReceiptSha256'], 'Gate index changed')
        gates = json.loads(gates_raw)
        require(gates['freshAppleGates'] == result['freshAppleGates'] == 4 and
                gates['reusedAppleGates'] == contract['reusedAppleGates'] and gates['historicalAppleReceipts'] == 40,
                'Wrong producer gate scopes')
        require(gates['retainedDisposition'] == contract['retainedDisposition'] and
                gates['retainedChangedDependencies'] == contract['retainedChangedDependencies'], 'Historical scope changed')
        for gate in contract['gates']:
            raw = core.read(gate['report'])
            require(sha(raw) == gates['receipts'][gate['report']], 'Fresh receipt changed')
            engine.verify_gate(json.loads(raw), gate, contract, core_pin['source'])
        for name, expected in {**gates['retainedReceipts'], **gates['baselineEvidenceSha256'], **result['reusedEvidenceSha256']}.items():
            require(sha(core.read(name)) == expected, 'Retained producer evidence changed: ' + name)
        smoke_raw = core.read('runtime-smoke/actual-runtime.json')
        require(sha(smoke_raw) == result['runtimeSmokeSha256'], 'Actual simulator receipt changed')
        smoke = json.loads(smoke_raw)
        from validate_runtime_reuse import verify_smoke_report
        from verify_performance_core import verify_performance_smoke
        before = json.loads(core.read('core-validation/preflight.json'))
        engine.verify_execution(before, core_pin, 'Core preflight')
        engine.inputs_match(before['smokeInputs'], core_pin['source'])
        verify_smoke_report(smoke, {'simulatorSha256': core_pin['binaries']['iossimulator-arm64']['sha256']}, before['smokeInputs'])
        require(verify_performance_smoke(smoke) == result['performanceDiagnosticsFinalSessions'] == 2,
                'Missing final diagnostics from actual NativeAOT sessions')
        require(result['homebrewSimulatorSessions'] == result['releasedBackingSessions'] == 2 and
                all(result[key] is False for key in ('physicalDeviceTested', 'gameplayTested', 'fpsGainProven', 'historicalGatesReexecuted')),
                'Overstated Core execution scope')
    return result, identities


def new_producers(args, pins, modules):
    engine, host = modules['engine'], modules['host']
    core_pin, host_pin = pins['core'], pins['host']
    result, identities = core_producer(args, core_pin, modules)
    with bind_artifact(args.host_archive, host_pin, modules) as archive:
        result_raw = archive.read(host_pin['resultPath'])
        require(sha(result_raw) == host_pin['resultSha256'], 'Host result bytes changed')
        host_result = json.loads(result_raw)
        prefix = str(PurePosixPath(host_pin['resultPath']).parent)
        prefix = '' if prefix == '.' else prefix + '/'
        outputs = {name[len(prefix):]: archive.read(name) for name in archive.namelist()
                   if name.startswith(prefix) and '/' not in name[len(prefix):] and not name.endswith('/')}
        preflight = json.loads(outputs['preflight.json'])
        engine.verify_execution(preflight, host_pin, 'host preflight')
        require(preflight['inputs'] == host_pin['inputsSHA256'], 'Host tested other inputs')
        engine.inputs_match(preflight['inputs'], host_pin['source'])
        changed = subprocess.check_output(['git', 'diff', '--name-only', host.BASELINE, host_pin['source'], '--', 'lib', 'packages'], cwd=args.repository, text=True).splitlines()
        require(preflight['analyzerPaths'] == sorted(set(host.TESTS) | {p for p in changed if p.endswith('.dart')}), 'Host analyzer scope changed')
        engine.verify_host_recovery(preflight, outputs, host_pin, live_origin=False)
        require(host.result_from_outputs(preflight, outputs) == host_result, 'Original host logs do not reproduce result')
    return dict(coreResult=result, coreIdentity=identities['ios-arm64'], hostResult=host_result)



def retired_metadata_resolution(scan, identity_raw, authenticated_host):
    """Resolve only three known audit mentions in the already authenticated host proof.

    The canonical scanner is unchanged and its failed result remains in the
    report. The caller has verified authenticated_host against the exact host
    artifact, Git inputs and original command outputs before reaching here.
    """
    require(scan['passed'] is False and scan['findings'] ==
            {IDENTITY: ["3 occurrence(s) of 'dusklight'"]},
            'Retired component finding outside the exact authenticated audit document')
    identity = json.loads(identity_raw)
    host = identity['hostChecks']['originalHostResult']
    require(host == authenticated_host and host['result'] == 'passed', 'Audit host result differs from its authenticated producer')
    input_name = 'test/no_dusklight_ipa_test.py'
    input_sha = '2fc8fe45d34ee164e77b96dacabdffdcbc5fba449c38292a9f025b388f3198b4'
    names = {18: 'what Dusklight left is unknown, hence never deletable',
             54: "the KartPad cache folder is level 2, never during a game; Dusklight's is never proposed"}
    prefix = ('hostChecks', 'originalHostResult')
    expected = {('key', prefix + ('inputs', input_name)): input_sha,
                **{('value', prefix + ('flutter', 'names', index)): value for index, value in names.items()}}
    occurrences = {}

    def inspect(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                if 'dusklight' in key.lower():
                    occurrences[('key', path + (key,))] = child
                inspect(child, path + (key,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                inspect(child, path + (index,))
        elif isinstance(value, str) and 'dusklight' in value.lower():
            occurrences[('value', path)] = value

    inspect(identity)
    require(occurrences == expected and len(re.findall(rb'(?i)dusklight', identity_raw)) == 3,
            'Unexpected retired-component mention in the audit document')
    return dict(result='accepted-authenticated-audit-metadata-only', canonicalGuardPassed=False,
        member=IDENTITY, memberSHA256=sha(identity_raw), occurrenceCount=3,
        occurrences=[dict(kind=kind, path=list(path), value=value) for (kind, path), value in expected.items()],
        authenticatedHostExecution=authenticated_host['execution'],
        runtimeOrAssetExceptionGranted=False, sharedCanonicalGuardModified=False,
        scope='One removal-guard input filename and two actual storage-cleanup test names in the exact authenticated host result')


def delivery_metadata(args, receipts):
    run, job = read(args.run_metadata), read(args.job_metadata)
    require(run['head_sha'] == job['head_sha'] == args.app_source and run['id'] == job['run_id'] and
            run['conclusion'] == job['conclusion'] == 'success' and run['status'] == 'completed' and
            run['head_branch'] == 'Claude' and job['status'] == 'completed' and
            run['run_attempt'] == job['run_attempt'] and
            run['path'] == '.github/workflows/rewind606-hogwarts-performance-delivery.yml', 'Wrong successful IPA producer metadata')
    required = {'Compile Release device binary with measured AOT and Xcode phases',
                'Seal every executable, framework and extension for SideStore',
                'Verify actual signed translation plugin, fresh MeloNX and retained engines',
                'Verify final signed legal bundle and application and extension versions'}
    require(required <= {step['name'] for step in job['steps'] if step['conclusion'] == 'success'}, 'Missing successful signing/final validation steps')
    signed = receipts['signed-payload-identity.json']
    signature = receipts['signature.json']
    require(signed['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True and
            signed['abiMetadataUnchangedBySigning'] is True and signed['sideStoreAppleReSigningRequired'] is True,
            'Missing complete signing/payload audit')
    require(signed['imageCount'] == len(signed['images']) == EXPECTED_IMAGES and
            signed['completeNativeInventoryCheckedBeforeAndAfterSigning'] is True and
            signed['completeNativeInventoryCheckedInFinalZIP'] is True,
            'Inherited thin-only audit is insufficient for the downloaded606 IPA')
    require(signature['build'] == '606' and signature['minimumIOS'] == '18.0' and signature['architectures'] == ['arm64'] and
            signature['directAppleInstallationReady'] is False and signature['deviceInstallationTested'] is False and
            len(signature['signatures']) == EXPECTED_IMAGES and
            all(entry['signatureVerified'] is True and entry['appleProvisioningVerified'] is False for entry in signature['signatures']),
            'Missing actual macOS signature verification receipt')
    return dict(source=args.app_source, run=run['id'], job=job['id'], attempt=run['run_attempt'],
                macOSSignatureChecksReportedPassed=True, cryptographicSignatureVerificationPerformedHere=False)


def verify(args, modules, previous):
    pins = read(args.pins)
    require(pins['status'] == 'verified-producers' and pins['build'] == 606 and
            pins['baseline']['source'] == BASE_SOURCE and pins['baseline']['ipaSha256'] == BASE_SHA and
            pins['baseline']['ipaBytes'] == BASE_BYTES, 'Producer pins are pending or based on another IPA')
    require(re.fullmatch('[0-9a-f]{40}', args.app_source), 'Exact application source is required')
    require(args.pins.read_bytes() == subprocess.check_output(['git', 'show',
            args.app_source + ':build-utils/rewind606-delivery.json'], cwd=args.repository),
            'Pins are not the immutable configuration committed in the actual IPA source')
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.repository, text=True).strip() == args.app_source,
            'Repository must be the exact application checkout for source/legal verification')
    require(not subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=args.repository).strip(), 'Repository has uncommitted tracked source changes')
    receipt_names = ('rewind606-ipa-validation.json', 'signed-payload-identity.json', 'signature.json', 'version-validation.json')
    receipts = {name: read(args.receipts / name) for name in receipt_names}
    origin = delivery_metadata(args, receipts)
    ipa_sha, ipa_bytes = digest(args.ipa), args.ipa.stat().st_size
    for name, hash_key in (('rewind606-ipa-validation.json', 'ipaSHA256'), ('signed-payload-identity.json', 'ipaSha256')):
        require(receipts[name][hash_key] == ipa_sha and receipts[name]['ipaBytes'] == ipa_bytes, 'Downloaded IPA differs from final CI receipt: ' + name)
    require(receipts['rewind606-ipa-validation.json']['result'] == 'passed', 'Final IPA validation failed')
    producers = new_producers(args, pins, modules)
    with zipfile.ZipFile(args.ipa) as archive, zipfile.ZipFile(args.baseline) as old:
        current = archive_inventory(archive, 606, modules)
        require(set(current['images']) == set(previous['images']), 'Unexpected native component added or removed')
        require(set(current['bundles']) == set(previous['bundles']), 'Extension composition changed from605')
        for name, bundle in current['bundles'].items():
            require(bundle['CFBundleIdentifier'] == previous['bundles'][name]['CFBundleIdentifier'] and
                    bundle['CFBundleExecutable'] == previous['bundles'][name]['CFBundleExecutable'] and
                    bundle.get('NSExtension', {}).get('NSExtensionPointIdentifier') ==
                    previous['bundles'][name].get('NSExtension', {}).get('NSExtensionPointIdentifier'),
                    'Extension role or executable changed: ' + name)
        require(current['info']['CFBundleShortVersionString'] == previous['info']['CFBundleShortVersionString'], 'Unexpected marketing version')
        require(current['fingerprints'] == receipts['signed-payload-identity.json']['images'], 'Final ZIP differs from all-image signing receipt')
        require({name: image['container'] for name, image in current['images'].items()} ==
                receipts['signed-payload-identity.json']['architectureContainers'], 'Final Mach-O container inventory changed')
        signed_targets = {'.' if name == 'Runner' else name if name.endswith('.dylib') else PurePosixPath(name).parent.as_posix()
                          for name in current['images']}
        require(len(signed_targets) == EXPECTED_IMAGES and
                {entry['bundle'] for entry in receipts['signature.json']['signatures']} == signed_targets,
                'Signing receipt omitted or duplicated a framework, executable or extension')
        versions = receipts['version-validation.json']
        require(versions['result'] == 'passed' and versions['build'] == 606 and
                versions['version'] == current['info']['CFBundleShortVersionString'] and
                set(versions['bundles']) == {ROOT + name for name in current['bundles']}, 'Version receipt does not describe final ZIP')
        retained = RETAINED_IMAGES | {name for name in previous['images'] if re.search(r'/[^/]+_libretro\.framework/[^/]+_libretro$', name)}
        require(retained <= current['fingerprints'].keys(), 'Missing retained engine/dependency')
        for name in retained:
            require(current['fingerprints'][name] == previous['fingerprints'][name], 'Retained component payload changed: ' + name)
        rpc = modules['compareRPC'](archive.read(ROOT + 'Frameworks/libRPCS3Core.dylib'), old.read(ROOT + 'Frameworks/libRPCS3Core.dylib'), signed=True)
        identity_raw = archive.read(ROOT + IDENTITY)
        identity = json.loads(identity_raw)
        require(identity == receipts['rewind606-ipa-validation.json']['identity'], 'Embedded application identity differs from final CI receipt')
        application = identity['application']
        require(identity['build'] == 606 and application['source'] == args.app_source and
                application['reviewedSource'] == pins['reviewedSource'] and application['baseline'] == pins['baseline'] and
                application['productDelta'] == pins['productDelta'] and application['productTrees'] == pins['productTrees'] and
                application['concurrentHostDelta'] == pins['concurrentHostDelta'], 'Wrong reviewed application delta')
        require(identity['hostChecks']['originalHostResult'] == producers['hostResult'], 'Packaged host proof differs from its exact producer')
        old_identity = json.loads(old.read(ROOT + 'Achievement-translation-build-identity.json'))
        require(identity['dolphin'] == old_identity['dolphin'], 'Delivered605 achievement Dolphin identity changed')
        require(identity['translationTests']['originalResult'] == old_identity['translationTests'] and
                identity['translationTests']['historicalTestsReexecuted'] is False and
                identity['translationTests']['currentWholeApplicationInputsIdentical'] is False, 'Historical RA proof relabelled')
        require(identity['retainedRPCS3']['coreSource'] == old_identity['retainedRPCS3']['coreSource'] and
                identity['retainedRPCS3']['coreSHA256'] == old_identity['retainedRPCS3']['coreSHA256'], 'Wrong retained RPCS3 Core')
        native = json.loads(archive.read(ROOT + 'MeloNX-native-identity.json'))
        old_native = json.loads(old.read(ROOT + 'MeloNX-native-identity.json'))
        require(native['sourceCoreIdentity'] == producers['coreIdentity'] and native['sourceDependenciesIdentity'] == old_native['sourceDependenciesIdentity'],
                'Packaged Core or unchanged dependency identity differs')
        core_path = 'Frameworks/MeloNXCore.framework/MeloNXCore'
        require(current['fingerprints'][core_path] == pins['core']['packagedFingerprint'] and
                current['fingerprints'][core_path] != previous['fingerprints'][core_path], 'Wrong fresh Core or old Core silently reused')
        require(identity['newMeloNX']['binaries'] == pins['core']['binaries'] and
                identity['newMeloNX']['identities'] == pins['core']['identities'], 'New Core receipt points elsewhere')
        if 'validation' in pins['core']:
            new_core = identity['newMeloNX']
            actual = producers['coreResult']
            require(new_core['originalRunConclusion'] == 'failure' and
                    new_core['originalProducer'] == actual['originalProducer'] and
                    new_core['originalFailedStep'] == actual['originalFailedStep'] and
                    new_core['separateValidation'] == actual['validation'] and
                    new_core['validationResultSHA256'] == pins['core']['validation']['resultSha256'] and
                    new_core['originalMembersSHA256'] == actual['originalMembersSha256'] and
                    new_core['originalContractSHA256'] == actual['contractSha256'] and
                    new_core['currentContractSHA256'] == actual['currentContractSha256'] and
                    new_core['verifierChanges'] == actual['verifierChanges'], 'Packaged Core recovery provenance differs')
        require(identity['hostChecks'].get('recovery') == producers['hostResult'].get('recovery'),
                'Packaged host recovery provenance differs')
        helper = 'PlugIns/MeloNXJITHelper.appex/melonx-universal.js'
        require(archive.read(ROOT + helper) == old.read(ROOT + helper) ==
                (args.repository / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes(), 'JIT helper script changed')
        static_names = {name for name in old.namelist() if name.startswith(ROOT + 'Sys/') and not name.endswith('/')}
        require(static_names == {name for name in archive.namelist() if name.startswith(ROOT + 'Sys/') and not name.endswith('/')}, 'Dolphin Sys composition changed')
        for name in static_names:
            require(sha(archive.read(name)) == sha(old.read(name)), 'Retained Dolphin resource changed: ' + name)
        legal_record = json.loads(archive.read(ROOT + 'Legal/RPCS3-current-core/actual-compiled-source.json'))
        old_legal = json.loads(old.read(ROOT + 'Legal/RPCS3-current-core/actual-compiled-source.json'))
        require(legal_record['inputs'] == old_legal['inputs'] and legal_record['coreSHA256'] == old_legal['coreSHA256'], 'RPCS3 actual compiled source identity changed')
        source_zip = archive.read(ROOT + 'Legal/RPCS3-current-core/compiled-host-inputs.zip')
        require(sha(source_zip) == legal_record['compiledInputsZipSHA256'], 'RPCS3 source ZIP digest changed')
        with zipfile.ZipFile(io.BytesIO(source_zip)) as sources:
            members = modules['engine'].safe_members(sources)
            require({name: sha(sources.read(name)) for name in members} == legal_record['inputs'], 'RPCS3 compiled source bytes differ')
        for name in old.namelist():
            if name.startswith(ROOT + 'Legal/Dolphin-achievement-presentation/') and not name.endswith('/'):
                require(archive.read(name) == old.read(name), 'Retained RA Dolphin legal source changed')
        translation = archive.read(ROOT + 'Frameworks/achievement_translation.framework/achievement_translation')
        for marker in (b'AchievementTranslationPlugin', b'RBAchievementText', b'RBAchievementToast', b'rewindbox/achievement_translation', b'RBAchievementPresent'):
            require(marker in translation, 'Missing actual translated achievement implementation')
    removed = dict(kartpad=modules['kartpad'](args.ipa, '606'), dusklight=modules['dusklight'](args.ipa, '606'))
    require(removed['kartpad']['passed'], 'Removed KartPad or game-origin content returned')
    if not removed['dusklight']['passed']:
        removed['dusklightMetadataResolution'] = retired_metadata_resolution(
            removed['dusklight'], identity_raw, producers['hostResult'])
    legal = subprocess.run([sys.executable, str(args.repository / 'build-utils/validate_legal_bundle_ipa.py'), str(args.ipa),
        '--build-number', '606', '--commit', args.app_source], cwd=args.repository, capture_output=True, check=True)
    return dict(result='passed', mode='downloaded606-offline-validation', ipaSHA256=ipa_sha, ipaBytes=ipa_bytes,
        baseline=dict(build=605, ipaSHA256=BASE_SHA, ipaBytes=BASE_BYTES, source=BASE_SOURCE),
        origin=origin, entries=current['entries'], bundleCount=len(current['bundles']), machoCount=len(current['images']),
        images=current['images'], retainedPayloadFingerprints={name: current['fingerprints'][name] for name in sorted(retained)},
        newCoreFingerprint=pins['core']['packagedFingerprint'], nativeDependencyIdentitiesUnchanged=True,
        retainedRPCS3=rpc, retainedDolphinResourceFiles=len(static_names), removedComponents=removed,
        melonx=modules['melonx'](args.ipa), neoplay=modules['neoplay'](args.ipa, '606', args.app_source),
        shaders=modules['shaders'](args.ipa, '606'), legal=dict(result='passed', stdoutSHA256=sha(legal.stdout)),
        receiptSHA256={name: digest(args.receipts / name) for name in receipt_names},
        producerArchivesSHA256=dict(core=digest(args.core_archive), host=digest(args.host_archive),
            originalCore=digest(args.original_core_archive) if args.original_core_archive else None),
        coreOriginalRunConclusion=producers['coreResult'].get('originalRunConclusion', 'success'),
        coreSeparateValidation=producers['coreResult'].get('validation'),
        hostRecovery=producers['hostResult'].get('recovery'),
        signaturePresenceCheckedForAllImages=True, cryptographicSignatureVerificationPerformedHere=False,
        appleProvisioningVerified=False, sideStoreAppleReSigningRequired=True,
        physicalDeviceTested=False, gameplayTested=False, fpsGainProven=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=Path('/workspace/scratch/c5e4042e4ea8/delivery605/RewindBox-605.ipa'))
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--ipa', type=Path)
    parser.add_argument('--pins', type=Path)
    parser.add_argument('--receipts', type=Path)
    parser.add_argument('--core-archive', type=Path)
    parser.add_argument('--original-core-archive', type=Path)
    parser.add_argument('--host-archive', type=Path)
    parser.add_argument('--run-metadata', type=Path)
    parser.add_argument('--job-metadata', type=Path)
    parser.add_argument('--app-source')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    modules = load_modules(args.repository)
    previous = baseline(args.baseline, modules)
    if args.baseline_only:
        result = dict(result='authenticated', mode='baseline605-only', candidate606Validated=False,
            ipaSHA256=BASE_SHA, ipaBytes=BASE_BYTES, entries=previous['entries'], bundleCount=len(previous['bundles']),
            machoCount=len(previous['images']), images=previous['images'], fingerprints=previous['fingerprints'],
            cryptographicSignatureVerificationPerformedHere=False)
    else:
        for field in ('ipa', 'pins', 'receipts', 'core_archive', 'host_archive', 'run_metadata', 'job_metadata', 'app_source'):
            require(getattr(args, field) is not None, 'Missing --' + field.replace('_', '-'))
        result = verify(args, modules, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key in
        ('result', 'mode', 'ipaSHA256', 'ipaBytes', 'entries', 'bundleCount', 'machoCount', 'candidate606Validated',
         'cryptographicSignatureVerificationPerformedHere')}, indent=2))


if __name__ == '__main__':
    main()
