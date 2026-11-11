#!/usr/bin/env python3
"""Playability verdict of one MeloNX session against the maintainer's criteria (Hogwarts Legacy, 30 FPS at 1x).

    python3 tools/melonx/playability_verdict.py MeloNX-performance.log --pid 44597 [--warmup 60] [--min-minutes 20]
        [--max-footprint 4096] [--json]

Reads the per-second "[MeloNX:perf]" lines of that PID (MeloNX-performance.log) and judges the warm pass: from the
first second with a game frame plus --warmup seconds to the last line, without the paused seconds. Each criterion is
reported with its figure and PASS or FAIL; the exit status is 0 only when all pass:
- game FPS (the engine's distinct game frames per second): median and mean at least 29.5 (a stable 30);
- presentation gaps (gaps=, every interval between two presented frames): p95 at most 40 ms, p99 at most 50 ms, none
  over 1 s, at most 1 gap over 100 ms per 5 minutes;
- memory (mem= footprint/headroom/device %/donors): the maximum footprint at most --max-footprint MiB (4 GiB), its
  slope over the warm pass at most 5 MiB per minute (least squares), the device's available share never at 0 %;
- thermal state (th=): never critical;
- duration: the warm pass at least --min-minutes minutes;
- the session's end summary ("[MeloNX:perf] end:") is present (the journal stopped normally, not a crash or a kill).
The figures are the journal's own; nothing is extrapolated. One session per call; percentiles use the nearest rank.
"""
import argparse
import json
import re
import statistics
import sys


def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, round(q / 100 * (len(ordered) - 1))))
    return ordered[index]


