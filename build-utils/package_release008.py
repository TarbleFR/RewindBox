#!/usr/bin/env python3
"""Give the verified Build 480 its public 0.0.8 version without recompiling."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import subprocess
import tempfile
import zipfile

from delivery_benchmark import payload_fingerprint
from sign_delivery import sign

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '7493d9babe20be1b2939e21a1051a72da8fb5d01'
INPUT_HASH = 'a87c355491083f8e4c385f5c119f9a8e41ecd1738439747cd20dd38bdb2ba8f1'
RELEASE = '0.0.8'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def image_identity(data):
    if data[:4] == b'\xcf\xfa\xed\xfe':
        return payload_fingerprint(data)
    if data[:4] == b'\xca\xfe\xba\xbe':
        count = struct.unpack_from('>I', data, 4)[0]
        images = []
        for i in range(count):
            cpu, subtype, offset, size, _ = struct.unpack_from('>IIIII', data, 8 + i * 20)
            images.append([cpu, subtype, payload_fingerprint(data[offset:offset + size])])
        return images
    return None


def snapshot(app):
    records = {}
    for path in app.rglob('*'):
        if path.is_file():
            data = path.read_bytes()
            image = image_identity(data)
            records[path.relative_to(app).as_posix()] = (
                ['macho', image] if image is not None else ['file', digest(data)])
    return records


def compare(before, after, plists):
    changed = []
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        if before.get(name, [''])[0] == 'macho' or after.get(name, [''])[0] == 'macho':
            raise ValueError('Compiled payload changed: ' + name)
        if not (name in plists or '/_CodeSignature/' in '/' + name
                or name == 'Release-0.0.8-identity.json'):
            raise ValueError('Unexpected resource change: ' + name)
        changed.append(name)
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('ipa', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.ipa.stat().st_size != 226569533 or digest(args.ipa.read_bytes()) != INPUT_HASH:
        raise ValueError('Input is not the exact verified Build 480')
    if 'version: 0.0.8+480' not in (ROOT / 'pubspec.yaml').read_text():
        raise ValueError('Canonical release version mismatch')
    packaging = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = dict(release=RELEASE, build='480', original_source_commit=SOURCE,
                    original_ipa_sha256=INPUT_HASH, packaging_commit=packaging,
                    recompiled=False, new_device_tests_performed=False,
                    changes=['marketing version', 'ad hoc signatures'])
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        subprocess.run(['ditto', '-xk', str(args.ipa.resolve()), str(stage)], check=True)
        apps = list((stage / 'Payload').glob('*.app'))
        if len(apps) != 1:
            raise ValueError('Expected exactly one app')
        app = apps[0]
        before = snapshot(app)
        original = json.loads((app / 'Legal/BUILD_SOURCE_IDENTITY.json').read_text())
        if original['host_commit'] != SOURCE or original['build_number'] != '480':
            raise ValueError('Compiled source identity mismatch')
        paths = [app / 'Info.plist', *app.glob('PlugIns/*.appex/Info.plist')]
        if len(paths) != 6:
            raise ValueError('Expected the host and five existing extensions')
        plists = {p.relative_to(app).as_posix() for p in paths}
        for path in paths:
            info = plistlib.loads(path.read_bytes())
            if info['CFBundleVersion'] != '480' or info['CFBundleShortVersionString'] != '0.0.7':
                raise ValueError('Unexpected input bundle version: ' + str(path))
            info['CFBundleShortVersionString'] = RELEASE
            path.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
        (app / 'Release-0.0.8-identity.json').write_text(json.dumps(identity, indent=2) + '\n')
        sign(app, output / 'NeoStation-0.0.8-Signatures.json')
        after = snapshot(app)
        modified = compare(before, after, plists)
        images = {n: value[1] for n, value in before.items() if value[0] == 'macho'}
        if len(images) != 80:
            raise ValueError('Expected 77 thin and three universal compiled images')
        ipa = output / 'NeoStation-0.0.8.ipa'
        subprocess.run(['/usr/bin/zip', '-qry', str(ipa), 'Payload'], cwd=stage, check=True)
        subprocess.run(['unzip', '-tq', str(ipa)], check=True)
        with tempfile.TemporaryDirectory() as final:
            subprocess.run(['ditto', '-xk', str(ipa), final], check=True)
            final_app = Path(final) / 'Payload' / app.name
            if snapshot(final_app) != after:
                raise ValueError('Final archive differs from the signed staging bundle')
            subprocess.run(['codesign', '--verify', '--deep', '--strict', '--verbose=2',
                            str(final_app)], check=True)
        subprocess.run(['python3', str(ROOT / 'build-utils/validate_legal_bundle_ipa.py'),
                        str(ipa), '--build-number', '480', '--commit', SOURCE], check=True)
        subprocess.run(['python3', str(ROOT / 'build-utils/validate_single_ipa_distribution.py'),
                        str(ipa), '--report', str(output / 'NeoStation-0.0.8-Distribution.json')], check=True)
        report = dict(identity, sha256=digest(ipa.read_bytes()), size_bytes=ipa.stat().st_size,
                      all_compiled_code_and_data_unchanged=True, compiled_images=len(images),
                      images=images, changed_resources=modified, zip_integrity='passed',
                      signatures='verified ad hoc', sideStoreAppleReSigningRequired=True)
        (output / 'NeoStation-0.0.8-Packaging.json').write_text(json.dumps(report, indent=2) + '\n')
        with zipfile.ZipFile(output / 'NeoStation-0.0.8-Licenses-and-Notices.zip', 'w',
                             zipfile.ZIP_DEFLATED) as archive:
            for directory in ['Legal', 'Libretro-Licenses', 'Dusklight-Licenses']:
                for path in (app / directory).rglob('*'):
                    if path.is_file():
                        archive.write(path, path.relative_to(app))
            archive.write(app / 'Release-0.0.8-identity.json', 'Release-0.0.8-identity.json')
            for relative in ['docs/CHEAT_CATALOG_SOURCES.md', 'docs/OVERLAY_SOURCES_AND_CREDITS.md',
                             'docs/EMBEDDED_RUNTIME_PROVENANCE.md', 'docs/RELEASE_0.0.8_SOURCE_MANIFEST.md']:
                archive.write(ROOT / relative, relative)
        (output / 'NeoStation-0.0.8-Source-Manifest.md').write_bytes(
            (ROOT / 'docs/RELEASE_0.0.8_SOURCE_MANIFEST.md').read_bytes())
    checksums = ''.join(digest(p.read_bytes()) + '  ' + p.name + '\n'
                        for p in sorted(output.iterdir()) if p.is_file())
    (output / 'NeoStation-0.0.8-SHA256SUMS.txt').write_text(checksums)
    print(json.dumps({k: report[k] for k in ['release', 'build', 'sha256', 'size_bytes',
                                          'compiled_images', 'all_compiled_code_and_data_unchanged']}))


if __name__ == '__main__':
    main()
