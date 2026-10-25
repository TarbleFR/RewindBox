"""Reuse exact 521 native proofs; validate the bounded CELL diagnostic recorder."""
import argparse,hashlib,json,os,subprocess,tempfile,zipfile
from pathlib import Path,PurePosixPath
import rpcs3cell521_core as previous
ROOT=Path(__file__).resolve().parents[2]
BASE='93f82e6f98d9fbdf59e848e357bf85f7487af93f'
PRIOR_RUN=40093526893
PRIOR_ARTIFACT=12559508915
PRIOR_SHA='8c1e1fc11e5a65734628b53ad9074feaac9d917fe08bd76e3a650ad794410115'
PROBE_SOURCE='2deaeed298814650886cfb09a1b055bb2f365bb9'
PROBE_RUN=40094678344
PROBE_ARTIFACT=12560296853
PROBE_SHA='103fb3c50be176e2c1178c4dc6566017ba1bb59264e0e2474d0fca83a1e05129'
FIXTURE='test/fixtures/rpcs3_writer522.diff'
FIXTURE_SHA='f8a51396aa25e46fe0e966dd86b3f1a4643db28f958f5e3e9db4a046d22986b4'
EXTRA_INPUTS=previous.EXTRA_INPUTS+('.github/diagnostics/rpcs3cell522_core.py','.github/workflows/rpcs3-cell522-core.yml',
 'test/rpcs3_writer522_test.py',FIXTURE,'test/native/rpcs3_writer521_shards.h')
CHANGED={'build-utils/rpcs3/embedded-core.patch','build-utils/rpcs3/canonical-source.json',
 'build-utils/build_rpcs3_embedded_core.sh','test/neo_swap_core_pin_test.py'}
command=previous.command;sha=previous.sha;pin_module=previous.pin_module
old=lambda p:command('git','show',BASE+':'+p)
def inputs():return {**pin_module().core_input_hashes(),**{p:sha((ROOT/p).read_bytes()) for p in EXTRA_INPUTS}}
def source_contract(source=None):
 pin_module().validate_source_contract(source_root=source)
 before=json.loads(old('build-utils/rpcs3/canonical-source.json'));after=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes())
 assert {p for p in before['files_sha256'] if before['files_sha256'][p]!=after['files_sha256'].get(p)}=={'rpcs3/ios/RPCS3IOSPerformance.cpp'}
 assert set(after['files_sha256'])-set(before['files_sha256'])=={'rpcs3/ios/RPCS3IOSWriterCounters.h'}
 expected=dict(before);expected.update(files_sha256=after['files_sha256'],patch_sha256=after['patch_sha256'],cell522=after['cell522']);assert expected==after
 assert sha((ROOT/FIXTURE).read_bytes())==FIXTURE_SHA
 assert sha((ROOT/'test/native/rpcs3_writer521_shards.h').read_bytes())==after['files_sha256']['rpcs3/ios/RPCS3IOSWriterCounters.h']
 for p in dict.fromkeys(pin_module().CORE_INPUTS+previous.EXTRA_INPUTS):
  if p not in CHANGED:assert (ROOT/p).read_bytes()==old(p),p
 if source:
  with tempfile.TemporaryDirectory() as directory:
   target=Path(directory)/'rpcs3/ios/RPCS3IOSPerformance.cpp';target.parent.mkdir(parents=True);target.write_bytes((source/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_bytes())
   subprocess.run(['git','apply','--reverse',str(ROOT/FIXTURE)],cwd=directory,check=True)
   assert sha(target.read_bytes())==before['files_sha256']['rpcs3/ios/RPCS3IOSPerformance.cpp']
 return inputs()
def authenticated(run_id,source,artifact,digest,label):
 run=previous.previous.api('actions/runs/'+str(run_id));assert run['head_sha']==source and run['conclusion']=='success'
 out=ROOT/'build/rpcs3-core-diagnostics'/label;out.mkdir(parents=True,exist_ok=True);archive=out/'artifact.zip'
 with archive.open('wb') as stream:subprocess.run(['gh','api',f'repos/TarbleFR/RewindBox/actions/artifacts/{artifact}/zip'],stdout=stream,check=True)
 assert sha(archive.read_bytes())==digest
 with zipfile.ZipFile(archive) as bundle:
  for item in bundle.infolist():
   p=PurePosixPath(item.filename);assert not p.is_absolute() and '..' not in p.parts
   if not item.is_dir():target=out/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(bundle.read(item))
 return out
def prepare(source,out):
 current=source_contract(source);prior=authenticated(PRIOR_RUN,BASE,PRIOR_ARTIFACT,PRIOR_SHA,'prior521')
 identity=json.loads((prior/'identity.json').read_bytes());assert identity['host_commit']==BASE
 for p,digest in identity['cell521_input_sha256'].items():
  assert sha(old(p))==digest,p
  if p not in CHANGED:assert current[p]==digest,p
 proof=json.loads((prior/'cell521-reuse.json').read_bytes());assert sha((prior/'cell521-proof.txt').read_bytes())==proof['log_sha256']
 probe=authenticated(PROBE_RUN,PROBE_SOURCE,PROBE_ARTIFACT,PROBE_SHA,'writer-probe')
 measurement=json.loads((probe/'measurements.json').read_bytes());assert measurement['source']==PROBE_SOURCE and measurement['concurrentShardConservation'] and measurement['shardThreads']==96
 assert measurement['shardHeaderSHA256']==sha((ROOT/'test/native/rpcs3_writer521_shards.h').read_bytes())
 log=ROOT/'build/rpcs3-core-diagnostics/cell522-proof.txt';env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
 result=subprocess.run(['python3','test/rpcs3_writer522_test.py',str(source)],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
 log.write_text(result.stdout);print(result.stdout,end='',flush=True);result.check_returncode()
 log.write_text(log.read_text()+'PASS targeted CELL522 production recorder/drain campaign\n')
 record=dict(schema=1,source=command('git','rev-parse','HEAD').decode().strip(),input_sha256=current,prior_source=BASE,prior_run=PRIOR_RUN,prior_artifact=PRIOR_ARTIFACT,prior_archive_sha256=PRIOR_SHA,
  writer_probe_source=PROBE_SOURCE,writer_probe_run=PROBE_RUN,writer_probe_artifact=PROBE_ARTIFACT,writer_probe_sha256=PROBE_SHA,
  log_sha256=sha(log.read_bytes()),fixture_sha256=FIXTURE_SHA,physical_device_tested=False)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
def verify(path):
 record=json.loads(path.read_bytes());assert record['source']==command('git','rev-parse','HEAD').decode().strip()
 assert record['input_sha256']==source_contract() and record['prior_archive_sha256']==PRIOR_SHA and record['writer_probe_sha256']==PROBE_SHA
 log=ROOT/'build/rpcs3-core-diagnostics/cell522-proof.txt';assert sha(log.read_bytes())==record['log_sha256']
 print('PASS bounded writer counters and exact 521 proof reuse; CELL lock protocol untouched')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--verify-reuse',type=Path);p.add_argument('--output',type=Path,default=ROOT/'build/rpcs3-core-diagnostics/cell522-reuse.json');a=p.parse_args()
 if a.verify_reuse:verify(a.verify_reuse)
 elif a.source:prepare(a.source.resolve(),a.output.resolve())
 else:source_contract();print('PASS CELL522 two-path runtime diagnostic delta; JIT and emulation protocol unchanged')
