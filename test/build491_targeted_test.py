#!/usr/bin/env python3
"""Targeted checks of Build 491: delivered Build 490 + Canvas (ES-DE) + KartPad removal.

Parts:
  host    Ubuntu: the Canvas (ES-DE) generator check, analysis of the whole app,
          the delivery Dart suite of retroarch-delivery.yml (read from the
          workflow itself, so both stay identical), every changed Dart test, the
          KartPad removal and refusal tests, and every changed Python contract
          (content gate, KartPad-free IPA validator, donor subset, locked
          library files, legal bundle, storage, Ports, NeoPlay);
  native  macOS: the NeoPlay companion harness (NPCheck) in the iOS Simulator,
          which compiles every NeoPlay Swift source, NPGameHUDAnchor.swift
          included, and runs test/neoplay/*_tests.swift.

Before running anything, each part checks that the inputs it declares cover
every non-documentation path changed since the delivered Build 490 (tag
build-490), so a change outside these lists fails instead of being delivered
untested. Each part writes build/build491/<part>-verdict.json with the SHA-256
of every input it tested. Nothing here claims an iPhone result.
"""
from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/build491'
BUILD = 491
# Delivered Build 490 source (tag build-490).
BASE = 'd152e5a270037484a435d641e04acd3a2ccaf3a6'
DELIVERY = '.github/workflows/retroarch-delivery.yml'
DART_SUITE_STEP = 'Validate changed library, callback, launch and restart behavior'


def _files(*roots):
    return set(subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', *roots], cwd=ROOT, text=True,
    ).split())


# Product files of Build 491 still present (the deleted KartPad files are
# checked absent by the delivery gate).
PRODUCT = sorted({
    # Canvas (ES-DE) System Art and the analyzer cleanup of the same session.
    'assets/legal/Canvas-ES-DE-ATTRIBUTION.md',
    'lib/services/neo_assets_service.dart',
    'lib/services/system_art/canvas_es_de_capsules.dart',
    'tools/system_art/canvas-es-de-flat-webp.txt',
    'tools/system_art/canvas_es_de.py',
    'lib/services/libretro_skin_catalog_service.dart',
    'lib/services/texture_catalog_service.dart',
    # KartPad removal.
    'assets/legal/THIRD_PARTY_NOTICES.md',
    'assets/systems/ports.json',
    'lib/l10n/ports_locale.dart',
    'lib/l10n/storage_locale.dart',
    'lib/models/game_model.dart',
    'lib/providers/sqlite_config_provider.dart',
    'lib/providers/sqlite_config_provider/scanning.dart',
    'lib/screens/game_screen/my_games_list.dart',
    'lib/screens/libretro/libretro_consoles_screen.dart',
    'lib/screens/settings_screen/legal_credits_dialog.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/external_display_setting_rows.dart',
    'lib/services/console_catalog.dart',
    'lib/services/external_display_service.dart',
    'lib/services/game/game_launch_service.dart',
    'lib/services/game/game_list_service.dart',
    'lib/services/game_launch_manager.dart',
    'lib/services/home_music_service.dart',
    'lib/services/music_player_service.dart',
    'lib/services/ports_game_identity.dart',
    'lib/utils/game_launch_utils.dart',
    'lib/widgets/ports_internal_playlist_actions.dart',
    'pubspec.yaml',
    'pubspec.lock',
})

# Packaging and legal scripts read by the delivery (no Dart).
PACKAGING = [
    'NOTICE.md',
    'build-utils/embed_legal_bundle.py',
    'build-utils/validate_legal_bundle_ipa.py',
    'build-utils/fetch_native_donor_subset.py',
    'build-utils/game_content_gate.py',
    'build-utils/validate_no_kartpad_ipa.py',
]

SUPPORT = ['test/build491_targeted_test.py', '.github/workflows/build491-checks.yml', DELIVERY]

HOST_PYTHON = [
    'test/no_kartpad_ipa_test.py',
    'test/game_content_gate_test.py',
    'test/native_donor_subset_test.py',
    'test/retroarch_baseline_scope_test.py',
    'test/cheats_media_source_contract_test.py',
    'test/embedded_engine_route_contract_test.py',
    'test/external_display_test.py',
    'test/game_close_status_test.py',
    'test/ports_external_display_test.py',
    'test/storage_contract_test.py',
    'test/legal_bundle_preflight_test.py',
    'test/neoplay_companion_contract_test.py',
]
# A runner of an earlier build whose test list lost a deleted KartPad test: it
# is compiled and its listed files must all exist, it is not run (macOS-only).
HOST_PYTHON_COMPILED = ['test/build486_targeted_test.py']

