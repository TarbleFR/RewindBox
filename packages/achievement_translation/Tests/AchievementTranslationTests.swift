import XCTest
@testable import AchievementTranslation


actor MockTranslator: AchievementTranslator {
    private(set) var calls: [[String]] = []
    private var shouldFail = false
    func setFailure(_ value: Bool) { shouldFail = value }
    var translatedTextCount: Int { calls.reduce(0) { $0 + $1.count } }
    func translate(_ texts: [String], from source: String, to target: String) async throws -> [String] {
        calls.append(texts)
        if shouldFail { throw URLError(.notConnectedToInternet) }
        return texts.map { "[\(target)] \($0)" }
    }
}

struct MockOfficial: OfficialAchievementTranslationSource {
    let table: [Int: OfficialAchievementText]
    func officialTranslations(for achievements: [AchievementSource],
                              language: String) async -> [Int: OfficialAchievementText] { table }
}

@MainActor
final class AchievementTranslationTests: XCTestCase {

    private let tempURL = FileManager.default.temporaryDirectory
        .appendingPathComponent("ach-tests-\(UUID().uuidString)/cache.sqlite")

    private func assertIdle(_ provider: AchievementTextProvider, file: StaticString = #filePath, line: UInt = #line) async {
        let idle = await provider.waitUntilIdle()
        XCTAssertTrue(idle, "Translation worker did not become idle", file: file, line: line)
    }

    private func makeProvider(language: String = "fr", translator: AchievementTranslator? = nil,
                              official: OfficialAchievementTranslationSource? = nil,
                              retryDelay: TimeInterval = 120) -> AchievementTextProvider {
        AchievementTextProvider(language: language, cacheURL: tempURL, translator: translator,
                                official: official, batchSize: 25, retryDelay: retryDelay)
    }

    private let a1 = AchievementSource(id: 1, title: "First Blood", description: "Defeat the first boss")

    func testShowsOriginalThenTranslation() async {
        let t = MockTranslator()
        let p = makeProvider(translator: t)
        let first = p.text(for: a1)
        XCTAssertEqual(first.provenance, .original)
        XCTAssertEqual(first.title, "First Blood")
        await assertIdle(p)
        let second = p.text(for: a1)
        XCTAssertEqual(second.title, "[fr-FR] First Blood")
        XCTAssertEqual(second.description, "[fr-FR] Defeat the first boss")
        XCTAssertEqual(second.provenance, .machine)
    }

    func testSourceLanguageBypassesTranslation() async {
        let t = MockTranslator()
        let p = makeProvider(language: "en", translator: t)
        XCTAssertEqual(p.text(for: a1).provenance, .original)
        await assertIdle(p)
        let observed2547 = await t.calls
        XCTAssertTrue(observed2547.isEmpty)
    }

    func testSeveralLanguages() async {
        let t = MockTranslator()
        let p = makeProvider(language: "fr-FR", translator: t)
        for lang in AchievementLanguage.identifiers.keys.sorted() where lang != "en" {
            p.setLanguage(lang)
            _ = p.text(for: a1)
            await assertIdle(p)
            XCTAssertEqual(p.text(for: a1).title, "[\(AchievementLanguage.canonical(lang))] First Blood", lang)
        }
    }

    func testLanguageSwitchRefreshesImmediately() async {
        let t = MockTranslator()
        let p = makeProvider(language: "fr-FR", translator: t)
        _ = p.text(for: a1); await assertIdle(p)
        let rev = p.revision
        p.setLanguage("es")
        XCTAssertGreaterThan(p.revision, rev)
        XCTAssertEqual(p.text(for: a1).provenance, .original)   // plus de texte français périmé
        await assertIdle(p)
        XCTAssertEqual(p.text(for: a1).title, "[es-ES] First Blood")
    }

    func testPersistentCacheSurvivesRelaunch() async {
        let t1 = MockTranslator()
        let p1 = makeProvider(translator: t1)
        _ = p1.text(for: a1); await assertIdle(p1)
        let observed4139 = await t1.translatedTextCount
        XCTAssertEqual(observed4139, 2)

        let t2 = MockTranslator(); await t2.setFailure(true)     // même hors ligne
        let p2 = makeProvider(translator: t2)
        _ = p2.text(for: a1); await assertIdle(p2)
        XCTAssertEqual(p2.text(for: a1).title, "[fr-FR] First Blood")
        let observed4445 = await t2.calls
        XCTAssertTrue(observed4445.isEmpty)
    }

    func testStaleTranslationIsInvalidated() async {
        let t = MockTranslator()
        let p = makeProvider(translator: t)
        _ = p.text(for: a1); await assertIdle(p)
        let changed = AchievementSource(id: 1, title: "First Blood", description: "Defeat the FIRST boss without dying")
        XCTAssertEqual(p.text(for: changed).provenance, .original)   // ancienne traduction non réutilisée
        await assertIdle(p)
        XCTAssertEqual(p.text(for: changed).description, "[fr-FR] Defeat the FIRST boss without dying")
        let observed5091 = await t.calls
        XCTAssertEqual(observed5091.count, 2)
    }

    func testOfflineFallsBackToOriginalWithoutRetryLoop() async {
        let t = MockTranslator(); await t.setFailure(true)
        let p = makeProvider(translator: t)
        for _ in 0..<5 { _ = p.text(for: a1); await assertIdle(p) }
        XCTAssertEqual(p.text(for: a1).title, "First Blood")
        XCTAssertEqual(p.text(for: a1).provenance, .original)
        let observed5595 = await t.calls
        XCTAssertEqual(observed5595.count, 1)   // backoff : un seul essai
    }

