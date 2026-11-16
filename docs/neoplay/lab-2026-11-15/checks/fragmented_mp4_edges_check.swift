import Foundation
// Edge cases of NPFragmentedMP4: audio-only fragment, several audio samples, a picture > 64 KB, time stamps beyond 2^32 ticks.
let m = loadMedia(video: "../media/big.h264", audio: "../media/a.aac")
let big = m.units.map { $0.0.count }.max()!
print("pictures", m.units.count, "key", m.units.filter { $0.1 }.count, "largest", big, "aac", m.frames.count)
let hours = Double(CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "0")!
let vBase = UInt64(hours * 3600 * 90000), aBase = UInt64(hours * 3600 * 48000) / 1024 * 1024
print("vBase", vBase, "aBase", aBase, "2^32", UInt64(1) << 32)
var out = NPFragmentedMP4.initialization(width: 1280, height: 720, avcC: m.avcC, audio: .init(specificConfig: NPFragmentedMP4.aacSpecificConfig(sampleRate: 48000, channels: 2)!, channels: 2, sampleRate: 48000))
var a = 0; var seq: UInt32 = 0
func audioDue(until seconds: Double) -> [NPFragmentedMP4.Sample] { var due: [NPFragmentedMP4.Sample] = []; while Double(a * 1024) / 48000 <= seconds { due.append(.init(data: m.frames[a % m.frames.count], duration: 1024, key: true)); a += 1 }; return due }
let total = min(m.units.count, 600)
for index in 0..<total {
    let t = Double(index) / 60
    // 4.0-5.0 s: no picture at all (audio-only fragments, one per 1/60 s)
    // 6.0-7.0 s: audio held back then sent as one run of many samples with the picture
    let first = a
    var runs: [NPFragmentedMP4.Run] = []
    let videoRun = NPFragmentedMP4.Run(track: 1, decodeTime: vBase + UInt64(index) * 1500, samples: [.init(data: m.units[index].0, duration: 1500, key: m.units[index].1)])
    if t >= 4, t < 5 {
        // pictures skipped until the key picture at 6.0? no: keep the decoder fed is impossible; skip pictures 240..359 (until the next key at 360)
    }
    let skipVideo = index >= 240 && index < 360
    if !skipVideo { runs.append(videoRun) }
    if t >= 6.5, t < 7 { /* hold the sound */ }
    else { let due = audioDue(until: t + 1.0 / 60); if !due.isEmpty { runs.append(.init(track: 2, decodeTime: aBase + UInt64(first * 1024), samples: due)) } }
    seq += 1; out.append(NPFragmentedMP4.fragment(sequence: seq, runs: runs))
}
try out.write(to: URL(fileURLWithPath: "edge-\(Int(hours)).mp4")); print("wrote", out.count)
