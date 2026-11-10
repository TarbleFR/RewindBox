import XCTest
import Combine
@testable import AchievementTranslation

actor SlowTranslator: AchievementTranslator {
    private(set) var targets: [String] = []
    let slowTarget: String
    init(slowTarget: String = "fr-FR") { self.slowTarget = slowTarget }
    func translate(_ texts: [String], from source: String, to target: String) async throws -> [String] {
        targets.append(target)
        if target == slowTarget { try await Task.sleep(for: .seconds(60)) }
        return texts.map { "[\(target)] \($0)" }
    }
}

struct CancelledSessionTranslator: AchievementTranslator {
    func translate(_ texts: [String], from source: String, to target: String) async throws -> [String] {
        throw CancellationError()
    }
}

struct UnsupportedTranslator: AchievementTranslator {
    func translate(_ texts: [String], from source: String, to target: String) async throws -> [String] {
        throw AchievementTranslationError.unsupportedLanguage
    }
}

actor SuspendedFirstTranslator: AchievementTranslator {
    private var continuation: CheckedContinuation<Void, Never>?
    private(set) var requests: [[String]] = []

    func translate(_ texts: [String], from source: String, to target: String) async throws -> [String] {
        requests.append(texts)
        if requests.count == 1 {
            await withCheckedContinuation { continuation = $0 }
        }
        return texts.map { "[\(target)] \($0)" }
    }

    func release() {
        continuation?.resume()
        continuation = nil
    }
}

@MainActor
final class AchievementTranslationConcurrencyTests: XCTestCase {
    let source = AchievementSource(id: 123, title: "Éclair 勇者", description: "إنجاز البداية 🎮")

    func testExactlyTwelveMappedLanguagesAndScripts() {
        XCTAssertEqual(Set(AchievementLanguage.identifiers.keys),
                       Set(["en", "es", "ru", "zh", "zh_Hant", "pt", "fr", "de", "it", "id", "ja", "ko"]))
        XCTAssertEqual(AchievementLanguage.canonical("zh"), "zh-Hans-CN")
        XCTAssertEqual(AchievementLanguage.canonical("zh_Hant"), "zh-Hant-TW")
        XCTAssertEqual(AchievementLanguage.canonical("pt"), "pt-BR")
        XCTAssertEqual(Set(AchievementTranslationNotice.messages.keys), Set(AchievementLanguage.identifiers.keys))
        for language in AchievementLanguage.identifiers.keys {
            XCTAssertFalse(AchievementLanguage.canonical(language).contains("_"))
        }
    }

    func testSwitchCancelsActiveWorkAndNeverPublishesOldLanguage() async throws {
        let translator = SlowTranslator()
        let provider = AchievementTextProvider(language: "fr", cacheURL: nil, translator: translator)
        _ = provider.text(for: source)
        let startedDeadline = ContinuousClock.now.advanced(by: .seconds(1))
        while await translator.targets.isEmpty, ContinuousClock.now < startedDeadline {
            try await Task.sleep(for: .milliseconds(5))
        }
        let initial = await translator.targets
        XCTAssertEqual(initial, ["fr-FR"])
        provider.setLanguage("ja")
        let idle = await provider.waitUntilIdle(timeout: 1)
        XCTAssertTrue(idle)
        XCTAssertEqual(provider.text(for: source).title, "[ja-JP] Éclair 勇者")
        let targets = await translator.targets
        XCTAssertEqual(targets, ["fr-FR", "ja-JP"])
    }

    func testSourceChangeDuringWorkIsNotLost() async throws {
        let translator = MockTranslator()
        let provider = AchievementTextProvider(language: "fr", cacheURL: nil, translator: translator)
        _ = provider.text(for: source)
        let changed = AchievementSource(id: source.id, title: "Changed", description: "New requirements")
        _ = provider.text(for: changed)
        let idle = await provider.waitUntilIdle()
        XCTAssertTrue(idle)
        XCTAssertEqual(provider.text(for: changed).title, "[fr-FR] Changed")
    }

