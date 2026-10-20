#!/usr/bin/env python3
"""Targeted checks of Build 493: delivered Build 492 + the 3D boxes in the three
library views, the halo kept on the List view's selected title only, the
viewer's Back button and flat back view, and the manual inside the open box.

Part:
  host    Ubuntu: the twelve-language catalogue of the box texts, analysis of
          the whole app, the delivery Dart suite of retroarch-delivery.yml
          (read from the workflow itself, so both stay identical), the game box
          suites (geometry, booklet, media, reader text, viewer, manual in the
          box, grid and list), every existing Dart suite that reads a changed
          file, and the Python contracts of the box texts, the twelve locales,
          the locked Build 419 library files and the media sources.

No native input changes in this build (the neo_box_reader plugin, the
engines, their bridges and the Cores are the delivered Build 492 ones), so
there is no native part. Before running anything the part checks that its
declared inputs cover every non-documentation path changed since Build 492,
so a change outside these lists fails instead of being delivered untested.
It writes build/build493/host-verdict.json with the SHA-256 of every input
it tested. Nothing here claims an iPhone result.
"""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/build493'
BUILD = 493
# Build 492 source (Dusklight and Ports removal, another session); updated to the
# delivered 492 commit once its delivery run is recorded.
BASE = 'b1ca2a97bd212594d9602929b725742c42891787'
DELIVERY = '.github/workflows/retroarch-delivery.yml'
DART_SUITE_STEP = 'Validate changed library, callback, launch and restart behavior'

# Product files of Build 493.
PRODUCT = sorted({
    'lib/l10n/game_box_locale.dart',
    'lib/screens/game_box/box_back_reader_screen.dart',
    'lib/screens/game_box/game_box_inspector.dart',
    'lib/screens/game_box/game_box_scan_viewer.dart',
    'lib/screens/game_screen/game_details_card/game_details_card_list.dart',
    'lib/screens/game_screen/game_details_card/tabs/game_details_box2d_tab.dart',
    'lib/screens/game_screen/game_list_view.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_manual_tab.dart',
    'lib/screens/game_screen/my_games_carousel.dart',
    'lib/screens/game_screen/my_games_grid.dart',
    'lib/screens/game_screen/my_games_list.dart',
    'lib/screens/game_screen/my_games_list/gamepad_nav.dart',
    'lib/services/game_box/game_box_manual.dart',
    'lib/services/game_manual_service.dart',
    'lib/widgets/game_box/game_box_art_loader.dart',
    'lib/widgets/game_box/game_box_card.dart',
    'lib/widgets/game_box/game_box_geometry.dart',
    'lib/widgets/game_box/game_box_library.dart',
    'lib/widgets/game_box/game_box_scene.dart',
    'lib/widgets/game_box/game_box_surfaces.dart',
    'tools/game_box/generate_strings.py',
    'tools/game_box/strings.json',
})

SUPPORT = ['test/build493_targeted_test.py', '.github/workflows/build493-checks.yml', DELIVERY]

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
    # Build 493.
    'test/game_box_booklet_test.dart',
    'test/game_box_manual_inspector_test.dart',
    'test/game_box_library_views_test.dart',
    'test/game_box_render_open_preview_test.dart',
    # The game box suites of Build 490 (two changed: labels of the faces).
    'test/game_box_geometry_test.dart',
    'test/game_box_media_test.dart',
    'test/game_box_text_test.dart',
    'test/game_box_inspector_test.dart',
    'test/game_box_locale_test.dart',
    'test/game_box_render_preview_test.dart',
    'test/game_box_render_inspector_preview_test.dart',
    # Existing suites that read a changed file.
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
# Records, documentation and delivery wiring: no product or tested input.
NOT_TESTED = {'AGENTS.md', 'README.md', '.github/diagnostics/gamebox493_delivery.py',
              'build-utils/delivery-493-recipient.pem'}


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


def changed_since_492():
    subprocess.run(['git', 'cat-file', '-e', BASE + '^{commit}'], cwd=ROOT, check=True)
    paths = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--'], cwd=ROOT, text=True).split()
    paths += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).split()
    return {p for p in paths if (ROOT / p).is_file() and not p.startswith('docs/') and p not in NOT_TESTED}


def coverage():
    """Every changed file since Build 492 is an input of the host part."""
    declared = set(HOST_INPUTS)
    missing = {p for p in changed_since_492() if p not in declared
               and not (p.startswith('.github/workflows/') and p != '.github/workflows/build493-checks.yml')}
    if missing:
        raise SystemExit('Changed since Build 492 but not tested here: ' + ', '.join(sorted(missing)))
    for path in HOST_INPUTS:
        if not (ROOT / path).is_file():
            raise SystemExit('Declared input missing: ' + path)
    # No native input of this build: the delivered Build 492 ones.
    native = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--', 'packages', 'native', 'ios',
                                      'build-utils/libretro'], cwd=ROOT, text=True).split()
    if native:
        raise SystemExit('Native input changed since Build 492: ' + ', '.join(native))


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


def verdict(part, inputs, log):
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
    run(['flutter', 'test', *EXTRA_DART_TESTS], log)
    for test in HOST_PYTHON:
        run([sys.executable, test], log)
    verdict('host', HOST_INPUTS, log)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--part', choices=['host', 'coverage'], required=True)
    args = parser.parse_args()
    if args.part == 'coverage':
        coverage()
        print('coverage: every changed file since Build 492 is a declared input')
        return
    host()


if __name__ == '__main__':
    main()
