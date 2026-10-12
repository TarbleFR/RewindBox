import 'package:flutter/widgets.dart';

/// Texts of Settings › General › "AirPlay and external screen" (Build 447)
/// in NeoStation's twelve languages. Raw technical codes (plugin or scene
/// accessory status, platform error codes) are shown separately through
/// [technicalCode] and never translated.
abstract final class ExternalDisplayLocale {
  static const title = 'title';
  static const description = 'description';
  static const modeTitle = 'modeTitle';
  static const modeAutomatic = 'modeAutomatic';
  static const modeFit = 'modeFit';
  static const modeFill = 'modeFill';
  static const modeOriginal = 'modeOriginal';
  static const modeAutomaticHelp = 'modeAutomaticHelp';
  static const modeFitHelp = 'modeFitHelp';
  static const modeFillHelp = 'modeFillHelp';
  static const modeOriginalHelp = 'modeOriginalHelp';
  static const fillCrops = 'fillCrops';
  static const noExternalScreen = 'noExternalScreen';
  static const externalScreen = 'externalScreen';
  static const gameOnExternal = 'gameOnExternal';
  static const mirroringOff = 'mirroringOff';
  static const unsupportedEngine = 'unsupportedEngine';
  /// Build 449: outside a game the TV mirrors the iPhone (the "menu on the
  /// TV" switch and its two texts, and "menuOffMirroring", were removed).
  static const mirroringOutsideGames = 'mirroringOutsideGames';
  static const unavailable = 'unavailable';
  static const saveFailed = 'saveFailed';
  static const technicalCode = 'technicalCode';

