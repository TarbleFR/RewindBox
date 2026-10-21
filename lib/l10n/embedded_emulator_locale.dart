import 'package:flutter/widgets.dart';

/// Small shared localization surface for emulators compiled into RewindBox.
///
/// Keep emulator product names untranslated; only the embedded-status text is
/// localized in the same twelve locales exposed by RewindBox.
abstract final class EmbeddedEmulatorLocale {
  static const Map<String, String> _integrated = <String, String>{
    'en': 'Embedded in RewindBox',
    'fr': 'Embarqué dans RewindBox',
    'de': 'In RewindBox integriert',
    'es': 'Integrado en RewindBox',
    'it': 'Integrato in RewindBox',
    'pt': 'Integrado no RewindBox',
    'ru': 'Встроен в RewindBox',
    'id': 'Tersemat di RewindBox',
    'ja': 'RewindBox に内蔵',
    'ko': 'RewindBox에 내장됨',
    'zh': '内置于 RewindBox',
    'zh_Hant': '內建於 RewindBox',
  };

  static String integrated(BuildContext context) {
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    var key = locale.languageCode;
    if (key == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' ||
          country == 'TW' ||
          country == 'HK' ||
          country == 'MO') {
        key = 'zh_Hant';
      }
    }
    return _integrated[key] ?? _integrated['en']!;
  }
}