def slope_per_minute(points):
    """Least-squares slope of (second, value) points, per minute."""
    if len(points) < 2:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return 60 * sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def read(path, pid):
    marker = f'"pid":"{pid}"'
    seconds, ended = [], False
    with open(path, encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if not line.startswith('[MeloNX:perf] ') or marker not in line:
                continue
            body = line.split(' context=')[0][len('[MeloNX:perf] '):]
            if body.startswith('end:'):
                ended = True
                continue
            match = re.match(r't=(\d+) ', body)
            if not match:
                continue
            fields = body.split(' ')
            second = dict(t=int(match.group(1)), paused='paused' in fields, fps=None, gaps=[], footprint=None, device=None, thermal=None,
                          cpu=None, vm=None, hw=None, en=None, sw=None, threads=[], pc=None)
            for field in fields:
                if field.startswith('fps=') and field != 'fps=-':
                    second['fps'] = float(field[4:].split('/')[0])
                elif field.startswith('gaps='):
                    second['gaps'] = [int(value) for value in field[5:].split(',') if value]
                elif field.startswith('mem='):
                    parts = field[4:].split('/')
                    if parts[0].isdigit():
                        second['footprint'] = int(parts[0])
                    if len(parts) > 2 and re.fullmatch(r'-?\d+', parts[2]):
                        second['device'] = int(parts[2])
                elif field.startswith('th='):
                    second['thermal'] = field[3:]
                elif field.startswith('cpu=') and field[4:].isdigit():
                    second['cpu'] = int(field[4:])
                elif field.startswith('pc='):
                    # Per cent of each listed thread's CPU time on performance cores, in the order of the cpu= entries.
                    second['pc'] = field[3:].split(',')
                elif '=' not in field and re.fullmatch(r'.+:\d+/-?\d+', field):
                    # A cpu= thread entry: name:per cent of one core/priority.
                    name, _, rest = field.rpartition(':')
                    second['threads'].append((name, int(rest.split('/')[0]), int(rest.split('/')[1])))
                elif field[:3] in ('vm=', 'hw=', 'en=', 'sw='):
                    # Raw parts: vm= MiB compressed/pages decompressed/faults/page-ins, hw= GHz/instructions per
                    # cycle/% on performance cores/% ready without a core; "-" where the journal could not tell.
                    second[field[:2]] = field[3:].split('/')
            seconds.append(second)
    return seconds, ended


def verdict(seconds, ended, warmup=60, min_minutes=20, max_footprint=4096):
    first = next((s['t'] for s in seconds if s['fps'] and s['fps'] > 0), None)
    criteria = []

    def add(name, passed, figure):
        criteria.append(dict(criterion=name, passed=bool(passed), figure=figure))

    if first is None:
        add('a game frame was rendered', False, 'no second with game FPS above 0')
        return criteria, {}
    warm = [s for s in seconds if s['t'] >= first + warmup and not s['paused']]
    if not warm:
        add('a warm pass exists', False, f'no unpaused second after t={first + warmup}')
        return criteria, {}
    rates = [s['fps'] for s in warm if s['fps'] is not None]
    gaps = [gap for s in warm for gap in s['gaps']]
    minutes = len(warm) / 60
    median_fps = statistics.median(rates) if rates else 0.0
    mean_fps = statistics.fmean(rates) if rates else 0.0
    p50, p95, p99 = percentile(gaps, 50), percentile(gaps, 95), percentile(gaps, 99)
    over100 = sum(1 for gap in gaps if gap > 100)
    over1000 = sum(1 for gap in gaps if gap > 1000)
    footprints = [(s['t'], s['footprint']) for s in warm if s['footprint'] is not None]
    devices = [s['device'] for s in warm if s['device'] is not None and s['device'] >= 0]
    thermals = [s['thermal'] for s in warm if s['thermal']]
    slope = slope_per_minute(footprints)
    summary = dict(firstFrameSecond=first, warmFrom=first + warmup, warmSeconds=len(warm), pausedSecondsExcluded=sum(1 for s in seconds if s['paused']),
                   medianFps=round(median_fps, 2), meanFps=round(mean_fps, 2), presentedGaps=len(gaps), p50=p50, p95=p95, p99=p99,
                   maxGap=max(gaps) if gaps else None, gapsOver100=over100, gapsOver1000=over1000,
                   maxFootprint=max(f for _, f in footprints) if footprints else None,
                   footprintSlopePerMinute=round(slope, 2) if slope is not None else None,
                   minDeviceAvailable=min(devices) if devices else None,
                   thermal={state: thermals.count(state) for state in dict.fromkeys(thermals)}, ended=ended)
    add('game FPS median and mean at least 29.5', median_fps >= 29.5 and mean_fps >= 29.5,
        f'median {median_fps:.1f}, mean {mean_fps:.1f} over {len(rates)} s')
    add('frame gaps p95 at most 40 ms', p95 is not None and p95 <= 40, f'p50 {p50}, p95 {p95} ms over {len(gaps)} gaps')
    add('frame gaps p99 at most 50 ms', p99 is not None and p99 <= 50, f'p99 {p99} ms, max {summary["maxGap"]} ms')
    add('no gap over 1 s, at most 1 over 100 ms per 5 minutes', over1000 == 0 and over100 <= max(1, int(minutes / 5)),
        f'{over1000} over 1 s, {over100} over 100 ms in {minutes:.1f} min')
    add(f'footprint at most {max_footprint} MiB', summary['maxFootprint'] is not None and summary['maxFootprint'] <= max_footprint,
        f'max {summary["maxFootprint"]} MiB')
    add('footprint slope at most 5 MiB per minute', slope is not None and slope <= 5, f'{summary["footprintSlopePerMinute"]} MiB/min')
    add('device memory never exhausted (available above 0 %)', not devices or min(devices) > 0, f'min {summary["minDeviceAvailable"]} %')
    add('thermal state never critical', 'critical' not in thermals, ', '.join(f'{k} {v} s' for k, v in summary['thermal'].items()) or 'none')
    add(f'warm pass at least {min_minutes} minutes', minutes >= min_minutes, f'{minutes:.1f} min')
    add('the session ended normally (end summary present)', ended, 'end line present' if ended else 'no end line')
    return criteria, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('performance')
    parser.add_argument('--pid', required=True)
    parser.add_argument('--warmup', type=int, default=60, help='seconds after the first game frame excluded (load, first area)')
    parser.add_argument('--min-minutes', type=float, default=20)
    parser.add_argument('--max-footprint', type=int, default=4096, help='MiB')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    seconds, ended = read(args.performance, args.pid)
    criteria, summary = verdict(seconds, ended, args.warmup, args.min_minutes, args.max_footprint)
    passed = bool(criteria) and all(c['passed'] for c in criteria)
    if args.json:
        print(json.dumps(dict(pid=args.pid, passed=passed, criteria=criteria, summary=summary), indent=1))
    else:
        print(f'Session PID {args.pid}: warm pass from t={summary.get("warmFrom")} for {summary.get("warmSeconds")} s')
        for c in criteria:
            print(f'  {"PASS" if c["passed"] else "FAIL"}  {c["criterion"]}: {c["figure"]}')
        print('PLAYABLE (every criterion met)' if passed else 'NOT PLAYABLE by these criteria')
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
