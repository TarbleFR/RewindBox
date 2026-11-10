#!/usr/bin/env python3
"""Memory and garbage-collector report of one MeloNX session, over the same seconds as frame_report.py.

    python3 tools/melonx/memory_report.py MeloNX-performance.log MeloNX-core.log --pid 11152 \
        [--launch MeloNX-launch.log] [--from 40 --to 640] [--json session.json]
    python3 tools/melonx/memory_report.py --compare before.json after.json

Reads, for that PID only:
- MeloNX-performance.log per-second lines (t= seconds since the controls were installed): engine FPS, presented
  frames, presentation pauses over 50/100 ms when the build journals them, and mem=footprint/headroom/device %/donors
  (MiB, MiB, % of device RAM available, RamDonor processes);
- MeloNX-core.log: gcEvent lines (kind, pause, compaction, the fellBackFromBackground flag from Core 661 on, and for
  older Cores the equal-index pair a fallback leaves: a fullBlocking line and a stale 'background' line with the same
  index), memoryInventory lines (Core 661 on: managed heap, LOH size/free/occupied, texture and buffer cache bytes);
- with --launch, MeloNX-launch.log host memoryWarning lines.

Like-for-like comparison: every metric is computed over fixed windows that start at the first second with game frames
(t0): load and first scene [t0, t0+60), early play [t0+60, t0+300), later play [t0+300, t0+600), and the chosen
--from/--to seconds. Comparing two builds then compares the same windows of the same scene and duration; --compare
prints both and the difference, and refuses windows that one session does not cover completely.
No path, key or profile is printed; nothing is sent anywhere.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime

WINDOWS = (('load', 0, 60), ('early', 60, 300), ('later', 300, 600))


def stamp_seconds(value: str) -> float:
    value = value.rstrip('Z')
    head, _, fraction = value.partition('.')
    moment = datetime.strptime(head[:19], '%Y-%m-%dT%H:%M:%S')
    return moment.timestamp() + (float('0.' + fraction[:6]) if fraction else 0.0)


def parse_performance(path: str, pid: str):
    marker = f'"pid":"{pid}"'
    seconds, context = [], None
    for line in open(path, encoding='utf-8', errors='replace'):
        if marker not in line or not line.startswith('[MeloNX:perf] t='):
            continue
        body, _, tail = line.partition(' context=')
        stamp = json.loads(tail)
        context = context or stamp
        t = int(re.search(r' t=(\d+)', body).group(1))
        fps = re.search(r' fps=([\d.]+)/', body)
        pres = re.search(r' pres=(\d+)/([\d.]+)/', body)
        long_gaps = re.search(r' long=(\d+)/(\d+)', body)
        mem = re.search(r' mem=(\d+)/(\d+)/(\d+)/(\d+)', body)
        seconds.append(dict(t=t, wall=stamp_seconds(stamp['timestamp']) if stamp.get('timestamp') else None,
                            fps=float(fps.group(1)) if fps else 0.0, presented=int(pres.group(1)) if pres else 0,
                            over50=int(long_gaps.group(1)) if long_gaps else None,
                            over100=int(long_gaps.group(2)) if long_gaps else None,
                            footprint=int(mem.group(1)) if mem else None, headroom=int(mem.group(2)) if mem else None,
                            device=int(mem.group(3)) if mem else None, paused=body.rstrip().endswith(' paused')))
    return seconds, context or {}


def parse_core(path: str, pid: str):
    events, inventory = [], []
    for line in open(path, encoding='utf-8', errors='replace'):
        if not line.startswith('[MeloNX:core] {'):
            continue
        value = json.loads(line.split('] ', 1)[1])
        if str(value.get('pid')) != str(pid):
            continue
        stage = value.get('stage')
        if stage not in ('gcEvent', 'memoryInventory'):
            continue
        try:
            data = json.loads(value.get('diagnostic') or '{}')
        except json.JSONDecodeError:
            continue
        data['_wall'] = stamp_seconds(value['timestamp'])
        data['_status'] = value.get('status')
        (events if stage == 'gcEvent' else inventory).append(data)
    return events, inventory


def parse_launch(path: str, pid: str):
    warnings = []
    for line in open(path, encoding='utf-8', errors='replace'):
        if '"memoryWarning"' not in line or '{' not in line:
            continue
        value = json.loads(line[line.index('{'):])
        if str(value.get('pid')) == str(pid) and value.get('status') == 'memoryWarning':
            warnings.append(stamp_seconds(value['timestamp']))
    return warnings


def fallbacks(events):
    """Indices of background GCs that fell back to blocking: the Core 661 flag, else the equal-index pair."""
    found = {e['index'] for e in events if e.get('fellBackFromBackground') == 1}
    blocking = {e['index'] for e in events if e.get('kind') == 'fullBlocking'}
    found |= {e['index'] for e in events if e.get('kind') == 'background' and e['index'] in blocking}
    return found


def pause_of(event) -> float:
    pauses = event.get('pauseMs') or []
    return float(sum(pauses)) if isinstance(pauses, list) else float(pauses)


def window_metrics(seconds, events, inventory, warnings, first: int, last: int):
    chosen = [s for s in seconds if first <= s['t'] <= last]
    if not chosen:
        return None
    walls = [s['wall'] for s in chosen if s['wall'] is not None]
    begin, end = (min(walls), max(walls) + 1.0) if walls else (None, None)

    def inside(wall):
        return begin is not None and begin <= wall < end

    feet = [s['footprint'] for s in chosen if s['footprint'] is not None]
    window_events = [e for e in events if inside(e['_wall'])]
    pauses = [pause_of(e) for e in window_events if e.get('kind') != 'background' or e.get('concurrent') != 1]
    fell = fallbacks(window_events)
    inv = [i for i in inventory if inside(i['_wall'])]

    def loh_occupied(item):
        if 'lohOccupiedAfterBytes' in item:
            return item['lohOccupiedAfterBytes']
        loh = item.get('loh') or []
        return loh[2] - loh[3] if len(loh) >= 4 else None

    loh = [v for v in (loh_occupied(e) for e in window_events) if v is not None]
    played = [s for s in chosen if not s['paused']]
    return dict(
        seconds=len(chosen), first=chosen[0]['t'], last=chosen[-1]['t'],
        footprintStartMiB=feet[0] if feet else None, footprintEndMiB=feet[-1] if feet else None,
        footprintMaxMiB=max(feet) if feet else None,
        footprintMeanMiB=round(statistics.fmean(feet), 1) if feet else None,
        headroomMinMiB=min((s['headroom'] for s in chosen if s['headroom'] is not None), default=None),
        deviceMinPercent=min((s['device'] for s in chosen if s['device'] is not None), default=None),
        memoryWarnings=sum(1 for w in warnings if inside(w)),
        gcEvents=len(window_events),
        gcBlockingGen2=sum(1 for e in window_events if e.get('kind') == 'fullBlocking'),
        gcFallbacks=len(fell),
        gcPauseMaxMs=round(max(pauses), 1) if pauses else 0.0,
        gcPausesOver50Ms=sum(1 for p in pauses if p > 50), gcPausesOver100Ms=sum(1 for p in pauses if p > 100),
        lohOccupiedMaxMiB=round(max(loh) / 1048576, 1) if loh else None,
        inventoryLines=len(inv),
        fpsMean=round(statistics.fmean(s['fps'] for s in played), 2) if played else None,
        secondsUnder28Fps=sum(1 for s in played if s['fps'] < 28),
        presentationPausesOver50=sum(s['over50'] or 0 for s in chosen) if any(s['over50'] is not None for s in chosen) else None,
        presentationPausesOver100=sum(s['over100'] or 0 for s in chosen) if any(s['over100'] is not None for s in chosen) else None)


def report(args):
    seconds, context = parse_performance(args.performance, args.pid)
    if not seconds:
        raise SystemExit('No per-second line for PID ' + args.pid)
    events, inventory = parse_core(args.core, args.pid)
    warnings = parse_launch(args.launch, args.pid) if args.launch else []
    playing = [s['t'] for s in seconds if s['fps'] > 0]
    t0 = min(playing) if playing else min(s['t'] for s in seconds)
    tmax = max(s['t'] for s in seconds)
    out = dict(pid=args.pid, build=context.get('build'), coreSource=(context.get('coreSource') or '')[:12],
               titleId=context.get('titleId'), firstGameSecond=t0, lastSecond=tmax, windows={})
    for name, start, stop in WINDOWS:
        if t0 + stop - 1 <= tmax:
            out['windows'][name] = window_metrics(seconds, events, inventory, warnings, t0 + start, t0 + stop - 1)
    if args.start is not None or args.end is not None:
        first = args.start if args.start is not None else t0
        last = args.end if args.end is not None else tmax
        out['windows']['chosen'] = window_metrics(seconds, events, inventory, warnings, first, last)
    out['session'] = window_metrics(seconds, events, inventory, warnings, min(s['t'] for s in seconds), tmax)
    return out


def print_report(out):
    print(f"Session PID {out['pid']}: build {out['build']}, Core {out['coreSource']}, title {out['titleId']}; "
          f"first game second t={out['firstGameSecond']}, last t={out['lastSecond']}")
    for name, metrics in [*out['windows'].items(), ('session', out['session'])]:
        if metrics is None:
            continue
        print(f"  {name} (t={metrics['first']}..{metrics['last']}, {metrics['seconds']} s): "
              + ', '.join(f'{k} {v}' for k, v in metrics.items() if k not in ('first', 'last', 'seconds')))


def compare(before_path, after_path):
    before, after = json.load(open(before_path)), json.load(open(after_path))
    print(f"before: build {before['build']} pid {before['pid']} title {before['titleId']}; "
          f"after: build {after['build']} pid {after['pid']} title {after['titleId']}")
    if before.get('titleId') != after.get('titleId'):
        print('  WARNING: different titles, not a like-for-like comparison')
    for name, _, _ in WINDOWS:
        a, b = before['windows'].get(name), after['windows'].get(name)
        if not a or not b:
            print(f'  {name}: not covered completely by both sessions, not compared')
            continue
        parts = []
        for key, value in a.items():
            other = b.get(key)
            if isinstance(value, (int, float)) and isinstance(other, (int, float)) and key not in ('first', 'last'):
                parts.append(f'{key} {value} -> {other} ({other - value:+.1f})')
        print(f'  {name}: ' + '; '.join(parts))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('performance', nargs='?')
    parser.add_argument('core', nargs='?')
    parser.add_argument('--pid')
    parser.add_argument('--launch', help='MeloNX-launch.log, for host memoryWarning lines')
    parser.add_argument('--from', dest='start', type=int, default=None, help='first second (t=) of the chosen window')
    parser.add_argument('--to', dest='end', type=int, default=None, help='last second (t=) of the chosen window')
    parser.add_argument('--json', help='write the metrics to this file (for --compare)')
    parser.add_argument('--compare', nargs=2, metavar=('BEFORE', 'AFTER'))
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare)
        return
    if not (args.performance and args.core and args.pid):
        parser.error('performance log, core log and --pid are required')
    out = report(args)
    print_report(out)
    if args.json:
        with open(args.json, 'w') as handle:
            json.dump(out, handle, indent=1)


if __name__ == '__main__':
    main()
