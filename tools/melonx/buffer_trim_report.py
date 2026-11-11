#!/usr/bin/env python3
"""Buffer creations and disposals on the render thread against the GPU cache trims of one MeloNX session.

    python3 tools/melonx/buffer_trim_report.py MeloNX-stderr.log [MeloNX-core.log MeloNX-core.log.1] --pid 49375 [--json]

Reads, for that PID:
- the 5 s "LogRenderWork: Render thread commands over" lines (stderr capture, or the engine journal's engineWarning
  records): CreateBufferAccess and BufferDispose when they are among the eight commands listed (absent means fewer
  than the eighth, counted 0);
- the trims: "TrimCaches: Host reported <level> memory pressure ... released N MiB" (Info lines, stderr capture only);
- the "bufferCache coldTrim" records of the engine journal (Core 731 and later).
Each source is reported on its own clock (seconds since its first window): the stderr capture carries the trims, the
journal the coldTrim records. A window is "with a trim" when a trim line or a coldTrim record falls inside it.
Figures are the journal's own; a window's command times include whatever suspended the thread meanwhile (a collection).
IPA 724 (Hogwarts Legacy, pid 49375, before Core 731): windows with a trim created 1 400 to 7 026 buffers, the others 0
to 870.
"""
import argparse
import datetime
import json
import re
import statistics
import sys

STDERR = re.compile(r'\[MeloNX:stderr\] (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) Runner\[(\d+):\d+\] \S+ \|.\| (.*?)(?: context=\{.*)?$')
WINDOW = re.compile(r'LogRenderWork: Render thread commands over ([\d.]+) ms: busy ([\d.]+) ms; top \(calls, ms\): (.*)')
TRIM = re.compile(r'TrimCaches: Host reported (\w+) memory pressure.*?released (\d+) MiB')
COLD = re.compile(r'pass (\d+): released (\d+) buffers \((\d+) MiB\).*?left (\d+) MiB above the target in use; cache (\d+) of (\d+) MiB; '
                  r'so far (\d+) buffers \((\d+) MiB\) in (\d+) passes')


def commands(top):
    found = {}
    for entry in top.split('; GPU thread sync waits')[0].split('; '):
        parts = entry.strip().rstrip(';').split(' ')
        if len(parts) == 3 and parts[1].isdigit():
            found[parts[0]] = (int(parts[1]), float(parts[2]))
    return found


def read(paths, pid):
    sources = {'stderr capture': dict(windows=[], trims=[], cold=[]), 'engine journal': dict(windows=[], trims=[], cold=[])}
    for path in paths:
        with open(path, encoding='utf-8', errors='replace') as stream:
            for line in stream:
                if line.startswith('[MeloNX:stderr] '):
                    match = STDERR.match(line.rstrip('\n'))
                    if not match or match.group(2) != str(pid):
                        continue
                    when = datetime.datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S.%f').timestamp()
                    body, source = match.group(3), sources['stderr capture']
                elif line.startswith('[MeloNX:core] '):
                    try:
                        record = json.loads(line[len('[MeloNX:core] '):])
                    except ValueError:
                        continue
                    if str(record.get('pid')) != str(pid):
                        continue
                    stamp = record.get('timestamp', '')[:26].rstrip('Z')
                    try:
                        when = datetime.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S.%f').timestamp()
                    except ValueError:
                        continue
                    body, source = record.get('diagnostic', ''), sources['engine journal']
                    if record.get('stage') == 'bufferCache' and record.get('status') == 'coldTrim':
                        cold = COLD.search(body)
                        if cold:
                            source['cold'].append((when, [int(value) for value in cold.groups()]))
                        continue
                else:
                    continue
                window = WINDOW.search(body)
                if window:
                    top = commands(window.group(3))
                    source['windows'].append(dict(end=when, seconds=float(window.group(1)) / 1000, busy=float(window.group(2)),
                                                  created=top.get('CreateBufferAccess', (0, 0.0)), disposed=top.get('BufferDispose', (0, 0.0))))
                    continue
                trim = TRIM.search(body)
                if trim:
                    source['trims'].append((when, trim.group(1)[0], int(trim.group(2))))
    return sources


