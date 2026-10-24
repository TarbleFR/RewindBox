"""Authenticate Build 520 proofs and execute only the four changed Core paths."""
import argparse,hashlib,json,os,shlex,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
import rpcs3v012_core as previous
ROOT=Path(__file__).resolve().parents[2]
BASE='a4b2f27775b4038b7bd143d6cf723a6fc56f5a13'
PRIOR='407ea8f7462db0645590e799adcdff9ed56b1b21'
PRIOR_RUN=40039707148
PRIOR_ARTIFACT=12540236973
PRIOR_ARCHIVE_SHA='38c69c74b756b9c45a3a31fb05b8ead1be4841f9e70ea0097fb84b59ab0b96e1'
CORE_PATHS={'rpcs3/Emu/Cell/Modules/cellVdec.cpp','rpcs3/Emu/System.cpp',
 'rpcs3/ios/NeoSwapStorage/FrameClient.h','rpcs3/ios/NeoSwapStorage/SourceClient.cpp'}
CHANGED_INPUTS={'build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch',
 'build-utils/build_rpcs3_embedded_core.sh','test/neo_swap_core_pin_test.py',
 'native/neoswap-storage/FrameClient.h','native/neoswap-storage/SourceClient.cpp',
 'test/native/rpcs3_video_frame_archive_test.cpp','test/rpcs3_video_frame_archive_test.py',
 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'}
EXTRA_INPUTS=previous.EXTRA_INPUTS+(
 '.github/diagnostics/rpcs3cell521_core.py','.github/workflows/rpcs3-cell521-core.yml',
 'test/rpcs3_frame521_read_ahead_test.py','test/native/rpcs3_frame521_read_ahead.cpp',
 'test/rpcs3_video521_loans_test.py','test/neoswap_relay_loans_test.cpp',
 'packages/neo_swap/ios/Classes/NeoSwap.cpp',
 'native/neoswap-storage/tests/frame_archive_test.cpp','native/neoswap-storage/tests/source_archive_test.cpp',
 'native/neoswap-storage/run_source_validation.py',
)
command=previous.command
sha=previous.sha
pin_module=previous.pin_module
def old(path,ref=BASE):return command('git','show',ref+':'+path)
def inputs():return {**pin_module().core_input_hashes(),**{p:sha((ROOT/p).read_bytes()) for p in EXTRA_INPUTS}}
def source_contract():
 pin_module().validate_source_contract()
 before=json.loads(old('build-utils/rpcs3/canonical-source.json'));after=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes())
 assert {p for p in before['files_sha256'] if before['files_sha256'][p]!=after['files_sha256'].get(p)}==CORE_PATHS
 assert set(before['files_sha256'])==set(after['files_sha256'])
 expected=dict(before);expected.update(files_sha256=after['files_sha256'],patch_sha256=after['patch_sha256'],cell521=after['cell521'])
 assert expected==after
 assert set(after['cell521']['changed_core_paths'])==CORE_PATHS and after['cell521']['core_abi']==30
 for path in dict.fromkeys(pin_module().CORE_INPUTS+previous.EXTRA_INPUTS):
  if path not in CHANGED_INPUTS:assert (ROOT/path).read_bytes()==old(path),path
 # Host bootstrap is the separately proven 520 delta, unchanged in 521.
 host='packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
 assert (ROOT/host).read_bytes()==old(host)
 return inputs()
def prepare(source,out):
 current=source_contract();run=previous.api('actions/runs/'+str(PRIOR_RUN))
 assert run['head_sha']==PRIOR and run['conclusion']=='success'
 diagnostics=ROOT/'build/rpcs3-core-diagnostics';diagnostics.mkdir(parents=True,exist_ok=True)
 archive=diagnostics/'prior520.zip'
 with archive.open('wb') as stream:subprocess.run(['gh','api',f'repos/TarbleFR/RewindBox/actions/artifacts/{PRIOR_ARTIFACT}/zip'],stdout=stream,check=True)
 assert sha(archive.read_bytes())==PRIOR_ARCHIVE_SHA
 with zipfile.ZipFile(archive) as bundle:
  for item in bundle.infolist():
   rel=PurePosixPath(item.filename);assert not rel.is_absolute() and '..' not in rel.parts
   if not item.is_dir():
    target=diagnostics/'prior520'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(bundle.read(item))
 identity=json.loads((diagnostics/'prior520/identity.json').read_bytes());assert identity['host_commit']==PRIOR
 for path,digest in identity['v012_input_sha256'].items():
  assert sha(old(path,PRIOR))==digest,path
  if path not in CHANGED_INPUTS:assert current[path]==digest,path
 prior=json.loads((diagnostics/'prior520/v012-reuse.json').read_bytes())
 assert sha((diagnostics/'prior520/v012-proof.txt').read_bytes())==prior['log_sha256']
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
 sdk=env['HOST_MACOS_SDK'];wrapper=diagnostics/'native-cxx'
 wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(env['CXX'])+' -isysroot '+shlex.quote(sdk)+' "$@"\n');wrapper.chmod(0o700)
 env.update(CXX=str(wrapper),SDKROOT=sdk)
 tests=[
  ['python3','test/rpcs3_frame521_read_ahead_test.py',str(source),'--sanitize'],
  ['python3','test/rpcs3_video521_loans_test.py'],
  ['python3','native/neoswap-storage/run_source_validation.py','--output','build/rpcs3-core-diagnostics/source521'],
  ['python3','test/rpcs3_source_archive_test.py',str(source)],
  ['bash','build-utils/run_vdec_archive_validation.sh',str(source)],
  ['python3','test/rpcs3_restore_eof_test.py',str(source)],
 ]
 log=diagnostics/'cell521-proof.txt'
 with log.open('w') as stream:
  for test in tests:
   result=subprocess.run(test,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=1200)
   stream.write(result.stdout);stream.flush();print(result.stdout,end='',flush=True);result.check_returncode()
  stream.write('PASS targeted CELL521 native source campaign\n')
 for name in ['frame-read-ahead.json','video-loans.json']:
  (diagnostics/name).write_bytes((ROOT/'build/rpcs3-cell521-tests'/name).read_bytes())
 record={'schema':1,'source':command('git','rev-parse','HEAD').decode().strip(),'input_sha256':current,
  'prior_source':PRIOR,'prior_run':PRIOR_RUN,'prior_artifact':PRIOR_ARTIFACT,'prior_archive_sha256':PRIOR_ARCHIVE_SHA,
  'log_sha256':sha(log.read_bytes()),'tests':tests,'changed_core_paths':sorted(CORE_PATHS),'physical_device_tested':False}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
def verify(path):
 record=json.loads(path.read_bytes());assert record['source']==command('git','rev-parse','HEAD').decode().strip()
 assert record['input_sha256']==source_contract() and record['prior_archive_sha256']==PRIOR_ARCHIVE_SHA
 log=ROOT/'build/rpcs3-core-diagnostics/cell521-proof.txt';assert sha(log.read_bytes())==record['log_sha256']
 assert 'PASS targeted CELL521 native source campaign' in log.read_text()
 print('PASS exact CELL521 native campaign; authenticated unaffected 520 proofs reused')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--verify-reuse',type=Path)
 p.add_argument('--output',type=Path,default=ROOT/'build/rpcs3-core-diagnostics/cell521-reuse.json');a=p.parse_args()
 if a.verify_reuse:verify(a.verify_reuse)
 elif a.source:prepare(a.source.resolve(),a.output.resolve())
 else:source_contract();print('PASS exact four-path Core delta and unchanged CELL/RSX/ABI/source contracts')
