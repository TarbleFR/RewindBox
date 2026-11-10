"""Private554: the RPCS3 library-file import (410678b) on the delivered 553 product tree.

Every 553 receipt stays valid: the 554 files are shipped Dart only, shared
with no earlier build, and the 553 checks are bound to the 553 product tree
computed from this index with the 554 files put back to their 553 versions.
"""
import argparse,hashlib,json,os,re
from pathlib import Path
import rpcs3import554_tree as tree
import melonxparity553_tree as tree553
# The 553 checks compare their receipts with the product trees of the 553
# recipe; under the 554 index those are the trees with the 554 files at their
# 553 versions. Rebound before the 553 delivery is used.
tree553.product_trees=tree.product_trees_553
tree553.product_trees_552=tree.product_trees_552
tree553.product_trees_551=tree.product_trees_551
tree553.product_trees_550=tree.product_trees_550
import melonxparity553_delivery as d553
ROOT=Path(__file__).resolve().parents[2]
BUILD='554'
HOST_TREE=d553.HOST_TREE
FIX_SOURCE554=tree.SOURCE554
for name in ('MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','HOST_SOURCE','HOST_RUN','HOST_ARTIFACT',
             'CORE_SOURCE','CORE_RUN','HOST','HOST551','FIX_SOURCE','HOST552','FIX_CORE_INPUTS',
             'validate_rpc_core_identity','validate_rpc_core_pin','validate_psp_core_identity','command',
             'HOST546','LOGGER','SHIPPED','at','shipped_interface','PRODUCT_PARITY','PRODUCT549','PRODUCT',
             'DART549','SERVICE','ENGINE_INPUTS','MELONX_COUNTS','PARITY_CHECKS','ENGINE_STEPS','HOST_STEPS',
             'validate_interface','validate_service','validate_fix_tests','validate_melonx_rerun','engine_evidence'):
 globals()[name]=getattr(d553,name)
close,previous,previous546,d549,fix552=d553.close,d553.previous,d553.previous546,d553.d549,d553.fix552
SHIPPED554=set(tree.SHIPPED554)
LOCAL=tree.LOCAL
# The 554 tests that ran on the exact pinned tree (docs/evidence/rpcs3-import554-local.json).
IMPORT_TESTS=(('discImage','test/rpcs3_disc_image_test.dart',11),
              ('libraryFile','test/rpcs3_library_file_service_test.dart',16),
              ('dialogs','test/rpcs3_library_file_dialog_test.dart',18),
              ('library','test/rpcs3_library_service_test.dart',None))
assert not SHIPPED554&(close.CHANGED|HOST546|PRODUCT|set(DART549)|HOST552)

def evidence():
 return json.loads((ROOT/LOCAL).read_text())

