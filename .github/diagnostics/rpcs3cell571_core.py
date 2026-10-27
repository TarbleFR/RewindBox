"""Source-bound571 passive-lock fairness: authenticate the569 Core and run every571 case before building the actual iPhone Core."""
import argparse,hashlib,json,os,re,subprocess,sys,tempfile,zipfile
from pathlib import Path
import rpcs3cell527_core as prior
ROOT=Path(__file__).resolve().parents[2]
BASE='92ea4ef0b19ec841a25667f5915d336b606ff0f9'
# Core-only571 changes no product source: the commit that records cell563 is
# compared with its parent, so concurrent product commits on Claude stay theirs.
HOST_ALLOWED=set()
PRIOR_SOURCE='e70fa381297f53808db3e136ae9df65718daca3a'
PRIOR_RUN=40566094740
PRIOR_ARTIFACT=12762744843
PRIOR_BYTES=203119
PRIOR_SHA='b0ef9f5293b3abc337d5528e20cee2c14a1b380ce9ca0881e37a4b3afbaeb897'
PRIOR_CORE_SHA='7fd4739453c5aba9f638ee33e413d5abea584cef5087b4b8079860c1d06b2537'
OUT=ROOT/'build/rpcs3-core-diagnostics'
FIXTURE='test/fixtures/rpcs3_cell571.diff'
TESTS=[('cell571','test/rpcs3_cell571_test.py',[])]
# The 571 test imports its source helpers from the 559 and 538 tests.
EXTRA=['.github/diagnostics/rpcs3cell571_core.py','.github/workflows/rpcs3-cell571-core.yml',FIXTURE,
 'test/native/rpcs3_passive_gate571.inc','test/rpcs3_cell559_test.py',
 'test/rpcs3_cell538_test.py','build-utils/rpcs3/patch_moltenvk_compile_qos.py']
# This allowlist is deliberately closed; adding a production path requires review.
REVIEWED_PATHS={
 'rpcs3/Emu/Memory/vm.cpp','rpcs3/Emu/system_config.h','rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp',
 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h','rpcs3/ios/RPCS3IOSSettings.cpp','rpcs3/ios/IOSPassiveLockGate.h'}
sha=prior.sha;command=prior.command;pin_module=prior.pin_module

def manifest():return json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes())
def old(p):return command('git','show',BASE+':'+p)
def inputs():
 paths=set(pin_module().CORE_INPUTS)|set(EXTRA)|{t[1] for t in TESTS}
 paths|=set(command('git','ls-files','--','native/neoswap-storage').decode().splitlines())
 paths|={'build-utils/validate_source_archive_evidence.py'}
 paths|=set(command('git','ls-files','--','packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan').decode().splitlines())
 return {p:sha((ROOT/p).read_bytes()) for p in sorted(paths)}
