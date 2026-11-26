from pathlib import Path
import csv,statistics as st,sys
from collections import defaultdict
p=Path(sys.argv[1]);sets={}
for temp in ('warm','cold'):
 for order in [0,1]:
    f=p/(temp+str(order)+'.csv')
    if not f.exists():raise ValueError(f"missing results: {f}")
    g=defaultdict(lambda:defaultdict(dict))
    for r in csv.DictReader(f.open()):
        if r['pair'] and r['checksum']:g[r['case']][r['variant']][int(r['pair'])]=r
    sets[temp,order]=g
print('case,state,link_order,variant,ns_corrected,ns_variant,median_paired_percent,rank3_percent,rank10_percent,temporary_heap_before,temporary_heap_after,initial_checksum_matches,all_corrected_checksums')
for (temp,order),data in sets.items():
 for name,d in data.items():
    if any(set(d[v]) != set(range(1,13)) for v in ('corrected','initial','control','suffix','safe')):raise ValueError((name, temp, order))
    def ns(r):return int(r['cpu_ns'])/int(r['calls'])
    def heap(v):return d[v][1]['requested_heap_bytes_per_call']
    for v in ['initial','control','suffix','safe']:
        base=d['corrected'];var=d[v]
        ok=all(var[i]['checksum']==r['checksum'] for i,r in base.items())
        assert v=='initial' or ok
        times=sorted((ns(var[i])/ns(r)-1)*100 for i,r in base.items())
        print(','.join(map(str,[name,temp,order,v,round(st.median(map(ns,base.values())),1),round(st.median(map(ns,var.values())),1),round(st.median(times),1),round(times[2],1),round(times[9],1),heap('corrected'),heap(v),d['initial'][1]['checksum']==base[1]['checksum'],ok])))
