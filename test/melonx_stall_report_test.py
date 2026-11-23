#!/usr/bin/env python3
"""tools/melonx/stall_report.py: the [MeloNX:stall] records of one session, the engine's threads named with a symbol map.

A synthetic journal: two sessions whose records share labels (#1.0, #F1.0), rows without a context after each header,
an end line per stall, and a Core symbol map of three functions. Nothing is read from a device.
"""
import gzip
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/melonx/stall_report.py'
checks = 0


def check(condition, message):
    global checks
    assert condition, message
    checks += 1


def context(pid):
    return ' context=' + json.dumps({'build': '829', 'pid': str(pid), 'titleId': '0100f7e00c70e000'}, separators=(',', ':'))


with tempfile.TemporaryDirectory(prefix='melonx-stall-report-') as directory:
    work = Path(directory)
    symbols = work / 'Ryujinx.Library.symbols.txt.gz'
    with gzip.open(symbols, 'wt') as stream:
        stream.write('0000000000001000 T _S_P_CoreLib_System_Threading_Monitor__Wait\n'
                     '0000000000002000 T _Ryujinx_Graphics_GAL_Ryujinx_Graphics_GAL_Multithreading_Resources_ProgramQueue__WaitForProgram\n'
                     '0000000000003000 T _Ryujinx_Graphics_GAL_Ryujinx_Graphics_GAL_Multithreading_ThreadedRenderer__RenderLoop\n'
                     '0000000000004000 d _someData\n')
    render = 't11 NeoStation.MeloNX.Render W s0 p47/47 c+0.0 pc=libsystem_kernel.dylib+0x65f8 lr=libsystem_pthread.dylib+0x1dd0 ' \
             'bt=MeloNXCore+0x1010,MeloNXCore+0x2040,MeloNXCore+0x3008,MeloNXMoltenVKStandalone+0x90d84'
    gpu = 't12 GPU.MainThread W s0 p47/47 c+0.1 pc=libsystem_kernel.dylib+0x65f8 lr=libsystem_pthread.dylib+0x1dd0 bt=MeloNXCore+0x1004'
    other = 't13 AudioRendererManager.Wor W s0 p47/47 c+0.0 pc=libsystem_kernel.dylib+0x65f8 lr=libsystem_pthread.dylib+0x1dd0 bt=MeloNXCore+0x1004'
    lines = [
        # Session 100: a call stall, then a frame stall of two stages and its end.
        '[MeloNX:stall] #1.0 fps in flight 320 ms, 3 threads' + context(100),
        '[MeloNX:stall] #1.0 t21 NeoStation.MeloNX.Render R s0 p47/47 c5.0 pc=MeloNXCore+0x3010 lr=MeloNXCore+0x3004',
        '[MeloNX:stall] #1 end: fps returned after 410.0 ms' + context(100),
        '[MeloNX:perf] t=23 fps=0.0/0.0/100' + context(100),
        '[MeloNX:stall] #F1.0 no frame for 2010 ms, FIFO 100 %, 3 threads' + context(100),
        '[MeloNX:stall] #F1.0 ' + render, '[MeloNX:stall] #F1.0 ' + gpu, '[MeloNX:stall] #F1.0 ' + other,
        '[MeloNX:stall] #F1.1 no frame for 5020 ms, FIFO 100 %, 3 threads' + context(100),
        '[MeloNX:stall] #F1.1 ' + render.replace('c+0.0', 'c+0.2'),
        # Session 200, interleaved after: the same labels must not mix with session 100's.
        '[MeloNX:stall] #F1.0 no frame for 2005 ms, FIFO 0 %, 1 threads' + context(200),
        '[MeloNX:stall] #F1.0 t31 NeoStation.MeloNX.Render W s0 p47/47 c1.0 pc=libsystem_kernel.dylib+0x65f8 lr=x+0x1 bt=MeloNXCore+0x2004',
        '[MeloNX:stall] #F1 end: paused after 3001.0 ms' + context(200),
        '[MeloNX:stall] #F1 end: a frame again after 26000.5 ms' + context(100),
    ]
    journal = work / 'MeloNX-performance.log'
    journal.write_text('\n'.join(lines) + '\n')

    def run(*arguments):
        result = subprocess.run([sys.executable, '-I', str(TOOL), str(journal), *arguments], capture_output=True, text=True, timeout=60)
        check(result.returncode == 0, result)
        return result.stdout

    report = json.loads(run('--pid', '100', '--symbols', str(symbols), '--json'))
    check(report['named'] and [record['label'] for record in report['records']] == ['#1.0', '#F1.0', '#F1.1'], report)
    call, first, second = report['records']
    check(call['end'] == 'end: fps returned after 410.0 ms' and call['header'] == 'fps in flight 320 ms, 3 threads', call)
    # A stall's end goes with its last record.
    check(first['header'] == 'no frame for 2010 ms, FIFO 100 %, 3 threads' and first['end'] is None and
          second['end'] == 'end: a frame again after 26000.5 ms', (first, second))
    # The engine's threads by default (the audio thread is left out); Core addresses named, others kept.
    check([thread['name'] for thread in first['threads']] == ['NeoStation.MeloNX.Render', 'GPU.MainThread'], first['threads'])
    check(first['threads'][0]['frames'] == [
        'S_P_CoreLib_System_Threading_Monitor__Wait',
        'Ryujinx_Graphics_GAL_Ryujinx_Graphics_GAL_Multithreading_Resources_ProgramQueue__WaitForProgram',
        'Ryujinx_Graphics_GAL_Ryujinx_Graphics_GAL_Multithreading_ThreadedRenderer__RenderLoop',
        'MeloNXMoltenVKStandalone+0x90d84'], first['threads'][0])
    check(first['threads'][0]['pc'] == 'libsystem_kernel.dylib+0x65f8' and first['threads'][0]['state'] == 'W' and
          second['threads'][0]['cpu'] == '+0.2', (first, second))
    check(call['threads'][0]['pc'] == 'Ryujinx_Graphics_GAL_Ryujinx_Graphics_GAL_Multithreading_ThreadedRenderer__RenderLoop', call)

    other_session = json.loads(run('--pid', '200', '--json'))
    check(not other_session['named'] and [record['label'] for record in other_session['records']] == ['#F1.0'] and
          other_session['records'][0]['end'] == 'end: paused after 3001.0 ms' and
          other_session['records'][0]['threads'][0]['frames'] == ['MeloNXCore+0x2004'], other_session)

    every = json.loads(run('--pid', '100', '--all', '--json'))
    check([thread['name'] for thread in every['records'][1]['threads']] ==
          ['NeoStation.MeloNX.Render', 'GPU.MainThread', 'AudioRendererManager.Wor'], every)
    chosen = json.loads(run('--pid', '100', '--thread', 'AudioRendererManager.Worker', '--json'))
    check([thread['name'] for thread in chosen['records'][1]['threads']] == ['AudioRendererManager.Wor'], chosen)

    text = run('--pid', '100', '--symbols', str(symbols))
    check('#F1.1 no frame for 5020 ms, FIFO 100 %, 3 threads  [end: a frame again after 26000.5 ms]' in text and
          '      Ryujinx_Graphics_GAL_Ryujinx_Graphics_GAL_Multithreading_Resources_ProgramQueue__WaitForProgram' in text, text)
    check(run('--pid', '300').strip() == 'no stall record for pid 300', 'an absent session')

print(f'PASS {checks} stall report checks')