def validate_import_tests():
 """The 554 receipt, produced on the exact pinned 554 tree."""
 local=evidence()
 assert local['result']=='passed' and local['physicalDeviceTested'] is False and local['build']==554
 assert local['source']==FIX_SOURCE554 and local['flutter']=='3.47.2'
 assert local['productTrees']==tree.product_trees(),local['productTrees']
 assert local['productTrees553']==tree.product_trees_553()
 assert set(tree.FIX554)-{'docs/rpcs3-import554.md'}<=set(local['inputs'])
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 for key,path,count in IMPORT_TESTS:
  run=local['tests'][key]
  assert run['test']==path and run['failed']==0,key
  if count is not None:assert run['passedTests']==count and f'+{count}: All tests passed!' in run['log'],key
 for name in ('rpcs3_library_file_route_contract_test.py','localization_12_locale_coverage_test.py'):
  assert local['contracts'][name]['exitCode']==0,name
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert f"{local['analyzerIssues']} issues found." in local['analyzerLog']
 # The PS3 row went to RetroArch before the fix: the route contract fails on the 553 tree.
 control=local['negativeControl']
 assert control['tree']=='553' and control['exitCode']!=0,control
 assert 'taken by every iOS PS3 row' in control['log'],control['log']
 return local

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 kept=tree.verify()
 # The pinned index differs from the validated 542 host by the 553 changes
 # and the 554 Dart files only.
 changed=set(command('git','diff','--cached','--name-only',HOST_TREE,'--',*SHIPPED).splitlines())
 ui=changed&shipped_interface()
 fixed=close.CHANGED|HOST546|PRODUCT|SHIPPED554
 assert not ui&fixed,sorted(ui&fixed)
 expected=fixed|ui
 assert changed==expected,changed^expected
 for p in ui:assert (ROOT/p).read_bytes()==at(tree.SOURCE_UI,p),p
 interface=validate_interface()
 fix=validate_fix_tests()
 for p in close.CHANGED-PRODUCT:assert (ROOT/p).read_bytes()==at(close.HOST_SOURCE,p),p
 for p in HOST546-HOST552:assert (ROOT/p).read_bytes()==at(tree.HOST_TREE,p),p
 for p in HOST552:assert (ROOT/p).read_bytes()==at(FIX_SOURCE,p),p
 for p in PRODUCT:assert (ROOT/p).read_bytes()==at(tree.previous.source_of(p) if p in tree.previous.PARITY else MELONX_SOURCE,p),p
 for p in DART549-PRODUCT_PARITY:assert d549.only_added(at(tree.HOST_TREE,p),(ROOT/p).read_bytes()),p
 for p in SHIPPED554:assert (ROOT/p).read_bytes()==at(FIX_SOURCE554,p),p
 validate_service()
 fix552.native.pin_module().validate_source_contract()
 for p,h in fix552.native.inputs().items():
  assert not p in SHIPPED554,p
  assert hashlib.sha256(at(FIX_SOURCE if p in FIX_CORE_INPUTS else CORE_SOURCE,p)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in ENGINE_INPUTS:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 imported=validate_import_tests()
 ui550=tree.previous.previous.previous.previous
 return dict(source=head,build=int(BUILD),hostTree=tree.HOST_TREE,source547=ui550.SOURCE547,
  source548=ui550.SOURCE548,source549=ui550.SOURCE549,sourceInterface=tree.SOURCE_UI,
  source551=tree.SOURCE551,source552=FIX_SOURCE,sourceParity=MELONX_SOURCE,source554=FIX_SOURCE554,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,hostArtifact=HOST_ARTIFACT[0],hostFiles=tree.previous.HOST_FILES,
  rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,rpcs3HostFiles=sorted(HOST552),fixCoreInputs=sorted(FIX_CORE_INPUTS),profileTests=fix['profiles']['passedTests'],
  melonxChanged=sorted(PRODUCT_PARITY),importChanged=sorted(SHIPPED554),importTests={k:imported['tests'][k]['passedTests'] for k,_,_ in IMPORT_TESTS},
  interfaceChanged=sorted(ui),interfaceTests=interface['passedTests'],
  changed=sorted(expected),pinnedFiles=kept,productTrees=tree.product_trees(),productTrees553=tree.product_trees_553(),
  productTrees552=tree.product_trees_552(),productTrees551=tree.product_trees_551(),productTrees550=tree.product_trees_550(),
  physicalDeviceTested=False,importFixDeviceVerified=False,crashFixDeviceVerified=False,
  standaloneMoltenVkDeviceTested=False,flickerFixClaimed=False)

def retain_checks():
 """The 553 receipts stay bound under the 554 files; the 554 receipt is bound to the pinned tree."""
 d553.retain_checks()
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'rpcs3-import554-tests.json').write_text(json.dumps(validate_import_tests(),indent=2)+'\n')
 print('Bound the 554 import receipt to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation554.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:previous546.logger_proofs();print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(HOST_ARTIFACT,'dist/melonx-host')]
 if a.engine_evidence:report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS)
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
