#!/usr/bin/env python3
"""The empty Switch 2 playlist says how to import, through SwitchPlaylistEmptyState's `hint`, and names nothing of
the Switch 1 engine (plain python3).

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
    elif any(word in entry.group(1) for word in ('prod.keys', 'MeloNX', 'Switch 1')):
        failures.append(f'{code}: emptyHint must not name prod.keys or the Switch 1 engine (S2Arm needs no keys)')
    if block and re.search(r"'(importKeys|importKeysHint|keysFailed)':", block.group(1)):
        failures.append(f'{code}: a prod.keys string is left in the Switch 2 library strings')

# The maintainer wants no ambiguity between the two engines: the Switch 2 library strings never name the Switch 1 one.
for word in ('MeloNX', 'prod.keys'):
    if word in locale:
        failures.append(f'switch2_library_locale.dart names {word}')

for failure in failures:
    print('FAIL ' + failure)
print('ok' if not failures else f'{len(failures)} failure(s)')
sys.exit(1 if failures else 0)
