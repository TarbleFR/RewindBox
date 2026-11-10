#!/usr/bin/env python3
"""Authenticate Core1630 and build the reviewed vector, guard and occlusion delta."""
import argparse,hashlib,importlib,json,os,platform,shutil,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
import reuse_core_baseline as dependencies
import verify_core_candidate as common
from validate_runtime_reuse import child,digest,read,require,write
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'dist/melonx';EVIDENCE=OUT/'core-validation';SOURCE=ROOT/'.native-sources/MeloNX';TEST_SOURCE=ROOT/'.native-sources/MeloNX-guard-gates';CONTRACT=ROOT/'build-utils/melonx/guard-core-contract.json'

def contract():
 v=read(CONTRACT);require(v['schemaVersion']==1,'Unknown guard contract')
 require(v['freshAppleGates']==3 and v['reusedAppleGates']==36 and v['historicalAppleReceipts']==37,'Wrong gate scope')
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
 p=ROOT/'.native-sources/melonx-1630.zip';p.parent.mkdir(parents=True,exist_ok=True)
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

def validate_gate_report(data,gate,v):
 require(data['result']=='passed'and data.get('physicalDeviceTested')is False,'Affected fixture scope drift')
 common.inputs_match(data['inputs'])
 source=SOURCE if gate['sourceKind']=='pristine'else TEST_SOURCE
 for n,h in data.get('upstreamInputs',{}).items():
  require(digest(child(source,n))==h,'Changed '+gate['sourceKind']+' fixture dependency: '+n)
 baseline={**v['baselinePreparedMembers'],**v['baselineUnadaptedMembers']}
 for n,h in data.get('preimages',{}).items():
  require(n in baseline and baseline[n]==h,'Wrong fixture preimage: '+n)
 if gate['report']=='vector-register-mask-checks.json':
  path='src/Ryujinx.Cpu/LightningJit/Arm64/RegisterUtils.cs'
  paths={path,'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstTable.cs'}
  require(set(data['postimages'])==paths,'Wrong vector fixture postimage inventory')
  require(all(v['preparedMembers'][n]==h for n,h in data['postimages'].items()),'Vector fixture/compiled postimage mismatch')
  require(data['originalCrossUnitV31Preserved']is False and data['correctedCrossUnitV31Preserved']is True,'Missing actual cross-unit state regression')
  require(data['productionInstructionDecoder']and data['productionMaskFunctions']and data['productionBlockDataflow']and data['productionContextMethodsAndAssembler'],'Missing production vector fixture boundary')
  require(data['generatedArm64Executed']is False and data['hogwartsCrashCauseProven']is False,'Overstated vector proof')
 elif gate['report']=='guard-context-checks.json':
  paths={'src/Ryujinx.Cpu/LightningJit/NativeInterface.cs','src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs'}
  require(set(data['preimages'])==set(data['postimages'])==paths,'Wrong guard fixture inventory')
  require(all(v['preparedMembers'][n]==h for n,h in data['postimages'].items()),'Guard fixture/compiled postimage mismatch')
  require(data['productionNativeInterface']and data['productionGuardBody'],'Missing real diagnostic bodies')
  require(data['actualSignalHandlerExecuted']is False and data['actualNativeContextExecuted']is False,'Overstated guard proof')
 elif gate['report']=='occlusion-completion-checks.json':
  paths={'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs','src/Ryujinx.Graphics.GAL/Multithreading/ThreadedPipeline.cs','src/Ryujinx.Graphics.GAL/Multithreading/Commands/TryHostConditionalRenderingCommand.cs'}
  require(data['sourceKind']==gate['sourceKind']=='baselinePrepared','Wrong occlusion fixture source stage')
  require(set(data['preimages'])==set(data['postimages'])==paths and len(data['upstreamInputs'])==18,'Wrong occlusion fixture inventory')
  require(all(v['preparedMembers'][n]==h for n,h in data['postimages'].items()),'Occlusion fixture/compiled postimage mismatch')
  require(data['nativeQueryBoundariesDoubled']is True and data['commandTransportDoubled']is True and data['hogwartsCrashCauseProven']is False,'Overstated occlusion proof')
  control,candidate=data['reports']['control'],data['reports']['candidate']
  require(control==dict(checks=528,scenarios=75,lateSyncReproduced=12,falseHostReproduced=6,leakedReservationReproduced=4),'Missing occlusion control reproductions')
  require(candidate==dict(checks=528,scenarios=75,lateSyncReproduced=0,falseHostReproduced=0,leakedReservationReproduced=0),'Occlusion regressions remain')
 else:raise ValueError('Unexpected affected fixture: '+gate['report'])

