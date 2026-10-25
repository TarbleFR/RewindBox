"""Private 534: current RPCS3 source, preserved 533 app and emulator configuration."""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
import melonxruntime533_delivery as previous
import rpcs3cell534_core as native

ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = '2fa4ad668446b9166017b434e302836287d015b0'
CORE_RUN = 40181634906
HOST_RUN = 40181634909
BASE = native.BASE
HOST = previous.HOST | native.HOST_CHANGED
validate_psp_core_identity = previous.validate_psp_core_identity

def command(*args):
    return subprocess.check_output(list(args), cwd=ROOT, text=True).strip()

def validate_rpc_core_identity(identity):
    assert identity['host_commit'] == CORE_SOURCE and identity['abi_version'] == 30
    assert identity['cpu_baseline'] == 'armv8.4-a' and not identity['legacy_core_bundled']
    assert not identity['device_runtime_tested']
    assert identity['source_patch_sha256'] == native.manifest()['patch_sha256']
    assert identity['native_source_sha256'] == native.manifest()['files_sha256']
    assert identity['cell534_input_sha256'] == native.inputs()
    for path, digest in identity['cell534_input_sha256'].items():
        assert hashlib.sha256(subprocess.check_output(['git','show',CORE_SOURCE+':'+path],cwd=ROOT)).hexdigest() == digest, path

def validate_rpc_core_pin(source, paths):
    assert source == CORE_SOURCE
    for path in paths:
        assert subprocess.check_output(['git','show',CORE_SOURCE+':'+path],cwd=ROOT) == (ROOT/path).read_bytes(), path

def source_contract():
    assert os.environ.get('BUILD_NUMBER') == '534'
    assert os.environ.get('GITHUB_SHA') == command('git','rev-parse','HEAD')
    assert os.environ.get('GITHUB_REF_NAME','Claude') == 'Claude'
    native.source_contract()
    changed = set(command('git','diff','--name-only',BASE,'HEAD','--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').splitlines())
    assert changed == native.HOST_CHANGED, changed
    # All latest MeloNX 533 source and settings stay byte-identical, as do the
    # other emulator source trees. Reuse their completed tests, not old failures.
    for path in previous.MELONX_INPUTS:
        assert subprocess.check_output(['git','show',previous.MELONX_SOURCE+':'+path],cwd=ROOT) == (ROOT/path).read_bytes(), path
    identity = ROOT/'dist/rpcs3-native/identity.json'
    if identity.exists(): validate_rpc_core_identity(json.loads(identity.read_bytes()))
    return dict(source=command('git','rev-parse','HEAD'),baseline=BASE,build=534,
                coreSource=CORE_SOURCE,coreRun=CORE_RUN,hostRun=HOST_RUN,
                preservedMeloNXSource=previous.MELONX_SOURCE,preservedMeloNXRun=previous.MELONX_RUN,
                physicalDeviceTested=False,physicalPerformanceMeasured=False)

def completed(run, source):
    deadline = time.monotonic() + 7200
    while True:
        result = json.loads(command('gh','api',f'repos/TarbleFR/RewindBox/actions/runs/{run}'))
        assert result['head_sha'] == source
        if result['status'] == 'completed':
            assert result['conclusion'] == 'success', (run, result['conclusion'])
            return dict(run=run,source=source,conclusion='success')
        assert time.monotonic() < deadline, 'Timed out waiting for exact component'
        print('Waiting for verified component', run, result['status'], flush=True)
        time.sleep(20)

def main():
    p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
    p.add_argument('--source-only',action='store_true');p.add_argument('--wait-for-components',action='store_true')
    p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
    p.add_argument('--output',default='build/delivery/reused-validation534.json');a=p.parse_args()
    if a.rpc_core_inputs: validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths); return
    result=source_contract()
    if a.wait_for_components or a.skin_session_evidence:
        result['components']=[completed(CORE_RUN,CORE_SOURCE),completed(HOST_RUN,CORE_SOURCE),
            completed(40179366932,BASE),completed(previous.MELONX_RUN,previous.MELONX_SOURCE)]
    if not a.source_only:
        path=ROOT/a.output;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__ == '__main__': main()
