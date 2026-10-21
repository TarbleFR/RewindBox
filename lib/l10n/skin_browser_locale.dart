import 'package:flutter/widgets.dart';

/// Texts added by the skin pages of Build 448 (collapsible catalog filters,
/// preview orientation selector, details of a catalog skin) in RewindBox's
/// twelve languages. The other skin texts stay in LibretroLocale.
abstract final class SkinBrowserLocale {
  static const filters = 'filters';
  static const preview = 'preview';
  static const showDetails = 'showDetails';
  static const close = 'close';

  static const Map<String, Map<String, String>> values = {
    'en': {
      filters: 'Filters',
      preview: 'Preview',
      showDetails: 'Show the details',
      close: 'Close',
    },
    'fr': {
      filters: 'Filtres',
      preview: 'Aperçu',
      showDetails: 'Afficher les détails',
      close: 'Fermer',
    },
    'de': {
      filters: 'Filter',
      preview: 'Vorschau',
      showDetails: 'Details anzeigen',
      close: 'Schließen',
    },
    'es': {
      filters: 'Filtros',
      preview: 'Vista previa',
      showDetails: 'Mostrar los detalles',
      close: 'Cerrar',
    },
    'it': {
      filters: 'Filtri',
      preview: 'Anteprima',
      showDetails: 'Mostra i dettagli',
      close: 'Chiudi',
    },
    'pt': {
      filters: 'Filtros',
      preview: 'Pré-visualização',
      showDetails: 'Mostrar os detalhes',
      close: 'Fechar',
    },
    'ru': {
      filters: 'Фильтры',
      preview: 'Предпросмотр',
      showDetails: 'Показать подробности',
      close: 'Закрыть',
    },
    'id': {
      filters: 'Saring',
      preview: 'Pratinjau',
      showDetails: 'Tampilkan detail',
      close: 'Tutup',
    },
    'ja': {
      filters: 'フィルター',
      preview: 'プレビュー',
      showDetails: '詳細を表示',
      close: '閉じる',
    },
    'ko': {
      filters: '필터',
      preview: '미리보기',
      showDetails: '자세히 보기',
      close: '닫기',
    },
    'zh': {
      filters: '筛选',
      preview: '预览',
      showDetails: '显示详细信息',
      close: '关闭',
    },
    'zh_Hant': {
      filters: '篩選',
      preview: '預覽',
      showDetails: '顯示詳細資訊',
      close: '關閉',
    },
  };

  /// Catalog code for [locale]: `zh_Hant` for Traditional Chinese (script
  /// Hant, or Taiwan, Hong Kong, Macao), English for unsupported languages.
  static String codeFor(Locale locale) {
    var code = locale.languageCode;
    if (code == 'zh_Hant') return 'zh_Hant';
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
    return values.containsKey(code) ? code : 'en';
  }

  static String forLocale(Locale locale, String key) =>
      values[codeFor(locale)]?[key] ?? values['en']![key] ?? key;

  static String text(BuildContext context, String key) => forLocale(
    Localizations.maybeLocaleOf(context) ?? const Locale('en'),
    key,
  );
}
