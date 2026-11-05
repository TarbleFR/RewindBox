#!/usr/bin/env python3
"""Summarise bgc_timeline.py output: every BGC request (real or fallback) with its gap."""
import collections, re, sys

for path in sys.argv[1:]:
    print('##', path.rsplit('/', 1)[-1])
    rows = []
    pid = build = None
    for line in open(path):
        m = re.match(r'=== pid (\S+) build (\S+)', line)
        if m:
            pid, build = m.groups()
            continue
        m = re.match(r'\s+perf (\S+ \S+) (\S+)\s+idx\s+(\d+) gapSincePrevBgcSample\s+(\S+)\s+windowGcPauseMs (\S+)', line)
        if m:
            rows.append((pid, build) + m.groups())
    for r in rows:
        if r[3] in ('FALLBACK', 'fullBlocking'):
            print('%-6s b%-4s %s %-12s idx %5s gap %8s windowPauseMs %s' % r)
    b = collections.Counter()
    for pid, build, t, kind, idx, gap, pause in rows:
        if kind not in ('background', 'FALLBACK') or gap == '-':
            continue
        g = float(gap.rstrip('s'))
        bucket = 'a <15s' if g < 15 else ('b 15-25s' if g <= 25 else 'c >25s')
        b[(bucket, kind)] += 1
    for k in sorted(b):
        print('  bucket', k, b[k])
