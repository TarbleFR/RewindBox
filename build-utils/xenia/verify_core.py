#!/usr/bin/env python3
"""Checks the built XeniaCore.framework, then copies it to dist/xenia.

Refuses anything that is not the embedded Core RewindBox's bridge expects:
an arm64 iPhoneOS framework with minos 26.0, install name @rpath, a non-weak
@rpath/libmetalirconverter.dylib dependency and NeoXenia_GetAPI as its only
exported symbol; no main(), no absolute build path. The shader converter is
never copied into dist (docs/xenios-playlist.md § Shader converter).
Usage: verify_core.py <ios-build-dir> <dist-dir>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build-utils' / 'xenia'))
import validate_shader_converter as macho  # noqa: E402


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
    for forbidden in (b'/Users/runner/', b'/Users/builder/', b'/home/runner/'):
        if forbidden in data:
            raise SystemExit(f'Absolute build path {forbidden!r} leaked into XeniaCore')
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
        'source': json.loads((ROOT / 'build-utils' / 'xenia' / 'source.json').read_text())['revision'],
    }
    (dist / 'XeniaCore.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
