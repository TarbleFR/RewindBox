import 'package:flutter/widgets.dart';

/// iOS-specific first-run setup copy: the "link a folder without moving it"
/// option of the setup wizard and the relaunch message shown once a folder is
/// linked. Any games folder can be linked (RetroArch's is only an example);
/// embedded consoles never need the RetroArch app (Build 438).
abstract final class IosSetupLocale {
  static const Map<String, String> _linkTitles = {
    'de': 'RetroArch verknüpfen',
    'en': 'Link RetroArch',
    'es': 'Vincular RetroArch',
    'fr': 'Lier RetroArch',
    'id': 'Tautkan RetroArch',
    'it': 'Collega RetroArch',
    'ja': 'RetroArch をリンク',
    'ko': 'RetroArch 연결',
    'pt': 'Vincular RetroArch',
    'ru': 'Подключить RetroArch',
    'zh': '连接 RetroArch',
    'zh_Hant': '連結 RetroArch',
  };

  static const Map<String, String> _linkDescriptions = {
    'de': 'Wähle einen Ordner, der deine Spiele bereits enthält, zum Beispiel den von RetroArch. NeoStation liest ihn direkt dort, ohne etwas zu kopieren oder zu verschieben.',
    'en': 'Choose a folder that already holds your games, RetroArch’s for example. NeoStation reads it in place, without copying or moving anything.',
    'es': 'Elige una carpeta que ya contenga tus juegos, por ejemplo la de RetroArch. NeoStation la lee donde está, sin copiar ni mover nada.',
    'fr': 'Choisissez un dossier qui contient déjà vos jeux, celui de RetroArch par exemple. NeoStation le lit sur place, sans rien copier ni déplacer.',
    'id': 'Pilih folder yang sudah berisi game Anda, misalnya folder RetroArch. NeoStation membacanya langsung di tempat tanpa menyalin atau memindahkan apa pun.',
    'it': 'Scegli una cartella che contiene già i tuoi giochi, per esempio quella di RetroArch. NeoStation la legge dove si trova, senza copiare né spostare nulla.',
    'ja': 'ゲームが入っているフォルダ（たとえば RetroArch のフォルダ）を選んでください。NeoStation は何もコピーや移動をせず、その場所から読み込みます。',
    'ko': '게임이 이미 들어 있는 폴더(예: RetroArch 폴더)를 선택하세요. NeoStation은 아무것도 복사하거나 옮기지 않고 그 자리에서 읽습니다.',
    'pt': 'Escolha uma pasta que já contenha seus jogos, a do RetroArch por exemplo. O NeoStation a lê no lugar, sem copiar nem mover nada.',
    'ru': 'Выберите папку, в которой уже есть ваши игры, например папку RetroArch. NeoStation читает её на месте, ничего не копируя и не перемещая.',
    'zh': '选择一个已存放游戏的文件夹，例如 RetroArch 的文件夹。NeoStation 会直接在原处读取，不复制也不移动任何内容。',
    'zh_Hant': '選擇一個已存放遊戲的資料夾，例如 RetroArch 的資料夾。NeoStation 會直接在原處讀取，不會複製或移動任何內容。',
  };

  static const Map<String, String> _linked = {
    'de': 'Verknüpft und synchronisiert.',
    'en': 'Linked and synced.',
    'es': 'Vinculado y sincronizado.',
    'fr': 'Lié et synchronisé.',
    'id': 'Tertaut dan tersinkron.',
    'it': 'Collegato e sincronizzato.',
    'ja': 'リンクして同期しました。',
    'ko': '연결 및 동기화되었습니다.',
    'pt': 'Vinculado e sincronizado.',
    'ru': 'Подключено и синхронизировано.',
    'zh': '已连接并同步。',
    'zh_Hant': '已連結並同步。',
  };

