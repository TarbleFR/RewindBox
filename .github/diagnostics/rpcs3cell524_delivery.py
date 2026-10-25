"""Reuse the exact 523 compiled app and admit only the source-built 524 Core."""
import argparse
import json
import os
from pathlib import Path
import rpcs3cell523_delivery as previous
import rpcs3cell524_core as native

ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = 'a7a109b955d2e60de005fd663eb4391f6c93e88d'
CORE_RUN = 40110663507
APP_SOURCE = 'c1f550f8be86c91d65dc564ebddff593f2e3fe46'
APP_RUN = 40104064265
BASE_IPA_SHA = '7fa958570e802c489db4d4df07b7388cde4bb18f94c2555bcce060db9aedb8a1'
APP_CACHE = 'neostation-device-v2-macOS-ARM64-xcode26.3-flutter3.47.2-c1f550f8be86c91d65dc564ebddff593f2e3fe46-523-09b8aa7d1bc439098e74eaba3735094714b3cd5740c469e7c84be8dd2fec6336-normal'
FIXTURE = 'test/fixtures/rpcs3_app523_payload.json'
FIXTURE_SHA = 'a4cbe634f3eb9cc06ae115b47553b9c3813ce4c7ef72a80111289def4774f13a'
HOST = previous.HOST
HOST_DELTA_SHA = previous.HOST_DELTA_SHA
validate_host_proof = previous.validate_host_proof
ASSEMBLY = {'.github/diagnostics/rpcs3cell524_delivery.py', '.github/workflows/rpcs3-cell524-delivery.yml',
    'build-utils/rpcs3_cell524_package.py', 'build-utils/validate_rpcs3_cell524_ipa.py',
    'build-utils/delivery-524-rpcs3-recipient.pem', FIXTURE,
    'docs/rpcs3-cell524.md', 'docs/evidence/rpcs3-cell524-validation.json'}
CONTROLS = ('build-utils/delivery_cipher.py', 'build-utils/sign_delivery.py',
    'build-utils/delivery_benchmark.py', 'build-utils/embed_legal_bundle.py',
    'build-utils/collect_build_source_evidence.py', 'build-utils/validate_legal_bundle_ipa.py',
    'packages/dolphin_internal_bridge/ci/build_support.py',
    'packages/dolphin_internal_bridge/ci/verify_ipa.py')


def validate_rpc_core_identity(identity):
    assert identity['host_commit'] == CORE_SOURCE
    native.pin_module().validate_core_input_identity(identity)
    assert identity['cell524_input_sha256'] == native.inputs()
    assert identity['cpu_baseline'] == 'armv8.4-a' and identity['legacy_core_bundled'] is False
    assert identity['device_runtime_tested'] is False


def source_closure():
    assert os.environ.get('GITHUB_REF_NAME', 'Claude') == 'Claude'
    assert os.environ.get('BUILD_NUMBER', '524') == '524'
    native.source_contract()
    assert native.sha((ROOT / FIXTURE).read_bytes()) == FIXTURE_SHA
    for revision in (['HEAD'], []):
        changed = set(native.command('git', 'diff', '--name-only', CORE_SOURCE, *revision).decode().splitlines())
        assert not changed - ASSEMBLY, sorted(changed - ASSEMBLY)
        product = native.command('git', 'diff', '--name-only', APP_SOURCE, *revision,
            '--', 'lib', 'native', 'packages', 'assets', 'ios', 'pubspec.yaml', 'pubspec.lock')
        assert not product.strip(), product
    for path in CONTROLS:
        assert (ROOT / path).read_bytes() == native.command('git', 'show', APP_SOURCE + ':' + path), path
    return dict(source=native.command('git', 'rev-parse', 'HEAD').decode().strip(),
        coreSource=CORE_SOURCE, coreRun=CORE_RUN, compiledAppSource=APP_SOURCE, compiledAppRun=APP_RUN,
        appCodeRecompiled=False, changedAppProduct=[], physicalDeviceTested=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-only', action='store_true')
    p.add_argument('--wait-for-components', action='store_true')
    args = p.parse_args()
    report = dict(result='passed', sourceClosure=source_closure())
    if not args.source_only:
        component = previous.previous.component
        report['components'] = [component(CORE_RUN, CORE_SOURCE,
            ['RPCS3 CELL524: HLE abort wake and iPhone Core'], args.wait_for_components),
            component(APP_RUN, APP_SOURCE, ['checks', 'native', 'Release device build • cold'], args.wait_for_components)]
    out = ROOT / 'build/delivery/reused-validation.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS exact Core524 and authenticated compiled app523; no Flutter rebuild or device-performance claim')
