import Foundation
// Linux check of NPFragmentedMP4: Annex B H.264 + ADTS AAC from ffmpeg -> init + one fragment per picture.
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
func be32(_ v: Int) -> Data { withUnsafeBytes(of: UInt32(v).bigEndian) { Data($0) } }
let video = try Data(contentsOf: URL(fileURLWithPath: "v.h264")), audio = try Data(contentsOf: URL(fileURLWithPath: "a.aac"))
var sps: Data?, pps: Data?; var units: [(Data, Bool)] = []; var current = Data(); var key = false
for nal in nals(video) {
    let type = nal[nal.startIndex] & 0x1f
    if type == 9 { if !current.isEmpty { units.append((current, key)) }; current = Data(); key = false; continue }
    if type == 7 { sps = nal; continue }; if type == 8 { pps = nal; continue }
    if type == 5 { key = true }
    current.append(be32(nal.count)); current.append(nal)
}
if !current.isEmpty { units.append((current, key)) }
guard let sps, let pps else { fatalError("no parameter sets") }
var avcC = Data([1, sps[1], sps[2], sps[3], 0xff, 0xe1]); avcC.append(contentsOf: [UInt8(sps.count >> 8), UInt8(sps.count & 0xff)]); avcC.append(sps)
avcC.append(1); avcC.append(contentsOf: [UInt8(pps.count >> 8), UInt8(pps.count & 0xff)]); avcC.append(pps)
var frames: [Data] = []; var at = 0
while at + 7 <= audio.count { let len = (Int(audio[at+3] & 3) << 11) | (Int(audio[at+4]) << 3) | (Int(audio[at+5]) >> 5); let hdr = (audio[at+1] & 1) == 1 ? 7 : 9; frames.append(audio.subdata(in: (at+hdr)..<(at+len))); at += len }
print("pictures", units.count, "key", units.filter { $0.1 }.count, "aac frames", frames.count)
var out = NPFragmentedMP4.initialization(width: 640, height: 360, avcC: avcC, audio: .init(specificConfig: NPFragmentedMP4.aacSpecificConfig(sampleRate: 48000, channels: 2)!, channels: 2, sampleRate: 48000))
print("init bytes", out.count)
var a = 0; var seq: UInt32 = 1
for (index, unit) in units.enumerated() {
    let vt = UInt64(index) * 1500 // 90000 / 60
    var due: [NPFragmentedMP4.Sample] = []; let first = a
    while a < frames.count, Double(a * 1024) / 48000 <= Double(index + 1) / 60 { due.append(.init(data: frames[a], duration: 1024, key: true)); a += 1 }
    var runs = [NPFragmentedMP4.Run(track: NPFragmentedMP4.videoTrack, decodeTime: vt, samples: [.init(data: unit.0, duration: 1500, key: unit.1)])]
    if !due.isEmpty { runs.append(.init(track: NPFragmentedMP4.audioTrack, decodeTime: UInt64(first * 1024), samples: due)) }
    out.append(NPFragmentedMP4.fragment(sequence: seq, runs: runs)); seq += 1
}
try out.write(to: URL(fileURLWithPath: "out.mp4")); print("wrote", out.count)
