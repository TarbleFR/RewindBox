import 'package:flutter/widgets.dart';

/// Texts of the ambient music (Build 448) in NeoStation's twelve languages:
/// Settings › General ("Ambient music", "Music volume") and the music card
/// of Settings › Themes. Track names (the bundled "Once Upon a Time — TAD"
/// or a file name) are inserted as they are, never translated.
abstract final class AmbientMusicLocale {
  static const title = 'title';
  static const description = 'description';
  static const track = 'track';
  static const trackHelp = 'trackHelp';
  static const volumeTitle = 'volumeTitle';
  static const volumeDescription = 'volumeDescription';
  static const volumeValue = 'volumeValue';
  static const on = 'on';
  static const off = 'off';
  static const cardDefault = 'cardDefault';
  static const cardCustom = 'cardCustom';
  static const choose = 'choose';
  static const restoreDefault = 'restoreDefault';

  static const Map<String, Map<String, String>> values = {
    'en': {
      title: 'Ambient music',
      description:
          'Plays in every section of the menu. It fades out when a game starts and comes back when you return.',
      track: 'Track: {track}',
      trackHelp: 'Your own file can replace it in Settings › Themes.',
      volumeTitle: 'Music volume',
      volumeDescription:
          'Independent of the game volume and of the sound effects.',
      volumeValue: '{percent}%',
      on: 'On',
      off: 'Off',
      cardDefault: 'Default · {track}',
      cardCustom: 'Your file · {track}',
      choose: 'Choose your music (MP3, WAV, OGG or FLAC)',
      restoreDefault: 'Back to the default music',
    },
    'fr': {
      title: 'Musique d’ambiance',
      description:
          'Joue dans toutes les sections du menu. Elle s’efface au lancement d’un jeu et revient à votre retour.',
      track: 'Piste : {track}',
      trackHelp:
          'Votre propre fichier peut la remplacer dans Paramètres › Thèmes.',
      volumeTitle: 'Volume de la musique',
      volumeDescription:
          'Indépendant du volume des jeux et des effets sonores.',
      volumeValue: '{percent}\u202f%',
      on: 'Activée',
      off: 'Désactivée',
      cardDefault: 'Par défaut · {track}',
      cardCustom: 'Votre fichier · {track}',
      choose: 'Choisir votre musique (MP3, WAV, OGG ou FLAC)',
      restoreDefault: 'Revenir à la musique par défaut',
    },
    'de': {
      title: 'Hintergrundmusik',
      description:
          'Läuft in allen Bereichen des Menüs. Beim Start eines Spiels wird sie ausgeblendet und kehrt bei deiner Rückkehr zurück.',
      track: 'Titel: {track}',
      trackHelp:
          'Eine eigene Datei kann sie unter Einstellungen › Themes ersetzen.',
      volumeTitle: 'Musiklautstärke',
      volumeDescription:
          'Unabhängig von der Lautstärke der Spiele und der Soundeffekte.',
      volumeValue: '{percent}\u00a0%',
      on: 'Ein',
      off: 'Aus',
      cardDefault: 'Standard · {track}',
      cardCustom: 'Deine Datei · {track}',
      choose: 'Eigene Musik wählen (MP3, WAV, OGG oder FLAC)',
      restoreDefault: 'Zur Standardmusik zurückkehren',
    },
    'es': {
      title: 'Música ambiental',
      description:
          'Suena en todas las secciones del menú. Se desvanece al iniciar un juego y vuelve cuando regresas.',
      track: 'Pista: {track}',
      trackHelp: 'Tu propio archivo puede sustituirla en Ajustes › Themes.',
      volumeTitle: 'Volumen de la música',
      volumeDescription:
          'Independiente del volumen de los juegos y de los efectos de sonido.',
      volumeValue: '{percent}\u00a0%',
      on: 'Activada',
      off: 'Desactivada',
      cardDefault: 'Predeterminada · {track}',
      cardCustom: 'Tu archivo · {track}',
      choose: 'Elegir tu música (MP3, WAV, OGG o FLAC)',
      restoreDefault: 'Volver a la música predeterminada',
    },
    'it': {
      title: 'Musica d’atmosfera',
      description:
          'Suona in tutte le sezioni del menu. Sfuma all’avvio di un gioco e riprende al tuo ritorno.',
      track: 'Brano: {track}',
      trackHelp: 'Un tuo file può sostituirla in Impostazioni › Temi.',
      volumeTitle: 'Volume della musica',
      volumeDescription:
          'Indipendente dal volume dei giochi e degli effetti sonori.',
      volumeValue: '{percent}%',
      on: 'Attiva',
      off: 'Disattivata',
      cardDefault: 'Predefinita · {track}',
      cardCustom: 'Il tuo file · {track}',
      choose: 'Scegli la tua musica (MP3, WAV, OGG o FLAC)',
      restoreDefault: 'Torna alla musica predefinita',
    },
    'pt': {
      title: 'Música ambiente',
      description:
          'Toca em todas as seções do menu. Diminui gradualmente ao iniciar um jogo e volta quando você retorna.',
      track: 'Faixa: {track}',
      trackHelp:
          'Seu próprio arquivo pode substituí-la em Configurações › Themes.',
      volumeTitle: 'Volume da música',
      volumeDescription:
          'Independente do volume dos jogos e dos efeitos sonoros.',
      volumeValue: '{percent}%',
      on: 'Ativada',
      off: 'Desativada',
      cardDefault: 'Padrão · {track}',
      cardCustom: 'Seu arquivo · {track}',
      choose: 'Escolher sua música (MP3, WAV, OGG ou FLAC)',
      restoreDefault: 'Voltar à música padrão',
    },
    'ru': {
      title: 'Фоновая музыка',
      description:
          'Звучит во всех разделах меню. Плавно затихает при запуске игры и возвращается, когда вы выходите из неё.',
      track: 'Трек: {track}',
      trackHelp: 'Её можно заменить своим файлом в разделе Настройки › Темы.',
      volumeTitle: 'Громкость музыки',
      volumeDescription: 'Не зависит от громкости игр и звуковых эффектов.',
      volumeValue: '{percent}\u00a0%',
      on: 'Включена',
      off: 'Выключена',
      cardDefault: 'По умолчанию · {track}',
      cardCustom: 'Ваш файл · {track}',
      choose: 'Выбрать свою музыку (MP3, WAV, OGG или FLAC)',
      restoreDefault: 'Вернуть музыку по умолчанию',
    },
    'id': {
      title: 'Musik latar',
      description:
          'Diputar di semua bagian menu. Memudar saat game dimulai dan kembali saat Anda kembali.',
      track: 'Lagu: {track}',
      trackHelp: 'File Anda sendiri dapat menggantinya di Pengaturan › Tema.',
      volumeTitle: 'Volume musik',
      volumeDescription: 'Terpisah dari volume game dan efek suara.',
      volumeValue: '{percent}%',
      on: 'Aktif',
      off: 'Nonaktif',
      cardDefault: 'Bawaan · {track}',
      cardCustom: 'File Anda · {track}',
      choose: 'Pilih musik Anda (MP3, WAV, OGG, atau FLAC)',
      restoreDefault: 'Kembali ke musik bawaan',
    },
    'ja': {
      title: 'メニューBGM',
      description: 'メニューのすべての画面で再生されます。ゲームの起動時にフェードアウトし、戻ると再開します。',
      track: '曲：{track}',
      trackHelp: '設定 › テーマ で自分のファイルに置き換えられます。',
      volumeTitle: 'BGMの音量',
      volumeDescription: 'ゲームの音量や効果音とは別に設定されます。',
      volumeValue: '{percent}%',
      on: 'オン',
      off: 'オフ',
      cardDefault: '標準 · {track}',
      cardCustom: 'あなたのファイル · {track}',
      choose: '自分の音楽を選ぶ（MP3、WAV、OGG、FLAC）',
      restoreDefault: '標準の音楽に戻す',
    },
    'ko': {
      title: '배경 음악',
      description: '메뉴의 모든 화면에서 재생됩니다. 게임을 시작하면 서서히 꺼지고, 돌아오면 다시 재생됩니다.',
      track: '곡: {track}',
      trackHelp: '설정 › 테마에서 내 파일로 바꿀 수 있습니다.',
      volumeTitle: '음악 볼륨',
      volumeDescription: '게임 볼륨 및 효과음과 별도로 설정됩니다.',
      volumeValue: '{percent}%',
      on: '켜짐',
      off: '꺼짐',
      cardDefault: '기본 · {track}',
      cardCustom: '내 파일 · {track}',
      choose: '내 음악 선택(MP3, WAV, OGG 또는 FLAC)',
      restoreDefault: '기본 음악으로 되돌리기',
    },
    'zh': {
      title: '背景音乐',
      description: '在菜单的所有页面中播放。启动游戏时淡出，返回后恢复播放。',
      track: '曲目：{track}',
      trackHelp: '可在 设置 › 主题 中换成你自己的文件。',
      volumeTitle: '音乐音量',
      volumeDescription: '独立于游戏音量和音效。',
      volumeValue: '{percent}%',
      on: '已开启',
      off: '已关闭',
      cardDefault: '默认 · {track}',
      cardCustom: '你的文件 · {track}',
      choose: '选择你的音乐（MP3、WAV、OGG 或 FLAC）',
      restoreDefault: '恢复默认音乐',
    },
    'zh_Hant': {
      title: '背景音樂',
      description: '在選單的所有頁面中播放。啟動遊戲時淡出，返回後恢復播放。',
      track: '曲目：{track}',
      trackHelp: '可在 設定 › 主題 中換成你自己的檔案。',
      volumeTitle: '音樂音量',
      volumeDescription: '獨立於遊戲音量和音效。',
      volumeValue: '{percent}%',
      on: '已開啟',
      off: '已關閉',
      cardDefault: '預設 · {track}',
      cardCustom: '你的檔案 · {track}',
      choose: '選擇你的音樂（MP3、WAV、OGG 或 FLAC）',
      restoreDefault: '恢復預設音樂',
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

  static String format(
    BuildContext context,
    String key,
    Map<String, Object?> parameters,
  ) {
    var value = text(context, key);
    for (final entry in parameters.entries) {
      value = value.replaceAll('{${entry.key}}', entry.value?.toString() ?? '');
    }
    return value;
  }
}
