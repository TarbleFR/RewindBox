#!/usr/bin/env python3
"""tools/melonx/hot_spots.py on a synthetic journal and a synthetic symbol map (no device log is used or stored).

Two profiles of one PID (a slow one and a base one) and one of another PID: the profiles are read per PID, each
thread's lists are summed per function of the map (two call sites of one function add up, never above the running
samples), by image without a map, and the text and JSON reports agree.
"""
import gzip
import json
import struct
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/melonx/hot_spots.py'
checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def header(number, kind, second, fps, pid):
    context = json.dumps(dict(build='733', pid=str(pid)), separators=(',', ':'))
    return f'[MeloNX:hot] #{number} {kind} t={second} fps={fps} 300 samples in 3040 ms, 2 threads context={context}\n'


def thread(number, name, priority, run, wait, own, stack, waiting, missed=0):
    def text(entries):
        return ','.join(f'{place}:{count}' for place, count in entries) or '-'
    return f'[MeloNX:hot] #{number} {name} p{priority} run={run} wait={wait} missed={missed} self={text(own)} stack={text(stack)} waiting={text(waiting)}\n'


PID = 4242
with tempfile.TemporaryDirectory(prefix='melonx-hot-spots-') as directory:
    log = Path(directory) / 'MeloNX-performance.log'
    with open(log, 'w') as out:
        out.write('[MeloNX:perf] t=41 fps=19.0/52.0/40 context={"pid":"4242"}\n')
        out.write(header(1, 'slow', 42, 19.5, PID))
        out.write(thread(1, 'GPU.MainThread', 47, 240, 60,
                         [('MeloNXCore+0x1010', 100), ('MeloNXCore+0x1020', 40), ('MeloNXCore+0x2008', 50), ('libsystem_platform.dylib+0x400', 30), ('jit', 20)],
                         [('MeloNXCore+0x3004', 240), ('MeloNXCore+0x3010', 200), ('MeloNXCore+0x1010', 100), ('MeloNXCore+0x2008', 50), ('jit', 20)],
                         [('MeloNXCore+0x4000', 60), ('MeloNXCore+0x3004', 60)]))
        out.write(thread(1, '<MainThread>', 31, 150, 150, [('jit', 120), ('MeloNXCore+0x2008', 30)], [('jit', 150), ('MeloNXCore+0x2008', 30)], []))
        out.write('[MeloNX:perf] t=43 fps=19.0/52.0/40 context={"pid":"4242"}\n')
        out.write(header(1, 'slow', 50, 15.0, PID + 1))
        out.write(thread(1, 'Other.Process', 47, 300, 0, [('MeloNXCore+0x9999', 300)], [('MeloNXCore+0x9999', 300)], []))
        out.write(header(2, 'base', 90, 30.0, PID))
        out.write(thread(2, 'GPU.MainThread', 47, 90, 210, [('MeloNXCore+0x1010', 60)], [('MeloNXCore+0x3004', 90)], [('MeloNXCore+0x4000', 210)], missed=0))
        out.write(thread(2, 'gone', 31, 0, 0, [], [], [], missed=300))
    symbols = Path(directory) / 'Ryujinx.Library.symbols.txt.gz'
    with gzip.open(symbols, 'wt') as out:
        out.write('0000000000000040 a CurrentEntry\n0000000000001000 t _CommitBindings\n0000000000002000 t _UpdateState\n'
                  '0000000000003000 t _Dispatch\n0000000000004000 t _WaitForCommands\n0000000000005000 d _data\n')

    # A thin arm64 Mach-O image with one segment at address 0x1000: `bl` to 0x1000 (_CommitBindings) before the return
    # address 0x3004, an indirect call (blr x8) before 0x3010.
    code = bytearray(0x4000)
    struct.pack_into('<I', code, 0x3000 - 0x1000, 0x94000000 | (((0x1000 - 0x3000) // 4) & 0x3FFFFFF))
    struct.pack_into('<I', code, 0x300C - 0x1000, 0xD63F0100)
    segment = struct.pack('<II16sQQQQIIII', 0x19, 72, b'__TEXT', 0x1000, len(code), 4096, len(code), 5, 5, 0, 0)
    binary = Path(directory) / 'Ryujinx.Library.dylib'
    binary.write_bytes((struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 0, 6, 1, len(segment), 0, 0) + segment).ljust(4096, b'\0') + bytes(code))

    named = subprocess.run([sys.executable, str(TOOL), str(log), '--pid', str(PID), '--symbols', str(symbols), '--json'], capture_output=True, text=True)
    check(named.returncode == 0, named.stderr[-400:])
    report = json.loads(named.stdout)
    check(report['named'] is True and [(p['number'], p['kind'], p['second'], p['fps']) for p in report['profiles']] == [(1, 'slow', 42, 19.5), (2, 'base', 90, 30.0)],
          'the two profiles of this PID, in order; the other PID left out: ' + named.stdout[:300])
    gpu, main = report['profiles'][0]['threads']
    check(gpu['name'] == 'GPU.MainThread' and gpu['priority'] == 47 and gpu['run'] == 240 and gpu['wait'] == 60 and gpu['runningPercent'] == 80.0,
          'running share of the samples: ' + json.dumps(gpu))
    check(gpu['selfByImage'] == [['MeloNXCore', 190], ['libsystem_platform.dylib', 30], ['jit', 20]] and gpu['selfListed'] == 240, 'self by image')
    check(gpu['selfFunctions'] == [['_CommitBindings', 140], ['_UpdateState', 50]], 'two places of one function add up: ' + json.dumps(gpu['selfFunctions']))
    check(gpu['stackFunctions'] == [['_Dispatch', 240], ['_CommitBindings', 100], ['_UpdateState', 50]],
          'two call sites of one function add up, never above the running samples: ' + json.dumps(gpu['stackFunctions']))
    check(gpu['waitingPlaces'] == [['_Dispatch', 60], ['_WaitForCommands', 60]], 'what the thread waits in: ' + json.dumps(gpu['waitingPlaces']))
    check(main['selfByImage'] == [['jit', 120], ['MeloNXCore', 30]] and main['runningPercent'] == 50.0 and main['selfFunctions'] == [['_UpdateState', 30]],
          'a guest thread: translated code and the engine: ' + json.dumps(main))
    check(gpu['calls'] is None, 'without the binary no callee is named')
    with_binary = json.loads(subprocess.run([sys.executable, str(TOOL), str(log), '--pid', str(PID), '--symbols', str(symbols), '--binary', str(binary), '--json'],
                                            capture_output=True, text=True).stdout)
    check(with_binary['profiles'][0]['threads'][0]['calls'] ==
          [['_Dispatch', '_CommitBindings', 240], ['_Dispatch', 'an indirect call', 200], ['_CommitBindings', 'an indirect call', 100],
           ['_UpdateState', 'an indirect call', 50]],
          'with the binary a direct call names its callee: ' + json.dumps(with_binary['profiles'][0]['threads'][0]['calls']))
    gone = report['profiles'][1]['threads'][1]
    check(gone['run'] == 0 and gone['missed'] == 300 and gone['runningPercent'] is None and gone['selfFunctions'] == [], 'a thread that ended: nothing invented')

    plain = json.loads(subprocess.run([sys.executable, str(TOOL), str(log), '--pid', str(PID), '--json'], capture_output=True, text=True).stdout)
    check(plain['named'] is False and plain['profiles'][0]['threads'][0]['selfFunctions'] == [['MeloNXCore+0x1010', 100], ['MeloNXCore+0x2008', 50], ['MeloNXCore+0x1020', 40]],
          'without a map the places are listed as written')
    text = subprocess.run([sys.executable, str(TOOL), str(log), '--pid', str(PID), '--symbols', str(symbols)], capture_output=True, text=True)
    check(text.returncode == 0 and '#1 slow at t=42 (19.5 FPS): 300 samples in 3040 ms' in text.stdout and
          'GPU.MainThread (priority 47): running 240 of 300 samples (80.0 %)' in text.stdout and
          'self, by image: MeloNXCore 190, libsystem_platform.dylib 30, jit 20' in text.stdout and ' 140  _CommitBindings' in text.stdout and
          'waiting in: _Dispatch 60; _WaitForCommands 60' in text.stdout and 'gone (priority 31): running 0 of 0 samples, 300 reads missed' in text.stdout,
          'the text report: ' + text.stdout[-1200:])
    other = subprocess.run([sys.executable, str(TOOL), str(log), '--pid', '1'], capture_output=True, text=True)
    check(other.returncode != 0 and 'no [MeloNX:hot] profile for pid 1' in other.stderr, 'a PID without a profile is said')

print(json.dumps(dict(result='passed', checks=checks)))
