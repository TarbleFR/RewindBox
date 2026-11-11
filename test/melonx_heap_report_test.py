#!/usr/bin/env python3
"""tools/melonx/heap_report.py on a synthetic journal and a synthetic symbol map (no device log is used or stored).

Two windows of one PID and one of another: windows are read per PID, the engine's places are named with the map, a
stack's owner is the image of its first place that is not an allocation wrapper, and the text and JSON reports agree.
"""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/melonx/heap_report.py'
checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def header(seconds, reason, live, samples, pid):
    context = json.dumps(dict(build='735', pid=str(pid)), separators=(',', ':'))
    return (f'[MeloNX:heap] window {seconds} s ({reason}): live {live} MiB in {samples} samples, allocated 5000 MiB in 20000, interval 256 KiB, '
            f'870 stacks, 0 dropped, 3 unwalked; zones=DefaultMallocZone:907/1004,QuartzCore:0/0 context={context}\n')


PID = 4242
with tempfile.TemporaryDirectory(prefix='melonx-heap-report-') as directory:
    log = Path(directory) / 'MeloNX-performance.log'
    with open(log, 'w') as out:
        out.write('[MeloNX:perf] t=41 fps=19.0/52.0/40 context={"pid":"4242"}\n')
        out.write(header(120, 'window', 600, 2400, PID))
        out.write('[MeloNX:heap] #1 live=300/1200 total=320/1280 stack=libc++abi.dylib+0x10<MeloNXMoltenVKStandalone+0x2000<MeloNXMoltenVKStandalone+0x2400<MeloNXCore+0x3004<MeloNXCore+0x1010\n')
        out.write('[MeloNX:heap] #2 live=200/800 total=900/3600 stack=MeloNXCore+0x2008<MeloNXCore+0x3010<jit\n')
        out.write('[MeloNX:heap] #3 live=40/40 total=40/40 stack=-\n')
        out.write('[MeloNX:perf] t=121 fps=30.0 context={"pid":"4242"}\n')
        out.write(header(120, 'window', 111, 444, PID + 1))
        out.write('[MeloNX:heap] #1 live=111/444 total=111/444 stack=Other+0x1\n')
        out.write(header(35, 'sessionEnd', 50, 200, PID))
        out.write('[MeloNX:heap] #1 live=50/200 total=50/200 stack=libswiftCore.dylib+0x44<Flutter+0x900\n')
    symbols = Path(directory) / 'Ryujinx.Library.symbols.txt.gz'
    with gzip.open(symbols, 'wt') as out:
        out.write('0000000000001000 t _RunLoop\n0000000000002000 t _NativeAlloc\n0000000000003000 t _CreatePipeline\n0000000000004000 t _End\n')

    def run(*extra):
        return subprocess.run([sys.executable, str(TOOL), str(log), '--pid', str(PID), *extra], capture_output=True, text=True)

    plain = run()
    check(plain.returncode == 0, plain.stderr)
    data = json.loads(run('--json', '--symbols', str(symbols)).stdout)
    check(data['pid'] == str(PID) and data['named'] is True and len(data['windows']) == 2, 'two windows of this PID, the other PID\'s left out')
    first, second = data['windows']
    check(first['seconds'] == 120 and first['reason'] == 'window' and first['liveMiB'] == 600 and first['liveSamples'] == 2400 and
          first['allocatedMiB'] == 5000 and first['intervalKiB'] == 256 and first['stacksRecorded'] == 870 and first['unwalked'] == 3 and
          first['zones'].startswith('DefaultMallocZone:907/1004'), 'the header\'s fields')
    check([s['liveMiB'] for s in first['stacks']] == [300, 200, 40] and first['listedLiveMiB'] == 540 and
          [s['livePercent'] for s in first['stacks']] == [50.0, 33.3, 6.7], 'stacks in order, with their share of the live bytes')
    check(first['stacks'][0]['names'] == ['libc++abi.dylib+0x10', 'MeloNXMoltenVKStandalone+0x2000', 'MeloNXMoltenVKStandalone+0x2400', '_CreatePipeline', '_RunLoop'] and
          first['stacks'][1]['names'] == ['_NativeAlloc', '_CreatePipeline', 'jit'] and first['stacks'][2]['names'] == [],
          'the engine\'s places are named, the others kept')
    check(first['liveByOwner'] == [['MeloNXMoltenVKStandalone', 300], ['MeloNXCore', 200], ['-', 40]],
          'the owner is the first place that is not an allocation wrapper: ' + str(first['liveByOwner']))
    check(first['liveByEngineEntry'] == [['_CreatePipeline', 200], ['_RunLoop', 300]] or first['liveByEngineEntry'] == [['_RunLoop', 300], ['_CreatePipeline', 200]],
          'live bytes under the engine\'s outermost listed function: ' + str(first['liveByEngineEntry']))
    check(second['reason'] == 'sessionEnd' and second['seconds'] == 35 and second['liveByOwner'] == [['Flutter', 50]] and second['liveByEngineEntry'] == [],
          'a window ended by the session; a Swift allocation wrapper is passed over')
    unnamed = json.loads(run('--json').stdout)
    check(unnamed['named'] is False and unnamed['windows'][0]['stacks'][1]['names'] == ['MeloNXCore+0x2008', 'MeloNXCore+0x3010', 'jit'] and
          unnamed['windows'][0]['liveByEngineEntry'] == [['MeloNXCore+0x1010', 300], ['MeloNXCore+0x3010', 200]], 'without a map the places stand')
    text = run('--symbols', str(symbols)).stdout
    check('window of 120 s (window): live 600 MiB in 2400 samples' in text and '#1 live 300 MiB (50.0 %) in 1200 samples; allocated 320 MiB in 1280' in text and
          'MeloNXMoltenVKStandalone 300, MeloNXCore 200' in text and '_CreatePipeline' in text and 'window of 35 s (sessionEnd)' in text, text)
    missing = subprocess.run([sys.executable, str(TOOL), str(log), '--pid', '1'], capture_output=True, text=True)
    check(missing.returncode != 0 and 'no [MeloNX:heap] window for pid 1' in missing.stderr, 'an unknown PID is refused')

print(f'PASS {checks} heap report checks')
