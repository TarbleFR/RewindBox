#!/usr/bin/env python3
"""Checks the built XeniaCore.framework, then copies it to dist/xenia.

Refuses anything that is not the embedded Core RewindBox's bridge expects:
an arm64 iPhoneOS framework with minos 26.0, install name @rpath, a non-weak
@rpath/libmetalirconverter.dylib dependency and NeoXenia_GetAPI as its only
exported symbol; no main(), no absolute build path; no Objective-C class
sharing a name with one of the bridge's (RTLD_LOCAL does not isolate the
Objective-C runtime). The shader converter is never copied into dist
(docs/xenios-playlist.md § Shader converter).
Usage: verify_core.py <ios-build-dir> <dist-dir>
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build-utils' / 'xenia'))
sys.path.insert(0, str(ROOT / 'test'))
import validate_shader_converter as macho  # noqa: E402
from xenia_objc_namespace_test import bridge_classes  # noqa: E402


def defined_objc_classes(nm_output: str) -> set[str]:
    """Classes the binary defines (`nm -m`, every symbol, undefined ones left out)."""
    names = set()
    for line in nm_output.splitlines():
        if '(undefined)' in line:
            continue
        match = re.search(r'_OBJC_CLASS_\$_([A-Za-z_]\w*)', line)
        if match:
            names.add(match.group(1))
    return names


FORBIDDEN_PATHS = (b'/Users/runner/', b'/Users/builder/', b'/home/runner/')
LOAD_COMMANDS = {0x2: 'LC_SYMTAB', 0xC: 'LC_LOAD_DYLIB', 0xD: 'LC_ID_DYLIB', 0x19: 'LC_SEGMENT_64',
                 0x8000001C: 'LC_RPATH', 0x80000018: 'LC_LOAD_WEAK_DYLIB'}


def regions(data: bytes) -> list[tuple[int, int, str]]:
    """File ranges of a thin 64-bit Mach-O: each load command, each section, the string table."""
    if len(data) < 32 or struct.unpack_from('<I', data, 0)[0] != 0xFEEDFACF:
        return []
    ncmds = struct.unpack_from('<I', data, 16)[0]
    found, offset = [], 32
    for _ in range(ncmds):
        if offset + 8 > len(data):
            break
        command, size = struct.unpack_from('<II', data, offset)
        if size < 8:
            break
        name = LOAD_COMMANDS.get(command, hex(command))
        found.append((offset, offset + size, 'load command ' + name))
        if command == 0x19:
            nsects = struct.unpack_from('<I', data, offset + 64)[0]
            for index in range(nsects):
                base = offset + 72 + 80 * index
                if base + 80 > offset + size:
                    break
                section = data[base:base + 16].rstrip(b'\0').decode('ascii', 'replace')
                segment = data[base + 16:base + 32].rstrip(b'\0').decode('ascii', 'replace')
                length, start = struct.unpack_from('<QI', data, base + 40)
                if start:
                    found.append((start, start + length, f'section {segment},{section}'))
        elif command == 0x2:
            stroff, strsize = struct.unpack_from('<II', data, offset + 16)
            found.append((stroff, stroff + strsize, 'symbol string table (N_SO/N_OSO debug map, symbol names)'))
        offset += size
    return found


def leaked_paths(data: bytes, limit: int = 40) -> list[str]:
    """Every distinct printable string holding an absolute build path, with where it sits (empty when none)."""
    spans = regions(data)
    seen, report = set(), []
    for forbidden in FORBIDDEN_PATHS:
        start = data.find(forbidden)
        while start != -1:
            begin, end = start, start
            while begin > 0 and 0x20 <= data[begin - 1] < 0x7F:
                begin -= 1
            while end < len(data) and 0x20 <= data[end] < 0x7F:
                end += 1
            text = data[begin:end].decode('ascii', 'replace')
            where = next((name for low, high, name in spans if low <= begin < high), 'outside any section')
            if (where, text) not in seen:
                seen.add((where, text))
                report.append(f'{where} @0x{begin:x}: {text}')
            start = data.find(forbidden, end)
    total = len(report)
    return report[:limit] + ([f'... {total - limit} more'] if total > limit else [])


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True)


def main() -> None:
    build, dist = map(Path, sys.argv[1:3])
    candidates = [path for path in build.rglob('XeniaCore.framework')
                  if (path / 'XeniaCore').is_file()]
    if len(candidates) != 1:
        raise SystemExit(f'Expected one XeniaCore.framework, found {candidates}')
    framework = candidates[0]
    binary = framework / 'XeniaCore'
    data = binary.read_bytes()
    leaks = leaked_paths(data)
    if leaks:
        # Refused, never relaxed: every leaked string is listed with its place in the binary.
        raise SystemExit('Absolute build paths leaked into XeniaCore:\n- ' + '\n- '.join(leaks))
    facts = macho.parse(data)
    failures = []
    if facts['cpu'] != 'arm64' or facts['filetype'] != 'dylib':
        failures.append(f"not an arm64 dylib: {facts['cpu']} {facts['filetype']}")
    if facts['platform'] != 'IOS' or facts['minos'] != '26.0.0':
        failures.append(f"platform {facts['platform']} minos {facts['minos']} (IOS 26.0.0 expected)")
    if facts['install_name'] != '@rpath/XeniaCore.framework/XeniaCore':
        failures.append(f"install name {facts['install_name']}")
    if '@rpath/libmetalirconverter.dylib' not in facts['dependencies']:
        failures.append('libmetalirconverter.dylib is not a (non-weak) dependency')
    exported = sorted(set(facts['exports']))
    if exported != ['_NeoXenia_GetAPI']:
        failures.append(f'exports must be only _NeoXenia_GetAPI, found {exported[:10]}')
    nm = run('xcrun', 'nm', '-gU', str(binary))
    if ' _main\n' in nm:
        failures.append('main() is exported')
    core_classes = defined_objc_classes(run('xcrun', 'nm', '-m', str(binary)))
    if not core_classes and '__objc_classlist' in run('xcrun', 'otool', '-l', str(binary)):
        failures.append('Objective-C classes present but not listed by nm -m (stripped?): cannot check names')
    clash = sorted(core_classes & bridge_classes())
    if clash:
        failures.append(f'Objective-C classes shared with the bridge: {clash}')
    for resource in ('LICENSE.txt', 'Acknowledgements.json', 'Info.plist'):
        if not (framework / resource).is_file():
            failures.append(f'{resource} missing from the framework')
    if failures:
        raise SystemExit('XeniaCore rejected:\n- ' + '\n- '.join(failures))
    destination = dist / 'XeniaCore.framework'
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(framework, destination, symlinks=True)
    report = {
        'framework': 'XeniaCore.framework',
        'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'minos': facts['minos'],
        'sdk': facts['sdk'],
        'dependencies': facts['dependencies'],
        'exports': exported,
        'objc_classes': len(core_classes),
        'source': json.loads((ROOT / 'build-utils' / 'xenia' / 'source.json').read_text())['revision'],
    }
    (dist / 'XeniaCore.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
