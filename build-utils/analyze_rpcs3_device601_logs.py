#!/usr/bin/env python3
"""Summarize the supplied, mixed-generation journals without conflating sessions.

Only existing events are read. Counts deduplicate mirrored performance/diagnostic
events by process, timestamp and message. Completed intervals are never compared
as if they represented matched gameplay scenes or GPU execution time.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def fields(message):
    return dict(re.findall(r'(?<!\S)([A-Za-z0-9_]+)=([^\s]+)', message))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    inputs, events, invalid = {}, {}, {}
    for path in sorted(args.logs.glob('*')):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        inputs[path.name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if not path.name.startswith('RPCS3-'):
            continue
        for line_number, line in enumerate(raw.decode('utf-8').splitlines(), 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                invalid[path.name] = invalid.get(path.name, 0) + 1
                continue
            if not isinstance(row.get('message'), str) or not isinstance(row.get('timestamp'), (float, int)):
                continue
            key = (row.get('pid'), row['timestamp'], row['message'])
            entry = events.setdefault(key, {'event': row, 'references': []})
            entry['references'].append(f'{path.name}:{line_number}')
    ordered = sorted(events.values(), key=lambda item: item['event']['timestamp'])
    sessions, active = {}, {}
    for item in ordered:
        row = item['event']
        if row.get('build') != '601':
            continue
        message, pid = row['message'], row.get('pid')
        if row.get('stage') == 'game_boot_begin':
            key = f"{pid}:{row['timestamp']}"
            active[pid] = key
            sessions[key] = {'pid': pid, 'title': message, 'boot_timestamp': row['timestamp'],
                             'boot_reference': item['references'], 'frames': [], 'profiles': [],
                             'render_cause': [], 'sync': [], 'last_timestamp': row['timestamp']}
        if pid not in active:
            continue
        session = sessions[active[pid]]
        session['last_timestamp'] = row['timestamp']
        data = fields(message)
        value = {'timestamp': row['timestamp'], 'references': item['references'], **data}
        if row.get('stage') == 'game_boot_return':
            session['boot_return_seconds'] = row['timestamp'] - session['boot_timestamp']
        if 'COREPROF FRAMEPROF527 ' in message:
            session['frames'].append(value)
        elif 'COREPROF frames=' in message:
            session['profiles'].append(value)
        elif 'COREPROF RENDERCAUSE ' in message:
            session['render_cause'].append(value)
        elif 'RSXSYNC551 ' in message:
            session['sync'].append(value)
    for session in sessions.values():
        session['observed_seconds_after_boot'] = session['last_timestamp'] - session['boot_timestamp']
        session['render_events_retained'] = sum(int(row.get('retained', 0)) for row in session['render_cause'])
        # Report raw windows; no FPS averaging over different phases or titles.
        session['metal_compile_requests_default'] = sum(int(row.get('metal_compiles_default', 0))
                                                       for row in session['sync'])
    report = {'schema': 1, 'inputs': inputs, 'unique_structured_events': len(events),
              'invalid_json_lines': invalid, 'build601_sessions': list(sessions.values()),
              'limits': ['Only retained journals are available.',
                         'A title/mode restart can occur without a new host game_boot_begin.',
                         'Native UI and gameplay scenes are not identified by FPS.',
                         'No GPU execution measurement or candidate device run.',
                         'No before/after FPS gain can be computed from these mixed scenes.']}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'unique_events': len(events), 'build601_sessions': len(sessions),
                      'invalid_json_lines': invalid, 'report': str(args.report)}))


if __name__ == '__main__':
    main()
