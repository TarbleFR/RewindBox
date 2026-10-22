"""Build 502 test-delivery guard for the current RewindBox Claude candidate.

This lane is intentionally scoped to the exact already-reviewed Claude product
at BASE. Only delivery plumbing may differ from that base. Unlike the legacy
497 lane, Build 502 does not reuse stale Dart/NeoSwap/libretro verdicts: the
workflow re-runs the affected checks and native validation before packaging.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path
import psprelaunch497_delivery as previous

base = previous.base
BASE = '69a514390fffb1389977ca8863f0bb03f756db84'
BASE_UI_RUN = 39769356204
DELIVERY_ONLY = {
    '.github/diagnostics/psprelaunch502_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/delivery-502-chatgpt-recipient.pem',
    'test/library_ui_details_screen_test.dart',
    'test/library_ui_hub_test.dart',
    'test/libretro_host/frontend/session_journal_test.m',
    'test/libretro_frontend_test.py',
    'test/stikjit_scoped_host_test.py',
}

validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_rpc_core_pin = previous.validate_rpc_core_pin
rpc_core_input_view = previous.rpc_core_input_view


def source_closure():
    for end in (['HEAD'], []):
        changed = set(base.command(['git', 'diff', '--name-only', BASE, *end]).splitlines())
        extra = changed - DELIVERY_ONLY
        if extra:
            raise ValueError(
                'Unexpected product change after validated Claude base: '
                + ', '.join(sorted(extra))
            )
    # The exact base already passed the UI workflow that includes whole-app
    # analysis and the dedicated main-tab swipe arbitration tests.
    ui = base.successful_run(BASE_UI_RUN, BASE, ['test'])
    return {
        'validatedBase': BASE,
        'validatedUIRun': BASE_UI_RUN,
        'deliveryOnlyChanges': sorted(
            set(base.command(['git', 'diff', '--name-only', BASE, 'HEAD']).splitlines())
        ),
        'uiEvidence': ui,
        'deviceGameplayValidated': False,
    }


def _current_prerequisites():
    run_id = os.environ.get('GITHUB_RUN_ID')
    if not run_id:
        return None
    raw = subprocess.check_output(
        ['gh', 'api', f'repos/TarbleFR/RewindBox/actions/runs/{run_id}/jobs?per_page=100'],
        text=True,
    )
    jobs = json.loads(raw)['jobs']
    required = {}
    for name in ('checks', 'native'):
        job = next((j for j in jobs if j.get('name') == name), None)
        if job is None or job.get('conclusion') != 'success':
            raise ValueError(f'Current Build 502 prerequisite job is not successful: {name}')
        required[name] = {
            'id': job['id'],
            'conclusion': job['conclusion'],
            'head_sha': job.get('head_sha'),
        }
    return {'runId': int(run_id), 'jobs': required}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--dart-evidence', action='store_true')
    parser.add_argument('--libretro-evidence', action='store_true')
    parser.add_argument('--skin-session-evidence', action='store_true')
    parser.add_argument(
        '--scope',
        default='full',
        choices=['full', 'rpcs3_neoswap', 'library_covers'],
    )
    parser.add_argument('--output', default='build/delivery/build502-validation.json')
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths', nargs='*')
    args = parser.parse_args()

    closure = source_closure()
    if args.rpc_core_inputs:
        validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    if args.source_only:
        print('PASS exact validated Claude base + delivery-only Build 502 changes')
        return

    record = {
        'result': 'passed',
        'candidateSHA': base.command(['git', 'rev-parse', 'HEAD']),
        'sourceClosure': closure,
        'scope': args.scope,
        'validationWasReused': False,
        'deviceGameplayValidated': False,
    }
    if args.dart_evidence:
        record.update(
            key=os.environ.get('DART_VALIDATION_KEY', ''),
            tool='Flutter 3.47.2, Ubuntu 24.04',
        )
    if args.libretro_evidence:
        record.update(
            xcode=base.command(['xcodebuild', '-version']),
            iphoneSDK=base.command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version']),
        )
    if args.skin_session_evidence:
        record['currentPrerequisites'] = _current_prerequisites()

    out = base.ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS Build 502 exact source closure and current validation prerequisites')


if __name__ == '__main__':
    main()
