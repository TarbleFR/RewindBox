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
  static const menuOnTv = 'menuOnTv';
  static const menuOnTvHelp = 'menuOnTvHelp';
  static const noExternalScreen = 'noExternalScreen';
  static const externalScreen = 'externalScreen';
  static const gameOnExternal = 'gameOnExternal';
  static const mirroringOff = 'mirroringOff';
  static const unsupportedEngine = 'unsupportedEngine';
  static const unavailable = 'unavailable';
  static const saveFailed = 'saveFailed';
  static const technicalCode = 'technicalCode';

  static const Map<String, Map<String, String>> values = {
    'en': {
      title: 'AirPlay and external screen',
      description:
          'NeoStation draws its own picture on the TV or the adapter instead of mirroring the iPhone, so there are no black bars.',
      modeTitle: 'Picture format on the external screen',
      modeAutomatic: 'Automatic',
      modeFit: 'Fit to screen',
      modeFill: 'Fill the screen',
      modeOriginal: 'Original format',
      modeAutomaticHelp:
          'The menu fills the screen; games keep their whole image.',
      modeFitHelp:
          'The whole image is shown; bars appear only when the formats differ.',
      modeFillHelp: 'A 4:3 image is zoomed to the width of the screen.',
      modeOriginalHelp:
          'The iPhone format, centred at the height of the screen.',
      fillCrops: 'Fill the screen cuts the top and bottom of the image.',
      menuOnTv: 'Show the menu on the TV',
      menuOnTvHelp:
          'Outside a game, the TV shows the NeoStation menu view instead of a copy of the iPhone.',
      noExternalScreen: 'No external screen connected.',
      externalScreen: 'External screen: {width}×{height}',
      gameOnExternal: 'The game is shown on the external screen.',
      mirroringOff: 'Off: iOS mirrors the iPhone screen, with its bars.',
      unsupportedEngine:
          'This game’s engine does not use the external screen; iOS mirrors the iPhone.',
      unavailable: 'Not available in this version of NeoStation.',
      saveFailed: 'The setting could not be saved.',
      technicalCode: 'Technical code: {code}',
    },
    'es': {
      title: 'AirPlay y pantalla externa',
      description:
          'NeoStation muestra su propia imagen en el televisor o el adaptador en lugar de duplicar el iPhone: sin bandas negras.',
      modeTitle: 'Formato de imagen en la pantalla externa',
      modeAutomatic: 'Automático',
      modeFit: 'Ajustar a la pantalla',
      modeFill: 'Llenar la pantalla',
      modeOriginal: 'Formato original',
      modeAutomaticHelp:
          'El menú ocupa toda la pantalla; los juegos conservan la imagen completa.',
      modeFitHelp:
          'Se muestra la imagen completa; solo aparecen bandas si los formatos difieren.',
      modeFillHelp: 'Una imagen 4:3 se amplía al ancho de la pantalla.',
      modeOriginalHelp:
          'El formato del iPhone, centrado a la altura de la pantalla.',
      fillCrops:
          'Llenar la pantalla recorta la parte superior e inferior de la imagen.',
      menuOnTv: 'Mostrar el menú en el televisor',
      menuOnTvHelp:
          'Fuera del juego, el televisor muestra la vista de menú de NeoStation en lugar de una copia del iPhone.',
      noExternalScreen: 'No hay ninguna pantalla externa conectada.',
      externalScreen: 'Pantalla externa: {width}×{height}',
      gameOnExternal: 'El juego se muestra en la pantalla externa.',
      mirroringOff:
          'Desactivado: iOS duplica la pantalla del iPhone, con sus bandas.',
      unsupportedEngine:
          'El motor de este juego no usa la pantalla externa; iOS duplica el iPhone.',
      unavailable: 'No disponible en esta versión de NeoStation.',
      saveFailed: 'No se pudo guardar el ajuste.',
      technicalCode: 'Código técnico: {code}',
    },
    'ru': {
      title: 'AirPlay и внешний экран',
      description:
          'NeoStation выводит собственное изображение на телевизор или адаптер вместо повтора экрана iPhone — без чёрных полос.',
      modeTitle: 'Формат изображения на внешнем экране',
      modeAutomatic: 'Автоматически',
      modeFit: 'По размеру экрана',
      modeFill: 'Заполнить экран',
      modeOriginal: 'Исходный формат',
      modeAutomaticHelp:
          'Меню занимает весь экран; игры сохраняют полное изображение.',
      modeFitHelp:
          'Показывается всё изображение; полосы появляются, только если форматы различаются.',
      modeFillHelp: 'Изображение 4:3 увеличивается до ширины экрана.',
      modeOriginalHelp: 'Формат iPhone, по центру и по высоте экрана.',
      fillCrops: 'Режим «Заполнить экран» обрезает верх и низ изображения.',
      menuOnTv: 'Показывать меню на телевизоре',
      menuOnTvHelp:
          'Вне игры телевизор показывает вид меню NeoStation вместо копии экрана iPhone.',
      noExternalScreen: 'Внешний экран не подключён.',
      externalScreen: 'Внешний экран: {width}×{height}',
      gameOnExternal: 'Игра выводится на внешний экран.',
      mirroringOff: 'Выключено: iOS повторяет экран iPhone вместе с полосами.',
      unsupportedEngine:
          'Движок этой игры не использует внешний экран; iOS повторяет экран iPhone.',
      unavailable: 'Недоступно в этой версии NeoStation.',
      saveFailed: 'Не удалось сохранить настройку.',
      technicalCode: 'Технический код: {code}',
    },
    'zh': {
      title: 'AirPlay 与外接屏幕',
      description: 'NeoStation 在电视或转接器上显示自己的画面，而不是镜像 iPhone，因此没有黑边。',
      modeTitle: '外接屏幕上的画面格式',
      modeAutomatic: '自动',
      modeFit: '适应屏幕',
      modeFill: '填满屏幕',
      modeOriginal: '原始格式',
      modeAutomaticHelp: '菜单占满屏幕；游戏保留完整画面。',
      modeFitHelp: '显示完整画面；仅在比例不同时出现黑边。',
      modeFillHelp: '4:3 画面放大到屏幕宽度。',
      modeOriginalHelp: 'iPhone 的格式，按屏幕高度居中显示。',
      fillCrops: '“填满屏幕”会裁掉画面的顶部和底部。',
      menuOnTv: '在电视上显示菜单',
      menuOnTvHelp: '未进行游戏时，电视显示 NeoStation 的菜单视图，而不是 iPhone 的镜像。',
      noExternalScreen: '未连接外接屏幕。',
      externalScreen: '外接屏幕：{width}×{height}',
      gameOnExternal: '游戏显示在外接屏幕上。',
      mirroringOff: '已关闭：iOS 镜像 iPhone 屏幕，带有黑边。',
      unsupportedEngine: '此游戏的引擎不使用外接屏幕；iOS 镜像 iPhone。',
      unavailable: '此版本的 NeoStation 不支持。',
      saveFailed: '无法保存该设置。',
      technicalCode: '技术代码：{code}',
    },
    'zh_Hant': {
      title: 'AirPlay 與外接螢幕',
      description: 'NeoStation 在電視或轉接器上顯示自己的畫面，而不是鏡像輸出 iPhone，因此沒有黑邊。',
      modeTitle: '外接螢幕上的畫面格式',
      modeAutomatic: '自動',
      modeFit: '符合螢幕',
      modeFill: '填滿螢幕',
      modeOriginal: '原始格式',
      modeAutomaticHelp: '選單佔滿螢幕；遊戲保留完整畫面。',
      modeFitHelp: '顯示完整畫面；僅在比例不同時出現黑邊。',
      modeFillHelp: '4:3 畫面放大至螢幕寬度。',
      modeOriginalHelp: 'iPhone 的格式，依螢幕高度置中顯示。',
      fillCrops: '「填滿螢幕」會裁掉畫面的頂部和底部。',
      menuOnTv: '在電視上顯示選單',
      menuOnTvHelp: '未進行遊戲時，電視顯示 NeoStation 的選單畫面，而不是 iPhone 的鏡像輸出。',
      noExternalScreen: '未連接外接螢幕。',
      externalScreen: '外接螢幕：{width}×{height}',
      gameOnExternal: '遊戲顯示在外接螢幕上。',
      mirroringOff: '已關閉：iOS 鏡像輸出 iPhone 螢幕，帶有黑邊。',
      unsupportedEngine: '此遊戲的引擎不使用外接螢幕；iOS 鏡像輸出 iPhone。',
      unavailable: '此版本的 NeoStation 不支援。',
      saveFailed: '無法儲存此設定。',
      technicalCode: '技術代碼：{code}',
    },
    'pt': {
      title: 'AirPlay e tela externa',
      description:
          'O NeoStation mostra sua própria imagem na TV ou no adaptador em vez de espelhar o iPhone: sem faixas pretas.',
      modeTitle: 'Formato da imagem na tela externa',
      modeAutomatic: 'Automático',
      modeFit: 'Ajustar à tela',
      modeFill: 'Preencher a tela',
      modeOriginal: 'Formato original',
      modeAutomaticHelp:
          'O menu ocupa toda a tela; os jogos mantêm a imagem inteira.',
      modeFitHelp:
          'A imagem inteira é exibida; faixas aparecem apenas se os formatos forem diferentes.',
      modeFillHelp: 'Uma imagem 4:3 é ampliada até a largura da tela.',
      modeOriginalHelp: 'O formato do iPhone, centralizado na altura da tela.',
      fillCrops:
          'Preencher a tela corta a parte superior e inferior da imagem.',
      menuOnTv: 'Mostrar o menu na TV',
      menuOnTvHelp:
          'Fora do jogo, a TV mostra a visualização de menu do NeoStation em vez de uma cópia do iPhone.',
      noExternalScreen: 'Nenhuma tela externa conectada.',
      externalScreen: 'Tela externa: {width}×{height}',
      gameOnExternal: 'O jogo é exibido na tela externa.',
      mirroringOff:
          'Desativado: o iOS espelha a tela do iPhone, com suas faixas.',
      unsupportedEngine:
          'O motor deste jogo não usa a tela externa; o iOS espelha o iPhone.',
      unavailable: 'Indisponível nesta versão do NeoStation.',
      saveFailed: 'Não foi possível salvar o ajuste.',
      technicalCode: 'Código técnico: {code}',
    },
    'fr': {
      title: 'AirPlay et écran externe',
      description:
          'NeoStation affiche sa propre image sur le téléviseur ou l’adaptateur au lieu de recopier l’iPhone : plus de bandes noires.',
      modeTitle: 'Format sur l’écran externe',
      modeAutomatic: 'Automatique',
      modeFit: 'Adapter à l’écran',
      modeFill: 'Remplir l’écran',
      modeOriginal: 'Format d’origine',
      modeAutomaticHelp:
          'Le menu occupe tout l’écran ; les jeux gardent leur image entière.',
      modeFitHelp:
          'L’image entière est affichée ; des bandes n’apparaissent que si les formats diffèrent.',
      modeFillHelp: 'Une image 4:3 est agrandie à la largeur de l’écran.',
      modeOriginalHelp: 'Le format de l’iPhone, centré à la hauteur de l’écran.',
      fillCrops: 'Remplir l’écran coupe le haut et le bas de l’image.',
      menuOnTv: 'Afficher le menu sur le téléviseur',
      menuOnTvHelp:
          'Hors jeu, le téléviseur affiche la vue menu de NeoStation au lieu d’une copie de l’iPhone.',
      noExternalScreen: 'Aucun écran externe connecté.',
      externalScreen: 'Écran externe : {width}×{height}',
      gameOnExternal: 'Le jeu est affiché sur l’écran externe.',
      mirroringOff:
          'Désactivé : iOS recopie l’écran de l’iPhone, avec ses bandes.',
      unsupportedEngine:
          'Le moteur de ce jeu n’utilise pas l’écran externe ; iOS recopie l’iPhone.',
      unavailable: 'Non disponible dans cette version de NeoStation.',
      saveFailed: 'Le réglage n’a pas pu être enregistré.',
      technicalCode: 'Code technique : {code}',
    },
    'de': {
      title: 'AirPlay und externer Bildschirm',
      description:
          'NeoStation zeigt sein eigenes Bild auf dem Fernseher oder Adapter, statt das iPhone zu spiegeln – ohne schwarze Balken.',
      modeTitle: 'Bildformat auf dem externen Bildschirm',
      modeAutomatic: 'Automatisch',
      modeFit: 'An Bildschirm anpassen',
      modeFill: 'Bildschirm füllen',
      modeOriginal: 'Originalformat',
      modeAutomaticHelp:
          'Das Menü füllt den Bildschirm; Spiele behalten ihr ganzes Bild.',
      modeFitHelp:
          'Das ganze Bild wird gezeigt; Balken erscheinen nur bei unterschiedlichen Formaten.',
      modeFillHelp: 'Ein 4:3-Bild wird auf die Bildschirmbreite vergrößert.',
      modeOriginalHelp: 'Das iPhone-Format, zentriert auf die Bildschirmhöhe.',
      fillCrops:
          '„Bildschirm füllen“ schneidet oben und unten einen Teil des Bildes ab.',
      menuOnTv: 'Menü auf dem Fernseher anzeigen',
      menuOnTvHelp:
          'Außerhalb eines Spiels zeigt der Fernseher die Menüansicht von NeoStation statt einer Kopie des iPhone.',
      noExternalScreen: 'Kein externer Bildschirm verbunden.',
      externalScreen: 'Externer Bildschirm: {width}×{height}',
      gameOnExternal: 'Das Spiel wird auf dem externen Bildschirm gezeigt.',
      mirroringOff: 'Aus: iOS spiegelt den iPhone-Bildschirm mit seinen Balken.',
      unsupportedEngine:
          'Die Engine dieses Spiels nutzt den externen Bildschirm nicht; iOS spiegelt das iPhone.',
      unavailable: 'In dieser NeoStation-Version nicht verfügbar.',
      saveFailed: 'Die Einstellung konnte nicht gespeichert werden.',
      technicalCode: 'Technischer Code: {code}',
    },
    'it': {
      title: 'AirPlay e schermo esterno',
      description:
          'NeoStation mostra la propria immagine sul televisore o sull’adattatore invece di duplicare l’iPhone: niente bande nere.',
      modeTitle: 'Formato dell’immagine sullo schermo esterno',
      modeAutomatic: 'Automatico',
      modeFit: 'Adatta allo schermo',
      modeFill: 'Riempi lo schermo',
      modeOriginal: 'Formato originale',
      modeAutomaticHelp:
          'Il menu occupa tutto lo schermo; i giochi mantengono l’immagine intera.',
      modeFitHelp:
          'Viene mostrata l’immagine intera; le bande compaiono solo se i formati sono diversi.',
      modeFillHelp:
          'Un’immagine 4:3 viene ingrandita alla larghezza dello schermo.',
      modeOriginalHelp:
          'Il formato dell’iPhone, centrato all’altezza dello schermo.',
      fillCrops:
          'Riempi lo schermo taglia la parte superiore e inferiore dell’immagine.',
      menuOnTv: 'Mostra il menu sul televisore',
      menuOnTvHelp:
          'Fuori dal gioco, il televisore mostra la vista menu di NeoStation invece di una copia dell’iPhone.',
      noExternalScreen: 'Nessuno schermo esterno collegato.',
      externalScreen: 'Schermo esterno: {width}×{height}',
      gameOnExternal: 'Il gioco è mostrato sullo schermo esterno.',
      mirroringOff:
          'Disattivato: iOS duplica lo schermo dell’iPhone, con le sue bande.',
      unsupportedEngine:
          'Il motore di questo gioco non usa lo schermo esterno; iOS duplica l’iPhone.',
      unavailable: 'Non disponibile in questa versione di NeoStation.',
      saveFailed: 'Impossibile salvare l’impostazione.',
      technicalCode: 'Codice tecnico: {code}',
    },
    'id': {
      title: 'AirPlay dan layar eksternal',
      description:
          'NeoStation menampilkan gambarnya sendiri di TV atau adaptor, bukan mencerminkan iPhone, sehingga tidak ada bilah hitam.',
      modeTitle: 'Format gambar di layar eksternal',
      modeAutomatic: 'Otomatis',
      modeFit: 'Sesuaikan dengan layar',
      modeFill: 'Penuhi layar',
      modeOriginal: 'Format asli',
      modeAutomaticHelp:
          'Menu memenuhi layar; game mempertahankan gambar utuhnya.',
      modeFitHelp:
          'Seluruh gambar ditampilkan; bilah hanya muncul jika formatnya berbeda.',
      modeFillHelp: 'Gambar 4:3 diperbesar hingga selebar layar.',
      modeOriginalHelp: 'Format iPhone, di tengah setinggi layar.',
      fillCrops: 'Penuhi layar memotong bagian atas dan bawah gambar.',
      menuOnTv: 'Tampilkan menu di TV',
      menuOnTvHelp:
          'Di luar game, TV menampilkan tampilan menu NeoStation, bukan salinan iPhone.',
      noExternalScreen: 'Tidak ada layar eksternal yang terhubung.',
      externalScreen: 'Layar eksternal: {width}×{height}',
      gameOnExternal: 'Game ditampilkan di layar eksternal.',
      mirroringOff: 'Nonaktif: iOS mencerminkan layar iPhone beserta bilahnya.',
      unsupportedEngine:
          'Mesin game ini tidak menggunakan layar eksternal; iOS mencerminkan iPhone.',
      unavailable: 'Tidak tersedia di versi NeoStation ini.',
      saveFailed: 'Pengaturan tidak dapat disimpan.',
      technicalCode: 'Kode teknis: {code}',
    },
    'ja': {
      title: 'AirPlay と外部ディスプレイ',
      description:
          'NeoStation は iPhone をミラーリングする代わりに、テレビやアダプタに独自の画面を表示します。黒い帯は出ません。',
      modeTitle: '外部ディスプレイでの画面フォーマット',
      modeAutomatic: '自動',
      modeFit: '画面に合わせる',
      modeFill: '画面いっぱいに表示',
      modeOriginal: '元のフォーマット',
      modeAutomaticHelp: 'メニューは画面全体に表示され、ゲームは映像全体を保ちます。',
      modeFitHelp: '映像全体を表示します。帯はフォーマットが異なる場合にのみ現れます。',
      modeFillHelp: '4:3 の映像を画面の幅まで拡大します。',
      modeOriginalHelp: 'iPhone のフォーマットを画面の高さに合わせて中央に表示します。',
      fillCrops: '「画面いっぱいに表示」では映像の上下が切れます。',
      menuOnTv: 'テレビにメニューを表示',
      menuOnTvHelp:
          'ゲーム中以外は、iPhone のコピーではなく NeoStation のメニュー画面をテレビに表示します。',
      noExternalScreen: '外部ディスプレイは接続されていません。',
      externalScreen: '外部ディスプレイ：{width}×{height}',
      gameOnExternal: 'ゲームは外部ディスプレイに表示されています。',
      mirroringOff: 'オフ：iOS が iPhone の画面を帯付きでミラーリングします。',
      unsupportedEngine:
          'このゲームのエンジンは外部ディスプレイを使用しません。iOS が iPhone をミラーリングします。',
      unavailable: 'このバージョンの NeoStation では利用できません。',
      saveFailed: '設定を保存できませんでした。',
      technicalCode: '技術コード：{code}',
    },
    'ko': {
      title: 'AirPlay 및 외부 화면',
      description:
          'NeoStation이 iPhone을 미러링하는 대신 TV나 어댑터에 자체 화면을 표시하므로 검은 띠가 생기지 않습니다.',
      modeTitle: '외부 화면의 화면 형식',
      modeAutomatic: '자동',
      modeFit: '화면에 맞춤',
      modeFill: '화면 채우기',
      modeOriginal: '원본 형식',
      modeAutomaticHelp: '메뉴는 화면 전체를 채우고 게임은 전체 영상을 유지합니다.',
      modeFitHelp: '전체 영상을 표시합니다. 띠는 형식이 다를 때만 나타납니다.',
      modeFillHelp: '4:3 영상을 화면 너비까지 확대합니다.',
      modeOriginalHelp: 'iPhone 형식을 화면 높이에 맞춰 가운데에 표시합니다.',
      fillCrops: '화면 채우기는 영상의 위아래를 잘라냅니다.',
      menuOnTv: 'TV에 메뉴 표시',
      menuOnTvHelp: '게임 중이 아닐 때 TV에 iPhone 복사본 대신 NeoStation 메뉴 화면을 표시합니다.',
      noExternalScreen: '연결된 외부 화면이 없습니다.',
      externalScreen: '외부 화면: {width}×{height}',
      gameOnExternal: '게임이 외부 화면에 표시됩니다.',
      mirroringOff: '꺼짐: iOS가 iPhone 화면을 띠와 함께 미러링합니다.',
      unsupportedEngine:
          '이 게임의 엔진은 외부 화면을 사용하지 않습니다. iOS가 iPhone을 미러링합니다.',
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
