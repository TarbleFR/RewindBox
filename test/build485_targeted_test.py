#!/usr/bin/env python3
"""Targeted Build 485 checks: HD texture packs of the embedded ARMSX2 engine, host side.

Runs what Build 485 changes outside the ARMSX2 Core workflow: analysis of the
changed Dart files, the game-settings panel and ARMSX2 Dart tests, the Dart
tests sharing the emulator tab and the bridge, the twelve-locale coverage and
the generated catalogues, the pack readers and installer on real fixtures
(normal and AddressSanitizer/UBSan builds), the portable ARMSX2 contracts and
the library baseline guards. The verdict records the SHA-256 of every tested
input so the delivery closure can prove it reuses exactly this run. The Core,
its adapter test, the Foundation store test and the UIKit menu run in
armsx2-core.yml. Nothing here renders a game or claims an iPhone result.
"""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/build485'
PRODUCT = [
    'build-utils/armsx2/neostation-core.patch',
    'build-utils/armsx2/source.json',
    'build-utils/armsx2/upstream-files.json',
    'lib/l10n/armsx2_texture_locale.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_emulator_tab.dart',
    'lib/services/armsx2_texture_service.dart',
    'lib/widgets/armsx2_texture_panel.dart',
    'packages/armsx2_internal_bridge/core/ARMSX2Core.mm',
    'packages/armsx2_internal_bridge/core/ARMSX2TextureReplacements.inc',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePackCore.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePackStore.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePackStore.mm',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePage.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TexturePage.mm',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TextureStrings.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2TextureStrings.m',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.h',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2TextureBridge.h',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2TextureBridge.mm',
    'packages/armsx2_internal_bridge/ios/Classes/upstream/TexturePackPaths.h',
    'packages/armsx2_internal_bridge/ios/Classes/upstream/TexturePackTar.h',
    'packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec',
    'packages/armsx2_internal_bridge/lib/armsx2_internal_bridge.dart',
    'tools/armsx2_textures/generate_strings.py',
    'tools/armsx2_textures/strings.json',
]
TESTS = [
    'test/armsx2_texture_panel_test.dart',
    'test/armsx2_embedded_library_contract_test.dart',
    'test/armsx2_in_game_localization_test.dart',
    'test/armsx2_bios_selection_test.dart',
    'test/armsx2_isolated_root_test.dart',
    'test/armsx2_retroarch_routing_isolation_test.dart',
    'test/libretro_engine_settings_test.dart',
    'test/rpcs3_embedded_identity_test.dart',
    'test/localization_12_locale_coverage_test.py',
    'test/armsx2_texture_packs_test.py',
    'test/armsx2_texture_pack_core_test.cpp',
    'test/armsx2_bios_hacks_test.py',
    'test/armsx2_graphics_test.py',
    'test/game_audio_handoff_test.py',
    'test/retroarch_baseline_scope_test.py',
    'test/libretro_frontend_ui_contract_test.py',
    # Reads the bridge podspec (the Core framework is never linked at start).
    'test/armsx2_external_display_test.py',
    # Executed on macOS by armsx2-core.yml; hashed here so both runs name the same files.
    'test/armsx2_texture_native_test.py',
    'test/armsx2_texture_store_test.mm',
    'test/armsx2_texture_core_adapter_test.mm',
    'test/armsx2_graphics_ui_test.py',
    'test/build485_targeted_test.py',
    '.github/workflows/build485-checks.yml',
    '.github/workflows/armsx2-core.yml',
]
DART_TESTS = [t for t in TESTS if t.endswith('_test.dart')]
ANALYZED = [p for p in PRODUCT if p.endswith('.dart')] + DART_TESTS
PYTHON_CHECKS = [
    'test/localization_12_locale_coverage_test.py',
    'test/armsx2_bios_hacks_test.py',
    'test/armsx2_graphics_test.py',
    'test/game_audio_handoff_test.py',
    'test/retroarch_baseline_scope_test.py',
    'test/libretro_frontend_ui_contract_test.py',
    'test/armsx2_external_display_test.py',
]


def run(args, env=None):
    print('+', ' '.join(args), flush=True)
    started = time.monotonic()
    # UTF-8 sources on every host, including a cp1252 Windows console.
    subprocess.run(args, cwd=ROOT, check=True, env={**os.environ, 'PYTHONUTF8': '1', **(env or {})})
    return round(time.monotonic() - started, 3)


def main():
    flutter = shutil.which('flutter') or 'flutter'
    python = sys.executable
    timings = {}
    timings['analyze'] = run([flutter, 'analyze', '--no-fatal-infos', *ANALYZED])
    timings['dartTests'] = run([flutter, 'test', *DART_TESTS])
    timings['generatedStrings'] = run([python, 'tools/armsx2_textures/generate_strings.py', '--check'])
    # Real ZIP/TAR/folder/ISO fixtures through the production reader and installer.
    timings['packFiles'] = run([python, 'test/armsx2_texture_packs_test.py'])
    # Same suite under AddressSanitizer and UndefinedBehaviorSanitizer.
    timings['packFilesSanitized'] = run([python, 'test/armsx2_texture_packs_test.py'],
                                        env={'ARMSX2_TEXTURE_SANITIZE': '1', 'CXX': 'g++'})
    for check in PYTHON_CHECKS:
        timings[Path(check).stem] = run([python, check])
    inputs = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PRODUCT + TESTS}
    OUT.mkdir(parents=True, exist_ok=True)
    verdict = {
        'result': 'passed',
        'build': 485,
        'source': os.environ.get('GITHUB_SHA', subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()),
        'host': platform.platform(),
        'flutter': subprocess.check_output([flutter, '--version', '--machine'], cwd=ROOT, text=True).strip(),
        'dartTests': DART_TESTS,
        'pythonChecks': ['tools/armsx2_textures/generate_strings.py --check', 'test/armsx2_texture_packs_test.py',
                         'test/armsx2_texture_packs_test.py (ASan/UBSan)', *PYTHON_CHECKS],
        'timingsSeconds': timings,
        'inputsSHA256': inputs,
        'coreRebuilt': False,
        'deviceValidated': False,
        'notes': [
            'The ARMSX2 Core (ABI 8), its adapter test, the Foundation store test and the UIKit menu run in armsx2-core.yml.',
            'Host and Simulator results are not physical iPhone validation; no game was rendered.',
        ],
    }
    (OUT / 'verdict.json').write_text(json.dumps(verdict, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'inputs': len(inputs), 'timingsSeconds': timings}, indent=2))


if __name__ == '__main__':
    main()
