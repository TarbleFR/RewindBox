"""Bind Build 515 to the verified 514 application and exact restore/freeze Core."""
import argparse
import json
import os
from pathlib import Path

import rpcs3restore513_delivery as previous

ROOT = Path(__file__).resolve().parents[2]
base = previous.base
HOST = previous.HOST
core_module = previous.core_module
validate_psp_core_identity = previous.validate_psp_core_identity
BASELINE = 'dfdb87169601002bfef745e5fff605a0c2c3d398'
DELIVERED = '22df4502db21ee1bcd68e15c1791aeba1a826658'
DELIVERED_RUN = 39979130143
CORE_SOURCE = 'a69860297d7b26dbb688df0daf16a31b42046462'
CORE_RUN = 39982269326
PATCH_SHA256 = '388c5c37ed89c97d2b2aebd7642b611fd5a5ef2ed1d3c0cfa2be815357f66767'
ASSEMBLY = {
    '.github/workflows/retroarch-delivery.yml',
    '.github/diagnostics/rpcs3freeze515_delivery.py',
    'build-utils/delivery-515-chatgpt-recipient.pem',
    'build-utils/validate_rpcs3_gow3_ipa.py',
    'build-utils/validate_melonx_launch_ipa.py',
}
HOST_CHANGE = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'


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
    print('PASS exact restore/freeze Core source, host logging input, recipe and ABI')


def source_closure():
    assert os.environ.get('GITHUB_REF_NAME') == 'Claude'
    assert os.environ.get('BUILD_NUMBER', '515') == '515'
    for revision in (['HEAD'], []):
        changed = set(base.command(['git', 'diff', '--name-only', BASELINE, *revision]).splitlines())
        assert not changed - ASSEMBLY, sorted(changed - ASSEMBLY)
        product = set(base.command(['git', 'diff', '--name-only', DELIVERED, *revision, '--',
            'lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock']).splitlines())
        assert product == {HOST_CHANGE}, sorted(product)
    core = core_module()
    core.validate_source_contract()
    core.validate_exact_pin(CORE_SOURCE)
    assert core.PATCH_SHA256 == PATCH_SHA256
    old = base.command(['git', 'show', BASELINE + ':.github/workflows/retroarch-delivery.yml'])
    current = (ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    for line in old.splitlines():
        if any(key in line for key in ['DOLPHIN_CORE_HOST_SHA:', 'ARMSX2_CORE_HOST_SHA:',
                'ARMSX2_CORE_RUN_ID:', 'LIBRETRO_CORES_HOST_SHA:', 'LIBRETRO_CORES_RUN_ID:',
                'name: MeloNX-engine-', 'run-id: 39978893582',
                'name: MeloNX-native-dependencies-', 'run-id: 39854858591']):
            assert line in current, line
    for validator in ['validate_rpcs3_ipa.py', 'validate_single_ipa_distribution.py',
            'validate_neoswap_ipa.py', 'validate_unified_cheats_ipa.py', 'validate_hd_textures_ipa.py',
            'validate_melonx_ipa.py', 'validate_motion507_ipa.py', 'validate_melonx_delete509_ipa.py',
            'validate_rpcs3_gow3_ipa.py', 'validate_ui_correction511_ipa.py',
            'validate_navigation512_ipa.py', 'validate_melonx_launch_ipa.py',
            'delivery_benchmark.py seal']:
        assert validator in old and validator in current, validator
    return {'baseline': BASELINE, 'delivered514Source': DELIVERED,
        'delivered514Run': DELIVERED_RUN, 'auditedCoreSource': CORE_SOURCE,
        'auditedCoreRun': CORE_RUN, 'canonicalPatchSHA256': PATCH_SHA256,
        'hostChange': HOST_CHANGE, 'frontendAndOtherEngineSourcesPreserved': True,
        'physicalDeviceTested': False}


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
            base.successful_run(DELIVERED_RUN, DELIVERED,
                ['checks', 'native', 'Release device build • cold']),
            base.successful_run(CORE_RUN, CORE_SOURCE,
                ['RPCS3 GoW3: targeted proofs and iPhone Core'])]
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS verified Build 514 components plus exact restore/freeze Core and host diagnostics')


if __name__ == '__main__':
    main()