    func testSourceChangeWhileEngineIsSuspendedReplacesOldResult() async throws {
        let translator = SuspendedFirstTranslator()
        let provider = AchievementTextProvider(language: "fr", cacheURL: nil, translator: translator)
        _ = provider.text(for: source)
        let deadline = ContinuousClock.now.advanced(by: .seconds(1))
        while await translator.requests.isEmpty, ContinuousClock.now < deadline {
            try await Task.sleep(for: .milliseconds(5))
        }
        let first = await translator.requests
        XCTAssertEqual(first.count, 1, "The old source must actually be in flight")
        let changed = AchievementSource(id: source.id, title: "Changed in flight", description: "New requirements")
        _ = provider.text(for: changed)
        await translator.release()
        let idle = await provider.waitUntilIdle()
        XCTAssertTrue(idle)
        let requests = await translator.requests
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(provider.text(for: changed).title, "[fr-FR] Changed in flight")
        XCTAssertEqual(provider.text(for: changed).description, "[fr-FR] New requirements")
    }

    func testLateEngineConfigurationRecoversWithoutBackoff() async {
        let provider = AchievementTextProvider(language: "fr", cacheURL: nil)
        _ = provider.text(for: source)
        let firstIdle = await provider.waitUntilIdle()
        XCTAssertTrue(firstIdle)
        XCTAssertEqual(provider.text(for: source).fallback, .unavailable)
        provider.configure(translator: MockTranslator())
        let secondIdle = await provider.waitUntilIdle()
        XCTAssertTrue(secondIdle)
        XCTAssertEqual(provider.text(for: source).provenance, .machine)
    }

    func testSystemSessionCancellationPublishesFallback() async {
        let provider = AchievementTextProvider(language: "fr", cacheURL: nil, translator: CancelledSessionTranslator())
        _ = provider.text(for: source)
        let idle = await provider.waitUntilIdle()
        XCTAssertTrue(idle)
        XCTAssertEqual(provider.text(for: source).fallback, .unavailable)
    }

    func testUnsupportedPairKeepsOriginalAndExplainsWhy() async {
        let provider = AchievementTextProvider(language: "fr", cacheURL: nil, translator: UnsupportedTranslator())
        _ = provider.text(for: source)
        let idle = await provider.waitUntilIdle()
        XCTAssertTrue(idle)
        let text = provider.text(for: source)
        XCTAssertEqual(text.title, source.title)
        XCTAssertEqual(text.description, source.description)
        XCTAssertEqual(text.provenance, .original)
        XCTAssertEqual(text.fallback, .unsupported)
        XCTAssertEqual(AchievementTranslationNotice.text(for: text, language: provider.language),
                       "Texte original · langue non prise en charge")
    }

    func testUnlockStateProceedsBeforeBoundedNotificationResolution() async {
        let provider = AchievementTextProvider(language: "fr", cacheURL: nil, translator: SlowTranslator())
        var unlockCount = 0
        var synchronizedCount = 0
        // Models the existing event order; native source-contract tests also inspect the real callsite.
        unlockCount += 1
        synchronizedCount += 1
        let start = ContinuousClock.now
        let notification = Task { await provider.resolve(source, timeout: 0.05) }
        XCTAssertEqual(unlockCount, 1)
        XCTAssertEqual(synchronizedCount, 1)
        let text = await notification.value
        XCTAssertLessThan(start.duration(to: ContinuousClock.now), .seconds(0.3))
        XCTAssertEqual(text.provenance, .original)
        provider.setLanguage("en") // Cancels the slow background work.
    }

    func testCancelledResolveAndBoundedIdleReturnPromptly() async throws {
        let provider = AchievementTextProvider(language: "fr", cacheURL: nil, translator: SlowTranslator())
        let notification = Task { await provider.resolve(source, timeout: 10) }
        try await Task.sleep(for: .milliseconds(45))
        let start = ContinuousClock.now
        notification.cancel()
        _ = await notification.value
        XCTAssertLessThan(start.duration(to: ContinuousClock.now), .seconds(0.25))
        let idle = await provider.waitUntilIdle(timeout: 0.03)
        XCTAssertFalse(idle)
        provider.setLanguage("en")
    }

