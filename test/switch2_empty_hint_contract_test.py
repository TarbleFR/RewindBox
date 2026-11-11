#!/usr/bin/env python3
"""The empty Switch 2 playlist says how to import, through SwitchPlaylistEmptyState's `hint` (plain python3).

    python3 -B test/switch2_empty_hint_contract_test.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ('en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko')
failures = []

source = (ROOT / 'lib/screens/game_screen/my_games_list.dart').read_text(encoding='utf-8')
start = source.index('Widget _buildEmptyState()')
call = source[start:source.index('final isRpcs3Library', start)]
if not re.search(r"_isS2ArmLibrary\s*\?\s*Switch2LibraryLocale\.text\(context, 'emptyHint'\)", call):
    failures.append('the Switch 2 empty state does not pass Switch2LibraryLocale emptyHint as its hint')
if "XeniaLocale.text(context, 'emptyBody')" not in call or not re.search(r':\s*null,\s*\)', call):
    failures.append('the Xbox 360 hint or the Switch default (null) changed')
if "import 'package:neostation/l10n/switch2_library_locale.dart';" not in source:
    failures.append('my_games_list.dart does not import Switch2LibraryLocale')

locale = (ROOT / 'lib/l10n/switch2_library_locale.dart').read_text(encoding='utf-8')
for code in LOCALES:
    block = re.search(r"\n    '%s': <String, String>\{\n(.*?)\n    \}," % re.escape(code), locale, re.S)
    entry = block and re.search(r"'emptyHint': \"([^\"]+)\"", block.group(1))
    if not entry:
        failures.append(f'{code}: no emptyHint')
    elif 'prod.keys' not in entry.group(1) or 'MeloNX' not in entry.group(1):
        failures.append(f'{code}: emptyHint must name prod.keys and MeloNX (shared keys)')

for failure in failures:
    print('FAIL ' + failure)
print('ok' if not failures else f'{len(failures)} failure(s)')
sys.exit(1 if failures else 0)
