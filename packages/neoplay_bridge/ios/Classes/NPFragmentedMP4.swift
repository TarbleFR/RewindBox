import Foundation

// Fragmented MP4 written by hand for the direct Chromecast route: one
// initialization segment (ftyp + moov), then one small fragment (moof + mdat)
// per picture. The receiver's media element plays that as one endless HTTP
// response, a picture being available as soon as it is encoded. AVAssetWriter
// cannot produce it: it only publishes a fragment that starts on a key picture.
// Pure Foundation; the layout follows ISO/IEC 14496-12 and -14.
enum NPFragmentedMP4 {
    static let videoTimescale: UInt32 = 90_000
    static let videoTrack: UInt32 = 1
    static let audioTrack: UInt32 = 2
    struct Sample { let data: Data; let duration: UInt32; let key: Bool }
    // One run of consecutive samples of a track; decodeTime is in the track's time scale.
    struct Run { let track: UInt32; let decodeTime: UInt64; let samples: [Sample] }
    struct Audio { let specificConfig: Data; let channels: Int; let sampleRate: Int }

    // AudioSpecificConfig of AAC-LC: 5 bits object type 2, 4 bits frequency index, 4 bits channels.
    static func aacSpecificConfig(sampleRate: Int, channels: Int) -> Data? {
        let rates = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350]
        guard let index = rates.firstIndex(of: sampleRate), (1...2).contains(channels) else { return nil }
        let bits = UInt16(2) << 11 | UInt16(index) << 7 | UInt16(channels) << 3
        return Data([UInt8(bits >> 8), UInt8(bits & 0xff)])
    }

    static func initialization(width: Int, height: Int, avcC: Data, audio: Audio?) -> Data {
        var out = box("ftyp") { $0.append(ascii("iso5")); $0.append(u32(512)); $0.append(ascii("iso5iso6mp41")) }
        out.append(box("moov") { moov in
            moov.append(full("mvhd", 0, 0) { b in
                b.append(u32(0)); b.append(u32(0)); b.append(u32(1000)); b.append(u32(0)) // times, time scale, duration unknown: live
                b.append(u32(0x0001_0000)); b.append(u16(0x0100)); b.append(zeros(10)); b.append(matrix); b.append(zeros(24))
                b.append(u32(audio == nil ? 2 : 3)) // next track id
            })
            moov.append(track(id: videoTrack, timescale: videoTimescale, handler: "vide", name: "VideoHandler", width: width, height: height) { stsd in
                stsd.append(box("avc1") { e in
                    e.append(zeros(6)); e.append(u16(1)); e.append(zeros(16))
                    e.append(u16(UInt16(clamping: width))); e.append(u16(UInt16(clamping: height)))
                    e.append(u32(0x0048_0000)); e.append(u32(0x0048_0000)); e.append(u32(0)); e.append(u16(1))
                    e.append(zeros(32)); e.append(u16(0x0018)); e.append(u16(0xffff))
                    e.append(box("avcC") { $0.append(avcC) })
                })
            })
            if let audio {
                moov.append(track(id: audioTrack, timescale: UInt32(audio.sampleRate), handler: "soun", name: "SoundHandler", width: 0, height: 0) { stsd in
                    stsd.append(box("mp4a") { e in
                        e.append(zeros(6)); e.append(u16(1)); e.append(zeros(8))
                        e.append(u16(UInt16(audio.channels))); e.append(u16(16)); e.append(u32(0)); e.append(u32(UInt32(audio.sampleRate) << 16))
                        e.append(full("esds", 0, 0) { d in
                            let config = audio.specificConfig
                            d.append(contentsOf: [0x03, UInt8(23 + config.count), 0, 0, 0]) // ES descriptor, ES_ID 0, no flags
                            d.append(contentsOf: [0x04, UInt8(15 + config.count), 0x40, 0x15, 0, 0, 0]) // AAC, audio stream, buffer size
                            d.append(u32(0)); d.append(u32(0)) // maximum and average bit rate: unknown
                            d.append(contentsOf: [0x05, UInt8(config.count)]); d.append(config)
                            d.append(contentsOf: [0x06, 1, 2])
                        })
                    })
                })
            }
            moov.append(box("mvex") { mvex in
                for id in [videoTrack] + (audio == nil ? [] : [audioTrack]) {
                    mvex.append(full("trex", 0, 0) { $0.append(u32(id)); $0.append(u32(1)); $0.append(u32(0)); $0.append(u32(0)); $0.append(u32(0)) })
                }
            })
        })
        return out
    }

    // One moof + mdat; the sample data of the runs follow each other in the mdat, in order. `minimumSize` pads the mdat
    // with zeros that no sample refers to, so that a fragment never is smaller than that many bytes.
    static func fragment(sequence: UInt32, runs: [Run], minimumSize: Int = 0) -> Data {
        let runs = runs.filter { !$0.samples.isEmpty }
        let trafSizes = runs.map { 64 + 12 * $0.samples.count }
        let moofSize = 8 + 16 + trafSizes.reduce(0, +)
        let payload = runs.reduce(0) { $0 + $1.samples.reduce(0) { $0 + $1.data.count } }
        let padding = max(0, minimumSize - (moofSize + 8 + payload))
        var out = Data(capacity: moofSize + 8 + payload + padding)
        out.append(u32(UInt32(moofSize))); out.append(ascii("moof"))
        out.append(u32(16)); out.append(ascii("mfhd")); out.append(u32(0)); out.append(u32(sequence))
        var offset = moofSize + 8
        for (index, run) in runs.enumerated() {
            out.append(u32(UInt32(trafSizes[index]))); out.append(ascii("traf"))
            out.append(u32(16)); out.append(ascii("tfhd")); out.append(u32(0x02_0000)); out.append(u32(run.track)) // default-base-is-moof
            out.append(u32(20)); out.append(ascii("tfdt")); out.append(u32(0x0100_0000)); out.append(u64(run.decodeTime))
            out.append(u32(UInt32(20 + 12 * run.samples.count))); out.append(ascii("trun"))
            out.append(u32(0x00_0701)); out.append(u32(UInt32(run.samples.count))); out.append(u32(UInt32(offset))) // data offset, duration, size, flags
            for sample in run.samples {
                out.append(u32(sample.duration)); out.append(u32(UInt32(sample.data.count)))
                out.append(u32(sample.key ? 0x0200_0000 : 0x0101_0000)) // depends on no other / depends on others and is not a sync sample
                offset += sample.data.count
            }
        }
        out.append(u32(UInt32(payload + padding + 8))); out.append(ascii("mdat"))
        for run in runs { for sample in run.samples { out.append(sample.data) } }
        if padding > 0 { out.append(Data(count: padding)) }
        return out
    }

    private static func track(id: UInt32, timescale: UInt32, handler: String, name: String, width: Int, height: Int, entry: (inout Data) -> Void) -> Data {
        box("trak") { trak in
            trak.append(full("tkhd", 0, 3) { b in // enabled, in movie
                b.append(u32(0)); b.append(u32(0)); b.append(u32(id)); b.append(u32(0)); b.append(u32(0)); b.append(zeros(8))
                b.append(u16(0)); b.append(u16(handler == "soun" ? 1 : 0)); b.append(u16(handler == "soun" ? 0x0100 : 0)); b.append(u16(0)); b.append(matrix)
                b.append(u32(UInt32(width) << 16)); b.append(u32(UInt32(height) << 16))
            })
            trak.append(box("mdia") { mdia in
                mdia.append(full("mdhd", 0, 0) { $0.append(u32(0)); $0.append(u32(0)); $0.append(u32(timescale)); $0.append(u32(0)); $0.append(u16(0x55c4)); $0.append(u16(0)) })
                mdia.append(full("hdlr", 0, 0) { $0.append(u32(0)); $0.append(ascii(handler)); $0.append(zeros(12)); $0.append(ascii(name)); $0.append(0) })
                mdia.append(box("minf") { minf in
                    if handler == "soun" { minf.append(full("smhd", 0, 0) { $0.append(u32(0)) }) }
                    else { minf.append(full("vmhd", 0, 1) { $0.append(zeros(8)) }) }
                    minf.append(box("dinf") { $0.append(full("dref", 0, 0) { $0.append(u32(1)); $0.append(full("url ", 0, 1) { _ in }) }) })
                    minf.append(box("stbl") { stbl in
                        stbl.append(full("stsd", 0, 0) { $0.append(u32(1)); entry(&$0) })
                        stbl.append(full("stts", 0, 0) { $0.append(u32(0)) })
                        stbl.append(full("stsc", 0, 0) { $0.append(u32(0)) })
                        stbl.append(full("stsz", 0, 0) { $0.append(u32(0)); $0.append(u32(0)) })
                        stbl.append(full("stco", 0, 0) { $0.append(u32(0)) })
                    })
                })
            })
        }
    }
    private static let matrix: Data = { var m = Data(); for value in [0x0001_0000, 0, 0, 0, 0x0001_0000, 0, 0, 0, 0x4000_0000] as [UInt32] { m.append(u32(value)) }; return m }()
    private static func box(_ type: String, _ body: (inout Data) -> Void) -> Data {
        var payload = Data(); body(&payload)
        var out = Data(capacity: payload.count + 8); out.append(u32(UInt32(payload.count + 8))); out.append(ascii(type)); out.append(payload)
        return out
    }
    private static func full(_ type: String, _ version: UInt8, _ flags: UInt32, _ body: (inout Data) -> Void) -> Data {
        box(type) { $0.append(u32(UInt32(version) << 24 | flags)); body(&$0) }
    }
    private static func ascii(_ text: String) -> Data { Data(text.utf8) }
    private static func zeros(_ count: Int) -> Data { Data(count: count) }
    private static func u16(_ value: UInt16) -> Data { withUnsafeBytes(of: value.bigEndian) { Data($0) } }
    private static func u32(_ value: UInt32) -> Data { withUnsafeBytes(of: value.bigEndian) { Data($0) } }
    private static func u64(_ value: UInt64) -> Data { withUnsafeBytes(of: value.bigEndian) { Data($0) } }
}
