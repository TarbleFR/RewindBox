import 'package:flutter/widgets.dart';
import 'package:flutter_localization/flutter_localization.dart';

import 'app_locale.dart';

/// Small shared localization surface for emulators compiled into RewindBox.
///
/// Product names and build identifiers retain the spelling of the engine.
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

  static String version(BuildContext context, String version) => AppLocale
      .updateVersion
      .getString(context)
      .replaceFirst('{version}', version);

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
