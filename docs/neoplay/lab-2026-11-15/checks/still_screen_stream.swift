import Foundation
// Still, silent screen on the direct route: pictures every 0.2 s (NPCapture.stillInterval), no capture sound at all.
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
let fps = Double(CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "5")!
let withSound = CommandLine.arguments.count > 2 && CommandLine.arguments[2] == "sound"
let video = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments.count > 3 ? CommandLine.arguments[3] : "still.h264")), audio = try Data(contentsOf: URL(fileURLWithPath: "silent.aac"))
var sps: Data?, pps: Data?; var units: [(Data, Bool)] = []; var current = Data(); var key = false
for nal in nals(video) { let type = nal[nal.startIndex] & 0x1f
    if type == 9 { if !current.isEmpty { units.append((current, key)) }; current = Data(); key = false; continue }
    if type == 7 { sps = nal; continue }; if type == 8 { pps = nal; continue }; if type == 6 { continue }
    if type == 5 { key = true }; current.append(be(UInt64(nal.count), 4)); current.append(nal) }
if !current.isEmpty { units.append((current, key)) }
var avcC = Data([1, sps![1], sps![2], sps![3], 0xff, 0xe1]); avcC.append(be(UInt64(sps!.count), 2)); avcC.append(sps!); avcC.append(1); avcC.append(be(UInt64(pps!.count), 2)); avcC.append(pps!)
var frames: [Data] = []; var at = 0
while at + 7 <= audio.count { let len = (Int(audio[at+3] & 3) << 11) | (Int(audio[at+4]) << 3) | (Int(audio[at+5]) >> 5); frames.append(audio.subdata(in: (at+7)..<(at+len))); at += len }
var p = Data([3]); p.append(be(1280, 2)); p.append(be(588, 2)); p.append(be(48000, 4)); p.append(2); p.append(avcC)
let stream = NPDirectStream(audioEncoder: StandIn(frames))
var out = Data(); var fragments = 0; var now = 0.0
stream.setBitrate(9_000_000)
stream.consume(p, at: 0)
precondition(stream.attach(send: { out.append($0); fragments += 1 }, pending: { 0 }, at: 0))
var nextSound = 0.030; let soundFrames = 1024
for k in 0..<units.count {
    now = Double(k) / fps
    if withSound { while nextSound <= now { var s = Data([5]); s.append(be(UInt64(nextSound * 1_000_000), 8)); s.append(Data(count: soundFrames * 4)); stream.consume(s, at: now); nextSound += Double(soundFrames) / 48000 } }
    var v = Data([4]); v.append(be(UInt64(now * 1_000_000), 8)); v.append(units[k].1 ? 1 : 0); v.append(units[k].0); stream.consume(v, at: now)
}
let name = "stream-still\(Int(fps))\(withSound ? "-sound" : "").mp4"
try out.write(to: URL(fileURLWithPath: name))
print(name, "units", units.count, "keys", units.filter { $0.1 }.count, "fragments", fragments, "bytes", out.count)
print("  ", stream.statistics.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: " "))
