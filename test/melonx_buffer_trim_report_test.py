#!/usr/bin/env python3
"""tools/melonx/buffer_trim_report.py on synthetic journals (no device log is used or stored).

A stderr capture with six 5 s render-thread windows, two trims and another PID's lines; an engine journal (two files,
one window repeated in both) with windows and bufferCache coldTrim records. The report must count each window once,
class it by the trims or records falling inside it, read CreateBufferAccess and BufferDispose only from the first
command list (absent means 0), and keep the two sources on their own clocks.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/melonx/buffer_trim_report.py'
checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def stamp(second):
    return '2026-11-10 23:%02d:%02d.500' % (second // 60, second % 60)


def work(created, disposed, busy=2000.0):
    top = ['DrawIndexed 80000 700.0']
    if created:
        top.append('CreateBufferAccess %d %.1f' % created)
    if disposed:
        top.append('BufferDispose %d %.1f' % disposed)
    top.append('SetVertexBuffers 50000 60.0')
    # The second list ("own ms") must not be read as commands: its entries have four fields, and one is named like a command.
    return ('Gpu LogRenderWork: Render thread commands over 5000.0 ms: busy %.1f ms; top (calls, ms): %s; GPU thread sync waits 60 calls '
            '300.0 ms (invoked commands themselves 0.0 ms, the rest queued ahead); top (calls, ms, own ms): Action 60 300.0 0.0; '
            'CreateBufferAccess 9 9.0 9.0;' % (busy, '; '.join(top)))


def stderr_line(pid, second, level, thread, text):
    context = json.dumps(dict(build='731', pid=str(pid)), separators=(',', ':'))
    return '[MeloNX:stderr] %s Runner[%d:777] 00:00:%02d.000 |%s| %s %s context=%s\n' % (stamp(second), pid, second % 60, level, thread, text, context)


def journal_line(pid, second, stage, status, diagnostic, sequence):
    record = dict(timestamp='2026-11-10T22:%02d:%02d.5000000Z' % (second // 60, second % 60), pid=pid, sequence=sequence, stage=stage,
                  status=status, nativeStatus=0, diagnostic=diagnostic)
    return '[MeloNX:core] ' + json.dumps(record) + '\n'


PID = 4242
with tempfile.TemporaryDirectory(prefix='melonx-buffer-trim-report-') as directory:
    directory = Path(directory)
    capture = directory / 'MeloNX-stderr.log'
    with open(capture, 'w') as out:
        rows = [(5, (200, 15.0), None), (10, (4500, 320.0), (4700, 85.0)), (15, None, None), (20, (3300, 190.0), None), (25, (400, 30.0), None),
                (30, (1700, 120.0), None)]
        for second, created, disposed in rows:
            out.write(stderr_line(PID, second, 'W', 'NeoStation.MeloNX.Render', work(created, disposed)))
            out.write(stderr_line(PID + 1, second, 'W', 'NeoStation.MeloNX.Render', work((9999, 999.0), (9999, 99.0))))
        out.write(stderr_line(PID, 7, 'I', 'GPU.MainThread', 'Gpu TrimCaches: Host reported Critical memory pressure, 1376 MiB available, device 5% '
                                                             'available, released 63 MiB of GPU caches; device short only: kept 155 MiB of textures'))
        out.write(stderr_line(PID, 17, 'I', 'GPU.MainThread', 'Gpu TrimCaches: Host reported Warning memory pressure, 1641 MiB available, device 7% '
                                                              'available, released 26 MiB of GPU caches; device short only: kept 145 MiB of textures'))
        out.write(stderr_line(PID + 1, 27, 'I', 'GPU.MainThread', 'Gpu TrimCaches: Host reported Critical memory pressure, released 99 MiB of GPU caches'))
        out.write('[MeloNX:stderr] a line that is not an engine line context={}\n')
    cold = ('pass %d: released %d buffers (%d MiB) unused for 60 s of play, left %d MiB above the target in use; cache %d of 554 MiB; '
            'so far %d buffers (%d MiB) in %d passes (adapt_cold_buffer_trim)')
    older, newer = directory / 'MeloNX-core.log.1', directory / 'MeloNX-core.log'
    with open(older, 'w') as out:
        out.write(journal_line(PID, 105, 'gpu', 'engineWarning', work((300, 20.0), None), 1))
        out.write(journal_line(PID, 107, 'bufferCache', 'coldTrim', cold % (1, 0, 0, 25, 100, 0, 0, 1), 2))
        out.write(journal_line(PID, 110, 'gpu', 'engineWarning', work((250, 18.0), None), 3))
    with open(newer, 'w') as out:
        out.write(journal_line(PID, 110, 'gpu', 'engineWarning', work((250, 18.0), None), 3))  # the rotation kept it in both files
        out.write(journal_line(PID, 115, 'gpu', 'engineWarning', work((180, 12.0), None), 4))
        out.write(journal_line(PID, 118, 'bufferCache', 'coldTrim', cold % (9, 40, 12, 3, 88, 40, 12, 9), 5))
        out.write(journal_line(PID, 120, 'gpu', 'engineWarning', work((90, 6.0), None), 6))
        out.write(journal_line(PID + 1, 120, 'gpu', 'engineWarning', work((7777, 77.0), None), 7))
        out.write('[MeloNX:core] not json\n')

    run = subprocess.run([sys.executable, str(TOOL), str(capture), str(older), str(newer), '--pid', str(PID), '--json'], capture_output=True, text=True)
    check(run.returncode == 0, 'the tool runs: ' + run.stderr[-400:])
    report = json.loads(run.stdout)
    capture_report, journal = report['stderr capture'], report['engine journal']
    check([row['created'][0] for row in capture_report['windows']] == [200, 4500, 0, 3300, 400, 1700] and
          [row['disposed'][0] for row in capture_report['windows']] == [0, 4700, 0, 0, 0, 0], 'the first command list alone is read; absent is 0')
    check([row['t'] for row in capture_report['windows']] == [5.0, 10.0, 15.0, 20.0, 25.0, 30.0], 'seconds since the first window\'s start')
    check([row['trims'] for row in capture_report['windows']] == [[], [['C', 63]], [], [['W', 26]], [], []], 'each trim in its window; the other PID ignored')
    check(capture_report['trims'] == 2 and capture_report['releasedByTrimsMiB'] == 89, 'two trims, 89 MiB')
    with_trim, without = capture_report['withTrim'], capture_report['withoutTrim']
    check(with_trim['windows'] == 2 and with_trim['createdTotal'] == 7800 and with_trim['createdMedian'] == 3900 and with_trim['createMs'] == 510.0 and
          with_trim['disposedTotal'] == 4700 and with_trim['createdMin'] == 3300 and with_trim['createdMax'] == 4500, 'windows with a trim: ' + json.dumps(with_trim))
    check(without['windows'] == 4 and without['createdTotal'] == 2300 and without['createdMedian'] == 300 and without['disposedTotal'] == 0 and
          without['createdMax'] == 1700, 'windows without: ' + json.dumps(without))
    check([row['created'][0] for row in journal['windows']] == [300, 250, 180, 90], 'the window both journal files hold is counted once')
    check([len(row['cold']) for row in journal['windows']] == [0, 1, 0, 1] and journal['coldTrimRecords'] == 2 and journal['trims'] == 0,
          'coldTrim records class the journal\'s windows')
    check(journal['coldTrimTotals'] == dict(buffers=40, MiB=12, passes=9), 'the totals of the last record')
    check(journal['withTrim']['windows'] == 2 and journal['withoutTrim']['windows'] == 2, 'two windows with a record, two without')

    text = subprocess.run([sys.executable, str(TOOL), str(capture), str(newer), '--pid', str(PID)], capture_output=True, text=True)
    check(text.returncode == 0 and 'windows with a trim:   2' in text.stdout and 'cold:40 buffers' in text.stdout and 'C63' in text.stdout,
          'the text report: ' + text.stdout[-600:])
    none = subprocess.run([sys.executable, str(TOOL), str(capture), '--pid', '1'], capture_output=True, text=True)
    check(none.returncode == 1 and 'No "LogRenderWork' in none.stdout, 'an unknown PID is said so')

print(json.dumps(dict(result='passed', checks=checks)))
