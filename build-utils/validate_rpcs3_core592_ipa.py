#!/usr/bin/env python3
"""Bind the verified Core592 artifact to the signed private IPA588.

The raw artifact SHA is exact. Signing may change binary bytes, so compare
compiled code/data and ABI metadata with the authenticated raw Core using the
existing delivery fingerprint. Non-signature load commands and LINKEDIT are also
sealed, allowing bounded signature alignment and segment resizing. LC_ID_DYLIB
must remain unchanged. IPA587 is the
baseline; its unchanged receipts and earlier Core contracts are not replayed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3runtime592_delivery_core as core592

BUILD = 588
RECEIPT = 'RPCS3-core592-identity.json'
CORE = 'Frameworks/libRPCS3Core.dylib'


def sha(data):
    return hashlib.sha256(data).hexdigest()


INSTALL_NAME = core592.CORE_ID


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
    raw = core592.raw_core()
    if path:
        provided = Path(path).read_bytes()
        assert sha(provided) == core592.core_receipt()['coreSHA256'], 'Raw Core differs from authenticated artifact'
        assert provided == raw
    return raw


def expected(identity):
    core592.validate_rpc_core_identity(identity)
    record = core592.core_receipt()
    return dict(build=BUILD, baseline=587, coreSource=record['coreSource'],
                coreNativeSource=record['coreNativeSource'], coreRun=record['coreRun'],
                coreArtifact=record['artifact'], diagnosticsArtifact=record['diagnosticsArtifact'],
                coreSHA256=record['coreSHA256'], corePayloadFingerprint=record['corePayloadFingerprint'],
                identitySHA256=record['identitySHA256'], proofSHA256=record['proofSHA256'],
                hostCommit=identity['host_commit'], abiVersion=identity['abi_version'],
                sourcePatchSHA256=identity['source_patch_sha256'], codegen=record['codegen'],
                changedPaths=record['changedPaths'], canonicalPostimages=record['canonicalPostimages'],
                tests=record['tests'], installName=core592.CORE_ID,
                physicalDeviceTested=False, gameplayMeasured=False, fpsGainMeasured=False)


def compare_core(packaged, raw, signed):
    """Compare against authenticated raw bytes, allowing the signing fingerprint."""
    before, after = core592.macho(raw), core592.macho(packaged)
    assert before['id'] == after['id'] == core592.CORE_ID, 'RPCS3 install name changed during packaging'
    assert after['platform'] == before['platform'] == 2
    assert after['fileType'] == before['fileType'] == 6
    assert len(after['definedSymbols']) == 88
    if signed:
        assert after['codeSignature'] is True, 'Packaged Core has no code signature'
    fingerprint = core592.payload_fingerprint(packaged)
    assert fingerprint == core592.payload_fingerprint(raw), 'Signing/packaging changed Core code, data or ABI metadata'
    metadata = compare_signature_metadata(raw, packaged) if signed or packaged != raw else {}
    for marker in core592.CORE_MARKERS:
        assert marker in packaged, marker
    return dict(compiledPayloadFingerprint=fingerprint, installName=after['id'],
                signed=after['codeSignature'], definedSymbols=len(after['definedSymbols']), metadata=metadata)


def embed(app, identity_path, raw_path=None, report=None):
    identity = json.loads(Path(identity_path).read_bytes())
    receipt = expected(identity)
    raw = raw_core(raw_path)
    state = compare_core((Path(app) / CORE).read_bytes(), raw, signed=False)
    (Path(app) / RECEIPT).write_text(json.dumps(receipt, indent=2) + '\n')
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        Path(report).write_text(json.dumps(dict(receipt=receipt, core=state), indent=2) + '\n')
    return receipt


def validate(ipa, build, identity_path, raw_path=None):
    assert int(build) == BUILD, 'Core592 delivery receipt is for private build588'
    identity = json.loads(Path(identity_path).read_bytes())
    receipt = expected(identity)
    raw = raw_core(raw_path)
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        assert len(names) == len(set(names)), 'Duplicate IPA entries'
        roots = [name[:-10] for name in names if name.startswith('Payload/') and
                 len(name.split('/')) == 3 and name.endswith('.app/Info.plist')]
        assert len(roots) == 1, roots
        root = roots[0]
        info = plistlib.loads(z.read(root + 'Info.plist'))
        assert str(info['CFBundleVersion']) == str(build), info['CFBundleVersion']
        assert json.loads(z.read(root + RECEIPT)) == receipt, 'Packaged Core592 receipt changed'
        packaged = z.read(root + CORE)
        state = compare_core(packaged, raw, signed=True)
    return dict(result='passed', build=build, ipaSHA256=sha(Path(ipa).read_bytes()),
                receipt=receipt, rawCoreSHA256=sha(raw), signedCoreSHA256=sha(packaged),
                core=state, physicalDeviceTested=False, gameplayMeasured=False,
                scope='Authenticated Core592 raw binary; compiled sections, ABI fingerprint, non-signature load commands and LINKEDIT preserved in the signed IPA. Other component checks belong to the delivery.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ipa', nargs='?', type=Path)
    p.add_argument('--embed', type=Path)
    p.add_argument('--core-binary', type=Path)
    p.add_argument('--core-identity', type=Path, default=ROOT / 'dist/rpcs3-native/identity.json')
    p.add_argument('--build-number', type=int, default=BUILD)
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    if args.embed:
        assert not args.ipa
        result = embed(args.embed, args.core_identity, args.core_binary, args.report)
    else:
        assert args.ipa and args.report
        result = validate(args.ipa, args.build_number, args.core_identity, args.core_binary)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
