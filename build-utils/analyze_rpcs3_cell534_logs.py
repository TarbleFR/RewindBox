#!/usr/bin/env python3
"""Separate native sessions and preserve clock/loss caveats in a small JSON report.

No raw application paths or thread dumps are copied to the output. Parent and
child operation durations are reported separately; they must never be added.
"""
import argparse, collections, datetime, hashlib, json, re
from pathlib import Path

def rows(path):
    result=[]; invalid=0
    for number,line in enumerate(path.read_text(errors='replace').splitlines(),1):
        try: item=json.loads(line)
        except (ValueError,TypeError): invalid+=1; continue
        if not isinstance(item,dict): invalid+=1; continue
        result.append((number,item))
    return result,invalid

def fields(text):
    return dict(re.findall(r'(\w+)=([^ ]+)',text))

def utc(value):
    return datetime.datetime.fromtimestamp(value,datetime.timezone.utc).isoformat()

def main():
    p=argparse.ArgumentParser();p.add_argument('--neo',type=Path,required=True)
    p.add_argument('--rpc',type=Path,required=True);p.add_argument('--milestones',type=Path,required=True)
    p.add_argument('--app',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report={'inputs':{},'neoSessions':[],'rpcProcesses':[],
        'scope':'Observed retained events only; no cross-process causation or before/after gameplay benchmark. Durations of nested operations overlap.'}
    for path in (a.neo,a.rpc,a.milestones,a.app):
        report['inputs'][path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
    groups={}
    parsed,invalid=rows(a.neo);report['neoInvalidLines']=invalid
    for line,row in parsed:
        batch=row.get('batch',{});pid=row.get('pid')
        for event in batch.get('events',[]):
            key=(pid,event['session']);g=groups.setdefault(key,{'events':{},'dropped':0,'anchors':set(),'conflicts':0})
            sequence=event['sequence']
            if sequence in g['events'] and g['events'][sequence]!=event:g['conflicts']+=1
            g['events'][sequence]=event
            g['dropped']=max(g['dropped'],batch.get('droppedEventsCumulative',0))
            if all(k in batch for k in ('clockUnixUs','clockMonotonicBeginUs','clockMonotonicEndUs')):
                g['anchors'].add((batch['clockUnixUs'],batch['clockMonotonicBeginUs'],batch['clockMonotonicEndUs']))
    for (pid,session),g in sorted(groups.items()):
        events=list(g['events'].values());by=collections.defaultdict(list)
        for e in events:by[(e['domainKind'],e['operation'])].append(e)
        item=dict(pid=pid,session=session,events=len(events),firstSequence=min(g['events']),lastSequence=max(g['events']),
            droppedEventsCumulative=g['dropped'],conflictingDuplicates=g['conflicts'],
            monotonicSpanUs=[min(e['monotonicUs'] for e in events),max(e['monotonicUs'] for e in events)],
            pairedAnchors=len(g['anchors']),operations=[],pressure=[])
        item['missingSequencesWithinRetainedSpan']=item['lastSequence']-item['firstSequence']+1-len(events)
        if g['anchors']:
            offsets=[(wall-end,wall-begin) for wall,begin,end in g['anchors']]
            item['unixMinusMonotonicUsRange']=[min(x[0] for x in offsets),max(x[1] for x in offsets)]
            item['clockCaveat']='Range includes observed anchor spread, not a guarantee against an unobserved wall-clock step. Export timestamp is not event time.'
        for (domain,operation),values in sorted(by.items()):
            slowest=max(values,key=lambda e:e['durationUs'])
            item['operations'].append(dict(domain=domain,operation=operation,count=len(values),
                totalUs=sum(e['durationUs'] for e in values),maxUs=slowest['durationUs'],
                slowest={k:slowest[k] for k in ('sequence','object','chunk','logicalBytes','monotonicUs')}))
            if operation=='restored_from_managed_chunks':
                counts=collections.Counter(e['object'] for e in values)
                item['repeatedRestoredObjectsRetained']={str(k):v for k,v in counts.items() if v>1}
            if operation=='pressure_changed':
                item['pressure']=[{k:e[k] for k in ('sequence','monotonicUs','resultName')} for e in values]
        report['neoSessions'].append(item)
    rpc=collections.defaultdict(list)
    for path in (a.rpc,a.milestones):
        parsed,invalid=rows(path);report['inputs'][path.name]['invalidLines']=invalid
        for line,row in parsed:rpc[(row.get('pid'),row.get('build'))].append(row)
    for (pid,build),items in sorted(rpc.items()):
        unique={(r.get('timestamp'),r.get('stage'),r.get('message')):r for r in items}
        items=sorted(unique.values(),key=lambda r:r['timestamp']);windows={};thermal=collections.Counter()
        for r in items:
            message=r.get('message','');data=fields(message)
            if 'thermal' in data:thermal[data['thermal']]+=1
            for tag in ('FRAMEPROF527','WAITPROF527','MEMPROF527','VDECIO528','JITPUB527','SHADERCOST534'):
                if tag in message:
                    key=(data.get('session'),data.get('window'));w=windows.setdefault(key,{'session':key[0],'window':key[1]})
                    w[tag]=data
                    w[tag]['capturedUnix']=r['timestamp']
                    w[tag]['capturedMonotonicUs']=[r.get('clockMonotonicBeginUs'),r.get('clockMonotonicEndUs')]
        config=next((fields(r['message']) for r in reversed(items) if 'CONFIG_LAYERS' in r.get('message','')),None)
        if config:config={k:v for k,v in config.items() if k not in ('name','legacy_path')}
        report['rpcProcesses'].append(dict(pid=pid,build=build,uniqueRecords=len(items),
            utcRange=[utc(items[0]['timestamp']),utc(items[-1]['timestamp'])],thermalSamples=dict(thermal),
            config=config,windows=sorted(windows.values(),key=lambda x:(int(x['session']),int(x['window']))),
            bootReports=sum('JITPROF_BOOT' in r.get('message','') for r in items),
            freezeDumps=sum('FREEZE_DUMP' in r.get('message','') for r in items),
            missingResources=[fields(r['message']) for r in items if 'phase=missing_resource' in r.get('message','')]))
    app=a.app.read_text(errors='replace')
    report['app']={'clockAndPid':'Mixed history without reliable per-line native clock/PID; no causal join attempted.',
        'gameDBUnavailableMessages':app.count('GameDB publication unavailable'),
        'freezeDumpLines':app.count('FREEZE_DUMP'),'jitBootLines':app.count('JITPROF_BOOT')}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'neoSessions':len(groups),'rpcProcesses':len(rpc),'output':str(a.output)},indent=2))
if __name__=='__main__':main()