def source_contract(source=None):
 pin_module().validate_source_contract(source_root=source)
 before=json.loads(old('build-utils/rpcs3/canonical-source.json'));after=manifest();rec=after['cell571']
 changed={p for p,h in before['files_sha256'].items() if after['files_sha256'].get(p)!=h}
 added=set(after['files_sha256'])-set(before['files_sha256'])
 assert changed==set(rec['modified_paths']) & set(before['files_sha256'])
 assert added==set(rec['new_files']) | (set(rec['modified_paths'])-set(before['files_sha256']))
 assert all(rec['before_sha256'][p]==before['files_sha256'][p] for p in changed)
 assert sha((ROOT/FIXTURE).read_bytes())==rec['fixture_sha256']
 assert after==dict(before,files_sha256=after['files_sha256'],patch_sha256=after['patch_sha256'],cell571=rec)
 assert rec['baseline']==BASE and rec['codegen']==before['cell569']['codegen']
 assert rec['core_baseline_patch_sha256']==before['patch_sha256'] and rec['core_baseline_sha256']==PRIOR_CORE_SHA
 assert set(rec['modified_paths']) | set(rec['new_files']) <= REVIEWED_PATHS
 assert set(rec['before_sha256']) == set(rec['modified_paths'])
 assert set(rec['after_sha256']) == set(rec['modified_paths']) | set(rec['new_files'])
 assert all(after['files_sha256'][p] == h for p,h in rec['after_sha256'].items())
 assert set(before['files_sha256']) <= set(after['files_sha256']), 'A previous Core source disappeared'
 assert before['cell551']['moltenvk_archive']['patched_sha256'] in (ROOT/'build-utils/rpcs3/patch_moltenvk_compile_qos.py').read_text()
 core=command('git','log','-1','--format=%H','-S','"cell571": {','--','build-utils/rpcs3/canonical-source.json').decode().strip() or 'HEAD'
 changed_host=set(command('git','diff','--name-only',core+'~1',core,'--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').decode().splitlines())
 assert changed_host<=HOST_ALLOWED,changed_host-HOST_ALLOWED
 if source:
  sys.path.insert(0,str(ROOT/'test'))
  from rpcs3_cell538_test import cache_identities
  assert cache_identities(source)==rec['codegen']
  with tempfile.TemporaryDirectory() as td:
   w=Path(td)
   for p in set(rec['modified_paths'])|set(rec['new_files']):
    dest=w/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((source/p).read_bytes())
   subprocess.run(['git','apply','--reverse',str(ROOT/FIXTURE)],cwd=w,check=True)
   for p,h in rec['before_sha256'].items():assert sha((w/p).read_bytes().replace(b'\r\n',b'\n'))==h,p
   assert all(not (w/p).exists() for p in rec['new_files'])
   for p in set(rec['modified_paths'])-set(before['files_sha256']):
    upstream=subprocess.check_output(['git','show',before['upstream_commit']+':'+p],cwd=source)
    assert sha(upstream.replace(b'\r\n',b'\n'))==rec['before_sha256'][p],p
 return inputs()
