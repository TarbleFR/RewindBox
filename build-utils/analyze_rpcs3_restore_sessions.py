#!/usr/bin/env python3
"""Local RPCS3 evidence, partitioned by build/PID and recorded boot epoch.

Reads explicit local attachments. It sends nothing and does not interpret
capacity, mapped aliases or cumulative archive bytes as extra physical RAM.
"""
import argparse,collections,hashlib,json,re,statistics
from pathlib import Path
from analyze_rpcs3_cell_sessions import fields,span
METRICS=['avg_fps','low1_fps','p95_ms','p99_ms','memory_mib','headroom_mib','ppu_cores','spu_cores','rsx_cores','jit_cores','range_wait_ms','gpu_time_ms']
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--build',default='522');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 names={'diagnostic':'RPCS3-diagnostic(1).log','milestones':'RPCS3-milestones(1).log','operations':'NeoSwap-operations.jsonl','app':'app(2).log'}
 hashes={k:dict(name=n,bytes=(a.directory/n).stat().st_size,sha256=hashlib.sha256((a.directory/n).read_bytes()).hexdigest()) for k,n in names.items()}
 rows={k:[json.loads(s) for s in (a.directory/n).read_text().splitlines()] for k,n in names.items() if k!='app'}
 inventory={k:[dict(build=b,pid=pid,rows=n) for (b,pid),n in collections.Counter((str(x.get('build')),x.get('pid')) for x in v).items()] for k,v in rows.items() if k!='operations'}
 runtimes=[]
 pids=sorted({r['pid'] for r in rows['diagnostic'] if str(r.get('build'))==a.build})
 for pid in pids:
  diag=[r for r in rows['diagnostic'] if str(r.get('build'))==a.build and r['pid']==pid]
  mile=[r for r in rows['milestones'] if str(r.get('build'))==a.build and r['pid']==pid]
  start=min(r['timestamp'] for r in diag+mile);end=max(r['timestamp'] for r in diag+mile)
  phase=[];epochs={1:start};boots=[]
  for r in diag:
   f=fields(r.get('message',''))
   if r['stage']=='neoswap_guest_sample' and f.get('phase')=='before_boot':epochs[int(f['sample_epoch'])]=r['timestamp']
   if 'SAVESTATE_RESTORE ' in r.get('message',''):phase.append(dict(seconds=r['timestamp']-start,**{k:f[k] for k in ['phase','bytes','position'] if k in f}))
  for r in mile:
   f=fields(r.get('message',''))
   if 'JITPROF_BOOT ' in r.get('message','') and 'wall_ms' in f:boots.append(f)
  sessions=[];ordered=sorted(epochs.items(),key=lambda x:x[1])
  for index,(epoch,begin) in enumerate(ordered):
   stop=ordered[index+1][1] if index+1<len(ordered) else end+1
   selected=[r for r in diag if begin<=r['timestamp']<stop]
   windows=[dict(seconds=r['timestamp']-start,**fields(r['message'])) for r in selected if 'COREPROF ' in r.get('message','')]
   perf=[dict(seconds=r['timestamp']-start,**fields(r['message'])) for r in selected if r['stage']=='performance_sample']
   video=[dict(seconds=r['timestamp']-start,**fields(r['message'])) for r in selected if 'NEOSWAP_VDEC ' in r.get('message','')]
   vma=[fields(r['message']) for r in selected if 'JITMEM ' in r.get('message','')]
   resilience=[fields(r['message']) for r in selected if 'COREPROF_RESILIENCE ' in r.get('message','')]
   spu=[fields(r['message']) for r in selected if 'SPUPROF ' in r.get('message','')]
   memory=[int(str(x['memory']).split('/')[0]) for x in perf if 'memory' in x]
   sessions.append(dict(sampleEpoch=epoch,beginSeconds=begin-start,endSeconds=min(stop,end)-start,
    scene='not labelled by the supplied capture; FPS does not identify menu/cinematic/gameplay',
    coreprofWindows=len(windows),metrics={k:span([r[k] for r in windows if isinstance(r.get(k),(int,float))]) for k in METRICS},
    firstWindowBelow30=next((r for r in windows if r.get('avg_fps',60)<30),None),lastCoreprof=windows[-1] if windows else None,
    sampledFootprintBytes=span(memory),thermalSamples=dict(collections.Counter(str(r.get('thermal')) for r in perf)),lastPerformance=perf[-1] if perf else None,
    videoArchiveAndRestoreNotices=video,lastVMA=vma[-1] if vma else None,
    windowCounterSums={k:sum(r.get(k,0) for r in resilience) for k in ['memory_reclaims','memory_reclaim_effective','shader_cache_hits','shader_cache_misses','rsx_semaphore_wait_ms','rsx_semaphore_stalls','rsx_semaphore_timeouts']},
    spuObjectWindowSums={k:sum(r.get(k,0) for r in spu) for k in ['obj_hits','obj_misses','obj_written','loading_attempts','gameplay_attempts','gameplay_total_ms']}))
  operations=[r for r in rows['operations'] if r.get('pid')==pid];events={}
  for batch in operations:
   for e in batch['batch']['events']:events[(e['session'],e['sequence'])]=e
  groups=collections.defaultdict(list)
  for e in events.values():groups[(e['domain'],e['operation'])].append(e)
  runtime=dict(build=a.build,pid=pid,observedSeconds=end-start,rows=len(diag),stages=dict(collections.Counter(r['stage'] for r in diag)),
    gameIDs=sorted({x for r in diag for x in re.findall(r'\b(?:B[CL][A-Z]{2}|N[PE][A-Z]{2})[0-9]{5}\b',r.get('message',''))}),
    bootProfiles=boots,restorePhases=phase,sessions=sessions,
    operations=dict(batches=len(operations),uniqueEvents=len(events),sessionIDs=sorted({key[0] for key in events}),
     buildFieldPresent=any('build' in r for r in operations),association='same PID and overlapping capture timestamps; operations have no build field',
     completeHistory=all(r['batch']['completeHistory'] for r in operations),droppedEventsMax=max((r['batch']['droppedEventsCumulative'] for r in operations),default=0),
     byDomainAndOperation=[dict(domain=d,operation=o,count=len(items),durationUs=span([e['durationUs'] for e in items]),logicalBytes=sum(e['logicalBytes'] for e in items)) for (d,o),items in sorted(groups.items())]))
  runtimes.append(runtime)
 record=dict(schema=1,inputSHA256=hashes,inventory=inventory,selectedBuild=a.build,runtimes=runtimes,limits={
  'noMatchedSceneBeforeAfter':True,'noSceneClassificationFromFPS':True,'noGPUTimeWhenMinusOne':True,
  'rangeWaitIsAggregateAcrossThreadsPerPresentedFrame':True,'mappedAliasesResidentCompressedFootprintNotAdditive':True,
  'configuredCapacityNotPhysicalRAM':True,'cumulativeArchivedBytesNotLiveSavings':True,
  'vmaUnusedMayIncludeFragmentation':True,'restoreLogEndDoesNotProveDeadlockOrCrashCause':True,
  'milestoneDuplicatesExcludedFromWindowSums':True,'missingOperationEventsPreventCompleteTotals':True})
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(record,indent=2)+'\n')
 print('Selected',len(runtimes),'runtime(s); older build/PID rows inventoried separately; no transmission')
if __name__=='__main__':main()
