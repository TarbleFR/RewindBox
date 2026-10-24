#!/usr/bin/env python3
"""Offline, local-only RPCS3 log analysis. No upload or automatic telemetry."""
import argparse,collections,hashlib,json,re,statistics
from pathlib import Path
FIELDS=re.compile(r'\b([a-zA-Z_][a-zA-Z_0-9]*)=([^\s]+)')
def fields(message):
 result={}
 for key,value in FIELDS.findall(message):
  try:result[key]=float(value) if '.' in value else int(value)
  except ValueError:result[key]=value
 return result
def span(values):return {'min':min(values),'median':statistics.median(values),'max':max(values)} if values else None
def analyze(directory):
 groups=collections.defaultdict(list);hashes={}
 for name in ['RPCS3-milestones.log','RPCS3-diagnostic.log','NeoSwap-v1.jsonl.previous']:
  p=directory/name;hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
  for line in p.open():
   row=json.loads(line);groups[(str(row.get('build')),str(row.get('pid')))].append((name,row))
 app=directory/'app(1).log'
 if app.exists():hashes[app.name]=hashlib.sha256(app.read_bytes()).hexdigest()
 sessions=[]
 for (build,pid),rows in sorted(groups.items(),key=lambda item:(int(item[0][0]),int(item[0][1]))):
  stamps=[float(r['timestamp']) for _,r in rows if r.get('timestamp') is not None]
  record={'build':build,'pid':pid,'observedSeconds':max(stamps)-min(stamps),'rowsByFile':dict(collections.Counter(n for n,_ in rows))}
  games=set();boots=[];restores=[];windows=[];reads=[];swaps=[];vma=[];resilience=[]
  for name,row in rows:
   message=row.get('message','');games.update(re.findall(r'\b(?:B[CL][A-Z]{2}|N[PE][A-Z]{2})[0-9]{5}\b',message))
   f=fields(message)
   if name=='RPCS3-milestones.log' and 'JITPROF_BOOT ' in message and 'wall_ms' in f:
    boots.append({k:f[k] for k in ['session','boot_kind','modules_total','modules_compiled','modules_cached','wall_ms','ppu_codegen','ppu_cache_write','ppu_pipeline','ppu_ir_passes','spu_pipeline'] if k in f})
   if name=='RPCS3-milestones.log' and 'SAVESTATE_RESTORE ' in message:
    restores.append({'relativeSeconds':float(row['timestamp'])-min(stamps),**{k:f[k] for k in ['phase','bytes','position'] if k in f}})
   if name=='RPCS3-diagnostic.log' and 'COREPROF ' in message:windows.append(f)
   if name=='RPCS3-diagnostic.log' and 'JITMEM ' in message:vma.append(f)
   if name=='RPCS3-diagnostic.log' and 'COREPROF_RESILIENCE ' in message:resilience.append(f)
   if name=='RPCS3-diagnostic.log' and 'NEOSWAP_VDEC restored_frames=' in message:reads.append(f)
   if name=='NeoSwap-v1.jsonl.previous':swaps.append(row)
  record.update(gameIDsObserved=sorted(games),bootSessions=boots,restorePhases=restores)
  if windows:
   record['coreprof']={'windows':len(windows),'sumWindowMs':sum(w.get('window_ms',0) for w in windows),
    'windowMetrics':{k:span([w[k] for w in windows if isinstance(w.get(k),(int,float))]) for k in ['avg_fps','low1_fps','p95_ms','p99_ms','memory_mib','headroom_mib','ppu_cores','spu_cores','rsx_cores','jit_cores','range_wait_ms','gpu_time_ms','gpu_fence_wait_ms']}}
  if vma:record['vma']={'samples':len(vma),'last':{k:vma[-1][k] for k in ['vma_block_bytes','vma_allocated','vma_unused']},'byteMetrics':{k:span([v[k] for v in vma]) for k in ['vma_block_bytes','vma_allocated','vma_unused']}}
  if resilience:record['resilience']={'windows':len(resilience),'sumsOfWindowCounters':{k:sum(r.get(k,0) for r in resilience) for k in ['memory_reclaims','memory_reclaim_effective','memory_reclaim_deferred','shader_cache_hits','shader_cache_misses','rsx_semaphore_wait_ms']},'maximumSeverity':max(r.get('memory_pressure_peak',0) for r in resilience)}
  if reads:record['videoDemandReads']={'loggedSamples':len(reads),'readUs':span([r['read_us'] for r in reads]),'maximumUs':max(r['max_read_us'] for r in reads)}
  if swaps:record['neoSwap']={'samples':len(swaps),'sampledSeconds':max(float(r['timestamp']) for r in swaps)-min(float(r['timestamp']) for r in swaps),
   'byteMetrics':{k:span([r[k] for r in swaps if isinstance(r.get(k),(int,float))]) for k in ['capacityBytes','processFootprintBytes','processResidentBytes','processCompressedLedgerBytes','processAvailableBytes','donorFootprintBytes']},
   'iosMemoryWarningsMax':max(r.get('iosMemoryWarningCount',0) for r in swaps),'jetsamConfirmed':any(r.get('jetsamConfirmed') for r in swaps)}
  sessions.append(record)
 return {'schema':1,'inputSHA256':hashes,'sessions':sessions,'interpretation':{
  'appLogUsedForNumericAggregation':False,'duplicateMilestonesAndDiagnosticsNotSummed':True,
  'fpsAreWindowStatisticsNotSceneLabels':True,'rangeWaitMsAreAggregatePerPresentedFrameNotWindowMs':True,'vmaUnusedIncludesFragmentationNotNecessarilyReleasableBlocks':True,'gpuMinusOneMeansUnavailable':True,
  'capacitiesAndMappedAliasesAreNotAdditionalPhysicalRam':True,'residentFootprintCompressedAreNotAdditive':True,
  'afterDeviceMeasurementsAvailable':False}}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 report=analyze(a.directory);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
 print('Separated',len(report['sessions']),'build/PID groups; local report:',a.output)
