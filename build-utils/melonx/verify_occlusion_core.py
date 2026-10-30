#!/usr/bin/env python3
"""Authenticate the Core87 baseline, test the reviewed delta, and build via the existing Apple recipe."""
import argparse,hashlib,importlib,json,os,platform,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
import verify_gpu_core as historical
import verify_core_candidate as previous
import reuse_core_baseline as baseline
from validate_runtime_reuse import read,write,digest,require
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dist/melonx';EVIDENCE=OUT/'core-validation';SOURCE=ROOT/'.native-sources/MeloNX'
TEST_SOURCE=ROOT/'.native-sources/MeloNX-occlusion-gates'
CONTRACT=ROOT/'build-utils/melonx/occlusion-core-contract.json'


def contract():
 v=read(CONTRACT)
 require(v['schemaVersion']==1,'Unknown occlusion core contract')
 for p,h in v['inputs'].items():require(digest(ROOT/p)==h,'Changed reviewed input: '+p)
 historical_contract(v) # authenticate every old guard with an explicit reviewed delta
 return v


def historical_contract(current=None):
 # Keep the original frozen verifier unchanged. Only these three reviewed
 # recipe/host inputs differ; authenticate their before AND after inventories.
 current=current or read(CONTRACT)
 old=read(historical.CONTRACT)
 changes=current['reviewedHistoricalChanges']
 require(set(changes)=={'.github/workflows/melonx-core.yml','build-utils/melonx/prepare_embedded.py','native/melonx/EmbeddedGraphicsSettings.cs'},'Historical delta scope drift')
 for p,h in old['inputs'].items():
  if p in changes:
   require(changes[p]['before']==h and digest(ROOT/p)==changes[p]['after']==current['inputs'][p],'Reviewed historical input drift: '+p)
  else:require(digest(ROOT/p)==h,'Changed historical input: '+p)
 return old


def preparation_inputs():
 v=contract();current=v['preparationInputs'];old=historical_contract()['preparationInputs']
 previous.inputs_match(current)
 require(set(current)-set(old)==set(v['addedPreparationInputs']),'Unexpected added preparation input')
 require(set(old)-set(current)==set(),'Removed historical preparation input')
 require({p for p in old if old[p]!=current[p]}=={'build-utils/melonx/prepare_embedded.py','native/melonx/EmbeddedGraphicsSettings.cs'},'Unexpected changed historical input')
 return current


def prepare_dependencies():
 current=preparation_inputs()
 def reviewed_delta(old,pin):
  expected=read(ROOT/pin['expectedInputs'])
  require(digest(ROOT/pin['expectedInputs'])==pin['expectedInputsSha256'],'Engine82 inventory drift')
  require(len(old)==74 and len(expected)==87,'Historical preparation count drift')
  require(set(expected)==set(old)|set(pin['newAdapters']),'Historical adapter delta drift')
  for p,h in old.items():
   if p!=baseline.RECIPE:require(expected[p]==h,'Engine82 input drift: '+p)
  # The new delta was checked above against the frozen Core87 input set;
  # no historical receipt is relabelled as a fresh execution.
  return current
 baseline.verify_inputs=reviewed_delta
 baseline.prepare()
 receipt=OUT/'baseline-engine82/authentication/result.json';result=read(receipt)
 result.update(candidatePreparationInputs=len(current),scope='Engine82 dependencies only; Core87 and new tests authenticated separately')
 write(receipt,result)


def preflight():
 v=contract();inputs=preparation_inputs()
 require(platform.system()=='Darwin' and platform.machine()=='arm64','Apple ARM64 required')
 require(previous.command('dotnet','--version')=='10.0.100','Wrong SDK')
 require('osx-arm64' in previous.command('dotnet','--info'),'Wrong SDK architecture')
 require(previous.command('git','rev-parse','HEAD',cwd=SOURCE)==read(ROOT/'build-utils/melonx/source.json')['revision'],'Wrong upstream pin')
 require(previous.command('git','rev-parse','HEAD^{tree}',cwd=SOURCE)=='82a29e6f593f6244869481e9a489b8d5154175fe','Wrong upstream tree')
 require(not previous.command('git','status','--porcelain',cwd=SOURCE),'Upstream is not pristine')
 write(EVIDENCE/'preflight.json',dict(result='passed',execution=previous.execution(),system=platform.system(),architecture=platform.machine(),preparationInputs=inputs,contractSha256=digest(CONTRACT),smokeInputs={p:digest(ROOT/p)for p in previous.HOST_INPUTS}))