  static const Map<String, Map<String, String>> values = {
    'en': {
      title: 'AirPlay and external screen',
      description:
          'During a game, NeoStation shows the game full screen on the TV or the adapter, with the controls on the iPhone. Outside a game, iOS mirrors the iPhone.',
      modeTitle: 'Picture format on the external screen',
      modeAutomatic: 'Automatic',
      modeFit: 'Fit to screen',
      modeFill: 'Fill the screen',
      modeOriginal: 'Original format',
      modeAutomaticHelp: 'Games keep their whole image, as with Fit to screen.',
      modeFitHelp:
          'The whole image is shown; bars appear only when the formats differ.',
      modeFillHelp: 'A 4:3 image is zoomed to the width of the screen.',
      modeOriginalHelp:
          'The iPhone format, centred at the height of the screen.',
      fillCrops: 'Fill the screen cuts the top and bottom of the image.',
      noExternalScreen: 'No external screen connected.',
      externalScreen: 'External screen: {width}×{height}',
      gameOnExternal: 'The game is shown on the external screen.',
      mirroringOff: 'Off: iOS mirrors the iPhone screen, with its bars.',
      unsupportedEngine:
          'This game’s engine does not use the external screen; iOS mirrors the iPhone.',
      mirroringOutsideGames:
          'Outside a game, iOS mirrors the NeoStation interface of the iPhone.',
      unavailable: 'Not available in this version of NeoStation.',
      saveFailed: 'The setting could not be saved.',
      technicalCode: 'Technical code: {code}',
    },
    'es': {
      title: 'AirPlay y pantalla externa',
      description:
          'Durante una partida, NeoStation muestra el juego a pantalla completa en el televisor o el adaptador, con los controles en el iPhone. Fuera del juego, iOS duplica el iPhone.',
      modeTitle: 'Formato de imagen en la pantalla externa',
      modeAutomatic: 'Automático',
      modeFit: 'Ajustar a la pantalla',
      modeFill: 'Llenar la pantalla',
      modeOriginal: 'Formato original',
      modeAutomaticHelp:
          'Los juegos conservan la imagen completa, como con «Ajustar a la pantalla».',
      modeFitHelp:
          'Se muestra la imagen completa; solo aparecen bandas si los formatos difieren.',
      modeFillHelp: 'Una imagen 4:3 se amplía al ancho de la pantalla.',
      modeOriginalHelp:
          'El formato del iPhone, centrado a la altura de la pantalla.',
      fillCrops:
          'Llenar la pantalla recorta la parte superior e inferior de la imagen.',
      noExternalScreen: 'No hay ninguna pantalla externa conectada.',
      externalScreen: 'Pantalla externa: {width}×{height}',
      gameOnExternal: 'El juego se muestra en la pantalla externa.',
      mirroringOff:
          'Desactivado: iOS duplica la pantalla del iPhone, con sus bandas.',
      unsupportedEngine:
          'El motor de este juego no usa la pantalla externa; iOS duplica el iPhone.',
      mirroringOutsideGames:
          'Fuera del juego, iOS duplica la interfaz de NeoStation del iPhone.',
      unavailable: 'No disponible en esta versión de NeoStation.',
      saveFailed: 'No se pudo guardar el ajuste.',
      technicalCode: 'Código técnico: {code}',
    },
    'ru': {
      title: 'AirPlay и внешний экран',
      description:
          'Во время игры NeoStation выводит игру на весь экран телевизора или адаптера, а управление остаётся на iPhone. Вне игры iOS повторяет экран iPhone.',
      modeTitle: 'Формат изображения на внешнем экране',
      modeAutomatic: 'Автоматически',
      modeFit: 'По размеру экрана',
      modeFill: 'Заполнить экран',
      modeOriginal: 'Исходный формат',
      modeAutomaticHelp:
          'Игры сохраняют полное изображение, как в режиме «По размеру экрана».',
      modeFitHelp:
          'Показывается всё изображение; полосы появляются, только если форматы различаются.',
      modeFillHelp: 'Изображение 4:3 увеличивается до ширины экрана.',
      modeOriginalHelp: 'Формат iPhone, по центру и по высоте экрана.',
      fillCrops: 'Режим «Заполнить экран» обрезает верх и низ изображения.',
      noExternalScreen: 'Внешний экран не подключён.',
      externalScreen: 'Внешний экран: {width}×{height}',
      gameOnExternal: 'Игра выводится на внешний экран.',
      mirroringOff: 'Выключено: iOS повторяет экран iPhone вместе с полосами.',
      unsupportedEngine:
          'Движок этой игры не использует внешний экран; iOS повторяет экран iPhone.',
      mirroringOutsideGames:
          'Вне игры iOS повторяет интерфейс NeoStation с экрана iPhone.',
      unavailable: 'Недоступно в этой версии NeoStation.',
      saveFailed: 'Не удалось сохранить настройку.',
      technicalCode: 'Технический код: {code}',
    },
    'zh': {
      title: 'AirPlay 与外接屏幕',
      description:
          '游戏期间，NeoStation 在电视或转接器上全屏显示游戏，操作控件保留在 iPhone 上。未进行游戏时，iOS 镜像 iPhone。',
      modeTitle: '外接屏幕上的画面格式',
      modeAutomatic: '自动',
      modeFit: '适应屏幕',
      modeFill: '填满屏幕',
      modeOriginal: '原始格式',
      modeAutomaticHelp: '游戏保留完整画面，与“适应屏幕”相同。',
      modeFitHelp: '显示完整画面；仅在比例不同时出现黑边。',
      modeFillHelp: '4:3 画面放大到屏幕宽度。',
      modeOriginalHelp: 'iPhone 的格式，按屏幕高度居中显示。',
      fillCrops: '“填满屏幕”会裁掉画面的顶部和底部。',
      noExternalScreen: '未连接外接屏幕。',
      externalScreen: '外接屏幕：{width}×{height}',
      gameOnExternal: '游戏显示在外接屏幕上。',
      mirroringOff: '已关闭：iOS 镜像 iPhone 屏幕，带有黑边。',
      unsupportedEngine: '此游戏的引擎不使用外接屏幕；iOS 镜像 iPhone。',
      mirroringOutsideGames: '未进行游戏时，iOS 镜像 iPhone 上的 NeoStation 界面。',
      unavailable: '此版本的 NeoStation 不支持。',
      saveFailed: '无法保存该设置。',
      technicalCode: '技术代码：{code}',
    },
    'zh_Hant': {
      title: 'AirPlay 與外接螢幕',
      description:
          '遊戲期間，NeoStation 在電視或轉接器上全螢幕顯示遊戲，操作控制保留在 iPhone 上。未進行遊戲時，iOS 鏡像輸出 iPhone。',
      modeTitle: '外接螢幕上的畫面格式',
      modeAutomatic: '自動',
      modeFit: '符合螢幕',
      modeFill: '填滿螢幕',
      modeOriginal: '原始格式',
      modeAutomaticHelp: '遊戲保留完整畫面，與「符合螢幕」相同。',
      modeFitHelp: '顯示完整畫面；僅在比例不同時出現黑邊。',
      modeFillHelp: '4:3 畫面放大至螢幕寬度。',
      modeOriginalHelp: 'iPhone 的格式，依螢幕高度置中顯示。',
      fillCrops: '「填滿螢幕」會裁掉畫面的頂部和底部。',
      noExternalScreen: '未連接外接螢幕。',
      externalScreen: '外接螢幕：{width}×{height}',
      gameOnExternal: '遊戲顯示在外接螢幕上。',
      mirroringOff: '已關閉：iOS 鏡像輸出 iPhone 螢幕，帶有黑邊。',
      unsupportedEngine: '此遊戲的引擎不使用外接螢幕；iOS 鏡像輸出 iPhone。',
      mirroringOutsideGames: '未進行遊戲時，iOS 鏡像輸出 iPhone 上的 NeoStation 介面。',
      unavailable: '此版本的 NeoStation 不支援。',
      saveFailed: '無法儲存此設定。',
      technicalCode: '技術代碼：{code}',
    },
    'pt': {
      title: 'AirPlay e tela externa',
      description:
          'Durante um jogo, o NeoStation mostra o jogo em tela cheia na TV ou no adaptador, com os controles no iPhone. Fora do jogo, o iOS espelha o iPhone.',
      modeTitle: 'Formato da imagem na tela externa',
      modeAutomatic: 'Automático',
      modeFit: 'Ajustar à tela',
      modeFill: 'Preencher a tela',
      modeOriginal: 'Formato original',
      modeAutomaticHelp:
          'Os jogos mantêm a imagem inteira, como em “Ajustar à tela”.',
      modeFitHelp:
          'A imagem inteira é exibida; faixas aparecem apenas se os formatos forem diferentes.',
      modeFillHelp: 'Uma imagem 4:3 é ampliada até a largura da tela.',
      modeOriginalHelp: 'O formato do iPhone, centralizado na altura da tela.',
      fillCrops:
          'Preencher a tela corta a parte superior e inferior da imagem.',
      noExternalScreen: 'Nenhuma tela externa conectada.',
      externalScreen: 'Tela externa: {width}×{height}',
      gameOnExternal: 'O jogo é exibido na tela externa.',
      mirroringOff:
          'Desativado: o iOS espelha a tela do iPhone, com suas faixas.',
      unsupportedEngine:
          'O motor deste jogo não usa a tela externa; o iOS espelha o iPhone.',
      mirroringOutsideGames:
          'Fora do jogo, o iOS espelha a interface do NeoStation do iPhone.',
      unavailable: 'Indisponível nesta versão do NeoStation.',
      saveFailed: 'Não foi possível salvar o ajuste.',
      technicalCode: 'Código técnico: {code}',
    },
    'fr': {
      title: 'AirPlay et écran externe',
      description:
          'Pendant un jeu, NeoStation affiche le jeu en plein écran sur le téléviseur ou l’adaptateur, les commandes restant sur l’iPhone. Hors jeu, iOS recopie l’iPhone.',
      modeTitle: 'Format sur l’écran externe',
      modeAutomatic: 'Automatique',
      modeFit: 'Adapter à l’écran',
      modeFill: 'Remplir l’écran',
      modeOriginal: 'Format d’origine',
      modeAutomaticHelp:
          'Les jeux gardent leur image entière, comme avec « Adapter à l’écran ».',
      modeFitHelp:
          'L’image entière est affichée ; des bandes n’apparaissent que si les formats diffèrent.',
      modeFillHelp: 'Une image 4:3 est agrandie à la largeur de l’écran.',
      modeOriginalHelp:
          'Le format de l’iPhone, centré à la hauteur de l’écran.',
      fillCrops: 'Remplir l’écran coupe le haut et le bas de l’image.',
      noExternalScreen: 'Aucun écran externe connecté.',
      externalScreen: 'Écran externe : {width}×{height}',
      gameOnExternal: 'Le jeu est affiché sur l’écran externe.',
      mirroringOff:
          'Désactivé : iOS recopie l’écran de l’iPhone, avec ses bandes.',
      unsupportedEngine:
          'Le moteur de ce jeu n’utilise pas l’écran externe ; iOS recopie l’iPhone.',
      mirroringOutsideGames:
          'Hors jeu, iOS recopie l’interface NeoStation de l’iPhone.',
      unavailable: 'Non disponible dans cette version de NeoStation.',
      saveFailed: 'Le réglage n’a pas pu être enregistré.',
      technicalCode: 'Code technique : {code}',
    },
    'de': {
      title: 'AirPlay und externer Bildschirm',
      description:
          'Während eines Spiels zeigt NeoStation das Spiel im Vollbild auf dem Fernseher oder Adapter, die Steuerung bleibt auf dem iPhone. Außerhalb eines Spiels spiegelt iOS das iPhone.',
      modeTitle: 'Bildformat auf dem externen Bildschirm',
      modeAutomatic: 'Automatisch',
      modeFit: 'An Bildschirm anpassen',
      modeFill: 'Bildschirm füllen',
      modeOriginal: 'Originalformat',
      modeAutomaticHelp:
          'Spiele behalten ihr ganzes Bild, wie bei „An Bildschirm anpassen“.',
      modeFitHelp:
          'Das ganze Bild wird gezeigt; Balken erscheinen nur bei unterschiedlichen Formaten.',
      modeFillHelp: 'Ein 4:3-Bild wird auf die Bildschirmbreite vergrößert.',
      modeOriginalHelp: 'Das iPhone-Format, zentriert auf die Bildschirmhöhe.',
      fillCrops:
          '„Bildschirm füllen“ schneidet oben und unten einen Teil des Bildes ab.',
      noExternalScreen: 'Kein externer Bildschirm verbunden.',
      externalScreen: 'Externer Bildschirm: {width}×{height}',
      gameOnExternal: 'Das Spiel wird auf dem externen Bildschirm gezeigt.',
      mirroringOff:
          'Aus: iOS spiegelt den iPhone-Bildschirm mit seinen Balken.',
      unsupportedEngine:
          'Die Engine dieses Spiels nutzt den externen Bildschirm nicht; iOS spiegelt das iPhone.',
      mirroringOutsideGames:
          'Außerhalb eines Spiels spiegelt iOS die NeoStation-Oberfläche des iPhone.',
      unavailable: 'In dieser NeoStation-Version nicht verfügbar.',
      saveFailed: 'Die Einstellung konnte nicht gespeichert werden.',
      technicalCode: 'Technischer Code: {code}',
    },
    'it': {
      title: 'AirPlay e schermo esterno',
      description:
          'Durante una partita, NeoStation mostra il gioco a schermo intero sul televisore o sull’adattatore, con i comandi sull’iPhone. Fuori dal gioco, iOS duplica l’iPhone.',
      modeTitle: 'Formato dell’immagine sullo schermo esterno',
      modeAutomatic: 'Automatico',
      modeFit: 'Adatta allo schermo',
      modeFill: 'Riempi lo schermo',
      modeOriginal: 'Formato originale',
      modeAutomaticHelp:
          'I giochi mantengono l’immagine intera, come con «Adatta allo schermo».',
      modeFitHelp:
          'Viene mostrata l’immagine intera; le bande compaiono solo se i formati sono diversi.',
      modeFillHelp:
          'Un’immagine 4:3 viene ingrandita alla larghezza dello schermo.',
      modeOriginalHelp:
          'Il formato dell’iPhone, centrato all’altezza dello schermo.',
      fillCrops:
          'Riempi lo schermo taglia la parte superiore e inferiore dell’immagine.',
      noExternalScreen: 'Nessuno schermo esterno collegato.',
      externalScreen: 'Schermo esterno: {width}×{height}',
      gameOnExternal: 'Il gioco è mostrato sullo schermo esterno.',
      mirroringOff:
          'Disattivato: iOS duplica lo schermo dell’iPhone, con le sue bande.',
      unsupportedEngine:
          'Il motore di questo gioco non usa lo schermo esterno; iOS duplica l’iPhone.',
      mirroringOutsideGames:
          'Fuori dal gioco, iOS duplica l’interfaccia di NeoStation dell’iPhone.',
      unavailable: 'Non disponibile in questa versione di NeoStation.',
      saveFailed: 'Impossibile salvare l’impostazione.',
      technicalCode: 'Codice tecnico: {code}',
    },
    'id': {
      title: 'AirPlay dan layar eksternal',
      description:
          'Selama bermain, NeoStation menampilkan game dalam layar penuh di TV atau adaptor, dengan kontrol tetap di iPhone. Di luar game, iOS mencerminkan iPhone.',
      modeTitle: 'Format gambar di layar eksternal',
      modeAutomatic: 'Otomatis',
      modeFit: 'Sesuaikan dengan layar',
      modeFill: 'Penuhi layar',
      modeOriginal: 'Format asli',
      modeAutomaticHelp:
          'Game mempertahankan gambar utuhnya, seperti pada “Sesuaikan dengan layar”.',
      modeFitHelp:
          'Seluruh gambar ditampilkan; bilah hanya muncul jika formatnya berbeda.',
      modeFillHelp: 'Gambar 4:3 diperbesar hingga selebar layar.',
      modeOriginalHelp: 'Format iPhone, di tengah setinggi layar.',
      fillCrops: 'Penuhi layar memotong bagian atas dan bawah gambar.',
      noExternalScreen: 'Tidak ada layar eksternal yang terhubung.',
      externalScreen: 'Layar eksternal: {width}×{height}',
      gameOnExternal: 'Game ditampilkan di layar eksternal.',
      mirroringOff: 'Nonaktif: iOS mencerminkan layar iPhone beserta bilahnya.',
      unsupportedEngine:
          'Mesin game ini tidak menggunakan layar eksternal; iOS mencerminkan iPhone.',
      mirroringOutsideGames:
          'Di luar game, iOS mencerminkan antarmuka NeoStation dari iPhone.',
      unavailable: 'Tidak tersedia di versi NeoStation ini.',
      saveFailed: 'Pengaturan tidak dapat disimpan.',
      technicalCode: 'Kode teknis: {code}',
    },
    'ja': {
      title: 'AirPlay と外部ディスプレイ',
      description:
          'ゲーム中は、NeoStation がテレビやアダプタにゲームを全画面で表示し、操作は iPhone に残ります。ゲーム中以外は iOS が iPhone をミラーリングします。',
      modeTitle: '外部ディスプレイでの画面フォーマット',
      modeAutomatic: '自動',
      modeFit: '画面に合わせる',
      modeFill: '画面いっぱいに表示',
      modeOriginal: '元のフォーマット',
      modeAutomaticHelp: '「画面に合わせる」と同じく、ゲームは映像全体を保ちます。',
      modeFitHelp: '映像全体を表示します。帯はフォーマットが異なる場合にのみ現れます。',
      modeFillHelp: '4:3 の映像を画面の幅まで拡大します。',
      modeOriginalHelp: 'iPhone のフォーマットを画面の高さに合わせて中央に表示します。',
      fillCrops: '「画面いっぱいに表示」では映像の上下が切れます。',
      noExternalScreen: '外部ディスプレイは接続されていません。',
      externalScreen: '外部ディスプレイ：{width}×{height}',
      gameOnExternal: 'ゲームは外部ディスプレイに表示されています。',
      mirroringOff: 'オフ：iOS が iPhone の画面を帯付きでミラーリングします。',
      unsupportedEngine: 'このゲームのエンジンは外部ディスプレイを使用しません。iOS が iPhone をミラーリングします。',
      mirroringOutsideGames: 'ゲーム中以外は、iOS が iPhone の NeoStation 画面をミラーリングします。',
      unavailable: 'このバージョンの NeoStation では利用できません。',
      saveFailed: '設定を保存できませんでした。',
      technicalCode: '技術コード：{code}',
    },
    'ko': {
      title: 'AirPlay 및 외부 화면',
      description:
          '게임 중에는 NeoStation이 TV나 어댑터에 게임을 전체 화면으로 표시하고 조작은 iPhone에 남습니다. 게임 중이 아닐 때는 iOS가 iPhone을 미러링합니다.',
      modeTitle: '외부 화면의 화면 형식',
      modeAutomatic: '자동',
      modeFit: '화면에 맞춤',
      modeFill: '화면 채우기',
      modeOriginal: '원본 형식',
      modeAutomaticHelp: '\'화면에 맞춤\'과 같이 게임은 전체 영상을 유지합니다.',
      modeFitHelp: '전체 영상을 표시합니다. 띠는 형식이 다를 때만 나타납니다.',
      modeFillHelp: '4:3 영상을 화면 너비까지 확대합니다.',
      modeOriginalHelp: 'iPhone 형식을 화면 높이에 맞춰 가운데에 표시합니다.',
      fillCrops: '화면 채우기는 영상의 위아래를 잘라냅니다.',
      noExternalScreen: '연결된 외부 화면이 없습니다.',
      externalScreen: '외부 화면: {width}×{height}',
      gameOnExternal: '게임이 외부 화면에 표시됩니다.',
      mirroringOff: '꺼짐: iOS가 iPhone 화면을 띠와 함께 미러링합니다.',
      unsupportedEngine: '이 게임의 엔진은 외부 화면을 사용하지 않습니다. iOS가 iPhone을 미러링합니다.',
      mirroringOutsideGames: '게임 중이 아닐 때는 iOS가 iPhone의 NeoStation 화면을 미러링합니다.',
      unavailable: '이 버전의 NeoStation에서는 사용할 수 없습니다.',
      saveFailed: '설정을 저장할 수 없습니다.',
      technicalCode: '기술 코드: {code}',
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
