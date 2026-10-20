#!/usr/bin/env python3
"""Targeted checks of Build 492: Build 491 without Dusklight and without the Ports playlist.

Maintainer decision of 20 October 2026 (docs/ports-removal-2026-10-20.md).

Parts:
  host    Ubuntu: absence of every removed Dusklight/Ports path, the Canvas
          (ES-DE) generator check (the Ports capsule left), analysis of the
          whole app, the delivery Dart suite of retroarch-delivery.yml (read
          from the workflow itself), every changed Dart test outside it (the
          checked database copy before the Ports rows leave, the refused launch
          of a former Ports game), every changed Python contract (Dusklight-free
          IPA validator, donor subset, locked library files, legal bundle,
          storage, routes, external display, NeoPlay), two tests that already
          failed on Build 491 (no new failing case allowed), and source proofs
          for the changes that only touch comments or assertion messages;
  native  macOS: the NeoPlay companion harness (NPCheck) in the iOS Simulator,
          which compiles every NeoPlay Swift source, NPGameHUDAnchor.swift
          included, and the iPhone arm64 syntax of every external_display
          Objective-C source against the pinned Flutter.xcframework.

Before running anything, each part checks that the inputs it declares cover
every non-documentation path changed since Build 491 (delivered 9faa3f9b), so a
change outside these lists fails instead of being delivered untested. Each part
writes build/build492/<part>-verdict.json with the SHA-256 of every input it
tested. Nothing here claims an iPhone result.
"""
from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/build492'
BUILD = 492
# Build 491 delivery source (KartPad removal, Canvas ES-DE; run 39353891715; product
# identical to 59bec98c, the commits since touched only its gate and records).
BASE = '9faa3f9b07f93b4fdca19a0a325a9180fe75b20f'
DELIVERY = '.github/workflows/retroarch-delivery.yml'
DART_SUITE_STEP = 'Validate changed library, callback, launch and restart behavior'


def _files(*roots):
    return set(subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', *roots], cwd=ROOT, text=True,
    ).split())


# Removed by Build 492: none of them may exist again.
REMOVED = [
    'native/dusklight',
    'packages/dusklight_internal_bridge',
    'build-utils/dusklight',
    'build-utils/validate_dusklight_ipa.py',
    '.github/workflows/dusklight-core.yml',
    'assets/legal/Dusklight-CC0-1.0.txt',
    'assets/systems/ports.json',
    'assets/images/ports-gaming.webp',
    'lib/l10n/dusklight_locale.dart',
    'lib/l10n/ports_locale.dart',
    'lib/services/dusklight_internal_service.dart',
    'lib/services/dusklight_game_identity.dart',
    'lib/services/ports_game_identity.dart',
    'lib/widgets/ports_internal_playlist_actions.dart',
]

# Product files of Build 492 still present (Dart, assets, packages).
PRODUCT = sorted({
    'assets/legal/THIRD_PARTY_NOTICES.md',
    'lib/data/datasources/sqlite_database_service.dart',
    'lib/data/datasources/sqlite_service.dart',
    'lib/l10n/storage_locale.dart',
    'lib/providers/sqlite_config_provider.dart',
    'lib/providers/sqlite_config_provider/scanning.dart',
    'lib/repositories/scraper_repository.dart',
    'lib/repositories/system_repository.dart',
    'lib/screens/game_screen/game_details_card/game_details_card_list.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_emulator_tab.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_manage_tab.dart',
    'lib/screens/game_screen/my_games_list.dart',
    'lib/screens/libretro/libretro_consoles_screen.dart',
    'lib/screens/settings_screen/legal_credits_dialog.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/external_display_setting_rows.dart',
    'lib/screens/systems_screen/my_systems_section/system_card.dart',
    'lib/services/console_catalog.dart',
    'lib/services/game/game_launch_service.dart',
    'lib/services/game_launch_manager.dart',
    'lib/services/retired_ports_backup.dart',
    'lib/services/screenscraper_service.dart',
    'lib/services/storage/storage_categorizer.dart',
    'lib/services/storage/storage_cleanup_planner.dart',
    'lib/services/storage/storage_orphan_detector.dart',
    'lib/services/storage/storage_roots.dart',
    'lib/services/system_art/canvas_es_de_capsules.dart',
    'lib/utils/game_launch_utils.dart',
    'lib/widgets/libretro_engine_panel.dart',
    'lib/widgets/system_emulator_settings_dialog.dart',
    'packages/external_display/lib/external_display.dart',
    'pubspec.yaml',
    'pubspec.lock',
})