def authenticate_core87():
 pin=contract()['core87'];api_pin=dict(repository='TarbleFR/RewindBox')
 run=baseline.api(api_pin,'actions/runs/'+str(pin['run']));artifact=baseline.api(api_pin,'actions/artifacts/'+str(pin['artifact']))
 require(run['head_sha']==pin['source'] and run['head_branch']=='Claude' and run['run_attempt']==1 and run['conclusion']=='success' and run['path']=='.github/workflows/melonx-core.yml','Wrong Core87 run')
 require(artifact['digest']=='sha256:'+pin['sha256'] and not artifact['expired'] and artifact['workflow_run']['id']==pin['run'] and artifact['workflow_run']['head_sha']==pin['source'],'Wrong Core87 artifact')
 path=ROOT/'.native-sources/melonx-core87.zip'
 if not path.exists():
  with path.open('xb')as out:subprocess.run(['gh','api',f"repos/TarbleFR/RewindBox/actions/artifacts/{pin['artifact']}/zip"],stdout=out,check=True,timeout=300)
 require(digest(path)==pin['sha256'] and path.stat().st_size==pin['bytes'],'Wrong Core87 archive bytes')
 receipts={}
 with zipfile.ZipFile(path)as z:
  require(hashlib.sha256(z.read('core-validation/result.json')).hexdigest()==pin['resultSha256'],'Core87 result drift')
  require(json.loads(z.read('embedded-inputs.json'))==historical_contract()['preparationInputs'],'Core87 inputs drift')
  index=json.loads(z.read('core-validation/gates.json'))
  require(index['execution']['source']==pin['source'] and len(index['receipts'])==15,'Wrong Core87 gates')
  sets=[index['receipts'],historical_contract()['core85']['receipts']]
  for names in sets:
   for name,h in names.items():
    data=z.read(name if name in z.namelist() else 'historical-core85/'+name);require(hashlib.sha256(data).hexdigest()==h,'Historical receipt drift: '+name)
    report=json.loads(data);require(report['result']=='passed' and report['physicalDeviceTested'] is False,'Failed historical gate')
    previous.inputs_match(report['inputs'])
    target=OUT/'historical-core87'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);receipts[name]=h
  write(EVIDENCE/'reused-core87-gates.json',dict(result='authenticated',source=pin['source'],run=pin['run'],artifact=pin['artifact'],archiveSha256=pin['sha256'],receipts=receipts,testsExecuted=0,scope='Unchanged historical fixtures only; new query/mapping paths have fresh gates'))
 return path


