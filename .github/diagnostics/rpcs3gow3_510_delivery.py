"""Close Build 510 around the new GoW3 Core and the unchanged delivered 509 app."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import melonxdelete509_delivery as previous
import rpcs3memory508_delivery as audit

base = previous.base
HOST = audit.HOST
ROOT = Path(__file__).resolve().parents[2]
BASELINE = '92dd1caa3442769dc6148df33a488d85e7b88500'
DELIVERED = 'd4e61fa1388b9b52e4ea51ea0a0a65cee58bab90'
DELIVERED_RUN = 39884045828
CORE_SOURCE = '50714fe0980d0b50ccd93c1c739c480b054a31b9'
CORE_RUN = 39888215155
PATCH_SHA256 = 'f31bf5f7d66c44dd3a02683a12a3b3ad6ac450d83bd66603e8c2010f7579198d'
ALLOWED = {
    '.github/diagnostics/rpcs3gow3_core.py', '.github/workflows/neoswap-ipa.yml',
    '.github/workflows/retroarch-delivery.yml', '.github/workflows/rpcs3-memory-audit.yml',
    'build-utils/build_rpcs3_embedded_core.sh', 'build-utils/rpcs3/canonical-source.json',
    'build-utils/rpcs3/embedded-core.patch', 'test/native/rpcs3_memory_audit_test.cpp',
    'test/neo_swap_core_pin_test.py', 'test/rpcs3_gow3_boot_regression_test.py',
    'test/rpcs3_memory_audit_test.py', '.github/diagnostics/rpcs3gow3_510_delivery.py',
    'build-utils/validate_rpcs3_gow3_ipa.py', 'build-utils/delivery-510-chatgpt-recipient.pem',
    'docs/rpcs3-gow3-build510.md', 'docs/evidence/rpcs3-gow3-510-delivery.json',
}
validate_psp_core_identity = previous.validate_psp_core_identity

def core_module():
    sys.path.insert(0, str(ROOT / 'test'))
    import neo_swap_core_pin_test
    return neo_swap_core_pin_test

def validate_rpc_core_identity(identity):
    assert identity['host_commit'] == CORE_SOURCE
    assert identity['source_patch_sha256'] == PATCH_SHA256
    core_module().validate_core_input_identity(identity)

def validate_rpc_core_pin(pin, paths):
    core = core_module()
    assert pin == CORE_SOURCE
    assert len(paths) == len(core.CORE_INPUTS) and set(paths) == set(core.CORE_INPUTS)
    core.validate_source_contract()
    core.validate_exact_pin(pin)
    print('PASS exact newly built GoW3 Core source, recipe, tests and ABI; no identity rewriting')

def source_closure():
    assert os.environ.get('GITHUB_REF_NAME') == 'Claude'
    assert os.environ.get('BUILD_NUMBER', '510') == '510'
    for revision in (['HEAD'], []):
        changed = set(base.command(['git', 'diff', '--name-only', BASELINE, *revision]).splitlines())
        assert not (changed - ALLOWED), sorted(changed - ALLOWED)
        product = base.command(['git', 'diff', '--name-only', DELIVERED, *revision, '--',
            'lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock'])
        assert not product, 'Untested change outside the RPCS3 Core: ' + product
    core = core_module()
    core.validate_source_contract()
    core.validate_exact_pin(CORE_SOURCE)
    assert core.PATCH_SHA256 == PATCH_SHA256
    # Keep every unrelated source-built engine pin and every distribution gate.
    old = base.command(['git', 'show', BASELINE + ':.github/workflows/retroarch-delivery.yml'])
    current = (ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    for line in old.splitlines():
        if any(token in line for token in ['DOLPHIN_CORE_HOST_SHA:', 'ARMSX2_CORE_HOST_SHA:',
                'ARMSX2_CORE_RUN_ID:', 'LIBRETRO_CORES_HOST_SHA:', 'LIBRETRO_CORES_RUN_ID:']):
            assert line in current, line
    for name in ['validate_rpcs3_ipa.py', 'validate_single_ipa_distribution.py',
            'validate_neoswap_ipa.py', 'validate_unified_cheats_ipa.py', 'validate_hd_textures_ipa.py',
            'validate_melonx_ipa.py', 'validate_motion507_ipa.py', 'validate_melonx_delete509_ipa.py',
            'delivery_benchmark.py seal']:
        assert name in old and name in current, name
    assert 'validate_rpcs3_gow3_ipa.py' in current
    return {'baseline': BASELINE, 'delivered509Source': DELIVERED, 'delivered509Run': DELIVERED_RUN,
        'auditedCoreSource': CORE_SOURCE, 'auditedCoreRun': CORE_RUN,
        'canonicalPatchSHA256': PATCH_SHA256, 'rebuiltCores': ['RPCS3'],
        'allAppAndOtherEngineInputsPreserved': True, 'physicalDeviceTested': False}

def successful_core(wait):
    if wait:
        deadline = time.monotonic() + 10800
        while True:
            state = base.api('actions/runs/' + str(CORE_RUN))
            assert state['head_sha'] == CORE_SOURCE
            if state['status'] == 'completed':
                break
            assert time.monotonic() < deadline, 'Timed out waiting for the frozen GoW3 Core'
            print('Waiting for frozen GoW3 Core', CORE_RUN, state['status'], flush=True)
            time.sleep(30)
    return base.successful_run(CORE_RUN, CORE_SOURCE, ['RPCS3 GoW3: targeted proofs and iPhone Core'])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', default='full')
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--wait-for-components', action='store_true')
    parser.add_argument('--skin-session-evidence', action='store_true')
    parser.add_argument('--output', default='build/delivery/reused-validation.json')
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths', nargs='*')
    args = parser.parse_args()
    if args.rpc_core_inputs:
        validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    record = {'result': 'passed', 'source': base.command(['git', 'rev-parse', 'HEAD']),
        'sourceClosure': source_closure()}
    if not args.source_only:
        record['reusedEvidence'] = [
            base.successful_run(DELIVERED_RUN, DELIVERED, ['checks', 'native', 'Release device build • cold']),
            successful_core(args.wait_for_components)]
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS frozen GoW3 Core with authentic 509 frontend/MeloNX/other-engine evidence; no unchanged Flutter replay')

if __name__ == '__main__':
    main()
