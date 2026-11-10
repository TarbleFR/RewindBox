import 'package:flutter/cupertino.dart' show CupertinoLocalizations;
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

/// The saved language and FlutterLocalization catalog keep the existing
/// `zh_Hant` key. Only Flutter's built-in delegates need a structured Locale.
/// Do not normalize the surrounding Localizations locale: that would select
/// the app's `zh` catalog instead of its Traditional Chinese catalog.
Locale _frameworkLocale(Locale locale) {
  if (locale.languageCode == 'zh_Hant') {
    return Locale.fromSubtags(
      languageCode: 'zh',
      scriptCode: 'Hant',
      countryCode: locale.countryCode,
    );
  }
  return locale;
}

/// Keep FlutterLocalization's catalog delegate first on every app display.
/// These adapters resolve catalog aliases before MaterialApp's defaults;
/// the catalog delegate stays unchanged and owns all application strings.
const appWidgetLocalizationsDelegates = <LocalizationsDelegate<dynamic>>[
  FallbackMaterialLocalizationsDelegate(),
  _CatalogCupertinoLocalizationsDelegate(),
  _CatalogWidgetsLocalizationsDelegate(),
];

/// Historical public name retained for callers importing it from main.dart.
/// Loads the selected language instead of the previous unconditional English.
class FallbackMaterialLocalizationsDelegate
    extends LocalizationsDelegate<MaterialLocalizations> {
  const FallbackMaterialLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) =>
      GlobalMaterialLocalizations.delegate.isSupported(_frameworkLocale(locale));

  @override
  Future<MaterialLocalizations> load(Locale locale) =>
      GlobalMaterialLocalizations.delegate.load(_frameworkLocale(locale));

  @override
  bool shouldReload(
    covariant LocalizationsDelegate<MaterialLocalizations> old,
  ) => false;
}

class _CatalogCupertinoLocalizationsDelegate
    extends LocalizationsDelegate<CupertinoLocalizations> {
  const _CatalogCupertinoLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) =>
      GlobalCupertinoLocalizations.delegate.isSupported(_frameworkLocale(locale));

  @override
  Future<CupertinoLocalizations> load(Locale locale) =>
      GlobalCupertinoLocalizations.delegate.load(_frameworkLocale(locale));

  @override
  bool shouldReload(
    covariant LocalizationsDelegate<CupertinoLocalizations> old,
  ) => false;
}

class _CatalogWidgetsLocalizationsDelegate
    extends LocalizationsDelegate<WidgetsLocalizations> {
  const _CatalogWidgetsLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) =>
      GlobalWidgetsLocalizations.delegate.isSupported(_frameworkLocale(locale));

  @override
  Future<WidgetsLocalizations> load(Locale locale) =>
      GlobalWidgetsLocalizations.delegate.load(_frameworkLocale(locale));

  @override
  bool shouldReload(
    covariant LocalizationsDelegate<WidgetsLocalizations> old,
  ) => false;
}
