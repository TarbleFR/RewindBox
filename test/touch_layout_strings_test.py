#!/usr/bin/env python3
"""Build 484: texts of the touch-controls editor and of the in-game menu rows.

The canonical catalogue (tools/touch_layout/strings.json) has the same keys in
the twelve NeoStation locales, no placeholder, and both generated catalogues
(native NeoTouchLayoutStrings.m, Flutter touch_layout_locale.dart) are exactly
what the generator writes. Every key the native code asks for exists.
"""
from pathlib import Path
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ['en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'id', 'ja', 'ko', 'zh', 'zh_Hant']
NATIVE_SOURCES = [
    'packages/neo_touch_layout/ios/Classes/NeoTouchLayoutEditor.m',
    'packages/dolphin_internal_bridge/ios/Classes/DOLTouchLayout.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinSessionMenu.mm',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinTouchOverlay.swift',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2TouchControls.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3TouchControls.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3SessionMenu.mm',
    'lib/widgets/embedded_touch_controls_panel.dart',
]


def main():
    subprocess.run([sys.executable, str(ROOT / 'tools/touch_layout/generate_strings.py'), '--check'], check=True)
    data = json.loads((ROOT / 'tools/touch_layout/strings.json').read_text(encoding='utf-8'))
    assert data['locales'] == LOCALES, data['locales']
    keys = set(data['values']['en'])
    for locale in LOCALES:
        assert set(data['values'][locale]) == keys, locale
        for key, text in data['values'][locale].items():
            assert text.strip() and '%' not in text and '{' not in text, (locale, key)
    # zh_Hant really is Traditional Chinese (not a copy of zh).
    differing = [k for k in keys if data['values']['zh'][k] != data['values']['zh_Hant'][k]]
    assert len(differing) >= len(keys) // 2, 'zh_Hant looks like a copy of zh'
    native = (ROOT / 'packages/neo_touch_layout/ios/Classes/NeoTouchLayoutStrings.m').read_text(encoding='utf-8')
    for locale in LOCALES:
        assert f'@"{locale}": @{{' in native, locale
    used = set()
    patterns = [
        r'NeoTouchLayoutText\(@"(\w+)"',
        r'touchText:@"(\w+)"',
        r'\[self text:@"(\w+)"\]',
        r'labels\[@"touch\.(\w+)"\]',
        r'return "@(\w+)"',
        r"_t\('(\w+)'\)",
        r'textKey:@"(\w+)"',
    ]
    for relative in NATIVE_SOURCES:
        text = (ROOT / relative).read_text(encoding='utf-8')
        for pattern in patterns:
            for key in re.findall(pattern, text):
                if relative.endswith('NeoTouchLayoutEditor.m') or pattern != r'\[self text:@"(\w+)"\]':
                    used.add((relative, key))
    # Engine menus have their own catalogues for `[self text:]`; only the
    # editor's `text:` and the explicit touch accessors use this catalogue.
    missing = sorted((path, key) for path, key in used if key not in keys)
    assert not missing, missing
    print(f'PASS touch layout texts: {len(keys)} keys x {len(LOCALES)} locales, {len(used)} uses checked')


if __name__ == '__main__':
    main()
