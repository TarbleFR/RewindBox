#!/usr/bin/env python3
"""Verify the downloaded Build605 IPA against its actual Apple CI receipts.

Offline byte, payload and signature-structure checks. This does not claim an
iPhone launch, Apple provisioning or independent cryptographic verification of
the code signatures. The latter were verified with codesign on the CI Mac.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
SOURCE = '5de451091208c13926ccdb373a0a34f35ec2ee2d'
BUILD = '605'
sys.path[:0] = [str(ROOT / 'build-utils'),
                str(ROOT / 'packages/dolphin_internal_bridge/ci')]
from verify_ipa import validate as validate_structure, macho
from delivery_benchmark import payload_fingerprint
from validate_neoplay_ipa import validate as validate_neoplay
from validate_shader_compiler_ipa import validate as validate_shaders


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


# Same bounded signature-container inspection as the delivered604 checker;
# no historical build constants, image counts or producer files are reused.
def thin_image(data):
    if data[:4] in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        wide = data[:4] == b'\xca\xfe\xba\xbf'
        require(struct.unpack_from('>I', data, 4)[0] == 1,
                'A delivery fat image is not mono-ARM64')
        require(struct.unpack_from('>I', data, 8)[0] == 0x0100000c,
                'A delivery fat image is not ARM64')
        offset, size = struct.unpack_from('>QQ' if wide else '>II', data, 16)
        require(offset + size <= len(data), 'Truncated fat image')
        return data[offset:offset + size], True
    return data, False


def signature_structure(data):
    data, fat = thin_image(data)
    image = macho(data)
    require(image['architecture'] == 'arm64' and image['platform'] == 2,
            'Image is not ARM64 iOS')
    require(image['codeSignature'], 'Image has no bounded code signature')
    count = struct.unpack_from('<I', data, 16)[0]
    cursor, signatures = 32, []
    for _ in range(count):
        command, size = struct.unpack_from('<II', data, cursor)
        if command == 0x1d:
            offset, length = struct.unpack_from('<II', data, cursor + 8)
            signatures.append(data[offset:offset + length])
        cursor += size
    require(len(signatures) == 1, 'Unexpected code-signature command count')
    blob = signatures[0]
    require(len(blob) >= 12, 'Truncated embedded signature')
    magic, length, count = struct.unpack_from('>III', blob)
    require(magic == 0xfade0cc0 and 12 <= length <= len(blob) and
            12 + 8 * count <= length, 'Invalid embedded signature superblob')
    slots = []
    for index in range(count):
        slot, offset = struct.unpack_from('>II', blob, 12 + 8 * index)
        require(12 + 8 * count <= offset <= length - 8, 'Invalid signature slot')
        child_magic, child_length = struct.unpack_from('>II', blob, offset)
        require(child_length >= 8 and offset + child_length <= length,
                'Signature child outside superblob')
        slots.append((slot, child_magic))
    require(any(slot == 0 and magic == 0xfade0c02 for slot, magic in slots),
            'Embedded signature has no primary CodeDirectory')
    return image, fat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path)
    parser.add_argument('--receipts', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    args.ipa = args.ipa.resolve()
    args.receipts = args.receipts.resolve()
    args.report = args.report.resolve()
    data = args.ipa.read_bytes()
    digest = sha(data)
    sealed = read_json(args.receipts / 'signed-payload-identity.json')
    require(sealed['ipaSha256'] == digest and sealed['ipaBytes'] == len(data),
            'Downloaded bytes differ from sealed IPA identity')
    require(sealed['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True and
            sealed['abiMetadataUnchangedBySigning'] is True,
            'Sealed receipt lacks compiled-payload preservation')
    require((args.receipts / 'SHA256SUMS').read_text().split()[0] == digest,
            'SHA256SUMS differs from actual IPA')
    environment = read_json(args.receipts / 'environment.json')
    require(environment['commit'] == SOURCE and str(environment['build']) == BUILD,
            'Build environment source or number differs')
    validation = read_json(args.receipts / 'achievement-ipa-validation.json')
    require(validation['result'] == 'passed' and str(validation['build']) == BUILD and
            validation['ipaSHA256'] == digest and validation['ipaBytes'] == len(data),
            'Final Apple CI validation does not describe these bytes')
    identity = validation['identity']
    require(identity['application']['source'] == SOURCE and
            identity['translationTests']['source'] == SOURCE and
            identity['translationTests']['result'] == 'passed' and
            identity['translationTests']['inputsIdenticalToApplication'] is True,
            'Tested translation source differs from the compiled application')
    signing = read_json(args.receipts / 'signature.json')
    require(str(signing['build']) == BUILD and signing['version'] == '0.0.8',
            'Wrong CI signature receipt build/version')
    require(all(row['signatureVerified'] is True and row['signature'] == 'adhoc' and
                row['appleProvisioningVerified'] is False for row in signing['signatures']),
            'Incomplete Apple CI signature verification receipt')
    require(signing['directAppleInstallationReady'] is False and
            signing['deviceInstallationTested'] is False,
            'Unexpected device/provisioning claim')
    structure = validate_structure(args.ipa)
    legal = subprocess.run([sys.executable, str(ROOT / 'build-utils/validate_legal_bundle_ipa.py'),
                            str(args.ipa), '--build-number', BUILD, '--commit', SOURCE],
                           cwd=ROOT, check=True, text=True, capture_output=True)
    require('IPA legal bundle validated.' in legal.stdout,
            'Legal validator did not report success')
    melonx = subprocess.run([sys.executable, str(ROOT / 'build-utils/validate_melonx_ipa.py'),
                             str(args.ipa)], cwd=ROOT, check=True, text=True, capture_output=True)
    require(melonx.returncode == 0, 'MeloNX actual-payload validation failed')
    neoplay = validate_neoplay(args.ipa, BUILD, SOURCE)
    shaders = validate_shaders(args.ipa, BUILD)
    prior = read_json(ROOT / 'docs/evidence/rewind604-delivery.json')
    root = 'Payload/NeoStation.app/'
    with zipfile.ZipFile(args.ipa) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and archive.testzip() is None,
                'Duplicate or damaged ZIP entries')
        require(not any(token in name.lower() for name in names
                        for token in ('mariokartpad', 'dusklight')),
                'Retired component path restored')
        require(json.loads(archive.read(root + 'Achievement-translation-build-identity.json')) == identity,
                'Embedded translation/engine identity differs from final receipt')
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        require(info['CFBundleDisplayName'] == 'RewindBox', 'Wrong application display name')
        require(info['MinimumOSVersion'] in ('18.0', '18.0.0'), 'Wrong minimum iOS')
        bundles = [name for name in names if name == root + 'Info.plist' or
                   (name.startswith(root + 'PlugIns/') and name.endswith('.appex/Info.plist'))]
        require(set(bundles) == set(prior['bundleVersions']), 'Changed application/extension inventory')
        versions, components = {}, set()
        for name in bundles:
            value = plistlib.loads(archive.read(name))
            require(value['CFBundleShortVersionString'] == '0.0.8' and
                    str(value['CFBundleVersion']) == BUILD, 'Bundle version mismatch: ' + name)
            versions[name] = {'version': value['CFBundleShortVersionString'], 'build': BUILD}
        images, fingerprints, fat_images = {}, {}, {}
        for name in names:
            if name.endswith('/'):
                continue
            with archive.open(name) as entry:
                magic = entry.read(4)
            if magic not in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
                continue
            raw = archive.read(name)
            image, fat = signature_structure(raw)
            require(name.startswith(root), 'Mach-O is outside main application')
            relative = name[len(root):]
            images[relative] = {'platform': image['platform'], 'kind': image['fileType'],
                                'exports': len(image['definedSymbols']), 'sha256': sha(raw),
                                'bytes': len(raw), 'signatureStructureValid': True}
            if fat:
                fat_images[relative] = images[relative]
            else:
                fingerprints[relative] = payload_fingerprint(raw)
            parts = Path(relative).parts
            containers = [i for i, part in enumerate(parts) if part.endswith(('.framework', '.appex'))]
            components.add('/'.join(parts[:containers[-1] + 1]) if containers
                           else relative if relative.endswith('.dylib') else '.')
        require(fingerprints == sealed['images'], 'Signed code/data/ABI fingerprints differ')
        require(set(fat_images) == set(prior['fatContainers']), 'Changed fat-container inventory')
        signed_components = [row['bundle'] for row in signing['signatures']]
        require(len(signed_components) == len(set(signed_components)) and
                set(signed_components) == components,
                'CI signature receipt differs from actual executable component inventory')
        plugin = archive.read(root + 'Frameworks/achievement_translation.framework/achievement_translation')
        plugin_image = macho(plugin)
        require(plugin_image['minimumOS'].startswith('18.') and any(
                'Translation.framework' in dependency['path'] for dependency in plugin_image['dependencies']),
                'Plugin minimum iOS or system Translation dependency differs')
        for marker in (b'AchievementTranslationPlugin', b'RBAchievementText', b'RBAchievementToast',
                       b'rewindbox/achievement_translation', b'RBAchievementPresent'):
            require(marker in plugin, 'Missing compiled translation implementation: ' + repr(marker))
        consumer_floors = {}
        for consumer in ('armsx2_internal_bridge', 'dolphin_internal_bridge', 'libretro_internal_bridge'):
            consumer_image = macho(archive.read(root + f'Frameworks/{consumer}.framework/{consumer}'))
            consumer_floors[consumer] = consumer_image['minimumOS']
            require(consumer_image['minimumOS'].startswith('18.'),
                    'Native translation consumer targets an older iOS: ' + consumer)
        dolphin = archive.read(root + 'Frameworks/DolphinCore.framework/DolphinCore')
        require(payload_fingerprint(dolphin) == identity['dolphin']['payloadFingerprint'],
                'Dolphin differs from the newly compiled producer')
        require('_neostation_dolphin_set_achievement_presenter' in macho(dolphin)['definedSymbols'],
                'Dolphin achievement presenter is missing')
        source_record = json.loads(archive.read(root + 'Legal/RPCS3-current-core/actual-compiled-source.json'))
        source_zip = archive.read(root + 'Legal/RPCS3-current-core/compiled-host-inputs.zip')
        require(source_record['compiledInputsZipSHA256'] == sha(source_zip), 'RPCS3 source ZIP differs')
        with zipfile.ZipFile(io.BytesIO(source_zip)) as sources:
            require({n: sha(sources.read(n)) for n in sources.namelist()} == source_record['inputs'],
                    'Actual RPCS3 source members differ from their receipt')
    report = dict(result='passed', build=int(BUILD), source=SOURCE, ipaName=args.ipa.name,
        ipaSHA256=digest, ipaBytes=len(data), zipEntries=len(names), zipCrcVerified=True,
        bundleVersions=versions, displayName=info['CFBundleDisplayName'], minimumIOS=info['MinimumOSVersion'],
        machOImages=len(images), thinPayloadFingerprintsVerified=len(fingerprints), fatContainers=fat_images,
        signatureStructuresVerified=len(images), signaturesVerifiedByAppleCI=len(signed_components),
        signatureCryptographicallyVerifiedIndependently=False,
        structuralValidation=structure['structuralValidation'], legalBundleValidation='passed',
        retiredComponentPathsAbsent=True, relocatedDependenciesVerified=len(structure['resolvedDependencies']),
        actualTranslationPluginPresent=True, systemTranslationLinked=True,
        nativeConsumerMinimumIOS=consumer_floors,
        newDolphinPayloadMatched=True, rpcCompiledSourceMembersVerified=True,
        melonxActualPayloadValidation='passed', retainedNeoPlay=neoplay, shaderCompilerIsolation=shaders,
        sideStoreAppleReSigningRequired=True, physicalDeviceTested=False,
        scriptSHA256=sha(Path(__file__).read_bytes()), verifiedUTC=datetime.now(timezone.utc).isoformat())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in (
        'result', 'ipaName', 'ipaSHA256', 'ipaBytes', 'zipEntries', 'machOImages',
        'thinPayloadFingerprintsVerified', 'signatureStructuresVerified',
        'signatureCryptographicallyVerifiedIndependently', 'physicalDeviceTested')}, indent=2))


if __name__ == '__main__':
    main()