# Changed or affected Dart tests outside the delivery suite.
EXTRA_DART_TESTS = [
    'test/kartpad_removal_test.dart',
    'test/dusklight_ports_stage1_test.dart',
    'test/dusklight_library_test.dart',
    'test/external_display_unsupported_engine_test.dart',
    'test/game_box_render_preview_test.dart',
    'test/game_box_render_inspector_preview_test.dart',
    'test/scraping_streaming_md5_test.dart',
    'test/services/neo_assets_service_external_pack_test.dart',
]
# Changed Dart tests run by the delivery suite (listed so the coverage check
# sees them; the suite runs them).
SUITE_DART_TESTS = [
    'test/ambient_music_service_test.dart',
    'test/general_settings_external_display_test.dart',
    'test/libretro_skin_catalogs_test.dart',
    'test/storage_log_rotation_test.dart',
    'test/storage_picker_copies_test.dart',
]
SUITE_PYTHON = ['test/game_audio_handoff_test.py']

NATIVE = sorted(_files('packages/neoplay_bridge/ios/Classes', 'test/neoplay')
                | {'build-utils/neoplay_native_project.rb', 'test/neoplay_pod_graph_test.py',
                   'test/neoplay_deployment_project_test.py'})

HOST_INPUTS = PRODUCT + PACKAGING + SUPPORT + HOST_PYTHON + HOST_PYTHON_COMPILED + EXTRA_DART_TESTS \
    + SUITE_DART_TESTS + SUITE_PYTHON
NATIVE_INPUTS = NATIVE + SUPPORT
# Records, documentation and delivery wiring: no product or tested input.
NOT_TESTED = {'AGENTS.md', 'README.md', '.github/diagnostics/kartpad491_delivery.py',
              'build-utils/verify_delivery_reuse.py', 'build-utils/delivery_cipher.py',
              'build-utils/delivery-491-recipient.pem'}


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


def changed_since_490():
    subprocess.run(['git', 'cat-file', '-e', BASE + '^{commit}'], cwd=ROOT, check=True)
    paths = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--'], cwd=ROOT, text=True).split()
    paths += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).split()
    return {p for p in paths if (ROOT / p).is_file() and not p.startswith('docs/') and p not in NOT_TESTED}


def coverage():
    """Every changed file since Build 490 is an input of one part."""
    declared = set(HOST_INPUTS) | set(NATIVE_INPUTS)
    missing = {p for p in changed_since_490() if p not in declared
               and not (p.startswith('.github/workflows/') and p != '.github/workflows/build491-checks.yml')}
    if missing:
        raise SystemExit('Changed since Build 490 but not tested here: ' + ', '.join(sorted(missing)))
    for path in HOST_INPUTS + NATIVE_INPUTS:
        if not (ROOT / path).is_file():
            raise SystemExit('Declared input missing: ' + path)


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
    run([sys.executable, 'tools/system_art/canvas_es_de.py', '--check'], log)
    run(['flutter', 'pub', 'get', '--enforce-lockfile'], log)
    run(['flutter', 'analyze'], log)
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
    for test in HOST_PYTHON_COMPILED:
        run([sys.executable, '-m', 'py_compile', test], log)
        source = (ROOT / test).read_text()
        listed = re.findall(r"'(test/[^'*{}]+\.[a-z]+)'", source)
        absent = [p for p in listed if not (ROOT / p).exists()]
        if absent:
            raise SystemExit(f'{test} lists missing files: ' + ', '.join(absent))
    verdict('host', HOST_INPUTS, log)


def native():
    coverage()
    log = []
    OUT.mkdir(parents=True, exist_ok=True)
    run(['xcodebuild', '-version'], log)
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
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], text=True).strip()
    verdict('native', NATIVE_INPUTS, log, {'xcode': xcode, 'iphoneSDK': sdk, 'simulator': device})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--part', choices=['host', 'native', 'coverage'], required=True)
    args = parser.parse_args()
    if args.part == 'coverage':
        coverage()
        print('coverage: every changed file since Build 490 is a declared input')
        return
    {'host': host, 'native': native}[args.part]()


if __name__ == '__main__':
    main()
