#!/usr/bin/env python3
"""Extend session/clock analysis with reservation, JIT and merged frame evidence.

No raw private paths, inferred scene labels, or averaged percentiles are emitted.
The inherited reader deduplicates NeoSwap by (PID, session, sequence).
"""
import argparse,collections,json,math,re,subprocess,sys
from pathlib import Path
from analyze_rpcs3_cell534_logs import rows,fields,utc

def histogram_lower(upper):
    if upper==4294967295:return 1144000
    return upper-(999 if upper<128000 else 7999)

def summarize(windows):
    frames=[w['FRAMEPROF527'] for w in windows if 'FRAMEPROF527' in w]
    hist=collections.Counter()
    for frame in frames:
        raw=frame['histogram_upper_us']
        bins={} if raw=='none' else {int(k):int(v) for k,v in (part.split(':') for part in raw.split(','))}
        assert sum(bins.values())==int(frame['intervals'])
        hist.update(bins)
    total=sum(hist.values())
    def quantile(percent):
        if not total:return None
        rank=math.ceil(total*percent/100);count=0
        for upper,n in sorted(hist.items()):
            count+=n
            if count>=rank:return [histogram_lower(upper)/1000,upper/1000]
    above=sum(n for upper,n in hist.items() if histogram_lower(upper)>500000)
    ambiguous=sum(n for upper,n in hist.items() if histogram_lower(upper)<=500000<upper)
    return dict(intervals=total,unavailable=sum(int(f['unavailable']) for f in frames),
                p50MsBounds=quantile(50),p95MsBounds=quantile(95),p99MsBounds=quantile(99),
                maximumMs=max(float(f['max_ms']) for f in frames),
                over50ms=sum(int(f['over50ms']) for f in frames),
                over100ms=sum(int(f['over100ms']) for f in frames),over500msBounds=[above,above+ambiguous],
                totalIntervalMs=round(sum(float(f['total_interval_ms']) for f in frames),3),
                phaseLabels=sorted({f['phase'] for f in frames}),
                histogramUpperUs=dict(sorted(hist.items())),
                noFrames='No independent continuous presentation/no-frame timeline; guest flip intervals only. Missing time outside the retained windows is unmeasured.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--neo',type=Path,required=True);p.add_argument('--rpc',type=Path,required=True)
    p.add_argument('--milestones',type=Path,required=True);p.add_argument('--app',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    subprocess.run([sys.executable,str(Path(__file__).with_name('analyze_rpcs3_cell534_logs.py')),*sys.argv[1:]],check=True)
    report=json.loads(a.output.read_bytes());native=rows(a.rpc)[0]+rows(a.milestones)[0]
    for proc in report['rpcProcesses']:
        records=sorted([r for _,r in native if r.get('pid')==proc['pid'] and r.get('build')==proc['build']],key=lambda r:r['timestamp'])
        frame_windows=[w for w in proc['windows'] if 'FRAMEPROF527' in w]
        frame_tids={}
        for row in records:
            if 'FRAMEPROF527' not in row.get('message',''):continue
            data=fields(row['message']);tid=re.match(r'TID: (\d+):',row['message'])
            if tid:frame_tids[(data.get('session'),data.get('window'))]=tid.group(1)
        for row in records:
            message=row.get('message','');data=fields(message)
            tag=next((t for t in ('RANGELOCKPROF','SPUPROF','JITPROF','JITMEM','COREPROF_RESILIENCE') if re.search(r'\b'+t+r'\b',message)),None)
            if message.startswith('TID: ') and 'COREPROF frames=' in message:tag='COREPROF'
            if not tag or not frame_windows:continue
            # Same native capture clock, PID, logger TID, and reporting batch.
            # Tags without a window id are emitted by the same sampler function.
            begin=row.get('clockMonotonicBeginUs')
            if begin is None:continue
            nearest=min(frame_windows,key=lambda w:abs(w['FRAMEPROF527']['capturedMonotonicUs'][0]-begin))
            delta=begin-nearest['FRAMEPROF527']['capturedMonotonicUs'][0]
            if abs(delta)>100000 or ('session' in data and data['session']!=nearest['session']):continue
            tid=re.match(r'TID: (\d+):',message)
            if not tid or tid.group(1)!=frame_tids.get((nearest['session'],nearest['window'])):continue
            assert tag not in nearest,(tag,nearest['window'])
            nearest[tag]=dict(data,captureDeltaFromFrameUs=delta,association='same process/logger TID/native clock, within 100 ms; sampler emits these tags together')
        samples=[dict(fields(r['message']),capturedUnix=r['timestamp']) for r in records if r['stage']=='performance_sample']
        proc['sampleSummary']=dict(samples=len(samples),epochs=sorted({s.get('sample_epoch') for s in samples}),
            maximumSampledFootprint=max((int(s['memory'].split('/')[0]) for s in samples),default=None),
            zeroOrNegativeFpsSamples=sum(float(s['fps'])<=0 for s in samples),
            thermal= dict(collections.Counter(s.get('thermal','unavailable') for s in samples)),
            firstUtc=utc(samples[0]['capturedUnix']) if samples else None,lastUtc=utc(samples[-1]['capturedUnix']) if samples else None)
        proc['bootPhases']=[dict(fields(r['message']),capturedUtc=utc(r['timestamp'])) for r in records if 'JITPROF_BOOT' in r['message']]
        proc['restoreFinalization']=[dict(phase=fields(r['message']).get('phase'),capturedUtc=utc(r['timestamp'])) for r in records if any(t in r['message'] for t in ('phase=finalize_run_begin','phase=finalize_run_end'))]
        if frame_windows:proc['mergedFrames']=summarize(frame_windows)
        first= min((w['FRAMEPROF527']['capturedMonotonicUs'][0]-float(w['FRAMEPROF527']['window_ms'])*1000 for w in frame_windows),default=None)
        for neo in report['neoSessions']:
            if neo['pid']!=proc['pid']:continue
            offsets=neo.get('unixMinusMonotonicUsRange')
            for pressure in neo['pressure']:
                if offsets:pressure['utcBounds']=[utc((pressure['monotonicUs']+offset)/1e6) for offset in offsets]
                if first is not None:pressure['secondsBeforeFirstObservedFrameWindow']=(first-pressure['monotonicUs'])/1e6
    report['limitations']=['No controlled before/after gameplay pair or reliable cinematic/gameplay labels.',
        'Thread wait sums overlap across threads and with caller operations; never sum them as a single visible pause.',
        'Sampled footprint includes compressed accounting; VMA requests and aliases are not independent physical allocations.',
        'Old NeoSwap sessions without clock anchors cannot be causally aligned to this process.',
        'Current session contains no managed archive activity: device fsync-removal effect, dirty-page cost and restore latency remain unmeasured.']
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    for proc in report['rpcProcesses']:print(json.dumps({k:proc.get(k) for k in ('pid','build','sampleSummary','mergedFrames')},indent=2))
if __name__=='__main__':main()
