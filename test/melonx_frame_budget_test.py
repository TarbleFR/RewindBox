#!/usr/bin/env python3
"""tools/melonx/frame_budget.py on a synthetic journal (no device log is used or stored).

Ten seconds at 30 FPS, ten at 10 FPS and one line whose host could not tell its ratios, with the vm= and hw= fields of
the bridge (lots 10 and 11), another PID's lines and a paused second: the budget's classes add up to the excess, each
gap is counted once, and the memory activity and CPU service of each window are the journal's figures.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/melonx/frame_budget.py'
checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def line(pid, t, gaps, cpu, vm=None, hw=None, paused=False):
    context = json.dumps(dict(build='731', pid=str(pid)), separators=(',', ':'))
    body = (f't={t} fps={len(gaps):.1f}/33.3/40 mgd=0.2 pres={len(gaps)}/0.0/0/0 long=0/0 gaps={",".join(str(g) for g in gaps)} '
            f'cpu={cpu} Render:40/47 mem=4000/2000/9/0' + (f' vm={vm}' if vm else '') + (f' hw={hw}' if hw else '') + ' th=fair lp=0'
            + (' paused' if paused else ''))
    return f'[MeloNX:perf] {body} context={context}\n'


PID = 4242
with tempfile.TemporaryDirectory(prefix='melonx-frame-budget-') as directory:
    log = Path(directory) / 'MeloNX-performance.log'
    with open(log, 'w') as out:
        for t in range(1, 11):
            out.write(line(PID, t, [33] * 30, 250, vm='4/1000/5000/2', hw='3.0/2.00/60/10'))
            out.write(line(PID + 1, t, [500] * 2, 600, vm='900/900000/1/1', hw='9.9/9.99/99/99'))
        for t in range(11, 21):
            out.write(line(PID, t, [100] * 10, 300, vm='40/30000/90000/5', hw='2.0/1.00/30/50'))
        out.write(line(PID, 21, [33], 100, vm='-/-/10/0', hw='0.0/-/-/5'))
        out.write(line(PID, 22, [], 5, vm='1/1/1/1', hw='1.0/1.00/1/1', paused=True))
    run = subprocess.run([sys.executable, str(TOOL), str(log), '--pid', str(PID), '--window', '1-10', '--window', '11-20', '--window', '21-', '--json'],
                         capture_output=True, text=True)
    check(run.returncode == 0, run.stderr[-400:])
    good, slow, odd = json.loads(run.stdout)['windows']
    check(good['frames'] == 300 and good['meanMs'] == 33.3 and good['excessMs'] == 0.0 and good['slowFrames'] == 0 and good['over100'] == 0,
          'ten seconds on target: ' + json.dumps(good))
    check(good['memoryActivity'] == dict(lines=10, compressedMiB=40, decompressedMiB=156, decompressedPagesMedian=1000, decompressedPagesMax=1000, pageIns=20),
          'memory activity of the first window: ' + json.dumps(good['memoryActivity']))
    check(good['cpuService'] == dict(lines=10, clockGHzMedian=3.0, instructionsPerCycleMedian=2.0, performanceCoresPercentMedian=60.0,
                                     readyWithoutACorePercentMedian=10.0, instructionsPerFrameMillions=500),
          'CPU service of the first window: ' + json.dumps(good['cpuService']))
    check(slow['frames'] == 100 and slow['meanMs'] == 100.0 and slow['excessMs'] == 66.7 and slow['slowMs'] == 66.7 and slow['stutterMs'] == 0.0 and
          slow['slowFrames'] == 100 and round(slow['stutterMs'] + slow['slowMs'] + slow['fastMs'], 1) == slow['excessMs'],
          'ten seconds at 10 FPS: every gap is a slow frame, the classes add up: ' + json.dumps(slow))
    check(slow['memoryActivity']['compressedMiB'] == 400 and slow['memoryActivity']['decompressedMiB'] == 4688 and
          slow['memoryActivity']['decompressedPagesMedian'] == 30000 and slow['cpuService']['clockGHzMedian'] == 2.0 and
          slow['cpuService']['performanceCoresPercentMedian'] == 30.0 and slow['cpuService']['instructionsPerFrameMillions'] == 600,
          'the second window\'s own figures: ' + json.dumps(slow))
    check(odd['frames'] == 1 and odd['memoryActivity'] is None and odd['cpuService'] == dict(
        lines=1, clockGHzMedian=0.0, instructionsPerCycleMedian=None, performanceCoresPercentMedian=None, readyWithoutACorePercentMedian=5.0,
        instructionsPerFrameMillions=None), 'a line whose host could not tell: nothing invented; the paused second left out: ' + json.dumps(odd))
    text = subprocess.run([sys.executable, str(TOOL), str(log), '--pid', str(PID), '--window', '1-10'], capture_output=True, text=True)
    check(text.returncode == 0 and 'memory activity (vm=, 10 lines): 40 MiB compressed, 156 MiB decompressed' in text.stdout and
          'CPU service (hw=, 10 lines, medians): clock 3.0 GHz, 2.0 instructions per cycle, 60.0 % on performance cores, 10.0 % ready without a core; '
          'about 500 million instructions per frame' in text.stdout, 'the text report: ' + text.stdout[-700:])
    old = Path(directory) / 'old.log'
    with open(old, 'w') as out:
        for t in range(1, 4):
            out.write(line(PID, t, [33] * 30, 250))
    plain = json.loads(subprocess.run([sys.executable, str(TOOL), str(old), '--pid', str(PID), '--window', '1-', '--json'],
                                      capture_output=True, text=True).stdout)['windows'][0]
    check(plain['frames'] == 90 and plain['memoryActivity'] is None and plain['cpuService'] is None, 'a journal without the fields: no such section')

print(json.dumps(dict(result='passed', checks=checks)))
