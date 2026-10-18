"""Test only the new UI evidence composition guard; never rerun old suites."""
import unittest
import game_close_delivery as gate


class ReturnEvidence(unittest.TestCase):
    def record(self):
        return dict(result='passed', source=gate.UI_REF,
                    baseline='9429a1627a2f72dddc07a5fe3c4cda35cdbd7db9',
                    baselineReproductions=6, correctedReturnCases=6, desktopCases=1,
                    embeddedExecutables=['ios_' + x + '_internal' for x in
                                         ('libretro', 'dolphin', 'armsx2', 'rpcs3', 'dusklight', 'kartpad')],
                    cleanupBeforeNativeEnd=False, physicalDeviceValidated=False,
                    locales={'app_locale_' + x: dict(launchingGame='start', gameExecuting='run', closingGame='close')
                             for x in ('en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'ja', 'ko', 'zh', 'zh_hant', 'id')})

    def test_exact_ui_witness_and_closed_product_scope(self):
        record = self.record()
        self.assertEqual(gate.validate_ui_verdict(record), record)
        gate.validate_changed_paths([*gate.UI_INPUTS, *gate.DELIVERY_ONLY])
        for path in ('lib/services/game_launch_manager.dart', 'lib/main.dart',
                     'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
                     'native/nestopia/reset-background.patch'):
            with self.assertRaises(ValueError):
                gate.validate_changed_paths([path])

    def test_reject_wrong_source_incomplete_cases_premature_cleanup_and_missing_translation(self):
        for key, value in [('source', 'wrong'), ('correctedReturnCases', 5),
                           ('baselineReproductions', 0), ('desktopCases', 0),
                           ('embeddedExecutables', []), ('cleanupBeforeNativeEnd', True),
                           ('physicalDeviceValidated', True), ('locales', {})]:
            record = self.record()
            record[key] = value
            with self.assertRaises(ValueError):
                gate.validate_ui_verdict(record)
        record = self.record()
        record['locales']['app_locale_fr']['closingGame'] = ''
        with self.assertRaises(ValueError):
            gate.validate_ui_verdict(record)


if __name__ == '__main__':
    unittest.main()
