#!/usr/bin/env python3
"""Summarize527 internal journals without inventing matched526 observations.

--phases is an array of {name,start,end,build?,pid?,session?}, with epoch seconds
from the controlled route. Only whole reporting windows inside one phase are
admitted. The four records associate by build/PID/session/window even when log
transport changes their order. Histograms, never reported percentiles, merge.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

MARKER = re.compile(r'\b(FRAMEPROF527|WAITPROF527|MEMPROF527|JITPUB527)\s+')
FIELD = re.compile(r'(\w+)=([^\s]+)')
WAITS = {
    'pipeline_queue': 'queued asynchronous pipeline job; not a proven RSX stall',
    'pipeline_build_callback': 'pipeline build callback CPU residence; not a GPU timer',
    'cpu_gpu_fence': 'CPU waiting for a GPU fence; excludes fence wait_flush',
    'vm_range_episode': 'whole VM range-lock episode; overlaps other work',
    'guest_rsx_semaphore': 'RSX polling a guest semaphore',
    'llvm_budget_cv': 'compiler waiting for host memory-budget admission',
    'llvm_admission_mutex': 'compiler acquiring admission mutex',
}
JIT_SUM_FIELDS = ('calls', 'empty_calls', 'deferred_calls', 'history_ranges',
                  'dirty_ranges', 'flushed_bytes', 'total_ms')
JIT_MAX_FIELDS = ('max_ms',)
JIT_METADATA_FIELDS = ('retained_metadata_bytes', 'peak_metadata_bytes')
MEMORY_FIELDS = ('footprint', 'resident', 'compressed', 'virtual')


def number(fields, key, default=0):
    try:
        result = float(fields.get(key, default))
        if not math.isfinite(result) or result < 0:
            raise ValueError(key)
        return result
    except (TypeError, ValueError):
        raise ValueError('Invalid nonnegative field ' + key)


def integer(fields, key, default=0):
    raw = str(fields.get(key, default))
    if not re.fullmatch(r'\d+', raw):
        raise ValueError('Invalid nonnegative integer field ' + key)
    return int(raw)


def rows(paths):
    seen = {}
    duplicates = 0
    result, inputs, builds = [], [], set()
    for path in paths:
        data = path.read_bytes()
        inputs.append(dict(name=path.name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        for line in data.decode('utf-8', errors='replace').splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            build, pid = str(obj.get('build', 'unknown')), str(obj.get('pid', 'unknown'))
            builds.add(build)
            message = obj.get('message', '')
            if not isinstance(message, str) or not (match := MARKER.search(message)):
                continue
            try:
                timestamp = float(obj['timestamp'])
                if not math.isfinite(timestamp) or timestamp < 0:
                    continue
            except (ValueError, TypeError, KeyError):
                continue
            fields = dict(FIELD.findall(message[match.end():]))
            # Mirrors can use another timestamp, TID prefix, stage or field
            # order. An explicit window is the event identity, not its text.
            identity = (build, pid, fields.get('session', 'unknown'))
            window = fields.get('window')
            key = (*identity, window, match[1]) if window is not None else (*identity, timestamp, match[1])
            payload = tuple(sorted(fields.items()))
            if key in seen:
                first, previous_payload = seen[key]
                if payload == previous_payload and abs(timestamp - first['timestamp']) <= 60:
                    duplicates += 1
                    first['timestamp'] = min(first['timestamp'], timestamp)
                else:
                    # Never choose one of two conflicting observations to get
                    # a more favorable result. The whole window is rejected.
                    first['conflicting_duplicate'] = True
                continue
            row = dict(build=build, pid=pid, timestamp=timestamp, marker=match[1], fields=fields)
            seen[key] = row, payload
            result.append(row)
    return sorted(result, key=lambda row: row['timestamp']), inputs, duplicates, sorted(builds)


def reporting_windows(observations, rejected):
    windows, legacy_last = {}, {}
    for row in observations:
        f = row['fields']
        identity = row['build'], row['pid'], f.get('session', 'unknown')
        if 'window' in f:
            window = integer(f, 'window')
            key = (*identity, 'window', window)
            association = 'explicit_session_window'
        elif row['marker'] == 'FRAMEPROF527':
            key = (*identity, 'legacy_timestamp', row['timestamp'])
            legacy_last[identity] = key, row['timestamp']
            association = 'legacy_timestamp_fallback'
        else:
            previous = legacy_last.get(identity)
            if previous is None or not 0 <= row['timestamp'] - previous[1] <= 1:
                rejected['unassociated_report_row'] += 1
                continue
            key, _ = previous
            association = 'legacy_timestamp_fallback'
        window = windows.setdefault(key, dict(identity=identity, identifier=f.get('window'),
                                               association=association, reports={}))
        if row.get('conflicting_duplicate') or row['marker'] in window['reports']:
            window['conflict'] = True
        window['reports'][row['marker']] = row
    return windows.values()


def analyze(paths, phases=()):
    observations, inputs, duplicates, builds = rows(paths)
    groups, rejected = {}, Counter()
    for phase in phases:
        if not isinstance(phase, dict) or not isinstance(phase.get('name'), str) or not {'start', 'end'} <= set(phase):
            raise ValueError('Every phase needs a name and increasing epoch start/end')
        start, end = number(phase, 'start'), number(phase, 'end')
        if not start < end:
            raise ValueError('Every phase needs increasing epoch start/end')
    for window in reporting_windows(observations, rejected):
        reports = window['reports']
        if window.get('conflict'):
            rejected['conflicting_duplicate_window'] += 1
            continue
        if 'FRAMEPROF527' not in reports:
            rejected['window_without_frame_report'] += 1
            continue
        frame = reports['FRAMEPROF527']
        start = frame['timestamp'] - number(frame['fields'], 'window_ms') / 1000
        end = frame['timestamp']
        identity = window['identity']
        selected = [phase['name'] for phase in phases
            if all(key not in phase or str(phase[key]) == identity[index]
                   for index, key in enumerate(('build', 'pid', 'session')))
            and number(phase, 'start') <= start and end <= number(phase, 'end')]
        if phases and len(selected) != 1:
            rejected['straddled_or_unlabelled_window' if not selected else 'ambiguous_phase'] += 1
            continue
        label = selected[0] if selected else 'unclassified'
        key = (*identity, label)
        g = groups.setdefault(key, dict(build=identity[0], pid=identity[1], session=identity[2], phase=label,
            frame_windows=0, intervals=0, unavailable_intervals=0, interval_total_ms=0.0,
            over50ms=0, over100ms=0, maximum_frame_ms=0.0, histogram=Counter(),
            window_association_modes=[], waits={},
            jit={**{name: 0 for name in JIT_SUM_FIELDS}, 'max_ms': 0.0},
            memory=dict(reports=0, valid_instant_reports=0, sampling_period_target_ms=500,
                session_valid_samples_observed_max=0, reported_instant_max={}, session_sampled_peaks={}),
            slow_windows=[]))
        if window['association'] not in g['window_association_modes']:
            g['window_association_modes'].append(window['association'])
        for marker, row in reports.items():
            f = row['fields']
            if marker == 'FRAMEPROF527':
                histogram = Counter()
                raw = f.get('histogram_upper_us', 'none')
                if raw != 'none':
                    for item in raw.split(','):
                        upper, count = item.split(':')
                        upper, count = integer({'v': upper}, 'v'), integer({'v': count}, 'v')
                        if upper <= 0:
                            raise ValueError('Invalid frame histogram')
                        histogram[upper] += count
                count = integer(f, 'intervals')
                if sum(histogram.values()) != count:
                    raise ValueError('Histogram and frame interval count disagree')
                g['frame_windows'] += 1
                g['intervals'] += count
                g['unavailable_intervals'] += integer(f, 'unavailable')
                g['interval_total_ms'] += number(f, 'total_interval_ms')
                g['over50ms'] += integer(f, 'over50ms')
                g['over100ms'] += integer(f, 'over100ms')
                g['maximum_frame_ms'] = max(g['maximum_frame_ms'], number(f, 'max_ms'))
                g['histogram'].update(histogram)
                if number(f, 'max_ms') > 50:
                    g['slow_windows'].append(dict(window=window['identifier'], start=start, end=end,
                        maximum_ms=number(f, 'max_ms'), reported_p95_ms=number(f, 'p95_ms'),
                        note='Reporting-window co-occurrence, not event-level causality'))
            elif marker == 'WAITPROF527':
                for name, scope in WAITS.items():
                    if name not in f:
                        continue
                    values = f[name].split(':')
                    if len(values) != 3:
                        raise ValueError('Invalid wait tuple ' + name)
                    count = integer({'count': values[0]}, 'count')
                    total, maximum = (number({'value': value}, 'value') for value in values[1:])
                    target = g['waits'].setdefault(name, dict(count=0, total_ms=0.0, max_ms=0.0, scope=scope))
                    target['count'] += count
                    target['total_ms'] += total
                    target['max_ms'] = max(target['max_ms'], maximum)
            elif marker == 'JITPUB527':
                # Iterate fixed raw fields: never re-read the derived
                # *_observed_max keys from a previous reporting window.
                for name in JIT_SUM_FIELDS:
                    g['jit'][name] += number(f, name) if name == 'total_ms' else integer(f, name)
                for name in JIT_MAX_FIELDS:
                    g['jit'][name] = max(g['jit'][name], number(f, name))
                for name in JIT_METADATA_FIELDS:
                    derived = name + '_observed_max'
                    g['jit'][derived] = max(g['jit'].get(derived, 0), integer(f, name))
            elif marker == 'MEMPROF527':
                memory = g['memory']
                memory['reports'] += 1
                valid, samples = integer(f, 'valid'), integer(f, 'samples')
                if valid not in (0, 1):
                    raise ValueError('Memory valid flag must be0 or1')
                memory['session_valid_samples_observed_max'] = max(memory['session_valid_samples_observed_max'], samples)
                if valid:
                    memory['valid_instant_reports'] += 1
                    for name in MEMORY_FIELDS:
                        target = memory['reported_instant_max']
                        target[name] = max(target.get(name, 0), integer(f, name))
                # Peaks and sample count are cumulative since session reset.
                # A peak printed during gameplay may have occurred at startup.
                if samples:
                    for name in MEMORY_FIELDS:
                        target = memory['session_sampled_peaks']
                        target[name] = max(target.get(name, 0), integer(f, 'peak_' + name))
    output = []
    for g in groups.values():
        hist = g.pop('histogram')
        def quantile(percent):
            target = math.ceil(g['intervals'] * percent / 100)
            cumulative = 0
            for upper, count in sorted(hist.items()):
                cumulative += count
                if target and cumulative >= target:
                    return upper / 1000
            return None
        g['frame_quantile_upper_bound_ms'] = {str(p): quantile(p) for p in (50, 95, 99)}
        g['frame_quantile_scope'] = 'Available recorded guest-flip intervals; unavailable intervals excluded'
        g['histogram_upper_us'] = dict(sorted(hist.items()))
        g['guest_interval_cadence_fps'] = g['intervals'] * 1000 / g['interval_total_ms'] if g['interval_total_ms'] else None
        jit = g['jit']
        jit['historical_range_visits_avoided'] = jit['history_ranges'] - jit['dirty_ranges']
        jit['scope'] = 'Observed527 publication; historical range count is counterfactual work, not526 time'
        g['memory']['reported_instant_max_scope'] = 'Maximum of valid latest500ms samples printed in admitted reports; not all phase samples'
        g['memory']['session_sampled_peaks_scope'] = 'Session-lifetime sampled peaks observed in admitted reports; may predate this phase'
        output.append(g)
    metric_builds = {row['build'] for row in observations}
    return dict(schema_version=2, inputs=inputs, observed_builds=builds,
        builds_without_527_metrics=[build for build in builds if build not in metric_builds],
        duplicate_rows=duplicates, rejected=dict(rejected), observed_rows=len(observations), groups=output,
        physical_device_tested_by_analyzer=False, limitations=[
            'No matched526/527 gameplay claim is generated.',
            'Histogram-merged quantiles are bucket upper bounds; reported window quantiles are never averaged.',
            'Wait totals may overlap across threads and their drain boundaries are approximate; window co-occurrence does not prove a frame blocker.',
            'Memory sample counts and printed peaks are cumulative per session, not phase counts or phase peaks.',
            'Process memory sampling targets500ms and can miss transient peaks; categories/shared counters overlap.',
            'Unclassified guest windows are not automatically gameplay; provide timestamped phase notes.',
            'Old527 records without window IDs use an explicitly labelled timestamp fallback.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+', type=Path)
    parser.add_argument('--phases', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = analyze(args.logs, json.loads(args.phases.read_text()) if args.phases else ())
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
