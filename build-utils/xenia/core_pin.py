#!/usr/bin/env python3
"""Pins a built XeniaCore.framework, and verifies an artifact against the pin.

The pin (build-utils/xenia/core-pin.json) follows build-utils/melonx/dma-core-pin.json:
the workflow run, job and artifact that built it, the artifact's SHA-256 (the
zip GitHub stores), the binary's SHA-256 and size, and its packaged
fingerprint (build-utils/delivery_benchmark.payload_fingerprint: Mach-O
sections and ABI metadata, independent of the code signature, so the
delivery's re-signing keeps it). The converter (libmetalirconverter.dylib) is
never in the artifact: it is pinned by build-utils/xenia/source.json.

  core_pin.py pin <artifact.zip> --run R --job J --attempt N --artifact ID --name NAME
                  --expires ISO8601 [--replaces-reason TEXT]
                  [--converter-signature <codesign -dvvv output saved from the run's log>]
                  writes core-pin.json
  core_pin.py verify <artifact.zip | extracted dir> [--pin core-pin.json]
                  exits 0 only when the artifact is the pinned one (the delivery calls this)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / 'build-utils' / 'xenia' / 'core-pin.json'
SOURCE = ROOT / 'build-utils' / 'xenia' / 'source.json'
WORKFLOW = '.github/workflows/xenia-core.yml'
BINARY = 'XeniaCore.framework/XeniaCore'
REPORT = 'XeniaCore.json'
RESOURCES = ('XeniaCore.framework/Info.plist', 'XeniaCore.framework/LICENSE.txt',
             'XeniaCore.framework/Acknowledgements.json')
sys.path.insert(0, str(ROOT / 'build-utils'))
sys.path.insert(0, str(ROOT / 'build-utils' / 'xenia'))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(binary: bytes) -> str:
    from delivery_benchmark import payload_fingerprint
    return payload_fingerprint(binary)


def read_artifact(location: Path) -> tuple[dict[str, bytes], str | None]:
    """Files of the artifact by relative path, and the zip's digest when given one."""
    if location.is_dir():
        return ({str(PurePosixPath(*path.relative_to(location).parts)): path.read_bytes()
                 for path in location.rglob('*') if path.is_file() and not path.is_symlink()}, None)
    data = location.read_bytes()
    files = {}
    with zipfile.ZipFile(location) as archive:
        for info in archive.infolist():
            name = PurePosixPath(info.filename)
            if info.is_dir():
                continue
            if name.is_absolute() or '..' in name.parts:
                raise SystemExit(f'Unsafe path in the artifact: {info.filename}')
            files[str(name)] = archive.read(info)
    return files, sha256(data)


def facts(files: dict[str, bytes]) -> dict:
    """Checks the framework itself (as verify_core.py does on the build host)."""
    import validate_shader_converter as macho
    failures = []
    for required in (BINARY, REPORT, *RESOURCES):
        if required not in files:
            failures.append(f'{required} missing from the artifact')
    if failures:
        raise SystemExit('XeniaCore artifact refused:\n- ' + '\n- '.join(failures))
    if any('libmetalirconverter' in name for name in files):
        raise SystemExit('XeniaCore artifact refused: it carries the shader converter')
    binary = files[BINARY]
    report = json.loads(files[REPORT])
    parsed = macho.parse(binary)
    if parsed['cpu'] != 'arm64' or parsed['platform'] != 'IOS' or parsed['minos'] != '26.0.0':
        failures.append(f"not an arm64 iPhoneOS 26.0 image: {parsed['cpu']} {parsed['platform']} {parsed['minos']}")
    if parsed['install_name'] != '@rpath/XeniaCore.framework/XeniaCore':
        failures.append(f"install name {parsed['install_name']}")
    if '@rpath/libmetalirconverter.dylib' not in parsed['dependencies']:
        failures.append('libmetalirconverter.dylib is not a dependency')
    if sorted(set(parsed['exports'])) != ['_NeoXenia_GetAPI']:
        failures.append('exports are not exactly _NeoXenia_GetAPI')
    if report.get('sha256') != sha256(binary) or report.get('bytes') != len(binary):
        failures.append('XeniaCore.json does not describe this binary')
    revision = json.loads(SOURCE.read_text())['revision']
    if report.get('source') != revision:
        failures.append(f"built from {report.get('source')}, pinned source is {revision}")
    if failures:
        raise SystemExit('XeniaCore artifact refused:\n- ' + '\n- '.join(failures))
    return {'binary': binary, 'report': report, 'revision': revision}


