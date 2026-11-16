import json, sys, statistics
# per-second view of a progressive run: delay of the picture on screen, element rate, buffered ahead, frozen samples
r = json.load(open(sys.argv[1])); fps = r['origin']['options']['fps']; t0 = r['origin']['t0']; load = r['marks']['loadSent']
rows = {}
prev = None
for s in r['page']['samples']:
    if 'mt' not in s or s.get('mt') is None: continue
    n = round(s['mt'] * fps) if s.get('n', -1) == -2 else s.get('n', -1)
    if n < 0: continue
    sec = int((s['w'] - load) / 1000)
    d = s['w'] - (t0 + n / fps * 1000)
    ahead = (s['b'][-1][1] - s['ct']) if s.get('b') else None
    frozen = prev is not None and n == prev
    rows.setdefault(sec, []).append((d, s.get('r'), ahead, frozen)); prev = n
acts = [(round((a['t'] - load) / 1000, 1), a['action'].get('do'), (a['action'].get('msg') or {}).get('type'), (a['action'].get('msg') or {}).get('playbackRate'), a['action'].get('ms')) for a in r.get('actionsDone', []) if a['action'].get('do') != 'snapshot']
print('actions (s after LOAD):', acts)
out = []
for sec in sorted(rows):
    v = rows[sec]; d = statistics.median(x[0] for x in v); ah = [x[2] for x in v if x[2] is not None]
    out.append(f"{sec:>3}s delay {d:6.0f} ms  rate {max(x[1] for x in v):.2f}  ahead {statistics.median(ah) if ah else -1:5.2f}s  frozen {sum(1 for x in v if x[3])}/{len(v)}")
print('\n'.join(out))
