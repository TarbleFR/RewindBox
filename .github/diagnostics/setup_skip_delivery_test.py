"""Only the new setup proof composition guard; do not rerun old suites."""
import hashlib
import unittest
import setup_skip_delivery as gate


class SetupEvidence(unittest.TestCase):
    def record(self):
        return dict(result='passed', source=gate.SETUP_REF, baseline=gate.BASE_REF,
                    wizardSHA256=hashlib.sha256((gate.ROOT / 'lib/widgets/setup_wizard.dart').read_bytes()).hexdigest(),
                    cases=gate.CASES.copy(), externalFolderChosen=False,
                    physicalDeviceValidated=False,
                    locales={x: x for x in ('en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'ja', 'ko', 'zh', 'zh_hant', 'id')})

    def test_exact_setup_witness_and_closed_product_scope(self):
        record = self.record()
        self.assertEqual(gate.validate_setup_verdict(record), record)
        gate.validate_changed_paths([*gate.SETUP_INPUTS, *gate.previous.UI_INPUTS, *gate.DELIVERY_ONLY])
        for path in ('lib/services/game_launch_manager.dart', 'lib/main.dart',
                     'lib/providers/sqlite_config_provider/scanning.dart',
                     'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m'):
            with self.assertRaises(ValueError):
                gate.validate_changed_paths([path])

    def test_reject_wrong_source_missing_cases_or_folder_side_effects(self):
        for key, value in [('source', 'wrong'), ('wizardSHA256', 'wrong'), ('cases', []),
                           ('externalFolderChosen', True), ('physicalDeviceValidated', True), ('locales', {})]:
            record = self.record()
            record[key] = value
            with self.assertRaises(ValueError):
                gate.validate_setup_verdict(record)
        record = self.record()
        record['locales']['zh_hant'] = record['locales']['zh']
        with self.assertRaises(ValueError):
            gate.validate_setup_verdict(record)


if __name__ == '__main__':
    unittest.main()