# Objective-C sources whose only change is in comments (proved below against
# Build 491) and compiled for iPhone by the native part.
COMMENT_ONLY = [
    'packages/external_display/ios/Classes/ExternalDisplayPlugin.m',
    'packages/external_display/ios/Classes/NeoExternalDisplayCoordinator.h',
]
# A Simulator XCTest that no gate executes (docs/build484 note on
# external-display-check): only the text of assertion messages changed.
MESSAGE_ONLY = ['test/external_display_ui_test.py']

# Packaging and legal scripts read by the delivery (no Dart).
PACKAGING = [
    'NOTICE.md',
    'build-utils/delivery_cipher.py',
    'build-utils/embed_legal_bundle.py',
    'build-utils/validate_legal_bundle_ipa.py',
    'build-utils/fetch_native_donor_subset.py',
    'build-utils/prepare_fast_native_runtime.py',
    'build-utils/game_content_gate.py',
    'build-utils/validate_no_kartpad_ipa.py',
    'build-utils/validate_no_dusklight_ipa.py',
    'tools/system_art/canvas_es_de.py',
]

SUPPORT = ['test/build492_targeted_test.py', '.github/workflows/build492-checks.yml', DELIVERY]

HOST_PYTHON = [
    'test/no_dusklight_ipa_test.py',
    'test/no_kartpad_ipa_test.py',
    'test/game_content_gate_test.py',
    'test/native_donor_subset_test.py',
    'test/retroarch_baseline_scope_test.py',
    'test/legal_bundle_preflight_test.py',
    'test/cheats_media_source_contract_test.py',
    'test/embedded_engine_route_contract_test.py',
    'test/external_display_test.py',
    'test/game_close_status_test.py',
    'test/game_launch_route_test.py',
    'test/storage_contract_test.py',
    'test/neoplay_companion_contract_test.py',
]
# Already failing on Build 491 for reasons this build does not touch; each was
# updated for the removal. Run here and at Build 491: no new failing case.
PRE_EXISTING = [
    'test/build351_native_donor_test.py',
    'test/external_display_host_plist_test.py',
]

# Changed Dart tests outside the delivery suite.
EXTRA_DART_TESTS = [
    'test/retired_ports_backup_test.dart',
    'test/retired_ports_launch_test.dart',
]
# Changed Dart tests run by the delivery suite (listed so the coverage check
# sees them; the suite runs them).
SUITE_DART_TESTS = [
    'test/armsx2_embedded_library_contract_test.dart',
    'test/console_manager_test.dart',
    'test/external_display_unsupported_engine_test.dart',
    'test/general_settings_external_display_test.dart',
    'test/libretro_consoles_tab_test.dart',
    'test/libretro_engine_settings_test.dart',
    'test/rpcs3_embedded_identity_test.dart',
    'test/storage_categorizer_test.dart',
    'test/storage_cleanup_planner_test.dart',
    'test/storage_picker_copies_test.dart',
    'test/storage_roots_test.dart',
    'test/storage_scanner_test.dart',
]
SUITE_PYTHON = ['test/game_audio_handoff_test.py']

NATIVE = sorted(_files('packages/neoplay_bridge/ios/Classes', 'test/neoplay', 'packages/external_display/ios/Classes')
                | {'build-utils/neoplay_native_project.rb', 'test/neoplay_pod_graph_test.py',
                   'test/neoplay_deployment_project_test.py'})

HOST_INPUTS = PRODUCT + COMMENT_ONLY + MESSAGE_ONLY + PACKAGING + SUPPORT + HOST_PYTHON + PRE_EXISTING \
    + EXTRA_DART_TESTS + SUITE_DART_TESTS + SUITE_PYTHON
NATIVE_INPUTS = NATIVE + SUPPORT
# Records, documentation and delivery wiring: no product or tested input.
NOT_TESTED = {'AGENTS.md', 'README.md', '.github/diagnostics/portsremoval492_delivery.py',
              'build-utils/delivery-492-recipient.pem'}


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def run(cmd, log, cwd=ROOT, check=True, shell=False):
    started = time.time()
    shown = cmd if shell else ' '.join(cmd)
    print('$', shown, flush=True)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=shell)
    log.append({
        'command': shown,
        'returncode': result.returncode,
        'seconds': round(time.time() - started, 1),
        'stdoutTail': result.stdout[-4000:],
        'stderrTail': result.stderr[-4000:],
    })
    sys.stdout.write(result.stdout[-6000:])
    sys.stderr.write(result.stderr[-6000:])
    if check and result.returncode != 0:
        raise SystemExit(f'failed ({result.returncode}): {shown}')
    return result


