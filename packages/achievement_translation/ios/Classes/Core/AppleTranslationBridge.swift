import Foundation
import SwiftUI
import Translation

/// A job snapshot is bound to a SwiftUI view identity. Late callbacks cannot
/// translate another job with the old session, even after cancellation/timeout.
public struct AchievementTranslationJob: Identifiable, Sendable {
    public let id: UUID
    let texts: [String]
    let source: String
    let target: String
}

@MainActor
public final class AppleTranslationBridge: ObservableObject, AchievementTranslator {
    @Published public private(set) var job: AchievementTranslationJob?
    private var queue: [AchievementTranslationJob] = []
    private var continuations: [UUID: CheckedContinuation<[String], any Error>] = [:]
    private var timer: Task<Void, Never>?
    private let hostTimeout: Duration

    public init(hostTimeout: Duration = .seconds(120)) { self.hostTimeout = hostTimeout }

    public func translate(_ texts: [String], from source: String, to target: String) async throws -> [String] {
        try Task.checkCancellation()
        guard !texts.isEmpty else { return [] }
        let id = UUID()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                guard !Task.isCancelled else { continuation.resume(throwing: CancellationError()); return }
                continuations[id] = continuation
                queue.append(AchievementTranslationJob(id: id, texts: texts, source: source, target: target))
                pump()
            }
        } onCancel: {
            Task { @MainActor [weak self] in self?.finish(id: id, result: .failure(CancellationError())) }
        }
    }

    private func pump() {
        guard job == nil, !queue.isEmpty else { return }
        let next = queue.removeFirst()
        job = next
        timer = Task { [weak self, hostTimeout] in
            do { try await Task.sleep(for: hostTimeout) } catch { return }
            self?.finish(id: next.id, result: .failure(AchievementTranslationError.hostUnavailable))
        }
    }

    func isCurrent(_ id: UUID) -> Bool { job?.id == id && continuations[id] != nil }

    func finish(id: UUID, result: Result<[String], any Error>) {
        guard let continuation = continuations.removeValue(forKey: id) else { return }
        queue.removeAll { $0.id == id }
        if job?.id == id {
            timer?.cancel()
            timer = nil
            job = nil
        }
        continuation.resume(with: result)
        pump()
    }

    /// Testable response validation. Duplicate/missing/foreign IDs are errors.
    static func orderedResults(_ responses: [(String?, String)], count: Int) throws -> [String] {
        var output = [String?](repeating: nil, count: count)
        for (identifier, text) in responses {
            guard let identifier, let index = Int(identifier), output.indices.contains(index), output[index] == nil else {
                throw AchievementTranslationError.mismatchedResponse
            }
            output[index] = text
        }
        guard output.allSatisfy({ $0 != nil }) else { throw AchievementTranslationError.mismatchedResponse }
        return output.compactMap { $0 }
    }
}

@MainActor
public struct AchievementTranslationHost: View {
    @ObservedObject private var bridge: AppleTranslationBridge
    public init(bridge: AppleTranslationBridge) { self.bridge = bridge }

    public var body: some View {
        Group {
            if let job = bridge.job {
                AchievementTranslationJobView(job: job, bridge: bridge).id(job.id)
            } else {
                Color.clear
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

@MainActor
private struct AchievementTranslationJobView: View {
    let job: AchievementTranslationJob
    let bridge: AppleTranslationBridge

    var body: some View {
        Color.clear.translationTask(TranslationSession.Configuration(
            source: Locale.Language(identifier: job.source), target: Locale.Language(identifier: job.target)
        )) { session in
            // Session and Request never leave this callback or enter a singleton.
            // A fresh view identity, rather than an equal configuration assignment,
            // starts each job, including repeated requests for the same pair.
            guard await bridge.isCurrent(job.id) else { return }
            do {
                try Task.checkCancellation()
                let availability = LanguageAvailability()
                let status = await availability.status(from: Locale.Language(identifier: job.source),
                                                       to: Locale.Language(identifier: job.target))
                guard status != .unsupported else { throw AchievementTranslationError.unsupportedLanguage }
                try Task.checkCancellation()
                let requests = job.texts.enumerated().map {
                    TranslationSession.Request(sourceText: $0.element, clientIdentifier: String($0.offset))
                }
                let responses = try await session.translations(from: requests)
                try Task.checkCancellation()
                let values = responses.map { ($0.clientIdentifier, $0.targetText) }
                let ordered = try await AppleTranslationBridge.orderedResults(values, count: job.texts.count)
                await bridge.finish(id: job.id, result: .success(ordered))
            } catch {
                await bridge.finish(id: job.id, result: .failure(error))
            }
        }
    }
}
