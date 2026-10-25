import UIKit

/// Resolve UIKit ownership when launching, after Flutter has attached its view.
enum MeloNXPresentation {
    static func resolve(preferred: UIViewController?) -> UIViewController? {
        precondition(Thread.isMainThread)
        func eligible(_ window: UIWindow) -> Bool {
            guard let scene = window.windowScene else { return false }
            return scene.activationState == .foregroundActive &&
                scene.session.role == .windowApplication &&
                !window.isHidden && window.alpha > 0 && window.windowLevel == .normal
        }
        var roots: [UIViewController] = []
        if let preferred, let window = preferred.viewIfLoaded?.window, eligible(window) {
            roots.append(preferred)
        }
        let windows = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }.flatMap(\.windows)
            .filter(eligible).sorted { $0.isKeyWindow && !$1.isKeyWindow }
        roots += windows.compactMap(\.rootViewController)
        for root in roots {
            var current = root
            while true {
                // A file picker may still be finishing dismissal. Wait instead
                // of presenting behind it or adopting an external-display scene.
                if current.isBeingDismissed || current.isBeingPresented { break }
                if let next = current.presentedViewController { current = next }
                else if let nav = current as? UINavigationController, let next = nav.visibleViewController { current = next }
                else if let tabs = current as? UITabBarController, let next = tabs.selectedViewController { current = next }
                else {
                    if let window = current.viewIfLoaded?.window, eligible(window) { return current }
                    break
                }
            }
        }
        return nil
    }

    static func whenReady(preferred: @escaping () -> UIViewController?,
                          isCurrent: @escaping () -> Bool,
                          completion: @escaping (UIViewController?) -> Void) {
        precondition(Thread.isMainThread)
        let deadline = ProcessInfo.processInfo.systemUptime + 2
        func attempt() {
            guard isCurrent() else { return }
            if let controller = resolve(preferred: preferred()) { completion(controller) }
            else if ProcessInfo.processInfo.systemUptime >= deadline { completion(nil) }
            else { DispatchQueue.main.asyncAfter(deadline: .now() + 0.05, execute: attempt) }
        }
        attempt()
    }
}
