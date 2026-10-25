"""Private 537: automatic update targeting and the active Apple audio backend."""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
import rpcs3cell536_delivery as previous

ROOT = Path(__file__).resolve().parents[2]
BASE = '5fdc4c4feb729918eb1aaa96ac50bce470dc7e6c'
BASE_RUN = 40186697206
SOURCE = '94ae1314f653a4eb76f8020660273a9faf1b0680'
MELONX_SOURCE = '23d92f17d0df716151ef136e64453fe774e8b6c7'
MELONX_RUN = 40188516292
HOST_SOURCE = SOURCE
HOST_RUN = 40187994797
CORE_SOURCE, CORE_RUN, HOST = previous.CORE_SOURCE, previous.CORE_RUN, previous.HOST
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_psp_core_identity = previous.validate_psp_core_identity
CHANGED = {
    'lib/l10n/melonx_transfer_locale.dart',
    'lib/services/melonx_embedded_library_service.dart',
    'lib/services/melonx_import_progress.dart',
    'lib/widgets/melonx_internal_playlist_actions.dart',
    'native/melonx/EmbeddedAddons.cs',
    'native/melonx/EmbeddedAddonSelection.cs',
    'native/melonx/EmbeddedContent.cs',
    'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
}
IMPORT_INPUTS = previous.previous.IMPORT_INPUTS | {
    'test/melonx_import_completion_test.dart', 'test/database_test_helper.dart',
    'lib/data/datasources/sqlite_service.dart', 'pubspec.yaml', 'pubspec.lock',
}

def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()

def hashes(paths):
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}

def api(path):
    return json.loads(command('gh','api','repos/TarbleFR/RewindBox/'+path))

def completed(run, source, required=()):
    deadline=time.monotonic()+5400
    while True:
        state=api(f'actions/runs/{run}')
        assert state['head_sha']==source
        if state['status']=='completed': break
        assert time.monotonic()<deadline, 'Component deadline exceeded'
        print(f'Waiting for exact component {run}: {state["status"]}',flush=True)
        time.sleep(20)
    assert state['conclusion']=='success', (run,state['conclusion'])
    jobs=api(f'actions/runs/{run}/jobs')['jobs']
    passed={s['name'] for j in jobs if j['conclusion']=='success' for s in j['steps'] if s['conclusion']=='success'}
    assert set(required)<=passed, set(required)-passed
    return dict(run=run,source=source,result='passed',requiredSteps=list(required))

def validate_local_imports(receipt):
    assert receipt['result']=='passed' and receipt['source']==SOURCE
    assert receipt['executor']=='local Linux' and receipt['passedTests']==12
    assert receipt['physicalDeviceTested'] is False and receipt['nativeContentInspectionMocked'] is True
    assert receipt['inputs']==hashes(IMPORT_INPUTS)
    for p in IMPORT_INPUTS:
        assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show',SOURCE+':'+p],cwd=ROOT),p
    assert '00:10 +12: All tests passed!' in receipt['flutterLog']
    assert not any(' - '+severity+' - ' in receipt['analyzerLog'] for severity in ('error','warning'))
    assert '13 issues found.' in receipt['analyzerLog']

def retain_checks():
    out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
    validate_local_imports(receipt)
    (out/'melonx-import537-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
    completed(BASE_RUN,BASE,['Verify actual logger retains writer and resilience evidence after restoration errors'])
    prior=json.loads((ROOT/'docs/evidence/rpcs3-cell536-delivery-ci.json').read_text())['ciValidation']['retention536-tests.json']
    assert prior['source']==BASE and prior['run']==str(BASE_RUN) and prior['passed']
    for p,h in prior['inputs'].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
        assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT),p
    (out/'retention536-tests.json').write_text(json.dumps(prior,indent=2)+'\n')
    print('Reused 12 completed local import checks and unchanged successful 536 Foundation logger proof.')

def source_contract():
    assert os.environ['BUILD_NUMBER']=='537' and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
    head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
    changed=set(command('git','diff','--name-only',BASE,'HEAD','--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').splitlines())
    assert changed==CHANGED, changed^CHANGED
    for p in CHANGED:
        source=HOST_SOURCE if p.startswith('packages/') else SOURCE
        assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show',source+':'+p],cwd=ROOT),p
    previous.native.pin_module().validate_source_contract()
    identity=ROOT/'dist/rpcs3-native/identity.json'
    if identity.exists(): validate_rpc_core_identity(json.loads(identity.read_text()))
    return dict(source=head,build=537,baseline=BASE,baselineRun=BASE_RUN,
        coreSource=MELONX_SOURCE,coreRun=MELONX_RUN,hostSource=HOST_SOURCE,hostRun=HOST_RUN,
        changed=sorted(CHANGED),physicalDeviceTested=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
    p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
    p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
    p.add_argument('--output',default='build/delivery/reused-validation537.json');a=p.parse_args()
    if a.rpc_core_inputs: validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
    report=source_contract()
    if a.retain_checks: retain_checks()
    if a.wait_for_components or a.skin_session_evidence:
        report['engine']=completed(MELONX_RUN,MELONX_SOURCE,[
            'Exercise the selected Apple audio backend and update target selection',
            'Retain exact unchanged runtime and graphics tests',
            'Compile NativeAOT library and verify exported ABI',
            'Exercise this exact rebuilt engine in an ARM64 iOS app'])
        report['host']=completed(HOST_RUN,HOST_SOURCE,[
            'Compile the iPhone host and execute its native ABI scenarios',
            'Exercise audio ownership, route changes and presentation handoff',
            'Exercise registered plugin presentation and retry in actual UIKit'])
    if not a.source_only:
        out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
