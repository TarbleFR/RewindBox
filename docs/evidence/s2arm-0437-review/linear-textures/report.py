import csv,sys
from pathlib import Path
from statistics import median
from collections import defaultdict
for path in map(Path,sys.argv[1:]):
    all_pairs=defaultdict(lambda:defaultdict(dict))
    for v in csv.DictReader(path.open()):
        all_pairs[v['case'],v['direction']][int(v['pair'])][int(v['variant'])]=float(v['ns_per_copy'])
    print(path.name, 'case direction pairs median(ns base) change% [96.14% nominal] control/base% candidate/control%')
    for (case,direction),samples in all_pairs.items():
        assert len(samples)==12 and all(len(p)==3 for p in samples.values())
        def change(i,j):return sorted(100*(p[i]/p[j]-1) for p in samples.values())
        v=change(1,0);c=change(2,0)
        print(f"{case:18} {'W' if direction=='1' else 'R'} {len(v):2} {median([p[0] for p in samples.values()]):11.1f} {median(v):+6.1f} [{v[2]:+5.1f},{v[9]:+5.1f}] {median(c):+5.1f} {median(change(1,2)):+6.1f}")