def materialize_baseline(source,recipe_root):
 v=contract()
 shutil.copytree(ROOT/'build-utils/melonx',recipe_root/'build-utils/melonx',ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copytree(ROOT/'native/melonx',recipe_root/'native/melonx')
 # Recover the exact baseline inputs in an isolated preparation workspace.
 # This never overwrites the current tracked sources or weakens an adapter.
 for p in ('build-utils/melonx/prepare_embedded.py','native/melonx/EmbeddedGraphicsSettings.cs'):
  data=subprocess.check_output(['git','show',v['recipeParent']+':'+p],cwd=ROOT)
  require(hashlib.sha256(data).hexdigest()==historical_contract()['preparationInputs'][p],'Baseline recipe input drift: '+p)
  (recipe_root/p).write_bytes(data)
 subprocess.run([sys.executable,str(recipe_root/'build-utils/melonx/prepare_embedded.py'),str(source)],check=True,timeout=120)
 output=recipe_root/'dist/melonx'
 require(read(output/'embedded-inputs.json')==historical_contract()['preparationInputs'],'Baseline preparation inventory drift')
 with zipfile.ZipFile(output/'embedded-adapted-source.zip')as z:
  require({p:hashlib.sha256(z.read(p)).hexdigest()for p in z.namelist()}==historical_contract()['preparedMembers'],'Baseline prepared source drift')
 return output


def run_gates():
 v=contract();require(read(EVIDENCE/'preflight.json')['execution']==previous.execution(),'Preflight execution drift')
 authenticate_core87()
 require(not TEST_SOURCE.exists(),'Refusing stale test source')
 shutil.copytree(SOURCE,TEST_SOURCE,ignore=shutil.ignore_patterns('.git','bin','obj'))
 with tempfile.TemporaryDirectory(prefix='melonx-baseline-')as temp:
  materialize_baseline(TEST_SOURCE,Path(temp))
 receipts={}
 for name in ('test/melonx_occlusion_test.py','test/melonx_query_policy_test.py','test/melonx_display_native_test.py'):
  receipt=v['gates'][name];require(not (OUT/receipt).exists(),'Refusing stale receipt: '+receipt)
  # The display fixture applies its unchanged allocator adapter to pristine source.
  source=SOURCE if 'display' in name else TEST_SOURCE
  subprocess.run([sys.executable,str(ROOT/name),str(source)],check=True,timeout=600)
  report=read(OUT/receipt);require(report['result']=='passed','New gate failed')
  previous.inputs_match(report['inputs']);receipts[receipt]=digest(OUT/receipt)
 for name in v['adapters']:
  importlib.import_module(name).apply(TEST_SOURCE)
 for p in sorted((ROOT/'native/melonx').glob('*.cs')):
  if p.name=='EmbeddedGraphicsSettings.cs':shutil.copyfile(p,TEST_SOURCE/'src/Ryujinx.Library'/p.name)
 require(all(digest(TEST_SOURCE/p)==h for p,h in v['preparedMembers'].items()),'New gate source composition drift')
 write(EVIDENCE/'gates.json',dict(result='passed',execution=previous.execution(),receipts=receipts,freshAppleGates=3,reusedAppleGates=29,historicalGatesReexecuted=False,reusedGateProofSha256=digest(EVIDENCE/'reused-core87-gates.json'),finalSourceInputs=historical.source_members(TEST_SOURCE),physicalDeviceTested=False))


def compiled():
 v=contract();inputs=preparation_inputs();gates=read(EVIDENCE/'gates.json')
 require(gates['execution']==previous.execution() and len(gates['receipts'])==3,'Wrong new gates')
 for p,h in gates['receipts'].items():require(digest(OUT/p)==h,'Changed new receipt')
 require(read(OUT/'embedded-inputs.json')==inputs,'Compiled preparation differs')
 require(historical.source_members(SOURCE)==gates['finalSourceInputs'],'Compiled production source differs from tested composition')
 with zipfile.ZipFile(OUT/'embedded-adapted-source.zip')as z:
  require(len(z.namelist())==len(set(z.namelist()))==len(v['preparedMembers']),'Prepared member count drift')
  require({p:hashlib.sha256(z.read(p)).hexdigest()for p in z.namelist()}==v['preparedMembers'],'Compiled adapted archive drift')
  require(all(z.read(p)==(SOURCE/p).read_bytes()for p in z.namelist()),'Archive differs from compiled sources')
 identities={};binaries={}
 for runtime in ('ios-arm64','iossimulator-arm64'):
  directory=OUT/runtime;identity=read(directory/'identity.json');core=directory/'Ryujinx.Library.dylib'
  require(identity['host']==previous.execution()['source'] and identity['adaptations']==inputs and identity['runtimeIdentifier']==runtime and identity['source']==read(ROOT/'build-utils/melonx/source.json'),'Wrong compiled identity')
  require(digest(core)==identity['sha256'] and core.stat().st_size==identity['size'] and len(identity['exports'])==47 and identity['embeddedLibraryAbi']==2,'Wrong binary/ABI')
  symbols={line.split()[-1]for line in(directory/'exports.txt').read_text().splitlines()if line.split()}
  require(all('_'+p in symbols for p in identity['exports']),'Missing native export')
  target='IOS'if runtime=='ios-arm64'else'IOSSIMULATOR'
  require('platform '+target+'\n'in(directory/'platform.txt').read_text(),'Wrong native platform')
  previous.command('xcrun','lipo',str(core),'-verify_arch','arm64')
  identities[runtime]=digest(directory/'identity.json');binaries[runtime]=dict(sha256=digest(core),bytes=core.stat().st_size)
 write(EVIDENCE/'compiled.json',dict(result='passed',execution=previous.execution(),identities=identities,binaries=binaries,adaptationCount=len(inputs),continuationAdapters=3,reviewedContinuationSources=len(v['productionChanges']),embeddedArchiveSha256=digest(OUT/'embedded-adapted-source.zip'),gateReceiptSha256=digest(EVIDENCE/'gates.json'),physicalDeviceTested=False,gameplayTested=False))


def finalize():
 previous.finalize() # identical two-session SVC, close and backing-release gates
 result=read(EVIDENCE/'result.json');result.update(freshAppleGates=3,reusedAppleGates=29,occlusionContractSha256=digest(CONTRACT),core87HistoricalProofSha256=digest(EVIDENCE/'reused-core87-gates.json'))
 result['inputs'].update({p:digest(ROOT/p)for p in ('build-utils/melonx/verify_occlusion_core.py','build-utils/melonx/occlusion-core-contract.json')})
 write(EVIDENCE/'result.json',result)
 shutil.copyfile(ROOT/'docs/melonx-occlusion-2026-10-30.md',OUT/'melonx-occlusion-2026-10-30.md')
 lines=['# RewindBox MeloNX Core', '', 'Commit: `'+previous.execution()['source']+'`',
        'Workflow: https://github.com/TarbleFR/RewindBox/actions/runs/'+str(previous.execution()['run']), '',
        'Three fresh Apple gates; 29 authenticated historical gates. Two fresh homebrew simulator sessions closed and released their backing. No iPhone gameplay or FPS measurement.', '',
        'Both experimental GPU controls are OFF by default; Hogwarts only. Progressive JIT fallback remains unavailable because native rollback is unproved.', '']
 for runtime,binary in result['binaries'].items():lines.append(runtime+': SHA256 `'+binary['sha256']+'`, '+str(binary['bytes'])+' bytes.')
 (OUT/'CORE_DELIVERY.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('prepare_dependencies','preflight','run_gates','compiled','finalize'));args=p.parse_args();globals()[args.phase]()
