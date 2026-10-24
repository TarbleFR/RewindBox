"""Assemble the scoped native Core changes from an authenticated compiled app523."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.github/diagnostics'),
               str(ROOT / 'packages/dolphin_internal_bridge/ci')]
import rpcs3arm526_delivery as source
from delivery_benchmark import payload_fingerprint, seal
from embed_rpcs3_host_entitlements import embedded_entitlements
from verify_ipa import macho

CORE = 'Frameworks/libRPCS3Core.dylib'
OLD_RECEIPT = 'RPCS3-cell523-identity.json'
RECEIPT = 'RPCS3-arm526-identity.json'
REUSE = 'RPCS3-arm526-app-reuse.json'
LEGAL_ID = 'Legal/BUILD_SOURCE_IDENTITY.json'
LEGAL_SOURCE = 'Legal/Sources/BUILD_SOURCE_EVIDENCE.json'
RETAINED = {
    'Legal/Sources/RPCS3-ARM526/canonical-source.json': 'build-utils/rpcs3/canonical-source.json',
    'Legal/Sources/RPCS3-ARM526/embedded-core.patch': 'build-utils/rpcs3/embedded-core.patch',
    'Legal/Sources/RPCS3-ARM526/build_rpcs3_embedded_core.sh': 'build-utils/build_rpcs3_embedded_core.sh',
}
VARIABLE_ASSETS = {OLD_RECEIPT, RECEIPT, REUSE, LEGAL_ID, LEGAL_SOURCE, *RETAINED}
MAGICS = {b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'}
OUT = ROOT / 'build/delivery'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def arm64(data):
    if data[:4] == b'\xcf\xfa\xed\xfe':
        return data
    assert data[:4] in MAGICS
    wide = data[:4] == b'\xca\xfe\xba\xbf'
    count = struct.unpack_from('>I', data, 4)[0]
    assert 0 < count <= 32
    choices = []
    for index in range(count):
        pos = 8 + index * (32 if wide else 20)
        cpu = struct.unpack_from('>I', data, pos)[0]
        offset, length = struct.unpack_from('>QQ' if wide else '>II', data, pos + 8)
        assert offset + length <= len(data)
        if cpu == 0x0100000c:
            choices.append(data[offset:offset + length])
    assert len(choices) == 1
    return choices[0]


def snapshot(entries):
    assets, images, entitlements = [], {}, {}
    for name, data, symlink in entries:
        if '_CodeSignature' in name.split('/'):
            continue
        if not symlink and data[:4] in MAGICS:
            binary = arm64(data)
            images[name] = payload_fingerprint(binary)
            if capabilities := embedded_entitlements(binary):
                entitlements[name] = capabilities
        elif name not in VARIABLE_ASSETS:
            if name == 'Info.plist' or (name.startswith('PlugIns/') and len(name.split('/')) == 3 and name.endswith('.appex/Info.plist')):
                info = plistlib.loads(data)
                info['CFBundleVersion'] = '<build>'
                data = plistlib.dumps(info, sort_keys=True)
            assets.append([name, sha(data)])
    assets.sort()
    return dict(assetCount=len(assets), assetRootSHA256=sha(json.dumps(assets, ensure_ascii=False,
        separators=(',', ':')).encode()), images=images, entitlements=entitlements)


def app_entries(app):
    for path in app.rglob('*'):
        if path.is_symlink():
            yield path.relative_to(app).as_posix(), os.readlink(path).encode(), True
        elif path.is_file():
            yield path.relative_to(app).as_posix(), path.read_bytes(), False


def zip_entries(archive, root):
    for item in archive.infolist():
        if item.filename.startswith(root) and not item.is_dir():
            yield item.filename.removeprefix(root), archive.read(item), stat.S_ISLNK(item.external_attr >> 16)


def baseline():
    data = (ROOT / source.FIXTURE).read_bytes()
    assert sha(data) == source.FIXTURE_SHA
    result = json.loads(data)
    assert result['ipaSHA256'] == source.BASE_IPA_SHA and result['compiledAppSource'] == source.APP_SOURCE
    return result


def compare(observed, expected, core_fingerprint):
    assert observed['assetCount'] == expected['assetCount'] and observed['assetRootSHA256'] == expected['assetRootSHA256'], 'App resource bytes/paths changed outside the native assembly scope'
    assert observed['entitlements'] == expected['entitlements'], 'Runtime capabilities changed'
    images = dict(expected['images'])
    images[CORE] = core_fingerprint
    assert observed['images'] == images, 'Compiled code/data/ABI differs outside the RPCS3 Core'


def record_baseline(ipa, output):
    with ipa.open('rb') as f:
        assert hashlib.file_digest(f, 'sha256').hexdigest() == source.BASE_IPA_SHA
    with zipfile.ZipFile(ipa) as archive:
        root = 'Payload/NeoStation.app/'
        result = snapshot(zip_entries(archive, root))
        result.update(schema=1, compiledAppSource=source.APP_SOURCE, compiledAppRun=source.APP_RUN,
            ipaSHA256=source.BASE_IPA_SHA, build=523, oldCoreReceiptSHA256=sha(archive.read(root + OLD_RECEIPT)),
            coreExports=macho(archive.read(root + CORE))['definedSymbols'],
            policy='Every ARM64 image and all other assets retained; only Info build numbers, signatures and enumerated native provenance may vary')
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('Recorded authenticated app523:', len(result['images']), 'ARM64 images,', result['assetCount'], 'retained asset entries')


def prepare():
    source.source_closure()
    reference = baseline()
    stage = ROOT / 'build/ios/dolphin-unsigned'
    assert not stage.exists()
    app = stage / 'Payload/NeoStation.app'
    compiled = ROOT / 'build/ios/DolphinDerivedData/Build/Products/Release-iphoneos/Runner.app'
    assert compiled.is_dir(), 'Exact compiled app523 is absent from the authenticated cache'
    shutil.copytree(compiled, app, symlinks=True)
    # The existing package step removes this one byte-identical redundant copy.
    duplicate = app / 'PlugIns/DolphinJITHelper.appex/Frameworks/StikJIT.framework'
    if duplicate.exists():
        assert (duplicate / 'StikJIT').read_bytes() == (app / 'Frameworks/StikJIT.framework/StikJIT').read_bytes()
        helper = app / 'PlugIns/DolphinJITHelper.appex/DolphinJITHelper'
        assert '@executable_path/../../Frameworks' in macho(helper.read_bytes())['rpaths']
        shutil.rmtree(duplicate)
    compare(snapshot(app_entries(app)), reference, reference['images'][CORE])
    old = (app / OLD_RECEIPT).read_bytes()
    assert sha(old) == reference['oldCoreReceiptSHA256']
    prior = json.loads(old)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'rpcs3-cpu-escrow-proof.json').write_text(json.dumps(prior['hostBootstrapProof']))
    original_evidence = json.loads((app / LEGAL_SOURCE).read_bytes())
    core_path = ROOT / 'dist/rpcs3-native/libRPCS3Core.dylib'
    identity_path = ROOT / 'dist/rpcs3-native/identity.json'
    identity = json.loads(identity_path.read_bytes())
    source.validate_rpc_core_identity(identity)
    core = core_path.read_bytes()
    assert sha(core) == identity['sha256']
    shutil.copyfile(core_path, app / CORE)
    (app / CORE).chmod(0o755)
    for path in [app / 'Info.plist', *app.glob('PlugIns/*.appex/Info.plist')]:
        info = plistlib.loads(path.read_bytes())
        assert info['CFBundleVersion'] == '523'
        info['CFBundleVersion'] = '526'
        path.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
    (app / OLD_RECEIPT).unlink()
    from validate_rpcs3_arm526_ipa import embed
    embed(app, core_path, identity_path)
    reuse = dict(schema=1, compiledAppSource=source.APP_SOURCE, compiledAppRun=source.APP_RUN,
        compiledAppBuild=523, baselineIPASHA256=source.BASE_IPA_SHA, assemblySource=os.environ['GITHUB_SHA'],
        coreSource=source.CORE_SOURCE, coreRun=source.CORE_RUN, appCodeRecompiled=False,
        allOtherARM64ImagesAndAssetsPreserved=True, baselineFixtureSHA256=source.FIXTURE_SHA,
        physicalDeviceTested=False, physicalPerformanceMeasured=False)
    (app / REUSE).write_text(json.dumps(reuse, indent=2) + '\n')
    # The legal generator recreates its directory. Preserve actual resolved
    # SDK/plugin and embedded-engine notices from the authenticated app first.
    with tempfile.TemporaryDirectory(prefix='arm526-original-legal-') as temporary:
        backup = Path(temporary) / 'Legal'
        shutil.copytree(app / 'Legal', backup, symlinks=True)
        with (OUT / 'legal-package.log').open('wb') as log:
            subprocess.run(['python3', 'build-utils/embed_legal_bundle.py', '--app', str(app),
                '--build-number', '526', '--dolphin-sha', '7cac54161659421ed95c2cd1c0b0746539a4cd38'], cwd=ROOT,
                stdout=log, stderr=subprocess.STDOUT, check=True)
        for original in backup.rglob('*'):
            relative = original.relative_to(backup)
            if relative.as_posix() in {'BUILD_SOURCE_IDENTITY.json', 'Sources/BUILD_SOURCE_EVIDENCE.json'}:
                continue
            if original.is_dir() and not original.is_symlink():
                continue
            current = app / 'Legal' / relative
            if current.exists() or current.is_symlink():
                assert current.is_symlink() == original.is_symlink(), relative
                if original.is_symlink():
                    assert os.readlink(current) == os.readlink(original), relative
                else:
                    assert current.read_bytes() == original.read_bytes(), relative
            else:
                current.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, current, follow_symlinks=False)
    evidence = json.loads((app / LEGAL_SOURCE).read_bytes())
    # Keep the actual original Flutter/plugin observations when no SDK is run.
    for relative in ('Build/flutter-plugin-selection.json', 'Build/flutter-sdk-version.json'):
        path = app / 'Legal/Sources' / relative
        expected = original_evidence['captured_files_sha256'].get(relative)
        if expected:
            assert sha(path.read_bytes()) == expected
            evidence['captured_files_sha256'][relative] = expected
    evidence['flutter_sdk_identity'] = 'reused_from_authenticated_build523'
    evidence['compiled_host_reuse'] = reuse
    for relative, repository in RETAINED.items():
        data = (ROOT / repository).read_bytes()
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        evidence['captured_files_sha256'][relative.removeprefix('Legal/Sources/')] = sha(data)
    (app / LEGAL_SOURCE).write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
    legal = json.loads((app / LEGAL_ID).read_bytes())
    legal['build_source_evidence_sha256'] = sha((app / LEGAL_SOURCE).read_bytes())
    legal['compiled_host_reuse'] = reuse
    (app / LEGAL_ID).write_text(json.dumps(legal, indent=2, ensure_ascii=False) + '\n')
    compare(snapshot(app_entries(app)), reference, payload_fingerprint(core))
    (ROOT / 'dist/NeoStation.ipa').touch()
    seal()
    validate(ROOT / 'dist/NeoStation.ipa')


def validate(ipa):
    from validate_rpcs3_arm526_ipa import validate as validate_core
    from ipa_extension_versions import validate_extension_versions
    result = validate_core(ipa, 526)
    reference = baseline()
    with zipfile.ZipFile(ipa) as archive:
        root = 'Payload/NeoStation.app/'
        assert archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist()))
        observed = snapshot(zip_entries(archive, root))
        compare(observed, reference, result['compiledCorePayloadFingerprint'])
        assert macho(archive.read(root + CORE))['definedSymbols'] == reference['coreExports']
        assert root + OLD_RECEIPT not in archive.namelist()
        reuse = json.loads(archive.read(root + REUSE))
        assert reuse['compiledAppSource'] == source.APP_SOURCE and reuse['compiledAppRun'] == source.APP_RUN
        assert reuse['baselineIPASHA256'] == source.BASE_IPA_SHA and reuse['baselineFixtureSHA256'] == source.FIXTURE_SHA
        assert reuse['appCodeRecompiled'] is False and reuse['coreSource'] == source.CORE_SOURCE and reuse['coreRun'] == source.CORE_RUN
        assert reuse['physicalDeviceTested'] is False and reuse['physicalPerformanceMeasured'] is False
        assert reuse['allOtherARM64ImagesAndAssetsPreserved'] is True
        extensions = validate_extension_versions(archive, root, 526)
        for relative, repository in RETAINED.items():
            assert archive.read(root + relative) == (ROOT / repository).read_bytes()
    result.update(compiledAppSource=source.APP_SOURCE, compiledAppRun=source.APP_RUN,
        appCodeRecompiled=False, unchangedOtherARM64Images=len(observed['images']) - 1,
        preservedAssetEntries=observed['assetCount'], preservedAssetRootSHA256=observed['assetRootSHA256'],
        allRuntimeEntitlementsUnchanged=True, extensionVersionsChecked=extensions,
        nativeSourceAndLicensesRetained=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'arm526-package-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot-baseline', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--validate', type=Path)
    args = p.parse_args()
    if args.snapshot_baseline:
        assert args.output
        record_baseline(args.snapshot_baseline, args.output)
    elif args.validate:
        validate(args.validate)
    else:
        prepare()
