"""Run the fresh610 suites and retain actual commands, exit codes and logs.

The RetroAchievements credentials fix (45d19d76) changed Dart, host plugins,
the central session plugin and the toast presenter after IPA609, so the 608
Flutter and Xcode16.4 groups run again on this exact source, extended with the
fix's own regression suite and the Core 610 RPCS3 profile/adapter suites. The
608 group helpers (translation XCTest, real iPhoneOS host compilation, central
receipt validation) are reused unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

import rewind610_baseline as tree
import rewind608_checks as checks608

ROOT = tree.ROOT
FLUTTER_TESTS = checks608.FLUTTER_TESTS + (
    'test/retro_achievements_login_regression_test.dart',
    'test/rpcs3_game_profile_service_test.dart',
    'test/rpcs3_profile_engine_test.dart',
    'test/rpcs3_guest_relay_launch_test.dart',
)
ANALYZE = checks608.ANALYZE + ('lib/services/rpcs3_config_adapter.dart', 'lib/services/rpcs3_game_profile_service.dart',
                               'lib/l10n/retro_achievements_status_locale.dart', 'lib/services/rpcs3_internal_service.dart',
                               'packages/neo_swap/lib')


def _flutter_group():
    group = []
    for name, argv in checks608.GROUPS['flutter']:
        if name == 'delivery-contract-tests':
            argv = ('python3', '-B', 'test/rewind610_delivery_contract_test.py')
        elif name == 'flutter-analysis':
            argv = ('flutter', 'analyze', *ANALYZE)
        elif name == 'flutter-behavior':
            argv = ('flutter', 'test', '--reporter', 'expanded', *FLUTTER_TESTS)
        group.append((name, argv))
    return tuple(group)


def _native_group():
    group = []
    for name, argv in checks608.GROUPS['native']:
        if name == 'translation-xctest':
            argv = ('python3', '-B', '.github/diagnostics/rewind610_checks.py', 'translation')
        elif name == 'actual-flutter-host-compile':
            argv = ('python3', '-B', '.github/diagnostics/rewind610_checks.py', 'hosts')
        group.append((name, argv))
    return tuple(group)


GROUPS = {'flutter': _flutter_group(), 'native': _native_group()}


def command_names(group):
    return [name for name, _ in GROUPS[group]]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return value


def execution():
    source = os.environ['GITHUB_SHA']
    tree.require(re.fullmatch('[0-9a-f]{40}', source) and source == tree.git('rev-parse', 'HEAD'),
                 'Test checkout differs from the workflow SHA')
    return dict(source=source, tree=tree.git('rev-parse', 'HEAD^{tree}'),
                run=int(os.environ['GITHUB_RUN_ID']), attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))


def run(group):
    tree.require(group in GROUPS, 'Unknown610 test group')
    tree.verify()
    directory = ROOT / 'build/validation610' / group
    directory.mkdir(parents=True, exist_ok=True)
    receipt = dict(schema=1, result='running', group=group, execution=execution(),
        sourceScopeSHA256=tree.sha((ROOT / tree.CONFIG).read_bytes()), commands=[],
        physicalDeviceTested=False, translationModelsDownloaded=False)
    if group == 'native':
        receipt['xcodeVersion'] = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
        receipt['swiftVersion'] = subprocess.check_output(['xcrun', 'swift', '--version'], text=True).strip()
        tree.require(receipt['xcodeVersion'].startswith('Xcode 16.4\n'), 'Select Xcode16.4 before targeted tests')
    first_failure = 0
    for name, arguments in GROUPS[group]:
        start = time.monotonic()
        log = directory / (name + '.log')
        print('+ ' + ' '.join(arguments), flush=True)
        with log.open('wb') as output:
            try:
                process = subprocess.run(arguments, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=1800)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 124
        raw = log.read_bytes()
        print(raw.decode(errors='replace')[-18000:], flush=True)
        receipt['commands'].append(dict(name=name, argv=list(arguments), exitCode=code,
            seconds=round(time.monotonic() - start, 3), log=log.name, logSHA256=tree.sha(raw)))
        if code:
            first_failure = first_failure or code
            receipt['result'] = 'failed'
        save(directory / 'validation.json', receipt)
    if first_failure:
        # Keep independent diagnostics from this exact source; no IPA can consume a failed group.
        raise SystemExit(first_failure)
    receipt['result'] = 'passed'
    if group == 'native':
        result = json.loads((ROOT / 'build/ra-session-validation/validation.json').read_bytes())
        receipt['centralSessionXCTest'] = checks608.validate_central_receipt(result)
    return save(directory / 'validation.json', receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['flutter', 'native', 'translation', 'hosts'])
    args = parser.parse_args()
    if args.operation in GROUPS:
        print(json.dumps(run(args.operation), indent=2))
    elif args.operation == 'translation':
        checks608.translation()
    else:
        checks608.hosts()
