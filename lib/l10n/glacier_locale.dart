import 'package:flutter/widgets.dart';

import 'interface_style_locale.dart';

/// Texts of the RewindBox Glacier menu and of its one-step preset, in
/// RewindBox's twelve languages. "RewindBox", "Glacier", "System Art", "LB"
/// and "RB" are names and stay identical in every language.
abstract final class GlacierLocale {
  /// Second line of the recent game card ("Hogwarts Legacy / Récent").
  static const recent = 'recent';
  static const presetSubtitle = 'presetSubtitle';
  static const presetApply = 'presetApply';
  static const presetRestore = 'presetRestore';
  static const presetActive = 'presetActive';
  static const presetApplied = 'presetApplied';
  static const presetRestored = 'presetRestored';
  static const bundledPack = 'bundledPack';

  static const Map<String, Map<String, String>> values = {
    'en': {
      recent: 'Recent',
      presetSubtitle: 'Menu, background, tab glyphs and System Art in one step',
      presetApply: 'Apply Glacier',
      presetRestore: 'Restore previous look',
      presetActive: 'Glacier is active',
      presetApplied: 'RewindBox Glacier applied',
      presetRestored: 'Previous look restored',
      bundledPack: 'Included in the app · works offline',
    },
    'es': {
      recent: 'Reciente',
      presetSubtitle:
          'Menú, fondo, iconos de pestañas y System Art en un solo paso',
      presetApply: 'Aplicar Glacier',
      presetRestore: 'Restaurar el aspecto anterior',
      presetActive: 'Glacier está activo',
      presetApplied: 'RewindBox Glacier aplicado',
      presetRestored: 'Aspecto anterior restaurado',
      bundledPack: 'Incluido en la app · funciona sin conexión',
    },
    'ru': {
      recent: 'Недавнее',
      presetSubtitle: 'Меню, фон, значки вкладок и System Art за один шаг',
      presetApply: 'Применить Glacier',
      presetRestore: 'Вернуть прежний вид',
      presetActive: 'Glacier включён',
      presetApplied: 'RewindBox Glacier применён',
      presetRestored: 'Прежний вид восстановлен',
      bundledPack: 'Входит в приложение · работает офлайн',
    },
    'zh': {
      recent: '最近',
      presetSubtitle: '一步应用菜单、背景、标签图标和 System Art',
      presetApply: '应用 Glacier',
      presetRestore: '恢复之前的外观',
      presetActive: 'Glacier 已启用',
      presetApplied: '已应用 RewindBox Glacier',
      presetRestored: '已恢复之前的外观',
      bundledPack: '内置于应用 · 可离线使用',
    },
    'zh_Hant': {
      recent: '最近',
      presetSubtitle: '一步套用選單、背景、分頁圖示與 System Art',
      presetApply: '套用 Glacier',
      presetRestore: '還原先前的外觀',
      presetActive: 'Glacier 已啟用',
      presetApplied: '已套用 RewindBox Glacier',
      presetRestored: '已還原先前的外觀',
      bundledPack: '內建於 App · 可離線使用',
    },
    'pt': {
      recent: 'Recente',
      presetSubtitle: 'Menu, fundo, ícones das abas e System Art de uma só vez',
      presetApply: 'Aplicar Glacier',
      presetRestore: 'Restaurar o visual anterior',
      presetActive: 'Glacier está ativo',
      presetApplied: 'RewindBox Glacier aplicado',
      presetRestored: 'Visual anterior restaurado',
      bundledPack: 'Incluído no app · funciona offline',
    },
    'fr': {
      recent: 'Récent',
      presetSubtitle:
          'Menu, fond, pictogrammes des onglets et System Art en une fois',
      presetApply: 'Appliquer Glacier',
      presetRestore: "Revenir à l'apparence précédente",
      presetActive: 'Glacier est actif',
      presetApplied: 'RewindBox Glacier appliqué',
      presetRestored: 'Apparence précédente rétablie',
      bundledPack: "Inclus dans l'app · fonctionne hors ligne",
    },
    'de': {
      recent: 'Zuletzt',
      presetSubtitle:
          'Menü, Hintergrund, Tab-Symbole und System Art in einem Schritt',
      presetApply: 'Glacier anwenden',
      presetRestore: 'Vorheriges Aussehen wiederherstellen',
      presetActive: 'Glacier ist aktiv',
      presetApplied: 'RewindBox Glacier angewendet',
      presetRestored: 'Vorheriges Aussehen wiederhergestellt',
      bundledPack: 'In der App enthalten · funktioniert offline',
    },
    'it': {
      recent: 'Recente',
      presetSubtitle:
          'Menu, sfondo, icone delle schede e System Art in un solo passaggio',
      presetApply: 'Applica Glacier',
      presetRestore: "Ripristina l'aspetto precedente",
      presetActive: 'Glacier è attivo',
      presetApplied: 'RewindBox Glacier applicato',
      presetRestored: 'Aspetto precedente ripristinato',
      bundledPack: "Incluso nell'app · funziona offline",
    },
    'id': {
      recent: 'Terbaru',
      presetSubtitle: 'Menu, latar, ikon tab, dan System Art sekaligus',
      presetApply: 'Terapkan Glacier',
      presetRestore: 'Kembalikan tampilan sebelumnya',
      presetActive: 'Glacier aktif',
      presetApplied: 'RewindBox Glacier diterapkan',
      presetRestored: 'Tampilan sebelumnya dikembalikan',
      bundledPack: 'Sudah ada di aplikasi · berfungsi offline',
    },
    'ja': {
      recent: '最近',
      presetSubtitle: 'メニュー、背景、タブアイコン、System Art をまとめて適用',
      presetApply: 'Glacier を適用',
      presetRestore: '以前の外観に戻す',
      presetActive: 'Glacier は有効です',
      presetApplied: 'RewindBox Glacier を適用しました',
      presetRestored: '以前の外観に戻しました',
      bundledPack: 'アプリに内蔵 · オフラインで使用可',
    },
    'ko': {
      recent: '최근',
      presetSubtitle: '메뉴, 배경, 탭 아이콘, System Art를 한 번에 적용',
      presetApply: 'Glacier 적용',
      presetRestore: '이전 모양으로 되돌리기',
      presetActive: 'Glacier 사용 중',
      presetApplied: 'RewindBox Glacier 적용됨',
      presetRestored: '이전 모양으로 되돌렸습니다',
      bundledPack: '앱에 포함 · 오프라인 사용 가능',
    },
  };

  static String forLocale(Locale locale, String key) {
    var code = InterfaceStyleLocale.codeFor(locale);
    if (!values.containsKey(code)) code = 'en';
    return values[code]![key] ?? values['en']![key] ?? key;
  }

  static String text(BuildContext context, String key) =>
      forLocale(InterfaceStyleLocale.localeOf(context), key);
}
