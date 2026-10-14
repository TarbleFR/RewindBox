#!/usr/bin/env python3
"""Check the linked shader compiler boundary in the final IPA (not gameplay)."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import zipfile


def exported_symbols(data):
    """Use dyld's export trie, not debug/local nlist entries left by strip."""
    if data[:4] != b'\xcf\xfa\xed\xfe':
        raise ValueError('Expected the delivered thin arm64 framework')
    count, command_bytes = struct.unpack_from('<II', data, 16)
    position, table = 32, None
    for _ in range(count):
        command, size = struct.unpack_from('<II', data, position)
        if size < 8 or position + size > 32 + command_bytes:
            raise ValueError('Invalid Mach-O load commands')
        if command == 0x80000033:  # LC_DYLD_EXPORTS_TRIE
            table = struct.unpack_from('<II', data, position + 8)
        elif command in (0x22, 0x80000022) and table is None:  # LC_DYLD_INFO(_ONLY)
            table = struct.unpack_from('<II', data, position + 40)
        position += size
    if table is None or not table[1] or table[0] + table[1] > len(data):
        raise ValueError('The framework has no valid dyld export trie')
    trie = data[table[0]:table[0] + table[1]]

    def uleb(offset):
        value, shift = 0, 0
        while offset < len(trie) and shift < 64:
            byte = trie[offset]
            offset += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value, offset
            shift += 7
        raise ValueError('Invalid export trie integer')

    exports = {}

    def visit(offset, prefix, ancestors):
        if offset in ancestors or len(ancestors) > 256 or len(prefix) > 4096:
            raise ValueError('Cyclic or oversized export trie')
        terminal_size, cursor = uleb(offset)
        end = cursor + terminal_size
        if end >= len(trie):
            raise ValueError('Truncated export trie node')
        if terminal_size:
            flags, _ = uleb(cursor)
            exports[prefix] = flags
        children = trie[end]
        cursor = end + 1
        for _ in range(children):
            edge_end = trie.find(b'\0', cursor)
            if edge_end < cursor:
                raise ValueError('Unterminated export edge')
            edge = trie[cursor:edge_end].decode('utf-8')
            child, cursor = uleb(edge_end + 1)
            visit(child, prefix + edge, ancestors | {offset})

    visit(0, '', set())
    return exports


def validate(ipa, build_number):
    with zipfile.ZipFile(ipa) as archive:
        infos = [n for n in archive.namelist() if n.startswith('Payload/') and n.count('/') == 2 and n.endswith('.app/Info.plist')]
        if len(infos) != 1:
            raise ValueError('Expected one application')
        info = plistlib.loads(archive.read(infos[0]))
        if str(info['CFBundleVersion']) != build_number:
            raise ValueError('Unexpected application build number')
        app = infos[0].removesuffix('Info.plist')
        kit_data = archive.read(app + 'Frameworks/neo_shader_kit.framework/neo_shader_kit')
        kit = exported_symbols(kit_data)
        prefixes = ('_Neo', '_OBJC_CLASS_$_Neo', '_OBJC_METACLASS_$_Neo', '_OBJC_IVAR_$_Neo', '_neo_shader_kitVersion')
        unexpected = sorted(n for n in kit if not n.startswith(prefixes))
        if unexpected:
            raise ValueError('Compiler implementation escaped the framework boundary: ' + ', '.join(unexpected[:8]))
        required = {'_OBJC_CLASS_$_NeoSlangProgram', '_OBJC_CLASS_$_NeoSlangChain',
                    '_OBJC_CLASS_$_NeoShaderStorage', '_NeoShaderFormatSlang'}
        if not required <= set(kit):
            raise ValueError('The linked framework hid its public shader API: ' + str(required - set(kit)))
        dolphin_data = archive.read(app + 'Frameworks/DolphinCore.framework/DolphinCore')
        dolphin = exported_symbols(dolphin_data)
        old_weak = [name for name, flags in dolphin.items() if 'glslang' in name and 'addSwizzle' in name and flags & 4]
        if len(old_weak) != 2:
            raise ValueError('The expected pinned Dolphin compiler image is absent')
        return {'build': build_number, 'kitSha256': hashlib.sha256(kit_data).hexdigest(),
                'publicExportCount': len(kit), 'compilerExports': 0, 'oldDolphinWeakSwizzles': old_weak,
                'compilerIsolationPackaged': True, 'physicalDeviceGameplayValidated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path)
    parser.add_argument('--build-number', required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = validate(args.ipa, args.build_number)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