    func testRevisionAndNotificationArePublishedOnLanguageChange() {
        let provider = AchievementTextProvider(cacheURL: nil)
        var notices = 0
        let observer = NotificationCenter.default.publisher(for: AchievementTextProvider.didChangeNotification, object: provider)
            .sink { _ in notices += 1 }
        let revision = provider.revision
        provider.setLanguage("ko")
        XCTAssertGreaterThan(provider.revision, revision)
        XCTAssertEqual(notices, 1)
        withExtendedLifetime(observer) {}
    }

    func testAppleBridgeWithoutHostTimesOutAndReleasesJob() async {
        let bridge = AppleTranslationBridge(hostTimeout: .milliseconds(30))
        do {
            _ = try await bridge.translate(["hello"], from: "en-US", to: "fr-FR")
            XCTFail("Missing host must not report success")
        } catch {
            guard case AchievementTranslationError.hostUnavailable = error else { XCTFail("\(error)"); return }
        }
        XCTAssertNil(bridge.job)
    }

    func testAppleBridgeCancellationReleasesContinuationAndIgnoresLateResponse() async throws {
        let bridge = AppleTranslationBridge()
        let first = Task { try await bridge.translate(["first"], from: "en-US", to: "fr-FR") }
        let firstDeadline = ContinuousClock.now.advanced(by: .seconds(1))
        while bridge.job == nil, ContinuousClock.now < firstDeadline { try await Task.sleep(for: .milliseconds(5)) }
        let oldID = try XCTUnwrap(bridge.job?.id)
        first.cancel()
        do { _ = try await first.value; XCTFail("Cancelled job succeeded") } catch { XCTAssertTrue(error is CancellationError) }
        let second = Task { try await bridge.translate(["second"], from: "en-US", to: "ja-JP") }
        let secondDeadline = ContinuousClock.now.advanced(by: .seconds(1))
        while bridge.job == nil, ContinuousClock.now < secondDeadline { try await Task.sleep(for: .milliseconds(5)) }
        let newID = try XCTUnwrap(bridge.job?.id)
        XCTAssertNotEqual(oldID, newID)
        bridge.finish(id: oldID, result: .success(["wrong language"]))
        XCTAssertEqual(bridge.job?.id, newID)
        bridge.finish(id: newID, result: .success(["日本語"]))
        let output = try await second.value
        XCTAssertEqual(output, ["日本語"])
    }

    func testAppleResponsesRejectDuplicateMissingAndForeignIdentifiers() throws {
        XCTAssertEqual(try AppleTranslationBridge.orderedResults([("1", "b"), ("0", "a")], count: 2), ["a", "b"])
        XCTAssertThrowsError(try AppleTranslationBridge.orderedResults([("0", "a"), ("0", "b")], count: 2))
        XCTAssertThrowsError(try AppleTranslationBridge.orderedResults([("0", "a")], count: 2))
        XCTAssertThrowsError(try AppleTranslationBridge.orderedResults([(nil, "a")], count: 1))
        XCTAssertThrowsError(try AppleTranslationBridge.orderedResults([("3", "a")], count: 1))
    }

    func testCacheRejectsOriginalProvenanceAndPreservesEmbeddedNull() async throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("ach-null-\(UUID()).sqlite")
        let cache = try AchievementTranslationCache(fileURL: url)
        let row = CachedAchievementTranslation(achievementID: 9, sourceHash: "h", title: "before\0after",
                                               description: "عربي\0日本語", provenance: .machine)
        try await cache.store([row], language: "fr-FR")
        let fetched = try await cache.fetch(language: "fr-FR", ids: [9])
        XCTAssertEqual(fetched[9], row)
        let invalid = CachedAchievementTranslation(achievementID: 10, sourceHash: "h", title: "original",
                                                   description: "", provenance: .original)
        do { try await cache.store([invalid], language: "fr-FR"); XCTFail("Original must not enter translated cache") }
        catch { guard case AchievementTranslationError.invalidProvenance = error else { XCTFail("\(error)"); return } }
        let count = try await cache.count(language: "fr-FR")
        XCTAssertEqual(count, 1)
    }
}
