// SPDX-License-Identifier: GPL-3.0-or-later
//
// Executable check of the box reader's recognition code (BoxTextRecognizer)
// with Apple's real frameworks, built for macOS and for the iOS Simulator by
// .github/workflows/game-box-checks.yml.
//
// For each of NeoStation's twelve languages it draws a back-cover-like text
// with the system font for that language, recognises it with the plugin's
// own code and the hints the app would give, and measures how close the
// result is. It also checks the language detection, lists the recognition
// languages of this OS and the Translation availability of the twelve targets.
// The report is JSON on stdout; the exit status is 1 when a check fails.

import CoreGraphics
import CoreText
import Foundation
import ImageIO
#if canImport(Translation)
import Translation
#endif

struct Sample {
    let code: String       // NeoStation code
    let hints: [String]    // what the app passes for that edition's region
    let detect: String     // NaturalLanguage identifier expected
    let text: String
}

let samples: [Sample] = [
    Sample(code: "en", hints: ["en-US"], detect: "en", text: "Explore forty dangerous caves and defeat the Shadow King."),
    Sample(code: "fr", hints: ["fr-FR", "en-US"], detect: "fr", text: "Explorez quarante grottes dangereuses et battez le roi des ombres."),
    Sample(code: "de", hints: ["de-DE", "en-US"], detect: "de", text: "Erkunde vierzig gefährliche Höhlen und besiege den Schattenkönig."),
    Sample(code: "es", hints: ["es-ES", "en-US"], detect: "es", text: "Explora cuarenta cuevas peligrosas y derrota al rey de las sombras."),
    Sample(code: "it", hints: ["it-IT", "en-US"], detect: "it", text: "Esplora quaranta grotte pericolose e sconfiggi il re delle ombre."),
    Sample(code: "pt", hints: ["pt-BR", "en-US"], detect: "pt", text: "Explore quarenta cavernas perigosas e derrote o rei das sombras."),
    Sample(code: "ru", hints: ["ru-RU", "en-US"], detect: "ru", text: "Исследуйте сорок опасных пещер и победите короля теней."),
    Sample(code: "id", hints: ["en-US"], detect: "id", text: "Jelajahi empat puluh gua berbahaya dan kalahkan raja bayangan."),
    Sample(code: "ja", hints: ["ja-JP", "en-US"], detect: "ja", text: "四十の危険な洞窟を探検して、影の王を倒そう。"),
    Sample(code: "ko", hints: ["ko-KR", "en-US"], detect: "ko", text: "위험한 동굴 마흔 곳을 탐험하고 그림자 왕을 물리치세요."),
    Sample(code: "zh", hints: ["zh-Hans", "en-US"], detect: "zh-Hans", text: "探索四十个危险的洞穴，打败影子之王。"),
    Sample(code: "zh_Hant", hints: ["zh-Hant", "en-US"], detect: "zh-Hant", text: "探索四十個危險的洞穴，打敗影子之王。"),
]

func render(_ text: String, language: String, to path: String) -> Bool {
    let width = 1400, height = 360
    guard let space = CGColorSpace(name: CGColorSpace.sRGB),
          let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                              space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
    ctx.setFillColor(CGColor(red: 0.08, green: 0.08, blue: 0.12, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    let font = CTFontCreateUIFontForLanguage(.system, 44, language as CFString)
        ?? CTFontCreateWithName("Helvetica" as CFString, 44, nil)
    let attributes: [CFString: Any] = [
        kCTFontAttributeName: font,
        kCTForegroundColorAttributeName: CGColor(red: 1, green: 1, blue: 1, alpha: 1),
    ]
    let attributed = CFAttributedStringCreate(nil, text as CFString, attributes as CFDictionary)!
    let framesetter = CTFramesetterCreateWithAttributedString(attributed)
    let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: 0, length: 0),
                                         CGPath(rect: CGRect(x: 60, y: 40, width: width - 120, height: height - 80), transform: nil), nil)
    CTFrameDraw(frame, ctx)
    guard let image = ctx.makeImage(),
          let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, "public.png" as CFString, 1, nil) else { return false }
    CGImageDestinationAddImage(dest, image, nil)
    return CGImageDestinationFinalize(dest)
}

