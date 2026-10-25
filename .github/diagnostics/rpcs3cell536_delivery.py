"""Private 536: rebuilt RPCS3, byte-identical 535 host, authenticated import tests."""
import argparse,hashlib,json,os,subprocess,zipfile
from pathlib import Path
import melonximport535_delivery as previous
import rpcs3cell536_core as native
ROOT=Path(__file__).resolve().parents[2]
CORE_SOURCE='d712d5e9cbac256c6677adf7c161ea36b69ba835'
CORE_RUN=40185694306
HOST=previous.HOST
BASE=native.HOST_BASE
IMPORT_RUN=40184947714
IMPORT_JOB=121143666725
IMPORT_ARTIFACT=12595557429
IMPORT_ZIP_SHA='3723adde48b9ad408aa54c9cfad5bad6277697ed29625b45c66f055a32511a79'
IMPORT_RECEIPT_SHA='337929402e37703d547ad91675ca9e7bcb77d0e75f0098e3fbe2d28c8334d8a4'
validate_psp_core_identity=previous.validate_psp_core_identity
def command(*args):return subprocess.check_output(args,cwd=ROOT,text=True).strip()
def validate_rpc_core_identity(identity):
    assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
    assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
    assert not identity['device_runtime_tested']
    assert identity['source_patch_sha256']==native.manifest()['patch_sha256']
    assert identity['native_source_sha256']==native.manifest()['files_sha256']
    assert identity['cell536_input_sha256']==native.inputs()
    for p,h in identity['cell536_input_sha256'].items():
        assert hashlib.sha256(subprocess.check_output(['git','show',CORE_SOURCE+':'+p],cwd=ROOT)).hexdigest()==h,p
def validate_rpc_core_pin(source,paths):
    assert source==CORE_SOURCE
    for p in paths:assert subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)==(ROOT/p).read_bytes(),p
def validate_import_receipt(receipt):
    expected=json.loads((ROOT/'docs/evidence/melonx-import535-retained536.json').read_bytes())
    assert receipt==expected
    assert receipt['source']==BASE and receipt['run']==str(IMPORT_RUN) and receipt['result']=='passed'
    assert not receipt['physicalDeviceTested'] and receipt['nativeContentInspectionMocked']
    assert set(receipt['inputs'])==previous.IMPORT_INPUTS|previous.TEST_INPUTS
    for p,h in receipt['inputs'].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
        assert subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT)==(ROOT/p).read_bytes(),p
def retain_import_checks():
    def api(endpoint):return json.loads(command('gh','api','repos/TarbleFR/RewindBox/'+endpoint))
    run=api(f'actions/runs/{IMPORT_RUN}');job=api(f'actions/jobs/{IMPORT_JOB}')
    assert run['head_sha']==BASE
    assert job['run_id']==IMPORT_RUN and job['status']=='completed' and job['conclusion']=='success'
    artifact=api(f'actions/artifacts/{IMPORT_ARTIFACT}')
    assert not artifact['expired'] and artifact['workflow_run']['id']==IMPORT_RUN
    assert artifact['digest']=='sha256:'+IMPORT_ZIP_SHA
    out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
    path=out/'import535-checks.zip'
    with path.open('wb') as stream:subprocess.run(['gh','api',f'repos/TarbleFR/RewindBox/actions/artifacts/{IMPORT_ARTIFACT}/zip'],stdout=stream,check=True)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==IMPORT_ZIP_SHA
    with zipfile.ZipFile(path) as z:payload=z.read('melonx-import535-tests.json')
    assert hashlib.sha256(payload).hexdigest()==IMPORT_RECEIPT_SHA
    validate_import_receipt(json.loads(payload));(out/'melonx-import535-tests.json').write_bytes(payload)
    return dict(source=BASE,run=IMPORT_RUN,job=IMPORT_JOB,artifact=IMPORT_ARTIFACT,historical=True,allInputsUnchanged=True)
def source_contract():
    assert os.environ['BUILD_NUMBER']=='536' and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
    assert os.environ['GITHUB_SHA']==command('git','rev-parse','HEAD')
    native.source_contract()
    changed=command('git','diff','--name-only',BASE,'HEAD','--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock')
    assert not changed,changed
    validate_import_receipt(json.loads((ROOT/'docs/evidence/melonx-import535-retained536.json').read_bytes()))
    identity=ROOT/'dist/rpcs3-native/identity.json'
    if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
    return dict(source=command('git','rev-parse','HEAD'),build=536,hostBaseline=BASE,hostSourceUnchanged=True,
                coreSource=CORE_SOURCE,coreRun=CORE_RUN,physicalDeviceTested=False,physicalPerformanceMeasured=False)
def main():
    p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
    p.add_argument('--retain-import-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
    p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
    p.add_argument('--output',default='build/delivery/reused-validation536.json');a=p.parse_args()
    if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
    result=source_contract()
    if a.retain_import_checks:result['imports']=retain_import_checks()
    if a.wait_for_components:result['core']=previous.previous.completed(CORE_RUN,CORE_SOURCE)
    if a.skin_session_evidence:result['retained534']=previous.previous.completed(previous.BASE_RUN,previous.BASE)
    if not a.source_only:
        out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
