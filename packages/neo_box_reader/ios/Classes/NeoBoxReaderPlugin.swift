// SPDX-License-Identifier: GPL-3.0-or-later

import Flutter
import UIKit

/// Channel `neostation/neo_box_reader` (docs/game-box-3d.md § 7).
///
/// Errors carry a stable code for the Flutter side, which shows its own
/// translated explanation; the native message is only the technical detail.
public final class NeoBoxReaderPlugin: NSObject, FlutterPlugin {
    private let work = DispatchQueue(label: "neostation.box-reader", qos: .userInitiated)

    public static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(name: "neostation/neo_box_reader", binaryMessenger: registrar.messenger())
        registrar.addMethodCallDelegate(NeoBoxReaderPlugin(), channel: channel)
    }

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        let args = call.arguments as? [String: Any] ?? [:]
        switch call.method {
        case "capabilities":
            work.async {
                let languages = BoxTextRecognizer.supportedLanguages()
                DispatchQueue.main.async {
                    // The pod requires iOS 18, where TranslationSession exists.
                    result(["ocr": true, "translation": true, "ocrLanguages": languages])
                }
            }
        case "recognize":
            guard let path = args["path"] as? String, FileManager.default.fileExists(atPath: path) else {
                result(FlutterError(code: "missing-image", message: "No scan at the given path", details: nil))
                return
            }
            let languages = args["languages"] as? [String] ?? []
            work.async {
                do {
                    let recognition = try BoxTextRecognizer.recognize(path: path, languages: languages)
                    let payload: [String: Any] = [
                        "lines": recognition.lines.map { $0.dictionary },
                        "width": recognition.pixelWidth,
                        "height": recognition.pixelHeight,
                        "languages": recognition.languages,
                    ]
                    DispatchQueue.main.async { result(payload) }
                } catch {
                    DispatchQueue.main.async {
                        result(FlutterError(code: "ocr-failed", message: String(describing: error), details: nil))
                    }
                }
            }
        case "detectLanguage":
            let text = args["text"] as? String ?? ""
            work.async {
                let guess = BoxTextRecognizer.detectLanguage(text)
                DispatchQueue.main.async {
                    if case let (language, p)? = guess {
                        result(["language": language, "confidence": p])
                    } else {
                        result(["language": NSNull(), "confidence": 0.0])
                    }
                }
            }
        case "translationStatus":
            let target = args["target"] as? String ?? "en"
            let source = args["source"] as? String
            let sample = args["sample"] as? String
            Task {
                let status = await BoxTranslator.status(source: source, target: target, sample: sample)
                await MainActor.run { result(status) }
            }
        case "supportedTranslationLanguages":
            Task {
                let languages = await BoxTranslator.supportedLanguages()
                await MainActor.run { result(languages) }
            }
        case "translate":
            let texts = args["texts"] as? [String] ?? []
            let target = args["target"] as? String ?? "en"
            let source = args["source"] as? String
            guard !texts.isEmpty else {
                result(["texts": [String](), "source": Self.nullable(source)])
                return
            }
            guard let presenter = Self.visibleController() else {
                result(FlutterError(code: "no-presenter", message: "No visible view controller", details: nil))
                return
            }
            Task { @MainActor in
                let sample = texts.joined(separator: "\n")
                let before = await BoxTranslator.status(source: source, target: target, sample: sample)
                if before == "unsupported" {
                    result(FlutterError(code: "unsupported", message: "Language pair not supported", details: nil))
                    return
                }
                BoxTranslator.translate(texts: texts, source: source, target: target, presenter: presenter) { outcome in
                    switch outcome {
                    case .success(let (translated, detected)):
                        result(["texts": translated, "source": Self.nullable(detected ?? source)])
                    case .failure(let error):
                        Task { @MainActor in
                            // A language still not installed after the request means
                            // the download was declined or could not run.
                            let after = await BoxTranslator.status(source: source, target: target, sample: sample)
                            let code = after == "supported" ? "not-installed" : (error is CancellationError ? "cancelled" : "failed")
                            result(FlutterError(code: code, message: String(describing: error), details: nil))
                        }
                    }
                }
            }
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    static func nullable(_ value: String?) -> Any {
        if let value { return value }
        return NSNull()
    }

    /// Topmost presented view controller of the key window.
    static func visibleController() -> UIViewController? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let window = scenes.flatMap { $0.windows }.first { $0.isKeyWindow } ?? scenes.first?.windows.first
        var controller = window?.rootViewController
        while let presented = controller?.presentedViewController, !presented.isBeingDismissed {
            controller = presented
        }
        return controller
    }
}
