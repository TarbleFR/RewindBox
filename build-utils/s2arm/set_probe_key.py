#!/usr/bin/env python3
"""Switch 2 (S2Arm) test IPA: turn the device probe on in the generated host, and check the built app.

The MeloNX bridge runs the probe only when the host Info.plist carries the boolean
RewindBoxS2ArmProbe = true (packages/melonx_internal_bridge, MeloNXInternalBridgePlugin.swift).
The common IPA never sets it. This script is the only place of the test line that does, the same
way the configure_*.py scripts of the common recipe write their own host keys: on the generated
ios/Runner/Info.plist, after the scaffold and before the version stamp and the compilation.

    set_probe_key.py set [--plist ios/Runner/Info.plist]
    set_probe_key.py check-host [--registrant ios/Runner/GeneratedPluginRegistrant.m] [--plist ...]
    set_probe_key.py check-app  build/.../Runner.app
    set_probe_key.py check-ipa  dist/NeoStation.ipa

RewindBoxS2ArmProbeMapped is never written and is refused wherever it is found.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import plistlib
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
KEY = 'RewindBoxS2ArmProbe'
FORBIDDEN_KEY = 'RewindBoxS2ArmProbeMapped'
HOST_PLIST = 'ios/Runner/Info.plist'
HOST_REGISTRANT = 'ios/Runner/GeneratedPluginRegistrant.m'
PLUGIN_CLASS = 'S2ArmProbePlugin'
# Symbols the Runner executable must define: the static pod is linked into it (no image is added).
REQUIRED_SYMBOLS = ('_OBJC_CLASS_$_' + PLUGIN_CLASS, '_rb_s2arm_probe_attached', '_rb_s2arm_probe_detached')
ARM64 = 0x0100000C


class ProbeError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ProbeError(message)


def load_plist(raw, label):
    try:
        value = plistlib.loads(raw)
    except (ValueError, plistlib.InvalidFileException) as error:
        raise ProbeError(f'{label} is not a property list: {error}') from error
    require(isinstance(value, dict), f'{label} is not a dictionary')
    return value


def set_key(plist):
    """Set RewindBoxS2ArmProbe = true in the generated host Info.plist. The key must not be there yet."""
    plist = Path(plist)
    require(plist.is_file(), f'Missing host Info.plist: {plist} (the scaffold step did not run)')
    info = load_plist(plist.read_bytes(), str(plist))
    require(KEY not in info, f'{KEY} is already in {plist}: the key is set once, by this step only')
    require(FORBIDDEN_KEY not in info, f'{FORBIDDEN_KEY} must never be set (found in {plist})')
    info[KEY] = True
    # Same writer as build-utils/stamp_host_version.py, which rewrites this file next.
    plist.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_XML, sort_keys=False))
    return check_info(plist.read_bytes(), str(plist))


def check_info(raw, label):
    info = load_plist(raw, label)
    require(info.get(KEY) is True, f'{label}: {KEY} is not the boolean true (found {info.get(KEY)!r})')
    require(FORBIDDEN_KEY not in info, f'{label}: {FORBIDDEN_KEY} must never be set')
    return dict(plist=label, key=KEY, value=True, forbiddenKeyAbsent=True)


def check_host(registrant, plist):
    """Before the compilation: the generated registrant names the plugin class and the key is set."""
    registrant = Path(registrant)
    require(registrant.is_file(), f'Missing generated plugin registrant: {registrant}')
    require(PLUGIN_CLASS in registrant.read_text(), f'{registrant} does not register {PLUGIN_CLASS}: the probe '
            'package is not a dependency of the application')
    require(Path(plist).is_file(), f'Missing host Info.plist: {plist}')
    return dict(check_info(Path(plist).read_bytes(), str(plist)), registrant=str(registrant), pluginClass=PLUGIN_CLASS)


def arm64_slice(data):
    """The thin arm64 Mach-O of an executable (a fat container is opened)."""
    if data[:4] in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        wide = data[:4] == b'\xca\xfe\xba\xbf'
        require(len(data) >= 8, 'Truncated fat header')
        count = struct.unpack_from('>I', data, 4)[0]
        stride = 32 if wide else 20
        require(0 < count <= 32 and len(data) >= 8 + stride * count, 'Invalid fat architecture table')
        for index in range(count):
            position = 8 + index * stride
            if struct.unpack_from('>I', data, position)[0] == ARM64:
                offset, size = struct.unpack_from('>QQ' if wide else '>II', data, position + 8)
                require(offset + size <= len(data), 'Truncated arm64 slice')
                return data[offset:offset + size]
        raise ProbeError('The executable has no arm64 slice')
    require(len(data) >= 32 and data[:4] == b'\xcf\xfa\xed\xfe', 'The executable is not a 64-bit Mach-O')
    require(struct.unpack_from('<i', data, 4)[0] == ARM64, 'The executable is not arm64')
    return data


def defined_symbols(data):
    """Names of the symbols the image defines (external or local; debugging and undefined entries left out)."""
    data = arm64_slice(data)
    commands, size_of_commands = struct.unpack_from('<II', data, 16)
    require(commands <= 65536 and 32 + size_of_commands <= len(data), 'Truncated Mach-O load commands')
    position, table = 32, None
    for _ in range(commands):
        require(position + 8 <= 32 + size_of_commands, 'Truncated load command')
        command, size = struct.unpack_from('<II', data, position)
        require(size >= 8 and position + size <= 32 + size_of_commands, 'Invalid load command size')
        if command == 0x2:  # LC_SYMTAB
            require(size >= 24, 'Truncated symbol-table command')
            table = struct.unpack_from('<IIII', data, position + 8)
        position += size
    require(table is not None, 'The executable has no symbol table')
    symbol_offset, count, string_offset, string_size = table
    require(symbol_offset + 16 * count <= len(data) and string_offset + string_size <= len(data),
            'Truncated symbol table')
    names = set()
    for index in range(count):
        string_index, kind = struct.unpack_from('<IB', data, symbol_offset + 16 * index)
        # N_STAB entries (0xe0) are debugging records; N_TYPE == N_UNDF (0) is an import.
        if kind & 0xE0 or kind & 0x0E == 0 or string_index == 0:
            continue
        require(string_index < string_size, 'Symbol string offset out of range')
        start = string_offset + string_index
        end = data.find(b'\0', start, string_offset + string_size)
        require(end >= start, 'Unterminated symbol name')
        names.add(data[start:end].decode('utf-8', errors='replace'))
    return names


def check_executable(raw, label):
    """The Runner executable links the probe: its Objective-C class (the symbol the compiler emits for the
    class object) and its two entry points are defined in it."""
    symbols = defined_symbols(raw)
    missing = [name for name in REQUIRED_SYMBOLS if name not in symbols]
    require(not missing, f'{label} does not define {missing}: the static probe pod is not linked into the '
            'Runner executable (or its symbols were stripped before this check)')
    return dict(executable=label, pluginClass=PLUGIN_CLASS, definedSymbols=list(REQUIRED_SYMBOLS))


def no_probe_image(names, label):
    """static_framework = true: the probe adds no Mach-O image of its own."""
    found = sorted(name for name in names if 's2arm_probe.framework' in name)
    require(not found, f'{label} packages a separate probe framework {found[:3]}: the probe must be linked '
            'statically into Runner')


def check_app(app):
    app = Path(app)
    require(app.is_dir(), f'Missing built application: {app}')
    require((app / 'Info.plist').is_file() and (app / 'Runner').is_file(), f'{app} has no Info.plist or Runner')
    no_probe_image([path.relative_to(app).as_posix() for path in app.rglob('*') if 's2arm' in path.name.lower()],
                   str(app))
    return dict(result='passed', app=str(app), **check_info((app / 'Info.plist').read_bytes(), 'Info.plist'),
                **check_executable((app / 'Runner').read_bytes(), 'Runner'))


def check_ipa(ipa):
    ipa = Path(ipa)
    require(ipa.is_file(), f'Missing IPA: {ipa}')
    with zipfile.ZipFile(ipa) as archive:
        names = archive.namelist()
        roots = sorted({name.split('/')[1] for name in names
                        if name.startswith('Payload/') and name.count('/') >= 2 and name.split('/')[1].endswith('.app')})
        require(len(roots) == 1, f'{ipa} does not hold exactly one application: {roots}')
        root = f'Payload/{roots[0]}/'
        require(root + 'Info.plist' in names and root + 'Runner' in names, f'{ipa} has no Info.plist or Runner')
        no_probe_image(names, str(ipa))
        return dict(result='passed', ipa=str(ipa), application=roots[0],
                    **check_info(archive.read(root + 'Info.plist'), root + 'Info.plist'),
                    **check_executable(archive.read(root + 'Runner'), root + 'Runner'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('operation', choices=('set', 'check-host', 'check-app', 'check-ipa'))
    parser.add_argument('target', nargs='?', type=Path)
    parser.add_argument('--plist', type=Path, default=ROOT / HOST_PLIST)
    parser.add_argument('--registrant', type=Path, default=ROOT / HOST_REGISTRANT)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'set':
            require(args.target is None, 'set takes --plist, not a positional path')
            result = dict(set_key(args.plist), result='set')
        elif args.operation == 'check-host':
            result = dict(check_host(args.registrant, args.plist), result='passed')
        else:
            require(args.target is not None, args.operation + ' needs the application or IPA path')
            result = check_app(args.target) if args.operation == 'check-app' else check_ipa(args.target)
    except ProbeError as error:
        print('S2ARM PROBE CHECK FAILED: ' + str(error), file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
