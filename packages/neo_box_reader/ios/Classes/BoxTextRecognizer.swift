// SPDX-License-Identifier: GPL-3.0-or-later
//
// Text recognition of a box scan. Platform-neutral (iOS and macOS) so the
// same code runs in the macOS CI test (packages/neo_box_reader/ci).

import Foundation
import ImageIO
import NaturalLanguage
import Vision

/// One recognised line, in normalised coordinates with a top-left origin.
public struct BoxTextLine {
    public let text: String
    public let confidence: Float
    public let x: Double
    public let y: Double
    public let width: Double
    public let height: Double

    public var dictionary: [String: Any] {
        ["text": text, "confidence": Double(confidence), "x": x, "y": y, "w": width, "h": height]
    }
}

public struct BoxTextRecognition {
    public let lines: [BoxTextLine]
    public let pixelWidth: Int
    public let pixelHeight: Int
    /// Recognition languages Vision was given ("auto" when it detected them).
    public let languages: [String]
}

public enum BoxTextRecognizerError: Error {
    case unreadableImage
}

public enum BoxTextRecognizer {
    /// Languages the accurate recogniser of this OS supports.
    public static func supportedLanguages() -> [String] {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        return (try? request.supportedRecognitionLanguages()) ?? []
    }

    /// Loads a scan, downscaled so that its longest side is at most
    /// [maxDimension] pixels (Vision gains nothing beyond, memory does).
    static func loadImage(path: String, maxDimension: Int) -> CGImage? {
        let url = URL(fileURLWithPath: path) as CFURL
        guard let source = CGImageSourceCreateWithURL(url, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxDimension,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        return CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
    }

    /// Recognises the text of the scan at [path].
    ///
    /// [languages] are hints from the region of the scan (`ja-JP` first for
    /// a Japanese edition). Without usable hints, or when the hinted pass
    /// finds almost nothing, Vision's automatic language detection runs and
    /// the richer result is kept. Nothing is ever invented: only what Vision
    /// returns is passed on, with its confidence.
    public static func recognize(path: String, languages: [String], maxDimension: Int = 4096) throws -> BoxTextRecognition {
        guard let image = loadImage(path: path, maxDimension: maxDimension) else {
            throw BoxTextRecognizerError.unreadableImage
        }
        let supported = Set(supportedLanguages())
        let hints = languages.filter { supported.contains($0) }
        var best = try run(image: image, languages: hints)
        if !hints.isEmpty && best.lines.count < 3 {
            let auto = try run(image: image, languages: [])
            if score(auto) > score(best) { best = auto }
        }
        return best
    }

    static func score(_ r: BoxTextRecognition) -> Double {
        r.lines.reduce(0) { $0 + Double($1.text.count) * Double($1.confidence) }
    }

    static func run(image: CGImage, languages: [String]) throws -> BoxTextRecognition {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        if languages.isEmpty {
            request.automaticallyDetectsLanguage = true
        } else {
            request.recognitionLanguages = languages
        }
        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        try handler.perform([request])
        var lines: [BoxTextLine] = []
        for observation in request.results ?? [] {
            guard let candidate = observation.topCandidates(1).first else { continue }
            let text = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty { continue }
            let box = observation.boundingBox
            lines.append(BoxTextLine(
                text: text,
                confidence: candidate.confidence,
                x: Double(box.origin.x),
                y: Double(1 - box.origin.y - box.height),
                width: Double(box.width),
                height: Double(box.height)
            ))
        }
        return BoxTextRecognition(
            lines: lines,
            pixelWidth: image.width,
            pixelHeight: image.height,
            languages: languages.isEmpty ? ["auto"] : languages
        )
    }

    /// Dominant language of [text] (BCP 47, e.g. "ja", "zh-Hans") with its
    /// probability, or nil when undetermined.
    public static func detectLanguage(_ text: String) -> (String, Double)? {
        let recognizer = NLLanguageRecognizer()
        recognizer.processString(text)
        guard let language = recognizer.dominantLanguage, language != .undetermined else { return nil }
        let p = recognizer.languageHypotheses(withMaximum: 1)[language] ?? 0
        return (language.rawValue, p)
    }
}
