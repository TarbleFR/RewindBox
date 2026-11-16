import Foundation

// The phone's side of the RewindBox Cast receiver (tools/neoplay-cast-receiver/receiver.mjs), without Google Cast types:
// NPGoogleCast carries these dictionaries as JSON on the namespace. Main thread.
//   phone → TV  hello {v} · ping {id, t} · play {engine, url} · stop
//   TV → phone  caps · pong {id, t, r} · playing {engine} · key · switch {engine, reason} · error {engine, reason, fatal} · stats
// It also measures the delay that matters: from the capture of a picture on the phone to its display by the receiver. The
// receiver reports which picture it showed and when, on its own clock; pings over the Cast connection give the offset
// between the two clocks (the pair with the shortest round trip, so the error is under half of it).
final class NPReceiverLink {
    static let namespace = "urn:x-cast:com.rewindbox.neoplay"
    static let capsTimeout: TimeInterval = 15   // the page never answered: it cannot be loaded or reached from this TV
    static let playTimeout: TimeInterval = 15   // play was sent and no picture was shown
    enum Event { case caps([String: Any]), playing(String), key, switchEngine(String), failed(String) }
    var send: (([String: Any]) -> Void)?
    var onEvent: ((Event) -> Void)?
    var log: ((String, [String: Any]) -> Void)?
    var captureOrigin: (() -> Double?)?         // clock seconds of time stamp zero of the stream (the capture's first picture)
    private let clock: () -> Double
    private var startedAt: Double?
    private var lastHello = -Double.infinity
    private(set) var caps: [String: Any]?
    private(set) var engine: String?
    private(set) var playing = false
    private var playSentAt: Double?
    private var failed = false
    private var pingCount = 0
    private var lastPing = -Double.infinity
    private var offsets: [(rtt: Double, offset: Double)] = [] // receiver ms minus phone ms, with the round trip it was read on
    private(set) var latencyMs: Int?
    private var window = (count: 0, sum: 0.0, low: Double.infinity, high: 0.0)
    private(set) var lastStats: [String: Any] = [:]
    private var statsCount = 0

