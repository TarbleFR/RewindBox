import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter/material.dart' show MaterialLocalizations;

/// Dates shown by the reading Library, formatted for the Library's language.
///
/// `MaterialLocalizations.of(context)` cannot be used: lib/main.dart (locked
/// on Build 419) installs a fallback delegate that always loads English
/// before GlobalMaterialLocalizations, so every Material date would read
/// "Oct 9, 2026" inside translated sentences. This helper loads the Global
/// Material localizations of the Library language itself (the same 12
/// languages and the same zh_Hant rule as the Library catalogs) and caches
/// them. Until a language is loaded, dates use the unambiguous ISO form
/// (2026-10-09); [preload] at section start avoids that in practice.
abstract final class LibraryDateFormat {
  static final Map<String, MaterialLocalizations> _loaded =
      <String, MaterialLocalizations>{};
  static final Map<String, Future<void>> _loading = <String, Future<void>>{};

  /// Library language code: one of the 12 catalog codes.
  static String codeOf(BuildContext context) {
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    var code = locale.languageCode;
    if (code == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' ||
          country == 'TW' ||
          country == 'HK' ||
          country == 'MO') {
        code = 'zh_Hant';
      }
    }
    return _supported.contains(code) ? code : 'en';
  }

  static const Set<String> _supported = <String>{
    'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko',
  };

  static Locale _localeFor(String code) => switch (code) {
    'zh_Hant' => const Locale.fromSubtags(
      languageCode: 'zh',
      scriptCode: 'Hant',
    ),
    'zh' => const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans'),
    _ => Locale(code),
  };

  /// Starts loading the formats of the context's Library language.
  static Future<void> preload(BuildContext context) => _load(codeOf(context));

  static Future<void> _load(String code) {
    if (_loaded.containsKey(code)) return Future<void>.value();
    return _loading[code] ??= () async {
      try {
        final locale = _localeFor(code);
        if (GlobalMaterialLocalizations.delegate.isSupported(locale)) {
          _loaded[code] = await GlobalMaterialLocalizations.delegate.load(
            locale,
          );
        }
      } catch (_) {
        // Keep the ISO form for this language.
      } finally {
        _loading.remove(code);
      }
    }();
  }

  static MaterialLocalizations? _formats(BuildContext context) {
    final code = codeOf(context);
    final formats = _loaded[code];
    if (formats == null) _load(code);
    return formats;
  }

  /// Numeric date with the year, in the language's order
  /// (fr 09/10/2026, en 10/9/2026, ja 2026/10/09...).
  static String short(BuildContext context, DateTime date) {
    final local = date.toLocal();
    return _formats(context)?.formatShortDate(local) ?? iso(local);
  }

  /// Written-out date with the year (fr « vendredi 9 octobre 2026 »).
  static String full(BuildContext context, DateTime date) {
    final local = date.toLocal();
    return _formats(context)?.formatFullDate(local) ?? iso(local);
  }

  static String iso(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';

  @visibleForTesting
  static void resetForTesting() {
    _loaded.clear();
    _loading.clear();
  }
}
