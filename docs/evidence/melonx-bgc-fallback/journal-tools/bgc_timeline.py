#!/usr/bin/env python3
"""Aggregate MeloNX gen2 GC timing from private core/performance journals.

Reads gcEvent lines (core log) and performance samples (lastBackgroundGcIndex,
lastFullBlockingGcIndex, collections) per pid, then lists every gen2 event with
the idle gap since the previous *real* background GC.  Prints aggregated rows
only; nothing is written next to the private logs.
"""
import json, sys, datetime, collections

def ts(s):
    s = s.rstrip('Z')
    if '.' in s:
        head, frac = s.split('.')
        s = head + '.' + frac[:6]
        return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%f')
    return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S')

def records(path):
    with open(path, 'r', errors='replace') as f:
        for line in f:
            i = line.find('{')
            if i < 0:
                continue
            try:
                rec = json.loads(line[i:])
            except Exception:
                continue
            if not isinstance(rec, dict):
                continue
            d = rec.get('diagnostic')
            if isinstance(d, str) and d.startswith('{'):
                try:
                    rec['_d'] = json.loads(d)
                except Exception:
                    rec['_d'] = None
            yield rec

def main(paths):
    gcev = collections.defaultdict(list)    # pid -> rows
    perf = collections.defaultdict(list)    # pid -> rows
    build = {}
    for p in paths:
        for r in records(p):
            pid = str(r.get('pid') or (r.get('context') or {}).get('pid'))
            ctx = r.get('context') or {}
            if ctx.get('build'):
                build[pid] = ctx.get('build')
            st = r.get('stage')
            d = r.get('_d')
            if st == 'gcEvent' and d:
                gcev[pid].append((ts(r['timestamp']), d))
            elif st == 'performance' and d and 'managed' in d:
                perf[pid].append((ts(r['timestamp']), d))
    for pid in sorted(set(gcev) | set(perf), key=lambda x: int(x) if x.isdigit() else 0):
        ev = sorted({(t, json.dumps(d, sort_keys=True)) for t, d in gcev[pid]})
        pf = sorted({(t, json.dumps(d, sort_keys=True)) for t, d in perf[pid]})
        ev = [(t, json.loads(d)) for t, d in ev]
        pf = [(t, json.loads(d)) for t, d in pf]
        fb_seen = [d['managed'].get('lastFullBlockingGcIndex') for _, d in pf]
        has_fb = any(x not in (None, 0, 1) for x in fb_seen) or any(d['kind'] == 'fullBlocking' for _, d in ev)
        if not ev and not has_fb and not any(d['managed'].get('lastBackgroundGcIndex') for _, d in pf):
            continue
        print(f'=== pid {pid} build {build.get(pid)} gcEvent={len(ev)} perfSamples={len(pf)}')
        # Timeline of gen2 events from performance samples (index changes).
        last_bg = last_fb = None
        last_real_bg_t = None
        events = []
        for t, d in pf:
            m = d['managed']
            bg, fb = m.get('lastBackgroundGcIndex'), m.get('lastFullBlockingGcIndex')
            if bg is None:
                continue
            if last_bg is None:
                last_bg, last_fb = bg, fb
                continue
            g2 = None
            col = m.get('collections')
            if fb != last_fb:
                kind = 'FALLBACK' if fb == bg else 'fullBlocking'
                events.append((t, kind, fb, m, d))
            if bg != last_bg and bg != fb:
                events.append((t, 'background', bg, m, d))
            last_bg, last_fb = bg, fb
        prev_bg_t = None
        for t, kind, idx, m, d in events:
            gap = (t - prev_bg_t).total_seconds() if prev_bg_t else None
            gaps = f'{gap:7.1f}s' if gap is not None else '      -'
            print(f'  perf {t:%m-%d %H:%M:%S} {kind:12s} idx {idx:5d} gapSincePrevBgcSample {gaps} '
                  f'windowGcPauseMs {d["managed"].get("gcPauseMs")} lastGc(gen {m.get("lastGcGeneration")} conc {m.get("lastGcConcurrent")} comp {m.get("lastGcCompacted")})')
            if kind == 'background':
                prev_bg_t = t
        prev_bg_t = None
        for t, d in ev:
            gap = (t - prev_bg_t).total_seconds() if prev_bg_t else None
            gaps = f'{gap:7.1f}s' if gap is not None else '      -'
            print(f'  gcEv {t:%m-%d %H:%M:%S} {d["kind"]:12s} idx {d["index"]:5d} gen {d["generation"]} conc {d["concurrent"]} comp {d["compacted"]} '
                  f'pauseMs {d["pauseMs"]} new {int(d["newInWindow"])} win {d["gen2CollectionsInWindow"]} final {int(d["finalSample"])} '
                  f'heapMiB {d["heapSizeBytes"]/2**20:.0f} gapSincePrevBg {gaps}')
            if d['kind'] == 'background':
                prev_bg_t = t

if __name__ == '__main__':
    main(sys.argv[1:])