    func testRetriesAfterBackoffOnceBackOnline() async {
        let t = MockTranslator(); await t.setFailure(true)
        let p = makeProvider(translator: t, retryDelay: 0.05)
        _ = p.text(for: a1); await assertIdle(p)
        await t.setFailure(false)
        try? await Task.sleep(for: .milliseconds(120))
        _ = p.text(for: a1); await assertIdle(p)
        XCTAssertEqual(p.text(for: a1).title, "[fr-FR] First Blood")
    }

    func testNoDuplicateRequests() async {
        let t = MockTranslator()
        let p = makeProvider(translator: t)
        for _ in 0..<50 { _ = p.text(for: a1) }
        await assertIdle(p)
        let observed6352 = await t.translatedTextCount
        XCTAssertEqual(observed6352, 2)   // titre + description, une seule fois
    }

    func testOfficialTranslationTakesPriorityAndKeepsProvenance() async {
        let t = MockTranslator()
        let o = MockOfficial(table: [1: OfficialAchievementText(title: "Premier sang", description: "Battez le premier boss")])
        let p = makeProvider(translator: t, official: o)
        _ = p.text(for: a1); await assertIdle(p)
        let r = p.text(for: a1)
        XCTAssertEqual(r.title, "Premier sang")
        XCTAssertEqual(r.provenance, .official)
        let observed7014 = await t.calls
        XCTAssertTrue(observed7014.isEmpty)
    }

    func testUnicodeRoundTrip() async throws {
        let cache = try AchievementTranslationCache(fileURL: tempURL)
        let samples = ["Épée d'Éclair — œuvre « spéciale »", "勇者の証 ⚔️", "إنجاز البداية", "Ünïcödé ñ ß 🎮",
                       String(repeating: "Très long texte. ", count: 500)]
        let rows = samples.enumerated().map {
            CachedAchievementTranslation(achievementID: $0.offset, sourceHash: "h", title: $0.element,
                                         description: $0.element, provenance: .machine)
        }
        try await cache.store(rows, language: "fr-FR")
        let back = try await cache.fetch(language: "fr-FR", ids: Array(0..<samples.count))
        for (i, s) in samples.enumerated() {
            XCTAssertEqual(back[i]?.title, s)
            XCTAssertEqual(back[i]?.description, s)
        }
    }

    func testEmptyDescriptionIsNotTranslated() async {
        let t = MockTranslator()
        let p = makeProvider(translator: t)
        let a = AchievementSource(id: 9, title: "Hidden", description: "")
        _ = p.text(for: a); await assertIdle(p)
        let observed8311 = await t.translatedTextCount
        XCTAssertEqual(observed8311, 1)
        XCTAssertEqual(p.text(for: a).description, "")
    }

    func testLargeLibraryIsBatchedAndCached() async throws {
        let t = MockTranslator()
        let p = makeProvider(translator: t)
        let list = (0..<800).map { AchievementSource(id: $0, title: "Title \($0)", description: "Desc \($0)") }
        let start = Date()
        p.prefetch(list)
        await assertIdle(p)
        let elapsed = Date().timeIntervalSince(start)
        let observed8891 = await t.calls
        XCTAssertTrue(observed8891.allSatisfy { $0.count <= 50 })             // lots de 25 succès max
        let observed8989 = await t.translatedTextCount
        XCTAssertEqual(observed8989, 1600)
        XCTAssertLessThan(elapsed, 10)
        let cache = try AchievementTranslationCache(fileURL: tempURL)
        let n = try await cache.count(language: "fr-FR")
        XCTAssertEqual(n, 800)
        let before = await t.translatedTextCount
        p.setLanguage("es"); p.setLanguage("fr")
        p.prefetch(list); await assertIdle(p)
        let observed9440 = await t.translatedTextCount
        XCTAssertEqual(observed9440, before)
    }

    func testResolveFallsBackQuicklyWhenTranslationFails() async {
        let t = MockTranslator(); await t.setFailure(true)
        let p = makeProvider(translator: t)
        let start = Date()
        let r = await p.resolve(a1, timeout: 1.0)
        XCTAssertEqual(r.provenance, .original)
        XCTAssertLessThan(Date().timeIntervalSince(start), 1.0)
    }

    func testResolveReturnsTranslationWhenFast() async {
        let p = makeProvider(translator: MockTranslator())
        let r = await p.resolve(a1, timeout: 2.0)
        XCTAssertEqual(r.title, "[fr-FR] First Blood")
    }

    func testCachePurgeByLanguage() async throws {
        let cache = try AchievementTranslationCache(fileURL: tempURL)
        let row = CachedAchievementTranslation(achievementID: 1, sourceHash: "h", title: "a", description: "b", provenance: .machine)
        try await cache.store([row], language: "fr-FR")
        try await cache.store([row], language: "es-ES")
        try await cache.purge(language: "fr-FR")
        let fr = try await cache.count(language: "fr-FR")
        let es = try await cache.count(language: "es-ES")
        XCTAssertEqual(fr, 0)
        XCTAssertEqual(es, 1)
    }

    func testFingerprintStableAndSensitive() {
        let a = AchievementSource(id: 1, title: "A", description: "B")
        let b = AchievementSource(id: 1, title: "A", description: "B")
        let c = AchievementSource(id: 1, title: "A", description: "C")
        XCTAssertEqual(a.sourceHash, b.sourceHash)
        XCTAssertNotEqual(a.sourceHash, c.sourceHash)
    }
}