def changed_since_491():
    subprocess.run(['git', 'cat-file', '-e', BASE + '^{commit}'], cwd=ROOT, check=True)
    paths = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--'], cwd=ROOT, text=True).split()
    paths += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).split()
    return {p for p in paths if (ROOT / p).is_file() and not p.startswith('docs/') and p not in NOT_TESTED}


def coverage():
    """Every changed file since Build 491 is an input of one part; every removed path stays absent."""
    declared = set(HOST_INPUTS) | set(NATIVE_INPUTS)
    missing = {p for p in changed_since_491() if p not in declared
               and not (p.startswith('.github/workflows/') and p != '.github/workflows/build492-checks.yml')}
    if missing:
        raise SystemExit('Changed since Build 491 but not tested here: ' + ', '.join(sorted(missing)))
    for path in HOST_INPUTS + NATIVE_INPUTS:
        if not (ROOT / path).is_file():
            raise SystemExit('Declared input missing: ' + path)
    back = [path for path in REMOVED if (ROOT / path).exists()]
    if back:
        raise SystemExit('Removed by Build 492 but present again: ' + ', '.join(back))


def base_text(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT, text=True)


def strip_c_comments(text):
    """C/Objective-C text without comments; string and character literals kept."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in '"\'':
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith('//', i):
            i = text.find('\n', i)
            i = n if i < 0 else i
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            if end < 0:
                raise SystemExit('Unterminated comment')
            i = end + 2
        else:
            out.append(c)
            i += 1
    return ' '.join(''.join(out).split())


def message_only(old, new):
    """Lines changed only inside @"..." literals (assertion messages)."""
    literal = re.compile(r'@"(?:[^"\\]|\\.)*"')
    a, b = old.splitlines(), new.splitlines()
    if len(a) != len(b):
        return False
    return all(literal.sub('@""', x) == literal.sub('@""', y) for x, y in zip(a, b))


def source_proofs(log):
    for path in COMMENT_ONLY:
        if strip_c_comments(base_text(path)) != strip_c_comments((ROOT / path).read_text()):
            raise SystemExit(f'{path}: more than comments changed since Build 491')
    for path in MESSAGE_ONLY:
        if not message_only(base_text(path), (ROOT / path).read_text()):
            raise SystemExit(f'{path}: more than assertion messages changed since Build 491')
    log.append({'command': 'source proofs: comments only in ' + ', '.join(COMMENT_ONLY)
                + '; assertion messages only in ' + ', '.join(MESSAGE_ONLY),
                'returncode': 0, 'seconds': 0, 'stdoutTail': '', 'stderrTail': ''})


def failing_cases(output):
    """Failing case names of a unittest run, or the SystemExit message of a script."""
    cases = set(re.findall(r'^(?:FAIL|ERROR): (\S+ \([^)]*\))', output, re.M))
    if not cases:
        lines = [line for line in output.strip().splitlines() if line.strip()]
        cases = {lines[-1]} if lines else set()
    return cases


def pre_existing(log):
    """Each test fails at Build 491; the candidate may not add a failing case."""
    with tempfile.TemporaryDirectory(prefix='build491-') as directory:
        tree = Path(directory) / 'tree'
        subprocess.run(['git', 'worktree', 'add', '--detach', str(tree), BASE], cwd=ROOT, check=True,
                       capture_output=True)
        try:
            for test in PRE_EXISTING:
                before = run([sys.executable, test], log, cwd=tree, check=False)
                after = run([sys.executable, test], log, check=False)
                old = failing_cases(before.stdout + before.stderr)
                new = failing_cases(after.stdout + after.stderr)
                if before.returncode == 0:
                    raise SystemExit(f'{test} passes at Build 491: run it as an ordinary check')
                if after.returncode != 0 and not new <= old:
                    raise SystemExit(f'{test}: new failing case(s) {sorted(new - old)}')
        finally:
            subprocess.run(['git', 'worktree', 'remove', '--force', str(tree)], cwd=ROOT, check=False)


def delivery_dart_suite():
    """The delivery job's Dart suite, line for line, up to its record heredoc."""
    lines = (ROOT / DELIVERY).read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == '- name: ' + DART_SUITE_STEP)
    if lines[start + 1].strip() != 'run: |':
        raise SystemExit('Unexpected delivery Dart suite layout')
    commands = []
    for line in lines[start + 2:]:
        text = line.strip()
        if text.startswith("python3 - <<"):
            break
        if text.startswith('#') or not text:
            continue
        if not (text.startswith('flutter test ') or text.startswith('python3 test/')):
            raise SystemExit('Unexpected command in the delivery Dart suite: ' + text)
        commands.append(text)
    if len(commands) < 8:
        raise SystemExit('Delivery Dart suite not found')
    return commands


