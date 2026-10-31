import SwiftUI

@MainActor
public struct TranslatedAchievementTitle: View {
    public let source: AchievementSource
    @ObservedObject private var provider: AchievementTextProvider
    public init(_ source: AchievementSource, provider: AchievementTextProvider = .shared) {
        self.source = source
        self.provider = provider
    }
    public var body: some View {
        let _ = provider.revision
        let text = provider.text(for: source)
        VStack(alignment: .leading, spacing: 2) {
            Text(verbatim: text.title)
            if let note = AchievementTranslationNotice.text(for: text, language: provider.language) {
                Text(verbatim: note).font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
}

@MainActor
public struct TranslatedAchievementDescription: View {
    public let source: AchievementSource
    @ObservedObject private var provider: AchievementTextProvider
    public init(_ source: AchievementSource, provider: AchievementTextProvider = .shared) {
        self.source = source
        self.provider = provider
    }
    public var body: some View {
        let _ = provider.revision
        Text(verbatim: provider.text(for: source).description)
    }
}

/// Mirrors the app's twelve-locale catalog; returned to Flutter/native consumers
/// with the text so every surface displays the same provenance/fallback message.
public enum AchievementTranslationNotice {
    // automatic, original/unavailable, original/unsupported, original/pending
    static let messages: [String: [String]] = [
        "en": ["Automatic translation", "Original text · translation unavailable", "Original text · language not supported", "Original text · translation pending"],
        "es": ["Traducción automática", "Texto original · traducción no disponible", "Texto original · idioma no compatible", "Texto original · traducción pendiente"],
        "ru": ["Автоматический перевод", "Оригинал · перевод недоступен", "Оригинал · язык не поддерживается", "Оригинал · ожидание перевода"],
        "zh": ["自动翻译", "原文 · 翻译暂不可用", "原文 · 不支持此语言", "原文 · 等待翻译"],
        "zh_Hant": ["自動翻譯", "原文 · 翻譯暫不可用", "原文 · 不支援此語言", "原文 · 等待翻譯"],
        "pt": ["Tradução automática", "Texto original · tradução indisponível", "Texto original · idioma não compatível", "Texto original · aguardando tradução"],
        "fr": ["Traduction automatique", "Texte original · traduction indisponible", "Texte original · langue non prise en charge", "Texte original · traduction en attente"],
        "de": ["Automatische Übersetzung", "Originaltext · Übersetzung nicht verfügbar", "Originaltext · Sprache nicht unterstützt", "Originaltext · Übersetzung ausstehend"],
        "it": ["Traduzione automatica", "Testo originale · traduzione non disponibile", "Testo originale · lingua non supportata", "Testo originale · traduzione in attesa"],
        "id": ["Terjemahan otomatis", "Teks asli · terjemahan tidak tersedia", "Teks asli · bahasa tidak didukung", "Teks asli · menunggu terjemahan"],
        "ja": ["自動翻訳", "原文 · 翻訳を利用できません", "原文 · 未対応の言語", "原文 · 翻訳待ち"],
        "ko": ["자동 번역", "원문 · 번역을 사용할 수 없음", "원문 · 지원되지 않는 언어", "원문 · 번역 대기 중"]
    ]

    public static func text(for text: LocalizedAchievementText, language: String) -> String? {
        if text.provenance == .official { return nil }
        let code = AchievementLanguage.identifiers.first { $0.value == AchievementLanguage.canonical(language) }?.key ?? "en"
        let messages = messages[code]!
        if text.provenance == .machine { return messages[0] }
        guard !AchievementLanguage.isEnglish(language) else { return nil }
        switch text.fallback {
        case .unsupported: return messages[2]
        case .pending: return messages[3]
        default: return messages[1]
        }
    }
}
