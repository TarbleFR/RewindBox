import Foundation
import Combine

@MainActor
public final class AchievementTextProvider: ObservableObject {
    public static let shared = AchievementTextProvider()
    public static let didChangeNotification = Notification.Name("AchievementTextProviderDidChange")
    @Published public private(set) var revision = 0
    public private(set) var language: String

    private struct Key: Hashable { let id: Int; let hash: String }
    private struct Failure { let until: ContinuousClock.Instant; let reason: TranslationFallback }
    private let cache: AchievementTranslationCache?
    private var translator: (any AchievementTranslator)?
    private var official: (any OfficialAchievementTranslationSource)?
    private let batchSize: Int
    private let retryDelay: TimeInterval
    private let memoryLimit: Int
    private var memory: [Key: CachedAchievementTranslation] = [:]
    private var memoryOrder: [Key] = []
    private var known: [Int: AchievementSource] = [:]
    private var pending: [Key: AchievementSource] = [:]
    private var order: [Key] = []
    private var queued: Set<Key> = []
    private var failed: [Key: Failure] = [:]
    private var worker: Task<Void, Never>?
    private var generation = 0

    public init(language: String = "en", cacheURL: URL? = AchievementTranslationCache.defaultURL(),
                translator: (any AchievementTranslator)? = nil,
                official: (any OfficialAchievementTranslationSource)? = nil,
                batchSize: Int = 25, retryDelay: TimeInterval = 120, memoryLimit: Int = 4000) {
        self.language = AchievementLanguage.canonical(language)
        self.cache = cacheURL.flatMap { try? AchievementTranslationCache(fileURL: $0) }
        self.translator = translator
        self.official = official
        self.batchSize = max(1, batchSize)
        self.retryDelay = max(0, retryDelay)
        self.memoryLimit = max(1, memoryLimit)
    }

    public func configure(translator: (any AchievementTranslator)? = nil,
                          official: (any OfficialAchievementTranslationSource)? = nil) {
        if let translator { self.translator = translator }
        if let official { self.official = official }
        restart()
    }

    /// Called only by RewindBox's existing language authority.
    public func setLanguage(_ code: String) {
        let target = AchievementLanguage.canonical(code)
        guard target != language else { return }
        language = target
        memory.removeAll()
        memoryOrder.removeAll()
        restart()
    }

    /// Foreground/manual retry also handles a model installed outside the app.
    public func retryUnavailable() { restart() }

    private func restart() {
        generation &+= 1
        worker?.cancel()
        worker = nil
        pending.removeAll()
        order.removeAll()
        queued.removeAll()
        failed.removeAll()
        for source in known.values { enqueue(source) }
        notifyChange()
    }

    private func key(_ source: AchievementSource) -> Key { Key(id: source.id, hash: source.sourceHash) }

    public func text(for source: AchievementSource) -> LocalizedAchievementText {
        if known.count >= memoryLimit, known[source.id] == nil, let old = known.keys.first {
            known.removeValue(forKey: old)
        }
        known[source.id] = source
        if AchievementLanguage.isEnglish(language) { return original(source) }
        let k = key(source)
        if let row = memory[k] { return row.text }
        enqueue(source)
        return original(source, reason: failed[k]?.reason ?? .pending)
    }

    private func original(_ source: AchievementSource, reason: TranslationFallback? = nil) -> LocalizedAchievementText {
        LocalizedAchievementText(title: source.title, description: source.description,
                                 provenance: .original, fallback: reason)
    }

    /// Presentation-only deadline. The caller has already committed the unlock.
    /// Cancellation or a language switch never returns a stale-language result.
    public func resolve(_ source: AchievementSource, timeout: TimeInterval = 0.25) async -> LocalizedAchievementText {
        let gen = generation
        let clock = ContinuousClock()
        let deadline = clock.now.advanced(by: .seconds(max(0, timeout)))
        var result = text(for: source)
        while result.provenance == .original, queued.contains(key(source)), clock.now < deadline {
            if Task.isCancelled || gen != generation { return text(for: source) }
            do { try await clock.sleep(until: min(deadline, clock.now.advanced(by: .milliseconds(10)))) }
            catch { return text(for: source) }
            result = text(for: source)
        }
        return result
    }

    public func prefetch(_ sources: [AchievementSource]) {
        for source in sources { _ = text(for: source) }
    }

    /// Bounded diagnostic/test wait; a broken engine cannot hang XCTest forever.
    @discardableResult
    public func waitUntilIdle(timeout: TimeInterval = 10) async -> Bool {
        let clock = ContinuousClock()
        let deadline = clock.now.advanced(by: .seconds(timeout))
        while worker != nil || !pending.isEmpty {
            guard !Task.isCancelled, clock.now < deadline else { return false }
            do { try await Task.sleep(for: .milliseconds(5)) } catch { return false }
        }
        return true
    }

