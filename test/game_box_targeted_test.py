#!/usr/bin/env python3
"""Targeted checks of the 3D game box (Jaquette view, inspector, back reader).

Parts:
  host    Ubuntu: catalogue generator, 12-language coverage, locked library
          files, Flutter analysis of every changed Dart file, the new Flutter
          suites and every existing suite that reads a changed file;
  native  macOS: the plugin's text recognition code with Apple's Vision and
          NaturalLanguage on macOS and in the iOS Simulator (twelve languages),
          the Translation availability of the twelve targets, and a type check
          of the plugin's Swift sources against the iPhone SDK and Flutter.

Each part writes build/gamebox/<part>-verdict.json with the SHA-256 of every
input it tested. Nothing here claims an iPhone result: the Simulator runs
Vision on the host CPU and cannot download translation models.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/gamebox'
BUILD = 490


def _files(*roots):
    return set(subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', *roots], cwd=ROOT, text=True,
    ).split())


PRODUCT = sorted({
    'lib/l10n/game_box_locale.dart',
    'lib/screens/game_screen/my_games_carousel.dart',
    'lib/repositories/game_repository.dart',
    'lib/services/screenscraper_service.dart',
    'lib/services/screenscraper/media_downloader.dart',
    'lib/services/screenscraper/media_resolver.dart',
    'pubspec.yaml',
} | _files('lib/services/game_box', 'lib/widgets/game_box', 'lib/screens/game_box', 'packages/neo_box_reader'))

SUPPORT = sorted(_files('tools/game_box') | {'test/game_box_targeted_test.py', '.github/workflows/game-box-checks.yml'})

HOST_PYTHON = [
    'test/game_box_strings_test.py',
    'test/localization_12_locale_coverage_test.py',
    'test/retroarch_baseline_scope_test.py',
]

DART_TESTS = [
    'test/game_box_geometry_test.dart',
    'test/game_box_media_test.dart',
    'test/game_box_text_test.dart',
    'test/game_box_inspector_test.dart',
    'test/game_box_locale_test.dart',
    # Existing suites that read a changed file.
    'test/game_deletion_regression_test.dart',
    'test/game_repository_test.dart',
    'test/screenscraper_manual_media_test.dart',
    'test/screenscraper_service_test.dart',
    'test/rainbow_selection_fairy_test.dart',
    'test/ios_selective_rollback_test.dart',
    'test/storage_orphan_detector_test.dart',
]

ANALYZED = [p for p in PRODUCT if p.endswith('.dart')] + [p for p in DART_TESTS if p.startswith('test/game_box')]

RECOGNIZER = 'packages/neo_box_reader/ios/Classes/BoxTextRecognizer.swift'
NATIVE_MAIN = 'packages/neo_box_reader/ci/main.swift'


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def run(cmd, log, env=None, cwd=ROOT, check=True):
    started = time.time()
    print('$', ' '.join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    log.append({
        'command': cmd,
        'returncode': result.returncode,
        'seconds': round(time.time() - started, 1),
        'stdoutTail': result.stdout[-4000:],
        'stderrTail': result.stderr[-4000:],
    })
    sys.stdout.write(result.stdout[-6000:])
    sys.stderr.write(result.stderr[-6000:])
    if check and result.returncode != 0:
        raise SystemExit(f'failed ({result.returncode}): {" ".join(cmd)}')
    return result


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
        'inputsSHA256': {p: sha(p) for p in sorted(set(inputs)) if (ROOT / p).exists()},
        'checks': [' '.join(entry['command']) for entry in log],
        'timingsSeconds': {' '.join(entry['command']): entry['seconds'] for entry in log},
        'commands': log,
        **(extra or {}),
    }
    (OUT / f'{part}-verdict.json').write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f'{part}: passed, {len(data["inputsSHA256"])} inputs recorded')


def host():
    log = []
    run([sys.executable, 'tools/game_box/generate_strings.py', '--check'], log)
    for test in HOST_PYTHON:
        run([sys.executable, test], log)
    run(['flutter', 'analyze', '--no-fatal-infos', *ANALYZED], log)
    run(['flutter', 'test', *DART_TESTS], log)
    verdict('host', PRODUCT + SUPPORT + HOST_PYTHON + DART_TESTS, log)


def flutter_framework():
    roots = [os.environ.get('FLUTTER_ROOT', '')]
    which = shutil.which('flutter')
    if which:
        roots.append(str(Path(which).resolve().parents[1]))
    for root in roots:
        if not root:
            continue
        for candidate in sorted(Path(root, 'bin/cache/artifacts/engine').glob('ios*/Flutter.xcframework/ios-arm64')):
            if (candidate / 'Flutter.framework').exists():
                return candidate
    raise SystemExit('Flutter.xcframework (ios-arm64) not found: run flutter precache --ios')


def simulator_udid():
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True))
    for runtime, entries in sorted(devices['devices'].items(), reverse=True):
        if 'iOS' not in runtime:
            continue
        for d in entries:
            if d.get('isAvailable') and d['name'].startswith('iPhone'):
                return d['udid'], runtime, d['name']
    raise SystemExit('No available iPhone simulator')


def native():
    log = []
    OUT.mkdir(parents=True, exist_ok=True)
    reports = {}

    # macOS: Vision, NaturalLanguage and Translation of the runner's macOS.
    mac_bin = OUT / 'recognizer-macos'
    run(['xcrun', 'swiftc', '-O', '-swift-version', '5', '-target', f'{platform.machine()}-apple-macos14.0',
         RECOGNIZER, NATIVE_MAIN, '-o', str(mac_bin)], log)
    env = dict(os.environ, GAMEBOX_REQUIRE_TRANSLATION='1')
    result = run([str(mac_bin)], log, env=env, check=False)
    (OUT / 'recognizer-macos.json').write_text(result.stdout)
    reports['macos'] = json.loads(result.stdout)
    if result.returncode != 0:
        raise SystemExit('macOS recognition checks failed: ' + '; '.join(reports['macos'].get('failures', [])))

    # iOS Simulator: the same code against the iOS frameworks.
    sim_bin = OUT / 'recognizer-ios-sim'
    run(['xcrun', '--sdk', 'iphonesimulator', 'swiftc', '-O', '-swift-version', '5',
         '-target', 'arm64-apple-ios18.0-simulator', RECOGNIZER, NATIVE_MAIN, '-o', str(sim_bin)], log)
    udid, runtime, name = simulator_udid()
    run(['xcrun', 'simctl', 'boot', udid], log, check=False)
    run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], log)
    result = run(['xcrun', 'simctl', 'spawn', udid, str(sim_bin)], log, check=False)
    (OUT / 'recognizer-ios-simulator.json').write_text(result.stdout)
    reports['iosSimulator'] = {'runtime': runtime, 'device': name, **json.loads(result.stdout)}
    if result.returncode != 0:
        raise SystemExit('iOS Simulator recognition checks failed: ' + '; '.join(reports['iosSimulator'].get('failures', [])))

    # iPhone SDK: the plugin's Swift sources with Flutter.
    run(['flutter', 'precache', '--ios'], log)
    framework = flutter_framework()
    sources = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'packages/neo_box_reader/ios/Classes').glob('*.swift'))
    run(['xcrun', '--sdk', 'iphoneos', 'swiftc', '-typecheck', '-swift-version', '5',
         '-target', 'arm64-apple-ios18.0', '-F', str(framework), '-module-name', 'neo_box_reader', *sources], log)
    xcode = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], text=True).strip()
    verdict('native', PRODUCT + SUPPORT + [NATIVE_MAIN], log, {'reports': reports, 'xcode': xcode, 'iphoneSDK': sdk})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--part', choices=['host', 'native'], required=True)
    args = parser.parse_args()
    {'host': host, 'native': native}[args.part]()


if __name__ == '__main__':
    main()
