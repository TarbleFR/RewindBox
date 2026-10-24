"""Authenticate 522 and the M1 VM probe; test the changed restore lifetime."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
import rpcs3cell522_core as previous
ROOT=Path(__file__).resolve().parents[2]
BASE='1ae41b6400688d20a8d72173d3d80d0a1fe19710'
PRIOR_RUN=40095061758;PRIOR_ARTIFACT=12559704852
PRIOR_SHA='7bd27ada1d3af6d8c6bfc717cffe41efd0623454371c085ff225504fe8890a04'
PROBE_SOURCE='77089aa283e6db0ea37c188151ea0ab1ea490b79';PROBE_RUN=40099814314;PROBE_ARTIFACT=12562336862
PROBE_SHA='f64bb116ba9ab3faf357f76cb8178c2d103d44ca9b8ed320bb0c6935400f5706'
FIXTURE='test/fixtures/rpcs3_restore523.diff'
FIXTURE_SHA='0554375cfa7d3fe3fc20e77dd101f256a9a7c1bef04cfe92675913b1807fa913'
MODIFIED={'rpcs3/Emu/Cell/PPUModule.cpp','rpcs3/Emu/Memory/vm.cpp','rpcs3/Emu/System.cpp','rpcs3/Emu/savestate_utils.cpp','rpcs3/ios/RPCS3IOS.cpp','rpcs3/Emu/RSX/VK/VKResourceManager.cpp','rpcs3/ios/RPCS3IOSPerformance.cpp'}
ADDED={'rpcs3/util/fixed_typemap.hpp','rpcs3/ios/IOSRestoreExecutor.h','rpcs3/ios/IOSGraphicsMemorySnapshot.h'}
EXTRA_INPUTS=previous.EXTRA_INPUTS+('.github/diagnostics/rpcs3cell523_core.py','.github/workflows/rpcs3-cell523-core.yml',
 'test/rpcs3_memory523_test.py','test/native/rpcs3_memory523.cpp','test/rpcs3_memory523_stream_test.py',
 'test/rpcs3_restore523_test.py','test/native/rpcs3_restore523.cpp',
 'test/rpcs3_restore_executor523_test.py','test/native/rpcs3_restore_executor523.cpp',
 'test/rpcs3_gpu_memory523_test.py','test/native/rpcs3_gpu_memory523.cpp','test/fixtures/rpcs3_shutdown523_before.inc',FIXTURE)
CHANGED=previous.CHANGED|{'build-utils/rpcs3_core_syntax_gate.py'}
command=previous.command;sha=previous.sha;pin_module=previous.pin_module;authenticated=previous.authenticated
old=lambda p:command('git','show',BASE+':'+p)
def inputs():return {**pin_module().core_input_hashes(),**{p:sha((ROOT/p).read_bytes()) for p in EXTRA_INPUTS}}
def source_contract(source=None):
 pin_module().validate_source_contract(source_root=source)
 before=json.loads(old('build-utils/rpcs3/canonical-source.json'));after=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes())
 assert {p for p in before['files_sha256'] if before['files_sha256'][p]!=after['files_sha256'].get(p)}==MODIFIED
 assert set(after['files_sha256'])-set(before['files_sha256'])==ADDED
 expected=dict(before);expected.update(files_sha256=after['files_sha256'],patch_sha256=after['patch_sha256'],cell523=after['cell523']);assert expected==after
 assert sha((ROOT/FIXTURE).read_bytes())==FIXTURE_SHA
 for p in dict.fromkeys(pin_module().CORE_INPUTS+previous.EXTRA_INPUTS):
  if p not in CHANGED:assert (ROOT/p).read_bytes()==old(p),p
 if source:
  with tempfile.TemporaryDirectory() as d:
   work=Path(d)
   for p in MODIFIED|ADDED:
    target=work/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/p).read_bytes())
   subprocess.run(['git','apply','--unidiff-zero','--reverse',str(ROOT/FIXTURE)],cwd=work,check=True)
   for p,expected in after['cell523']['before_sha256'].items():assert sha((work/p).read_bytes())==expected,p
   assert all(not (work/p).exists() for p in after['cell523']['added_paths'])
   for p in MODIFIED:assert sha((work/p).read_bytes())==before['files_sha256'][p],p
   assert sha(command('git','-C',str(source),'show','HEAD:rpcs3/util/fixed_typemap.hpp'))==after['cell523']['before_sha256']['rpcs3/util/fixed_typemap.hpp']
 return inputs()
def prepare(source,out):
 current=source_contract(source);prior=authenticated(PRIOR_RUN,BASE,PRIOR_ARTIFACT,PRIOR_SHA,'prior522')
 identity=json.loads((prior/'identity.json').read_bytes());assert identity['host_commit']==BASE
 for p,digest in identity['cell522_input_sha256'].items():
  assert sha(old(p))==digest,p
  if p not in CHANGED:assert current[p]==digest,p
 proof=json.loads((prior/'cell522-reuse.json').read_bytes());assert sha((prior/'cell522-proof.txt').read_bytes())==proof['log_sha256']
 probe=authenticated(PROBE_RUN,PROBE_SOURCE,PROBE_ARTIFACT,PROBE_SHA,'memory-probe')
 probe_id=json.loads((probe/'identity.json').read_bytes());assert probe_id['source']==PROBE_SOURCE and not probe_id['physicalDeviceTested']
 stable={'rpcs3/Emu/Memory/vm.cpp','rpcs3/Emu/Cell/PPUModule.cpp','rpcs3/Emu/System.cpp','rpcs3/util/fixed_typemap.hpp'}
 for p in stable:assert sha((source/p).read_bytes())==probe_id['nativeInputs'][p],p
 for p,digest in probe_id['fixtureInputs'].items():
  assert sha(command('git','show',PROBE_SOURCE+':'+p))==digest,p
  if p in {'test/rpcs3_memory523_test.py','test/rpcs3_memory523_stream_test.py'}:
   # Only the authenticated reverse-fixture transport gained zero-context
   # support; emitted C++, measurement loop and serial adapters are identical.
   assert (ROOT/p).read_bytes().replace(b"'--unidiff-zero',",b'')==command('git','show',PROBE_SOURCE+':'+p),p
  elif p!=FIXTURE:assert sha((ROOT/p).read_bytes())==digest,p
 correctness=json.loads((probe/'correctness.json').read_bytes());stream=json.loads((probe/'stream.json').read_bytes())
 assert correctness['passed'] and correctness['cases']==160 and correctness['sameUncompressedBytes'] and correctness['sameBreatheBoundaries']
 assert stream['passed'] and stream['realZstd'] and stream['realSerialMethods'] and len(stream['cases'])==8
 assert all(r['afterBufferCapacity']<=r['beforeBufferCapacity'] for r in stream['cases'])
 # The new queue and its cancellation/cleanup integration changed after the
 # immutable memory probe. Execute these affected paths with the actual header.
 log=ROOT/'build/rpcs3-core-diagnostics/cell523-proof.txt'
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
 outputs=[]
 for script,name in [('test/rpcs3_restore_executor523_test.py','executor'),('test/rpcs3_restore523_test.py','restore'),('test/rpcs3_gpu_memory523_test.py','gpu-memory')]:
  result=subprocess.run(['python3',script,str(source),'--report',str(log.parent/(name+'-result.json'))],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
  outputs.append(result.stdout);log.write_text('\n'.join(outputs));print(result.stdout,end='',flush=True);result.check_returncode()
 outputs.append('PASS actual owned restore lifetime + HLE/FXO diagnostics; authenticated unchanged 522 and M1 VM/ZSTD evidence\n');log.write_text('\n'.join(outputs))
 record=dict(schema=1,source=command('git','rev-parse','HEAD').decode().strip(),input_sha256=current,prior_source=BASE,prior_run=PRIOR_RUN,prior_artifact=PRIOR_ARTIFACT,prior_archive_sha256=PRIOR_SHA,
  memory_probe_source=PROBE_SOURCE,memory_probe_run=PROBE_RUN,memory_probe_artifact=PROBE_ARTIFACT,memory_probe_sha256=PROBE_SHA,
  log_sha256=sha(log.read_bytes()),fixture_sha256=FIXTURE_SHA,physical_device_tested=False)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
def verify(path):
 record=json.loads(path.read_bytes());assert record['source']==command('git','rev-parse','HEAD').decode().strip()
 assert record['input_sha256']==source_contract() and record['prior_archive_sha256']==PRIOR_SHA and record['memory_probe_sha256']==PROBE_SHA
 assert sha((ROOT/'build/rpcs3-core-diagnostics/cell523-proof.txt').read_bytes())==record['log_sha256']
 print('PASS owned restore worker, saved HLE range, exact VM stream and authenticated source-bound native proof')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--verify-reuse',type=Path);p.add_argument('--output',type=Path,default=ROOT/'build/rpcs3-core-diagnostics/cell523-reuse.json');a=p.parse_args()
 if a.verify_reuse:verify(a.verify_reuse)
 elif a.source:prepare(a.source.resolve(),a.output.resolve())
 else:source_contract();print('PASS CELL523 scoped native source and preserved runtime/host inputs')
