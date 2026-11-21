#!/usr/bin/env python3
"""Report timestamp intervals for one matched device window, keeping GPU counter and feedback clocks separate."""
import argparse
import collections
import json
import math
import re
from pathlib import Path

def quantiles(values):
    values=sorted(values)
    return {k:values[math.ceil(len(values)*p)-1] if values else None
            for k,p in [('p50_us',.50),('p95_us',.95)]} | {'n':len(values)}

def summarize(lines,first,last):
    durations=collections.defaultdict(list)
    boundaries=collections.Counter()
    counts=[]
    rows={}
    missing=0
    for line in lines:
        fid=re.search(r'\[gpuprof\] F(\d+)|\[rb-tail\] (?:FX|present) frame=(\d+)',line)
        if not fid: continue
        frame=int(fid[1] or fid[2])
        if not first <= frame <= last: continue
        fields=dict(re.findall(r'([A-Za-z0-9_]+)=([^ ]+)',line.rstrip()))
        if 'end_to_start_us' in fields:
            boundaries[fields.get('boundary','unclassified')]+=1
            durations['render_end_to_next_start'].append(float(fields['end_to_start_us']))
        if fields.get('cb_markers_valid')=='1':
            durations['fx_cb_elapsed'].append(float(fields['fx_cb_elapsed_us']))
        if fields.get('cb_markers_valid')=='0': missing+=1
        if fields.get('cb_valid')=='1' and fields.get('nearest_only')=='1':
            durations['nearest_present_cb'].append(float(fields['present_cb_us']))
        if 'cuts_physical' in fields:
            counts.append((frame,{k:int(fields[k]) for k in ('kept','empty_encoders_saved','terminal_dependencies_omitted','copy_reused','cuts_physical','cuts_busy_deferred','cuts_copy','cuts_inside_render')}))
        # Older logs lack MetalFX brackets. Retain observable render endpoints, never assign index 67 to FX.
        m=re.search(r'\s(\d+)\s+([\d.]+) us render pass (53923|53924) .*?start \+([\d.]+) seg (\d+)',line)
        if m and frame==2813:
            rows[int(m[1])] = {'pass':int(m[3]),'end':float(m[4])+float(m[2]),'start':float(m[4]),'seg':int(m[5])}
    result={'requested_frame_range':[first,last],'nearest_present_sampling':'1 of 16 tickets',
            'durations':{k:quantiles(durations[k]) for k in ('render_end_to_next_start','fx_cb_elapsed','nearest_present_cb')},
            'boundaries':dict(boundaries),'invalid_fx_marker_pairs':missing}
    if 66 in rows and 68 in rows and rows[66]['pass']==53923 and rows[68]['pass']==53924:
        result['F2813_render_gap']={'end_to_start_us':round(rows[68]['start']-rows[66]['end'],1),
                                     'start_to_start_us':round(rows[68]['start']-rows[66]['start'],1),'segments':[rows[66]['seg'],rows[68]['seg']]}
    if len(counts)>1:
        low,high=counts[0],counts[-1]
        if any(b[1][k]<a[1][k] for a,b in zip(counts,counts[1:]) for k in a[1]):
            raise ValueError('Counter reset. Supply an uninterrupted single-session window.')
        result['fx_count_interval']=[low[0],high[0]]
        result['fx_count_deltas']={k:high[1][k]-low[1][k] for k in low[1]}
    return result
if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('log',type=Path)
    cli.add_argument('--first',type=int,required=True)
    cli.add_argument('--last',type=int,required=True)
    a=cli.parse_args()
    with a.log.open(errors='replace') as fp:
        print(json.dumps(summarize(fp,a.first,a.last),indent=2))
