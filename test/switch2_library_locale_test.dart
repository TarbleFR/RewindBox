import 'dart:ui' show Locale;

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/s2arm_engine_locale.dart';
import 'package:neostation/l10n/switch2_library_locale.dart';
import 'package:neostation/services/s2arm_internal_service.dart';

void main() {
  test('every key exists in the 12 locales and is non-empty', () {
    final english = Switch2LibraryLocale.values['en']!;
    expect(Switch2LibraryLocale.values.keys, hasLength(12));
    for (final entry in Switch2LibraryLocale.values.entries) {
      expect(entry.value.keys.toSet(), english.keys.toSet(), reason: entry.key);
      for (final value in entry.value.values) {
        expect(value.trim(), isNotEmpty, reason: entry.key);
      }
    }
  });

  test('placeholders are kept in every locale', () {
    for (final entry in Switch2LibraryLocale.values.entries) {
      expect(entry.value['importing'], contains('{name}'), reason: entry.key);
      expect(entry.value['preparing'], contains('{name}'), reason: entry.key);
      expect(entry.value['imported'], contains('{count}'), reason: entry.key);
      expect(entry.value['duplicates'], contains('{count}'), reason: entry.key);
    }
  });

  test('locale resolution and formatting', () {
    expect(Switch2LibraryLocale.codeFor(const Locale('xx')), 'en');
    expect(Switch2LibraryLocale.codeFor(const Locale('zh', 'TW')), 'zh_Hant');
    expect(Switch2LibraryLocale.codeFor(const Locale('zh', 'CN')), 'zh');
    expect(Switch2LibraryLocale.format(const Locale('en'), 'importing', {'name': 'Game'}), 'Importing Game…');
  });

  test('every engine state the Consoles row and launch can report has a message', () {
    for (final key in ['engineMissing', 'systemDataMissing', 'jitHelperMissing', 'unsupportedPlatform', 'unknown', 'busy']) {
      final text = S2ArmInternalService.localizedError(const Locale('en'), key);
      expect(text, isNotEmpty, reason: key);
    }
    expect(S2ArmInternalService.localizedError(const Locale('en'), 'engineMissing'),
        S2ArmEngineLocale.text(const Locale('en'), 'engineChainMissing'));
  });
}
