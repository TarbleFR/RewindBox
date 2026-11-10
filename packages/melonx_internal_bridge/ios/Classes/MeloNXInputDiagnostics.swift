import Foundation
import CoreGraphics

// Measurement only, for a stick that "did not work" (IPA 658, second player):
// what the router received and sent, and the touch layout it ran with.

// Written on the main thread by MeloNXInputRouter, read and reset once per
// second by MeloNXPerfJournal's sampler queue ("in=").
final class MeloNXInputCounters {
    private let lock = NSLock()
    private var events: [String: Int] = [:]    // "tL" touch left, "tR", "pL" controller left, "pR"
    private var largest: [String: Float] = [:] // the same keys, then "oL"/"oR": magnitude sent to the Core
    private var buttons = 0, drops = 0, refused = 0
    private var lastRefusal: Int32 = 0

    func stick(source: String, stick: Int32, value: (Float, Float), sent: (Float, Float), code: Int32) {
        let side = stick == 2 ? "R" : "L"
        let key = (source == "touch" ? "t" : "p") + side
        lock.lock(); defer { lock.unlock() }
        events[key, default: 0] += 1
        largest[key] = max(largest[key] ?? 0, Self.magnitude(value))
        largest["o" + side] = max(largest["o" + side] ?? 0, Self.magnitude(sent))
        if code != 0 { refused += 1; lastRefusal = code }
    }
    func button(code: Int32) {
        lock.lock(); defer { lock.unlock() }
        buttons += 1
        if code != 0 { refused += 1; lastRefusal = code }
    }
    func dropped() { lock.lock(); drops += 1; lock.unlock() }

    // "tL<events>/<largest>,...,oL<largest sent>,oR..,b<buttons>,d<dropped>,e<refused>:<last code>"
    // for the interval since the previous call; nil when nothing happened.
    func take() -> String? {
        lock.lock(); defer { lock.unlock() }
        var parts: [String] = []
        for key in ["tL", "tR", "pL", "pR"] {
            if let count = events[key] { parts.append(key + "\(count)/" + String(format: "%.2f", largest[key] ?? 0)) }
        }
        for key in ["oL", "oR"] {
            if let value = largest[key] { parts.append(key + String(format: "%.2f", value)) }
        }
        if buttons > 0 { parts.append("b\(buttons)") }
        if drops > 0 { parts.append("d\(drops)") }
        if refused > 0 { parts.append("e\(refused):\(lastRefusal)") }
        events.removeAll(); largest.removeAll(); buttons = 0; drops = 0; refused = 0; lastRefusal = 0
        return parts.isEmpty ? nil : parts.joined(separator: ",")
    }

    private static func magnitude(_ value: (Float, Float)) -> Float {
        min(9.99, (value.0 * value.0 + value.1 * value.1).squareRoot())
    }
}

enum MeloNXInputDiagnostics {
    // The layout ControllerView loads (LayoutManager.load: this title's file,
    // else default.json, else the built-in layout) and where it came from.
    static func layout(gameID: String) -> String {
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MeloNX/controller_layouts")
        func decode(_ file: String) -> LayoutConfig? {
            guard let data = try? Data(contentsOf: directory.appendingPathComponent(file)) else { return nil }
            return try? JSONDecoder().decode(LayoutConfig.self, from: data)
        }
        // A path-keyed identity is a 64-hex hash: the scrubber would redact it.
        let key = gameID.count == 16 ? gameID : "path-keyed"
        var origin = "builtin"
        var layout = LayoutConfig()
        if let game = decode(gameID + ".json") { origin = "game " + key; layout = game }
        else {
            if let global = decode("default.json") { origin = "default.json"; layout = global }
            if FileManager.default.fileExists(atPath: directory.appendingPathComponent(gameID + ".json").path) {
                origin += " (game " + key + " unreadable)"
            }
        }
        func stick(_ id: String) -> String {
            guard let value = layout.joysticks[id] else { return "default" }
            let offset = "\(Int(value.offset.width.rounded())),\(Int(value.offset.height.rounded()))"
            let scale = String(format: "%.2f", Double(value.scale))
            let opacity = value.opacity.map { String(format: "%.2f", Double($0)) } ?? "-"
            return "hidden=\(value.hidden ? 1 : 0) hide=\(value.hide ? 1 : 0) offset=\(offset) scale=\(scale) opacity=\(opacity)"
        }
        // The D-pad is drawn over the left stick (ABXY over the right): hidden
        // buttons take no touch, larger ones cover more of the stick.
        func cover(_ ids: [String]) -> String {
            let entries = ids.compactMap { layout.buttons[$0] }
            let scale = entries.map { Double($0.scale) }.max() ?? 1
            return "hidden=\(entries.filter { $0.hidden }.count) scale=\(String(format: "%.2f", scale))"
        }
        let defaults = UserDefaults.standard
        let size = String(format: "%.2f", defaults.object(forKey: "rewindbox.melonx.On-ScreenControllerScale") as? Double ?? 1)
        let slide = defaults.object(forKey: "rewindbox.melonx.buttonSlide") as? Bool ?? true
        let dpadStick = defaults.bool(forKey: "rewindbox.melonx.joystickDpad")
        let sticks = "left \(stick("leftJoystick")); right \(stick("rightJoystick"))"
        let covers = "dpad \(cover(["dPadUp", "dPadDown", "dPadLeft", "dPadRight"])); abxy \(cover(["A", "B", "X", "Y"]))"
        return "layout \(origin); \(sticks); \(covers); size=\(size) slide=\(slide ? 1 : 0) dpadStick=\(dpadStick ? 1 : 0)"
    }

    // A controller name inside the journal line: no separators, bounded.
    static func name(_ text: String) -> String {
        String(text.map { $0 == ";" || $0 == "=" || $0 == "|" || $0.isNewline ? "_" : $0 }.prefix(40))
    }
}