def summarize(rows):
    if not rows:
        return None
    created = [row['created'][0] for row in rows]
    return dict(windows=len(rows), createdMedian=statistics.median(created), createdMin=min(created), createdMax=max(created),
                createdTotal=sum(created), createMs=round(sum(row['created'][1] for row in rows), 1),
                disposedTotal=sum(row['disposed'][0] for row in rows), disposeMs=round(sum(row['disposed'][1] for row in rows), 1),
                seconds=round(sum(row['seconds'] for row in rows), 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('logs', nargs='+')
    parser.add_argument('--pid', required=True)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    result = {}
    for name, source in read(args.logs, args.pid).items():
        windows = sorted(source['windows'], key=lambda row: row['end'])
        if not windows:
            continue
        # A window listed twice (the stderr capture and a rotated journal) is counted once.
        unique, seen = [], set()
        for row in windows:
            key = (round(row['end'], 1), row['busy'])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        origin = unique[0]['end'] - unique[0]['seconds']
        rows = []
        for row in unique:
            start = row['end'] - row['seconds']
            trims = [(level, released) for when, level, released in source['trims'] if start <= when < row['end']]
            cold = [values for when, values in source['cold'] if start <= when < row['end']]
            rows.append(dict(row, t=round(row['end'] - origin, 1), trims=trims, cold=cold))
        with_trim = [row for row in rows if row['trims'] or row['cold']]
        without = [row for row in rows if not row['trims'] and not row['cold']]
        last_cold = max(source['cold'], key=lambda item: item[1][8])[1] if source['cold'] else None
        result[name] = dict(windows=rows, withTrim=summarize(with_trim), withoutTrim=summarize(without),
                            trims=len(source['trims']), releasedByTrimsMiB=sum(released for _, _, released in source['trims']),
                            coldTrimRecords=len(source['cold']),
                            coldTrimTotals=dict(buffers=last_cold[6], MiB=last_cold[7], passes=last_cold[8]) if last_cold else None)
    if args.json:
        print(json.dumps(result, indent=1))
        return 0 if result else 1
    if not result:
        print('No "LogRenderWork: Render thread commands" window for PID %s in these files.' % args.pid)
        return 1
    for name, data in result.items():
        print('%s: %d windows, %d trim lines (%d MiB "released"), %d coldTrim records%s' % (
            name, len(data['windows']), data['trims'], data['releasedByTrimsMiB'], data['coldTrimRecords'],
            (' (so far %(buffers)d buffers, %(MiB)d MiB in %(passes)d passes)' % data['coldTrimTotals']) if data['coldTrimTotals'] else ''))
        print('  t(s)   busy ms  created (calls, ms)  disposed (calls, ms)  trims in the window')
        for row in data['windows']:
            marks = ' '.join('%s%d' % trim for trim in row['trims'])
            if row['cold']:
                marks += ' cold:' + ','.join('%d buffers' % values[1] for values in row['cold'])
            print('  %6.1f  %7.0f  %6d %8.1f     %6d %8.1f     %s' % (row['t'], row['busy'], row['created'][0], row['created'][1],
                                                                  row['disposed'][0], row['disposed'][1], marks))
        for label, key in (('with a trim', 'withTrim'), ('without', 'withoutTrim')):
            summary = data[key]
            if summary:
                print('  windows %-11s: %3d (%.0f s); buffers created per window median %.0f, %d to %d; created %d in %.0f ms, disposed %d in %.0f ms' % (
                    label, summary['windows'], summary['seconds'], summary['createdMedian'], summary['createdMin'], summary['createdMax'],
                    summary['createdTotal'], summary['createMs'], summary['disposedTotal'], summary['disposeMs']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
