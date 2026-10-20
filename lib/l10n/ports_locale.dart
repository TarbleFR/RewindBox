import 'package:flutter/widgets.dart';

abstract final class PortsLocale {
  static const values = <String, Map<String, String>>{
    'en': {
      'import': 'Import',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad is no longer included in NeoStation; it installs as its own app. Your game file and saves remain in Files › NeoStation › Ports › KartPad.',
    },
    'fr': {
      'import': 'Importer',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad n’est plus inclus dans NeoStation ; il s’installe comme une application séparée. Votre fichier de jeu et vos sauvegardes restent dans Fichiers › NeoStation › Ports › KartPad.',
    },
    'es': {
      'import': 'Importar',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad ya no está incluido en NeoStation; se instala como una app independiente. Tu archivo de juego y tus partidas guardadas siguen en Archivos › NeoStation › Ports › KartPad.',
    },
    'pt': {
      'import': 'Importar',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'O Mario Kart Pad não está mais incluído no NeoStation; ele é instalado como um app separado. Seu arquivo de jogo e seus salvamentos continuam em Arquivos › NeoStation › Ports › KartPad.',
    },
    'de': {
      'import': 'Importieren',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad ist nicht mehr in NeoStation enthalten; es wird als eigene App installiert. Deine Spieldatei und deine Spielstände bleiben unter Dateien › NeoStation › Ports › KartPad.',
    },
    'it': {
      'import': 'Importa',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad non è più incluso in NeoStation; si installa come app separata. Il file del gioco e i salvataggi restano in File › NeoStation › Ports › KartPad.',
    },
    'ru': {
      'import': 'Импорт',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad больше не входит в NeoStation: он устанавливается как отдельное приложение. Файл игры и сохранения остаются в «Файлы» › NeoStation › Ports › KartPad.',
    },
    'zh': {
      'import': '导入',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'NeoStation 不再包含 Mario Kart Pad，它需作为独立的 App 安装。你的游戏文件和存档仍保留在“文件” › NeoStation › Ports › KartPad 中。',
    },
    'zh_Hant': {
      'import': '匯入',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'NeoStation 不再包含 Mario Kart Pad，它需作為獨立的 App 安裝。你的遊戲檔案和存檔仍保留在「檔案」› NeoStation › Ports › KartPad 中。',
    },
    'id': {
      'import': 'Impor',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad tidak lagi disertakan di NeoStation; aplikasi ini dipasang sebagai aplikasi terpisah. File game dan data simpanan Anda tetap ada di File › NeoStation › Ports › KartPad.',
    },
    'ja': {
      'import': 'インポート',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad は NeoStation に含まれなくなり、別のアプリとしてインストールします。ゲームファイルとセーブデータは「ファイル」› NeoStation › Ports › KartPad に残っています。',
    },
    'ko': {
      'import': '가져오기',
      'dusklight': 'DuskLight',
      'kartpadRemoved':
          'Mario Kart Pad는 더 이상 NeoStation에 포함되지 않으며 별도의 앱으로 설치합니다. 게임 파일과 저장 데이터는 파일 › NeoStation › Ports › KartPad에 그대로 남아 있습니다.',
    },
  };

  static String localeKey(Locale locale) => locale.languageCode == 'zh' &&
          (locale.scriptCode?.toLowerCase() == 'hant' ||
              ['TW', 'HK', 'MO'].contains(locale.countryCode?.toUpperCase()))
      ? 'zh_Hant'
      : locale.languageCode;

  static String forLocale(Locale locale, String key) {
    final table = values[localeKey(locale)] ?? values['en']!;
    return table[key] ?? values['en']![key] ?? key;
  }

  static String text(BuildContext context, String key) =>
      forLocale(Localizations.localeOf(context), key);
}
