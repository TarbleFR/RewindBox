#!/usr/bin/env python3
"""Focused PSP relaunch checks; no commercial ROMs and no core rebuild."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'fee67e4d0aeede934bfed722f8dd9b43fb6d2ff5'
SOURCE = 'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.m'


def native():
    out = ROOT / 'build/psp496'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='psp496-') as name:
        work = Path(name)
        old = work / 'baseline.m'
        old.write_bytes(subprocess.check_output(['git', 'show', BASE + ':' + SOURCE], cwd=ROOT))
        records = []
        for label, source in [('baseline', old), ('candidate', ROOT / SOURCE)]:
            executable = work / label
            subprocess.run(['clang', '-fobjc-arc', '-O1', '-Wall', '-Werror',
                            '-I', str((ROOT / SOURCE).parent), str(source),
                            str(ROOT / 'test/libretro_host/frontend/address_space_test.m'),
                            '-framework', 'Foundation', '-o', str(executable)], check=True)
            result = subprocess.run([str(executable)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (out / (label + '.log')).write_text(result.stdout)
            if label == 'baseline':
                assert result.returncode != 0 and 'FAIL PSP_RELAUNCH_UNUSED_RAM_PROTECTED' in result.stdout, result.stdout
            else:
                assert result.returncode == 0, result.stdout
            records.append({'label': label, 'exit': result.returncode})
            print(label, result.returncode, result.stdout[-1000:], flush=True)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
        subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Werror', '-target', 'arm64-apple-ios18.0',
                        '-isysroot', sdk, '-c', str(ROOT / SOURCE), '-o', str(work / 'address.o')], check=True)
        (out / 'native.json').write_text(json.dumps({'baseline': BASE, 'records': records, 'iphoneSDKCompile': True}))


def simulator():
    import libretro_simulator_probe as probe
    original = {s['name']: s for s in probe.SCENARIOS}
    sequence = ['ppsspp-iso-1', 'ppsspp-iso-2', 'ppsspp-prx',
                'neotest-1', 'ppsspp-iso-1', 'ppsspp-prx', 'ppsspp-iso-2']
    probe.SCENARIOS = [dict(original[name], name=f'psp496-{index}-{name}') for index, name in enumerate(sequence)]
    # Every session uses the production session/host and the pinned real
    # PPSSPP binary. The existing checker requires startup, frames, stop,
    # the complete teardown, return to the library and successful relaunch.
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    probe.main()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'native':
        native()
    elif len(sys.argv) > 1 and sys.argv[1] == 'simulator':
        simulator()
    else:
        raise SystemExit('expected native or simulator')