def run_gates():
 v=contract();archive=prior_archive()
 require(not TEST_SOURCE.exists(),'Stale gate source')
 shutil.copytree(SOURCE,TEST_SOURCE,ignore=shutil.ignore_patterns('.git'))
 historical={};dispositions={};auxiliary={}
 with zipfile.ZipFile(archive)as z:
  result=json.loads(z.read('core-validation/result.json'))
  raw_index=z.read('core-validation/gates.json');index=json.loads(raw_index)
  require(result['result']=='passed'and result['execution']['source']==v['baseline']['source']and result['homebrewSimulatorSessions']==result['releasedBackingSessions']==2,'Failed baseline result')
  require(hashlib.sha256(raw_index).hexdigest()==result['gateReceiptSha256']and index['execution']==result['execution'],'Baseline gate index drift')
  before=json.loads(z.read('embedded-inputs.json'))
  require(before==v['baselinePreparationInputs'],'Baseline preparation inventory drift')
  require(set(before)<=set(v['preparationInputs']),'Removed historical input')
  require({p for p in before if before[p]!=v['preparationInputs'][p]}==set(v['changedPreparationInputs']),'Unreviewed existing preparation change')
  require(set(v['preparationInputs'])-set(before)==set(v['addedPreparationInputs']),'Unexpected added inputs')
  with zipfile.ZipFile(__import__('io').BytesIO(z.read('embedded-adapted-source.zip')))as prepared:
   require(len(prepared.namelist())==len(set(prepared.namelist()))==154,'Wrong baseline prepared inventory')
   require({n:hashlib.sha256(prepared.read(n)).hexdigest()for n in prepared.namelist()}==v['baselinePreparedMembers'],'Baseline postimage drift')
   for n in prepared.namelist():
    p=child(TEST_SOURCE,n);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(prepared.read(n))
  for n,h in v['baselineUnadaptedMembers'].items():
   require(n not in v['baselinePreparedMembers'] and digest(child(TEST_SOURCE,n))==h,'Changed pristine delta input: '+n)
  receipts={**index['receipts'],**index['retainedReceipts']}
  require(len(receipts)==37 and receipts==v['baselineReceipts'],'Historical receipt inventory drift')
  for n,h in receipts.items():
   raw=z.read(n);require(hashlib.sha256(raw).hexdigest()==h,'Historical receipt drift: '+n)
   receipt=json.loads(raw);require(receipt['result']=='passed','Failed historical fixture: '+n)
   target=child(OUT,'historical-1630/'+n);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
   historical['historical-1630/'+n]=h
   dispositions['historical-1630/'+n]=('historical-only-changed-guard-postimage'if n in v['supersededReceipts']else'unchanged-scoped-proof-not-reexecuted')
  for n,scope in v['auxiliaryHistoricalReceipts'].items():
   raw=z.read(n);require(hashlib.sha256(raw).hexdigest()==scope['sha256'],'Auxiliary historical receipt drift: '+n)
   data=json.loads(raw)
   require(scope['currentFullFixtureProof']is False and scope['supersededBy']=='occlusion-completion-checks.json','Overstated historical GAL proof')
   overlap={p:h for p,h in data['compiledProductionFiles'].items()if p in v['productionChanges']}
   require(overlap==scope['supersededProductionInputs']and len(overlap)==2,'Historical GAL changed dependency scope drift')
   require(all(digest(child(TEST_SOURCE,p))==h and v['preparedMembers'][p]!=h for p,h in overlap.items()),'Historical GAL preimage drift')
   target=child(OUT,'historical-1630/'+n);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
   auxiliary['historical-1630/'+n]=scope
 receipts={}
 for gate in v['gates']:
  script,report,source_kind=gate['script'],gate['report'],gate['sourceKind']
  target=child(OUT,report);require(not target.exists(),'Stale affected receipt: '+report)
  require(source_kind in ('pristine','baselinePrepared'),'Unknown fixture source kind')
  source=SOURCE if source_kind=='pristine'else TEST_SOURCE
  subprocess.run([sys.executable,str(ROOT/script),str(source)],check=True,timeout=gate['timeoutSeconds'])
  data=read(target);require(data['result']=='passed','Affected fixture failed: '+script)
  validate_gate_report(data,gate,v);receipts[report]=digest(target)
 for adapter in v['adapters']:importlib.import_module(adapter).apply(TEST_SOURCE)
 require(all(digest(child(TEST_SOURCE,n))==h for n,h in v['preparedMembers'].items()),'Tested source composition drift')
 # Every prepared path outside the seven reviewed changes must retain the compiled baseline bytes.
 old={**v['baselinePreparedMembers'],**v['baselineUnadaptedMembers']}
 require({n for n,h in old.items()if digest(child(TEST_SOURCE,n))!=h}==set(v['productionChanges']),'Unexpected production delta')
 write(EVIDENCE/'gates.json',dict(result='passed',execution=common.execution(),receipts=receipts,freshAppleGates=3,reusedAppleGates=36,historicalAppleReceipts=37,historicalGatesReexecuted=False,retainedReceipts=historical,retainedDisposition=dispositions,auxiliaryHistoricalReceipts=auxiliary,retainedScope='Immediate1630 provenance; startup trace guard postimage is historical only and superseded by the fresh guard fixture. The other36 direct scoped proofs retain their original boundaries. The separate older full GAL fixture is historical; its changed conditional paths have fresh bounded coverage, not a fresh full-GAL execution.',physicalDeviceTested=False))

