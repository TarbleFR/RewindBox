"""Cross-language integration contracts; no claim of running Apple models."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'packages/achievement_translation/ios/Classes/Core'

class AchievementTranslationContracts(unittest.TestCase):
    def test_native_consumers_match_translation_deployment_floor(self):
        for name in ('achievement_translation', 'armsx2_internal_bridge',
                     'dolphin_internal_bridge', 'libretro_internal_bridge'):
            spec = (ROOT / f'packages/{name}/ios/{name}.podspec').read_text()
            self.assertIn("s.platform = :ios, '18.0'", spec, name)
            self.assertIn("s.ios.deployment_target = '18.0'", spec, name)
            if name != 'achievement_translation':
                self.assertIn("s.dependency 'achievement_translation'", spec, name)

    def test_real_locales_and_bcp47_mapping(self):
        locale = (ROOT / 'lib/l10n/app_locale.dart').read_text()
        block = locale.split('supportedLanguages = {', 1)[1].split('};', 1)[0]
        codes = set(re.findall(r"'([^']+)'\s*:", block))
        self.assertEqual(len(codes), 12)
        swift = (CORE / 'AchievementModels.swift').read_text().split('identifiers:', 1)[1].split(']', 2)[-1] if False else (CORE / 'AchievementModels.swift').read_text()
        mapping = dict(re.findall(r'"([a-z_]+|zh_Hant)": "([A-Za-z-]+)"', swift))
        self.assertEqual(set(mapping), codes)
        for code in codes:
            name = 'zh_hant' if code == 'zh_Hant' else code
            self.assertTrue((ROOT / f'lib/l10n/app_locale_{name}.dart').is_file())
            self.assertRegex(mapping[code], r'^[a-z]{2}(?:-[A-Za-z]{2,4})*$')
        self.assertNotEqual(mapping['zh'], mapping['zh_Hant'])
        notices = (ROOT / 'lib/l10n/achievement_translation_locale.dart').read_text()
        self.assertEqual(set(re.findall(r"^    '([^']+)': \[", notices, re.M)), codes)

    def test_existing_language_authority_and_startup(self):
        main = (ROOT / 'lib/main.dart').read_text()
        self.assertEqual(main.count('await AchievementTranslationClient.shared.setLanguage(initLang.isNotEmpty'), 2)
        mutator = (ROOT / 'lib/providers/sqlite_config_provider/mutators.dart').read_text()
        language = mutator.split('Future<void> updateAppLanguage', 1)[1].split('\n  }', 1)[0]
        self.assertIn('SqliteConfigService.saveConfig(_config)', language)
        self.assertIn('FlutterLocalization.instance.translate(langCode)', language)
        self.assertIn('AchievementTranslationClient.shared.setLanguage(langCode)', language)
        for path in CORE.glob('*.swift'):
            self.assertNotIn('Locale.current', path.read_text(), str(path))
            self.assertNotIn('preferredLanguages', path.read_text(), str(path))

    def test_all_identified_flutter_sites_use_adapter(self):
        sites = {
            'lib/screens/game_screen/game_details_card/tabs/game_details_achievements_tab.dart': 2,
            'lib/screens/retro_achievements_screen/ra_dashboard.dart': 3,
            'lib/screens/secondary_screen/widgets/achievement_panel.dart': 2,
            'lib/screens/secondary_screen/widgets/achievement_comments.dart': 2,
        }
        for name, expected in sites.items():
            self.assertEqual((ROOT / name).read_text().count('TranslatedAchievementText('), expected, name)
        dashboard = (ROOT / 'lib/screens/retro_achievements_screen/ra_dashboard.dart').read_text()
        self.assertIn('gotw.game.title', dashboard)
        self.assertIn('${item.gameTitle}', dashboard)

    def test_native_unlock_is_committed_before_presentation(self):
        code = (ROOT / 'packages/libretro_internal_bridge/ios/Classes/LibretroAchievements.m').read_text()
        event = code.split('static void EventHandler(', 1)[1].split('static void GameLoaded', 1)[0]
        self.assertLess(event.index('[achievements refreshSummary]'), event.index('achievements.unlocked('))
        self.assertIn('event->achievement->id', event)
        self.assertIn('event->achievement->description', event)
        self.assertNotIn('RBAchievementResolve', event)
        self.assertNotIn('dispatch_sync', event)
        session = (ROOT / 'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m').read_text()
        self.assertIn('active->_controller != owner', session)
        self.assertIn('RBAchievementPresent(', session)

    def test_external_engine_reuses_only_display_plugin(self):
        registry = (ROOT / 'packages/external_display/ios/Classes/NeoExternalDisplayMenuEngine.m').read_text()
        block = registry.split('kNeoExternalMenuPlugins[] = {', 1)[1].split('};', 1)[0]
        self.assertEqual(re.findall(r'@"([^"]+)"', block), [
            'shared_preferences_foundation.SharedPreferencesPlugin',
            'achievement_translation.AchievementTranslationPlugin'])
        entry = (ROOT / 'lib/external_display/external_display_entrypoint.dart').read_text()
        self.assertIn('followAppLanguage(menuArgs.languageCode)', entry)
        self.assertNotIn('AchievementTranslationClient.shared.setLanguage', entry)

if __name__ == '__main__':
    unittest.main(verbosity=2)