def verdict(part, inputs, log, extra=None):
    OUT.mkdir(parents=True, exist_ok=True)
    data = {
        'build': BUILD,
        'part': part,
        'result': 'passed',
        'coreRebuilt': False,
        'deviceValidated': False,
        'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'host': platform.platform(),
        'inputsSHA256': {p: sha(p) for p in sorted(set(inputs)) if (ROOT / p).is_file()},
        'removedAbsent': REMOVED,
        'checks': [entry['command'] for entry in log],
        'timingsSeconds': {entry['command']: entry['seconds'] for entry in log},
        'commands': log,
        **(extra or {}),
    }
    (OUT / f'{part}-verdict.json').write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f'{part}: passed, {len(data["inputsSHA256"])} inputs recorded')


def host():
    coverage()
    log = []
    source_proofs(log)
    run([sys.executable, 'tools/system_art/canvas_es_de.py', '--check'], log)
    run(['flutter', 'pub', 'get', '--enforce-lockfile'], log)
    run(['flutter', 'analyze', '--no-fatal-infos'], log)
    suite = delivery_dart_suite()
    tokens = {token for command in suite for token in command.split()}
    for test in SUITE_DART_TESTS + SUITE_PYTHON:
        if not any(fnmatch.fnmatchcase(test, token) for token in tokens):
            raise SystemExit('Expected the delivery suite to run ' + test)
    for command in suite:
        run(command, log, shell=True)
    run(['flutter', 'test', *EXTRA_DART_TESTS], log)
    for test in HOST_PYTHON:
        run([sys.executable, test], log)
    pre_existing(log)
    verdict('host', HOST_INPUTS, log)


def native():
    coverage()
    log = []
    OUT.mkdir(parents=True, exist_ok=True)
    run(['xcodebuild', '-version'], log)
    # external_display: iPhone arm64 syntax of every Objective-C source against
    # the Flutter.xcframework of the pinned Flutter (as external-display-check).
    root = Path(shutil.which('flutter')).resolve().parents[1]
    xcframework = root / 'bin/cache/artifacts/engine/ios/Flutter.xcframework'
    slices = sorted(p for p in xcframework.glob('ios-arm64*') if 'simulator' not in p.name)
    if not slices or not (slices[0] / 'Flutter.framework/Flutter').is_file():
        raise SystemExit('Flutter device slice missing under ' + str(xcframework))
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    sources = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'packages/external_display/ios/Classes').glob('*.m'))
    if not sources:
        raise SystemExit('No Objective-C source in packages/external_display/ios/Classes')
    for source in sources:
        run(['xcrun', 'clang', '-fsyntax-only', '-x', 'objective-c', '-fobjc-arc', '-fmodules', '-Wall',
             '-arch', 'arm64', '-isysroot', sdk, '-miphoneos-version-min=17.4', '-F', str(slices[0]),
             '-I', 'packages/external_display/ios/Classes', source], log)
    run(['gem', 'install', 'xcodeproj', '--no-document', '--user-install'], log)
    gem_home = subprocess.check_output(['ruby', '-e', 'puts Gem.user_dir'], text=True).strip()
    env_prefix = f'GEM_HOME="{gem_home}" '
    run([sys.executable, 'test/neoplay_deployment_project_test.py'], log)
    run(env_prefix + 'ruby build-utils/neoplay_native_project.rb', log, shell=True)
    run(['pod', 'install', '--project-directory=build/neoplay-native'], log)
    run([sys.executable, 'test/neoplay_pod_graph_test.py'], log)
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True))
    device = next(x['udid'] for k, a in devices['devices'].items() if 'iOS-18' in k for x in a if 'iPhone' in x['name'])
    run(['xcodebuild', 'test', '-workspace', 'build/neoplay-native/NPCheck.xcworkspace', '-scheme', 'NPCheck',
         '-parallel-testing-enabled', 'NO', '-destination', f'id={device}',
         '-resultBundlePath', str(OUT / 'NPCheck.xcresult'), 'CODE_SIGNING_ALLOWED=NO'], log)
    xcode = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
    sdk_version = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], text=True).strip()
    verdict('native', NATIVE_INPUTS, log, {'xcode': xcode, 'iphoneSDK': sdk_version, 'simulator': device,
                                            'externalDisplaySources': sources})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--part', choices=['host', 'native', 'coverage', 'proofs'], required=True)
    args = parser.parse_args()
    if args.part == 'coverage':
        coverage()
        print('coverage: every changed file since Build 491 is a declared input; removed paths absent')
        return
    if args.part == 'proofs':
        source_proofs([])
        print('proofs: comment-only and message-only changes confirmed against Build 491')
        return
    {'host': host, 'native': native}[args.part]()


if __name__ == '__main__':
    main()
