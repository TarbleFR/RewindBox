#!/usr/bin/env python3
"""Targeted Build 486 checks: the unified HD texture catalogue.

Since the catalogue expansion of 19 October 2026 the same runner proves the
next candidate that changes the catalogue pod (Build 488: Nintendo 64 adapter
for Mupen64Plus-Next and the expanded index; Build 489: Beetle PSX HW in
Vulkan with its PS1 adapter, and manual packs whose author's file was
verified on CI); its verdicts carry BUILD.

Build 486 adds the neo_texture_catalog pod (catalogue, pack store, engine
adapters for ARMSX2, Dolphin, PPSSPP and Azahar, the shared "HD textures"
page), opens it from the PS2, GameCube/Wii and libretro in-game menus, the
console import menus and a game's settings, and ships the first catalogue
(native/textures/catalogue). This runner executes the new checks and every
existing check that reads a changed file (found by name across test/),
split in three parts:

  host    Ubuntu: archive readers, identities, installer, labels, catalogue
          build, engine and library contracts, Flutter analysis and tests;
  native  macOS: Foundation test of the store and adapters (with the Build 485
          ARMSX2 store), iPhone SDK compilation and link of the pod and of
          every changed bridge source, the existing suites compiling them;
  uikit   macOS: test/texture_catalog_ui_test.py (the page in the Simulator).

The packs themselves are verified against their authors' real files by
.github/workflows/hd-textures.yml (tools/textures/verify_packs.py) and
recorded in tools/textures/verified.jsonl.

Each part writes build/build486/<part>-verdict.json with the SHA-256 of every
input it tested. Nothing here rebuilds an emulator core or claims an iPhone
result. Checks that already fail on the unchanged base are listed in
PRE_EXISTING and compared with the commit before Build 486.
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
OUT = ROOT / 'build/build486'
# The candidate these verdicts prove (486: first catalogue; 488: N64 adapter and expanded index;
# 489: Beetle PSX HW in Vulkan, PS1 adapter, verified manual packs).
BUILD = 489

PRODUCT = sorted({
    'lib/l10n/texture_catalog_locale.dart',
    'lib/services/texture_catalog_service.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_manage_tab.dart',
    'lib/widgets/armsx2_internal_playlist_actions.dart',
    'lib/widgets/dolphin_internal_playlist_actions.dart',
    'lib/widgets/libretro_internal_playlist_actions.dart',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePackStore.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePackStore.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroVulkanRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroVulkanRenderer.m',
    'lib/services/libretro_core_catalog.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/services/libretro_resolution.dart',
    'pubspec.yaml',
    'native/textures/catalogue/manifest.json.gz',
} | set(subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard',
                                 'packages/neo_texture_catalog', 'tools/textures'], cwd=ROOT, text=True).split()))

HOST_PYTHON = [
    'test/texture_archive_test.py',
    'test/texture_identity_test.py',
    'test/texture_install_test.py',
    'test/texture_verify_checks_test.py',
    'test/texture_labels_test.py',
    'test/validate_hd_textures_ipa_test.py',
    'test/localization_12_locale_coverage_test.py',
    'test/armsx2_texture_packs_test.py',
    'test/libretro_external_surface_test.py',
    'test/cheats_media_source_contract_test.py',
    'test/dolphin_cheat_manager_test.py',
    'test/dolphin_cheats_menu_test.py',
    'test/dolphin_external_display_test.py',
    'test/dolphin_jit_relaunch_test.py',
    'test/dolphin_shake_wiring_test.py',
    'test/dolphin_registrant_test.py',
    'test/neoplay_companion_contract_test.py',
    'test/touch_layout_strings_test.py',
    'test/embedded_engine_route_contract_test.py',
    'test/integrated_import_tab_contract_test.py',
    'test/storage_contract_test.py',
    'test/libretro_frontend_ui_contract_test.py',
    'test/external_display_scope_test.py',
    'test/external_display_test.py',
    'test/kartpad_bridge_contract_test.py',
    'test/libretro_route_contract_test.py',
    'test/ui_refresh_rate_scope_test.py',
    'test/validate_cheat_bulk_ipa_test.py',
    'test/retroarch_baseline_scope_test.py',
    'test/game_audio_handoff_test.py',
    'test/game_close_status_test.py',
    'test/game_launch_route_test.py',
    'test/setup_skip_test.py',
    'test/carousel_chrome_layout_test.py',
]
# The catalogue: generated files current, every pack the app's own rules accept.
CATALOGUE = [['tools/textures/labels.py', '--check'], ['tools/textures/build_catalogue.py', '--check'],
             # Records of the packs verified on CI runners (repository archives) are those of the run's artifacts.
             ['tools/textures/check_ci_records.py']]
ANALYZED = [
    'lib/l10n/texture_catalog_locale.dart',
    'lib/services/texture_catalog_service.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_manage_tab.dart',
    'lib/widgets/armsx2_internal_playlist_actions.dart',
    'lib/widgets/dolphin_internal_playlist_actions.dart',
    'lib/widgets/libretro_internal_playlist_actions.dart',
    'packages/neo_texture_catalog/lib/neo_texture_catalog.dart',
    'lib/services/libretro_core_catalog.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/services/libretro_resolution.dart',
    'test/texture_catalog_service_test.dart',
    'test/libretro_core_catalog_test.dart',
    'test/libretro_resolution_test.dart',
    'test/libretro_beetle_vulkan_fallback_test.dart',
    'test/libretro_bios_launch_test.dart',
]
DART_TESTS = [
    'test/texture_catalog_service_test.dart',
    'test/libretro_playlist_actions_test.dart',
    'test/armsx2_embedded_library_contract_test.dart',
    'test/armsx2_in_game_localization_test.dart',
    'test/dolphin_smart_import_contract_test.dart',
    'test/dolphin_shake_locale_test.dart',
    'test/console_manager_test.dart',
    'test/rpcs3_preload_and_dolphin_delete_contract_test.dart',
    'test/rpcs3_regular_arena_dolphin_multidelete_contract_test.dart',
    'test/dusklight_ports_stage1_test.dart',
    'test/libretro_core_catalog_test.dart',
    'test/libretro_resolution_test.dart',
    'test/libretro_beetle_vulkan_fallback_test.dart',
    'test/libretro_bios_launch_test.dart',
]
NATIVE = [
    ['test/texture_catalog_native_test.py'],
    ['test/texture_catalog_ios_syntax_test.py'],
    ['test/armsx2_texture_native_test.py'],
    ['test/armsx2_graphics_ui_test.py'],
    ['test/libretro_ios_syntax_test.py'],
    ['test/touch_layout_ios_build.py'],
    ['test/unified_native_ios_test.py'],
]
UIKIT = [['test/texture_catalog_ui_test.py']]
SUPPORT = [
    'test/build486_targeted_test.py', '.github/workflows/hd-textures.yml',
    'test/native/texture_archive_driver.cpp', 'test/native/texture_identity_driver.cpp',
    'test/native/texture_install_driver.cpp', 'test/texture_7z_writer.py',
    'test/texture_catalog_store_test.mm', 'test/armsx2_texture_store_test.mm', 'test/armsx2_texture_core_adapter_test.mm',
    'test/armsx2_texture_pack_core_test.cpp', 'test/libretro_host/stubs/Flutter/Flutter.h',
    'test/touch_layout_support.py', 'test/libretro_ios_syntax_test.py', 'build-utils/validate_hd_textures_ipa.py',
]
# Fail on the unchanged base in the development container and read a changed
# file (pubspec.yaml, the Dolphin plugin): compared with the base on the CI host.
PRE_EXISTING = [
    'test/import_memory_candidate_scope_test.py', 'test/neoplay_build397_integration_test.py',
    'test/dolphin_pacing362_contract_test.py', 'test/dolphin_achievements_hacks_menu_test.py',
    'test/cheat_bulk_scope_test.py', 'test/external_display_host_plist_test.py', 'test/delivery_pipeline_test.py',
    'test/library_books_3d_contract_test.py', 'test/library_cover_delivery_test.py',
]


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
        sys.stdout.write(''.join(lines[-80:]))
        raise SystemExit(f'FAILED ({code}): {" ".join(args)}')
    print(f'  ok in {elapsed}s: {lines[-1].strip() if lines else ""}', flush=True)
    return elapsed


def error_lines(lines, root):
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
    """The commit before the one that added the pod (the delivered Build 485 record)."""
    added = subprocess.check_output(['git', 'log', '--diff-filter=A', '--format=%H', '--',
                                     'packages/neo_texture_catalog/pubspec.yaml'], cwd=ROOT, text=True).split()
    base = subprocess.check_output(['git', 'rev-parse', (added[-1] + '^') if added else 'HEAD'], cwd=ROOT, text=True).strip()
    tree = OUT / 'base-tree'
    if tree.exists():
        subprocess.run(['git', 'worktree', 'remove', '--force', str(tree)], cwd=ROOT, check=False)
    subprocess.run(['git', 'worktree', 'add', '--detach', str(tree), base], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    return base, tree


def run_or_compare(args, log, comparisons):
    """A failing native check is accepted as pre-existing only if it fails on the
    base too with every error line seen here."""
    code, elapsed, lines = execute(args, log)
    if not code:
        print(f'  ok in {elapsed}s: {lines[-1].strip() if lines else ""}', flush=True)
        return elapsed
    sys.stdout.write(''.join(lines[-60:]))
    script = args[1]
    if not (ROOT / script).exists() or script.startswith('test/texture_'):
        raise SystemExit(f'FAILED ({code}): {" ".join(args)}')
    if 'tree' not in comparisons:
        comparisons['base'], comparisons['tree'] = base_tree()
    tree = comparisons['tree']
    if not (tree / script).exists():
        raise SystemExit(f'FAILED ({code}): {" ".join(args)} (absent on the base)')
    base_code, _, base_lines = execute(args, log, cwd=tree)
    head_errors, base_errors = error_lines(lines, ROOT), error_lines(base_lines, tree)
    new = sorted(head_errors - base_errors)
    comparisons.setdefault('checks', {})[' '.join(args[1:])] = {
        'head': code, 'base': base_code, 'errorLines': sorted(head_errors), 'newErrorLines': new}
    if base_code == 0 or new:
        raise SystemExit(f'Regression: {" ".join(args[1:])} (base exit {base_code}); new errors: {new}')
    print(f'  pre-existing failure (identical on the base {comparisons["base"][:8]}): {" ".join(args[1:])}', flush=True)
    return elapsed


def compare_with_base(log):
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
                raise SystemExit(f'Regression: {test} passes before Build 486 and fails here')
    finally:
        subprocess.run(['git', 'worktree', 'remove', '--force', str(tree)], cwd=ROOT, check=False)
    return base, results


def digest(paths):
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(set(paths)) if (ROOT / path).is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--part', required=True, choices=['host', 'native', 'uikit'])
    part = parser.parse_args().part
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / f'{part}.log'
    log.write_text('')
    python = sys.executable
    timings, checks = {}, []
    comparison_base, comparison = None, {}
    if part == 'host':
        flutter = shutil.which('flutter') or 'flutter'
        for command in CATALOGUE:
            timings[' '.join(command)] = run([python, *command], log)
            checks.append(' '.join(command))
        for test in HOST_PYTHON:
            timings[test] = run([python, test], log)
            checks.append(test)
        timings['analyze'] = run([flutter, 'analyze', '--no-fatal-infos', *ANALYZED], log)
        timings['dartTests'] = run([flutter, 'test', *DART_TESTS], log)
        checks += DART_TESTS
        tested = HOST_PYTHON + DART_TESTS + PRE_EXISTING + [command[0] for command in CATALOGUE]
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
                subprocess.run(['git', 'worktree', 'remove', '--force', str(comparisons.pop('tree'))], cwd=ROOT, check=False)
        comparison = comparisons
        tested = [command[0] for command in (NATIVE if part == 'native' else UIKIT)]
    inputs = digest(PRODUCT + SUPPORT + tested)
    verdict = {
        'result': 'passed',
        'build': BUILD,
        'part': part,
        'source': os.environ.get('GITHUB_SHA') or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'host': platform.platform(),
        'checks': checks,
        'timingsSeconds': timings,
        'inputsSHA256': inputs,
        'coreRebuilt': False,
        'deviceValidated': False,
        'notes': ['Compilation, host and Simulator results are not physical iPhone validation; no texture was displayed by an engine.'],
    }
    if part == 'host':
        verdict['preExistingComparison'] = {'base': comparison_base, 'exitCodes': comparison}
    else:
        verdict['preExistingComparison'] = comparison
        verdict['xcode'] = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
        verdict['iphoneSDK'] = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], text=True).strip()
    (OUT / f'{part}-verdict.json').write_text(json.dumps(verdict, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'part': part, 'checks': len(checks), 'inputs': len(inputs)}), flush=True)


if __name__ == '__main__':
    main()
