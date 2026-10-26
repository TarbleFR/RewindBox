"""Private557: the 557 fix (d645f05) on the delivered 554 product tree.

557 replaces files that earlier receipts hash (the 550 search screen, eight
554 files, sqlite_service.dart). The 554 recipe therefore runs unchanged on
the delivered 554 tree, which as_554() puts in place of the pinned 557 one
for the duration of each inherited check (a scratch index, the 557 files'
554 versions in the working tree and BUILD_NUMBER 554, all restored
afterwards): the 550 interface, 552 fix, 553 MeloNX and 554 import receipts
are checked exactly as the 554 delivery checked them. The 557 receipt is
bound to the pinned 557 tree.
"""
import argparse,contextlib,hashlib,json,os,re,tempfile
from pathlib import Path
import rpcs3libraryfiles557_tree as tree
import rpcs3import554_delivery as d554
ROOT=Path(__file__).resolve().parents[2]
BUILD='557'
HOST_TREE=d554.HOST_TREE
for name in ('MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','HOST_SOURCE','HOST_RUN','HOST_ARTIFACT',
             'CORE_SOURCE','CORE_RUN','HOST','HOST551','FIX_SOURCE','HOST552','FIX_CORE_INPUTS',
             'validate_rpc_core_identity','validate_rpc_core_pin','validate_psp_core_identity','command',
             'HOST546','LOGGER','SHIPPED','at','shipped_interface','PRODUCT_PARITY','PRODUCT549','PRODUCT',
             'DART549','SERVICE','ENGINE_INPUTS','MELONX_COUNTS','PARITY_CHECKS','ENGINE_STEPS','HOST_STEPS',
             'FIX_SOURCE554','SHIPPED554','IMPORT_TESTS'):
 globals()[name]=getattr(d554,name)
close,previous,previous546,d549,fix552=d554.close,d554.previous,d554.previous546,d554.d549,d554.fix552
FIX_SOURCE557=tree.SOURCE557
SHIPPED557=set(tree.SHIPPED557)
LOCAL=tree.LOCAL
# The 557 tests that ran on the exact pinned tree (docs/evidence/rpcs3-library-files557-local.json).
LIBRARY_TESTS=(('concurrentSaves','test/rom_folders_concurrent_save_test.dart',5),
               ('libraryFileRows','test/rpcs3_library_file_rows_test.dart',16),
               ('libraryFile','test/rpcs3_library_file_service_test.dart',18),
               ('dialogs','test/rpcs3_library_file_dialog_test.dart',19),
               ('discImage','test/rpcs3_disc_image_test.dart',11),
               ('romFolders','test/rom_folder_registration_test.dart',3),
               ('library','test/rpcs3_library_service_test.dart',None))
CONTRACTS=('rpcs3_library_file_route_contract_test.py','localization_12_locale_coverage_test.py')
assert not SHIPPED557&(HOST546|PRODUCT|set(DART549)|HOST552)

_active=[False]

@contextlib.contextmanager
def as_554():
 """The delivered 554 tree in place of the pinned 557 one: a scratch copy of
 the index with the 557 files at their 554 versions and this recipe removed,
 the same 557 files in the working tree, and build number 554. The 557
 bytes, the index in use and the environment are restored on exit; a check
 already inside the 554 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_554()
 files={p:s for p,s in versions.items() if p in tree.FIX557}
 saved={p:(ROOT/p).read_bytes() if (ROOT/p).is_file() else None for p in files}
 env={k:os.environ.get(k) for k in ('GIT_INDEX_FILE','BUILD_NUMBER')}
 with tempfile.TemporaryDirectory() as scratch:
  index=os.path.join(scratch,'index')
  tree.index_with(versions,index)
  try:
   for p,source in files.items():
    target=ROOT/p
    if source is None:target.unlink(missing_ok=True)
    else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(at(source,p))
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d554.BUILD
   _active[0]=True
   yield
  finally:
   _active[0]=False
   for k,v in env.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
   for p,data in saved.items():
    if data is None:(ROOT/p).unlink(missing_ok=True)
    else:(ROOT/p).write_bytes(data)
 # Nothing of the 554 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 554 recipe, run on the delivered 554 tree."""
 with as_554():return function(*args,**kwargs)

def validate_interface():
 return inherited(d554.validate_interface)

def validate_service():
 return inherited(d554.validate_service)

def validate_fix_tests():
 return inherited(d554.validate_fix_tests)

def validate_import_tests():
 return inherited(d554.validate_import_tests)

