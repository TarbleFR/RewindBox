"""Private 535: targeted import fixes, unchanged source-built engines from 534."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import rpcs3cell534_delivery as previous

ROOT = Path(__file__).resolve().parents[2]
BASE = 'b2598823eb3c3b3752f786730b97f35bb93f1dab'
BASE_RUN = 40181996501
CORE_SOURCE = previous.CORE_SOURCE
CORE_RUN = previous.CORE_RUN
HOST = previous.HOST
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_psp_core_identity = previous.validate_psp_core_identity
IMPORT_INPUTS = {
    'lib/l10n/melonx_transfer_locale.dart',
    'lib/services/melonx_embedded_library_service.dart',
    'lib/services/melonx_internal_service.dart',
    'lib/services/melonx_import_progress.dart',
    'lib/widgets/melonx_internal_playlist_actions.dart',
    'lib/widgets/melonx_transfer_dialog.dart',
}
TEST_INPUTS = {'test/melonx_import_completion_test.dart',
               'test/melonx_import_completion_test.py',
               'test/melonx_presentation_widgets_test.dart',
               'test/melonx_library_files_test.dart', 'test/melonx_transfer_test.dart'}

def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()

def check_source():
    assert os.environ['BUILD_NUMBER'] == '535'
    source = command('git','rev-parse','HEAD')
    assert os.environ['GITHUB_SHA'] == source
    changed = set(command('git','diff','--name-only',BASE,'HEAD','--',
        'lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').splitlines())
    assert changed == IMPORT_INPUTS, changed ^ IMPORT_INPUTS
    # No engine or shared native code is changed relative to successful 534.
    # Verify the downloaded RPCS3 identity using its original exact input set.
    identity = ROOT/'dist/rpcs3-native/identity.json'
    if identity.exists(): validate_rpc_core_identity(json.loads(identity.read_bytes()))
    return dict(source=source, build=535, baseline=BASE, baselineRun=BASE_RUN,
                rpcs3CoreSource=CORE_SOURCE, rpcs3CoreRun=CORE_RUN,
                melonxEngineSource=previous.previous.MELONX_SOURCE,
                melonxEngineRun=previous.previous.MELONX_RUN,
                physicalDeviceTested=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
    p.add_argument('--source-only',action='store_true')
    p.add_argument('--wait-for-components',action='store_true')
    p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
    p.add_argument('--output',default='build/delivery/reused-validation535.json')
    a=p.parse_args()
    if a.rpc_core_inputs:
        validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
    report=check_source()
    if a.wait_for_components or a.skin_session_evidence:
        report['retainedComponents']=previous.completed(BASE_RUN,BASE)
    if not a.source_only:
        out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
