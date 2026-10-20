#!/usr/bin/env python3
"""Targeted checks of Build 494: delivered Build 493 + the legibility of the
box backs (docs/build494-plan.md, docs/game-box-3d.md § 12).

Parts:
  host    Ubuntu: the twelve-language catalogue of the box texts, analysis of
          the whole app, the delivery Dart suite of retroarch-delivery.yml
          (read from the workflow itself, so both stay identical), the new
          suites (exact resampling and sharpening of the back, its use by the
          viewer and the flat view, the room left to the box in portrait), the
          game box suites, every existing Dart suite that reads a changed file,
          and the Python contracts of the box texts, the twelve locales, the
          locked Build 419 library files and the media sources;
  native  macOS: the recognizer of the box reader plugin with Apple's Vision
          on macOS and in the iOS Simulator: the twelve-language check of
          Build 490, then back-cover-like scans with small print read by the
          recognizer of Build 493 (control) and by the new one; the plugin's
          Swift sources against the iPhone SDK and Flutter.

The only native input of this build is the plugin's recognizer. Before
running anything the host part checks that the inputs of the two parts cover
every non-documentation path changed since Build 493, so a change outside
these lists fails instead of being delivered untested. Each part writes
build/build494/<part>-verdict.json with the SHA-256 of every input it tested.
Nothing here claims an iPhone result: the Simulator runs Vision on the host.
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
OUT = ROOT / 'build/build494'
BUILD = 494
# Delivered Build 493 source (3D boxes in the three views, run 39359025363).
BASE = '013d32ed0238922dcabe57aca407a6e4b49c82f5'
DELIVERY = '.github/workflows/retroarch-delivery.yml'
DART_SUITE_STEP = 'Validate changed library, callback, launch and restart behavior'

RECOGNIZER = 'packages/neo_box_reader/ios/Classes/BoxTextRecognizer.swift'
LANGUAGES_MAIN = 'packages/neo_box_reader/ci/main.swift'
SMALL_PRINT_MAIN = 'test/native/game_box_small_print/main.swift'

# Product files of Build 494.
PRODUCT = sorted({
    'lib/l10n/game_box_locale.dart',
    'lib/screens/game_box/game_box_inspector.dart',
    'lib/screens/game_box/game_box_scan_viewer.dart',
    'lib/services/game_box/box_text_service.dart',
    'lib/services/game_box/game_box_preferences.dart',
    'lib/services/game_box/game_box_sharp_scan.dart',
    'lib/widgets/game_box/game_box_scene.dart',
    RECOGNIZER,
    'tools/game_box/strings.json',
})
NATIVE_PRODUCT = [RECOGNIZER]
PLUGIN_SOURCES = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'packages/neo_box_reader/ios/Classes').glob('*.swift'))

SUPPORT = ['test/build494_targeted_test.py', '.github/workflows/build494-checks.yml', DELIVERY]

HOST_PYTHON = [
    'test/game_box_strings_test.py',
    'test/localization_12_locale_coverage_test.py',
    'test/retroarch_baseline_scope_test.py',
    'test/cheats_media_source_contract_test.py',
    'test/integrated_import_tab_contract_test.py',
    'test/libretro_route_contract_test.py',
]

# New, changed or affected Dart tests outside the delivery suite.
EXTRA_DART_TESTS = [
    # Build 494.
    'test/game_box_sharp_scan_test.dart',
    'test/game_box_sharp_back_test.dart',
    'test/game_box_text_test.dart',
    # The game box suites of Builds 490 and 493.
    'test/game_box_booklet_test.dart',
    'test/game_box_manual_inspector_test.dart',
    'test/game_box_library_views_test.dart',
    'test/game_box_render_open_preview_test.dart',
    'test/game_box_geometry_test.dart',
    'test/game_box_media_test.dart',
    'test/game_box_inspector_test.dart',
    'test/game_box_locale_test.dart',
    'test/game_box_render_preview_test.dart',
    'test/game_box_render_inspector_preview_test.dart',
    # Existing suites that read a changed file (the viewer through the views).
    'test/game_list_view_tap_test.dart',
    'test/rainbow_selection_fairy_test.dart',
    'test/ios_selective_rollback_test.dart',
    'test/armsx2_embedded_library_contract_test.dart',
    'test/rpcs3_regular_arena_dolphin_multidelete_contract_test.dart',
    'test/screenscraper_manual_media_test.dart',
    'test/external_display_games_list_test.dart',
    'test/grid_preview_audio_contract_test.dart',
    'test/rpcs3_lazy_load_contract_test.dart',
    'test/video_preview_lifecycle_test.dart',
    'test/audio_policy_service_test.dart',
]

HOST_INPUTS = PRODUCT + SUPPORT + HOST_PYTHON + EXTRA_DART_TESTS
NATIVE_INPUTS = sorted(set(NATIVE_PRODUCT + PLUGIN_SOURCES + [LANGUAGES_MAIN, SMALL_PRINT_MAIN]
                           + ['test/build494_targeted_test.py', '.github/workflows/build494-checks.yml']))
# Records, documentation and delivery wiring: no product or tested input.
NOT_TESTED = {'AGENTS.md', 'README.md', '.github/diagnostics/gamebox494_delivery.py',
              'build-utils/delivery-494-recipient.pem'}
# Changed since Build 493 by the HD-texture session (Mesen HD pack research,
# 487f1d80..44067e20): catalogue research tools and that cycle's own checks,
# neither packaged in the IPA nor run by its delivery, nor tested here. Listed
# path by path: any other change fails the coverage and the delivery gate.
OTHER_SESSION = {'tools/textures/discover.py', 'tools/textures/probe_cores.py', 'test/build486_targeted_test.py'}

# Small print read by the recognizer: the similarity each block must reach
# with the Build 494 recognizer (macOS and the iOS Simulator). The legal
# print of the low-resolution scan (6.6 px) is only reported.
SMALL_PRINT_GATES = {
    2.0: {'title': 0.85, 'body': 0.85, 'features': 0.85, 'panel': 0.85, 'legal': 0.85},
    1.0: {'title': 0.85, 'body': 0.85, 'features': 0.85, 'panel': 0.85, 'legal': 0.85},
    0.6: {'title': 0.85, 'body': 0.85, 'features': 0.80, 'panel': 0.75},
}
# No block may read worse than with the recognizer of Build 493.
NO_REGRESSION = 0.03


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def run(cmd, log, cwd=ROOT, check=True, shell=False, env=None):
    started = time.time()
    shown = cmd if shell else ' '.join(cmd)
    print('$', shown, flush=True)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=shell, env=env)
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


def changed_since_493():
    subprocess.run(['git', 'cat-file', '-e', BASE + '^{commit}'], cwd=ROOT, check=True)
    paths = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--'], cwd=ROOT, text=True).split()
    paths += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).split()
    return {p for p in paths if (ROOT / p).is_file() and not p.startswith('docs/') and p not in NOT_TESTED
            and p not in OTHER_SESSION}


def coverage():
    """Every changed file since Build 493 is an input of the host or native part."""
    declared = set(HOST_INPUTS) | set(NATIVE_INPUTS)
    missing = {p for p in changed_since_493() if p not in declared
               and not (p.startswith('.github/workflows/') and p != '.github/workflows/build494-checks.yml')}
    if missing:
        raise SystemExit('Changed since Build 493 but not tested here: ' + ', '.join(sorted(missing)))
    for path in set(HOST_INPUTS) | set(NATIVE_INPUTS):
        if not (ROOT / path).is_file():
            raise SystemExit('Declared input missing: ' + path)
    # The plugin's recognizer is the only native input of this build.
    native = set(subprocess.check_output(['git', 'diff', '--name-only', BASE, '--', 'packages', 'native', 'ios',
                                          'build-utils/libretro'], cwd=ROOT, text=True).split())
    if native != set(NATIVE_PRODUCT):
        raise SystemExit('Native inputs changed since Build 493: ' + ', '.join(sorted(native ^ set(NATIVE_PRODUCT))))


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
    run([sys.executable, 'tools/game_box/generate_strings.py', '--check'], log)
    run(['flutter', 'pub', 'get', '--enforce-lockfile'], log)
    run(['flutter', 'analyze'], log)
    for command in delivery_dart_suite():
        run(command, log, shell=True)
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GAME_BOX_SHARP_REPORT=str(OUT / 'small-print-rendering.txt'))
    run(['flutter', 'test', *EXTRA_DART_TESTS], log, env=env)
    for test in HOST_PYTHON:
        run([sys.executable, test], log)
    rendering = OUT / 'small-print-rendering.txt'
    verdict('host', HOST_INPUTS, log,
            {'smallPrintRendering': rendering.read_text() if rendering.is_file() else None})


# Native -------------------------------------------------------------------------


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


def build_and_run(name, recognizer, main, log, udid, env=None):
    """The recognizer with [main], on macOS and in the iOS Simulator: two JSON reports."""
    reports = {}
    mac = OUT / f'{name}-macos'
    run(['xcrun', 'swiftc', '-O', '-swift-version', '5', '-target', f'{platform.machine()}-apple-macos14.0',
         str(recognizer), main, '-o', str(mac)], log)
    result = run([str(mac)], log, check=False, env=env)
    (OUT / f'{name}-macos.json').write_text(result.stdout)
    reports['macos'] = {'returncode': result.returncode, **json.loads(result.stdout)}
    sim = OUT / f'{name}-ios-sim'
    run(['xcrun', '--sdk', 'iphonesimulator', 'swiftc', '-O', '-swift-version', '5',
         '-target', 'arm64-apple-ios18.0-simulator', str(recognizer), main, '-o', str(sim)], log)
    result = run(['xcrun', 'simctl', 'spawn', udid, str(sim)], log, check=False)
    (OUT / f'{name}-ios-simulator.json').write_text(result.stdout)
    reports['iosSimulator'] = {'returncode': result.returncode, **json.loads(result.stdout)}
    return reports


def small_print_table(report):
    return {(r['language'], r['scale'], r['block']): r for r in report['results'] if r['block'] != '_image'}


def compare_small_print(old, new):
    failures, rows = [], []
    for platform_name in ('macos', 'iosSimulator'):
        if new[platform_name]['returncode'] != 0 or new[platform_name].get('errors'):
            failures.append(f'{platform_name}: {new[platform_name].get("errors")}')
            continue
        before, after = small_print_table(old[platform_name]), small_print_table(new[platform_name])
        for key, r in sorted(after.items()):
            language, scale, block = key
            was = before.get(key, {}).get('similarity', 0.0)
            now = r['similarity']
            gate = SMALL_PRINT_GATES.get(scale, {}).get(block)
            rows.append({'platform': platform_name, 'language': language, 'scale': scale, 'block': block,
                         'fontPixels': r['fontPixels'], 'build493': round(was, 3), 'build494': round(now, 3),
                         'gate': gate, 'text493': before.get(key, {}).get('recognized', ''),
                         'text494': r['recognized']})
            if gate is not None and now < gate:
                failures.append(f'{platform_name} {language} ×{scale} {block}: {now:.3f} < {gate}')
            if now < was - NO_REGRESSION:
                failures.append(f'{platform_name} {language} ×{scale} {block}: {now:.3f} below Build 493 ({was:.3f})')
    return failures, rows


def native():
    log = []
    OUT.mkdir(parents=True, exist_ok=True)
    udid, runtime, device = simulator_udid()
    run(['xcrun', 'simctl', 'boot', udid], log, check=False)
    run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], log)

    # The twelve-language check of Build 490, with the new recognizer.
    languages = build_and_run('languages-494', ROOT / RECOGNIZER, LANGUAGES_MAIN, log, udid,
                              env=dict(os.environ, GAMEBOX_REQUIRE_TRANSLATION='1'))
    for name, report in languages.items():
        if report['returncode'] != 0:
            raise SystemExit(f'{name} twelve-language recognition failed: ' + '; '.join(report.get('failures', [])))

    # Small print: the recognizer of Build 493 (control) and the new one.
    old_recognizer = OUT / 'build493/BoxTextRecognizer.swift'
    old_recognizer.parent.mkdir(parents=True, exist_ok=True)
    old_recognizer.write_text(subprocess.check_output(['git', 'show', f'{BASE}:{RECOGNIZER}'], cwd=ROOT, text=True))
    old = build_and_run('small-print-493', old_recognizer, SMALL_PRINT_MAIN, log, udid)
    new = build_and_run('small-print-494', ROOT / RECOGNIZER, SMALL_PRINT_MAIN, log, udid)
    failures, rows = compare_small_print(old, new)
    (OUT / 'small-print-comparison.json').write_text(json.dumps({'rows': rows, 'failures': failures}, indent=1,
                                                                 ensure_ascii=False))
    for row in rows:
        print(f"{row['platform']:12} {row['language']} ×{row['scale']:<3} {row['block']:9} "
              f"{row['fontPixels']:5.1f} px  493 {row['build493']:.3f}  494 {row['build494']:.3f}")
        # The reports are cut in the log: the texts read differently are shown here.
        if row['text493'] != row['text494']:
            print(f"    493: {row['text493']!r}\n    494: {row['text494']!r}")
    if failures:
        raise SystemExit('Small print checks failed: ' + '; '.join(failures))

    # iPhone SDK: the plugin's Swift sources with Flutter.
    run(['flutter', 'precache', '--ios'], log)
    framework = flutter_framework()
    run(['xcrun', '--sdk', 'iphoneos', 'swiftc', '-typecheck', '-swift-version', '5',
         '-target', 'arm64-apple-ios18.0', '-F', str(framework), '-module-name', 'neo_box_reader', *PLUGIN_SOURCES], log)
    xcode = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], text=True).strip()
    verdict('native', NATIVE_INPUTS, log, {
        'xcode': xcode, 'iphoneSDK': sdk, 'simulator': {'runtime': runtime, 'device': device},
        'languages': {k: {'os': v.get('os'), 'failures': v.get('failures')} for k, v in languages.items()},
        'smallPrint': rows,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--part', choices=['host', 'native', 'coverage'], required=True)
    args = parser.parse_args()
    if args.part == 'coverage':
        coverage()
        print('coverage: every changed file since Build 493 is a declared input')
        return
    {'host': host, 'native': native}[args.part]()


if __name__ == '__main__':
    main()
