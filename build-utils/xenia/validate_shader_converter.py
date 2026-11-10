#!/usr/bin/env python3
"""Authenticates the Metal Shader Converter runtime supplied for XeniaCore.

XeniOS links `@rpath/libmetalirconverter.dylib` (Apple's Metal Shader
Converter) as a hard dependency: `MetalCommandProcessor` cannot render
without it, on both guest-shader paths (docs/xenios-playlist.md § Shader
converter). The library is Apple software under Apple's own terms; it is
never committed, rehosted or extracted from a third-party IPA. A builder
supplies it out of band, and this script checks that the supplied bytes are
the iPhoneOS library the pinned XeniOS sources expect before any Core build
or packaging uses them.

Usage: validate_shader_converter.py <dylib> [--pin build-utils/xenia/source.json]
       [--require-pinned-digest]

Exit 0 and a JSON report on success; exit 1 with the failed checks otherwise.
Pure standard library: no xcrun/vtool needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
FAT_MAGIC = 0xCAFEBABE
CPU_TYPE_ARM64 = 0x0100000C
MH_DYLIB = 0x6
LC_REQ_DYLD = 0x80000000
LC_SYMTAB = 0x2
LC_ID_DYLIB = 0xD
LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x18 | LC_REQ_DYLD
LC_ENCRYPTION_INFO_64 = 0x2C
LC_SOURCE_VERSION = 0x2A
LC_BUILD_VERSION = 0x32
LC_CODE_SIGNATURE = 0x1D
PLATFORMS = {1: 'MACOS', 2: 'IOS', 3: 'TVOS', 4: 'WATCHOS', 6: 'MACCATALYST',
             7: 'IOSSIMULATOR', 8: 'TVOSSIMULATOR', 9: 'WATCHOSSIMULATOR'}
N_EXT = 0x01
N_PEXT = 0x10
N_TYPE = 0x0E
N_SECT = 0x0E

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PIN = ROOT / 'build-utils' / 'xenia' / 'source.json'


def _version(value: int) -> str:
    return f'{value >> 16}.{(value >> 8) & 0xFF}.{value & 0xFF}'


def _source_version(value: int) -> str:
    parts = [(value >> 40) & 0xFFFFFF, (value >> 30) & 0x3FF, (value >> 20) & 0x3FF,
             (value >> 10) & 0x3FF, value & 0x3FF]
    while len(parts) > 2 and parts[-1] == 0:
        parts.pop()
    return '.'.join(str(part) for part in parts)


def parse(data: bytes) -> dict:
    """Facts of a thin arm64 Mach-O dylib; raises ValueError otherwise."""
    if len(data) < 32:
        raise ValueError('file too small for a Mach-O header')
    magic = struct.unpack_from('<I', data, 0)[0]
    if struct.unpack_from('>I', data, 0)[0] == FAT_MAGIC:
        raise ValueError('universal (fat) binary: an arm64 iPhoneOS thin library is required')
    if magic != MH_MAGIC_64:
        raise ValueError('not a 64-bit little-endian Mach-O')
    _, cputype, _, filetype, ncmds, sizeofcmds, flags, _ = struct.unpack_from('<IiiIIIII', data, 0)
    facts = {
        'cpu': 'arm64' if cputype == CPU_TYPE_ARM64 else hex(cputype & 0xFFFFFFFF),
        'filetype': 'dylib' if filetype == MH_DYLIB else hex(filetype),
        'install_name': None, 'current_version': None, 'compatibility_version': None,
        'platform': None, 'minos': None, 'sdk': None, 'source_version': None,
        'cryptid': None, 'code_signature': False, 'dependencies': [], 'weak_dependencies': [],
        'exports': [],
    }
    offset = 32
    end = offset + sizeofcmds
    if end > len(data):
        raise ValueError('load commands beyond end of file')
    symtab = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, offset)
        if size < 8 or offset + size > end:
            raise ValueError('malformed load command')
        if cmd in (LC_ID_DYLIB, LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB):
            name_offset, _, current, compatibility = struct.unpack_from('<IIII', data, offset + 8)
            name = data[offset + name_offset:offset + size].split(b'\0', 1)[0].decode('utf-8', 'replace')
            if cmd == LC_ID_DYLIB:
                facts['install_name'] = name
                facts['current_version'] = _version(current)
                facts['compatibility_version'] = _version(compatibility)
            elif cmd == LC_LOAD_DYLIB:
                facts['dependencies'].append(name)
            else:
                facts['weak_dependencies'].append(name)
        elif cmd == LC_BUILD_VERSION:
            platform, minos, sdk = struct.unpack_from('<III', data, offset + 8)
            facts['platform'] = PLATFORMS.get(platform, str(platform))
            facts['minos'] = _version(minos)
            facts['sdk'] = _version(sdk)
        elif cmd == LC_SOURCE_VERSION:
            facts['source_version'] = _source_version(struct.unpack_from('<Q', data, offset + 8)[0])
        elif cmd == LC_ENCRYPTION_INFO_64:
            facts['cryptid'] = struct.unpack_from('<III', data, offset + 8)[2]
        elif cmd == LC_CODE_SIGNATURE:
            facts['code_signature'] = True
        elif cmd == LC_SYMTAB:
            symtab = struct.unpack_from('<IIII', data, offset + 8)
        offset += size
    if symtab is not None:
        symoff, nsyms, stroff, strsize = symtab
        if symoff + nsyms * 16 > len(data) or stroff + strsize > len(data):
            raise ValueError('symbol table beyond end of file')
        for index in range(nsyms):
            strx, ntype, _, _, _ = struct.unpack_from('<IBBHQ', data, symoff + index * 16)
            if (ntype & N_EXT and not ntype & N_PEXT and (ntype & N_TYPE) == N_SECT
                    and 0 < strx < strsize):
                raw = data[stroff + strx:stroff + strsize].split(b'\0', 1)[0]
                facts['exports'].append(raw.decode('utf-8', 'replace'))
    facts['flags'] = flags
    return facts


def check(facts: dict, pin: dict, digest: str, size: int, require_digest: bool) -> list[str]:
    expected = pin['shader_converter']
    failures = []
    if facts['cpu'] != 'arm64' or facts['filetype'] != 'dylib':
        failures.append(f"not an arm64 dylib ({facts['cpu']}, {facts['filetype']})")
    if facts['platform'] != 'IOS':
        failures.append(f"platform {facts['platform']}: the iPhoneOS library is required, "
                        'not macOS or the simulator')
    if facts['install_name'] != expected['install_name']:
        failures.append(f"install name {facts['install_name']!r} != {expected['install_name']!r}")
    if facts['cryptid'] not in (None, 0):
        failures.append(f"encrypted (cryptid {facts['cryptid']})")
    minos = facts['minos'] or '0.0.0'
    if tuple(int(part) for part in minos.split('.')) > tuple(
            int(part) for part in expected['max_minos'].split('.')):
        failures.append(f"minos {minos} above {expected['max_minos']}")
    exports = set(facts['exports'])
    missing = [symbol for symbol in expected['required_exports'] if symbol not in exports]
    if missing:
        failures.append('missing exports: ' + ', '.join(missing))
    allowed = tuple(expected['allowed_dependency_prefixes'])
    foreign = [name for name in facts['dependencies'] if not name.startswith(allowed)]
    if foreign:
        failures.append('non-system dependencies: ' + ', '.join(foreign))
    pinned = {(item['sha256'], item['bytes'])
              for item in (expected['reference'], expected.get('upstream_mirror')) if item}
    if require_digest and (digest, size) not in pinned:
        failures.append(f'digest {digest} ({size} B) is neither the pinned reference nor the '
                        'pinned upstream mirror')
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('dylib', type=Path)
    parser.add_argument('--pin', type=Path, default=DEFAULT_PIN)
    parser.add_argument('--require-pinned-digest', action='store_true')
    args = parser.parse_args(argv)
    pin = json.loads(args.pin.read_text())
    data = args.dylib.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    try:
        facts = parse(data)
    except ValueError as error:
        print(json.dumps({'ok': False, 'failures': [str(error)]}, indent=2))
        return 1
    failures = check(facts, pin, digest, len(data), args.require_pinned_digest)
    report = {
        'ok': not failures,
        'failures': failures,
        'bytes': len(data),
        'sha256': digest,
        'matches_pinned_reference': digest == pin['shader_converter']['reference']['sha256'],
        'matches_pinned_mirror': digest == pin['shader_converter'].get('upstream_mirror', {}).get('sha256'),
        **{key: facts[key] for key in ('install_name', 'current_version', 'platform', 'minos',
                                       'sdk', 'source_version', 'cryptid', 'code_signature',
                                       'dependencies')},
        'exported_symbols': len(facts['exports']),
    }
    print(json.dumps(report, indent=2))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
