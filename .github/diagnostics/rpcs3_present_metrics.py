#!/usr/bin/env python3
"""Presentation metrics of one RPCS3 path, computed from individual guest presentations.

The Core counts every guest flip interval of a 5 s window in a histogram
(COREPROF FRAMEPROF527 histogram_upper_us: 1 ms bins up to 128 ms, 8 ms bins
up to about 1.1 s, then one overflow bin). Summing those histograms over the
windows of a path gives, without averaging window percentiles:

  intervals, total time, FPS over the path, median FPS (1000 / median interval),
  p95 and p99 of the intervals, intervals over 50 ms and over 100 ms (exact:
  the 1 ms bins split at 50 and 100 ms), and the longest window maximum.

Percentiles are reported as the upper bound of their bin (1 ms resolution
below 128 ms). Window boundaries are approximate (a few ms), so a path is the
set of whole windows whose end time falls inside [--from, --to].

Sources, read with python3 -I and never executed:
  * RPCS3-diagnostic*.log / RPCS3-performance*.log: COREPROF FRAMEPROF527 lines;
  * RPCS3-timeline*.log (Build 613+): frame_ms.histogram_upper_us.
Rows are deduplicated by (pid, session, window).

Usage:
  python3 -I .github/diagnostics/rpcs3_present_metrics.py LOG... --title BLES01717 [--session 13] \\
      [--from 10:37:24 --to 10:38:24] [--date 2026-11-02] [--windows] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

TOKEN = re.compile(r'(\w+)=([^\s"]+)')
FINE_BINS = 128


def bin_upper_us(bin_index: int) -> int:
    if bin_index < FINE_BINS:
        return (bin_index + 1) * 1000 - 1
    if bin_index < 255:
        return 128000 + (bin_index - 127) * 8000 - 1
    return 2 ** 32 - 1


def parse_histogram(text: str) -> dict[int, int]:
    result: dict[int, int] = {}
    if not text or text == 'none':
        return result
    for item in text.split(','):
        upper, count = item.split(':')
        result[int(upper)] = result.get(int(upper), 0) + int(count)
    return result


def utc(ts: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc)


def read_rows(paths: list[Path]) -> dict[tuple, dict]:
    rows: dict[tuple, dict] = {}
    titles_by_pid: dict[int, list[tuple[float, str]]] = {}
    pending: list[dict] = []
    for path in paths:
        for line in path.open(encoding='utf-8', errors='replace'):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            ts, pid = obj.get('timestamp'), obj.get('pid')
            if ts is None:
                continue
            frame = obj.get('frame_ms')
            if isinstance(frame, dict) and obj.get('session') is not None:
                key = (pid, obj['session'], obj.get('window'))
                hist = frame.get('histogram_upper_us')
                row = {'ts': ts, 'pid': pid, 'session': obj['session'], 'window': obj.get('window'),
                       'title': obj.get('title'), 'phase': frame.get('phase'),
                       'intervals': int(frame.get('intervals', 0)), 'total_ms': float(frame.get('total_interval_ms', 0)),
                       'max_ms': float(frame.get('max_ms', 0)), 'median_ms': float(frame.get('median_ms', 0)),
                       'p95_ms': float(frame.get('p95_ms', 0)), 'p99_ms': float(frame.get('p99_ms', 0)),
                       'over50': int(frame.get('over50ms', 0)), 'over100': int(frame.get('over100ms', 0)),
                       'histogram': parse_histogram(hist) if isinstance(hist, str) else None, 'source': 'timeline'}
                old = rows.get(key)
                if old is None or (old['histogram'] is None and row['histogram'] is not None):
                    rows[key] = row
                continue
            message = obj.get('message') or ''
            if 'CONFIG_LAYERS ' in message and 'part=rsx' not in message:
                found = TOKEN.findall(message)
                title = dict(found).get('title')
                if title:
                    titles_by_pid.setdefault(pid, []).append((ts, title))
            if 'COREPROF FRAMEPROF527 ' not in message:
                continue
            tokens = dict(TOKEN.findall(message.split('COREPROF FRAMEPROF527 ', 1)[1]))
            pending.append({'ts': ts, 'pid': pid, 'session': int(tokens.get('session', -1)),
                            'window': int(tokens.get('window', -1)), 'title': None, 'phase': tokens.get('phase'),
                            'intervals': int(tokens.get('intervals', 0)), 'total_ms': float(tokens.get('total_interval_ms', 0)),
                            'max_ms': float(tokens.get('max_ms', 0)), 'median_ms': float(tokens.get('median_ms', 0)),
                            'p95_ms': float(tokens.get('p95_ms', 0)), 'p99_ms': float(tokens.get('p99_ms', 0)),
                            'over50': int(tokens.get('over50ms', 0)), 'over100': int(tokens.get('over100ms', 0)),
                            'histogram': parse_histogram(tokens.get('histogram_upper_us', 'none')), 'source': 'frameprof527'})
    for row in pending:
        # The latest boot of that process before the window names the title.
        candidates = [title for ts, title in sorted(titles_by_pid.get(row['pid'], [])) if ts <= row['ts']]
        row['title'] = candidates[-1] if candidates else None
        key = (row['pid'], row['session'], row['window'])
        old = rows.get(key)
        if old is None or old['histogram'] is None:
            if old is not None and old.get('title'):
                row['title'] = old['title']
            rows[key] = row
    return rows


def percentile_upper_ms(hist: dict[int, int], total: int, fraction: float) -> float:
    rank = max(1, -(-int(total * fraction * 1_000_000) // 1_000_000)) if total else 0
    seen = 0
    for upper in sorted(hist):
        seen += hist[upper]
        if seen >= rank:
            return (upper + 1) / 1000.0
    return 0.0


def histogram_complete(row: dict) -> bool:
    # A histogram whose counts do not add up to the window's intervals was cut
    # or damaged on the way: it is not used as presentation data.
    return row['histogram'] is not None and sum(row['histogram'].values()) == row['intervals']


def summarize(selected: list[dict]) -> dict:
    exact = all(histogram_complete(row) for row in selected)
    hist: dict[int, int] = {}
    for row in selected if exact else []:
        for upper, count in (row['histogram'] or {}).items():
            hist[upper] = hist.get(upper, 0) + count
    intervals = sum(row['intervals'] for row in selected)
    total_ms = sum(row['total_ms'] for row in selected)
    result = {'windows': len(selected), 'intervals': intervals, 'total_s': round(total_ms / 1000.0, 3),
              'fps_over_path': round(intervals * 1000.0 / total_ms, 2) if total_ms else 0.0,
              'max_ms': max((row['max_ms'] for row in selected), default=0.0),
              'from_individual_presentations': exact}
    if exact and hist:
        counted = sum(hist.values())
        median = percentile_upper_ms(hist, counted, 0.5)
        result.update({'median_interval_ms_upper': median,
                       'median_fps': round(1000.0 / median, 2) if median else 0.0,
                       'p95_ms_upper': percentile_upper_ms(hist, counted, 0.95),
                       'p99_ms_upper': percentile_upper_ms(hist, counted, 0.99),
                       'over_50ms': sum(c for upper, c in hist.items() if upper >= 50999),
                       'over_100ms': sum(c for upper, c in hist.items() if upper >= 100999),
                       'histogram_intervals': counted})
    else:
        # Older timeline rows carry only window summaries: counts are exact,
        # percentiles are not combinable and are left out.
        result.update({'over_50ms': sum(row['over50'] for row in selected),
                       'over_100ms': sum(row['over100'] for row in selected),
                       'note': 'no complete per-presentation histogram in these rows; percentiles omitted'})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('logs', nargs='+', type=Path)
    parser.add_argument('--title')
    parser.add_argument('--pid', type=int)
    parser.add_argument('--session', type=int, action='append')
    parser.add_argument('--from', dest='start', help='UTC HH:MM:SS (window end time)')
    parser.add_argument('--to', dest='end', help='UTC HH:MM:SS (window end time)')
    parser.add_argument('--date', help='UTC YYYY-MM-DD; default: date of the first selected row')
    parser.add_argument('--include-preparation', action='store_true', help='keep windows whose phase is preparation')
    parser.add_argument('--windows', action='store_true', help='print one line per window')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    rows = sorted(read_rows(args.logs).values(), key=lambda row: row['ts'])
    selected = []
    for row in rows:
        if args.title and row['title'] != args.title:
            continue
        if args.pid is not None and row['pid'] != args.pid:
            continue
        if args.session and row['session'] not in args.session:
            continue
        if not args.include_preparation and row['phase'] == 'preparation':
            continue
        when = utc(row['ts'])
        if args.date and when.strftime('%Y-%m-%d') != args.date:
            continue
        clock = when.strftime('%H:%M:%S')
        if args.start and clock < args.start:
            continue
        if args.end and clock > args.end:
            continue
        selected.append(row)
    if not selected:
        raise SystemExit('no window matches')
    summary = summarize(selected)
    summary['span_utc'] = [utc(selected[0]['ts']).isoformat(timespec='seconds'), utc(selected[-1]['ts']).isoformat(timespec='seconds')]
    summary['sessions'] = sorted({(row['pid'], row['session']) for row in selected})
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    if args.windows:
        for row in selected:
            print(f"{utc(row['ts']).strftime('%H:%M:%S')} pid={row['pid']} s={row['session']} w={row['window']} "
                  f"{row['phase']} n={row['intervals']} med={row['median_ms']:.1f} p99={row['p99_ms']:.1f} "
                  f"max={row['max_ms']:.1f} >50={row['over50']} >100={row['over100']} src={row['source']}")
    for key, value in summary.items():
        print(f'{key}: {value}')


if __name__ == '__main__':
    sys.exit(main())