    private func enqueue(_ source: AchievementSource) {
        guard !AchievementLanguage.isEnglish(language) else { return }
        let k = key(source)
        guard memory[k] == nil, !queued.contains(k) else { return }
        if let failure = failed[k], failure.until > ContinuousClock.now { return }
        failed.removeValue(forKey: k)
        queued.insert(k)
        pending[k] = source
        order.append(k)
        guard worker == nil else { return }
        let gen = generation
        let target = language
        worker = Task { [weak self] in
            do { try await Task.sleep(for: .milliseconds(30)) } catch { return }
            await self?.drain(language: target, generation: gen)
        }
    }

    private func drain(language target: String, generation gen: Int) async {
        defer { if gen == generation { worker = nil } }
        while gen == generation, !Task.isCancelled, !order.isEmpty {
            let keys = Array(order.prefix(batchSize))
            order.removeFirst(keys.count)
            let sources = keys.compactMap { pending.removeValue(forKey: $0) }
            await process(sources, language: target, generation: gen)
            guard gen == generation, !Task.isCancelled else { return }
            for k in keys { queued.remove(k) }
        }
    }

    private func process(_ sources: [AchievementSource], language target: String, generation gen: Int) async {
        defer { if gen == generation, !Task.isCancelled { notifyChange() } }
        var missing = sources
        if let cache {
            let rows = (try? await cache.fetch(language: target, ids: sources.map(\.id))) ?? [:]
            guard gen == generation, !Task.isCancelled else { return }
            missing.removeAll { source in
                guard let row = rows[source.id], row.sourceHash == source.sourceHash else { return false }
                publish(row, generation: gen)
                return true
            }
        }
        if let official, !missing.isEmpty {
            let found = await official.officialTranslations(for: missing, language: target)
            guard gen == generation, !Task.isCancelled else { return }
            let rows = missing.compactMap { source -> CachedAchievementTranslation? in
                guard let text = found[source.id] else { return nil }
                return CachedAchievementTranslation(achievementID: source.id, sourceHash: source.sourceHash,
                    title: text.title, description: text.description, provenance: .official)
            }
            try? await cache?.store(rows, language: target)
            guard gen == generation, !Task.isCancelled else { return }
            for row in rows { publish(row, generation: gen) }
            let foundIDs = Set(rows.map(\.achievementID))
            missing.removeAll { foundIDs.contains($0.id) }
        }
        guard !missing.isEmpty else { return }
        do {
            guard let translator else { throw AchievementTranslationError.hostUnavailable }
            var texts: [String] = []
            var positions: [(Int?, Int?)] = []
            for source in missing {
                let title: Int? = source.title.isEmpty ? nil : texts.count
                if title != nil { texts.append(source.title) }
                let description: Int? = source.description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : texts.count
                if description != nil { texts.append(source.description) }
                positions.append((title, description))
            }
            let output = try await translator.translate(texts, from: "en-US", to: target)
            try Task.checkCancellation()
            guard gen == generation else { return }
            guard output.count == texts.count,
                  zip(texts, output).allSatisfy({ $0.0.isEmpty || !$0.1.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else {
                throw AchievementTranslationError.mismatchedResponse
            }
            let rows = zip(missing, positions).map { source, position in
                CachedAchievementTranslation(achievementID: source.id, sourceHash: source.sourceHash,
                    title: position.0.map { output[$0] } ?? source.title,
                    description: position.1.map { output[$0] } ?? source.description, provenance: .machine)
            }
            // Only genuine complete translations enter persistent storage.
            try? await cache?.store(rows, language: target)
            guard gen == generation, !Task.isCancelled else { return }
            for row in rows { publish(row, generation: gen) }
        } catch {
            guard gen == generation, !Task.isCancelled else { return }
            let reason: TranslationFallback
            if case AchievementTranslationError.unsupportedLanguage = error { reason = .unsupported }
            else { reason = .unavailable }
            let until = ContinuousClock.now.advanced(by: .seconds(retryDelay))
            for source in missing { failed[key(source)] = Failure(until: until, reason: reason) }
        }
    }

    private func publish(_ row: CachedAchievementTranslation, generation gen: Int) {
        guard gen == generation else { return }
        let k = Key(id: row.achievementID, hash: row.sourceHash)
        if let latest = known[row.achievementID], latest.sourceHash != row.sourceHash { return }
        if memory[k] == nil {
            while memoryOrder.count >= memoryLimit { memory.removeValue(forKey: memoryOrder.removeFirst()) }
            memoryOrder.append(k)
        }
        memory[k] = row
        failed.removeValue(forKey: k)
    }

    private func notifyChange() {
        revision &+= 1
        NotificationCenter.default.post(name: Self.didChangeNotification, object: self)
    }
}
