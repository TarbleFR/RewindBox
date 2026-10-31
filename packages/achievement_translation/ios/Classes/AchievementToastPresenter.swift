import UIKit
import Combine

/// Independent of award state. Each owner gets an ordered, bounded display queue.
@objc(RBAchievementToast)
@MainActor
public final class AchievementToastPresenter: NSObject {
    private final class Queue {
        weak var owner: UIViewController?
        var tail: Task<Void, Never>?
        var count = 0
        init(owner: UIViewController) { self.owner = owner }
    }
    private static var queues: [ObjectIdentifier: Queue] = [:]

    @objc(presentOn:achievementID:title:description:suffix:duration:valid:)
    public static func present(on owner: UIViewController, achievementID: Int, title: String,
                               description: String, suffix: String, duration: Double,
                               valid: @escaping () -> Bool) {
        queues = queues.filter { $0.value.owner != nil || $0.value.count > 0 }
        let identity = ObjectIdentifier(owner)
        let queue = queues[identity] ?? Queue(owner: owner)
        queues[identity] = queue
        // A flood of progress updates must not retain an unbounded UI queue.
        guard queue.count < 32 else { return }
        queue.count += 1
        let previous = queue.tail
        queue.tail = Task { @MainActor [weak owner] in
            await previous?.value
            defer {
                queue.count -= 1
                if queue.count == 0 { queue.tail = nil; queues.removeValue(forKey: identity) }
            }
            guard let owner, owner.viewIfLoaded?.window != nil, valid() else { return }
            let source = AchievementSource(id: achievementID, title: title, description: description)
            let text: LocalizedAchievementText
            if achievementID > 0 {
                text = await AchievementTextProvider.shared.resolve(source, timeout: 0.25)
            } else {
                text = LocalizedAchievementText(title: title, description: description,
                    provenance: .original, fallback: .unavailable)
            }
            guard owner.viewIfLoaded?.window != nil, valid() else { return }
            let panel = UIVisualEffectView(effect: UIBlurEffect(style: .systemChromeMaterialDark))
            panel.translatesAutoresizingMaskIntoConstraints = false
            panel.layer.cornerRadius = 12
            panel.clipsToBounds = true
            panel.isUserInteractionEnabled = false
            let stack = UIStackView()
            stack.axis = .vertical
            stack.spacing = 3
            stack.translatesAutoresizingMaskIntoConstraints = false
            panel.contentView.addSubview(stack)
            func add(_ value: String, size: CGFloat, lines: Int) -> UILabel {
                let label = UILabel()
                label.text = value
                label.textColor = .white
                label.textAlignment = .natural
                label.font = .systemFont(ofSize: size)
                label.numberOfLines = lines
                label.accessibilityLabel = value
                label.isHidden = value.isEmpty
                stack.addArrangedSubview(label)
                return label
            }
            let titleLabel = add("🏆 " + text.title, size: 15, lines: 2)
            let descriptionLabel = add(text.description, size: 13, lines: 3)
            _ = add(suffix, size: 12, lines: 1) // Points/progress copied verbatim from the core.
            let noticeLabel = add(AchievementTranslationNotice.text(for: text, language: AchievementTextProvider.shared.language) ?? "",
                size: 11, lines: 2)
            let observer = AchievementTextProvider.shared.$revision.dropFirst().sink { _ in
                let updated = achievementID > 0 ? AchievementTextProvider.shared.text(for: source) : text
                titleLabel.text = "🏆 " + updated.title
                titleLabel.accessibilityLabel = updated.title
                descriptionLabel.text = updated.description
                descriptionLabel.accessibilityLabel = updated.description
                descriptionLabel.isHidden = updated.description.isEmpty
                let note = AchievementTranslationNotice.text(for: updated, language: AchievementTextProvider.shared.language)
                noticeLabel.text = note
                noticeLabel.isHidden = note == nil
            }
            defer { observer.cancel() }
            owner.view.addSubview(panel)
            NSLayoutConstraint.activate([
                panel.topAnchor.constraintEqualToSystemSpacingBelow(owner.view.safeAreaLayoutGuide.topAnchor, multiplier: 1),
                panel.centerXAnchor.constraint(equalTo: owner.view.centerXAnchor),
                panel.widthAnchor.constraint(lessThanOrEqualToConstant: 420),
                panel.leadingAnchor.constraint(greaterThanOrEqualTo: owner.view.safeAreaLayoutGuide.leadingAnchor, constant: 12),
                panel.trailingAnchor.constraint(lessThanOrEqualTo: owner.view.safeAreaLayoutGuide.trailingAnchor, constant: -12),
                stack.leadingAnchor.constraint(equalTo: panel.contentView.leadingAnchor, constant: 12),
                stack.trailingAnchor.constraint(equalTo: panel.contentView.trailingAnchor, constant: -12),
                stack.topAnchor.constraint(equalTo: panel.contentView.topAnchor, constant: 8),
                stack.bottomAnchor.constraint(equalTo: panel.contentView.bottomAnchor, constant: -8)
            ])
            // Re-check session ownership while displayed; no toast survives a game switch.
            let deadline = ContinuousClock.now.advanced(by: .seconds(min(8, max(1, duration))))
            while ContinuousClock.now < deadline, valid(), owner.view.window != nil, !Task.isCancelled {
                do { try await Task.sleep(for: .milliseconds(100)) } catch { break }
            }
            panel.removeFromSuperview()
        }
    }
}
