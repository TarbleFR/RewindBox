import Foundation
import CryptoKit

/// The only mapping is from the existing app language picker. Never consult iOS preferences.
public enum AchievementLanguage {
    public static let identifiers: [String: String] = [
        "en": "en-US", "es": "es-ES", "ru": "ru-RU", "zh": "zh-Hans-CN",
        "zh_Hant": "zh-Hant-TW", "pt": "pt-BR", "fr": "fr-FR", "de": "de-DE",
        "it": "it-IT", "id": "id-ID", "ja": "ja-JP", "ko": "ko-KR"
    ]

    public static func canonical(_ code: String) -> String {
        identifiers[code] ?? code.replacingOccurrences(of: "_", with: "-")
    }

    public static func isEnglish(_ code: String) -> Bool {
        canonical(code).split(separator: "-").first?.lowercased() == "en"
    }
}

/// Display input only. No award, authentication, game name, points or date fields are mutated.
public struct AchievementSource: Sendable, Hashable {
    public let id: Int
    public let title: String
    public let description: String
    public let sourceHash: String

    public init(id: Int, title: String, description: String) {
        self.id = id
        self.title = title
        self.description = description
        // Length framing avoids ambiguous separators; SHA-256 is stable across launches.
        let framed = "\(title.utf8.count):\(title)\(description.utf8.count):\(description)"
        self.sourceHash = SHA256.hash(data: Data(framed.utf8))
            .map { String(format: "%02x", $0) }.joined()
    }
}

public enum TranslationProvenance: String, Sendable {
    case official, machine, original
}

public enum TranslationFallback: String, Sendable {
    case pending, unsupported, unavailable
}

public struct LocalizedAchievementText: Sendable, Equatable {
    public let title: String
    public let description: String
    public let provenance: TranslationProvenance
    public let fallback: TranslationFallback?

    public init(title: String, description: String, provenance: TranslationProvenance,
                fallback: TranslationFallback? = nil) {
        self.title = title
        self.description = description
        self.provenance = provenance
        self.fallback = fallback
    }
}

public struct CachedAchievementTranslation: Sendable, Equatable {
    public let achievementID: Int
    public let sourceHash: String
    public let title: String
    public let description: String
    public let provenance: TranslationProvenance

    public init(achievementID: Int, sourceHash: String, title: String,
                description: String, provenance: TranslationProvenance) {
        self.achievementID = achievementID
        self.sourceHash = sourceHash
        self.title = title
        self.description = description
        self.provenance = provenance
    }

    var text: LocalizedAchievementText {
        LocalizedAchievementText(title: title, description: description, provenance: provenance)
    }
}

public enum AchievementTranslationError: Error, Sendable {
    case mismatchedResponse, hostUnavailable, unsupportedLanguage, invalidProvenance
    case cache(String)
}

public protocol AchievementTranslator: Sendable {
    func translate(_ texts: [String], from source: String, to target: String) async throws -> [String]
}

public struct OfficialAchievementText: Sendable, Equatable {
    public let title: String
    public let description: String
    public init(title: String, description: String) {
        self.title = title
        self.description = description
    }
}

/// Deliberately not configured: RA has no verified public translation endpoint.
public protocol OfficialAchievementTranslationSource: Sendable {
    func officialTranslations(for achievements: [AchievementSource],
                              language: String) async -> [Int: OfficialAchievementText]
}