    init(clock: @escaping () -> Double = { ProcessInfo.processInfo.systemUptime }) { self.clock = clock }
    var isActive: Bool { startedAt != nil && !failed }
    var bestRoundTripMs: Int? { offsets.map(\.rtt).min().map { Int($0.rounded()) } }
    func start() { reset(); startedAt = clock(); tick() }
    func reset() {
        startedAt = nil; lastHello = -.infinity; caps = nil; engine = nil; playing = false; playSentAt = nil; failed = false
        pingCount = 0; lastPing = -.infinity; offsets = []; latencyMs = nil; window = (0, 0, .infinity, 0); lastStats = [:]; statsCount = 0
    }
    // Four times a second: hello until the page answers, then the clock pings; the two time limits.
    func tick() {
        guard let startedAt, !failed else { return }
        let now = clock()
        if caps == nil {
            if now - startedAt > Self.capsTimeout { fail("caps"); return }
            if now - lastHello >= 0.5 { lastHello = now; send?(["type": "hello", "v": 1]) }
            return
        }
        if let sent = playSentAt, !playing, now - sent > Self.playTimeout { fail("play"); return }
        if now - lastPing >= (pingCount < 6 ? 0.25 : 2) {
            lastPing = now; pingCount += 1
            send?(["type": "ping", "id": pingCount, "t": now * 1000])
        }
    }
    func play(engine: String, url: URL) {
        guard isActive else { return }
        self.engine = engine; playing = false; playSentAt = clock(); window = (0, 0, .infinity, 0)
        log?("cast.receiver.play", ["engine": engine])
        send?(["type": "play", "engine": engine, "url": url.absoluteString])
    }
    func receive(_ message: [String: Any]) {
        guard isActive, let type = message["type"] as? String else { return }
        let now = clock()
        switch type {
        case "caps":
            guard caps == nil else { return }
            caps = message
            var row = message; row.removeValue(forKey: "type"); row["afterMs"] = Int((now - (startedAt ?? now)) * 1000)
            log?("cast.receiver.caps", row)
            onEvent?(.caps(message))
        case "pong":
            guard let sent = Self.number(message["t"]), let remote = Self.number(message["r"]) else { return }
            let local = now * 1000, rtt = local - sent
            guard rtt >= 0, rtt < 2_000 else { return }
            offsets.append((rtt, remote - (sent + local) / 2)); if offsets.count > 12 { offsets.removeFirst() }
        case "playing":
            guard !playing else { return }
            playing = true
            log?("cast.receiver.playing", ["engine": message["engine"] as? String ?? engine ?? "", "afterMs": Int((now - (playSentAt ?? now)) * 1000)])
            onEvent?(.playing(message["engine"] as? String ?? engine ?? ""))
        case "key": onEvent?(.key)
        case "switch":
            log?("cast.receiver.switch", ["from": engine ?? "", "to": message["engine"] as? String ?? "", "reason": message["reason"] as? String ?? ""])
            onEvent?(.switchEngine(message["reason"] as? String ?? ""))
        case "error":
            let reason = message["reason"] as? String ?? ""
            log?("cast.receiver.error", ["engine": message["engine"] as? String ?? "", "reason": reason, "fatal": message["fatal"] as? Bool ?? false])
            if message["fatal"] as? Bool == true { fail("receiver: \(reason)") }
        case "stats": stats(message)
        default: break
        }
    }
    // Capture-to-screen delay of the picture the receiver last showed, and a log row every ten reports (ten seconds).
    private func stats(_ message: [String: Any]) {
        lastStats = message; statsCount += 1
        if let shown = message["shown"] as? [String: Any], let pts = Self.number(shown["pts"]), let at = Self.number(shown["at"]),
           let origin = captureOrigin?(), let best = offsets.min(by: { $0.rtt < $1.rtt }) {
            let delay = (at - best.offset) - (origin * 1000 + pts / 1000)
            if delay > -50, delay < 10_000 {
                latencyMs = Int(delay.rounded())
                window.count += 1; window.sum += delay; window.low = min(window.low, delay); window.high = max(window.high, delay)
            }
        }
        guard statsCount % 10 == 0 else { return }
        var row: [String: Any] = ["engine": message["engine"] as? String ?? engine ?? "", "rttMs": bestRoundTripMs ?? -1]
        if window.count > 0 { row["delayMs"] = Int(window.sum / Double(window.count)); row["delayMinMs"] = Int(window.low); row["delayMaxMs"] = Int(window.high) }
        for key in ["decoder", "width", "height", "second", "decodeMs", "ageMs", "spreadMs", "audio", "reconnects", "skipped", "replaced", "keyRequests",
                    "decodeErrors", "lagMs", "targetMs", "rate", "stalls", "seeks", "dropped", "wake", "error"] { if let value = message[key], !(value is NSNull) { row[key] = value } }
        log?("cast.receiver.stats", row)
        window = (0, 0, .infinity, 0)
    }
    private func fail(_ reason: String) {
        guard !failed else { return }
        failed = true
        log?("cast.receiver.failed", ["reason": reason, "engine": engine ?? "", "caps": caps != nil])
        onEvent?(.failed(reason))
    }
    private static func number(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? Int { return Double(value) }
        if let value = value as? NSNumber { return value.doubleValue }
        return nil
    }
}

// The RewindBox receiver application registered in the Google Cast SDK Developer Console (Custom Receiver, URL
// https://tarblefr.github.io/RewindBox/cast/). Empty: the feature is off and every session uses Google's receiver.
enum NPReceiverApp {
    static let applicationID = ""
    // Key of the GoogleCast 4.8.6 session option that names the application to launch (kGCKSessionOptionsKeyApplicationID,
    // exported by the framework but not declared in its public headers); discovery keeps Google's receiver, so a device
    // that cannot launch this one still appears and falls back.
    static let sessionOptionKey = "gck_applicationID"
    static var enabled: Bool { applicationID.count == 8 }
}
