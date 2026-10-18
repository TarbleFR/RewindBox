#!/usr/bin/env python3
"""Targeted Build 484 checks: touch-controls editor and controller policy.

Build 484 changes the touch controls of the embedded Dolphin (GameCube, Wii),
ARMSX2 (PS2) and RPCS3 (PS3) engines, their in-game menus and plugins, adds
the shared neo_touch_layout pod and the Emulators-tab panel. This runner
executes the new checks and every existing check that reads a changed file
(found by name across test/), split in three parts:

  host    Ubuntu: texts, portable geometry and pad merge, engine contracts,
          Flutter analysis and widget tests;
  native  macOS: iPhone SDK compilation and link of every changed source, the
          existing UIKit suites that compile the changed menus and Swift
          touch controls;
  uikit   macOS: test/touch_layout_ui_test.py (editor, five layouts,
          orientations, multitouch, controller policy, persistence across
          processes) in the iOS Simulator.

Each part writes build/build484/<part>-verdict.json with the SHA-256 of every
input it tested, so the delivery closure can prove it reuses exactly these
runs. Nothing here rebuilds an emulator core or claims an iPhone result.
Checks that already fail on the unchanged base (stale history scopes and
host-toolchain differences) are listed in PRE_EXISTING: the host part runs
each of them on the commit before Build 484 and here, and refuses a check
that passed before and fails now.
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
OUT = ROOT / 'build/build484'

PRODUCT = sorted({
    'lib/l10n/dolphin_import_locale.dart',
    'lib/l10n/touch_layout_locale.dart',
    'lib/widgets/embedded_touch_controls_panel.dart',
    'lib/widgets/system_emulator_settings_dialog.dart',
    'lib/widgets/system_emulator_settings_dialog/tabs.dart',
    'pubspec.yaml',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2TouchControls.h',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2TouchControls.mm',
    'packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec',
    'packages/dolphin_internal_bridge/ios/Classes/DOLTouchLayout.h',
    'packages/dolphin_internal_bridge/ios/Classes/DOLTouchLayout.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinSessionMenu.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinSessionMenu.mm',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinTouchOverlay.swift',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/TCDirectionalPad.swift',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/TCJoystick.swift',
    'packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3GameInputController.h',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3GameInputController.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3PadMerge.h',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3TouchControls.h',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3TouchControls.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3SessionMenu.h',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3SessionMenu.mm',
    'packages/rpcs3_internal_bridge/ios/rpcs3_internal_bridge.podspec',
} | {str(path.relative_to(ROOT)) for path in (ROOT / 'packages/neo_touch_layout').rglob('*') if path.is_file()}
  | {str(path.relative_to(ROOT)) for path in (ROOT / 'tools/touch_layout').rglob('*') if path.is_file()})

HOST_PYTHON = [
    'test/touch_layout_strings_test.py',
    'test/touch_layout_host_test.py',
    'test/rpcs3_input_bridge_test.py',
    'test/localization_12_locale_coverage_test.py',
    'test/armsx2_external_display_test.py',
    'test/dolphin_shake_wiring_test.py',
    'test/dolphin_cheat_manager_test.py',
    'test/dolphin_account_267_test.py',
    'test/dolphin_cheats_menu_test.py',
    'test/dolphin_core_linkage_test.py',
    'test/neoplay_companion_contract_test.py',
    'test/storage_contract_test.py',
    'test/rpcs3_savestate_overwrite_regression_test.py',
    'test/rpcs3_pod_header_visibility_test.py',
    'test/rpcs3_early_escrow_integration_test.py',
    'test/rpcs3_build306_single_path_test.py',
    'test/rpcs3_build285_core_handoff_test.py',
    'test/rpcs3_build283_boot_stability_test.py',
    'test/neoswap_donor_contract_test.py',
    'test/neoswap_comparison_test.py',
    'test/neoswap_bridge_syntax_stub_test.py',
    'test/neoswap_shader_storage_host_test.py',
    'test/libretro_frontend_ui_contract_test.py',
    'test/cheats_media_source_contract_test.py',
]
ANALYZED = [
    'lib/widgets/embedded_touch_controls_panel.dart',
    'lib/l10n/touch_layout_locale.dart',
    'lib/l10n/dolphin_import_locale.dart',
    'lib/widgets/system_emulator_settings_dialog.dart',
    'packages/neo_touch_layout/lib/neo_touch_layout.dart',
    'test/embedded_touch_controls_panel_test.dart',
]
DART_TESTS = [
    'test/embedded_touch_controls_panel_test.dart',
    'test/dolphin_wii_motion_panel_test.dart',
    'test/dolphin_shake_locale_test.dart',
    'test/armsx2_embedded_library_contract_test.dart',
    'test/armsx2_in_game_localization_test.dart',
    'test/rpcs3_internal_integration_test.dart',
    'test/rpcs3_lazy_load_contract_test.dart',
    'test/rpcs3_embedded_identity_test.dart',
    'test/rpcs3_stage3_test.dart',
    'test/rpcs3_stage7_test.dart',
    'test/rpcs3_silent_mode_policy_test.dart',
    'test/rpcs3_bridge_memory_mode_test.dart',
    'test/libretro_engine_settings_test.dart',
    'test/nav_tabs_test.dart',
    'test/main_menu_tab_strip_test.dart',
    'test/gamepad_settings_scrolling_test.dart',
]
NATIVE = [
    ['test/touch_layout_ios_build.py'],
    ['test/unified_native_ios_test.py'],
    ['test/rpcs3_loader_stability_280_test.py'],
    ['test/dolphin_jit_relaunch_test.py'],
    ['test/dolphin_recording_sdk_test.py'],
    ['test/dolphin_external_display_test.py'],
    ['test/armsx2_graphics_ui_test.py'],
    ['test/dolphin_touch_shake_ui_test.py'],
    ['test/dolphin_pacing362_ui_test.py'],
    ['test/dolphin_external_display_ui_test.py'],
    ['test/dolphin_shader_store_test.py'],
    ['test/cheat_editor361_ui_test.py'],
]
UIKIT = [['test/touch_layout_ui_test.py']]
SUPPORT = [
    'test/touch_layout_support.py', 'test/touch_layout_ui/TouchLayoutTests.mm',
    'test/touch_layout_ui/TouchLayoutTestSupport.mm', 'test/touch_layout_ui/main.m',
    'test/native/touch_layout_geometry_test.c', 'test/native/rpcs3_pad_merge_test.cpp',
    'test/libretro_ios_syntax_test.py', 'test/build484_targeted_test.py',
    '.github/workflows/touch-layout-checks.yml',
]
# Failed on the unchanged base in the development container (history scopes
# pinned to commits whose files moved, host compiler differences); compared
# with the base on the CI host by compare_with_base.
PRE_EXISTING = [
    'test/import_memory_candidate_scope_test.py', 'test/neoplay_build397_integration_test.py',
    'test/rpcs3_external_display_test.py', 'test/dolphin_pacing362_contract_test.py',
    'test/dolphin_achievements_hacks_menu_test.py', 'test/cheat_bulk_scope_test.py',
    'test/rpcs3_performance_telemetry_patch_test.py', 'test/rpcs3_performance_snapshot_test.py',
    'test/neoswap_swap_research_test.py', 'test/neoswap_source_archive_host_test.py',
    'test/external_display_host_plist_test.py', 'test/delivery_pipeline_test.py', 'test/check_neo_swap_scope.py',
]
# Two layout cases of this Flutter suite fail on the unchanged base under the
# Linux test fonts; compared case by case with the base.
PRE_EXISTING_DART = ['test/dolphin_import_ui_test.dart']


def execute(args, log, cwd=ROOT):
    """Runs a check, logging its output; returns (exit code, seconds, output)."""
    print('+', ' '.join(args), f'[{cwd}]' if cwd != ROOT else '', flush=True)
    started = time.monotonic()
    env = {**os.environ, 'PYTHONUTF8': '1'}
    lines = []
    with log.open('a', encoding='utf-8') as handle:
        handle.write('\n+ ' + ' '.join(args) + f' [{cwd}]\n')
        handle.flush()
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, errors='replace')
        for line in process.stdout:
            handle.write(line)
            lines.append(line)
        code = process.wait()
    return code, round(time.monotonic() - started, 3), lines


def run(args, log):
    code, elapsed, lines = execute(args, log)
    if code:
        sys.stdout.write(''.join(lines[-60:]))
        raise SystemExit(f'FAILED ({code}): {" ".join(args)}')
    print(f'  ok in {elapsed}s: {lines[-1].strip() if lines else ""}', flush=True)
    return elapsed


def error_lines(lines, root):
    """Error and failure lines of a check's output, with its tree root and
    temporary paths removed, to compare a failure here with one on the base."""
    import re
    keep = re.compile(r'(error:|FAIL:|AssertionError|Error:|\*\* TEST FAILED|Test Case .* failed|fatal)')
    found = set()
    for line in lines:
        if not keep.search(line):
            continue
        line = line.replace(str(root), '<root>')
        line = re.sub(r'/(private/)?(var/folders|tmp)/[^ :]*', '<tmp>', line)
        line = re.sub(r'DerivedData/[^/ ]+', 'DerivedData/<project>', line)
        line = re.sub(r'\b\d+(\.\d+)? ?(s|seconds)\b', '<t>', line)
        found.add(line.strip())
    return found


def base_tree():
    first = subprocess.check_output(['git', 'log', '--diff-filter=A', '--format=%H', '--',
                                     'packages/neo_touch_layout/pubspec.yaml'], cwd=ROOT, text=True).split()[-1]
    base = subprocess.check_output(['git', 'rev-parse', first + '^'], cwd=ROOT, text=True).strip()
    tree = OUT / 'base-tree'
    if tree.exists():
        subprocess.run(['git', 'worktree', 'remove', '--force', str(tree)], cwd=ROOT, check=False)
    subprocess.run(['git', 'worktree', 'add', '--detach', str(tree), base], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    return base, tree


def run_or_compare(args, log, comparisons):
    """A failing check is run on the commit before Build 484: it is accepted
    as pre-existing only if it fails there too with every error line seen
    here; a new error line, or a pass on the base, is a regression."""
    code, elapsed, lines = execute(args, log)
    if not code:
        print(f'  ok in {elapsed}s: {lines[-1].strip() if lines else ""}', flush=True)
        return elapsed
    sys.stdout.write(''.join(lines[-40:]))
    if 'tree' not in comparisons:
        comparisons['base'], comparisons['tree'] = base_tree()
    tree = comparisons['tree']
    base_code, _, base_lines = execute(args, log, cwd=tree)
    head_errors, base_errors = error_lines(lines, ROOT), error_lines(base_lines, tree)
    new = sorted(head_errors - base_errors)
    comparisons.setdefault('checks', {})[' '.join(args[1:])] = {
        'head': code, 'base': base_code, 'errorLines': sorted(head_errors), 'newErrorLines': new}
    if base_code == 0 or new:
        raise SystemExit(f'Regression: {" ".join(args[1:])} (base exit {base_code}); new errors: {new}')
    print(f'  pre-existing failure (identical on the base {comparisons["base"][:8]}): {" ".join(args[1:])}',
          flush=True)
    return elapsed


def compare_with_base(log):
    """Runs each PRE_EXISTING check on the commit before Build 484 and here:
    a check that passes there must pass here (no regression hidden among
    known failures)."""
    base, tree = base_tree()
    results = {}
    try:
        for test in PRE_EXISTING:
            codes = []
            for where in (tree, ROOT):
                completed = subprocess.run([sys.executable, test], cwd=where, capture_output=True, text=True,
                                           errors='replace', env={**os.environ, 'PYTHONUTF8': '1'}, timeout=900)
                with log.open('a', encoding='utf-8') as handle:
                    handle.write(f'\n+ [{"base" if where == tree else "head"}] {test} -> {completed.returncode}\n')
                    handle.write(completed.stdout[-4000:] + completed.stderr[-4000:])
                codes.append(completed.returncode)
            results[test] = {'base': codes[0], 'head': codes[1]}
            print(f'  {test}: base {codes[0]}, head {codes[1]}', flush=True)
            if codes[0] == 0 and codes[1] != 0:
                raise SystemExit(f'Regression: {test} passes before Build 484 and fails here')
        flutter = shutil.which('flutter') or 'flutter'
        subprocess.run([flutter, 'pub', 'get', '--enforce-lockfile'], cwd=tree, check=True,
                       stdout=subprocess.DEVNULL)
        for test in PRE_EXISTING_DART:
            failing = []
            for where in (tree, ROOT):
                completed = subprocess.run([flutter, 'test', '--machine', test], cwd=where, capture_output=True,
                                           text=True, errors='replace', timeout=1800)
                names, failed = {}, set()
                for line in completed.stdout.splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get('type') == 'testStart':
                        names[event['test']['id']] = event['test']['name']
                    elif event.get('type') == 'testDone' and event.get('result') != 'success' \
                            and not event.get('hidden'):
                        failed.add(names.get(event['testID'], str(event['testID'])))
                if completed.returncode and not failed:
                    failed.add('<suite failed to load>')
                failing.append(sorted(failed))
            results[test] = {'baseFailing': failing[0], 'headFailing': failing[1]}
            print(f'  {test}: base failing {failing[0]}, head failing {failing[1]}', flush=True)
            new_failures = set(failing[1]) - set(failing[0])
            if new_failures:
                raise SystemExit(f'Regression in {test}: ' + ', '.join(sorted(new_failures)))
    finally:
        subprocess.run(['git', 'worktree', 'remove', '--force', str(tree)], cwd=ROOT, check=False)
    return base, results


def digest(paths):
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(set(paths))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--part', required=True, choices=['host', 'native', 'uikit'])
    part = parser.parse_args().part
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / f'{part}.log'
    log.write_text('')
    python = sys.executable
    timings, checks = {}, []
    if part == 'host':
        flutter = shutil.which('flutter') or 'flutter'
        for test in HOST_PYTHON:
            timings[test] = run([python, test], log)
            checks.append(test)
        timings['analyze'] = run([flutter, 'analyze', '--no-fatal-infos', *ANALYZED], log)
        timings['dartTests'] = run([flutter, 'test', *DART_TESTS], log)
        checks += DART_TESTS
        tested = HOST_PYTHON + DART_TESTS + PRE_EXISTING + PRE_EXISTING_DART
        comparison_base, comparison = compare_with_base(log)
    else:
        if platform.system() != 'Darwin':
            raise SystemExit(f'The {part} part runs on macOS with Xcode.')
        comparisons = {}
        try:
            for command in NATIVE if part == 'native' else UIKIT:
                timings[' '.join(command)] = (run_or_compare([python, *command], log, comparisons)
                                              if part == 'native' else run([python, *command], log))
                checks.append(' '.join(command))
        finally:
            if 'tree' in comparisons:
                subprocess.run(['git', 'worktree', 'remove', '--force', str(comparisons.pop('tree'))], cwd=ROOT,
                               check=False)
        tested = [command[0] for command in (NATIVE if part == 'native' else UIKIT)]
    inputs = digest(PRODUCT + SUPPORT + tested)
    verdict = {
        'result': 'passed',
        'build': 484,
        'part': part,
        'source': os.environ.get('GITHUB_SHA') or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                                                          text=True).strip(),
        'host': platform.platform(),
        'checks': checks,
        'timingsSeconds': timings,
        'inputsSHA256': inputs,
        'coreRebuilt': False,
        'deviceValidated': False,
        'notes': ['Compilation, host and Simulator results are not physical iPhone validation.'],
    }
    if part == 'host':
        verdict['preExistingComparison'] = {'base': comparison_base, 'exitCodes': comparison}
    if part == 'native':
        verdict['preExistingComparison'] = comparisons
    if part != 'host':
        verdict['xcode'] = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
        verdict['iphoneSDK'] = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'],
                                                       text=True).strip()
    summary = ROOT / 'build/touch-layout/summary.json'
    if part == 'uikit' and summary.exists():
        verdict['uikit'] = json.loads(summary.read_text())
    (OUT / f'{part}-verdict.json').write_text(json.dumps(verdict, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'part': part, 'checks': len(checks), 'inputs': len(inputs)}), flush=True)


if __name__ == '__main__':
    main()
