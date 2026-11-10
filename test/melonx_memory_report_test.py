#!/usr/bin/env python3
"""tools/melonx/memory_report.py on a synthetic session (no device log is used or stored).

Builds per-second performance lines, gcEvent lines (an older Core's equal-index fallback pair and a Core 661 flagged
line), a memoryInventory line and a host memoryWarning for one PID plus noise from another PID, then checks the fixed
windows (load, early, later), the fallback detection, the pause counts, the memory metrics and --compare, which must
refuse a window that one session does not cover.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/melonx/memory_report.py'
checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def perf_line(pid, t, fps, footprint, device, second):
    context = dict(build='661', console='Switch', coreSource='abcdef1234567890', pid=str(pid), session='s',
                   timestamp=f'2026-11-05T10:{second // 60:02d}:{second % 60:02d}.000Z', titleId='0100f7e00c70e000')
    return (f'[MeloNX:perf] t={t} fps={fps}/{fps}/0 pres={int(fps)}/40.0/0/0 long=1/0 cpu=100 '
            f'mem={footprint}/{6655 - footprint}/{device}/2 th=nominal lp=0 context={json.dumps(context, separators=(",", ":"))}\n')


def core_line(pid, second, stage, status, diagnostic):
    value = dict(timestamp=f'2026-11-05T10:{second // 60:02d}:{second % 60:02d}.5000000Z', pid=pid, sequence=1,
                 stage=stage, status=status, nativeStatus=0, diagnostic=json.dumps(diagnostic))
    return '[MeloNX:core] ' + json.dumps(value) + '\n'


def gc(kind, index, pause, concurrent=0, **extra):
    return dict(schema=1, kind=kind, index=index, generation=2, concurrent=concurrent, compacted=0, pauseMs=[pause],
                loh=[600 << 20, 200 << 20, 600 << 20, 250 << 20], **extra)


def session(directory, pid, flagged, seconds=700, start_footprint=2500):
    perf, core, launch = [], [], []
    for t in range(1, seconds + 1):
        fps = 0.0 if t < 20 else (30.0 if t % 10 else 20.0)
        perf.append(perf_line(pid, t, fps, start_footprint + t, 10, t))
        perf.append(perf_line(pid + 1, t, 60.0, 9999, 50, t))  # another PID: ignored
    core.append(core_line(pid, 100, 'gcEvent', 'background', gc('background', 10, 1.0, concurrent=1)))
    if flagged:  # Core 661: one flagged blocking line
        core.append(core_line(pid, 200, 'gcEvent', 'fullBlocking', gc('fullBlocking', 20, 120.0, fellBackFromBackground=1)))
    else:  # older Core: the blocking line and a stale background line with the same index
        core.append(core_line(pid, 200, 'gcEvent', 'fullBlocking', gc('fullBlocking', 20, 120.0)))
        core.append(core_line(pid, 200, 'gcEvent', 'background', gc('background', 20, 1.0, concurrent=1)))
    core.append(core_line(pid, 400, 'gcEvent', 'ephemeral', gc('ephemeral', 30, 60.0)))
    core.append(core_line(pid, 410, 'memoryInventory', 'sample', dict(schema=1, footprintBytes=1)))
    core.append(core_line(pid + 1, 400, 'gcEvent', 'fullBlocking', gc('fullBlocking', 5, 900.0)))
    launch.append('[MeloNX:native] ' + json.dumps(dict(diagnostic='memory 1/2/3/2', nativeStatus=0, pid=pid, stage='lifecycle',
                                                       status='memoryWarning', timestamp='2026-11-05T10:05:00Z')) + '\n')
    paths = [directory / f'{pid}-{name}.log' for name in ('performance', 'core', 'launch')]
    for path, lines in zip(paths, (perf, core, launch)):
        path.write_text(''.join(lines))
    return paths


def run(*arguments):
    result = subprocess.run([sys.executable, str(TOOL), *map(str, arguments)], capture_output=True, text=True, check=True)
    return result.stdout


with tempfile.TemporaryDirectory(prefix='melonx-memory-report-') as temporary:
    directory = Path(temporary)
    old = session(directory, 100, flagged=False)
    new = session(directory, 200, flagged=True, start_footprint=2400)
    short = session(directory, 300, flagged=True, seconds=200)
    run(*old[:2], '--pid', 100, '--launch', old[2], '--json', directory / 'old.json')
    run(*new[:2], '--pid', 200, '--launch', new[2], '--json', directory / 'new.json')
    run(*short[:2], '--pid', 300, '--json', directory / 'short.json')
    before = json.loads((directory / 'old.json').read_text())
    after = json.loads((directory / 'new.json').read_text())
    check(before['firstGameSecond'] == 20 and before['build'] == '661' and before['titleId'] == '0100f7e00c70e000',
          'first game second and context')
    load, early, later = (before['windows'][name] for name in ('load', 'early', 'later'))
    check((load['first'], load['last'], early['first'], early['last'], later['first'], later['last']) ==
          (20, 79, 80, 319, 320, 619), 'fixed windows from the first game second')
    check(load['footprintStartMiB'] == 2520 and load['footprintEndMiB'] == 2579 and load['footprintMaxMiB'] == 2579,
          'footprint over the load window')
    check(early['gcFallbacks'] == 1 and early['gcBlockingGen2'] == 1 and early['gcPauseMaxMs'] == 120.0 and
          early['gcPausesOver100Ms'] == 1, 'older Core: the equal-index pair is one fallback; the stale line is no pause')
    check(after['windows']['early']['gcFallbacks'] == 1, 'Core 661: the flagged line is one fallback')
    check(later['gcPausesOver50Ms'] == 1 and later['gcPausesOver100Ms'] == 0 and later['inventoryLines'] == 1,
          'ephemeral pause and inventory line in the later window')
    check(before['session']['memoryWarnings'] == 1 and early['memoryWarnings'] == 1, 'host memoryWarning counted once')
    check(before['session']['gcPauseMaxMs'] == 120.0, 'another PID never counts')
    check(load['lohOccupiedMaxMiB'] is None and early['lohOccupiedMaxMiB'] == 350.0, 'LOH occupied = size - free after')
    check(load['secondsUnder28Fps'] == 6 and load['fpsMean'] == 29.0, 'frame rate over the load window')
    brief = json.loads((directory / 'short.json').read_text())
    check('load' in brief['windows'] and 'early' not in brief['windows'] and 'later' not in brief['windows'],
          'windows a session does not cover completely are absent')
    text = run('--compare', directory / 'old.json', directory / 'new.json')
    check('footprintStartMiB 2520 -> 2420 (-100.0)' in text, 'compare prints the difference over the same window')
    text = run('--compare', directory / 'old.json', directory / 'short.json')
    check('later: not covered completely by both sessions, not compared' in text, 'compare refuses an uncovered window')

print(json.dumps(dict(result='passed', checks=checks)))
