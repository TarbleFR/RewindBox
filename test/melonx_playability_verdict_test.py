#!/usr/bin/env python3
"""tools/melonx/playability_verdict.py on synthetic sessions (no device log is used or stored).

A 25-minute session at a steady 30 FPS with 33 ms gaps, a flat 3.8 GiB footprint and an end line must pass every
criterion; then one defect at a time must fail exactly its criterion: a median of 25 FPS, gaps whose p95 is 50 ms, a
1.2 s stall, a footprint climbing 10 MiB per minute, a 4.3 GiB footprint, a critical thermal state, a 10-minute pass, a
missing end line. Paused seconds and another PID's lines are ignored; the warm-up seconds are excluded.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/melonx/playability_verdict.py'
checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def line(pid, t, fps, gaps, footprint, device=20, thermal='fair', paused=False):
    context = dict(build='723', console='Switch', pid=str(pid), session='s', titleId='0100f7e00c70e000')
    body = (f't={t} fps={fps:.1f}/33.3/40 mgd=0.2 pres={len(gaps)}/{max(gaps) if gaps else 0}.0/0/0 long=0/0 '
            f'gaps={",".join(str(g) for g in gaps)} cpu=300 mem={footprint}/1500/{device}/0 th={thermal} lp=0' + (' paused' if paused else ''))
    return f'[MeloNX:perf] {body} context={json.dumps(context, separators=(",", ":"))}\n'


def session(path, minutes=25, fps=lambda t: 30.0, gaps=lambda t: [33] * 30, footprint=lambda t: 3900, thermal=lambda t: 'fair', end=True):
    pid = 4242
    with open(path, 'w') as out:
        out.write(f'[MeloNX:perf] begin: every 1.0 s, 6 cores, audio counters available context={json.dumps(dict(pid=str(pid)), separators=(",", ":"))}\n')
        for t in range(1, 30):  # loading: no game frame yet
            out.write(line(pid, t, 0.0, [], 2000))
        for t in range(30, 30 + 60 * minutes):
            paused = 600 <= t < 620
            out.write(line(pid, t, fps(t), gaps(t), footprint(t), thermal=thermal(t), paused=paused))
            out.write(line(pid + 1, t, 5.0, [200] * 5, 6000, thermal='critical'))  # another PID: ignored
        if end:
            out.write(f'[MeloNX:perf] end: 1500 s sampled, 1500 lines; game FPS 30.0 on average while running context={json.dumps(dict(pid=str(pid)), separators=(",", ":"))}\n')
    return pid


def run(path, pid, *extra):
    result = subprocess.run([sys.executable, str(TOOL), str(path), '--pid', str(pid), '--json', *extra], capture_output=True, text=True)
    report = json.loads(result.stdout)
    return result.returncode, report, {c['criterion']: c['passed'] for c in report['criteria']}


with tempfile.TemporaryDirectory(prefix='melonx-verdict-') as directory:
    directory = Path(directory)
    good = directory / 'good.log'
    pid = session(good)
    code, report, passed = run(good, pid)
    check(code == 0 and report['passed'] and all(passed.values()), 'a steady 30 FPS session passes: ' + json.dumps(report['criteria']))
    summary = report['summary']
    check(summary['firstFrameSecond'] == 30 and summary['warmFrom'] == 90 and summary['pausedSecondsExcluded'] == 20 and
          summary['warmSeconds'] == 25 * 60 - 60 - 20, 'warm-up and paused seconds excluded, the other PID ignored: ' + json.dumps(summary))
    check(summary['p95'] == 33 and summary['p99'] == 33 and summary['medianFps'] == 30.0 and summary['footprintSlopePerMinute'] == 0.0,
          'figures of the steady session: ' + json.dumps(summary))

    defects = {
        'game FPS median and mean at least 29.5': dict(fps=lambda t: 25.0),
        'frame gaps p95 at most 40 ms': dict(gaps=lambda t: [33] * 26 + [50] * 4 if t % 2 else [33] * 30),
        'no gap over 1 s, at most 1 over 100 ms per 5 minutes': dict(gaps=lambda t: [1200] if t == 700 else [33] * 30),
        'footprint slope at most 5 MiB per minute': dict(footprint=lambda t: 3000 + t // 6),
        'footprint at most 4096 MiB': dict(footprint=lambda t: 4400),
        'thermal state never critical': dict(thermal=lambda t: 'critical' if t == 900 else 'fair'),
        'warm pass at least 20 minutes': dict(minutes=10),
        'the session ended normally (end summary present)': dict(end=False),
    }
    for criterion, change in defects.items():
        path = directory / (str(len(criterion)) + '.log')
        pid = session(path, **change)
        code, report, passed = run(path, pid)
        failed = sorted(name for name, ok in passed.items() if not ok)
        check(code == 1 and criterion in failed, criterion + ': must fail: ' + json.dumps(report['criteria']))
        expected = {criterion}
        # A 1.2 s gap also moves p99 only when enough of them exist; one gap does not. A 10-minute pass is only short.
        check(set(failed) == expected, criterion + ': only that criterion fails: ' + str(failed))

    code, report, passed = run(good, 9999)
    check(code == 1 and not report['passed'], 'an absent PID is not playable')

print(json.dumps(dict(result='passed', checks=checks)))
