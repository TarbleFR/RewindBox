#!/usr/bin/env python3
"""Read the mixed 534/536 attachment set without joining unrelated clocks or video."""
import argparse,collections,hashlib,json,re,subprocess
from pathlib import Path
from analyze_rpcs3_cell534_logs import rows,fields,utc
from analyze_rpcs3_cell536_logs import summarize

def main():
 p=argparse.ArgumentParser()
 for name in ('rpc','milestones','neo','app','video','output'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();out=dict(inputs={},rpcProcesses=[],neoSnapshots=[],limitations=[])
 for path in (a.rpc,a.milestones,a.neo,a.app,a.video):out['inputs'][path.name]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
 groups=collections.defaultdict(dict)
 for path in (a.rpc,a.milestones):
  parsed,invalid=rows(path);out['inputs'][path.name]['invalidLines']=invalid
  for _,r in parsed:groups[(r['build'],r['pid'])][(r['timestamp'],r['stage'],r['message'])]=r
 for (build,pid),unique in sorted(groups.items()):
  records=sorted(unique.values(),key=lambda r:r['timestamp']);windows={};frame_tids={}
  for r in records:
   message=r['message'];data=fields(message)
   for tag in ('FRAMEPROF527','WAITPROF527','MEMPROF527','VDECIO528','JITPUB527','SHADERCOST534','SHADERCFG536'):
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
   if build=='536' and session=='2':
    proc['frameSummaries']['session2_windows8to23']=summarize([w for w in selected if 8<=int(w['window'])<=23])
    proc['frameSummaries']['session2_windows16to23']=summarize([w for w in selected if 16<=int(w['window'])<=23])
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
  proc['spuCacheTotals']={k:sum(int(w.get('SPUPROF',{}).get(k,0)) for w in frames) for k in ('obj_hits','obj_misses','obj_written','gameplay_attempts','loading_attempts','obj_evicted','obj_stale_dirs')}
  out['rpcProcesses'].append(proc)
 neo,invalid=rows(a.neo);out['inputs'][a.neo.name]['invalidLines']=invalid;ng=collections.defaultdict(list)
 for _,r in neo:ng[(r.get('build'),r.get('pid'))].append(r)
 for (build,pid),rs in sorted(ng.items()):
  rs.sort(key=lambda r:r['timestamp']);out['neoSnapshots'].append(dict(build=build,pid=pid,rows=len(rs),utcRange=[utc(rs[0]['timestamp']),utc(rs[-1]['timestamp'])],events=dict(collections.Counter(r.get('event') for r in rs)),operationBatches=sum('batch' in r for r in rs),
   warningCounterRange=[min(r.get('iosMemoryWarningCount',0) for r in rs),max(r.get('iosMemoryWarningCount',0) for r in rs)],
   donorLossCounterRange=[min(r.get('donorLostCount',0) for r in rs),max(r.get('donorLostCount',0) for r in rs)]))
 app=a.app.read_text(errors='replace');out['app']=dict(gameDBUnavailableMessages=app.count('GameDB publication unavailable'),scope='Historical unaligned text; message counts are not counts for the current native process.')
 video=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(a.video)]))
 out['video']=dict(durationSeconds=float(video['format']['duration']),creationTime=video['format'].get('tags',{}).get('creation_time'),streams=[{k:s.get(k) for k in ('codec_type','width','height','avg_frame_rate','duration')} for s in video['streams']],
  relativeSceneObservations=[dict(seconds=30,scene='snow / ride'),dict(seconds=45,scene='wide cinematic view'),dict(seconds=75,scene='HUD visible'),dict(seconds=90,scene='R1 traversal prompt'),dict(seconds=120,scene='interior combat')],
  alignment='No embedded creation-time or shared monotonic anchor. Filename is not a process clock; do not align to PID29509 or infer game FPS from VFR recording.')
 out['limitations']=['536 and 534 are different process/cache/scene/thermal histories, not a controlled before-after benchmark.',
  'Guest frame distributions are merged histogram bounds, never averaged window percentiles. Intervals crossing reporting boundaries retain their full duration.',
  'Phase is a report snapshot. No reliable per-frame gameplay/cinematic labels or continuous presentation timeline.',
  'CPU/JIT/wait sums across threads and parent-child operations overlap and are not elapsed pause totals.',
  'The supplied NeoSwap snapshot file has no PID29509 and no managed-operation batches. Current restore latency, lost-operation count, dirty pages and fsync-removal effect are unavailable.',
  'Native telemetry retains explicit unavailable counts; absence of an event outside the retained window does not prove it did not happen.',
  'Footprint is sampled, not an exact peak; resident, compressed, guest relay aliases and virtual reservations must not be added as independent physical memory.',
  'No post-538 iPhone run or prolonged controlled session is available.']
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
 for p in out['rpcProcesses']:print(json.dumps({k:p[k] for k in ('build','pid','sampleSummary','spuCacheTotals')}))
if __name__=='__main__':main()
