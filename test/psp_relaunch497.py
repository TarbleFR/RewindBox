#!/usr/bin/env python3
"""Reproduce the device arena collision and exercise continuous view ownership."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'b332bc2e59e4f44d4e820aa4879520a058bfd76b'
CLASSES = ROOT / 'packages/libretro_internal_bridge/ios/Classes'


def native():
    out = ROOT / 'build/psp497'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='psp497-') as name:
        work = Path(name)
        old = work / 'baseline.m'
        old.write_bytes(subprocess.check_output(['git', 'show', BASE + ':packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.m'], cwd=ROOT))
        records = []
        for label, source in [('baseline', old), ('candidate', CLASSES / 'LibretroAddressSpace.m')]:
            executable = work / label
            flags = ['-DPSP497_LEGACY_ONLY=1'] if label == 'baseline' else []
            subprocess.run(['clang', '-fobjc-arc', '-O1', '-Wall', '-Werror', *flags,
                            '-I', str(CLASSES), str(source),
                            str(ROOT / 'test/libretro_host/frontend/psp_managed_memory_test.m'),
                            '-framework', 'Foundation', '-o', str(executable)], check=True)
            result = subprocess.run([str(executable), *(['legacy'] if label == 'baseline' else [])],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (out / (label + '.log')).write_text(result.stdout)
            assert result.returncode == 0, result.stdout
            required = 'PSP497_ARENA_VIEW_COLLISION_REPRODUCED' if label == 'baseline' else 'PSP497_MANAGED_MEMORY cycles=18 allocatorIntrusions=0'
            assert 'PASS ' + required in result.stdout, result.stdout
            records.append({'label': label, 'exit': result.returncode, 'required': required})
            print(label, result.stdout[-2000:], flush=True)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
        subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Werror', '-target', 'arm64-apple-ios18.0',
                        '-isysroot', sdk, '-c', str(CLASSES / 'LibretroAddressSpace.m'), '-o', str(work / 'address.o')], check=True)
        (out / 'native.json').write_text(json.dumps({'baseline': BASE, 'records': records, 'iphoneSDKCompile': True}))


def simulator():
    import libretro_simulator_probe as probe
    original = {s['name']: s for s in probe.SCENARIOS}
    sequence = ['ppsspp-crowded', 'ppsspp-crowded', 'ppsspp-crowded-prx',
                'neotest-1', 'ppsspp-crowded', 'ppsspp-crowded-prx', 'ppsspp-crowded']
    scenarios = []
    for i, name in enumerate(sequence):
        s = dict(original[name], name=f'psp497-{i}-{name}')
        if s['core'] == 'ppsspp':
            s['requiredLog'] = ['PPSSPP managed memory ABI 1', "PPSSPP's memory at the reserved base",
                                'managed PSP arena released; all views continuously reserved',
                                ', 64 MiB of PSP RAM' if name.endswith('prx') else ', 32 MiB of PSP RAM']
        scenarios.append(s)
    probe.SCENARIOS = scenarios
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    probe.main()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'native':
        native()
    elif len(sys.argv) > 1 and sys.argv[1] == 'simulator':
        simulator()
    else:
        raise SystemExit('expected native or simulator')
