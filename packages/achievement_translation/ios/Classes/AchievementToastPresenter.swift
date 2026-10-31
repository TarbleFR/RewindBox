import UIKit
import Combine

/// Independent of award state. Each owner gets an ordered unlock display queue;
/// each translation lookup and displayed toast has a bounded lifetime.
@objc(RBAchievementToast)
@MainActor
public final class AchievementToastPresenter: NSObject {
    private final class Queue {
        weak var owner: UIViewController?
        var tail: Task<Void, Never>?
        var count = 0
        var progressID: UUID?
        var progress: Task<Void, Never>?
        init(owner: UIViewController) { self.owner = owner }
    }
    private static var queues: [ObjectIdentifier: Queue] = [:]

    @objc(presentOn:achievementID:title:description:suffix:duration:kind:surface:valid:)
    public static func present(on owner: UIViewController, achievementID: Int, title: String,
                               description: String, suffix: String, duration: Double,
                               kind: Int, surface: @escaping () -> UIView?, valid: @escaping () -> Bool) {
        queues = queues.filter { $0.value.owner != nil || $0.value.count > 0 }
        let identity = ObjectIdentifier(owner)
        let queue = queues[identity] ?? Queue(owner: owner)
        queues[identity] = queue
        let isProgress = kind == 2
        // Progress is coalesced and never occupies/delays the unlock FIFO.
        if isProgress && queue.count > 0 { return }
        let token = UUID()
        queue.progress?.cancel()
        if isProgress { queue.progressID = token }
        else { queue.progress = nil; queue.progressID = nil; queue.count += 1 }
        let previous = isProgress ? nil : queue.tail
        let task = Task { @MainActor [weak owner] in
            await previous?.value
            defer {
                if isProgress {
                    if queue.progressID == token { queue.progress = nil; queue.progressID = nil }
                } else {
                    queue.count -= 1
                    if queue.count == 0 { queue.tail = nil }
                }
                if queue.count == 0 && queue.progressID == nil { queues.removeValue(forKey: identity) }
            }
            guard let owner, owner.viewIfLoaded?.window != nil, valid(), !Task.isCancelled else { return }
            let source = AchievementSource(id: achievementID, title: title, description: description)
            let text: LocalizedAchievementText
            if achievementID > 0 {
                text = await AchievementTextProvider.shared.resolve(source, timeout: 0.25)
            } else {
                text = LocalizedAchievementText(title: title, description: description,
                    provenance: .original, fallback: .unavailable)
            }
            guard let initialSurface = surface(), initialSurface.window != nil, valid(), !Task.isCancelled else { return }
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
            @MainActor func add(_ value: String, size: CGFloat, lines: Int) -> UILabel {
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
            var attachedSurface: UIView?
            var surfaceConstraints: [NSLayoutConstraint] = []
            NSLayoutConstraint.activate([
                stack.leadingAnchor.constraint(equalTo: panel.contentView.leadingAnchor, constant: 12),
                stack.trailingAnchor.constraint(equalTo: panel.contentView.trailingAnchor, constant: -12),
                stack.topAnchor.constraint(equalTo: panel.contentView.topAnchor, constant: 8),
                stack.bottomAnchor.constraint(equalTo: panel.contentView.bottomAnchor, constant: -8)
            ])
            @MainActor func attach(to target: UIView) {
                guard attachedSurface !== target else { return }
                NSLayoutConstraint.deactivate(surfaceConstraints)
                panel.removeFromSuperview()
                target.addSubview(panel)
                attachedSurface = target
                surfaceConstraints = [
                    panel.topAnchor.constraint(equalTo: target.safeAreaLayoutGuide.topAnchor, constant: 8),
                    panel.centerXAnchor.constraint(equalTo: target.centerXAnchor),
                    panel.widthAnchor.constraint(lessThanOrEqualToConstant: 420),
                    panel.leadingAnchor.constraint(greaterThanOrEqualTo: target.safeAreaLayoutGuide.leadingAnchor, constant: 12),
                    panel.trailingAnchor.constraint(lessThanOrEqualTo: target.safeAreaLayoutGuide.trailingAnchor, constant: -12)
                ]
                NSLayoutConstraint.activate(surfaceConstraints)
            }
            attach(to: initialSurface)
            // Re-check session ownership while displayed; no toast survives a game switch.
            let deadline = ContinuousClock.now.advanced(by: .seconds(min(8, max(1, duration))))
            while ContinuousClock.now < deadline, valid(), owner.view.window != nil, !Task.isCancelled {
                if let target = surface(), target.window != nil { attach(to: target) }
                do { try await Task.sleep(for: .milliseconds(100)) } catch { break }
            }
            panel.removeFromSuperview()
        }
        if isProgress { queue.progress = task } else { queue.tail = task }
    }
}
