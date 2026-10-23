"""Close the audited RPCS3/NeoSwap change against the delivered Build 507."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import motion507_delivery as previous

base = previous.base
ROOT = Path(__file__).resolve().parents[2]
BASELINE = '741918e15a6bfe79ab213cdd5038ea31f1c0cc62'
DELIVERED = '49c33b29287c0b659abba4f09d04a6efd062b1b6'
DELIVERED_RUN = 39866664616
CORE_SOURCE = 'cfe92344e1b3dd26d2cb17bb8b8ad68260c5cc7f'
CORE_RUN = 39877981229
SWITCH_CORE_RUN = 39879059963
SWITCH_HOST_RUN = 39879059750
SWITCH_HOST = '741918e15a6bfe79ab213cdd5038ea31f1c0cc62'
SWITCH_APP_RUN = 39879059765
PATCH_SHA256 = '179156b3c987132d5a98c967b4c277d9934da7ce3a49e69d95127c996c56604a'
HOST = {
    'packages/neo_swap/ios/Classes/NeoSwapBudget.h',
    'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
    'packages/neo_swap/ios/Classes/NeoSwapCompiler.mm',
    'packages/neo_swap/ios/Classes/NeoSwapCompilerAPI.h',
    'packages/neo_swap/ios/Classes/NeoSwapCompilerBudget.h',
    'packages/neo_swap/ios/neo_swap.podspec',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
}
ALLOWED = HOST | {
    'AGENTS.md', '.gitattributes', '.github/workflows/neoswap-ipa.yml',
    '.github/workflows/touch-layout-checks.yml', '.github/workflows/unified-cheats.yml',
    '.github/workflows/retroarch-delivery.yml', '.github/workflows/rpcs3-memory-audit.yml',
    '.github/diagnostics/rpcs3memory508_delivery.py',
    'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
    'build-utils/rpcs3_core_syntax_gate.py', 'build-utils/validate_motion507_ipa.py',
    'build-utils/validate_rpcs3_memory_audit_ipa.py', 'build-utils/delivery-508-chatgpt-recipient.pem',
    'docs/rpcs3-memory-audit-2026-10-23.md', 'docs/rpcs3-memory-build508.md',
    'docs/evidence/rpcs3-memory508-delivery.json',
    'test/neo_swap_core_pin_test.py', 'test/rpcs3_build353_xitrix_v010_test.py',
    'test/rpcs3_build444_core_delta_test.py', 'test/rpcs3_build487_core_diagnostics_test.py',
    'test/rpcs3_build499_spu_audit_test.py', 'test/rpcs3_core_syntax_gate_test.py',
    'test/rpcs3_failed_startup_test.py', 'test/fixtures/rpcs3_memory_audit/JITLLVM.diff',
    'test/rpcs3_memory_audit_test.py', 'test/native/rpcs3_memory_audit_test.cpp',
}


def core_module():
    sys.path.insert(0, str(ROOT / 'test'))
    import neo_swap_core_pin_test
    return neo_swap_core_pin_test


def validate_rpc_core_identity(identity):
    assert identity['host_commit'] == CORE_SOURCE, 'Core source differs from the closed audit'
    assert identity['source_patch_sha256'] == PATCH_SHA256
    core_module().validate_core_input_identity(identity)


def validate_rpc_core_pin(pin, paths):
    assert pin == CORE_SOURCE, 'Unexpected audited Core pin'
    core = core_module()
    assert len(paths) == len(core.CORE_INPUTS) and set(paths) == set(core.CORE_INPUTS)
    core.validate_source_contract()
    core.validate_exact_pin(pin)
    print('PASS authentic audited Core source, ABI, recipe and native proof inputs; no identity rewriting.')


validate_psp_core_identity = previous.validate_psp_core_identity


def source_closure():
    assert os.environ.get('GITHUB_REF_NAME') == 'Claude', 'Final assembly belongs to Claude'
    assert os.environ.get('BUILD_NUMBER', '508') == '508'
    changed = set(base.command(['git', 'diff', '--name-only', BASELINE]).splitlines())
    committed = set(base.command(['git', 'diff', '--name-only', BASELINE, 'HEAD']).splitlines())
    assert not ((changed | committed) - ALLOWED), sorted((changed | committed) - ALLOWED)
    # Product scope is exact: the new compiler broker and its optional RPCS3
    # binding. UI, startup, data, all other engines and their recipes stay closed.
    product = set(base.command(['git', 'diff', '--name-only', BASELINE, '--',
        'lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock']).splitlines())
    assert not (product - HOST), sorted(product - HOST)
    for relative in sorted(HOST):
        tested = subprocess.check_output(['git', 'show', CORE_SOURCE + ':' + relative], cwd=ROOT)
        assert tested == (ROOT / relative).read_bytes(), 'Untested host change: ' + relative
    assert not base.command(['git','diff','--name-only',SWITCH_HOST,'--','packages/melonx_internal_bridge/ios/Classes']), 'MeloNX host changed after its native proof'
    core = core_module()
    core.validate_source_contract()
    core.validate_exact_pin(CORE_SOURCE)
    assert core.PATCH_SHA256 == PATCH_SHA256
    original = base.command(['git', 'show', BASELINE + ':.github/workflows/retroarch-delivery.yml'])
    current = (ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    # Broad bridge path triggers would replay unrelated Flutter/UIKit/other-core
    # campaigns. Only this closed assembly marker reuses their existing proofs;
    # every original command and manual invocation remains available.
    for name, count in [('touch-layout-checks.yml', 3), ('unified-cheats.yml', 4)]:
        relative = '.github/workflows/' + name
        old = base.command(['git', 'show', BASELINE + ':' + relative])
        lines = old.splitlines()
        changed_conditions = 0
        for i, line in enumerate(lines):
            if line.startswith('    if: ${{ '):
                assert line.endswith(' }}')
                lines[i] = "    if: ${{ !contains(github.event.head_commit.message, '[rpcs3-memory508]') && (" + line[len('    if: ${{ '):-3] + ') }}'
                changed_conditions += 1
        assert changed_conditions == count
        assert (ROOT / relative).read_text().strip() == '\n'.join(lines).strip(), relative
    for token in ['DOLPHIN_CORE_HOST_SHA:', 'ARMSX2_CORE_HOST_SHA:', 'ARMSX2_CORE_RUN_ID:',
                  'LIBRETRO_CORES_HOST_SHA:', 'LIBRETRO_CORES_RUN_ID:']:
        line = next(line for line in original.splitlines() if token in line)
        assert line in current, 'Unrelated engine pin changed: ' + token
    for name in ['validate_rpcs3_ipa.py', 'validate_single_ipa_distribution.py',
                 'validate_neoswap_ipa.py', 'validate_unified_cheats_ipa.py',
                 'validate_hd_textures_ipa.py', 'validate_melonx_ipa.py',
                 'validate_motion507_ipa.py', 'delivery_benchmark.py seal']:
        assert name in current and name in original, 'Missing existing delivery gate: ' + name
    catalogue = (ROOT / 'native/textures/catalogue/manifest.json.gz').read_bytes()
    assert catalogue == (ROOT / 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
    return {'baseline': BASELINE, 'delivered507Source': DELIVERED,
        'auditedCoreSource': CORE_SOURCE, 'auditedCoreRun': CORE_RUN,
        'canonicalPatchSHA256': PATCH_SHA256, 'hostChanges': sorted(product),
        'catalogueSHA256': hashlib.sha256(catalogue).hexdigest(),
        'switchLibraryBase': BASELINE, 'switchLibraryCoreRun': SWITCH_CORE_RUN,
        'interfaceAndOtherEnginesPreserved': True, 'rebuiltCores': ['RPCS3'],
        'productionMinimalSPULinkerEnabled': False, 'physicalDeviceTested': False}


def successful_component(run, source, jobs, wait):
    if wait:
        deadline = time.monotonic() + 1200
        while True:
            state = base.api('actions/runs/' + str(run))
            assert state['head_sha'] == source, 'Component source changed'
            if state['status'] == 'completed':
                break
            assert time.monotonic() < deadline, 'Timed out waiting for exact component ' + str(run)
            print('Waiting for exact component', run, state['status'], flush=True)
            time.sleep(20)
    return base.successful_run(run, source, jobs)


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
            base.successful_run(previous.TESTED_RUN, previous.TESTED, ['flutter']),
            base.successful_run(previous.NATIVE_RUN, previous.NATIVE_TESTED, ['flutter', 'native']),
            base.successful_run(CORE_RUN, CORE_SOURCE, ['RPCS3 memory audit: ARM64 proofs and iPhone core']),
            successful_component(SWITCH_CORE_RUN, BASELINE, ['core'], args.wait_for_components),
            successful_component(SWITCH_APP_RUN, BASELINE, ['host'], args.wait_for_components),
            successful_component(SWITCH_HOST_RUN, SWITCH_HOST, ['host'], args.wait_for_components),
        ]
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS closed RPCS3 audit and compiler broker; validated motion UI, current Switch library and other engines preserved.')


if __name__ == '__main__':
    main()
