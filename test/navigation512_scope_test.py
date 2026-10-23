"""Only the requested Switch playlist and main header presentation may change."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '2ed9a18ca6b22a00675dcbbe3a44985e26ed04d5'
PRODUCT = {
    'lib/screens/game_screen/my_games_list.dart',
    'lib/widgets/header.dart', 'lib/widgets/header_sort_dropdown.dart',
    'lib/widgets/header_layout.dart',
    'lib/widgets/melonx_internal_playlist_actions.dart',
    'lib/widgets/switch_playlist_empty_state.dart',
}
AUXILIARY = {
    '.github/workflows/navigation512-checks.yml', '.github/workflows/retroarch-delivery.yml',
    '.github/diagnostics/navigation512_delivery.py',
    'test/navigation512_scope_test.py', 'test/navigation512_switch_test.dart',
    'test/menu_carousel_correction_test.dart',
    'build-utils/delivery-512-chatgpt-recipient.pem',
    'build-utils/validate_navigation512_ipa.py',
    'docs/navigation-build512.md', 'docs/evidence/navigation512-delivery.json',
}

def delta(*paths):
    return set(subprocess.check_output(['git', 'diff', '--name-only', BASELINE, '--', *paths],
        cwd=ROOT, text=True).splitlines())

def check():
    changed = delta()
    untracked = set(subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines())
    assert not (changed | untracked) - PRODUCT - AUXILIARY, sorted((changed | untracked) - PRODUCT - AUXILIARY)
    product = delta('lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock')
    assert product | (untracked & PRODUCT) == PRODUCT, sorted(product)
    # Input owners, animation tracks, startup, storage, all engines and settings
    # retain the identities already verified in the delivered 511 artifact.
    assert not delta('assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock',
        'lib/services', 'lib/repositories', 'lib/data', 'lib/main.dart',
        'lib/utils', 'lib/screens/app_screen.dart', 'lib/widgets/main_menu_tab_strip.dart',
        'lib/widgets/native_carousel.dart', 'lib/widgets/liquid_motion_clock.dart')
    header = (ROOT / 'lib/widgets/header.dart').read_text()
    assert '_buildShoulderButton' not in header and 'BumperGlyph' not in header
    print('PASS exact Switch/header interface scope; native engines, data, controls and motion inputs preserved.')

if __name__ == '__main__':
    check()
