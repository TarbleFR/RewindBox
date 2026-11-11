// Strings of the Switch 2 playlist that S2ArmEngineLocale does not carry: the import button, its progress, the
// launch preparation dialog and the iOS 26 / pairing-file lines. 12 project locales; keep every key in every locale
// (test/switch2_library_locale_test.dart). Engine errors stay in S2ArmEngineLocale.
import 'package:flutter/widgets.dart';

abstract final class Switch2LibraryLocale {
  static const Map<String, Map<String, String>> values = <String, Map<String, String>>{
    'en': <String, String>{
      'importMenu': "Switch 2 / Import",
      'importFolder': "Import a Switch 2 export folder",
      'importing': "Importing {name}…",
      'preparing': "Preparing {name}…",
      'cancel': "Cancel",
      'imported': "{count} Switch 2 game(s) imported.",
      'duplicates': "{count} game(s) already in the library were skipped.",
      'cancelled': "Import cancelled. No partial game was kept.",
      'requiresIOS26': "Switch 2 games require iOS 26 or later.",
      'pairingRequired': "Switch 2 games need the JIT pairing file. Import it in the JIT settings, then try again.",
    },
    'es': <String, String>{
      'importMenu': "Switch 2 / Importar",
      'importFolder': "Importar una carpeta de exportación de Switch 2",
      'importing': "Importando {name}…",
      'preparing': "Preparando {name}…",
      'cancel': "Cancelar",
      'imported': "{count} juego(s) de Switch 2 importado(s).",
      'duplicates': "Se omitieron {count} juego(s) que ya estaban en la biblioteca.",
      'cancelled': "Importación cancelada. No se conservó ningún juego parcial.",
      'requiresIOS26': "Los juegos de Switch 2 requieren iOS 26 o posterior.",
      'pairingRequired': "Los juegos de Switch 2 necesitan el archivo de emparejamiento JIT. Impórtalo en los ajustes de JIT e inténtalo de nuevo.",
    },
    'ru': <String, String>{
      'importMenu': "Switch 2 / Импорт",
      'importFolder': "Импортировать папку экспорта Switch 2",
      'importing': "Импорт {name}…",
      'preparing': "Подготовка {name}…",
      'cancel': "Отмена",
      'imported': "Импортировано игр Switch 2: {count}.",
      'duplicates': "Пропущено игр, уже имеющихся в библиотеке: {count}.",
      'cancelled': "Импорт отменён. Неполные игры не сохранены.",
      'requiresIOS26': "Для игр Switch 2 требуется iOS 26 или новее.",
      'pairingRequired': "Для игр Switch 2 нужен файл сопряжения JIT. Импортируйте его в настройках JIT и повторите попытку.",
    },
    'zh': <String, String>{
      'importMenu': "Switch 2 / 导入",
      'importFolder': "导入 Switch 2 导出文件夹",
      'importing': "正在导入 {name}…",
      'preparing': "正在准备 {name}…",
      'cancel': "取消",
      'imported': "已导入 {count} 款 Switch 2 游戏。",
      'duplicates': "已跳过 {count} 款库中已有的游戏。",
      'cancelled': "导入已取消，未保留任何不完整的游戏。",
      'requiresIOS26': "Switch 2 游戏需要 iOS 26 或更高版本。",
      'pairingRequired': "Switch 2 游戏需要 JIT 配对文件。请在 JIT 设置中导入后重试。",
    },
    'zh_Hant': <String, String>{
      'importMenu': "Switch 2 / 匯入",
      'importFolder': "匯入 Switch 2 匯出資料夾",
      'importing': "正在匯入 {name}…",
      'preparing': "正在準備 {name}…",
      'cancel': "取消",
      'imported': "已匯入 {count} 款 Switch 2 遊戲。",
      'duplicates': "已略過 {count} 款資料庫中已有的遊戲。",
      'cancelled': "匯入已取消，未保留任何不完整的遊戲。",
      'requiresIOS26': "Switch 2 遊戲需要 iOS 26 或以上版本。",
      'pairingRequired': "Switch 2 遊戲需要 JIT 配對檔案。請在 JIT 設定中匯入後重試。",
    },
    'pt': <String, String>{
      'importMenu': "Switch 2 / Importar",
      'importFolder': "Importar uma pasta de exportação do Switch 2",
      'importing': "Importando {name}…",
      'preparing': "Preparando {name}…",
      'cancel': "Cancelar",
      'imported': "{count} jogo(s) de Switch 2 importado(s).",
      'duplicates': "{count} jogo(s) já presentes na biblioteca foram ignorados.",
      'cancelled': "Importação cancelada. Nenhum jogo parcial foi mantido.",
      'requiresIOS26': "Jogos de Switch 2 exigem iOS 26 ou posterior.",
      'pairingRequired': "Jogos de Switch 2 precisam do arquivo de pareamento JIT. Importe-o nos ajustes de JIT e tente de novo.",
    },
    'fr': <String, String>{
      'importMenu': "Switch 2 / Importer",
      'importFolder': "Importer un dossier d’export Switch 2",
      'importing': "Import de {name}…",
      'preparing': "Préparation de {name}…",
      'cancel': "Annuler",
      'imported': "{count} jeu(x) Switch 2 importé(s).",
      'duplicates': "{count} jeu(x) déjà dans la bibliothèque ont été ignoré(s).",
      'cancelled': "Import annulé. Aucun jeu partiel n’a été conservé.",
      'requiresIOS26': "Les jeux Switch 2 nécessitent iOS 26 ou une version ultérieure.",
      'pairingRequired': "Les jeux Switch 2 ont besoin du fichier d’appairage JIT. Importez-le dans les réglages JIT, puis réessayez.",
    },
    'de': <String, String>{
      'importMenu': "Switch 2 / Import",
      'importFolder': "Switch-2-Exportordner importieren",
      'importing': "{name} wird importiert…",
      'preparing': "{name} wird vorbereitet…",
      'cancel': "Abbrechen",
      'imported': "{count} Switch-2-Spiel(e) importiert.",
      'duplicates': "{count} bereits in der Bibliothek vorhandene(s) Spiel(e) übersprungen.",
      'cancelled': "Import abgebrochen. Kein unvollständiges Spiel wurde behalten.",
      'requiresIOS26': "Switch-2-Spiele erfordern iOS 26 oder neuer.",
      'pairingRequired': "Switch-2-Spiele benötigen die JIT-Pairing-Datei. Importiere sie in den JIT-Einstellungen und versuche es erneut.",
    },
    'it': <String, String>{
      'importMenu': "Switch 2 / Importa",
      'importFolder': "Importa una cartella di esportazione Switch 2",
      'importing': "Importazione di {name}…",
      'preparing': "Preparazione di {name}…",
      'cancel': "Annulla",
      'imported': "{count} gioco/giochi Switch 2 importato/i.",
      'duplicates': "{count} gioco/giochi già presenti nella libreria sono stati saltati.",
      'cancelled': "Importazione annullata. Nessun gioco parziale è stato conservato.",
      'requiresIOS26': "I giochi Switch 2 richiedono iOS 26 o versioni successive.",
      'pairingRequired': "I giochi Switch 2 richiedono il file di associazione JIT. Importalo nelle impostazioni JIT e riprova.",
    },
    'id': <String, String>{
      'importMenu': "Switch 2 / Impor",
      'importFolder': "Impor folder ekspor Switch 2",
      'importing': "Mengimpor {name}…",
      'preparing': "Menyiapkan {name}…",
      'cancel': "Batal",
      'imported': "{count} game Switch 2 diimpor.",
      'duplicates': "{count} game yang sudah ada di pustaka dilewati.",
      'cancelled': "Impor dibatalkan. Tidak ada game sebagian yang disimpan.",
      'requiresIOS26': "Game Switch 2 memerlukan iOS 26 atau yang lebih baru.",
      'pairingRequired': "Game Switch 2 membutuhkan file pairing JIT. Impor di pengaturan JIT, lalu coba lagi.",
    },
    'ja': <String, String>{
      'importMenu': "Switch 2 / 読み込み",
      'importFolder': "Switch 2 のエクスポートフォルダを読み込む",
      'importing': "{name} を読み込み中…",
      'preparing': "{name} を準備中…",
      'cancel': "キャンセル",
      'imported': "Switch 2 のゲームを {count} 本読み込みました。",
      'duplicates': "ライブラリに既にある {count} 本をスキップしました。",
      'cancelled': "読み込みをキャンセルしました。途中までのゲームは残していません。",
      'requiresIOS26': "Switch 2 のゲームには iOS 26 以降が必要です。",
      'pairingRequired': "Switch 2 のゲームには JIT のペアリングファイルが必要です。JIT 設定で読み込んでから、もう一度お試しください。",
    },
    'ko': <String, String>{
      'importMenu': "Switch 2 / 가져오기",
      'importFolder': "Switch 2 내보내기 폴더 가져오기",
      'importing': "{name} 가져오는 중…",
      'preparing': "{name} 준비 중…",
      'cancel': "취소",
      'imported': "Switch 2 게임 {count}개를 가져왔습니다.",
      'duplicates': "이미 라이브러리에 있는 게임 {count}개를 건너뛰었습니다.",
      'cancelled': "가져오기가 취소되었습니다. 불완전한 게임은 남기지 않았습니다.",
      'requiresIOS26': "Switch 2 게임에는 iOS 26 이상이 필요합니다.",
      'pairingRequired': "Switch 2 게임에는 JIT 페어링 파일이 필요합니다. JIT 설정에서 가져온 후 다시 시도하세요.",
    },
  };

  /// `zh_Hant` for Traditional Chinese (script Hant, or Taiwan, Hong Kong, Macao); English outside the 12 locales.
  static String codeFor(Locale locale) {
    var code = locale.languageCode;
    if (code == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' || country == 'TW' || country == 'HK' || country == 'MO') code = 'zh_Hant';
    }
    return values.containsKey(code) ? code : 'en';
  }

  static String forLocale(Locale locale, String key) => values[codeFor(locale)]?[key] ?? values['en']![key] ?? key;

  static String format(Locale locale, String key, Map<String, Object?> parameters) {
    var value = forLocale(locale, key);
    for (final entry in parameters.entries) {
      value = value.replaceAll('{${entry.key}}', entry.value?.toString() ?? '');
    }
    return value;
  }

  static String text(BuildContext context, String key) =>
      forLocale(Localizations.maybeLocaleOf(context) ?? const Locale('en'), key);

  static String textf(BuildContext context, String key, Map<String, Object?> parameters) =>
      format(Localizations.maybeLocaleOf(context) ?? const Locale('en'), key, parameters);
}
