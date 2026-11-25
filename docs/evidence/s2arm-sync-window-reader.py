#!/usr/bin/env python3
"""Read real cumulative snapshots; never substitute a missing frame-0 snapshot."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('log', type=Path)
parser.add_argument('--from-frame', type=int, required=True)
parser.add_argument('--to-frame', type=int, required=True)
parser.add_argument('--session', type=int, default=0)
args = parser.parse_args()
raw = args.log.read_bytes()
fields = ('queue_wait_records', 'queue_wait_drains', 'allocator_wait_ms', 'visibility_wait_ms')
sessions = [[]]
for line in raw.decode(errors='replace').splitlines():
    if '[rb-cpu-gpu-sync]' not in line:
        continue
    values = {k: Decimal(v) for k, v in re.findall(r'(\w+)=([0-9.]+)', line)}
    if 'frame' not in values or any(f not in values for f in fields):
        continue
    previous = sessions[-1][-1] if sessions[-1] else None
    if previous:
        if values == previous:
            continue
        if values['frame'] <= previous['frame'] or any(values[f] < previous[f] for f in fields):
            sessions.append([])
    sessions[-1].append(values)
if not 0 <= args.session < len(sessions):
    parser.error('requested session absent')
rows = [r for r in sessions[args.session] if args.from_frame <= r['frame'] <= args.to_frame]
if len(rows) < 2 or rows[0]['frame'] != args.from_frame or rows[-1]['frame'] != args.to_frame:
    parser.error('both boundary snapshots must actually be present; no interpolation')

def delta(a, b):
    frames = b['frame'] - a['frame']
    differences = {f: b[f] - a[f] for f in fields}
    return {'fromFrame': int(a['frame']), 'toFrame': int(b['frame']), 'frames': int(frames),
            'delta': {f: float(v) if f.endswith('_ms') else int(v) for f, v in differences.items()},
            'allocatorMsPerFrame': float(differences['allocator_wait_ms'] / frames),
            'visibilityMsPerFrame': float(differences['visibility_wait_ms'] / frames)}

print(json.dumps({'inputSHA256': hashlib.sha256(raw).hexdigest(), 'session': args.session,
                  'windowUnit': 'logged frame boundaries; not a 180-second A/B window',
                  'aggregate': delta(rows[0], rows[-1]),
                  'windows': [delta(a, b) for a, b in zip(rows, rows[1:])]}, indent=2))
