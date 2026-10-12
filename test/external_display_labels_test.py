#!/usr/bin/env python3
"""Parity of the native external-display labels in the twelve supported
languages (packages/external_display/ios/Classes/NeoExternalDisplayLabels.h).

Every language carries the same key set, no value is empty, no non-English
language falls back to the English text, the maintainer's French wording is
kept, and the lookup selects Traditional Chinese for zh-Hant / TW / HK / MO.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / 'packages/external_display/ios/Classes/NeoExternalDisplayLabels.h'
LANGUAGES = ['en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko']
KEYS = {'externalOnPhone', 'modeAutomatic', 'modeFit', 'modeFill', 'modeOriginal', 'modeOff'}
FRENCH = {
    'externalOnPhone': "Jeu affiché sur l'écran externe",
    'modeAutomatic': 'Automatique',
    'modeFit': "Adapter à l'écran",
    'modeFill': "Remplir l'écran",
    'modeOriginal': "Format d'origine",
}


def parse_labels(text: str) -> dict[str, dict[str, str]]:
    labels: dict[str, dict[str, str]] = {}
    for language, block in re.findall(r'@"(\w+)": @\{(.*?)\},\n', text, flags=re.S):
        pairs = re.findall(r'@"(\w+)": @"((?:\\.|[^"\\])*)"', block)
        labels[language] = {key: value for key, value in pairs}
    return labels


class LabelParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = HEADER.read_text(encoding='utf-8')
        self.labels = parse_labels(self.text)

    def test_twelve_languages_with_the_same_keys(self) -> None:
        self.assertEqual(sorted(self.labels), sorted(LANGUAGES))
        for language in LANGUAGES:
            self.assertEqual(set(self.labels[language]), KEYS, language)
            for key, value in self.labels[language].items():
                self.assertTrue(value.strip(), f'{language}.{key} is empty')

    def test_no_english_fallback_in_other_languages(self) -> None:
        english = self.labels['en']
        for language in LANGUAGES:
            if language == 'en':
                continue
            for key in KEYS:
                self.assertNotEqual(self.labels[language][key], english[key], f'{language}.{key} is the English text')

    def test_traditional_chinese_differs_from_simplified(self) -> None:
        self.assertNotEqual(self.labels['zh']['externalOnPhone'], self.labels['zh_Hant']['externalOnPhone'])
        self.assertNotEqual(self.labels['zh']['modeFit'], self.labels['zh_Hant']['modeFit'])

    def test_french_wording_of_the_maintainer(self) -> None:
        for key, value in FRENCH.items():
            self.assertEqual(self.labels['fr'][key], value, key)

    def test_header_is_published_by_the_pod(self) -> None:
        """The libretro bridge imports it as <external_display/NeoExternalDisplayLabels.h>
        for its in-game status line: with use_frameworks! only a public header
        of the pod resolves under that prefix in the cold Xcode build."""
        podspec = (ROOT / 'packages/external_display/ios/external_display.podspec').read_text(encoding='utf-8')
        public = podspec.split('s.public_header_files', 1)[1].split('s.dependency', 1)[0]
        self.assertIn("'Classes/NeoExternalDisplayLabels.h'", public)
        libretro = (ROOT / 'packages/libretro_internal_bridge/ios/Classes/LibretroGameViewController.m').read_text(encoding='utf-8')
        self.assertIn('#import <external_display/NeoExternalDisplayLabels.h>', libretro)
        self.assertIn('NeoExternalDisplayText(@"externalOnPhone"', libretro)

    def test_lookup_normalizes_locales_and_falls_back_to_english_then_key(self) -> None:
        lookup = self.text.split('dispatch_once(&once', 1)[1]
        self.assertIn('stringByReplacingOccurrencesOfString:@"-" withString:@"_"', lookup)
        for token in ('containsString:@"hant"', 'hasSuffix:@"_tw"', 'hasSuffix:@"_hk"', 'hasSuffix:@"_mo"'):
            self.assertIn(token, lookup, token)
        self.assertIn('language = @"zh_Hant";', lookup)
        self.assertIn('return labels[language][key] ?: labels[@"en"][key] ?: key;', lookup)
        # One static function: safe to include from several bridges.
        self.assertIn('static NSString *NeoExternalDisplayText(NSString *key, NSString *locale)', self.text)
        self.assertNotIn('<UIKit/', self.text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
