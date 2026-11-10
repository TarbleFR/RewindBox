@preconcurrency import Flutter
import UIKit
import SwiftUI
import Combine

private enum AchievementMethodCommand: Sendable {
    case setLanguage(String?)
    case texts([AchievementSource])
    case retry
    case notImplemented
}

private struct AchievementMethodRow: Sendable {
    let id: Int
    let values: [String: String]
}

private enum AchievementMethodReply: Sendable {
    case done
    case texts([AchievementMethodRow])
    case invalidLanguage
    case notImplemented
}

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
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.session.role == .windowApplication && $0.activationState == .foregroundActive }) else { return }
        if window?.windowScene === scene { return }
        // A recreated application scene must not keep using a detached host.
        // Remove the old host before creating the replacement: there is one
        // mounted translation window even across scene restoration.
        window?.isHidden = true
        window?.rootViewController = nil
        window = nil
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

    nonisolated static func source(_ row: [String: Any]) -> AchievementSource? {
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
        let arguments = call.arguments as? [String: Any] ?? [:]
        let command: AchievementMethodCommand
        switch call.method {
        case "setLanguage": command = .setLanguage(arguments["language"] as? String)
        case "texts":
            command = .texts((arguments["achievements"] as? [[String: Any]] ?? []).compactMap(RBAchievementText.source))
        case "retry": command = .retry
        default: command = .notImplemented
        }
        // Only value types enter/leave the actor boundary. Flutter's unannotated
        // result closure stays here and is called synchronously on the same
        // platform thread, never captured or transferred into another actor.
        let reply = MainActor.assumeIsolated { handleOnMain(command) }
        switch reply {
        case .done: result(nil)
        case .texts(let rows):
            result(rows.map { row -> [String: Any] in
                var value: [String: Any] = row.values
                value["id"] = row.id
                return value
            })
        case .invalidLanguage:
            result(FlutterError(code: "invalid_language", message: "Unknown app language", details: nil))
        case .notImplemented: result(FlutterMethodNotImplemented)
        }
    }

    private func handleOnMain(_ command: AchievementMethodCommand) -> AchievementMethodReply {
        switch command {
        case .setLanguage(let language):
            guard let code = language,
                  AchievementLanguage.identifiers[code] != nil else {
                return .invalidLanguage
            }
            TranslationRuntime.shared.attachHost()
            AchievementTextProvider.shared.setLanguage(code)
            return .done
        case .texts(let sources):
            return .texts(sources.map { source in
                var value = RBAchievementText.payload(AchievementTextProvider.shared.text(for: source))
                value["sourceTitle"] = source.title
                value["sourceDescription"] = source.description
                return AchievementMethodRow(id: source.id, values: value)
            })
        case .retry:
            AchievementTextProvider.shared.retryUnavailable()
            return .done
        case .notImplemented: return .notImplemented
        }
    }
}
