"""Close the Switch retirement/deletion fix against the verified Build 508."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import rpcs3memory508_delivery as previous

base = previous.base
ROOT = Path(__file__).resolve().parents[2]
BASELINE = '0cacb83bb4acdb6e46b133a1c663d55023988be2'
DELIVERED = 'e44b0d34bcca18a193793704ca01db1eccf819a4'
DELIVERED_RUN = 39880551632
PRODUCT = {
    'lib/repositories/game_repository.dart',
    'lib/services/melonx_retired_library_cleanup.dart',
    'lib/l10n/melonx_transfer_locale.dart',
    'lib/widgets/delete_game_dialog.dart',
    'lib/widgets/melonx_multi_delete_dialog.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_manage_tab.dart',
}
TESTS = {'test/melonx_deletion_test.dart', 'test/melonx_retired_library_cleanup_test.dart'}
ALLOWED = PRODUCT | TESTS | {
    '.github/diagnostics/melonxdelete509_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/delivery-509-chatgpt-recipient.pem',
    'build-utils/validate_melonx_delete509_ipa.py',
    'docs/melonx-delete-build509.md', 'docs/evidence/melonx-delete509-delivery.json',
}
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_psp_core_identity = previous.validate_psp_core_identity


def source_closure():
    assert os.environ.get('GITHUB_REF_NAME') == 'Claude'
    assert os.environ.get('BUILD_NUMBER', '509') == '509'
    for revision in (['HEAD'], []):
        changed = set(base.command(['git', 'diff', '--name-only', BASELINE, *revision]).splitlines())
        assert not (changed - ALLOWED), sorted(changed - ALLOWED)
        product = set(base.command(['git', 'diff', '--name-only', BASELINE, *revision, '--',
            'lib', 'packages', 'assets', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock']).splitlines())
        assert product == PRODUCT, sorted(product ^ PRODUCT)
    # Native engines, host bindings, all catalogues, startup and routing retain
    # the exact successfully delivered inputs. No native Core is rebuilt.
    assert not base.command(['git', 'diff', '--name-only', DELIVERED, '--',
        'packages', 'assets', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock',
        'build-utils/rpcs3', 'build-utils/melonx', 'build-utils/armsx2', 'build-utils/libretro',
        'build-utils/prepare_fast_native_runtime.py', 'build-utils/sign_delivery.py',
        'build-utils/delivery_benchmark.py', 'build-utils/embed_legal_bundle.py',
        'docs/evidence/package-sources-license-audit-2026-10-21.json'])
    old = subprocess.check_output(['git','show',DELIVERED+':.github/workflows/retroarch-delivery.yml'], cwd=ROOT, text=True)
    current = (ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    for line in old.splitlines():
        if any(token in line for token in ['DOLPHIN_CORE_HOST_SHA:', 'ARMSX2_CORE_HOST_SHA:',
            'ARMSX2_CORE_RUN_ID:', 'RPCS3_CORE_HOST_SHA:', 'RPCS3_CORE_RUN_ID:',
            'LIBRETRO_CORES_HOST_SHA:', 'LIBRETRO_CORES_RUN_ID:']):
            assert line in current, line
    for name in ['validate_rpcs3_ipa.py','validate_single_ipa_distribution.py',
        'validate_neoswap_ipa.py','validate_unified_cheats_ipa.py','validate_hd_textures_ipa.py',
        'validate_melonx_ipa.py','validate_motion507_ipa.py','validate_rpcs3_memory_audit_ipa.py',
        'delivery_benchmark.py seal']:
        assert name in old and name in current, name
    return {'baseline': BASELINE, 'delivered508Source': DELIVERED,
        'delivered508Run': DELIVERED_RUN, 'productInputSHA256': {
            name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(PRODUCT)},
        'rebuiltCores': [], 'allBuild508NativeInputsPreserved': True,
        'retiredExternalReferencesPurgedBeforeIOSLibraryReads': True,
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
    record = {'result':'passed', 'source':base.command(['git','rev-parse','HEAD']),
        'sourceClosure':source_closure()}
    if not args.source_only:
        record['reusedEvidence'] = [base.successful_run(DELIVERED_RUN, DELIVERED,
            ['checks','native','Release device build • cold'])]
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2)+'\n')
    print('PASS exact Build 508 engines, RPCS3 audit and native inputs; targeted Switch app changes only.')


if __name__ == '__main__':
    main()
