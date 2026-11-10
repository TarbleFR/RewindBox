#!/usr/bin/env python3
"""Authenticate the immediate compiled baseline and build only the Hogwarts literal-memory correction."""
import argparse,hashlib,importlib,json,os,platform,shutil,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
import reuse_core_baseline as dependencies
import verify_core_candidate as common
from validate_runtime_reuse import child,digest,read,require,write
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'dist/melonx';EVIDENCE=OUT/'core-validation';SOURCE=ROOT/'.native-sources/MeloNX';TEST_SOURCE=ROOT/'.native-sources/MeloNX-hogwarts-gates';CONTRACT=ROOT/'build-utils/melonx/hogwarts-launch-core-contract.json'

def contract():
 v=read(CONTRACT);require(v['schemaVersion']==1,'Unknown continuation contract')
 for p,h in v['inputs'].items():require(digest(ROOT/p)==h,'Changed reviewed continuation input: '+p)
 for p,h in v['preparationInputs'].items():require(digest(ROOT/p)==h,'Changed Core preparation input: '+p)
 return v

def origin(api, endpoint):
 for attempt in range(3):
  try:return dependencies.api(api,endpoint)
  except subprocess.CalledProcessError:
   if attempt==2:raise
   print('Retrying transient GitHub metadata transfer',flush=True);time.sleep(2**attempt)

def prior_archive():
 pin=contract()['baseline'];api=dict(repository='TarbleFR/RewindBox')
 r=origin(api,'actions/runs/'+str(pin['run']));j=origin(api,'actions/jobs/'+str(pin['job']));a=origin(api,'actions/artifacts/'+str(pin['artifact']))
 require(r['head_sha']==pin['source']and r['conclusion']=='success'and r['status']=='completed'and r['run_attempt']==1 and r['path']=='.github/workflows/melonx-core.yml','Wrong immediate Core baseline run')
 require(j['head_sha']==pin['source']and j['run_id']==pin['run']and j['conclusion']=='success','Wrong baseline Core job')
 require(a['digest']=='sha256:'+pin['sha256']and a['size_in_bytes']==pin['bytes']and not a['expired']and a['workflow_run']['id']==pin['run']and a['workflow_run']['head_sha']==pin['source'],'Wrong baseline Core archive')
 p=ROOT/'.native-sources/melonx-827f.zip';p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  with p.open('xb')as f:subprocess.run(['gh','api',f"repos/TarbleFR/RewindBox/actions/artifacts/{pin['artifact']}/zip"],stdout=f,check=True,timeout=300)
 require(p.stat().st_size==pin['bytes']and digest(p)==pin['sha256'],'Baseline ZIP digest mismatch');return p

def prepare_dependencies():
 v=contract()
 def reviewed_inputs(old,pin):
  expected=read(ROOT/pin['expectedInputs']);require(digest(ROOT/pin['expectedInputs'])==pin['expectedInputsSha256'],'Dependency input inventory drift')
  require(len(old)==74 and len(expected)==87 and set(expected)==set(old)|set(pin['newAdapters']),'Dependency historical composition drift')
  for p,h in old.items():
   if p!=dependencies.RECIPE:require(expected[p]==h,'Changed original dependency input: '+p)
  return v['preparationInputs']
 dependencies.verify_inputs=reviewed_inputs
 dependencies.prepare()
 write(EVIDENCE/'dependency-scope.json',dict(result='authenticated',scope='Unchanged LibHac and source-built native dependencies only',currentPreparationInputs=len(v['preparationInputs']),oldCoreGatesReexecuted=False))

def preflight():
 v=contract();require(platform.system()=='Darwin'and platform.machine()=='arm64','Apple ARM64 required')
 require(common.command('dotnet','--version')=='10.0.100','Wrong SDK')
 pin=read(ROOT/'build-utils/melonx/source.json');require(common.command('git','rev-parse','HEAD',cwd=SOURCE)==pin['revision'],'Wrong engine source')
 require(common.command('git','rev-parse','HEAD^{tree}',cwd=SOURCE)=='82a29e6f593f6244869481e9a489b8d5154175fe'and not common.command('git','status','--porcelain',cwd=SOURCE),'Upstream is not pristine')
 write(EVIDENCE/'preflight.json',dict(result='passed',execution=common.execution(),system='Darwin',architecture='arm64',preparationInputs=v['preparationInputs'],contractSha256=digest(CONTRACT),smokeInputs={p:digest(ROOT/p)for p in common.HOST_INPUTS}))

