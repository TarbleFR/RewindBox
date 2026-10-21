"""RewindBox branding without changing the existing app identity."""
from pathlib import Path
import re
import unittest
ROOT = Path(__file__).resolve().parents[1]
def text(name): return (ROOT/name).read_text(encoding='utf-8')
class RewindBoxBranding(unittest.TestCase):
    def test_flutter_display_name(self):
        source = text('lib/main.dart')
        self.assertIn("title: 'RewindBox'", source)
        self.assertNotIn("title: 'NeoStation'", source)
    def test_ios_display_name_and_stable_identifier(self):
        source = text('packages/dolphin_internal_bridge/ci/build_support.py')
        self.assertIn("info['CFBundleDisplayName'] = 'RewindBox'", source)
        self.assertIn("info['CFBundleName'] = 'RewindBox'", source)
        self.assertIn('com.neogamelab.neostation', source)
        self.assertTrue(text('pubspec.yaml').startswith('name: neostation'))
    def test_fork_updates_do_not_target_upstream(self):
        source = text('lib/services/update_service.dart')
        self.assertIn('api.github.com/repos/TarbleFR/RewindBox/releases/latest', source)
        self.assertNotIn('api.github.com/repos/misobadev/', source)
    def test_twelve_locale_titles_and_upstream_credit(self):
        source = text('lib/l10n/fork_credit_locale.dart')
        titles = source.split('_titles = {',1)[1].split('};',1)[0]
        self.assertEqual(len(re.findall(r"'[a-zA-Z_]+': 'RewindBox'", titles)),12)
        self.assertIn('NeoStation', source.split('_descriptions = {',1)[1])
        self.assertIn('misobadev/neostation-frontend', text('README.md'))
        self.assertTrue((ROOT/'assets/legal/NeoStation-GPL-3.0.txt').exists())
    def test_upstream_wordmark_is_not_rendered(self):
        for name in ('lib/main.dart','lib/widgets/shimmering_logo.dart','lib/widgets/setup_wizard.dart','lib/screens/systems_screen/fork_first_run_onboarding.dart','lib/screens/secondary_screen/secondary_screen.dart'):
            self.assertNotIn('assets/images/logo_transparent.png', text(name))
            self.assertIn('RewindBoxWordmark(', text(name))
    def test_website_keeps_stable_bundle_id(self):
        source = text('web-installer/api/manifest.js')
        self.assertIn("'RewindBox'", source)
        self.assertIn('com.neogamelab.neostation', source)
if __name__ == '__main__': unittest.main(verbosity=2)
