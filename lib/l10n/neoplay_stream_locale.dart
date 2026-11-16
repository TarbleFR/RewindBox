import 'package:flutter/widgets.dart';

/// Chromecast route setting and stream readout of the NeoPlay panel.
class NeoPlayStreamLocale {
  static String get(BuildContext context, String key) {
    final locale = Localizations.localeOf(context);
    final traditional = locale.languageCode == 'zh' &&
        (locale.scriptCode?.toLowerCase() == 'hant' ||
            const ['TW', 'HK', 'MO'].contains(locale.countryCode?.toUpperCase()));
    final language = traditional ? 'zh_Hant' : locale.languageCode;
    return (values[language] ?? values['en']!)[key]!;
  }

  static const values = <String, Map<String, String>>{
    'en': {
      'modeTitle': 'Chromecast: how the picture is sent',
      'automatic': 'Automatic',
      'direct': 'Direct (short delay)',
      'compatible': 'Compatible (longer delay)',
      'modeHelp': 'Automatic uses the direct route and switches to the compatible one if the TV does not play it. A shorter delay keeps less reserve: on weak Wi-Fi the picture may pause briefly.',
      'routeDirect': 'Direct route',
      'routeSegments': 'Compatible route',
      'delay': 'delay up to the TV player: {s} s',
    },
    'fr': {
      'modeTitle': 'Chromecast : mode d’envoi de l’image',
      'automatic': 'Automatique',
      'direct': 'Direct (retard court)',
      'compatible': 'Compatible (retard plus long)',
      'modeHelp': 'Automatique utilise la voie directe et passe en mode compatible si le téléviseur ne la lit pas. Un retard plus court garde moins de réserve : avec un Wi-Fi faible, l’image peut marquer de courtes pauses.',
      'routeDirect': 'Voie directe',
      'routeSegments': 'Voie compatible',
      'delay': 'retard jusqu’au lecteur du téléviseur : {s} s',
    },
    'de': {
      'modeTitle': 'Chromecast: Übertragungsart des Bildes',
      'automatic': 'Automatisch',
      'direct': 'Direkt (kurze Verzögerung)',
      'compatible': 'Kompatibel (längere Verzögerung)',
      'modeHelp': 'Automatisch nutzt den direkten Weg und wechselt zum kompatiblen, wenn der Fernseher ihn nicht abspielt. Eine kürzere Verzögerung lässt weniger Reserve: Bei schwachem WLAN kann das Bild kurz anhalten.',
      'routeDirect': 'Direkter Weg',
      'routeSegments': 'Kompatibler Weg',
      'delay': 'Verzögerung bis zum Player des Fernsehers: {s} s',
    },
    'es': {
      'modeTitle': 'Chromecast: modo de envío de la imagen',
      'automatic': 'Automático',
      'direct': 'Directo (retraso corto)',
      'compatible': 'Compatible (retraso mayor)',
      'modeHelp': 'Automático usa la vía directa y pasa a la compatible si el televisor no la reproduce. Un retraso más corto deja menos margen: con una Wi-Fi débil la imagen puede detenerse un instante.',
      'routeDirect': 'Vía directa',
      'routeSegments': 'Vía compatible',
      'delay': 'retraso hasta el reproductor del televisor: {s} s',
    },
    'it': {
      'modeTitle': 'Chromecast: modalità di invio dell’immagine',
      'automatic': 'Automatico',
      'direct': 'Diretto (ritardo breve)',
      'compatible': 'Compatibile (ritardo maggiore)',
      'modeHelp': 'Automatico usa la via diretta e passa a quella compatibile se il televisore non la riproduce. Un ritardo più breve lascia meno margine: con un Wi-Fi debole l’immagine può fermarsi per un attimo.',
      'routeDirect': 'Via diretta',
      'routeSegments': 'Via compatibile',
      'delay': 'ritardo fino al lettore del televisore: {s} s',
    },
    'pt': {
      'modeTitle': 'Chromecast: modo de envio da imagem',
      'automatic': 'Automático',
      'direct': 'Direto (atraso curto)',
      'compatible': 'Compatível (atraso maior)',
      'modeHelp': 'Automático usa a via direta e muda para a compatível se o televisor não a reproduzir. Um atraso mais curto deixa menos margem: com um Wi-Fi fraco a imagem pode parar por instantes.',
      'routeDirect': 'Via direta',
      'routeSegments': 'Via compatível',
      'delay': 'atraso até ao leitor do televisor: {s} s',
    },
    'ru': {
      'modeTitle': 'Chromecast: способ передачи изображения',
      'automatic': 'Автоматически',
      'direct': 'Напрямую (малая задержка)',
      'compatible': 'Совместимый (задержка больше)',
      'modeHelp': 'В автоматическом режиме используется прямой способ; если телевизор его не воспроизводит, включается совместимый. Чем меньше задержка, тем меньше запас: при слабом Wi-Fi изображение может ненадолго останавливаться.',
      'routeDirect': 'Прямой способ',
      'routeSegments': 'Совместимый способ',
      'delay': 'задержка до проигрывателя телевизора: {s} с',
    },
    'zh': {
      'modeTitle': 'Chromecast：画面发送方式',
      'automatic': '自动',
      'direct': '直接（延迟短）',
      'compatible': '兼容（延迟较长）',
      'modeHelp': '自动模式使用直接方式；如果电视无法播放，则切换到兼容方式。延迟越短，余量越小：Wi-Fi 较弱时画面可能短暂停顿。',
      'routeDirect': '直接方式',
      'routeSegments': '兼容方式',
      'delay': '到电视播放器的延迟：{s} 秒',
    },
    'zh_Hant': {
      'modeTitle': 'Chromecast：畫面傳送方式',
      'automatic': '自動',
      'direct': '直接（延遲短）',
      'compatible': '相容（延遲較長）',
      'modeHelp': '自動模式使用直接方式；如果電視無法播放，則切換到相容方式。延遲越短，餘裕越小：Wi-Fi 較弱時畫面可能短暫停頓。',
      'routeDirect': '直接方式',
      'routeSegments': '相容方式',
      'delay': '到電視播放器的延遲：{s} 秒',
    },
    'id': {
      'modeTitle': 'Chromecast: cara pengiriman gambar',
      'automatic': 'Otomatis',
      'direct': 'Langsung (jeda pendek)',
      'compatible': 'Kompatibel (jeda lebih panjang)',
      'modeHelp': 'Otomatis memakai jalur langsung dan beralih ke jalur kompatibel jika TV tidak memutarnya. Jeda yang lebih pendek menyisakan cadangan lebih sedikit: pada Wi-Fi lemah gambar dapat berhenti sejenak.',
      'routeDirect': 'Jalur langsung',
      'routeSegments': 'Jalur kompatibel',
      'delay': 'jeda sampai pemutar TV: {s} dtk',
    },
    'ja': {
      'modeTitle': 'Chromecast：映像の送信方法',
      'automatic': '自動',
      'direct': 'ダイレクト（遅延が短い）',
      'compatible': '互換（遅延が長い）',
      'modeHelp': '自動ではダイレクト方式を使い、テレビが再生できない場合は互換方式に切り替えます。遅延が短いほど余裕が少なくなり、Wi-Fi が弱いと映像が一瞬止まることがあります。',
      'routeDirect': 'ダイレクト方式',
      'routeSegments': '互換方式',
      'delay': 'テレビのプレーヤーまでの遅延：{s} 秒',
    },
    'ko': {
      'modeTitle': 'Chromecast: 화면 전송 방식',
      'automatic': '자동',
      'direct': '직접(지연 짧음)',
      'compatible': '호환(지연 김)',
      'modeHelp': '자동은 직접 방식을 사용하고 TV가 재생하지 못하면 호환 방식으로 전환합니다. 지연이 짧을수록 여유가 적어 Wi-Fi가 약하면 화면이 잠시 멈출 수 있습니다.',
      'routeDirect': '직접 방식',
      'routeSegments': '호환 방식',
      'delay': 'TV 플레이어까지의 지연: {s}초',
    },
  };
}