def converter_signature(text: str) -> dict:
    """What codesign itself reported in CI on the converter (build_core.sh logs codesign -dvvv,
    then requires '=anchor apple' and the pinned identity; the build stops if either fails)."""
    fields = {}
    authorities = []
    for line in text.splitlines():
        key, sep, value = line.strip().partition('=')
        if not sep:
            continue
        if key == 'Authority':
            authorities.append(value)
        elif key in ('Identifier', 'TeamIdentifier', 'Format', 'Signed Time', 'Timestamp'):
            fields[key] = value
    expected = ['Software Signing', 'Apple Code Signing Certification Authority', 'Apple Root CA']
    if (fields.get('Identifier') != 'libmetalirconverter' or authorities != expected or
            fields.get('TeamIdentifier', 'not set') != 'not set'):
        raise SystemExit('converter signature report: not the pinned Apple identity: '
                         f"{fields.get('Identifier')} {authorities} team {fields.get('TeamIdentifier')}")
    return {'reported_by': 'codesign -dvvv in the build run (build_core.sh)',
            'identifier': fields['Identifier'], 'team_identifier': fields.get('TeamIdentifier'),
            'authorities': authorities, 'leaf_cn': authorities[0],
            'requirements_satisfied': ["=anchor apple",
                                       '=identifier "libmetalirconverter" and anchor apple and '
                                       'certificate leaf[subject.CN] = "Software Signing"']}


def pin(arguments) -> int:
    files, digest = read_artifact(Path(arguments.artifact_zip))
    if digest is None:
        raise SystemExit('pin needs the downloaded artifact zip (its digest is pinned)')
    checked = facts(files)
    binary = checked['binary']
    previous = json.loads(PIN.read_text()) if PIN.is_file() else None
    record = {
        'status': 'verified',
        'source': checked['revision'],
        'run': arguments.run,
        'job': arguments.job,
        'attempt': arguments.attempt,
        'workflow': WORKFLOW,
        'artifact': arguments.artifact,
        'name': arguments.name,
        'bytes': Path(arguments.artifact_zip).stat().st_size,
        'sha256': digest,
        'expiresAt': arguments.expires,
        'image': 'Frameworks/XeniaCore.framework/XeniaCore',
        'binaries': {'ios-arm64': {'sha256': sha256(binary), 'bytes': len(binary)}},
        'packagedFingerprint': fingerprint(binary),
        'minimumOS': checked['report'].get('minos'),
        'sdk': checked['report'].get('sdk'),
        'dependencies': checked['report'].get('dependencies'),
        'shaderConverter': json.loads(SOURCE.read_text())['shader_converter']['upstream_mirror'],
        'sdkNote': ('Built with an iOS 26 SDK unless sdk says 27: StateReporting and the external-display scene '
                    'accessory are then compiled out, absent on iOS 27 devices too (docs/xenios-playlist.md).'),
    }
    if arguments.converter_signature:
        record['shaderConverterSignature'] = converter_signature(Path(arguments.converter_signature).read_text())
    if previous and previous.get('run') != arguments.run:
        record['replaces'] = {key: previous.get(key) for key in ('source', 'run', 'artifact', 'packagedFingerprint')}
        record['replaces']['reason'] = arguments.replaces_reason or ''
    PIN.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    return 0


def verify(arguments) -> int:
    record = json.loads(Path(arguments.pin).read_text())
    files, digest = read_artifact(Path(arguments.artifact))
    checked = facts(files)
    binary = checked['binary']
    failures = []
    if record.get('status') != 'verified' or record.get('workflow') != WORKFLOW:
        failures.append('the pin is not a verified xenia-core.yml build')
    if digest is not None and digest != record.get('sha256'):
        failures.append(f"artifact digest {digest} is not the pinned {record.get('sha256')}")
    expected = record.get('binaries', {}).get('ios-arm64', {})
    if expected != {'sha256': sha256(binary), 'bytes': len(binary)}:
        failures.append('the binary is not the pinned one')
    if record.get('packagedFingerprint') != fingerprint(binary):
        failures.append('the packaged fingerprint differs from the pin')
    if record.get('source') != checked['revision']:
        failures.append('the pin names another XeniOS revision than source.json')
    if failures:
        print('XeniaCore pin: REFUSED\n- ' + '\n- '.join(failures))
        return 1
    print(f"XeniaCore pin: OK (run {record['run']}, artifact {record['artifact']}, "
          f"binary {expected['sha256'][:12]}, fingerprint {record['packagedFingerprint'][:12]})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pin')
    p.add_argument('artifact_zip')
    for name in ('run', 'job', 'attempt', 'artifact'):
        p.add_argument('--' + name, type=int, required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--expires', required=True)
    p.add_argument('--replaces-reason')
    p.add_argument('--converter-signature')
    v = sub.add_parser('verify')
    v.add_argument('artifact')
    v.add_argument('--pin', default=str(PIN))
    arguments = parser.parse_args(argv)
    return pin(arguments) if arguments.command == 'pin' else verify(arguments)


if __name__ == '__main__':
    sys.exit(main())
