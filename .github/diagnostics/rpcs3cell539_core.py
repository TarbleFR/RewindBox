"""Source-bound539 pipeline cache consistency; authenticate unchanged538 evidence and rebuild actual Core."""
import argparse,hashlib,json,os,re,subprocess,sys,tempfile,zipfile
from pathlib import Path
import rpcs3cell527_core as prior
ROOT=Path(__file__).resolve().parents[2]
BASE='cb3e5d5bd2ba740164002fdb54951a482219fa22'
HOST_BASE='8a7fe586b82a8866ffaf43083318a44b39213bb5'
PRIOR_SOURCE='066a3fe6c015a3c25807a9feac07b392d2fc2cb4'
PRIOR_RUN=40190600339
PRIOR_ARTIFACT=12598296768
PRIOR_BYTES=196370
PRIOR_SHA='d2f3e2af63b73129fe86ec8df854f3280439661c0aeb6b206c285843f34c6d83'
OUT=ROOT/'build/rpcs3-core-diagnostics'
FIXTURE='test/fixtures/rpcs3_cell539.diff'
TESTS=[('cell539','test/rpcs3_cell539_test.py',[]),('writer539','test/rpcs3_writer539_test.py',[])]
EXTRA=['.github/diagnostics/rpcs3cell539_core.py','.github/workflows/rpcs3-cell539-core.yml',FIXTURE,
 'test/native/rpcs3_writer539.cpp','test/native/rpcs3_pipeline539_adapter.inc','test/native/rpcs3_pipeline_hash539.inc','test/rpcs3_memory523_test.py','test/rpcs3_cell538_test.py','test/fixtures/rpcs3_cell538.diff']
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
 before=json.loads(old('build-utils/rpcs3/canonical-source.json'));after=manifest();rec=after['cell539']
 changed={p for p,h in before['files_sha256'].items() if after['files_sha256'].get(p)!=h}
 added=set(after['files_sha256'])-set(before['files_sha256'])
 assert changed==set(rec['modified_paths']) and added==set(rec['new_files'])
 assert rec['before_sha256']=={p:before['files_sha256'][p] for p in changed}
 assert sha((ROOT/FIXTURE).read_bytes())==rec['fixture_sha256']
 assert after==dict(before,files_sha256=after['files_sha256'],patch_sha256=after['patch_sha256'],policy=after['policy'],cell539=rec)
 assert rec['baseline']==BASE and rec['codegen']==before['cell538']['codegen']
 changed_host=set(command('git','diff',HOST_BASE,'--name-only','--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').decode().splitlines())
 assert not changed_host,changed_host
 if source:
  sys.path.insert(0,str(ROOT/'test'))
  from rpcs3_cell538_test import cache_identities
  assert cache_identities(source)==rec['codegen']
  with tempfile.TemporaryDirectory() as td:
   w=Path(td)
   for p in changed|added:
    dest=w/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((source/p).read_bytes())
   subprocess.run(['git','apply','--reverse',str(ROOT/FIXTURE)],cwd=w,check=True)
   for p,h in rec['before_sha256'].items():assert sha((w/p).read_bytes().replace(b'\r\n',b'\n'))==h,p
   assert all(not (w/p).exists() for p in added)
 return inputs()
