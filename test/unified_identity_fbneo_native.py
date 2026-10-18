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
        outcome = subprocess.run([str(binary), str(core), str(work)], text=True, capture_output=True)
        (evidence / 'fbneo-native.stdout').write_text(outcome.stdout)
        (evidence / 'fbneo-native.stderr').write_text(outcome.stderr)
        report = {'originalBinarySHA256': DIGEST, 'returncode': outcome.returncode,
                  'codeChanged': False, 'hostFixture': 'unified_identity_fbneo_test.m',
                  'physicalDeviceValidated': False}
        if outcome.stdout.strip():
            try:
                report['native'] = json.loads(outcome.stdout.strip().splitlines()[-1])
            except json.JSONDecodeError:
                pass
        (evidence / 'fbneo-native.json').write_text(json.dumps(report, indent=2) + '\n')
        print(outcome.stdout, end='')
        if outcome.returncode:
            print(outcome.stderr, file=sys.stderr, end='')
            raise SystemExit(outcome.returncode)


if __name__ == '__main__':
    main()
