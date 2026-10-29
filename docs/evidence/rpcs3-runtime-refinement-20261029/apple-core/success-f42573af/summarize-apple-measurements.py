#!/usr/bin/env python3
"""Summarize retained plain Apple measurements without executing benchmarks."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path,case):
    p=json.loads(path.read_bytes())
    assert p['passed'] and p['case']==case and p['benchmark'] and p['sanitizer']==''
    assert p['host']==dict(system='Darwin',machine='arm64')
    assert all(p[k] is False for k in ('physicalDeviceTested','gameplayMeasured','gpuExecuted','coreBuilt'))
    assert len(p['programSHA256'])==2
    assert p['tsanSuppressions']==[] and '-UNDEBUG' in p['compilerFlags']
    return p


def metrics(raw):
    assert len(raw)==7 and all(isinstance(v,(int,float)) and v>0 for v in raw)
    q=statistics.quantiles(raw,n=4,method='inclusive')
    return dict(samples=raw,median=statistics.median(raw),minimum=min(raw),maximum=max(raw),
                firstQuartile=q[0],thirdQuartile=q[2],interquartileRange=q[2]-q[0])


def pair(family,case,before,after,**extra):
    a,b=metrics(before),metrics(after)
    return dict(family=family,case=case,unit='ns/operation',baseline=a,candidate=b,
                medianDurationChangePercent=100*(b['median']/a['median']-1),
                slowerMedian=b['median']>a['median'],
                sampleRangesOverlap=max(a['minimum'],b['minimum'])<=min(a['maximum'],b['maximum']),
                **extra)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--failed-diagnostics',type=Path,required=True)
    ap.add_argument('--lookup-report',type=Path)
    ap.add_argument('--lookup-run',type=int)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    assert not args.output.exists()
    assert bool(args.lookup_report)==bool(args.lookup_run)
    rows=[]; provenance={}
    for case in ('timer','descriptor'):
        path=args.failed_diagnostics/f'refined-{case}-plain-result.json'
        p=load(path,case)
        provenance[case]=dict(path=str(path),sha256=sha(path),source='5796e165cc0b355e779309f8a20360dc0e969f0d',
            runId=40914849302,overallRunConclusion='failure',individualModePassed=True,
            compiler=p['compiler'],host=p['host'],programSHA256=p['programSHA256'],compilerFlags=p['compilerFlags'])
        if case=='timer':
            results=p['results']; timing=results['timing']
            assert timing['samples']==7 and len(timing['cases'])==12
            for c in timing['cases']:
                r=pair('timer',f"{c['entries']}/{c['pattern']}",c['baselineNs'],c['candidateNs'],entries=c['entries'],pattern=c['pattern'],iterationsPerSample=c['iterationsPerSample'])
                assert r['baseline']['median']==c['baselineMedianNs']
                assert r['candidate']['median']==c['candidateMedianNs']
                rows.append(r)
            provenance[case]['functional']=results['functional']
        else:
            a,b=(p['results'][k] for k in ('baseline','candidate'))
            assert a['cases']==b['cases'] and a['commandBufferBytes']==b['commandBufferBytes']==336
            assert a['mismatches']==b['mismatches']==0 and len(a['benchmark'])==len(b['benchmark'])==3
            for x,y in zip(a['benchmark'],b['benchmark']):
                assert {k:v for k,v in x.items() if k!='nanoseconds'}=={k:v for k,v in y.items() if k!='nanoseconds'}
                n=x['operations']; assert n==2_000_000
                rows.append(pair('descriptor',x['name'],[v/n for v in x['nanoseconds']],[v/n for v in y['nanoseconds']],
                    operationsPerSample=n,driverCallsPerSample=x['calls'],checksum=x['checksum']))
            provenance[case].update(semanticCases=len(a['cases']),commandBufferBytes=336,driverCallsPreserved=True)
    if args.lookup_report:
        path=args.lookup_report; p=load(path,'lookup')
        provenance['lookup']=dict(path=str(path),sha256=sha(path),runId=args.lookup_run,
            individualModePassed=True,compiler=p['compiler'],host=p['host'],programSHA256=p['programSHA256'],compilerFlags=p['compilerFlags'])
        a,b=(p['results'][k] for k in ('baseline','candidate'))
        assert a['passed'] and b['passed'] and a['interleavedEpochRejected'] and b['interleavedEpochRejected']
        assert len(a['samples'])==len(b['samples'])==21 and a['sink']==b['sink']
        for mode,name in enumerate(('hit','epoch_miss','key_miss')):
            x=[s['nanoseconds'] for s in a['samples'] if s['mode']==mode]
            y=[s['nanoseconds'] for s in b['samples'] if s['mode']==mode]
            rows.append(pair('lookup',name,x,y,operationsPerSample=2_000_000))
    out=dict(schema=1,kind='retained-refinement-apple-microbenchmarks',passed=True,
        cases=rows,caseCount=len(rows),slowerMedianCount=sum(r['slowerMedian'] for r in rows),
        samplesPerCase=7,provenance=provenance,
        timingsExecutedDuringSummary=False,physicalDeviceTested=False,gameplayMeasured=False,gpuExecuted=False,
        limitations=[
            'Apple ARM64 macOS host microbenchmarks, not iPhone or gameplay measurements.',
            'Timer includes production sweep, host mutex/vector/lifetime costs; not complete emulation scheduling.',
            'Descriptor uses mocked driver boundary; no Vulkan/MoltenVK execution or GPU work is timed.',
            'Lookup uses publication/race adapter; it does not time a texture hash or an emulated frame.',
            'Seven series are retained with dispersion; no host affinity or cross-session confidence interval.',
            'Every case and slower median is retained. Overlap of sample ranges is descriptive only.',
            'The fixed-test retry does not rerun the retained timer or descriptor programs.',
        ],scriptSHA256=sha(Path(__file__)))
    args.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(caseCount=out['caseCount'],slowerMedianCount=out['slowerMedianCount'],output=str(args.output))))
    for r in rows:
        print(f"{r['family']:10s} {r['case']:30s} {r['baseline']['median']:.9g} -> {r['candidate']['median']:.9g} ns ({r['medianDurationChangePercent']:+.3f}%)")

if __name__=='__main__':
    main()
