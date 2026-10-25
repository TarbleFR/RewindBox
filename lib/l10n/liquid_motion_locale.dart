import 'package:flutter/widgets.dart';
import 'package:flutter_localization/flutter_localization.dart';

abstract final class LiquidMotionLocale {
  static const battery = <String, String>{
    'en': 'Device battery',
    'fr': 'Batterie de l’appareil',
    'es': 'Batería del dispositivo',
    'pt': 'Bateria do dispositivo',
    'ru': 'Заряд устройства',
    'zh': '设备电量',
    'zh_Hant': '裝置電量',
    'de': 'Geräteakku',
    'it': 'Batteria del dispositivo',
    'id': 'Baterai perangkat',
    'ja': '端末のバッテリー',
    'ko': '기기 배터리',
  };
  static String deviceBattery(BuildContext context) {
    final locale =
        FlutterLocalization.instance.currentLocale ??
        Localizations.localeOf(context);
    final traditional =
        locale.toString().contains('Hant') ||
        ['TW', 'HK', 'MO'].contains(locale.countryCode);
    return battery[traditional && locale.languageCode == 'zh'
            ? 'zh_Hant'
            : locale.languageCode] ??
        battery['en']!;
  }
}
