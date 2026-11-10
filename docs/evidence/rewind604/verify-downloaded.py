#!/usr/bin/env python3
"""Check actual downloaded IPA604 bytes against sealed receipts and producer ZIPs.

This is an offline integrity and structure check, not an iOS launch or Apple
certificate/provisioning verification. No compiler or native fixture is run.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import zipfile

WORK = Path('/workspace/scratch/17fcc7f76cc4')
ROOT = WORK / 'RewindBox'
SOURCE = '60add3d79b3e4d9d76b68ef154cb5d3f8772c323'
sys.path[:0] = [str(ROOT / 'build-utils'),
                str(ROOT / 'packages/dolphin_internal_bridge/ci'),
                str(ROOT / '.github/diagnostics')]
from verify_ipa import validate as validate_structure, macho
from delivery_benchmark import payload_fingerprint
from validate_rpcs3_core604_ipa import compare_core
from rewind604_engine import normalized_payload_fingerprint


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


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


def producer_core(path, archive_hash, member, core_hash):
    data = path.read_bytes()
    require(sha(data) == archive_hash, 'Original producer archive changed: ' + path.name)
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, 'Original producer CRC failure')
        raw = archive.read(member)
    require(sha(raw) == core_hash, 'Original producer core changed')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path)
    parser.add_argument('--receipts', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
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
    require(environment['commit'] == SOURCE and str(environment['build']) == '604',
            'Build environment source or number differs')
    signing = read_json(args.receipts / 'signature.json')
    require(str(signing['build']) == '604' and signing['version'] == '0.0.8',
            'Wrong CI signature receipt build/version')
    require(len(signing['signatures']) == 88 and all(
        row['signatureVerified'] is True and row['signature'] == 'adhoc' and
        row['appleProvisioningVerified'] is False for row in signing['signatures']),
        'Incomplete Apple CI signature verification receipt')
    require(signing['directAppleInstallationReady'] is False and
            signing['deviceInstallationTested'] is False,
            'Unexpected device/provisioning claim')
    structure = validate_structure(args.ipa)
    legal = subprocess.run([sys.executable, str(ROOT / 'build-utils/validate_legal_bundle_ipa.py'),
                            str(args.ipa), '--build-number', '604', '--commit', SOURCE],
                           cwd=ROOT, check=True, text=True, capture_output=True)
    require('IPA legal bundle validated.' in legal.stdout,
            'Legal validator did not report success')
    prior = read_json(ROOT / 'docs/evidence/rewind603-delivery.json')
    root = 'Payload/NeoStation.app/'
    with zipfile.ZipFile(args.ipa) as archive:
        names = archive.namelist()
        retired = [name for name in names if any(token in name.lower()
                   for token in ('mariokartpad', 'dusklight'))]
        require(not retired, 'Retired MarioKartPad/Dusklight component path restored')
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        require(info['CFBundleDisplayName'] == 'RewindBox', 'Wrong application display name')
        require(info['MinimumOSVersion'] in ('18.0', '18.0.0'), 'Wrong minimum iOS')
        bundles = [name for name in names if name == root + 'Info.plist' or
                   (name.startswith(root + 'PlugIns/') and name.endswith('.appex/Info.plist'))]
        require(set(bundles) == set(prior['bundleVersions']), 'Changed application/extension inventory')
        versions = {}
        for name in bundles:
            value = plistlib.loads(archive.read(name))
            require(value['CFBundleShortVersionString'] == '0.0.8' and
                    str(value['CFBundleVersion']) == '604', 'Bundle version mismatch: ' + name)
            versions[name] = {'version': value['CFBundleShortVersionString'],
                              'build': str(value['CFBundleVersion'])}
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
                                'exports': len(image['definedSymbols']),
                                'sha256': sha(raw), 'bytes': len(raw),
                                'signatureStructureValid': True}
            if fat:
                fat_images[relative] = images[relative]
            else:
                fingerprints[relative] = payload_fingerprint(raw)
        require(len(images) == 88 and len(fingerprints) == 85 and len(fat_images) == 3,
                'Unexpected actual Mach-O inventory')
        require(fingerprints == sealed['images'], 'Signed code/data/ABI fingerprints differ')
        require(set(fat_images) == set(prior['fatContainers']), 'Changed fat-container inventory')
        melonx_raw = producer_core(
            WORK / 'MeloNX-runtime-510e683.zip',
            'ed70ba31b1b52fc0fbd55e695b25cc4254d5f90c4f86b930d8bf2958235ac278',
            'ios-arm64/Ryujinx.Library.dylib',
            '7620fa3009e6df971665e7b8adec1a0bac654e6efa4bc3fceb292daefa6adb55')
        melonx = archive.read(root + 'Frameworks/MeloNXCore.framework/MeloNXCore')
        require(normalized_payload_fingerprint(melonx) ==
                normalized_payload_fingerprint(melonx_raw) ==
                '85cc56d985e6f0a2dcce559dfd099d9f4dd574e61cfb0066c9e715a5bbbf5c7a',
                'Actual MeloNX differs from authenticated newly compiled Core')
        rpcs3_raw = producer_core(
            WORK / 'rpcs3-604-staging/core.zip',
            'b260bb4fa48b72ff889d6e9c4eb061591676b18e12427c0160a44974c9ff2b07',
            'libRPCS3Core.dylib',
            'f2f167af5cfa7889e76af150b6c9f02e6a19b7f3e881de0397bcafe185dbe19a')
        rpcs3 = compare_core(archive.read(root + 'Frameworks/libRPCS3Core.dylib'),
                             rpcs3_raw, signed=True)
    report = dict(result='passed', build=604, source=SOURCE,
        ipaName=args.ipa.name, ipaSHA256=digest, ipaBytes=len(data), zipEntries=len(names),
        zipCrcVerified=True, bundleVersions=versions, displayName=info['CFBundleDisplayName'],
        minimumIOS=info['MinimumOSVersion'], machOImages=len(images),
        thinPayloadFingerprintsVerified=len(fingerprints), fatContainers=fat_images,
        signatureStructuresVerified=len(images), signaturesVerifiedByAppleCI=len(signing['signatures']),
        signatureCryptographicallyVerifiedIndependently=False,
        structuralValidation=structure['structuralValidation'],
        legalBundleValidation='passed', retiredComponentPathsAbsent=True,
        relocatedDependenciesVerified=len(structure['resolvedDependencies']),
        melonxOriginalPayloadMatched=True, rpcs3=rpcs3,
        sideStoreAppleReSigningRequired=True, physicalDeviceTested=False,
        scriptSHA256=sha(Path(__file__).read_bytes()),
        verifiedUTC=datetime.now(timezone.utc).isoformat())
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in (
        'result', 'ipaName', 'ipaSHA256', 'ipaBytes', 'zipEntries', 'machOImages',
        'thinPayloadFingerprintsVerified', 'signatureStructuresVerified',
        'signatureCryptographicallyVerifiedIndependently', 'physicalDeviceTested')}, indent=2))


if __name__ == '__main__':
    main()
