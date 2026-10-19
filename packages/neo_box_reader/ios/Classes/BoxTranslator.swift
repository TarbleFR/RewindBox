// SPDX-License-Identifier: GPL-3.0-or-later
//
// On-device translation with Apple's Translation framework (iOS 18).
//
// iOS 18 hands out a TranslationSession only to a SwiftUI view through
// `.translationTask`. A 1-point, invisible hosting controller is therefore
// attached to the visible view controller for the time of one request; it is
// also what lets iOS show its own prompt to download a missing language.
// Nothing is translated by a server of NeoStation.

import Foundation
import SwiftUI
import Translation
import UIKit

enum BoxTranslatorError: Error {
    case noPresenter
    case unsupported
    case notInstalled(String)
    case failed(String)
}

enum BoxTranslator {
    static func language(_ identifier: String?) -> Locale.Language? {
        guard let identifier, !identifier.isEmpty else { return nil }
        return Locale.Language(identifier: identifier)
    }

    /// "installed", "supported" (can be downloaded) or "unsupported".
    static func status(source: String?, target: String, sample: String?) async -> String {
        let availability = LanguageAvailability()
        let to = Locale.Language(identifier: target)
        let status: LanguageAvailability.Status
        if let from = language(source) {
            status = await availability.status(from: from, to: to)
        } else if let sample, !sample.isEmpty {
            status = (try? await availability.status(for: sample, to: to)) ?? .unsupported
        } else {
            return "unsupported"
        }
        switch status {
        case .installed: return "installed"
        case .supported: return "supported"
        case .unsupported: return "unsupported"
        @unknown default: return "unsupported"
        }
    }

    /// Identifiers of the languages Translation supports on this device.
    static func supportedLanguages() async -> [String] {
        let languages = await LanguageAvailability().supportedLanguages
        return languages.map { $0.minimalIdentifier }
    }

    /// The hosting controller of one request and whether it has answered.
    final class Request {
        var host: UIViewController?
        var finished = false
    }

    @MainActor
    static func translate(
        texts: [String],
        source: String?,
        target: String,
        presenter: UIViewController,
        completion: @escaping (Result<([String], String?), Error>) -> Void
    ) {
        let configuration = TranslationSession.Configuration(source: language(source), target: language(target))
        let request = Request()
        let finish: @MainActor (Result<([String], String?), Error>) -> Void = { result in
            if request.finished { return }
            request.finished = true
            if let host = request.host {
                host.willMove(toParent: nil)
                host.view.removeFromSuperview()
                host.removeFromParent()
            }
            request.host = nil
            completion(result)
        }
        let view = BoxTranslationTaskView(configuration: configuration, texts: texts, finish: finish)
        let controller = UIHostingController(rootView: view)
        controller.view.frame = CGRect(x: 0, y: 0, width: 1, height: 1)
        controller.view.backgroundColor = .clear
        controller.view.isUserInteractionEnabled = false
        controller.view.alpha = 0.011
        presenter.addChild(controller)
        presenter.view.addSubview(controller.view)
        controller.didMove(toParent: presenter)
        request.host = controller
    }
}

struct BoxTranslationTaskView: View {
    let configuration: TranslationSession.Configuration
    let texts: [String]
    let finish: @MainActor (Result<([String], String?), Error>) -> Void

    var body: some View {
        Color.clear
            .frame(width: 1, height: 1)
            .translationTask(configuration) { session in
                do {
                    try await session.prepareTranslation()
                    let requests = texts.enumerated().map { index, text in
                        TranslationSession.Request(sourceText: text, clientIdentifier: String(index))
                    }
                    let responses = try await session.translations(from: requests)
                    var output = Array(repeating: "", count: texts.count)
                    var detected: String?
                    for response in responses {
                        if detected == nil { detected = response.sourceLanguage.minimalIdentifier }
                        if let id = response.clientIdentifier, let index = Int(id), index < output.count {
                            output[index] = response.targetText
                        }
                    }
                    let answer = (output, detected)
                    await finish(.success(answer))
                } catch {
                    await finish(.failure(error))
                }
            }
    }
}