def reuse_literal_gate(v):
 pin=v['reusedLiteralGate'];api=dict(repository='TarbleFR/RewindBox')
 r=origin(api,'actions/runs/'+str(pin['run']));j=origin(api,'actions/jobs/'+str(pin['job']));a=origin(api,'actions/artifacts/'+str(pin['artifact']))
 require(r['head_sha']==pin['source']and r['status']=='completed'and r['conclusion']=='success'and r['run_attempt']==1 and r['path']=='.github/workflows/melonx-core.yml','Wrong successful literal gate producer')
 require(j['head_sha']==pin['source']and j['run_id']==pin['run']and j['conclusion']=='success','Wrong literal gate job')
 require(a['digest']=='sha256:'+pin['sha256']and a['size_in_bytes']==pin['bytes']and not a['expired']and a['workflow_run']['id']==pin['run']and a['workflow_run']['head_sha']==pin['source'],'Wrong literal gate artifact')
 p=ROOT/'.native-sources/melonx-literal-proof.zip'
 if not p.exists():
  with p.open('xb')as f:subprocess.run(['gh','api',f"repos/TarbleFR/RewindBox/actions/artifacts/{pin['artifact']}/zip"],stdout=f,check=True,timeout=300)
 require(p.stat().st_size==pin['bytes']and digest(p)==pin['sha256'],'Wrong literal proof bytes')
 with zipfile.ZipFile(p)as z:
  result=json.loads(z.read('core-validation/result.json'));index=json.loads(z.read('core-validation/gates.json'))
  require(result['result']=='passed'and result['execution']['source']==pin['source']and index['execution']['source']==pin['source'],'Failed literal producer')
  raw=z.read('literal-memory-checks.json');require(hashlib.sha256(raw).hexdigest()==index['receipts']['literal-memory-checks.json']==pin['receiptSha256'],'Changed literal receipt')
  report=json.loads(raw);require(report['result']=='passed'and report['generatedArm64Executed']is False,'Wrong literal proof scope')
  common.inputs_match(report['inputs'])
  for n,h in report['upstreamInputs'].items():require(digest(child(SOURCE,n))==h,'Changed literal code-generation input: '+n)
  with zipfile.ZipFile(__import__('io').BytesIO(z.read('embedded-adapted-source.zip')))as prepared:
   name='src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstEmitMemory.cs'
   require(hashlib.sha256(prepared.read(name)).hexdigest()==v['preparedMembers'][name],'Changed tested literal lowering')
 target=OUT/'reused-literal/literal-memory-checks.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 return {'reused-literal/literal-memory-checks.json':hashlib.sha256(raw).hexdigest()}

def run_gates():
 v=contract();archive=prior_archive();require(not TEST_SOURCE.exists(),'Stale gate source');shutil.copytree(SOURCE,TEST_SOURCE,ignore=shutil.ignore_patterns('.git'))
 retained={}
 with zipfile.ZipFile(archive)as z:
  result=json.loads(z.read('core-validation/result.json'));require(result['result']=='passed'and result['execution']['source']==v['baseline']['source']and result['homebrewSimulatorSessions']==result['releasedBackingSessions']==2,'Failed baseline result')
  before=json.loads(z.read('embedded-inputs.json'));require(before==v['baselinePreparationInputs'],'Baseline input inventory drift')
  for p,h in before.items():
   if p not in v['changedPreparationInputs']:require(v['preparationInputs'][p]==h,'Unreviewed preparation change: '+p)
  require(set(v['preparationInputs'])-set(before)==set(v['addedPreparationInputs']),'Unexpected added inputs')
  old_members=zipfile.ZipFile(__import__('io').BytesIO(z.read('embedded-adapted-source.zip')))
  require({n:hashlib.sha256(old_members.read(n)).hexdigest()for n in old_members.namelist()}==v['baselinePreparedMembers'],'Baseline postimage drift')
  for n in old_members.namelist():p=child(TEST_SOURCE,n);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(old_members.read(n))
  indexes=[('',json.loads(z.read('core-validation/gates.json'))['receipts']),('',json.loads(z.read('core-validation/gates.json'))['retainedReceipts'])]
  for prefix,index in indexes:
   for n,h in index.items():
    raw=z.read(prefix+n);require(hashlib.sha256(raw).hexdigest()==h,'Changed retained receipt: '+prefix+n)
    receipt=json.loads(raw);require(receipt['result']=='passed','Failed retained fixture')
    target=OUT/'historical-827f'/prefix/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);retained['historical-827f/'+prefix+n]=h
 require(len(retained)==35,'Expected35 original scoped Apple receipts')
 retained.update(reuse_literal_gate(v))
 receipts={}
 for script,report,with_source in v['gates']:
  target=OUT/report;require(not target.exists(),'Stale affected receipt: '+report)
  subprocess.run([sys.executable,str(ROOT/script)]+([str(TEST_SOURCE)]if with_source else[]),check=True,timeout=180)
  data=read(target);require(data['result']=='passed','Affected fixture failed: '+script)
  common.inputs_match(data['inputs']);receipts[report]=digest(target)
 for name in v['adapters']:importlib.import_module(name).apply(TEST_SOURCE)
 shutil.copyfile(ROOT/'native/melonx/EmbeddedStartupTrace.cs',TEST_SOURCE/'src/Ryujinx.Common/EmbeddedStartupTrace.cs')
 require(all(digest(TEST_SOURCE/n)==h for n,h in v['preparedMembers'].items()),'Tested source composition drift')
 write(EVIDENCE/'gates.json',dict(result='passed',execution=common.execution(),receipts=receipts,freshAppleGates=1,reusedAppleGates=36,historicalGatesReexecuted=False,retainedReceipts=retained,retainedScope='35 historical paths plus the exact successful literal-lowering gate; changed startup trace executes freshly',literalGateOrigin=v['reusedLiteralGate'],physicalDeviceTested=False))

