#!/usr/bin/env python3
"""Inspect a personal KartPad IPA without loading or extracting its game code.

This is an input preflight, not approval to replace NeoStation's current Core.
Runtime exports, shared state, signing and embedded lifecycle still need testing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import struct
import zipfile
from pathlib import Path

MAX_BINARY = 256 * 1024**2


def inspect_macho(data: bytes, pins: dict) -> dict:
    if len(data) < 32 or len(data) > MAX_BINARY:
        raise ValueError('Pack size is invalid')
    magic, cpu, subtype, kind, count, command_bytes, _, _ = struct.unpack_from('<8I', data)
    if (magic, cpu, subtype, kind) != (0xFEEDFACF, 0x0100000C, 0, 6):
        raise ValueError('Pack must be a thin arm64 iPhoneOS dylib')
    end = 32 + command_bytes
    if end > len(data) or count > command_bytes // 8:
        raise ValueError('Invalid Mach-O load commands')
    cursor = 32
    platforms, segments, tables = [], [], []
    for _ in range(count):
        if cursor + 8 > end:
            raise ValueError('Truncated Mach-O load command')
        command, size = struct.unpack_from('<2I', data, cursor)
        if size < 8 or size % 8 or cursor + size > end:
            raise ValueError('Invalid Mach-O load command size')
        if command == 0x32:  # LC_BUILD_VERSION
            if size < 24:
                raise ValueError('Invalid platform command')
            platforms.append(struct.unpack_from('<I', data, cursor + 8)[0])
        elif command == 0x19:  # LC_SEGMENT_64
            if size < 72:
                raise ValueError('Invalid segment command')
            vmaddr, vmsize, offset, length = struct.unpack_from('<4Q', data, cursor + 24)
            if length > vmsize or offset > len(data) or length > len(data) - offset:
                raise ValueError('Invalid file-backed segment')
            segments.append((vmaddr, offset, length))
        elif command == 2:  # LC_SYMTAB; exported data symbol retained by strip -x
            if size != 24:
                raise ValueError('Invalid symbol table command')
            tables.append(struct.unpack_from('<4I', data, cursor + 8))
        cursor += size
    if cursor != end or platforms != [2] or len(tables) != 1:
        raise ValueError('Expected iPhoneOS platform and one inspectable symbol table')
    symbol_offset, symbols, string_offset, string_bytes = tables[0]
    if (symbols > 1000000 or symbol_offset > len(data) or
            symbols * 16 > len(data) - symbol_offset or string_offset > len(data) or
            string_bytes > len(data) - string_offset):
        raise ValueError('Invalid symbol table bounds')
    strings = data[string_offset:string_offset + string_bytes]
    exports = {b'_kartpad_game_pack_info': [], b'_kartpad_game_pack_fingerprint': []}
    for index in range(symbols):
        name_offset, symbol_type, _, _, address = struct.unpack_from('<IBBHQ', data, symbol_offset + 16 * index)
        if name_offset >= len(strings):
            raise ValueError('Invalid symbol name')
        name_end = strings.find(b'\0', name_offset)
        if name_end < 0:
            raise ValueError('Unterminated symbol name')
        name = strings[name_offset:name_end]
        if name in exports:
            if symbol_type & 0xE0 or not symbol_type & 1 or symbol_type & 0x0E != 0x0E:
                raise ValueError('Game-pack info and fingerprint must be exported defined data')
            exports[name].append(address)

    def file_offset(name: bytes, size: int) -> int:
        if len(exports[name]) != 1:
            raise ValueError('Missing or ambiguous game-pack export ' + name.decode())
        address = exports[name][0]
        offsets = [offset + address - base for base, offset, length in segments
                   if base <= address and address - base + size <= length]
        if len(offsets) != 1:
            raise ValueError('Ambiguous or unmapped game-pack export ' + name.decode())
        return offsets[0]

    if struct.unpack_from('<I', data, file_offset(b'_kartpad_game_pack_info', 48))[0] != pins['pack_abi']:
        raise ValueError('Game-pack ABI mismatch')
    # ABI 3 accepts a pack by its interface fingerprint, which the pack exports
    # as a readable string; the runtime compares it before running any code.
    marker = b'kartpad-pack-fingerprint:' + pins['pack_interface_fingerprint'].encode() + b'\0'
    start = file_offset(b'_kartpad_game_pack_fingerprint', len(marker))
    if data[start:start + len(marker)] != marker:
        raise ValueError('Game-pack interface fingerprint mismatch')
    return {'pack_abi': pins['pack_abi'], 'pack_interface_fingerprint': pins['pack_interface_fingerprint'],
            'pack_sha256': hashlib.sha256(data).hexdigest(), 'pack_bytes': len(data)}


def inspect_ipa(path: Path, pins: dict) -> dict:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 10000:
            raise ValueError('IPA contains too many members')
        names = [item.filename for item in members]
        if len(names) != len(set(names)):
            raise ValueError('IPA contains duplicate members')
        plists = [item for item in members if item.filename.startswith('Payload/') and
                  item.filename.endswith('.app/Info.plist') and item.filename.count('/') == 2]
        if len(plists) != 1 or plists[0].file_size > 65536:
            raise ValueError('Expected exactly one application Info.plist')
        root = plists[0].filename.removesuffix('Info.plist')
        plist = plistlib.loads(archive.read(plists[0]))
        packs = [item for item in members if item.filename in
                 (root + 'Frameworks/libkartpad_game.dylib', root + 'libkartpad_game.dylib')]
        if len(packs) != 1:
            raise ValueError('A personal libkartpad_game.dylib is required; the public empty IPA is insufficient')
        if packs[0].file_size > MAX_BINARY:
            raise ValueError('Game pack exceeds the inspection limit')
        result = inspect_macho(archive.read(packs[0]), pins)
        result.update({'input_preflight_passed': True, 'app_version': plist.get('CFBundleShortVersionString'),
                       'target_release': pins['release'], 'integration_validated': pins['integrated'],
                       'physical_iphone_validated': pins['physical_iphone_validated']})
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('personal_ipa', type=Path)
    args = parser.parse_args()
    try:
        pins = json.loads(Path(__file__).with_name('migration-target.json').read_text())
        print(json.dumps(inspect_ipa(args.personal_ipa, pins), indent=2))
    except (ValueError, OSError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        parser.exit(1, f'ERROR: {error}\n')