  static const Map<String, String> _restartTitles = {
    'de': 'Fast geschafft',
    'en': 'Almost there',
    'es': 'Ya casi está',
    'fr': 'Presque terminé',
    'id': 'Hampir selesai',
    'it': 'Ci siamo quasi',
    'ja': 'あと少しです',
    'ko': '거의 다 됐어요',
    'pt': 'Quase lá',
    'ru': 'Почти готово',
    'zh': '快完成了',
    'zh_Hant': '快完成了',
  };

  static const Map<String, String> _restartDescriptions = {
    'de': 'Dein Spieleordner ist verknüpft. Starte NeoStation neu, um deine Spiele hier zu sehen.',
    'en': 'Your games folder is linked. Relaunch NeoStation to see your games here.',
    'es': 'Tu carpeta de juegos está vinculada. Reinicia NeoStation para ver aquí tus juegos.',
    'fr': 'Votre dossier de jeux est lié. Relancez NeoStation pour voir vos jeux ici.',
    'id': 'Folder game Anda sudah tertaut. Jalankan ulang NeoStation untuk melihat game Anda di sini.',
    'it': 'La cartella dei giochi è collegata. Riavvia NeoStation per vedere qui i tuoi giochi.',
    'ja': 'ゲームフォルダはリンクされています。NeoStation を再起動すると、ゲームがここに表示されます。',
    'ko': '게임 폴더가 연결되었습니다. NeoStation을 다시 실행하면 게임이 여기에 표시됩니다.',
    'pt': 'Sua pasta de jogos está vinculada. Reinicie o NeoStation para ver seus jogos aqui.',
    'ru': 'Папка с играми подключена. Перезапустите NeoStation, чтобы увидеть здесь свои игры.',
    'zh': '游戏文件夹已连接。重新启动 NeoStation 即可在这里看到你的游戏。',
    'zh_Hant': '遊戲資料夾已連結。重新啟動 NeoStation 即可在這裡看到你的遊戲。',
  };

  static const Map<String, String> _linkActionLabels = {
    'de': 'Verknüpfen',
    'en': 'Link',
    'es': 'Vincular',
    'fr': 'Lier',
    'id': 'Tautkan',
    'it': 'Collega',
    'ja': 'リンク',
    'ko': '연결',
    'pt': 'Vincular',
    'ru': 'Связать',
    'zh': '连接',
    'zh_Hant': '連結',
  };

  static const Map<String, String> _installActionLabels = {
    'de': 'Installieren',
    'en': 'Install',
    'es': 'Instalar',
    'fr': 'Installer',
    'id': 'Instal',
    'it': 'Installa',
    'ja': 'インストール',
    'ko': '설치',
    'pt': 'Instalar',
    'ru': 'Установить',
    'zh': '安装',
    'zh_Hant': '安裝',
  };

  static const Map<String, String> _continueLabels = {
    'de': 'Weiter',
    'en': 'Continue',
    'es': 'Continuar',
    'fr': 'Continuer',
    'id': 'Lanjutkan',
    'it': 'Continua',
    'ja': '続ける',
    'ko': '계속',
    'pt': 'Continuar',
    'ru': 'Продолжить',
    'zh': '继续',
    'zh_Hant': '繼續',
  };

  static String linkTitle(BuildContext context) =>
      _lookup(_linkTitles, context);
  static String linkDescription(BuildContext context) =>
      _lookup(_linkDescriptions, context);
  static String linked(BuildContext context) => _lookup(_linked, context);
  static String restartTitle(BuildContext context) =>
      _lookup(_restartTitles, context);
  static String restartDescription(BuildContext context) =>
      _lookup(_restartDescriptions, context);
  static String linkAction(BuildContext context) =>
      _lookup(_linkActionLabels, context);
  static String installAction(BuildContext context) =>
      _lookup(_installActionLabels, context);
  static String continueLabel(BuildContext context) =>
      _lookup(_continueLabels, context);

  static String _lookup(Map<String, String> values, BuildContext context) {
    final locale = Localizations.localeOf(context);
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
