import Foundation
// NPAudioTimeline against a capture whose sound arrives `la` seconds after its last sample and whose pictures arrive `lv` after their time stamp.
// The sound is absent in [quietFrom, quietTo) (a paused game), or late at start.
func run(la: Double, lv: Double, quietFrom: Double, quietTo: Double, fps: Double = 60, seconds: Double = 20) -> (taken: Double, offered: Double, filled: Double, skipped: Double, silentAtEnd: Bool) {
    var t = NPAudioTimeline()
    var events: [(Double, Int, Double)] = [] // arrival, kind (0 picture, 1 sound), time stamp
    var p = 0.0; while p < seconds { events.append((p + lv, 0, p)); p += 1 / fps }
    let frames = 1115; var s = 0.0
    while s < seconds { if !(s >= quietFrom && s < quietTo) { events.append((s + Double(frames) / 48000 + la, 1, s)) }; s += Double(frames) / 48000 }
    events.sort { $0.0 < $1.0 }
    var taken = 0, offered = 0
    for e in events where e.0 <= seconds {
        if e.1 == 0 { _ = t.follow(picture: Int64(e.2 * 48000)) }
        else { let r = t.place(start: Int64(e.2 * 48000), count: frames); if e.2 >= quietTo { taken += r.take; offered += frames } }
    }
    return (Double(taken) / 48000, Double(offered) / 48000, Double(t.filled) / 48000, Double(t.skipped) / 48000, t.silent)
}
print("A. sound pauses 2 s..5 s, then resumes; 60 pictures/s. taken/offered = seconds of sound kept after the resume")
for d in [0.0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.15, 0.2, 0.24] {
    let r = run(la: 0.03 + d, lv: 0.03, quietFrom: 2, quietTo: 5)
    print(String(format: "  sound later than pictures by %3.0f ms: kept %5.2f of %5.2f s, silence %5.2f s, skipped %5.2f s, silent at end %@", d * 1000, r.taken, r.offered, r.filled, r.skipped, r.silentAtEnd ? "YES" : "no"))
}
print("B. no sound during the first 0.5 s of the capture (late audio start), then continuous")
for d in [0.0, 0.04, 0.08, 0.1, 0.15, 0.2] {
    let r = run(la: 0.03 + d, lv: 0.03, quietFrom: 0, quietTo: 0.5)
    print(String(format: "  sound later than pictures by %3.0f ms: kept %5.2f of %5.2f s, silence %5.2f s, skipped %5.2f s, silent at end %@", d * 1000, r.taken, r.offered, r.filled, r.skipped, r.silentAtEnd ? "YES" : "no"))
}
print("C. as A on a still screen (5 pictures/s)")
for d in [0.0, 0.04, 0.08, 0.1, 0.15, 0.2] {
    let r = run(la: 0.03 + d, lv: 0.03, quietFrom: 2, quietTo: 5, fps: 5)
    print(String(format: "  sound later than pictures by %3.0f ms: kept %5.2f of %5.2f s, silence %5.2f s, skipped %5.2f s, silent at end %@", d * 1000, r.taken, r.offered, r.filled, r.skipped, r.silentAtEnd ? "YES" : "no"))
}
print("D. continuous sound from the start, never quiet")
for d in [0.0, 0.1, 0.2, 0.24, 0.27, 0.3] {
    let r = run(la: 0.03 + d, lv: 0.03, quietFrom: -1, quietTo: -1)
    print(String(format: "  sound later than pictures by %3.0f ms: kept %5.2f of %5.2f s, silence %5.2f s, skipped %5.2f s, silent at end %@", d * 1000, r.taken, r.offered, r.filled, r.skipped, r.silentAtEnd ? "YES" : "no"))
}