def reference():
 cache=ROOT/'build/cell539-reference';cache.mkdir(parents=True,exist_ok=True)
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
  identity,proof=(json.loads(z.read(n)) for n in ('identity.json','cell538-proof.json'))
  assert identity['host_commit']==proof['source']==PRIOR_SOURCE
  assert proof['all_tests_passed'] and not identity['device_runtime_tested']
  assert identity['sha256']=='071fc2871d6e61bfc015e21f147ec870ecf2fa65dc9440e06ff42468b16e3d7a'
  before=json.loads(old('build-utils/rpcs3/canonical-source.json'))
  assert before==json.loads(command('git','show',PRIOR_SOURCE+':build-utils/rpcs3/canonical-source.json'))
  assert identity['native_source_sha256']==proof['native_source_sha256']==before['files_sha256']
  assert identity['cell538_input_sha256']==proof['input_sha256']
  assert len(proof['tests'])==2
  for name,state in proof['tests'].items():
   assert state['passed'] and state['returncode']==0
   assert sha(z.read(name+'-result.json'))==state['report_sha256']
   assert sha(z.read(name+'-output.txt'))==state['output_sha256']
  for p,h in proof['input_sha256'].items():assert sha(command('git','show',PRIOR_SOURCE+':'+p))==h,p
  for n in ('identity.json','cell538-proof.json'):(OUT/('reference538-'+n)).write_bytes(z.read(n))
 (OUT/'reference538-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
 return dict(source=PRIOR_SOURCE,run=PRIOR_RUN,artifact=PRIOR_ARTIFACT,archiveSHA256=PRIOR_SHA,tests=2,
  historicalResults=True,coreBinaryReused=False,scope='Authenticated538 cache probe, shader records, LLVM relocation and inherited536 unchanged evidence retained. Current pipeline lookup/hash/dirty-state and writer counters execute before/after regressions; historical counter microbenchmarks are superseded. No iPhone gain claimed.')
def prepare(source):
 OUT.mkdir(parents=True,exist_ok=True);current=source_contract(source);historical=reference();reports={}
 receipt=dict(source=command('git','rev-parse','HEAD').decode().strip(),input_sha256=current,native_source_sha256=manifest()['files_sha256'],physical_device_tested=False,all_tests_passed=False,historical=historical,tests={})
 for name,script,args in TESTS:
  report=OUT/(name+'-result.json');report.unlink(missing_ok=True)
  argv=['python3',script,str(source),*args,'--report',str(report)]
  proc=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1200,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  (OUT/(name+'-output.txt')).write_bytes(proc.stdout);print(proc.stdout.decode(errors='replace'),flush=True)
  state=dict(command=argv,returncode=proc.returncode,output_sha256=sha(proc.stdout))
  if report.exists():
   payload=json.loads(report.read_bytes());state.update(report_sha256=sha(report.read_bytes()),passed=payload.get('passed') is True)
  receipt['tests'][name]=state;(OUT/'cell539-proof.json').write_text(json.dumps(receipt,indent=2)+'\n')
  assert proc.returncode==0 and state.get('passed'),name
 assert current==inputs(),'Tracked build/test inputs changed during execution'
 receipt['all_tests_passed']=True;(OUT/'cell539-proof.json').write_text(json.dumps(receipt,indent=2)+'\n')
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
 proof=verify(OUT/'cell539-proof.json')
 sys.path.insert(0,str(ROOT/'packages/dolphin_internal_bridge/ci'));from verify_ipa import macho
 core=directory/'libRPCS3Core.dylib';data=core.read_bytes();image=macho(data);assert image['platform']==2 and len(image['definedSymbols'])==88
 for marker in ['COREPROF VDECIO528','COREPROF SHADERCFG528','COREPROF SHADERCOST534','COREPROF SHADERCFG536','COREPROF SHADERSTALL538','SAVESTATE_MOUNT534','phase=missing_resource','partial_fxo_not_resumed=1','COREPROF FRAMEPROF527']:
  assert marker.encode() in data,marker
 log=(OUT/'build.log').read_text();actual={kind:re.findall(r'NeoStation '+kind+r' codegen identity: ([0-9a-f]{16})',log) for kind in ('PPU','SPU')}
 assert actual=={k:[v] for k,v in manifest()['cell539']['codegen'].items()},actual
 item=json.loads((OUT/'reference538-identity.json').read_bytes())
 item.update(host_commit=proof['source'],sha256=sha(data),source_patch_sha256=manifest()['patch_sha256'],core_input_sha256=pin_module().core_input_hashes(),cell539_input_sha256=inputs(),native_source_sha256=manifest()['files_sha256'])
 item.pop('cell538_input_sha256',None)
 assert item['source_commit']==(directory/'RPCS3_SOURCE_COMMIT.txt').read_text().strip()==manifest()['upstream_commit']
 assert item['abi_version']==int((directory/'RPCS3_IOS_ABI.txt').read_text().strip())==30
 for p in (directory/'identity.json',OUT/'identity.json'):p.write_text(json.dumps(item,indent=2)+'\n')
 (OUT/'codegen-identities.json').write_text(json.dumps(dict(actual=actual,unchangedFrom536=True,coldCompileRequiredByThisChange=False,physicalDeviceTested=False),indent=2)+'\n')
 print('PASS actual iPhone Core539: 88 exports, verified pipeline source, preserved 538 PPU/SPU identities')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--verify-reuse',type=Path);p.add_argument('--write-core-identity',type=Path);a=p.parse_args()
 if a.write_core_identity:identity(a.write_core_identity)
 elif a.verify_reuse:verify(a.verify_reuse,a.source)
 elif a.source:prepare(a.source)
 else:source_contract();print('PASS539 source contract; no binary or device claim')
