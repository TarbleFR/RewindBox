/// Build 442 texts of the embedded Dolphin performance overlay: the worst
/// sampled frame, the thermal state and the memory footprint line. The native
/// overlay receives them through the session labels built by
/// `DolphinImportLocale.labelsFor`.
abstract final class DolphinDisplayLocale {
  static const values = <String, Map<String, String>>{
    'en': {
      'peakFrameTime': 'Peak',
      'thermalState': 'Thermal',
      'memoryFootprint': 'Memory',
      'thermalNominal': 'normal',
      'thermalFair': 'warm',
      'thermalSerious': 'hot',
      'thermalCritical': 'critical',
    },
    'fr': {
      'peakFrameTime': 'Pic',
      'thermalState': 'Thermique',
      'memoryFootprint': 'Mémoire',
      'thermalNominal': 'normal',
      'thermalFair': 'tiède',
      'thermalSerious': 'chaud',
      'thermalCritical': 'critique',
    },
    'de': {
      'peakFrameTime': 'Spitze',
      'thermalState': 'Thermisch',
      'memoryFootprint': 'Speicher',
      'thermalNominal': 'normal',
      'thermalFair': 'warm',
      'thermalSerious': 'heiß',
      'thermalCritical': 'kritisch',
    },
    'es': {
      'peakFrameTime': 'Pico',
      'thermalState': 'Térmico',
      'memoryFootprint': 'Memoria',
      'thermalNominal': 'normal',
      'thermalFair': 'templado',
      'thermalSerious': 'caliente',
      'thermalCritical': 'crítico',
    },
    'it': {
      'peakFrameTime': 'Picco',
      'thermalState': 'Termico',
      'memoryFootprint': 'Memoria',
      'thermalNominal': 'normale',
      'thermalFair': 'tiepido',
      'thermalSerious': 'caldo',
      'thermalCritical': 'critico',
    },
    'pt': {
      'peakFrameTime': 'Pico',
      'thermalState': 'Térmico',
      'memoryFootprint': 'Memória',
      'thermalNominal': 'normal',
      'thermalFair': 'morno',
      'thermalSerious': 'quente',
      'thermalCritical': 'crítico',
    },
    'ru': {
      'peakFrameTime': 'Пик',
      'thermalState': 'Нагрев',
      'memoryFootprint': 'Память',
      'thermalNominal': 'норма',
      'thermalFair': 'тёплый',
      'thermalSerious': 'горячий',
      'thermalCritical': 'критический',
    },
    'id': {
      'peakFrameTime': 'Puncak',
      'thermalState': 'Termal',
      'memoryFootprint': 'Memori',
      'thermalNominal': 'normal',
      'thermalFair': 'hangat',
      'thermalSerious': 'panas',
      'thermalCritical': 'kritis',
    },
    'ja': {
      'peakFrameTime': 'ピーク',
      'thermalState': '温度',
      'memoryFootprint': 'メモリ',
      'thermalNominal': '通常',
      'thermalFair': 'やや高温',
      'thermalSerious': '高温',
      'thermalCritical': '危険',
    },
    'ko': {
      'peakFrameTime': '최대',
      'thermalState': '발열',
      'memoryFootprint': '메모리',
      'thermalNominal': '정상',
      'thermalFair': '미지근함',
      'thermalSerious': '뜨거움',
      'thermalCritical': '위험',
    },
    'zh': {
      'peakFrameTime': '峰值',
      'thermalState': '温度',
      'memoryFootprint': '内存',
      'thermalNominal': '正常',
      'thermalFair': '偏热',
      'thermalSerious': '过热',
      'thermalCritical': '严重过热',
    },
    'zh_Hant': {
      'peakFrameTime': '峰值',
      'thermalState': '溫度',
      'memoryFootprint': '記憶體',
      'thermalNominal': '正常',
      'thermalFair': '偏熱',
      'thermalSerious': '過熱',
      'thermalCritical': '嚴重過熱',
    },
  };

  /// Labels for a `DolphinImportLocale.localeKey` value. Every supported
  /// language has every key; English only covers an unsupported language.
  static Map<String, String> labels(String localeKey) => <String, String>{
        ...values['en']!,
        ...?values[localeKey],
      };
}
