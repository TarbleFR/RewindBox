"""Compose the delivered 473 baseline with exact, already executed cheat proofs.

This gate reads CI evidence; it never reruns suites or rebuilds a core. Failed
historical jobs are accepted only for their explicitly successful components.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '881c8df6bcffbdd0e4c3f5a32fd66492830f6dd1'
CATALOGUE = '2c328dfb6267245220da6162790b52542b9e2e0b'
SDK_SOURCE = '2ae6ec849c9e4b122a1fae62bc9715cbdcc64691'
RPC_SOURCE = 'c9ba99fb81dc7e9dd79d17dde845a22628924bdb'
DELIVERY_ONLY = {
    '.github/diagnostics/unified_cheats_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/validate_unified_cheats_ipa.py',
    'build-utils/delivery-474-recipient.pem',
    'docs/build474-unified-cheats.md', 'AGENTS.md',
}


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def api(path, raw=False):
    data = command(['gh', 'api', 'repos/TarbleFR/neostation-ios/' + path])
    return data if raw else json.loads(data)


def source_closure():
    for args in (['git', 'diff', '--name-only', CATALOGUE, 'HEAD'],
                 ['git', 'diff', '--name-only', CATALOGUE]):
        extra = set(command(args).splitlines()) - DELIVERY_ONLY
        if extra:
            raise ValueError('Unvalidated changes after final cheat proofs: ' + ', '.join(sorted(extra)))
    # These components inherit 473 evidence, not a newly invented test result.
    command(['git', 'diff', '--exit-code', BASE, '--', 'lib', 'assets',
             'native/neoswap', 'native/neoswap-relay', 'native/neoswap-donation',
             'native/nestopia', 'build-utils/libretro', 'packages/neo_swap',
             'packages/external_display', 'packages/external_folder_access'])
    # All changed native packages equal the Apple-tested source, except for
    # the separately tested RPCS3 first-import correction and the final index.
    expected = {'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz',
                'packages/rpcs3_internal_bridge/ios/Classes/RPCS3UnifiedCheats.mm'}
    changed = set(command(['git', 'diff', '--name-only', SDK_SOURCE, '--', 'packages']).splitlines())
    if changed != expected:
        raise ValueError('Changed Apple compilation inputs: ' + ', '.join(sorted(changed)))
    command(['git', 'diff', '--exit-code', RPC_SOURCE, '--',
             'packages/rpcs3_internal_bridge/ios/Classes/RPCS3UnifiedCheats.mm'])
    manifest = ROOT / 'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != 'cf8959bfd6b20b4ef2516e1e235723b1a5048b2fc2c98033d05ad0d48cf84e57':
        raise ValueError('Final manifest no longer matches the Apple preflight')
    return {'base': BASE, 'catalogue': CATALOGUE, 'nativeSDK': SDK_SOURCE,
            'correctedRPCS3Store': RPC_SOURCE, 'allOtherInputsUnchanged': True}


def successful_run(run_id, ref, names):
    run = api(f'actions/runs/{run_id}')
    if run['head_sha'] != ref or run['status'] != 'completed' or run['conclusion'] != 'success':
        raise ValueError('Missing successful run: ' + str(run_id))
    jobs = api(f'actions/runs/{run_id}/jobs?per_page=100')['jobs']
    for name in names:
        matching = [j for j in jobs if j['name'] == name]
        if len(matching) != 1 or matching[0]['conclusion'] != 'success':
            raise ValueError('Missing successful component: ' + name)
    return {'run': run_id, 'source': ref, 'jobs': names, 'conclusion': 'success'}


def evidence():
    records = [
        successful_run(39088132898, BASE, ['checks', 'native', 'Release device build • cold']),
        successful_run(39096074029, '6cbb8466a82fd64513240f43dc5b738967b9d2ff', ['data']),
        successful_run(39095959132, '1f024f0be5a61c5d66bdb50418473f275cd231b0', ['published-index']),
        successful_run(39094644017, 'd254ece2317a879dc821b7ca639c0d01a6874993', ['core-effects']),
        successful_run(39095481129, 'a302af0d8c79cd521e712aa50c7f25ac99fa2a8b', ['native']),
    ]
    # This job failed later in other components. Require its real SDK/link
    # successes and the 92-identity / seven native-file log witnesses exactly.
    job = api('actions/jobs/117576626168')
    if job['head_sha'] != SDK_SOURCE:
        raise ValueError('Wrong Apple source')
    successes = {s['name'] for s in job['steps'] if s.get('conclusion') == 'success'}
    required = {'Shared Foundation behavior and actual iPhone SDK',
                'Compile and link the affected Libretro bridge'}
    if not required <= successes:
        raise ValueError('Incomplete successful Apple components')
    log = api('actions/jobs/117576626168/logs', raw=True)
    if 'Unified identity: 92 checks, 0 failures' not in log:
        raise ValueError('Missing executed identity witness')
    for path in ('armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.mm',
                 'armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm',
                 'dolphin_internal_bridge/ios/Classes/DolphinSessionMenu.mm',
                 'dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm',
                 'rpcs3_internal_bridge/ios/Classes/Rpcs3SessionMenu.mm',
                 'rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
                 'rpcs3_internal_bridge/ios/Classes/RPCS3UnifiedCheats.mm'):
        if 'Z PASS iPhone SDK syntax: packages/' + path not in log:
            raise ValueError('Missing actual SDK compilation: ' + path)
    job = api('actions/jobs/117577305555')
    if job['head_sha'] != RPC_SOURCE:
        raise ValueError('Wrong corrected RPCS3 store source')
    successes = {s['name'] for s in job['steps'] if s.get('conclusion') == 'success'}
    if not {'Regional identities and per-core complete programs',
            'Native imports, disabled state and RPCS3 persistence'} <= successes:
        raise ValueError('Corrected FBNeo Host / RPCS3 store not validated')
    records.append({'run': 39094043482, 'source': SDK_SOURCE,
                    'job': 117576626168, 'scope': 'successful components only; overall job failed'})
    records.append({'run': 39094267628, 'source': RPC_SOURCE,
                    'job': 117577305555, 'scope': 'successful Host/store components only; overall job failed'})
    receipts = {}
    for name in ('core-effects', 'fbneo-native', 'ui-e813', 'ui-regional',
                 'full-index', 'publication', 'published-data'):
        path = 'docs/evidence/unified-cheats-' + name + '.json'
        raw = (ROOT / path).read_bytes()
        json.loads(raw)
        receipts[path] = hashlib.sha256(raw).hexdigest()
    # 28 UIKit successes from the earlier failed suite are reused explicitly,
    # together with the two successful targeted regional cases. No full rerun.
    old_ui = api('actions/jobs/117579007774')
    if old_ui['head_sha'] != 'e813d226dc1cd0b9d6e9b204d9de692621b9a62c':
        raise ValueError('Wrong original UIKit source')
    return records, receipts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-only', action='store_true')
    p.add_argument('--dart-evidence', action='store_true')
    p.add_argument('--libretro-evidence', action='store_true')
    p.add_argument('--skin-session-evidence', action='store_true')
    p.add_argument('--scope', default='full', choices=['full'])
    p.add_argument('--output', default='build/delivery/reused-validation.json')
    a = p.parse_args()
    closure = source_closure()
    if a.source_only:
        print('PASS exact final catalogue, Apple source closure and unchanged 473 components')
        return
    records, receipts = evidence()
    record = {'result': 'passed', 'testedSHA': CATALOGUE, 'candidateSHA': command(['git', 'rev-parse', 'HEAD']),
              'validationWasReused': True, 'sourceClosure': closure,
              'reusedEvidence': records, 'receiptSHA256': receipts,
              'deviceGameplayValidated': False, 'coreRebuilt': False}
    if a.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'], tool='Flutter 3.47.2, Ubuntu 24.04')
    if a.libretro_evidence:
        xcode = command(['xcodebuild', '-version'])
        sdk = command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'])
        if xcode != 'Xcode 26.3\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Changed native toolchain')
        record.update(xcode=xcode, iphoneSDK=sdk)
    out = ROOT / a.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS closed Build 473 baseline + final cheat component evidence; no suites rerun')


if __name__ == '__main__':
    main()
