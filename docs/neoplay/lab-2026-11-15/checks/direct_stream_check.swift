import Foundation
// Linux check of NPDirectStream with real H.264 pictures (ffmpeg, Annex B) and real AAC packets handed out by a stand-in encoder.
func nals(_ d: Data) -> [Data] {
    var out: [Data] = []; var i = 0; var start = -1; let n = d.count
    d.withUnsafeBytes { (p: UnsafeRawBufferPointer) in
        let b = p.bindMemory(to: UInt8.self)
        while i + 3 <= n {
            if b[i] == 0 && b[i+1] == 0 && (b[i+2] == 1 || (i + 3 < n && b[i+2] == 0 && b[i+3] == 1)) {
                let code = b[i+2] == 1 ? 3 : 4
                if start >= 0 { var end = i; while end > start && b[end-1] == 0 { end -= 1 }; out.append(Data(b[start..<end])) }
                start = i + code; i += code
            } else { i += 1 }
        }
        if start >= 0 { out.append(Data(b[start..<n])) }
    }
    return out
}
func be(_ v: UInt64, _ bytes: Int) -> Data { Data((0..<bytes).map { UInt8((v >> UInt64(8 * (bytes - 1 - $0))) & 0xff) }) }
final class StandIn: NPAudioPacketEncoder { let frames: [Data]; var index = 0; init(_ f: [Data]) { frames = f }
    func encode(block: Data) -> [Data] { precondition(block.count == 4096); defer { index += 1 }; return [frames[index % frames.count]] } }
let scenario = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "normal"
let video = try Data(contentsOf: URL(fileURLWithPath: "v.h264")), audio = try Data(contentsOf: URL(fileURLWithPath: "a.aac"))
var sps: Data?, pps: Data?; var units: [(Data, Bool)] = []; var current = Data(); var key = false
for nal in nals(video) { let type = nal[nal.startIndex] & 0x1f
    if type == 9 { if !current.isEmpty { units.append((current, key)) }; current = Data(); key = false; continue }
    if type == 7 { sps = nal; continue }; if type == 8 { pps = nal; continue }
    if type == 5 { key = true }; current.append(be(UInt64(nal.count), 4)); current.append(nal) }
if !current.isEmpty { units.append((current, key)) }
var avcC = Data([1, sps![1], sps![2], sps![3], 0xff, 0xe1]); avcC.append(be(UInt64(sps!.count), 2)); avcC.append(sps!); avcC.append(1); avcC.append(be(UInt64(pps!.count), 2)); avcC.append(pps!)
var frames: [Data] = []; var at = 0
while at + 7 <= audio.count { let len = (Int(audio[at+3] & 3) << 11) | (Int(audio[at+4]) << 3) | (Int(audio[at+5]) >> 5); frames.append(audio.subdata(in: (at+7)..<(at+len))); at += len }
func config(_ w: Int, _ h: Int) -> Data { var p = Data([3]); p.append(be(UInt64(w), 2)); p.append(be(UInt64(h), 2)); p.append(be(48000, 4)); p.append(2); p.append(avcC); return p }
let stream = NPDirectStream(audioEncoder: StandIn(frames))
var out = Data(); var chunks: [(Double, Int)] = []; var now = 0.0; var queue = 0
var keyRequests = 0, congestions = 0, resets: [String] = [], readyCalls = 0
stream.onKeyRequest = { keyRequests += 1 }; stream.onCongestion = { congestions += 1 }; stream.onReset = { resets.append("\($0)@\(String(format: "%.2f", now))") }; stream.onReady = { readyCalls += 1 }
stream.setBitrate(9_000_000)
let seconds = 20.0, total = min(units.count, Int(seconds * 60))
var nextSound = 0.030; let soundFrames = 1115
var attached = false
for k in 0..<total {
    now = Double(k) / 60
    if k == 0 { stream.consume(config(640, 360), at: now) }
    if scenario == "config", k == 16 * 60 { stream.consume(config(320, 180), at: now) }
    if !attached, k == 20 { attached = stream.attach(send: { out.append($0); chunks.append((now, $0.count)) }, pending: { queue }, at: now) }
    // sound up to this instant, except in the scenario's silent spans
    while nextSound <= now {
        let silentSpan = (scenario == "silence" && nextSound >= 5 && nextSound < 7.5) || (scenario == "mutestart" && nextSound < 6)
        if !silentSpan { var p = Data([5]); p.append(be(UInt64(nextSound * 1_000_000), 8)); p.append(Data(count: soundFrames * 4)); stream.consume(p, at: now) }
        nextSound += Double(soundFrames) / 48000
    }
    if scenario == "overflow" { queue = (now >= 8 && now < 8.9) ? 1_000_000 - Int((now - 8) * 1000) : 0 } // draining slowly, then empty
    if scenario == "stall" { queue = now >= 12 ? 1_000_000 + k : 0 }
    if scenario == "stillscreen", now >= 10, now < 13 { continue } // no pictures for 3 s: sound must keep flowing
    var p = Data([4]); p.append(be(UInt64(k) * 1_000_000 / 60, 8)); p.append(units[k].1 ? 1 : 0); p.append(units[k].0); stream.consume(p, at: now)
}
try out.write(to: URL(fileURLWithPath: "stream-\(scenario).mp4"))
try chunks.map { "\(Int($0.0 * 1000)) \($0.1)" }.joined(separator: "\n").write(toFile: "stream-\(scenario).times", atomically: true, encoding: .utf8)
let s = stream.statistics
print(scenario, "attached", attached, "ready", readyCalls, "keyRequests", keyRequests, "congestions", congestions, "resets", resets, "newest", stream.newestPictureSeconds)
print("  ", s.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: " "))