/// Similarity of two strings ignoring spaces and punctuation (1 = equal).
func similarity(_ a: String, _ b: String) -> Double {
    func norm(_ s: String) -> [Character] {
        Array(s.lowercased().filter { $0.isLetter || $0.isNumber })
    }
    let x = norm(a), y = norm(b)
    if x.isEmpty || y.isEmpty { return 0 }
    var previous = Array(0...y.count)
    for i in 1...x.count {
        var current = [i] + Array(repeating: 0, count: y.count)
        for j in 1...y.count {
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x[i - 1] == y[j - 1] ? 0 : 1))
        }
        previous = current
    }
    return 1 - Double(previous[y.count]) / Double(max(x.count, y.count))
}

var failures: [String] = []
var results: [[String: Any]] = []
let supported = BoxTextRecognizer.supportedLanguages()
let temp = NSTemporaryDirectory()

for sample in samples {
    let path = (temp as NSString).appendingPathComponent("gamebox-\(sample.code).png")
    guard render(sample.text, language: sample.hints.first ?? "en", to: path) else {
        failures.append("\(sample.code): could not render")
        continue
    }
    var entry: [String: Any] = ["code": sample.code, "hints": sample.hints]
    do {
        let r = try BoxTextRecognizer.recognize(path: path, languages: sample.hints)
        let text = r.lines.map { $0.text }.joined(separator: " ")
        let score = similarity(text, sample.text)
        entry["recognized"] = text
        entry["similarity"] = score
        entry["languagesUsed"] = r.languages
        entry["hintSupported"] = sample.hints.allSatisfy { supported.contains($0) }
        // Latin scripts must read almost exactly; ideographic text a little
        // less (punctuation and close glyphs).
        let threshold = ["ja", "zh", "zh_Hant", "ko"].contains(sample.code) ? 0.75 : 0.85
        if score < threshold { failures.append("\(sample.code): similarity \(score) < \(threshold) (\(text))") }
    } catch {
        failures.append("\(sample.code): recognition failed \(error)")
    }
    if case let (lang, p)? = BoxTextRecognizer.detectLanguage(sample.text) {
        entry["detected"] = lang
        entry["detectedConfidence"] = p
        if lang != sample.detect { failures.append("\(sample.code): detected \(lang), expected \(sample.detect)") }
    } else {
        failures.append("\(sample.code): language not detected")
    }
    results.append(entry)
}

var translation: [String: String] = [:]
var translationNote = "Translation framework not available on this OS"
#if canImport(Translation)
if #available(macOS 15.0, iOS 18.0, *) {
    translationNote = "LanguageAvailability.status(from: en / ja, to: target)"
    let targets = ["en", "es", "ru", "zh-Hans", "zh-Hant", "pt-BR", "fr", "de", "it", "id", "ja", "ko"]
    let semaphore = DispatchSemaphore(value: 0)
    Task {
        let availability = LanguageAvailability()
        for target in targets {
            let source = target == "en" ? "ja" : "en"
            let status = await availability.status(from: Locale.Language(identifier: source), to: Locale.Language(identifier: target))
            switch status {
            case .installed: translation["\(source)->\(target)"] = "installed"
            case .supported: translation["\(source)->\(target)"] = "supported"
            case .unsupported: translation["\(source)->\(target)"] = "unsupported"
            @unknown default: translation["\(source)->\(target)"] = "unknown"
            }
        }
        semaphore.signal()
    }
    semaphore.wait()
    // The Simulator may not provide translation models: required on macOS only.
    if ProcessInfo.processInfo.environment["GAMEBOX_REQUIRE_TRANSLATION"] == "1" {
        for (pair, status) in translation where status == "unsupported" || status == "unknown" {
            failures.append("translation \(pair): \(status)")
        }
    }
}
#endif

let report: [String: Any] = [
    "os": ProcessInfo.processInfo.operatingSystemVersionString,
    "recognitionLanguages": supported,
    "samples": results,
    "translation": translation,
    "translationNote": translationNote,
    "failures": failures,
    "passed": failures.isEmpty,
]
let data = try! JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
print(String(data: data, encoding: .utf8)!)
exit(failures.isEmpty ? 0 : 1)
