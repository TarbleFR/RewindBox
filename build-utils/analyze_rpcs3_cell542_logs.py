#!/usr/bin/env python3
"""Read native telemetry and historical NeoSwap snapshots without assuming shared sessions."""
import argparse,collections,hashlib,json,re
from pathlib import Path
from analyze_rpcs3_cell534_logs import rows,fields,utc
from analyze_rpcs3_cell536_logs import summarize as original_summary, histogram_lower

def summarize(windows):
 result=original_summary(windows);low=high=0
 for w in windows:
  f=w['FRAMEPROF527'];maximum=float(f['max_ms'])*1000
  if f['histogram_upper_us']=='none':continue
  for item in f['histogram_upper_us'].split(','):
   upper,count=map(int,item.split(':'))
   if histogram_lower(upper)>500000:low+=count;high+=count
   elif upper>500000 and maximum>500000:
    high+=count
    if maximum<=upper:low+=1 # The precise maximum proves one event in this bin.
 result['over500msBounds']=[low,high]
 return result

def main():
 p=argparse.ArgumentParser()
 for name in ('rpc','milestones','neo','app','output'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();out=dict(inputs={},rpcProcesses=[],neoSnapshots=[],neoSessions=[],limitations=[])
 for path in (a.rpc,a.milestones,a.neo,a.app):out['inputs'][path.name]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
 groups=collections.defaultdict(dict)
 for path in (a.rpc,a.milestones):
  parsed,invalid=rows(path);out['inputs'][path.name]['invalidLines']=invalid
  for _,r in parsed:groups[(r['build'],r['pid'])][(r['timestamp'],r['stage'],r['message'])]=r
 for (build,pid),unique in sorted(groups.items()):
  records=sorted(unique.values(),key=lambda r:r['timestamp']);windows={};frame_tids={}
  for r in records:
   message=r['message'];data=fields(message)
   for tag in ('SHADERSTALL538','FRAMEPROF527','WAITPROF527','MEMPROF527','VDECIO528','JITPUB527','SHADERCOST534','SHADERCFG536'):
    if re.search(r'\b'+tag+r'\b',message):
     key=(data.get('session'),data.get('window'));w=windows.setdefault(key,dict(session=key[0],window=key[1]));w[tag]=dict(data,capturedUnix=r['timestamp'],capturedMonotonicUs=[r.get('clockMonotonicBeginUs'),r.get('clockMonotonicEndUs')])
     if tag=='FRAMEPROF527':frame_tids[key]=re.match(r'TID: (\d+):',message).group(1)
  frames=[w for w in windows.values() if 'FRAMEPROF527' in w]
  for r in records:
   message=r['message'];data=fields(message);begin=r.get('clockMonotonicBeginUs')
   tag=next((t for t in ('RANGELOCKPROF','SPUPROF','JITPROF','JITMEM','COREPROF_RESILIENCE') if re.search(r'\b'+t+r'\b',message)),None)
   if message.startswith('TID: ') and 'COREPROF frames=' in message:tag='COREPROF'
   if not tag or not frames or begin is None:continue
   nearest=min(frames,key=lambda w:abs(w['FRAMEPROF527']['capturedMonotonicUs'][0]-begin));delta=begin-nearest['FRAMEPROF527']['capturedMonotonicUs'][0];tid=re.match(r'TID: (\d+):',message)
   if abs(delta)>100000 or ('session' in data and data['session']!=nearest['session']) or not tid or tid.group(1)!=frame_tids[(nearest['session'],nearest['window'])]:continue
   assert tag not in nearest
   nearest[tag]=dict(data,captureDeltaFromFrameUs=delta)
  samples=[dict(fields(r['message']),timestamp=r['timestamp']) for r in records if r['stage']=='performance_sample']
  peak=max(samples,key=lambda s:int(s['memory'].split('/')[0]),default=None)
  transitions={}
  for name in ('sample_epoch','thermal','donor_lost','relay_ready','emu_state'):
   seq=[]
   for s in samples:
    if not seq or seq[-1]['value']!=s.get(name):seq.append(dict(utc=utc(s['timestamp']),value=s.get(name)))
   transitions[name]=seq
  config=next((fields(r['message']) for r in reversed(records) if 'CONFIG_LAYERS' in r['message']),None)
  if config:config={k:v for k,v in config.items() if k not in ('name','legacy_path')}
  proc=dict(build=build,pid=pid,uniqueRecords=len(records),utcRange=[utc(records[0]['timestamp']),utc(records[-1]['timestamp'])],config=config,
   stages=dict(collections.Counter(r['stage'] for r in records)),windows=sorted(windows.values(),key=lambda w:(int(w['session']),int(w['window']))),
   sampleSummary=dict(samples=len(samples),thermal=dict(collections.Counter(s.get('thermal') for s in samples)),transitions=transitions,
    peak=None if peak is None else {**{k:peak.get(k) for k in ('memory','process_resident','available','thermal','donor_lost','relay_live')},'utc':utc(peak['timestamp'])}),
   bootPhases=[dict(fields(r['message']),utc=utc(r['timestamp'])) for r in records if 'JITPROF_BOOT' in r['message']],
   freezes=[dict(utc=utc(r['timestamp']),noFramesSeconds=fields(r['message']).get('no_frames_s')) for r in records if 'FREEZE_DUMP snapshot' in r['message']],
   restoreFinalization=[dict(phase=fields(r['message']).get('phase'),utc=utc(r['timestamp'])) for r in records if any(t in r['message'] for t in ('phase=finalize_run_begin','phase=finalize_run_end'))],
   missingResourceEvents=sum('phase=missing_resource' in r['message'] for r in records),frameSummaries={})
  for session in sorted({w['session'] for w in frames}):
   selected=[w for w in frames if w['session']==session];proc['frameSummaries']['session'+session]=summarize(selected)
   full=[w for w in selected if int(w['window'])>1 and w['FRAMEPROF527'].get('state')=='3' and w['FRAMEPROF527'].get('phase')=='guest_unclassified']
   if full:proc['frameSummaries']['session'+session+'_full_running_windows']=dict(summarize(full),windows=[int(w['window']) for w in full],selection='Exclude first partial window and non-running report snapshots; no cinematic/gameplay classification.')
  # Diagnostic and milestone sinks capture the same event a few microseconds apart.
  # Deduplicate identical event fields only inside a 5 ms capture cluster.
  import datetime
  for name in ('bootPhases','freezes','restoreFinalization'):
   logical=[]
   for event in proc[name]:
    payload={k:v for k,v in event.items() if k!='utc'}
    stamp=datetime.datetime.fromisoformat(event['utc']).timestamp()
    if logical and payload=={k:v for k,v in logical[-1].items() if k not in ('utc','duplicateCaptureCount','lastCaptureUtc')} and stamp-datetime.datetime.fromisoformat(logical[-1]['utc']).timestamp()<0.005:
     logical[-1]['duplicateCaptureCount']+=1;logical[-1]['lastCaptureUtc']=event['utc']
    else:logical.append(dict(event,duplicateCaptureCount=1,lastCaptureUtc=event['utc']))
   proc[name]=logical
  proc['shaderStalls']=[dict(fields(r['message']),capturedUnix=r['timestamp'],capturedMonotonicUs=[r.get('clockMonotonicBeginUs'),r.get('clockMonotonicEndUs')]) for r in records if 'SHADERSTALL538_EVENT' in r['message']]
  proc['configLayers']=[dict({k:v for k,v in fields(r['message']).items() if k not in ('name','legacy_path')},utc=utc(r['timestamp'])) for r in records if 'CONFIG_LAYERS' in r['message']]
  proc['restarts']=[dict(reason=fields(r['message']).get('reason'),utc=utc(r['timestamp'])) for r in records if r['stage']=='internal_restart']
  proc['memoryPeaks']={k:max((int(w.get('MEMPROF527',{}).get(k,0)) for w in frames),default=0) for k in ('peak_footprint','peak_resident','peak_compressed','peak_virtual')}
  proc['vdecLifetimeMaxima']={k:max((int(w.get('VDECIO528',{}).get(k,0)) for w in frames),default=0) for k in ('prefetch_requests','prefetch_hits','prefetch_failures','prefetch_read_total_us','prefetch_read_max_us','demand_reads','demand_read_total_us','demand_read_max_us','consumer_prefetch_wait_max_us','warm_payload_peak')}
  anchors=[r for r in records if r.get('clockMonotonicBeginUs') is not None and r.get('clockMonotonicEndUs') is not None]
  offsets=[r['timestamp']*1e6-r[k] for r in anchors for k in ('clockMonotonicBeginUs','clockMonotonicEndUs')]
  shader_windows=[w['SHADERSTALL538'] for w in frames if 'SHADERSTALL538' in w]
  delays=[w['capturedMonotonicUs'][0]-int(w['report_steady_us']) for w in shader_windows]
  proc['clocks']=dict(nativeCaptureAndShaderClock='Both sources use std::chrono::steady_clock in this process.',anchors=len(anchors),observedUnixMinusSteadyUsRange=[min(offsets),max(offsets)] if offsets else None,shaderReportToNativeCaptureDelayUsRange=[min(delays),max(delays)] if delays else None,limitation='Observed clock offsets are not proof against unobserved wall-clock jumps. Individual flip timestamps are absent.')
  for event in proc['shaderStalls']:
   off=[event['capturedUnix']*1e6-value for value in reversed(event['capturedMonotonicUs'])]
   event['beginUtcBounds']=[utc((int(event['begin_us'])+value)/1e6) for value in off]
   event['endUtcBounds']=[utc((int(event['end_us'])+value)/1e6) for value in off]
   window=windows.get((event['report_session'],event['report_window']))
   if window and 'FRAMEPROF527' in window:
    frame=window['FRAMEPROF527'];event['reportWindowMaximumFrameMs']=float(frame['max_ms'])
    event['association']='Same process/report window, not an identified individual frame interval.'
  proc['slowShaderSummary']=dict(events=len(proc['shaderStalls']),dropped=sum(int(w['dropped']) for w in shader_windows),uncapturedReports=sum(w['captured']!='1' for w in shader_windows),byReportingSession={session:dict(count=sum(e['report_session']==session for e in proc['shaderStalls']),sumOperationUs=sum(int(e['duration_us']) for e in proc['shaderStalls'] if e['report_session']==session),maxOperationUs=max((int(e['duration_us']) for e in proc['shaderStalls'] if e['report_session']==session),default=0)) for session in sorted({e['report_session'] for e in proc['shaderStalls']})})
  proc['spuCacheTotals']={k:sum(int(w.get('SPUPROF',{}).get(k,0)) for w in frames) for k in ('obj_hits','obj_misses','obj_written','gameplay_attempts','loading_attempts','obj_evicted','obj_stale_dirs')}
  for freeze in proc['freezes']:
   raw=next(r for r in records if 'FREEZE_DUMP snapshot' in r['message'] and utc(r['timestamp'])==freeze['utc'])
   t=raw.get('clockMonotonicBeginUs');freeze['steadyUs']=t
   freeze['inProgressShaderEvents']=[{k:e[k] for k in ('stage','begin_us','end_us','duration_us')} for e in proc['shaderStalls'] if t and int(e['begin_us'])<=t<=int(e['end_us'])]
   freeze['association']='Snapshot capture falls inside these measured driver calls; guest flips are not timestamped individually.'
  out['rpcProcesses'].append(proc)
 neo,invalid=rows(a.neo);out['inputs'][a.neo.name]['invalidLines']=invalid;ng=collections.defaultdict(list)
 for _,r in neo:ng[(r.get('build'),r.get('pid'))].append(r)
 for (build,pid),rs in sorted(ng.items()):
  rs.sort(key=lambda r:r['timestamp']);out['neoSnapshots'].append(dict(build=build,pid=pid,rows=len(rs),utcRange=[utc(rs[0]['timestamp']),utc(rs[-1]['timestamp'])],events=dict(collections.Counter(r.get('event') for r in rs)),operationBatches=sum('batch' in r for r in rs),
   warningCounterRange=[min(r.get('iosMemoryWarningCount',0) for r in rs),max(r.get('iosMemoryWarningCount',0) for r in rs)],
   donorLossCounterRange=[min(r.get('donorLostCount',0) for r in rs),max(r.get('donorLostCount',0) for r in rs)]))
 sessions=collections.defaultdict(list)
 for _,row in neo:
  batch=row.get('batch',{})
  for event in batch.get('events',[]):
   sessions[(row.get('build'),row.get('pid'),event.get('session'))].append((row,batch,event))
 for (build,pid,session),items in sorted(sessions.items(),key=lambda item:tuple(str(v) for v in item[0])):
  events=[];dropped=0;pending=0;seen=set();complete=True
  for row,batch,e in items:
   dropped=max(dropped,batch.get('droppedEventsCumulative',0));pending=max(pending,batch.get('pendingEvents',0));complete &= batch.get('completeHistory',False)
   key=(e.get('sequence'),e.get('monotonicUs'))
   if key in seen:continue
   seen.add(key)
   event={k:e.get(k) for k in ('sequence','monotonicUs','durationUs','operation','domainKind','resultName','object','chunk','logicalBytes')}
   if all(k in batch for k in ('clockUnixUs','clockMonotonicBeginUs','clockMonotonicEndUs')):
    offsets=[batch['clockUnixUs']-batch[k] for k in ('clockMonotonicEndUs','clockMonotonicBeginUs')]
    event['utcBounds']=[utc((e['monotonicUs']+o)/1e6) for o in offsets]
   events.append(event)
  out['neoSessions'].append(dict(build=build,pid=pid,session=session,eventCount=len(events),
   events=events if any(p['pid']==pid for p in out['rpcProcesses']) else sorted(events,key=lambda e:e.get('durationUs') or 0,reverse=True)[:10],
   eventListingScope='all retained events' if any(p['pid']==pid for p in out['rpcProcesses']) else 'ten longest historical operations; counts/losses cover every retained event',
   operationCounts=dict(collections.Counter(e['operation'] for e in events)),droppedEventsCumulativeMaximum=dropped,
   pendingEventsMaximum=pending,batchesDeclareCompleteHistory=complete,
   clock='SourceArchive::now_us and native anchors use std::chrono::steady_clock; batch export time is not event time.'))
 app=a.app.read_text(errors='replace');out['app']=dict(gameDBUnavailableMessages=app.count('GameDB publication unavailable'),launchMarkers=app.count('Starting NeoStation...'),scope='Historical unaligned text; message counts are not counts for the current native process.')
 out['limitations']=['No controlled same-scene before/after pair, no video/scene annotations.', 'Histograms merge guest flip intervals; no continuous presentation timeline.', 'NeoSwap operations are grouped by process/session. No build is inferred without matching native evidence; event loss/pending counters are retained. Absence of an operation cannot characterize unretained time.', 'Summed multi-thread and nested costs are not wall time.']
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
 for p in out['rpcProcesses']:print(json.dumps({k:p[k] for k in ('build','pid','sampleSummary','spuCacheTotals')}))
if __name__=='__main__':main()
