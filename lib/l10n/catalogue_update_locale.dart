import 'package:flutter/widgets.dart';
import 'package:flutter_localization/flutter_localization.dart';

/// Localized labels of the bell notification announcing newer catalogues.
///
/// The places named in the messages are the app's own labels: Settings >
/// Tools > "Cheats & Enhancements catalogue" ([EnhancementsLocale.toolTitle],
/// whose page has "Check for catalogue updates"), and a game's "HD textures"
/// page, whose catalogue row is "Download the HD catalogues" (labels.json of
/// neo_texture_catalog).
abstract final class CatalogueUpdateLocale {
  static const Map<String, String> _titles = {
    'de': 'Neue Kataloge verfügbar',
    'en': 'New catalogues available',
    'es': 'Nuevos catálogos disponibles',
    'fr': 'Nouveaux catalogues disponibles',
    'id': 'Katalog baru tersedia',
    'it': 'Nuovi cataloghi disponibili',
    'ja': '新しいカタログがあります',
    'ko': '새 카탈로그를 사용할 수 있습니다',
    'pt': 'Novos catálogos disponíveis',
    'ru': 'Доступны новые каталоги',
    'zh': '有新的目录可用',
    'zh_Hant': '有新的目錄可用',
  };

  /// `{added}` is replaced by [_entriesAdded] when the count grew, else by nothing.
  static const Map<String, String> _enhancements = {
    'de':
        'Katalog Cheats & Verbesserungen{added}: Einstellungen > Werkzeuge.',
    'en': 'Cheats & Enhancements catalogue{added}: Settings > Tools.',
    'es': 'Catálogo de trucos y mejoras{added}: Ajustes > Herramientas.',
    'fr': 'Catalogue Cheats & Enhancements{added} : Paramètres > Outils.',
    'id': 'Katalog Cheat & Peningkatan{added}: Pengaturan > Alat.',
    'it':
        'Catalogo trucchi e miglioramenti{added}: Impostazioni > Strumenti.',
    'ja': 'チート＆拡張カタログ{added}：設定 > ツール。',
    'ko': '치트 및 향상 카탈로그{added}: 설정 > 도구.',
    'pt':
        'Catálogo de cheats e melhorias{added}: Configurações > Ferramentas.',
    'ru': 'Каталог читов и улучшений{added}: Настройки > Инструменты.',
    'zh': '金手指与增强目录{added}：设置 > 工具。',
    'zh_Hant': '金手指與增強目錄{added}：設定 > 工具。',
  };

  /// `{added}` is replaced by [_packsAdded] when the count grew, else by nothing.
  static const Map<String, String> _textures = {
    'de':
        'HD-Texturen{added}: Seite HD-Texturen eines Spiels, „HD-Kataloge herunterladen“.',
    'en':
        'HD textures{added}: a game\'s HD textures page, "Download the HD catalogues".',
    'es':
        'Texturas HD{added}: página Texturas HD de un juego, «Descargar los catálogos HD».',
    'fr':
        'Textures HD{added} : page Textures HD d’un jeu, « Télécharger les catalogues HD ».',
    'id':
        'Tekstur HD{added}: halaman Tekstur HD sebuah game, "Unduh katalog HD".',
    'it':
        'Texture HD{added}: pagina Texture HD di un gioco, «Scarica i cataloghi HD».',
    'ja': 'HDテクスチャ{added}：ゲームのHDテクスチャページ「HDカタログをダウンロード」。',
    'ko': 'HD 텍스처{added}: 게임의 HD 텍스처 페이지, "HD 카탈로그 다운로드".',
    'pt':
        'Texturas HD{added}: página Texturas HD de um jogo, "Baixar os catálogos HD".',
    'ru':
        'HD-текстуры{added}: страница HD-текстур игры, «Загрузить HD-каталоги».',
    'zh': '高清纹理{added}：游戏的高清纹理页面，“下载高清目录”。',
    'zh_Hant': '高畫質材質{added}：遊戲的高畫質材質頁面，「下載高畫質目錄」。',
  };

  /// `{count}` is replaced by the number of entries added.
  static const Map<String, String> _entriesAdded = {
    'de': ' (+{count} Einträge)',
    'en': ' (+{count} entries)',
    'es': ' (+{count} entradas)',
    'fr': ' (+{count} entrées)',
    'id': ' (+{count} entri)',
    'it': ' (+{count} voci)',
    'ja': '（+{count} 件）',
    'ko': ' (+{count}개 항목)',
    'pt': ' (+{count} entradas)',
    'ru': ' (+{count} записей)',
    'zh': '（+{count} 项）',
    'zh_Hant': '（+{count} 項）',
  };

  /// `{count}` is replaced by the number of packs added.
  static const Map<String, String> _packsAdded = {
    'de': ' (+{count} Pakete)',
    'en': ' (+{count} packs)',
    'es': ' (+{count} paquetes)',
    'fr': ' (+{count} packs)',
    'id': ' (+{count} paket)',
    'it': ' (+{count} pacchetti)',
    'ja': '（+{count} パック）',
    'ko': ' (+{count}개 팩)',
    'pt': ' (+{count} pacotes)',
    'ru': ' (+{count} наборов)',
    'zh': '（+{count} 个包）',
    'zh_Hant': '（+{count} 個包）',
  };

  /// Notification title, read without a [BuildContext].
  static String title([Locale? locale]) => _lookup(_titles, locale);

  /// Notification body: one sentence per catalogue that has a newer
  /// publication, with the number of entries it adds when it grew.
  static String message({int? enhancementsAdded, int? texturesAdded, Locale? locale}) {
    final lines = <String>[
      if (enhancementsAdded != null)
        _lookup(_enhancements, locale).replaceAll('{added}', _added(_entriesAdded, enhancementsAdded, locale)),
      if (texturesAdded != null)
        _lookup(_textures, locale).replaceAll('{added}', _added(_packsAdded, texturesAdded, locale)),
    ];
    // No space after a full-width full stop (Chinese, Japanese).
    return lines.fold('', (text, line) => text.isEmpty || text.endsWith('。') ? '$text$line' : '$text $line');
  }

  static String _added(Map<String, String> unit, int count, Locale? locale) =>
      count > 0 ? _lookup(unit, locale).replaceAll('{count}', '$count') : '';

  /// Every table, for completeness checks.
  static const List<Map<String, String>> allTables = [_titles, _enhancements, _textures, _entriesAdded, _packsAdded];

  static String _lookup(Map<String, String> values, Locale? locale) {
    final current = locale ?? FlutterLocalization.instance.currentLocale;
    if (current == null) return values['en']!;
    return values[_localeKey(current)] ?? values['en']!;
  }

  static String _localeKey(Locale locale) {
    if (locale.languageCode == 'zh') {
      final scriptCode = locale.scriptCode?.toLowerCase();
      final countryCode = locale.countryCode?.toUpperCase();
      if (scriptCode == 'hant' || countryCode == 'TW' || countryCode == 'HK' || countryCode == 'MO') {
        return 'zh_Hant';
      }
    }
    return locale.languageCode;
  }
}
