#!/usr/bin/env python3
"""Run the host BGC probe in N processes (P at a time) and count thread-creation outcomes.

usage: run.py <label> <processes> <parallel> <idleTrials> <idleSeconds> <warmTrials> [dotnet] [env=value ...]
"""
import collections, concurrent.futures, json, os, subprocess, sys

label, n, par, idle, secs, warm = sys.argv[1], *map(int, sys.argv[2:7])
dotnet = sys.argv[7] if len(sys.argv) > 7 else '/home/user/work/dotnet/dotnet'
env = dict(os.environ)
for kv in sys.argv[8:]:
    k, v = kv.split('=', 1)
    env[k] = v
here = os.path.dirname(os.path.abspath(__file__))
dll = os.path.join(here, 'bin/Release/net10.0/probe.dll')


def one(_):
    out = subprocess.run([dotnet, dll, str(idle), str(secs), str(warm)], env=env, capture_output=True, text=True,
                         timeout=60 + idle * (secs + 10) + warm * 10)
    return [json.loads(line) for line in out.stdout.splitlines() if line.startswith('{')]


rows, meta = [], None
with concurrent.futures.ThreadPoolExecutor(par) as pool:
    for result in pool.map(one, range(n)):
        meta = result[-1]
        rows += result[:-1]
c = collections.Counter()
for r in rows:
    path = 'create' if r['bgcThreadsBefore'] == 0 else 'alive'
    c[(path, r['trial'].rstrip('0123456789s') or r['trial'], r['outcome'])] += 1
summary = {'label': label, 'runtime': meta, 'processes': n, 'parallel': par, 'idleSeconds': secs,
           'counts': {' / '.join(k): v for k, v in sorted(c.items())}}
created = [r for r in rows if r['bgcThreadsBefore'] == 0 and r['outcome'] in ('fallback', 'background')]
summary['threadCreationRequests'] = len(created)
summary['threadCreationFallbacks'] = sum(r['outcome'] == 'fallback' for r in created)
alive = [r for r in rows if r['bgcThreadsBefore'] > 0 and r['outcome'] in ('fallback', 'background')]
summary['liveThreadRequests'] = len(alive)
summary['liveThreadFallbacks'] = sum(r['outcome'] == 'fallback' for r in alive)
summary['fallbackPauseMs'] = sorted(r['fullBlockingPauseMs'] for r in rows if r['outcome'] == 'fallback')
print(json.dumps(summary, indent=1))