def compiled():
 v=contract();gates=read(EVIDENCE/'gates.json');require(gates['execution']==common.execution(),'Gate execution mismatch')
 require(read(OUT/'embedded-inputs.json')==v['preparationInputs'],'Compiled preparation mismatch')
 with zipfile.ZipFile(OUT/'embedded-adapted-source.zip')as z:
  require(len(z.namelist())==len(set(z.namelist()))==len(v['preparedMembers']),'Wrong prepared member count')
  require({n:hashlib.sha256(z.read(n)).hexdigest()for n in z.namelist()}==v['preparedMembers'],'Compiled postimage mismatch')
  require(all(z.read(n)==(SOURCE/n).read_bytes()for n in z.namelist()),'Prepared archive differs from compiled source')
 for n,h in gates['receipts'].items():require(digest(OUT/n)==h,'Affected fixture receipt drift')
 identities={};binaries={}
 for runtime in ('ios-arm64','iossimulator-arm64'):
  d=OUT/runtime;identity=read(d/'identity.json');binary=d/'Ryujinx.Library.dylib'
  require(identity['host']==common.execution()['source']and identity['adaptations']==v['preparationInputs']and identity['runtimeIdentifier']==runtime and identity['source']==read(ROOT/'build-utils/melonx/source.json'),'Wrong compiled identity')
  require(digest(binary)==identity['sha256']and binary.stat().st_size==identity['size']and len(identity['exports'])==47 and identity['embeddedLibraryAbi']==2,'Wrong core/ABI')
  symbols={l.split()[-1]for l in(d/'exports.txt').read_text().splitlines()if l.split()};require(all('_'+n in symbols for n in identity['exports']),'Missing native export')
  require('platform '+('IOS'if runtime=='ios-arm64'else'IOSSIMULATOR')+'\n'in(d/'platform.txt').read_text(),'Wrong native platform')
  common.command('xcrun','lipo',str(binary),'-verify_arch','arm64');identities[runtime]=digest(d/'identity.json');binaries[runtime]=dict(sha256=digest(binary),bytes=binary.stat().st_size)
 write(EVIDENCE/'compiled.json',dict(result='passed',execution=common.execution(),identities=identities,binaries=binaries,adaptationCount=len(v['preparationInputs']),preparedMembers=len(v['preparedMembers']),freshAppleGates=1,reusedAppleGates=36,embeddedArchiveSha256=digest(OUT/'embedded-adapted-source.zip'),physicalDeviceTested=False,gameplayTested=False))

def finalize():
 common.finalize()
 p=EVIDENCE/'result.json';r=read(p);r.update(freshAppleGates=1,reusedAppleGates=36,hogwartsLaunchContractSha256=digest(CONTRACT),literalMemoryCorrection='32-bit-width-and-register31',hogwartsCrashCauseProven=False,gpuStartupDelayFixed=False)
 r['inputs'].update({n:digest(ROOT/n)for n in ['build-utils/melonx/verify_hogwarts_launch_core.py','build-utils/melonx/hogwarts-launch-core-contract.json','packages/melonx_jit_helper/ios/Resources/melonx-universal.js']});write(p,r)
 (OUT/'CORE_DELIVERY.md').write_text('# RewindBox Hogwarts launch Core\n\n'+json.dumps(dict(execution=common.execution(),binaries=r['binaries'],freshAppleGates=1,reusedScopedAppleReceipts=36,gameplayMeasured=False),indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare_dependencies','preflight','run_gates','compiled','finalize']);a=p.parse_args();globals()[a.phase]()
