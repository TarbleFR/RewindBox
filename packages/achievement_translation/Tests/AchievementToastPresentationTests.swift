import XCTest
import UIKit
@testable import AchievementTranslation

/// Real UIKit presentation with deterministic translators. This exercises the
/// host queue and labels, not Apple's device-only model or a game's award logic.
@MainActor
final class AchievementToastPresentationTests: XCTestCase {
    private func makeSurface() -> (UIWindow, UIViewController) {
        let frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .first { $0.session.role == .windowApplication }
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: frame)
        window.frame = frame
        let owner = UIViewController()
        window.rootViewController = owner
        window.isHidden = false
        owner.loadViewIfNeeded()
        return (window, owner)
    }

    private func labels(in view: UIView) -> [String] {
        let own = (view as? UILabel).flatMap { $0.text }.map { [$0] } ?? []
        return own + view.subviews.flatMap { labels(in: $0) }
    }

    private func waitFor(_ predicate: @MainActor () -> Bool,
                         timeout: Duration = .seconds(2)) async throws -> Bool {
        let deadline = ContinuousClock.now.advanced(by: timeout)
        while !predicate() {
            if ContinuousClock.now >= deadline { return false }
            try await Task.sleep(for: .milliseconds(10))
        }
        return true
    }

    func testRapidProgressDisplaysOriginalThenRefreshesLanguage() async throws {
        let provider = AchievementTextProvider.shared
        provider.configure(translator: SlowTranslator())
        provider.setLanguage("fr")
        let (window, owner) = makeSurface()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            provider.setLanguage("en")
        }
        XCTAssertTrue(owner.view.window === window)
        let id = Int.random(in: 1_000_000_000...1_999_999_999)
        let title = "Progrès Éclair 勇者"
        let description = "إنجاز البداية 🎮"
        let source = AchievementSource(id: id, title: title, description: description)
        var active = true
        var displayedDuringBurst = false
        // A cold translator takes 60 seconds. Every event replaces the prior
        // progress well before the 250 ms unlock lookup timeout.
        for progress in 1...12 {
            AchievementToastPresenter.present(on: owner, achievementID: id, title: title,
                description: description, suffix: "\(progress)/12", duration: 4, kind: 2,
                surface: { [weak owner] in owner?.view }, valid: { active })
            try await Task.sleep(for: .milliseconds(20))
            displayedDuringBurst = displayedDuringBurst || labels(in: owner.view).contains("🏆 " + title)
        }
        XCTAssertTrue(displayedDuringBurst, "Progress must remain visible while translation is pending")
        XCTAssertEqual(provider.text(for: source).provenance, .original)
        XCTAssertTrue(labels(in: owner.view).contains(description))
        XCTAssertTrue(labels(in: owner.view).contains("12/12"))
        XCTAssertEqual(owner.view.subviews.filter { $0 is UIVisualEffectView }.count, 1)

        provider.setLanguage("ja") // Same visible panel, no new presentation request.
        let refreshed = try await waitFor { self.labels(in: owner.view).contains("🏆 [ja-JP] " + title) }
        XCTAssertTrue(refreshed)
        XCTAssertTrue(labels(in: owner.view).contains("[ja-JP] " + description))
        XCTAssertTrue(labels(in: owner.view).contains("12/12"))
        active = false
        let dismissed = try await waitFor { owner.view.subviews.allSatisfy { !($0 is UIVisualEffectView) } }
        XCTAssertTrue(dismissed, "A stopped game must remove its overlay")
    }

    func testUnlocksKeepOrderAndProgressCannotReplaceThem() async throws {
        let provider = AchievementTextProvider.shared
        provider.setLanguage("en")
        let (window, owner) = makeSurface()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        XCTAssertTrue(owner.view.window === window)
        var active = true
        for (id, title, suffix) in [(900001, "First unlock", "25"), (900002, "Second unlock", "50")] {
            AchievementToastPresenter.present(on: owner, achievementID: id, title: title,
                description: "Original requirements", suffix: suffix, duration: 1, kind: 1,
                surface: { [weak owner] in owner?.view }, valid: { active })
        }
        AchievementToastPresenter.present(on: owner, achievementID: 900003, title: "Progress must wait",
            description: "", suffix: "3/5", duration: 1, kind: 2,
            surface: { [weak owner] in owner?.view }, valid: { active })
        let first = try await waitFor { self.labels(in: owner.view).contains("🏆 First unlock") }
        XCTAssertTrue(first)
        XCTAssertTrue(labels(in: owner.view).contains("25"))
        XCTAssertFalse(labels(in: owner.view).contains("🏆 Second unlock"))
        XCTAssertFalse(labels(in: owner.view).contains("🏆 Progress must wait"))
        let second = try await waitFor { self.labels(in: owner.view).contains("🏆 Second unlock") }
        XCTAssertTrue(second)
        XCTAssertTrue(labels(in: owner.view).contains("50"))
        XCTAssertFalse(labels(in: owner.view).contains("🏆 First unlock"))
        active = false
        let dismissed = try await waitFor { owner.view.subviews.allSatisfy { !($0 is UIVisualEffectView) } }
        XCTAssertTrue(dismissed)
    }
}
