import 'package:achievement_translation/achievement_translation.dart';

/// Presentation notices only; game names, points and RA source models are unchanged.
class AchievementTranslationLocale {
  static const messages = <String, List<String>>{
    'en': ['Automatic translation', 'Original text · translation unavailable', 'Original text · language not supported', 'Original text · translation pending'],
    'es': ['Traducción automática', 'Texto original · traducción no disponible', 'Texto original · idioma no compatible', 'Texto original · traducción pendiente'],
    'ru': ['Автоматический перевод', 'Оригинал · перевод недоступен', 'Оригинал · язык не поддерживается', 'Оригинал · ожидание перевода'],
    'zh': ['自动翻译', '原文 · 翻译暂不可用', '原文 · 不支持此语言', '原文 · 等待翻译'],
    'zh_Hant': ['自動翻譯', '原文 · 翻譯暫不可用', '原文 · 不支援此語言', '原文 · 等待翻譯'],
    'pt': ['Tradução automática', 'Texto original · tradução indisponível', 'Texto original · idioma não compatível', 'Texto original · aguardando tradução'],
    'fr': ['Traduction automatique', 'Texte original · traduction indisponible', 'Texte original · langue non prise en charge', 'Texte original · traduction en attente'],
    'de': ['Automatische Übersetzung', 'Originaltext · Übersetzung nicht verfügbar', 'Originaltext · Sprache nicht unterstützt', 'Originaltext · Übersetzung ausstehend'],
    'it': ['Traduzione automatica', 'Testo originale · traduzione non disponibile', 'Testo originale · lingua non supportata', 'Testo originale · traduzione in attesa'],
    'id': ['Terjemahan otomatis', 'Teks asli · terjemahan tidak tersedia', 'Teks asli · bahasa tidak didukung', 'Teks asli · menunggu terjemahan'],
    'ja': ['自動翻訳', '原文 · 翻訳を利用できません', '原文 · 未対応の言語', '原文 · 翻訳待ち'],
    'ko': ['자동 번역', '원문 · 번역을 사용할 수 없음', '원문 · 지원되지 않는 언어', '원문 · 번역 대기 중'],
  };

  static String? notice(AchievementDisplayText text, String appLanguage) {
    if (text.provenance == 'official') return null;
    final labels = messages[appLanguage] ?? messages['en']!;
    if (text.provenance == 'machine') return labels[0];
    if (appLanguage == 'en') return null;
    return labels[switch (text.fallback) { 'unsupported' => 2, 'pending' => 3, _ => 1 }];
  }
}
