@preconcurrency import Flutter
import UIKit
import SwiftUI
import Combine

/// A non-key window keeps the one translation host mounted while Flutter presents
/// a full-screen native game controller. It only receives touches for Apple UI.
@MainActor
private final class TranslationHostWindow: UIWindow {
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        guard rootViewController?.presentedViewController != nil else { return nil }
        return super.hitTest(point, with: event)
    }
}

@MainActor
private final class TranslationRuntime {
    static let shared = TranslationRuntime()
    let bridge = AppleTranslationBridge()
    private var window: TranslationHostWindow?
    private var foreground: AnyCancellable?

    private init() {
        AchievementTextProvider.shared.configure(translator: bridge)
        foreground = NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)
            .receive(on: RunLoop.main).sink { [weak self] _ in
                MainActor.assumeIsolated {
                    self?.attachHost()
                    AchievementTextProvider.shared.retryUnavailable()
                }
            }
    }

    func attachHost() {
        guard window == nil else { return }
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.session.role == .windowApplication && $0.activationState == .foregroundActive }) else { return }
        let host = UIHostingController(rootView: AchievementTranslationHost(bridge: bridge))
        host.view.backgroundColor = .clear
        let window = TranslationHostWindow(windowScene: scene)
        window.windowLevel = .normal + 1
        window.backgroundColor = .clear
        window.rootViewController = host
        window.isHidden = false // Never make this window key or replace the game controller.
        self.window = window
    }
}

@objc(RBAchievementText)
@MainActor
public final class RBAchievementText: NSObject {
    static func payload(_ text: LocalizedAchievementText) -> [String: String] {
        var result = ["title": text.title, "description": text.description,
                      "provenance": text.provenance.rawValue,
                      "language": AchievementTextProvider.shared.language]
        result["notice"] = AchievementTranslationNotice.text(for: text, language: AchievementTextProvider.shared.language)
        result["fallback"] = text.fallback?.rawValue
        return result
    }

    @objc(resolveID:title:description:completion:)
    public static func resolve(id: Int, title: String, description: String,
                               completion: @escaping ([String: String]) -> Void) {
        TranslationRuntime.shared.attachHost()
        guard id > 0 else {
            completion(payload(LocalizedAchievementText(title: title, description: description,
                provenance: .original, fallback: .unavailable)))
            return
        }
        let source = AchievementSource(id: id, title: title, description: description)
        Task { @MainActor in
            let text = await AchievementTextProvider.shared.resolve(source, timeout: 0.25)
            completion(payload(text))
        }
    }

    @objc(prefetch:)
    public static func prefetch(_ achievements: [[String: Any]]) {
        TranslationRuntime.shared.attachHost()
        AchievementTextProvider.shared.prefetch(achievements.compactMap(source))
    }

    static func source(_ row: [String: Any]) -> AchievementSource? {
        guard let id = row["id"] as? NSNumber, id.intValue > 0,
              let title = row["title"] as? String, let description = row["description"] as? String else { return nil }
        return AchievementSource(id: id.intValue, title: title, description: description)
    }
}

@MainActor
public final class AchievementTranslationPlugin: NSObject, FlutterPlugin {
    private let channel: FlutterMethodChannel
    private var observer: AnyCancellable?

    private init(channel: FlutterMethodChannel) {
        self.channel = channel
        super.init()
        _ = TranslationRuntime.shared
        observer = AchievementTextProvider.shared.$revision.dropFirst().sink { [weak self] revision in
            self?.channel.invokeMethod("revision", arguments: ["revision": revision,
                "language": AchievementTextProvider.shared.language,
                "appLanguage": AchievementLanguage.identifiers.first {
                    $0.value == AchievementTextProvider.shared.language
                }?.key ?? "en"])
        }
    }

    public nonisolated static func register(with registrar: FlutterPluginRegistrar) {
        // Flutter's default iOS registrar and method channel callbacks execute
        // on the platform main thread. Keep non-Sendable ObjC values in this
        // synchronous boundary instead of transferring them into a Task.
        MainActor.assumeIsolated {
            let channel = FlutterMethodChannel(name: "rewindbox/achievement_translation", binaryMessenger: registrar.messenger())
            let instance = AchievementTranslationPlugin(channel: channel)
            registrar.addMethodCallDelegate(instance, channel: channel)
        }
    }

    public nonisolated func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        MainActor.assumeIsolated { handleOnMain(call, result: result) }
    }

    private func handleOnMain(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        let arguments = call.arguments as? [String: Any] ?? [:]
        switch call.method {
        case "setLanguage":
            guard let code = arguments["language"] as? String,
                  AchievementLanguage.identifiers[code] != nil else {
                result(FlutterError(code: "invalid_language", message: "Unknown app language", details: nil)); return
            }
            TranslationRuntime.shared.attachHost()
            AchievementTextProvider.shared.setLanguage(code)
            result(nil)
        case "texts":
            let rows = arguments["achievements"] as? [[String: Any]] ?? []
            let response = rows.compactMap { row -> [String: Any]? in
                guard let source = RBAchievementText.source(row) else { return nil }
                var value: [String: Any] = RBAchievementText.payload(AchievementTextProvider.shared.text(for: source))
                value["id"] = source.id
                value["sourceTitle"] = source.title
                value["sourceDescription"] = source.description
                return value
            }
            result(response)
        case "retry":
            AchievementTextProvider.shared.retryUnavailable()
            result(nil)
        default: result(FlutterMethodNotImplemented)
        }
    }
}
