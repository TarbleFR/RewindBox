import 'package:flutter/widgets.dart';

/// Texts of Settings › General › "120 Hz interface" (Build 440) in
/// RewindBox's twelve languages. Raw technical codes (hook status) are shown
/// separately through [technicalCode] and never translated.
abstract final class UiRefreshRateLocale {
  static const title = 'title';
  static const description = 'description';
  static const unavailableScreen = 'unavailableScreen';
  static const unavailableEngine = 'unavailableEngine';
  static const restartRequired = 'restartRequired';
  static const limitedLowPower = 'limitedLowPower';
  static const limitedThermal = 'limitedThermal';
  static const measured = 'measured';
  static const measuredAfterGame = 'measuredAfterGame';
  static const notMeasured = 'notMeasured';
  static const measureAction = 'measureAction';
  static const measuring = 'measuring';
  static const measureFailed = 'measureFailed';
  static const measureHint = 'measureHint';
  static const saveFailed = 'saveFailed';
  static const technicalCode = 'technicalCode';

  static const Map<String, Map<String, String>> values = {
    'en': {
      title: '120 Hz interface',
      description: 'Makes menus and scrolling smoother on compatible screens.',
      unavailableScreen: 'Not available on this screen (maximum {hz} Hz).',
      unavailableEngine: 'Not available in this version of RewindBox.',
      restartRequired:
          'Takes effect the next time RewindBox opens, after closing it from the app switcher.',
      limitedLowPower: 'Limited to 60 Hz by Low Power Mode.',
      limitedThermal: 'Limited by the device temperature.',
      measured: 'Measured rate: {hz} Hz',
      measuredAfterGame: 'After the last game: {hz} Hz',
      notMeasured: 'Not measured yet — scroll a list or tap Measure.',
      measureAction: 'Measure',
      measuring: 'Measuring…',
      measureFailed:
          'Could not measure: the interface did not draw enough frames.',
      measureHint: 'Measure the interface refresh rate',
      saveFailed: 'The setting could not be saved.',
      technicalCode: 'Technical code: {code}',
    },
    'es': {
      title: 'Interfaz a 120 Hz',
      description:
          'Mejora la fluidez de los menús y del desplazamiento en pantallas compatibles.',
      unavailableScreen: 'No disponible en esta pantalla (máximo {hz} Hz).',
      unavailableEngine: 'No disponible en esta versión de RewindBox.',
      restartRequired:
          'Se aplicará la próxima vez que abras RewindBox, después de cerrarla desde el selector de apps.',
      limitedLowPower: 'Limitada a 60 Hz por el modo de bajo consumo.',
      limitedThermal: 'Limitada por la temperatura del dispositivo.',
      measured: 'Frecuencia medida: {hz} Hz',
      measuredAfterGame: 'Después del último juego: {hz} Hz',
      notMeasured: 'Aún sin medir: desplázate por una lista o toca Medir.',
      measureAction: 'Medir',
      measuring: 'Midiendo…',
      measureFailed:
          'No se pudo medir: la interfaz no dibujó suficientes imágenes.',
      measureHint: 'Medir la frecuencia de la interfaz',
      saveFailed: 'No se pudo guardar el ajuste.',
      technicalCode: 'Código técnico: {code}',
    },
    'ru': {
      title: 'Интерфейс 120 Гц',
      description: 'Делает меню и прокрутку плавнее на совместимых экранах.',
      unavailableScreen: 'Недоступно на этом экране (максимум {hz} Гц).',
      unavailableEngine: 'Недоступно в этой версии RewindBox.',
      restartRequired:
          'Вступит в силу при следующем открытии RewindBox после закрытия приложения в переключателе приложений.',
      limitedLowPower: 'Ограничено до 60 Гц режимом энергосбережения.',
      limitedThermal: 'Ограничено из-за температуры устройства.',
      measured: 'Измеренная частота: {hz} Гц',
      measuredAfterGame: 'После последней игры: {hz} Гц',
      notMeasured:
          'Ещё не измерено — прокрутите список или нажмите «Измерить».',
      measureAction: 'Измерить',
      measuring: 'Идёт измерение…',
      measureFailed:
          'Не удалось измерить: интерфейс отрисовал слишком мало кадров.',
      measureHint: 'Измерить частоту обновления интерфейса',
      saveFailed: 'Не удалось сохранить настройку.',
      technicalCode: 'Технический код: {code}',
    },
    'zh': {
      title: '120 Hz 界面',
      description: '在兼容的屏幕上让菜单和滚动更流畅。',
      unavailableScreen: '此屏幕不支持（最高 {hz} Hz）。',
      unavailableEngine: '此版本的 RewindBox 不支持。',
      restartRequired: '在应用切换器中关闭 RewindBox 后，下次打开时生效。',
      limitedLowPower: '低电量模式将其限制为 60 Hz。',
      limitedThermal: '因设备温度而受限。',
      measured: '实测刷新率：{hz} Hz',
      measuredAfterGame: '上次游戏后：{hz} Hz',
      notMeasured: '尚未测量——请滚动列表或轻点“测量”。',
      measureAction: '测量',
      measuring: '正在测量…',
      measureFailed: '无法测量：界面绘制的帧数不足。',
      measureHint: '测量界面刷新率',
      saveFailed: '无法保存该设置。',
      technicalCode: '技术代码：{code}',
    },
    'zh_Hant': {
      title: '120 Hz 介面',
      description: '在相容的螢幕上讓選單與捲動更流暢。',
      unavailableScreen: '此螢幕不支援（最高 {hz} Hz）。',
      unavailableEngine: '此版本的 RewindBox 不支援。',
      restartRequired: '在 App 切換器中關閉 RewindBox 後，下次開啟時生效。',
      limitedLowPower: '低耗電模式將其限制為 60 Hz。',
      limitedThermal: '因裝置溫度而受限。',
      measured: '實測更新率：{hz} Hz',
      measuredAfterGame: '上次遊戲後：{hz} Hz',
      notMeasured: '尚未測量——請捲動列表或點一下「測量」。',
      measureAction: '測量',
      measuring: '正在測量…',
      measureFailed: '無法測量：介面繪製的影格不足。',
      measureHint: '測量介面更新率',
      saveFailed: '無法儲存此設定。',
      technicalCode: '技術代碼：{code}',
    },
    'pt': {
      title: 'Interface a 120 Hz',
      description:
          'Melhora a fluidez dos menus e da rolagem em telas compatíveis.',
      unavailableScreen: 'Indisponível nesta tela (máximo de {hz} Hz).',
      unavailableEngine: 'Indisponível nesta versão do RewindBox.',
      restartRequired:
          'Será aplicado na próxima vez que o RewindBox for aberto, depois de fechá-lo no seletor de apps.',
      limitedLowPower: 'Limitada a 60 Hz pelo Modo de Pouca Energia.',
      limitedThermal: 'Limitada pela temperatura do dispositivo.',
      measured: 'Taxa medida: {hz} Hz',
      measuredAfterGame: 'Após o último jogo: {hz} Hz',
      notMeasured: 'Ainda não medida — role uma lista ou toque em Medir.',
      measureAction: 'Medir',
      measuring: 'Medindo…',
      measureFailed:
          'Não foi possível medir: a interface não desenhou quadros suficientes.',
      measureHint: 'Medir a taxa de atualização da interface',
      saveFailed: 'Não foi possível salvar o ajuste.',
      technicalCode: 'Código técnico: {code}',
    },
    'fr': {
      title: 'Interface 120 Hz',
      description:
          'Améliore la fluidité des menus et du défilement sur les écrans compatibles.',
      unavailableScreen: 'Non disponible sur cet écran (maximum {hz} Hz).',
      unavailableEngine: 'Non disponible dans cette version de RewindBox.',
      restartRequired:
          'Prendra effet à la prochaine ouverture de RewindBox, après l’avoir fermée depuis le sélecteur d’apps.',
      limitedLowPower: 'Limité à 60 Hz par le mode Économie d’énergie.',
      limitedThermal: 'Limité par la température de l’appareil.',
      measured: 'Fréquence mesurée : {hz} Hz',
      measuredAfterGame: 'Après le dernier jeu : {hz} Hz',
      notMeasured:
          'Pas encore mesurée — faites défiler une liste ou touchez Mesurer.',
      measureAction: 'Mesurer',
      measuring: 'Mesure en cours…',
      measureFailed:
          'Mesure impossible : l’interface n’a pas affiché assez d’images.',
      measureHint: 'Mesurer la fréquence de l’interface',
      saveFailed: 'Le réglage n’a pas pu être enregistré.',
      technicalCode: 'Code technique : {code}',
    },
    'de': {
      title: '120-Hz-Oberfläche',
      description:
          'Macht Menüs und Scrollen auf kompatiblen Bildschirmen flüssiger.',
      unavailableScreen:
          'Auf diesem Bildschirm nicht verfügbar (maximal {hz} Hz).',
      unavailableEngine: 'In dieser RewindBox-Version nicht verfügbar.',
      restartRequired:
          'Wird beim nächsten Öffnen von RewindBox wirksam, nachdem die App im App-Umschalter geschlossen wurde.',
      limitedLowPower: 'Durch den Stromsparmodus auf 60 Hz begrenzt.',
      limitedThermal: 'Durch die Gerätetemperatur begrenzt.',
      measured: 'Gemessene Bildrate: {hz} Hz',
      measuredAfterGame: 'Nach dem letzten Spiel: {hz} Hz',
      notMeasured:
          'Noch nicht gemessen – scrolle in einer Liste oder tippe auf „Messen“.',
      measureAction: 'Messen',
      measuring: 'Wird gemessen …',
      measureFailed:
          'Messung nicht möglich: Die Oberfläche hat zu wenige Bilder gezeichnet.',
      measureHint: 'Bildwiederholrate der Oberfläche messen',
      saveFailed: 'Die Einstellung konnte nicht gespeichert werden.',
      technicalCode: 'Technischer Code: {code}',
    },
    'it': {
      title: 'Interfaccia a 120 Hz',
      description:
          'Rende più fluidi menu e scorrimento sugli schermi compatibili.',
      unavailableScreen: 'Non disponibile su questo schermo (massimo {hz} Hz).',
      unavailableEngine: 'Non disponibile in questa versione di RewindBox.',
      restartRequired:
          'Avrà effetto alla prossima apertura di RewindBox, dopo averla chiusa dal selettore delle app.',
      limitedLowPower: 'Limitata a 60 Hz dalla modalità Risparmio energetico.',
      limitedThermal: 'Limitata dalla temperatura del dispositivo.',
      measured: 'Frequenza misurata: {hz} Hz',
      measuredAfterGame: 'Dopo l’ultimo gioco: {hz} Hz',
      notMeasured: 'Non ancora misurata: scorri un elenco o tocca Misura.',
      measureAction: 'Misura',
      measuring: 'Misurazione in corso…',
      measureFailed:
          'Misurazione non riuscita: l’interfaccia non ha disegnato abbastanza immagini.',
      measureHint: 'Misura la frequenza dell’interfaccia',
      saveFailed: 'Impossibile salvare l’impostazione.',
      technicalCode: 'Codice tecnico: {code}',
    },
    'id': {
      title: 'Antarmuka 120 Hz',
      description:
          'Membuat menu dan pengguliran lebih mulus di layar yang kompatibel.',
      unavailableScreen: 'Tidak tersedia di layar ini (maksimum {hz} Hz).',
      unavailableEngine: 'Tidak tersedia di versi RewindBox ini.',
      restartRequired:
          'Berlaku saat RewindBox dibuka lagi, setelah ditutup dari pengalih aplikasi.',
      limitedLowPower: 'Dibatasi ke 60 Hz oleh Mode Daya Rendah.',
      limitedThermal: 'Dibatasi oleh suhu perangkat.',
      measured: 'Laju terukur: {hz} Hz',
      measuredAfterGame: 'Setelah game terakhir: {hz} Hz',
      notMeasured: 'Belum diukur — gulir daftar atau ketuk Ukur.',
      measureAction: 'Ukur',
      measuring: 'Sedang mengukur…',
      measureFailed:
          'Tidak dapat mengukur: antarmuka tidak menggambar cukup bingkai.',
      measureHint: 'Ukur laju penyegaran antarmuka',
      saveFailed: 'Pengaturan tidak dapat disimpan.',
      technicalCode: 'Kode teknis: {code}',
    },
    'ja': {
      title: '120Hz インターフェイス',
      description: '対応画面でメニューとスクロールをより滑らかにします。',
      unavailableScreen: 'この画面では利用できません（最大 {hz} Hz）。',
      unavailableEngine: 'このバージョンの RewindBox では利用できません。',
      restartRequired: 'App スイッチャーで RewindBox を閉じ、次に開いたときに有効になります。',
      limitedLowPower: '低電力モードにより 60 Hz に制限されています。',
      limitedThermal: 'デバイスの温度により制限されています。',
      measured: '測定したリフレッシュレート：{hz} Hz',
      measuredAfterGame: '前回のゲーム後：{hz} Hz',
      notMeasured: 'まだ測定されていません。リストをスクロールするか「測定」をタップしてください。',
      measureAction: '測定',
      measuring: '測定中…',
      measureFailed: '測定できませんでした：インターフェイスの描画フレームが不足しています。',
      measureHint: 'インターフェイスのリフレッシュレートを測定',
      saveFailed: '設定を保存できませんでした。',
      technicalCode: '技術コード：{code}',
    },
    'ko': {
      title: '120Hz 인터페이스',
      description: '호환되는 화면에서 메뉴와 스크롤을 더 부드럽게 합니다.',
      unavailableScreen: '이 화면에서는 사용할 수 없습니다(최대 {hz}Hz).',
      unavailableEngine: '이 버전의 RewindBox에서는 사용할 수 없습니다.',
      restartRequired: '앱 전환기에서 RewindBox을 닫은 뒤 다음에 열 때 적용됩니다.',
      limitedLowPower: '저전력 모드로 인해 60Hz로 제한됩니다.',
      limitedThermal: '기기 온도로 인해 제한됩니다.',
      measured: '측정된 주사율: {hz}Hz',
      measuredAfterGame: '마지막 게임 이후: {hz}Hz',
      notMeasured: '아직 측정되지 않았습니다. 목록을 스크롤하거나 측정을 탭하세요.',
      measureAction: '측정',
      measuring: '측정 중…',
      measureFailed: '측정할 수 없습니다: 인터페이스가 충분한 프레임을 그리지 않았습니다.',
      measureHint: '인터페이스 주사율 측정',
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