def compiled():
 v=contract();gates=read(EVIDENCE/'gates.json');require(gates['execution']==common.execution(),'Gate execution mismatch')
 require(read(OUT/'embedded-inputs.json')==v['preparationInputs'],'Compiled preparation mismatch')
 with zipfile.ZipFile(OUT/'embedded-adapted-source.zip')as z:
  require(len(z.namelist())==len(set(z.namelist()))==len(v['preparedMembers']),'Wrong prepared member count')
  require({n:hashlib.sha256(z.read(n)).hexdigest()for n in z.namelist()}==v['preparedMembers'],'Compiled postimage mismatch')
  require(all(z.read(n)==(SOURCE/n).read_bytes()for n in z.namelist()),'Prepared archive differs from compiled source')
 for n,h in gates['receipts'].items():require(digest(OUT/n)==h,'Affected fixture receipt drift')
 for n,scope in gates['auxiliaryHistoricalReceipts'].items():require(digest(OUT/n)==scope['sha256'],'Auxiliary historical receipt drift')
 identities={};binaries={}
 for runtime in ('ios-arm64','iossimulator-arm64'):
  d=OUT/runtime;identity=read(d/'identity.json');binary=d/'Ryujinx.Library.dylib'
  require(identity['host']==common.execution()['source']and identity['adaptations']==v['preparationInputs']and identity['runtimeIdentifier']==runtime and identity['source']==read(ROOT/'build-utils/melonx/source.json'),'Wrong compiled identity')
  require(digest(binary)==identity['sha256']and binary.stat().st_size==identity['size']and len(identity['exports'])==47 and identity['embeddedLibraryAbi']==2,'Wrong core/ABI')
  symbols={l.split()[-1]for l in(d/'exports.txt').read_text().splitlines()if l.split()};require(all('_'+n in symbols for n in identity['exports']),'Missing native export')
  require('platform '+('IOS'if runtime=='ios-arm64'else'IOSSIMULATOR')+'\n'in(d/'platform.txt').read_text(),'Wrong native platform')
  common.command('xcrun','lipo',str(binary),'-verify_arch','arm64');identities[runtime]=digest(d/'identity.json');binaries[runtime]=dict(sha256=digest(binary),bytes=binary.stat().st_size)
 write(EVIDENCE/'compiled.json',dict(result='passed',execution=common.execution(),identities=identities,binaries=binaries,adaptationCount=len(v['preparationInputs']),preparedMembers=len(v['preparedMembers']),freshAppleGates=3,reusedAppleGates=36,historicalAppleReceipts=37,embeddedArchiveSha256=digest(OUT/'embedded-adapted-source.zip'),physicalDeviceTested=False,gameplayTested=False))

def finalize():
 common.finalize()
 p=EVIDENCE/'result.json';r=read(p)
 r.update(freshAppleGates=3,reusedAppleGates=36,historicalAppleReceipts=37,
          guardCoreContractSha256=digest(CONTRACT),vectorRegisterMasksCorrected=True,occlusionCompletionCorrected=True,
          lastGuestDispatchIsExactFaultPc=False,hogwartsCrashCauseProven=False,
          gpuStartupDelayFixed=False)
 r['inputs'].update({n:digest(ROOT/n)for n in ['build-utils/melonx/verify_guard_core.py','build-utils/melonx/guard-core-contract.json','packages/melonx_jit_helper/ios/Resources/melonx-universal.js']})
 write(p,r)
 (OUT/'CORE_DELIVERY.md').write_text('# RewindBox vector, guard and occlusion Core\n\n'+json.dumps(dict(execution=common.execution(),binaries=r['binaries'],freshAppleGates=3,reusedScopedAppleReceipts=36,historicalAppleReceipts=37,gameplayMeasured=False),indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare_dependencies','preflight','run_gates','compiled','finalize']);a=p.parse_args();globals()[a.phase]()