def engine_evidence():
 return inherited(d554.engine_evidence)

def evidence():
 return json.loads((ROOT/LOCAL).read_text())

def validate_library_file_tests():
 """The 557 receipt, produced on the exact pinned 557 tree."""
 local=evidence()
 assert local['result']=='passed' and local['physicalDeviceTested'] is False and local['build']==557
 assert local['source']==FIX_SOURCE557 and local['flutter']=='3.47.2'
 assert local['productTrees']==tree.product_trees(),local['productTrees']
 assert local['productTrees554']==tree.product_trees_554()
 assert local['productTrees554']==d554.evidence()['productTrees'],'the 554 view is the delivered 554 tree'
 assert set(tree.FIX557)-{'docs/rpcs3-library-files557.md'}<=set(local['inputs'])
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 for key,path,count in LIBRARY_TESTS:
  run=local['tests'][key]
  assert run['test']==path and run['failed']==0,key
  if count is not None:assert run['passedTests']==count and f'+{count}: All tests passed!' in run['log'],key
 for name in CONTRACTS:
  assert local['contracts'][name]['exitCode']==0,name
 # The Build 419 contract: the two SQLite files give back their 419 bytes;
 # the failures already on the 554 tree, and only those, remain.
 baseline=local['contracts']['retroarch_baseline_scope_test.py']
 assert baseline['failures']==baseline['failures554'],baseline
 for p in ('lib/data/datasources/sqlite_service.dart','lib/data/datasources/sqlite_database_service.dart'):
  assert not any(p in f for f in baseline['failures']),p
 # The whole Dart suite on both trees: the same failing tests (already on
 # the delivered 554 tree), and the 557 tests added.
 suite=local['fullSuite']
 assert set(suite['failedTests'])==set(suite['failedTests554']) and suite['failed']==suite['failed554'],suite
 assert suite['passed']>suite['passed554'],suite
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert f"{local['analyzerIssues']} issues found." in local['analyzerLog']
 # Before the fix: concurrent saves collide on the 554 tree, and its router
 # still asks for the file of an installed disc.
 control=local['negativeControl']
 assert control['tree']=='554' and control['productTrees']==local['productTrees554'],control
 assert control['concurrentSaves']['exitCode']!=0 and 'UNIQUE constraint failed: user_rom_folders.path' in control['concurrentSaves']['log']
 assert control['routeContract']['exitCode']!=0 and 'one guard for installed discs whose file is gone' in control['routeContract']['log']
 return local

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 554 contract, unchanged, on the delivered 554 tree.
 report=inherited(d554.source_contract)
 assert report['productTrees']==tree.product_trees_554(),report['productTrees']
 # The pinned index differs from the delivered 554 tree by the 557 files and this recipe only.
 with tempfile.TemporaryDirectory() as scratch:
  env=tree.index_with(tree.at_554(),os.path.join(scratch,'index'))
  view=tree.git('write-tree',env=env)
 changed=set(command('git','diff','--cached','--name-only',view).splitlines())
 expected=set(tree.FIX557)|set(tree.RECIPE)
 assert changed==expected,changed^expected
 for p in SHIPPED557:assert (ROOT/p).read_bytes()==at(FIX_SOURCE557,p),p
 for p in set(tree.UI550)-set(tree.FIX557):assert (ROOT/p).read_bytes()==at(tree.SOURCE_UI,p),p
 for p in SHIPPED554-SHIPPED557:assert (ROOT/p).read_bytes()==at(FIX_SOURCE554,p),p
 library=validate_library_file_tests()
 return dict(report,build=int(BUILD),source=head,source557=FIX_SOURCE557,libraryFilesChanged=sorted(SHIPPED557),
  replaced=tree.REPLACED,libraryFileTests={k:library['tests'][k]['passedTests'] for k,_,_ in LIBRARY_TESTS},
  fullSuite=library['fullSuite'],pinnedFiles=kept,productTrees=tree.product_trees(),productTrees554=report['productTrees'],
  changed557=sorted(expected),libraryFileFixDeviceVerified=False,physicalDeviceTested=False)

def retain_checks():
 """The 554 receipts stay bound to the delivered 554 tree; the 557 receipt to the pinned tree."""
 inherited(d554.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'rpcs3-library-files557-tests.json').write_text(json.dumps(validate_library_file_tests(),indent=2)+'\n')
 print('Bound the 557 library-file receipt to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation557.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  inherited(previous546.logger_proofs);print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
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
