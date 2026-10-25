// SPDX-License-Identifier: GPL-3.0-or-later
//
// Small print of a box back (Build 494): draws back-cover-like scans with the
// proportions of real ones (title, body text, feature list, a light panel,
// legal print), saved as JPEG like most ScreenScraper scans, at three
// resolutions, and reads them with BoxTextRecognizer. The same file is built
// with the recognizer of Build 493 (the control) and with the current one by
// test/build494_targeted_test.py, which compares the two reports.
//
// Every text is drawn here: no real box scan is used. The report is JSON on
// stdout; this program itself fails only when an image cannot be produced.

import CoreGraphics
import CoreText
import Foundation
import ImageIO

struct Block {
    let name: String
    let fontPixels: Double   // at scale 1 (a 1000 × 1400 scan)
    let text: String
    let dark: Bool           // dark text on a light panel
}

struct Language {
    let code: String
    let hints: [String]
    let blocks: [Block]
}

let languages: [Language] = [
    Language(code: "en", hints: ["en-US"], blocks: [
        Block(name: "title", fontPixels: 54, text: "The Shadow King Returns", dark: false),
        Block(name: "body", fontPixels: 22, text: "Explore forty dangerous caves, gather the seven crystals and defeat the Shadow King before the last moon rises over the kingdom.", dark: false),
        Block(name: "features", fontPixels: 17, text: "Twelve playable heroes with unique skills. Four player cooperative mode. More than sixty hours of adventure.", dark: false),
        Block(name: "panel", fontPixels: 15, text: "Memory card with at least two free blocks required to save your progress.", dark: true),
        Block(name: "legal", fontPixels: 11, text: "Licensed for home use only. Unauthorised copying, rental or public performance of this game is prohibited.", dark: false),
    ]),
    Language(code: "fr", hints: ["fr-FR", "en-US"], blocks: [
        Block(name: "title", fontPixels: 54, text: "Le retour du roi des ombres", dark: false),
        Block(name: "body", fontPixels: 22, text: "Explorez quarante grottes dangereuses, rassemblez les sept cristaux et battez le roi des ombres avant que la dernière lune ne se lève.", dark: false),
        Block(name: "features", fontPixels: 17, text: "Douze héros jouables aux talents uniques. Mode coopératif à quatre joueurs. Plus de soixante heures d'aventure.", dark: false),
        Block(name: "panel", fontPixels: 15, text: "Carte mémoire avec au moins deux blocs libres nécessaire pour sauvegarder votre progression.", dark: true),
        Block(name: "legal", fontPixels: 11, text: "Réservé à un usage domestique. Toute copie, location ou représentation publique de ce jeu est interdite.", dark: false),
    ]),
]

let scales: [Double] = [2.0, 1.0, 0.6]

/// Draws one back and returns the rectangle of each block (pixels, top-left origin).
func draw(_ language: Language, scale: Double, to path: String) -> [String: CGRect]? {
    let width = Int(1000 * scale), height = Int(1400 * scale)
    guard let space = CGColorSpace(name: CGColorSpace.sRGB),
          let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                              space: space, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
    ctx.setFillColor(CGColor(red: 0.07, green: 0.09, blue: 0.16, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    var rects: [String: CGRect] = [:]
    var top = 70.0 * scale
    let margin = 80.0 * scale
    let columnWidth = Double(width) - 2 * margin
    for block in language.blocks {
        let size = block.fontPixels * scale
        let font = CTFontCreateUIFontForLanguage(.system, size, language.code as CFString)
            ?? CTFontCreateWithName("Helvetica" as CFString, size, nil)
        let color = block.dark ? CGColor(red: 0.1, green: 0.1, blue: 0.12, alpha: 1)
                               : CGColor(red: 0.95, green: 0.95, blue: 0.95, alpha: 1)
        let attributes: [CFString: Any] = [kCTFontAttributeName: font, kCTForegroundColorAttributeName: color]
        let attributed = CFAttributedStringCreate(nil, block.text as CFString, attributes as CFDictionary)!
        let framesetter = CTFramesetterCreateWithAttributedString(attributed)
        let fit = CTFramesetterSuggestFrameSizeWithConstraints(
            framesetter, CFRange(location: 0, length: 0), nil,
            CGSize(width: columnWidth, height: .greatestFiniteMagnitude), nil)
        let h = ceil(fit.height)
        // Core Graphics has a bottom-left origin.
        let frameRect = CGRect(x: margin, y: Double(height) - top - h, width: columnWidth, height: h)
        if block.dark {
            ctx.setFillColor(CGColor(red: 0.93, green: 0.9, blue: 0.82, alpha: 1))
            ctx.fill(frameRect.insetBy(dx: -18 * scale, dy: -14 * scale))
        }
        let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: 0, length: 0),
                                             CGPath(rect: frameRect, transform: nil), nil)
        CTFrameDraw(frame, ctx)
        rects[block.name] = CGRect(x: margin, y: top, width: columnWidth, height: h)
        top += h + 64 * scale
    }
    guard let image = ctx.makeImage(),
          let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, "public.jpeg" as CFString, 1, nil)
    else { return nil }
    CGImageDestinationAddImage(dest, image, [kCGImageDestinationLossyCompressionQuality: 0.8] as CFDictionary)
    return CGImageDestinationFinalize(dest) ? rects : nil
}

/// Similarity of two strings ignoring case, spaces and punctuation (1 = equal).
func similarity(_ a: String, _ b: String) -> Double {
    func norm(_ s: String) -> [Character] { Array(s.lowercased().filter { $0.isLetter || $0.isNumber }) }
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

var results: [[String: Any]] = []
var errors: [String] = []
let temp = NSTemporaryDirectory()
for language in languages {
    for scale in scales {
        let path = (temp as NSString).appendingPathComponent("gamebox-small-\(language.code)-\(scale).jpg")
        guard let rects = draw(language, scale: scale, to: path) else {
            errors.append("\(language.code) \(scale): could not draw")
            continue
        }
        let started = Date()
        var lines: [BoxTextLine] = []
        var pixels = (0, 0)
        do {
            let r = try BoxTextRecognizer.recognize(path: path, languages: language.hints)
            lines = r.lines
            pixels = (r.pixelWidth, r.pixelHeight)
        } catch {
            errors.append("\(language.code) \(scale): recognition failed \(error)")
        }
        let seconds = Date().timeIntervalSince(started)
        let w = 1000 * scale, h = 1400 * scale
        for block in language.blocks {
            guard let rect = rects[block.name] else { continue }
            let area = rect.insetBy(dx: -0.01 * w, dy: -0.006 * h)
            let inside = lines.filter { line in
                let cx = (line.x + line.width / 2) * w, cy = (line.y + line.height / 2) * h
                return area.contains(CGPoint(x: cx, y: cy))
            }
            let text = inside.map { $0.text }.joined(separator: " ")
            results.append([
                "language": language.code,
                "scale": scale,
                "scanWidth": Int(w),
                "block": block.name,
                "fontPixels": block.fontPixels * scale,
                "lines": inside.count,
                "recognized": text,
                "similarity": similarity(text, block.text),
            ])
        }
        results.append([
            "language": language.code, "scale": scale, "block": "_image",
            "seconds": seconds, "visionWidth": pixels.0, "visionHeight": pixels.1, "allLines": lines.count,
        ])
    }
}

let report: [String: Any] = [
    "os": ProcessInfo.processInfo.operatingSystemVersionString,
    "results": results,
    "errors": errors,
]
let data = try! JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
print(String(data: data, encoding: .utf8)!)
exit(errors.isEmpty ? 0 : 1)
