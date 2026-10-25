import 'package:flutter/widgets.dart';

/// Nintendo Switch's embedded-engine status, never an external-app fallback.
abstract final class MelonxLocale {
  static const values = <String, Map<String, String>>{
    'en': {'unavailable': "The embedded MeloNX engine is unavailable in this build.", 'reimport': "Import this game into RewindBox. Its previous link to the external MeloNX app cannot be used by the embedded engine.", 'launchFailed': "The Nintendo Switch game could not be started."},
    'fr': {'unavailable': "Le moteur MeloNX embarqué est indisponible dans cette version.", 'reimport': "Importez ce jeu dans RewindBox. Son ancien lien vers l’application MeloNX externe ne peut pas être utilisé par le moteur embarqué.", 'launchFailed': "Impossible de démarrer le jeu Nintendo Switch."},
    'de': {'unavailable': "Die integrierte MeloNX-Engine ist in dieser Version nicht verfügbar.", 'reimport': "Importiere dieses Spiel in RewindBox. Sein bisheriger Link zur externen MeloNX-App kann von der integrierten Engine nicht verwendet werden.", 'launchFailed': "Das Nintendo-Switch-Spiel konnte nicht gestartet werden."},
    'es': {'unavailable': "El motor MeloNX integrado no está disponible en esta versión.", 'reimport': "Importa este juego en RewindBox. El motor integrado no puede usar su antiguo enlace a la aplicación externa MeloNX.", 'launchFailed': "No se pudo iniciar el juego de Nintendo Switch."},
    'it': {'unavailable': "Il motore MeloNX integrato non è disponibile in questa versione.", 'reimport': "Importa questo gioco in RewindBox. Il motore integrato non può usare il vecchio collegamento all’app MeloNX esterna.", 'launchFailed': "Impossibile avviare il gioco Nintendo Switch."},
    'pt': {'unavailable': "O motor MeloNX integrado não está disponível nesta versão.", 'reimport': "Importe este jogo no RewindBox. O motor integrado não pode utilizar a ligação anterior à aplicação externa MeloNX.", 'launchFailed': "Não foi possível iniciar o jogo da Nintendo Switch."},
    'ru': {'unavailable': "Встроенный движок MeloNX недоступен в этой версии.", 'reimport': "Импортируйте эту игру в RewindBox. Встроенный движок не может использовать прежнюю ссылку на внешнее приложение MeloNX.", 'launchFailed': "Не удалось запустить игру Nintendo Switch."},
    'id': {'unavailable': "Mesin MeloNX bawaan tidak tersedia dalam versi ini.", 'reimport': "Impor game ini ke RewindBox. Mesin bawaan tidak dapat menggunakan tautan lama ke aplikasi MeloNX eksternal.", 'launchFailed': "Game Nintendo Switch tidak dapat dimulai."},
    'ja': {'unavailable': "このバージョンでは内蔵MeloNXエンジンを利用できません。", 'reimport': "このゲームをRewindBoxに読み込んでください。外部MeloNXアプリへの以前のリンクは内蔵エンジンでは使用できません。", 'launchFailed': "Nintendo Switchのゲームを開始できませんでした。"},
    'ko': {'unavailable': "이 버전에서는 내장 MeloNX 엔진을 사용할 수 없습니다.", 'reimport': "이 게임을 RewindBox으로 가져오세요. 내장 엔진은 외부 MeloNX 앱으로 연결되는 이전 링크를 사용할 수 없습니다.", 'launchFailed': "Nintendo Switch 게임을 시작할 수 없습니다."},
    'zh': {'unavailable': "此版本无法使用内置 MeloNX 引擎。", 'reimport': "请将此游戏导入 RewindBox。内置引擎无法使用之前指向外部 MeloNX 应用的链接。", 'launchFailed': "无法启动 Nintendo Switch 游戏。"},
    'zh_Hant': {'unavailable': "此版本無法使用內建 MeloNX 引擎。", 'reimport': "請將此遊戲匯入 RewindBox。內建引擎無法使用先前指向外部 MeloNX 應用程式的連結。", 'launchFailed': "無法啟動 Nintendo Switch 遊戲。"},
  };

  static String forLocale(Locale locale, String key) {
    final traditional = locale.languageCode == 'zh' &&
        (locale.scriptCode == 'Hant' || const {'TW', 'HK', 'MO'}.contains(locale.countryCode));
    return (values[traditional ? 'zh_Hant' : locale.languageCode] ?? values['en']!)[key] ?? key;
  }
}

