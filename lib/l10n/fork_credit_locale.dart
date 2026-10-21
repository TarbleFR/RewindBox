import 'package:flutter/widgets.dart';

/// Localized credit for the NeoStation iOS fork.
///
/// Kept separate from the upstream locale maps so the fork-specific attribution
/// remains isolated from upstream translations while still covering every
/// language offered by NeoStation.
abstract final class ForkCreditLocale {
  static const Map<String, String> _titles = {
    'de': 'RewindBox',
    'en': 'RewindBox',
    'es': 'RewindBox',
    'fr': 'RewindBox',
    'id': 'RewindBox',
    'it': 'RewindBox',
    'ja': 'RewindBox',
    'ko': 'RewindBox',
    'pt': 'RewindBox',
    'ru': 'RewindBox',
    'zh': 'RewindBox',
    'zh_Hant': 'RewindBox',
  };

  static const Map<String, String> _descriptions = {
    'de': 'Dies ist ein iOS-Fork von NeoStation, erstellt und gepflegt von TarbleFR.',
    'en': 'This is an iOS fork of NeoStation, created and maintained by TarbleFR.',
    'es': 'Este es un fork de NeoStation para iOS, creado y mantenido por TarbleFR.',
    'fr': 'Ceci est un fork iOS de NeoStation, créé et maintenu par TarbleFR.',
    'id': 'Ini adalah fork iOS dari NeoStation, dibuat dan dipelihara oleh TarbleFR.',
    'it': 'Questo è un fork iOS di NeoStation, creato e mantenuto da TarbleFR.',
    'ja': 'これは NeoStation の iOS フォークで、TarbleFR が作成・メンテナンスしています。',
    'ko': 'NeoStation의 iOS 포크이며, TarbleFR이 제작하고 유지 관리합니다.',
    'pt': 'Este é um fork do NeoStation para iOS, criado e mantido por TarbleFR.',
    'ru': 'Это iOS-форк NeoStation, созданный и поддерживаемый TarbleFR.',
    'zh': '这是 NeoStation 的 iOS 分支版本，由 TarbleFR 创建并维护。',
    'zh_Hant': '這是 NeoStation 的 iOS 分支版本，由 TarbleFR 建立並維護。',
  };

  static String title(BuildContext context) {
    return _lookup(_titles, Localizations.localeOf(context));
  }

  static String description(BuildContext context) {
    return _lookup(_descriptions, Localizations.localeOf(context));
  }

  static String _lookup(Map<String, String> values, Locale locale) {
    return values[_localeKey(locale)] ?? values['en']!;
  }

  static String _localeKey(Locale locale) {
    if (locale.languageCode == 'zh') {
      final scriptCode = locale.scriptCode?.toLowerCase();
      final countryCode = locale.countryCode?.toUpperCase();
      if (scriptCode == 'hant' ||
          countryCode == 'TW' ||
          countryCode == 'HK' ||
          countryCode == 'MO') {
        return 'zh_Hant';
      }
    }
    return locale.languageCode;
  }
}
