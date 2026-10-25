"""The maintainer's menu/carousel correction changes presentation only."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '8a79ae4e7855cde46e2922e8f71a2df81f0c7a7b'
PRODUCT = {
    'assets/data/mau-ali-tab-motion.json', 'assets/legal/Mau-Ali-Tab-Motion.txt',
    'assets/legal/THIRD_PARTY_NOTICES.md',
    'lib/widgets/header.dart', 'lib/widgets/fixed_header.dart', 'lib/widgets/header_layout.dart',
    'lib/widgets/main_menu_tab_strip.dart', 'lib/widgets/mau_ali_tab_motion.dart',
    'lib/widgets/mau_ali_tab_motion_data.dart', 'lib/widgets/native_carousel.dart',
    'lib/screens/app_screen.dart',
    'lib/screens/systems_screen/my_systems_section/my_systems_carousel.dart',
    'lib/screens/systems_screen/my_systems_section/system_card.dart',
}
AUXILIARY = {
    '.github/workflows/ui-correction511-checks.yml', '.github/workflows/retroarch-delivery.yml',
    '.github/diagnostics/uicorrection511_delivery.py',
    'build-utils/extract_mau_ali_motion.py', 'build-utils/validate_ui_correction511_ipa.py',
    'build-utils/delivery-511-chatgpt-recipient.pem',
    'test/ui_correction_scope_test.py', 'test/menu_carousel_correction_test.dart',
    'test/ui_correction_visual_test.dart', 'test/liquid_motion_test.dart',
    'docs/LEGAL_AND_CREDITS.md', 'docs/ui-correction-build511.md',
    'docs/evidence/ui-correction511-delivery.json',
}


def changed(*paths):
    return set(subprocess.check_output(['git', 'diff', '--name-only', BASELINE, '--', *paths], cwd=ROOT, text=True).splitlines())


def check():
    delta = changed()
    assert not delta - PRODUCT - AUXILIARY, sorted(delta - PRODUCT - AUXILIARY)
    assert changed('lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock') == PRODUCT
    assert not changed('lib/services', 'lib/repositories', 'lib/main.dart', 'lib/utils/nav_tabs.dart',
        'lib/widgets/rewind_startup.dart', 'lib/widgets/liquid_progress.dart',
        'lib/widgets/liquid_battery.dart', 'lib/widgets/liquid_motion_clock.dart',
        'build-utils/sign_delivery.py', 'build-utils/delivery_benchmark.py')
    print('PASS exact presentation-only correction; Build 509 engines, storage, Switch/RPCS3 fixes and startup preserved.')


if __name__ == '__main__':
    check()
