#!/usr/bin/env python3
"""Bind the exact BO2 runtime source candidate to private IPA 594.

Signature changes are confined to the existing strict Mach-O comparison.
The generic structural validator is reused with an explicit identity callback;
its other validations and the historical delivery files remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3runtime594_delivery_core as candidate

RECEIPT = 'RPCS3-runtime-core-identity.json'
CORE = 'Frameworks/libRPCS3Core.dylib'
INSTALL_NAME = candidate.CORE_ID


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _require_metadata(value, message):
    if not value:
        raise ValueError(message)


def _signature_image(data):
    _require_metadata(len(data) >= 32 and data[:4] == b'\xcf\xfa\xed\xfe', 'Expected thin Mach-O64')
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from('<8I', data)
    _require_metadata(cpu == 0x0100000c and kind == 6, 'Expected an ARM64 dylib')
    _require_metadata(count <= 65536 and 32 + size <= len(data), 'Truncated Mach-O commands')
    cursor, end = 32, 32 + size
    commands, segments, sections, signatures, ids = [], [], [], [], []
    linkedit = None
    for _ in range(count):
        _require_metadata(cursor + 8 <= end, 'Truncated Mach-O load command')
        command, length = struct.unpack_from('<II', data, cursor)
        _require_metadata(length >= 8 and length % 8 == 0 and cursor + length <= end, 'Invalid load-command size')
        record = bytearray(data[cursor:cursor + length])
        if command == 0x1d:
            _require_metadata(length == 16, 'Unexpected signature command')
            signatures.append(struct.unpack_from('<II', record, 8))
        else:
            if command == 0x19:
                _require_metadata(length >= 72, 'Truncated segment command')
                name = bytes(record[8:24]).split(b'\0', 1)[0]
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', record, 24)
                nsects = struct.unpack_from('<I', record, 64)[0]
                _require_metadata(length == 72 + 80 * nsects, 'Invalid segment sections')
                _require_metadata(fileoff + filesize <= len(data), 'Segment outside file')
                segments.append((name, fileoff, filesize))
                for index in range(nsects):
                    position = 72 + 80 * index
                    section_size = struct.unpack_from('<Q', record, position + 40)[0]
                    section_off = struct.unpack_from('<I', record, position + 48)[0]
                    if section_off and section_size:
                        _require_metadata(section_off + section_size <= len(data), 'Section outside file')
                        sections.append((section_off, section_size))
                if name == b'__LINKEDIT':
                    _require_metadata(linkedit is None and nsects == 0, 'Unexpected LINKEDIT layout')
                    _require_metadata(fileoff % 16 == 0 and fileoff >= end, 'Unexpected LINKEDIT offset')
                    _require_metadata(fileoff + filesize == len(data), 'LINKEDIT must end at EOF')
                    _require_metadata(vmsize >= filesize, 'LINKEDIT VM size too small')
                    linkedit = (fileoff, filesize, vmsize)
                    # codesign can resize this final file-backed segment. Every
                    # other bit of the segment and every other command is sealed.
                    struct.pack_into('<Q', record, 32, 0)  # vmsize
                    struct.pack_into('<Q', record, 48, 0)  # filesize
            elif command == 0xd:
                _require_metadata(length >= 24, 'Truncated dylib identity')
                string_off = struct.unpack_from('<I', record, 8)[0]
                _require_metadata(24 <= string_off < length, 'Invalid dylib identity offset')
                tail = bytes(record[string_off:])
                _require_metadata(b'\0' in tail, 'Unterminated dylib identity')
                ids.append(tail.split(b'\0', 1)[0].decode())
            commands.append(bytes(record))
        cursor += length
    _require_metadata(cursor == end and linkedit is not None, 'Incomplete Mach-O layout')
    _require_metadata(ids == [INSTALL_NAME], 'Changed LC_ID_DYLIB')
    _require_metadata(len(signatures) <= 1, 'Multiple code signatures')
    fileoff, filesize, vmsize = linkedit
    for name, offset, length in segments:
        if name != b'__LINKEDIT' and length:
            _require_metadata(offset + length <= fileoff, 'Segment overlaps LINKEDIT')
    body_end, signed = len(data), False
    if signatures:
        signature_off, signature_size = signatures[0]
        if signature_size:
            _require_metadata(signature_size >= 12 and signature_off % 16 == 0, 'Invalid signature layout')
            _require_metadata(fileoff <= signature_off and signature_off + signature_size == len(data), 'Signature must end LINKEDIT')
            _require_metadata(all(offset + length <= signature_off for offset, length in sections), 'Signature overlaps a section')
            body_end, signed = signature_off, True
        else:
            _require_metadata(signature_off in (0, len(data)), 'Unexpected empty signature')
    header = struct.pack('<8I', magic, cpu, subtype, kind, len(commands), sum(map(len, commands)), flags, reserved)
    body = data[fileoff:body_end]
    # Signing can append up to 15 zero bytes before the aligned signature. This
    # never discards a nonzero payload byte or a complete extra block of zeros.
    aligned_body = body + b'\0' * (-len(body) % 16)
    return dict(commands=header + b''.join(commands), linkeditBody=aligned_body,
                linkeditBytes=len(body), filesize=filesize, vmsize=vmsize, signed=signed)


def compare_signature_metadata(raw, signed):
    before, after = _signature_image(raw), _signature_image(signed)
    _require_metadata(after['signed'], 'Packaged Core has no signature payload')
    _require_metadata(before['commands'] == after['commands'], 'Non-signature load command changed')
    _require_metadata(abs(before['linkeditBytes'] - after['linkeditBytes']) <= 15, 'Unexpected LINKEDIT payload length change')
    _require_metadata(before['linkeditBody'] == after['linkeditBody'], 'Non-signature LINKEDIT payload changed')
    if before['vmsize'] != after['vmsize']:
        rounded = {
            (((before['filesize'] + page - 1) // page) * page,
             ((after['filesize'] + page - 1) // page) * page)
            for page in (4096, 16384)
        }
        _require_metadata((before['vmsize'], after['vmsize']) in rounded, 'Unexpected LINKEDIT VM resizing')
    return dict(nonSignatureLoadCommandsSHA256=hashlib.sha256(before['commands']).hexdigest(),
                nonSignatureLinkeditSHA256=hashlib.sha256(before['linkeditBody']).hexdigest(),
                nonSignatureLoadCommandsUnchanged=True, nonSignatureLinkeditUnchanged=True,
                alignmentPaddingDifference=after['linkeditBytes'] - before['linkeditBytes'])


def raw_core(path=None):
    raw = candidate.raw_core()
    if path:
        candidate.require(Path(path).read_bytes() == raw, 'Supplied Core differs from authenticated raw artifact')
    return raw


def delivery_build(build):
    value = int(build)
    candidate.require(value == 594, 'This verified Core delivery contract is fixed to private IPA 594')
    return value


def expected(identity, build):
    build = delivery_build(build)
    candidate.validate_rpc_core_identity(identity)
    record = candidate.core_receipt()
    return dict(build=build, baseline=candidate.DELIVERY_BASELINE, type=record['type'],
                coreSource=record['coreSource'], coreNativeSource=record['coreNativeSource'],
                coreRun=record['coreRun'], coreArtifact=record['artifact'],
                diagnosticsArtifact=record['diagnosticsArtifact'], coreSHA256=record['coreSHA256'],
                corePayloadFingerprint=record['corePayloadFingerprint'],
                identitySHA256=record['identitySHA256'], proofSHA256=record['proofSHA256'],
                hostCommit=identity['host_commit'], abiVersion=identity['abi_version'],
                sourcePatchSHA256=identity['source_patch_sha256'], codegen=record['codegen'],
                changedPaths=record['changedPaths'], canonicalPostimages=record['canonicalPostimages'],
                supplementalNativeSources=record['supplementalNativeSources'],
                tests=record['tests'], installName=candidate.CORE_ID,
                compatibility=record['compatibility'], sourceReceipt=record['sourceReceipt'],
                historicalTestsReplayed=False, candidateTestsReplayed=False,
                physicalDeviceTested=False, gameplayMeasured=False, fpsGainMeasured=False)


def compare_core(packaged, raw, signed):
    """Preserve code/data, exports, dependencies, install name and non-signature metadata."""
    before, after = candidate.macho(raw), candidate.macho(packaged)
    candidate.require(before['id'] == after['id'] == candidate.CORE_ID,
                      'RPCS3 install name changed during packaging')
    candidate.require(after['platform'] == before['platform'] == 2 and
                      after['fileType'] == before['fileType'] == 6 and
                      after['definedSymbols'] == before['definedSymbols'] and
                      len(after['definedSymbols']) == 88, 'RPCS3 platform/type/exports changed')
    if signed:
        candidate.require(after['codeSignature'] is True, 'Packaged Core has no signature payload')
    fingerprint = candidate.payload_fingerprint(packaged)
    candidate.require(fingerprint == candidate.payload_fingerprint(raw),
                      'Signing/packaging changed Core code, data or ABI metadata')
    metadata = compare_signature_metadata(raw, packaged) if signed or packaged != raw else {}
    for marker in candidate.CORE_MARKERS:
        candidate.require(marker in packaged, 'Core runtime marker missing: ' + repr(marker))
    return dict(compiledPayloadFingerprint=fingerprint, installName=after['id'],
                signed=after['codeSignature'], definedSymbols=len(after['definedSymbols']), metadata=metadata)


def _identity(identity_path):
    data = Path(identity_path).read_bytes()
    candidate.require(sha(data) == candidate.configuration()['identitySHA256'],
                      'Core artifact identity bytes changed')
    identity = json.loads(data)
    candidate.validate_rpc_core_identity(identity)
    return identity


def embed(app, build, identity_path, raw_path=None):
    app = Path(app)
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    candidate.require(str(info['CFBundleVersion']) == str(delivery_build(build)),
                      'Application build differs from the explicit delivery number')
    receipt = expected(_identity(identity_path), build)
    state = compare_core((app / CORE).read_bytes(), raw_core(raw_path), signed=False)
    (app / RECEIPT).write_text(json.dumps(receipt, indent=2) + '\n')
    return dict(receipt=receipt, core=state)


def validate(ipa, build, identity_path, raw_path=None):
    build = delivery_build(build)
    receipt = expected(_identity(identity_path), build)
    raw = raw_core(raw_path)
    with zipfile.ZipFile(ipa) as archive:
        names = archive.namelist()
        candidate.require(len(names) == len(set(names)), 'Duplicate IPA entries')
        roots = [name[:-10] for name in names if name.startswith('Payload/') and
                 len(name.split('/')) == 3 and name.endswith('.app/Info.plist')]
        candidate.require(len(roots) == 1, 'Expected one IPA application root')
        root = roots[0]
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        candidate.require(str(info['CFBundleVersion']) == str(build), 'IPA build number mismatch')
        candidate.require(json.loads(archive.read(root + RECEIPT)) == receipt,
                          'Packaged runtime source-candidate receipt changed')
        packaged = archive.read(root + CORE)
        state = compare_core(packaged, raw, signed=True)
    return dict(result='passed', build=build, ipaSHA256=sha(Path(ipa).read_bytes()),
                receipt=receipt, rawCoreSHA256=sha(raw), signedCoreSHA256=sha(packaged), core=state,
                physicalDeviceTested=False, gameplayMeasured=False,
                scope='Authenticated runtime source candidate; compiled payload, ABI, non-signature load commands and LINKEDIT preserved. Full codesign, entitlements and other component checks belong to the delivery.')


def validate_structure(ipa, build, commit, identity_path, core_host_commit, core_run_id):
    """Keep the existing IPA checks; adapt only the new immutable identity schema."""
    import validate_rpcs3_ipa as structural
    build = delivery_build(build)
    candidate.require(core_host_commit == candidate.CORE_SOURCE and str(core_run_id) == str(candidate.CORE_RUN),
                      'Structural validator received a different Core source/run')
    previous = structural.validate_core_identity
    structural.validate_core_identity = candidate.validate_core_identity
    try:
        result = structural.validate_ipa(Path(ipa), str(build), commit, Path(identity_path),
                                         core_host_commit, str(core_run_id))
    finally:
        structural.validate_core_identity = previous
    result['rpcS3CoreSourceType'] = candidate.CORE_TYPE
    result['rpcS3CoreCompatibility'] = candidate.compatibility()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', nargs='?', type=Path)
    parser.add_argument('--ipa', dest='ipa_option', type=Path)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--embed', type=Path)
    operation.add_argument('--structure', action='store_true')
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path, default=ROOT / 'dist/rpcs3-native/identity.json')
    parser.add_argument('--build-number', type=int, required=True)
    parser.add_argument('--commit')
    parser.add_argument('--core-host-commit', default=candidate.CORE_SOURCE)
    parser.add_argument('--core-run-id', default=str(candidate.CORE_RUN))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.ipa and args.ipa_option:
        parser.error('Pass the IPA once')
    ipa = args.ipa or args.ipa_option
    if args.embed:
        if ipa:
            parser.error('--embed does not accept an IPA')
        result = embed(args.embed, args.build_number, args.core_identity, args.core_binary)
    elif args.structure:
        if not ipa or not args.commit:
            parser.error('--structure requires --ipa and --commit')
        result = validate_structure(ipa, args.build_number, args.commit, args.core_identity,
                                    args.core_host_commit, args.core_run_id)
    else:
        if not ipa:
            parser.error('Final signed validation requires an IPA')
        result = validate(ipa, args.build_number, args.core_identity, args.core_binary)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2, sort_keys=True))
