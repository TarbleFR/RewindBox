import 'package:flutter/widgets.dart';
import 'package:flutter_localization/flutter_localization.dart';

/// Localized labels announcing System Art packs that can be updated.
abstract final class SystemArtUpdateLocale {
  static const Map<String, String> _titles = {
    'de': 'System-Art-Updates',
    'en': 'System Art updates',
    'es': 'Actualizaciones de System Art',
    'fr': 'Mises à jour System Art',
    'id': 'Pembaruan System Art',
    'it': 'Aggiornamenti System Art',
    'ja': 'System Art のアップデート',
    'ko': 'System Art 업데이트',
    'pt': 'Atualizações de System Art',
    'ru': 'Обновления System Art',
    'zh': 'System Art 更新',
    'zh_Hant': 'System Art 更新',
  };

  /// `{packs}` is replaced by the pack names.
  static const Map<String, String> _messages = {
    'de':
        'Update verfügbar: {packs}. Unter Einstellungen > System Art installieren.',
    'en': 'Update available: {packs}. Install it from Settings > System Art.',
    'es':
        'Actualización disponible: {packs}. Instálala en Ajustes > System Art.',
    'fr':
        'Mise à jour disponible : {packs}. Installez-la depuis Paramètres > System Art.',
    'id': 'Pembaruan tersedia: {packs}. Pasang dari Pengaturan > System Art.',
    'it':
        'Aggiornamento disponibile: {packs}. Installalo da Impostazioni > System Art.',
    'ja': 'アップデートがあります: {packs}。設定 > System Art からインストールしてください。',
    'ko': '업데이트 가능: {packs}. 설정 > System Art에서 설치하세요.',
    'pt': 'Atualização disponível: {packs}. Instale em Configurações > System Art.',
    'ru':
        'Доступно обновление: {packs}. Установите его в Настройки > System Art.',
    'zh': '有可用更新：{packs}。请在 设置 > System Art 中安装。',
    'zh_Hant': '有可用更新：{packs}。請在 設定 > System Art 中安裝。',
  };

  static const Map<String, String> _badges = {
    'de': 'Update',
    'en': 'Update',
    'es': 'Actualizar',
    'fr': 'Mise à jour',
    'id': 'Pembaruan',
    'it': 'Aggiorna',
    'ja': '更新',
    'ko': '업데이트',
    'pt': 'Atualizar',
    'ru': 'Обновить',
    'zh': '更新',
    'zh_Hant': '更新',
  };

  /// Notification title, read without a [BuildContext].
  static String title([Locale? locale]) => _lookupLocale(_titles, locale);

  /// Notification body listing [packNames].
  static String message(List<String> packNames, [Locale? locale]) =>
      _lookupLocale(
        _messages,
        locale,
      ).replaceAll('{packs}', packNames.join(', '));

  /// Badge shown on a pack card that can be updated.
  static String badge(BuildContext context) =>
      _badges[_localeKey(Localizations.localeOf(context))] ?? _badges['en']!;

  /// Every locale key, for completeness tests.
  static const List<Map<String, String>> allTables = [
    _titles,
    _messages,
    _badges,
  ];

  static String _lookupLocale(Map<String, String> values, Locale? locale) {
    final current = locale ?? FlutterLocalization.instance.currentLocale;
    if (current == null) return values['en']!;
    return values[_localeKey(current)] ?? values['en']!;
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