def reference():
 cache=ROOT/'build/cell571-reference';cache.mkdir(parents=True,exist_ok=True)
 def api(s):return json.loads(command('gh','api','repos/TarbleFR/RewindBox/'+s))
 metadata={'run':api('actions/runs/'+str(PRIOR_RUN)),'artifact':api('actions/artifacts/'+str(PRIOR_ARTIFACT))}
 run,artifact=metadata['run'],metadata['artifact']
 assert run['head_sha']==PRIOR_SOURCE and run['status']=='completed' and run['conclusion']=='success'
 assert artifact['id']==PRIOR_ARTIFACT and not artifact['expired'] and artifact['size_in_bytes']==PRIOR_BYTES
 assert artifact['digest']=='sha256:'+PRIOR_SHA and artifact['workflow_run']['id']==PRIOR_RUN
 path=cache/'reference.zip'
 with path.open('wb') as stream:subprocess.run(['gh','api',f'repos/TarbleFR/RewindBox/actions/artifacts/{PRIOR_ARTIFACT}/zip'],stdout=stream,check=True,timeout=240)
 assert path.stat().st_size==PRIOR_BYTES and sha(path.read_bytes())==PRIOR_SHA
 with zipfile.ZipFile(path) as z:
  identity,proof,codegen=(json.loads(z.read(n)) for n in ('identity.json','cell569-proof.json','codegen-identities.json'))
  assert identity['host_commit']==proof['source']==PRIOR_SOURCE
  assert proof['all_tests_passed'] and not identity['device_runtime_tested'] and proof['physical_device_tested'] is False
  assert identity['sha256']==PRIOR_CORE_SHA
  before=json.loads(old('build-utils/rpcs3/canonical-source.json'))
  assert before==json.loads(command('git','show',PRIOR_SOURCE+':build-utils/rpcs3/canonical-source.json'))
  assert identity['native_source_sha256']==proof['native_source_sha256']==before['files_sha256']
  assert identity['source_patch_sha256']==before['patch_sha256']
  assert identity['cell569_input_sha256']==proof['input_sha256']
  assert codegen['actual']=={k:[v] for k,v in before['cell569']['codegen'].items()} and codegen['coldCompileRequiredByThisChange'] is False
  assert set(proof['tests'])=={'cell569'}
  for name,state in proof['tests'].items():
   assert state['passed'] and state['returncode']==0
   assert sha(z.read(name+'-result.json'))==state['report_sha256']
   assert sha(z.read(name+'-output.txt'))==state['output_sha256']
  for p,h in proof['input_sha256'].items():assert sha(command('git','show',PRIOR_SOURCE+':'+p))==h,p
  for n in ('identity.json','cell569-proof.json','codegen-identities.json'):(OUT/('reference569-'+n)).write_bytes(z.read(n))
 (OUT/'reference569-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
 return dict(source=PRIOR_SOURCE,run=PRIOR_RUN,artifact=PRIOR_ARTIFACT,archiveSHA256=PRIOR_SHA,coreSHA256=PRIOR_CORE_SHA,tests=1,
  historicalResults=True,coreBinaryReused=False,scope='Authenticated569 Core evidence is historical. Current571 tests execute every571 change against the exact569 preimages. No iPhone gain claimed.')
def prepare(source):
 OUT.mkdir(parents=True,exist_ok=True);current=source_contract(source);historical=reference();reports={}
 receipt=dict(source=command('git','rev-parse','HEAD').decode().strip(),input_sha256=current,native_source_sha256=manifest()['files_sha256'],physical_device_tested=False,all_tests_passed=False,historical=historical,tests={})
 for name,script,args in TESTS:
  report=OUT/(name+'-result.json');report.unlink(missing_ok=True)
  argv=['python3',script,str(source),*args,'--report',str(report)]
  proc=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=2400,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  (OUT/(name+'-output.txt')).write_bytes(proc.stdout);print(proc.stdout.decode(errors='replace'),flush=True)
  state=dict(command=argv,returncode=proc.returncode,output_sha256=sha(proc.stdout))
  if report.exists():
   payload=json.loads(report.read_bytes());state.update(report_sha256=sha(report.read_bytes()),passed=payload.get('passed') is True)
  receipt['tests'][name]=state;(OUT/'cell571-proof.json').write_text(json.dumps(receipt,indent=2)+'\n')
  assert proc.returncode==0 and state.get('passed'),name
 assert current==inputs(),'Tracked build/test inputs changed during execution'
 receipt['all_tests_passed']=True;(OUT/'cell571-proof.json').write_text(json.dumps(receipt,indent=2)+'\n')
def verify(path,source=None):
 proof=json.loads(path.read_bytes());assert proof['source']==command('git','rev-parse','HEAD').decode().strip()
 current=source_contract(source)
 assert proof['input_sha256']==current,{p for p in set(current)|set(proof['input_sha256']) if current.get(p)!=proof['input_sha256'].get(p)}
 assert proof['native_source_sha256']==manifest()['files_sha256']
 assert proof['all_tests_passed'] and proof['physical_device_tested'] is False
 assert set(proof['tests'])=={t[0] for t in TESTS}
 for name,state in proof['tests'].items():
  assert state['returncode']==0 and state['passed']
  assert sha((OUT/(name+'-result.json')).read_bytes())==state['report_sha256']
  assert sha((OUT/(name+'-output.txt')).read_bytes())==state['output_sha256']
 return proof

def identity(directory):
 proof=verify(OUT/'cell571-proof.json')
 sys.path.insert(0,str(ROOT/'packages/dolphin_internal_bridge/ci'));from verify_ipa import macho
 core=directory/'libRPCS3Core.dylib';data=core.read_bytes();image=macho(data);assert image['platform']==2 and len(image['definedSymbols'])==88
 for marker in ['COREPROF RSXSYNC551','COREPROF SPUWAIT551','Applying database config under the custom config','MoltenVK asynchronous submits enabled for this boot','MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS','MoltenVK Asynchronous Submits','COREPROF PRESSURE547','SPUWARMUP duplicates removed=','Invalid installation directory name','PKG entry path escapes installation directory','context543=1 origin=','COREPROF SHADERPUB543','COREPROF SHADERPIPE543','COREPROF SHADERFEEDBACK543','NEOSTATION_CELL543_PIPELINE_CACHE','context542=1 properties=', 'COREPROF VDECIO528','COREPROF SHADERCFG528','COREPROF SHADERCOST534','COREPROF SHADERCFG536','COREPROF SHADERSTALL538','SAVESTATE_MOUNT534','phase=missing_resource','partial_fxo_not_resumed=1','COREPROF FRAMEPROF527',
               'fingerprint_scope=recent64','texture_hash_counter_hz=','texture_trim_scope=frame_end_all_sizes','READBACK555',
               'COREPROF OPT559','dirty_hash_releases=','dma_flush_skips=','rt_reload_skips=','bytes_scope=section_ranges_not_transfers',
               'epoch_skips=','Texture Validation Per FIFO Batch','texture_validation_epoch=',
               'COREPROF OPT560','deferred_fbo_writeback=','forced_writebacks=','Deferred Framebuffer Write-back',
               'experimental.deferred_fbo_writeback','fbo_commit','fault_read','fault_write',
               'COREPROF OPT561','early_submit=','early_submits=','gpu_busy_checks=','Early Command Buffer Submission',
               'experimental.early_submit','No-op PUTLLC Keeps Reservations','experimental.noop_putllc_keeps_reservations',
               'RSX Idle Park','experimental.rsx_idle_park','RSX Thread Priority','experimental.rsx_thread_priority',
               'rsx_idle_park=%d rsx_thread_priority=%d','Passive Lock Fairness','experimental.passive_lock_fairness',
               'rsx_thread_priority=%d passive_fairness=%d']:
  assert marker.encode() in data,marker
 log=(OUT/'build.log').read_text();actual={kind:re.findall(r'NeoStation '+kind+r' codegen identity: ([0-9a-f]{16})',log) for kind in ('PPU','SPU')}
 assert actual=={k:[v] for k,v in manifest()['cell571']['codegen'].items()},actual
 assert 'MoltenVK compile QoS hook linked' in log and 'b91a46f74456949aa2a6cb73de9696d0b5508efe3a7c30041e0ff07232fc9de4' in log
 undefined=subprocess.check_output(['nm','-u',str(core)]).decode().split()
 assert '_rbx_mvk_compile_qos_queue' not in undefined
 item=json.loads((OUT/'reference569-identity.json').read_bytes())
 item.update(host_commit=proof['source'],sha256=sha(data),source_patch_sha256=manifest()['patch_sha256'],core_input_sha256=pin_module().core_input_hashes(),cell571_input_sha256=inputs(),native_source_sha256=manifest()['files_sha256'])
 item.pop('cell569_input_sha256',None)
 assert item['source_commit']==(directory/'RPCS3_SOURCE_COMMIT.txt').read_text().strip()==manifest()['upstream_commit']
 assert item['abi_version']==int((directory/'RPCS3_IOS_ABI.txt').read_text().strip())==30
 for p in (directory/'identity.json',OUT/'identity.json'):p.write_text(json.dumps(item,indent=2)+'\n')
 (OUT/'codegen-identities.json').write_text(json.dumps(dict(actual=actual,unchangedFrom569=True,coldCompileRequiredByThisChange=False,physicalDeviceTested=False),indent=2)+'\n')
 print('PASS actual iPhone Core571: exact571 source and tests, 88 exports, retained561 markers and preserved PPU/SPU identities')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--verify-reuse',type=Path);p.add_argument('--write-core-identity',type=Path);a=p.parse_args()
 if a.write_core_identity:identity(a.write_core_identity)
 elif a.verify_reuse:verify(a.verify_reuse,a.source)
 elif a.source:prepare(a.source)
 else:source_contract();print('PASS571 source contract; no binary or device claim')
