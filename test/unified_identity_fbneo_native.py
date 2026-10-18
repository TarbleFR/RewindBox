#!/usr/bin/env python3
"""Run the already delivered FBNeo native parser/engine with an original CPU fixture.

Only a temporary copy's Mach-O platform metadata/signature is retargeted to
macOS. The original production artifact and all engine code remain unchanged.
The separate unified_identity_test.py verifies production Host/file routing.
"""
import argparse
import hashlib
import json
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DIGEST = '737bd97038db59e17d2ede4e68249be238c49bb31e3e93eced03a6e10e486625'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cores', required=True)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise SystemExit('Actual pinned FBNeo execution requires Apple Silicon macOS.')
    original = Path(args.cores) / 'Frameworks/fbneo_libretro.framework/fbneo_libretro'
    data = bytearray(original.read_bytes())
    if hashlib.sha256(data).hexdigest() != DIGEST:
        raise SystemExit('FBNeo is not the inspected delivered binary.')
    if struct.unpack_from('<I', data)[0] != 0xfeedfacf:
        raise SystemExit('Expected thin64-bit Mach-O.')
    offset, edits = 32, 0
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, offset)
        if command == 0x32:
            if struct.unpack_from('<I', data, offset + 8)[0] != 2:
                raise SystemExit('Expected delivered iOS platform metadata.')
            struct.pack_into('<I', data, offset + 8, 1)  # macOS; native code unchanged
            edits += 1
        offset += size
    if edits != 1:
        raise SystemExit('Expected exactly one platform command.')
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nsfb-', dir='/tmp') as work:
        work = Path(work)
        core, binary = work / 'fbneo.dylib', work / 'native-test'
        core.write_bytes(data)
        core.chmod(0o755)
        subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(core)], check=True)
        subprocess.run(['clang', '-std=c11', '-O1', '-Wall', '-Wextra',
                        '-I', str(ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include/libretro'),
                        str(ROOT / 'test/unified_identity_fbneo_native.c'), '-o', str(binary)], check=True)
        report = {'originalBinarySHA256': DIGEST, 'returncode': 0, 'cases': [],
                  'codeChanged': False, 'hostFixture': 'unified_identity_fbneo_test.m',
                  'physicalDeviceValidated': False}
        all_stdout, all_stderr = [], []
        combined = {'checks': 0, 'failures': 0}
        # The engine API and libretro lifecycle are independent fixtures. The
        # delivered BurnLibInit calls BurnLibExit itself, whose freed table
        # pointers remain non-null. Do not fabricate an Exit/init cycle in a
        # single process; each case starts with untouched native globals.
        for name, extra in (('engine', []), ('isolation', ['--isolation'])):
            command = [str(binary), str(core), str(work), *extra]
            outcome = subprocess.run(command, text=True, capture_output=True)
            case = {'name': name, 'returncode': outcome.returncode}
            report['cases'].append(case)
            (evidence / f'fbneo-native-{name}.stdout').write_text(outcome.stdout)
            (evidence / f'fbneo-native-{name}.stderr').write_text(outcome.stderr)
            all_stdout.append(outcome.stdout)
            all_stderr.append(outcome.stderr)
            if outcome.stdout.strip():
                try:
                    result = json.loads(outcome.stdout.strip().splitlines()[-1])
                    case['native'] = result
                    combined['checks'] += result.get('checks', 0)
                    combined['failures'] += result.get('failures', 0)
                    combined.update({key: value for key, value in result.items()
                                     if key not in ('checks', 'failures')})
                except json.JSONDecodeError:
                    pass
            print(outcome.stdout, end='')
            if outcome.returncode:
                report['returncode'] = outcome.returncode
                print(outcome.stderr, file=sys.stderr, end='')
                if outcome.returncode < 0:
                    case['signal'] = -outcome.returncode
                    try:
                        diagnostic = subprocess.run(
                            ['lldb', '--batch', '-o', 'settings set target.disable-aslr false',
                             '-o', 'run', '-k', 'thread backtrace all', '--', *command],
                            text=True, capture_output=True, timeout=60)
                        (evidence / 'fbneo-native-backtrace.txt').write_text(
                            diagnostic.stdout + diagnostic.stderr)
                        case['debuggerReturncode'] = diagnostic.returncode
                    except (OSError, subprocess.TimeoutExpired) as error:
                        (evidence / 'fbneo-native-backtrace.txt').write_text(str(error) + '\n')
                break
        report['native'] = combined
        (evidence / 'fbneo-native.stdout').write_text(''.join(all_stdout))
        (evidence / 'fbneo-native.stderr').write_text(''.join(all_stderr))
        (evidence / 'fbneo-native.json').write_text(json.dumps(report, indent=2) + '\n')
        if report['returncode']:
            raise SystemExit(report['returncode'])


if __name__ == '__main__':
    main()
