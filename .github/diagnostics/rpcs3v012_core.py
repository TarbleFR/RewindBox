"""Authenticate unchanged Core 515 proofs; execute only affected v0.12 cases."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
BASE='555603e541dc586b60d27cac28b38e62f7df12a0'
PRIOR='a69860297d7b26dbb688df0daf16a31b42046462'
PRIOR_RUN=39982269326
PRIOR_ARTIFACT=12515026082
PRIOR_ARCHIVE_SHA='6fbbeed2437ffa7fa810dbb82782171a68b5d693fc68ffafd0298bb99554cd05'
EXTRA_INPUTS=(
 '.github/diagnostics/rpcs3v012_core.py', '.github/workflows/rpcs3-v012.yml',
 'test/rpcs3_xitrix_v012_native_test.py',
 'test/rpcs3_v012_provenance_test.py',
 'packages/rpcs3_internal_bridge/ios/Classes/RPCS3CPUCompatibility.h',
 'packages/rpcs3_internal_bridge/ios/Classes/RPCS3CPUCompatibilityPolicy.h',
 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3JitBridgePlugin.mm',
)
CHANGED_INPUTS={
 'build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch',
 'build-utils/build_rpcs3_embedded_core.sh','build-utils/rpcs3_core_syntax_gate.py',
 'test/rpcs3_build499_spu_audit_test.py','test/neo_swap_core_pin_test.py',
 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
}

def command(*args):
 return subprocess.check_output(args,cwd=ROOT)

def sha(data):return hashlib.sha256(data).hexdigest()

def old(path,ref=BASE):return command('git','show',ref+':'+path)

def pin_module():
 sys.path.insert(0,str(ROOT/'test'))
 import neo_swap_core_pin_test
 return neo_swap_core_pin_test

def inputs():
 return {**pin_module().core_input_hashes(),**{p:sha((ROOT/p).read_bytes()) for p in EXTRA_INPUTS}}

def source_contract():
 pin_module().validate_source_contract()
 before=json.loads(old('build-utils/rpcs3/canonical-source.json'))
 after=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes())
 scope=after['xitrix_v012_backports']
 assert scope['core_abi']==30 and scope['cpu_baseline']=='armv8.4-a'
 assert not scope['device_runtime_tested'] and not scope['performance_gain_measured']
 assert not scope['exact_release_source_proven']
 changed={p for p,d in before['files_sha256'].items() if after['files_sha256'].get(p)!=d}
 changed|=set(after['files_sha256'])-set(before['files_sha256'])
 assert changed==set(scope['changed_core_paths']),sorted(changed^set(scope['changed_core_paths']))
 assert set(before['files_sha256'])<=set(after['files_sha256'])
 # Everything outside the exact source delta, including restore/acquire,
 # code aliases, NeoSwap, compiler admission and optional ABIs is byte-identical.
 expected=dict(before)
 for key in ('files_sha256','patch_sha256','policy','xitrix_v012_backports'):expected[key]=after[key]
 assert expected==after
 for path in pin_module().CORE_INPUTS:
  if path not in CHANGED_INPUTS:assert (ROOT/path).read_bytes()==old(path),path
 return inputs()

def api(path):return json.loads(command('gh','api','repos/TarbleFR/RewindBox/'+path))

def prepare(source,out):
 current=source_contract()
 run=api('actions/runs/'+str(PRIOR_RUN))
 assert run['head_sha']==PRIOR and run['status']=='completed' and run['conclusion']=='success'
 diagnostics=ROOT/'build/rpcs3-core-diagnostics';diagnostics.mkdir(parents=True,exist_ok=True)
 archive=diagnostics/'prior515.zip'
 with archive.open('wb') as stream:
  subprocess.run(['gh','api',f'repos/TarbleFR/RewindBox/actions/artifacts/{PRIOR_ARTIFACT}/zip'],stdout=stream,check=True)
 assert sha(archive.read_bytes())==PRIOR_ARCHIVE_SHA
 with zipfile.ZipFile(archive) as bundle:
  for item in bundle.infolist():
   rel=PurePosixPath(item.filename);assert not rel.is_absolute() and '..' not in rel.parts
   if not item.is_dir():
    target=diagnostics/'prior515'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(bundle.read(item))
 identity=json.loads((diagnostics/'prior515/identity.json').read_bytes())
 assert identity['host_commit']==PRIOR
 for path,digest in identity['core_input_sha256'].items():
  assert sha(old(path,PRIOR))==digest,path
  if path not in CHANGED_INPUTS:assert current[path]==digest,path
 prior=json.loads((diagnostics/'prior515/gow3-reuse.json').read_bytes())
 assert sha((diagnostics/'prior515/freeze-followup-proof.txt').read_bytes())==prior['new_targeted_log_sha256']
 version=command(str(Path(command('brew','--prefix','llvm@22').decode().strip())/'bin/llvm-config'),'--version').decode().strip()
 assert version=='22.1.8',version
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
 # Upstream runners accept one executable path in CXX. Preserve the selected
 # host SDK for every child compiler rather than relying on a CLT default.
 sdk=env['HOST_MACOS_SDK']
 driver=env['CXX']
 wrapper=diagnostics/'native-cxx'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(driver)+' -isysroot '+shlex.quote(sdk)+' "$@"\n')
 wrapper.chmod(0o700)
 env.update(CXX=str(wrapper),SDKROOT=sdk)
 log=diagnostics/'v012-proof.txt'
 tests=[
  ['python3','test/rpcs3_v012_provenance_test.py'],
  ['python3','test/rpcs3_xitrix_v012_native_test.py',str(source),'--sanitize'],
  ['python3','test/rpcs3_build499_spu_audit_test.py',str(source)],
  ['python3','test/rpcs3_build483_llvm_pipeline_test.py',str(source)],
  ['python3','test/rpcs3_core_syntax_gate_test.py'],
  ['cmake','-S',str(source/'3rdparty/asmjit/asmjit'),'-B',str(diagnostics/'host-asmjit'),'-G','Ninja','-DASMJIT_STATIC=ON','-DCMAKE_BUILD_TYPE=Release'],
  ['cmake','--build',str(diagnostics/'host-asmjit'),'--parallel','3'],
  ['python3',str(source/'rpcs3/ios/tests/run-ppu-far-jump-tests.py'),'--asmjit-library',str(diagnostics/'host-asmjit/libasmjit.a')],
  ['python3',str(source/'rpcs3/ios/tests/run-ppu-far-jump-tests.py'),'--asmjit-library',str(diagnostics/'host-asmjit/libasmjit.a'),'--negative-control'],
  ['python3',str(source/'rpcs3/ios/tests/run-spu-arm64-constant-table-tests.py')],
 ]
 with log.open('w') as stream:
  for test in tests:
   result=subprocess.run(test,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=900)
   stream.write(result.stdout);stream.flush();print(result.stdout,end='',flush=True);result.check_returncode()
  stream.write('PASS targeted v0.12 native source campaign\n')
 record={'schema':1,'source':command('git','rev-parse','HEAD').decode().strip(),'input_sha256':current,
  'prior_source':PRIOR,'prior_run':PRIOR_RUN,'prior_artifact':PRIOR_ARTIFACT,'prior_archive_sha256':PRIOR_ARCHIVE_SHA,
  'llvm':version,'log_sha256':sha(log.read_bytes()),'tests':tests,'physical_device_tested':False}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')

def verify(path):
 record=json.loads(path.read_bytes())
 assert record['schema']==1 and record['source']==command('git','rev-parse','HEAD').decode().strip()
 assert record['input_sha256']==source_contract()
 assert record['prior_archive_sha256']==PRIOR_ARCHIVE_SHA and record['llvm']=='22.1.8'
 log=ROOT/'build/rpcs3-core-diagnostics/v012-proof.txt'
 assert sha(log.read_bytes())==record['log_sha256'] and 'PASS targeted v0.12 native source campaign' in log.read_text()
 print('PASS source-bound v0.12 proof; unchanged authenticated native campaigns reused')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--verify-reuse',type=Path)
 p.add_argument('--output',type=Path,default=ROOT/'build/rpcs3-core-diagnostics/v012-reuse.json');a=p.parse_args()
 if a.verify_reuse:verify(a.verify_reuse)
 elif a.source:prepare(a.source.resolve(),a.output.resolve())
 else:source_contract();print('PASS exact v0.12 source scope and preserved prior Core inputs')
