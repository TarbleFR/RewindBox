import Foundation

// One block of 1024 stereo 16-bit samples at 48 kHz in, the AAC-LC packets the
// encoder has finished out, in order. On the phone: NPAACEncoder.
protocol NPAudioPacketEncoder: AnyObject {
    func encode(block: Data) -> [Data]
}

// Direct Chromecast route. Takes the packets of NPFrameEncoder (3 configuration,
// 4 picture, 5 sound; see its header) and produces one fragmented-MP4 stream:
// an initialization segment, then a fragment per picture carrying the sound
// that is due. One receiver connection at a time reads it as one endless HTTP
// response. Nothing waits for a segment: a picture leaves as soon as it is
// encoded. Pure Foundation: the same code runs in the Linux checks.
//
// Threads: pictures and the configuration arrive on the capture queue, sound on
// the capture's audio queue, attach/detach on the HTTP queue. One lock orders
// them; fragments are handed to `send` under that lock so that they keep their
// order. `send` and `pending` must not call back into this object. The other
// callbacks run after the lock is released.
final class NPDirectStream {
    static let blockFrames = 1_024
    static let aacPriming: Int64 = 2_112   // samples the AAC encoder delays its output by
    static let stallSeconds: TimeInterval = 2.5
    private let lock = NSLock()
    private let audioEncoder: NPAudioPacketEncoder
    private var deferred: [() -> Void] = []
    // stream
    private var initialization: Data?
    private var configuration: Data?
    private var size = NPSize(width: 0, height: 0)
    private var sequence: UInt32 = 0
    private var lastPictureTicks: UInt64?
    private var newestPicture = 0.0
    // sound
    private var timeline = NPAudioTimeline()
    private var block = Data()
    private var audioBase: Int64?          // time, in samples, of AAC packet 0
    private var packets: Int64 = 0
    private var ready: [(time: Int64, data: Data)] = []
    // receiver connection
    private enum Phase { case none, waitingKey, live, dropping }
    private var phase = Phase.none
    private var send: ((Data) -> Void)?
    private var pending: (() -> Int)?
    private var keyRequested = false
    private var lastPending = 0
    private var lastDrain: TimeInterval = 0
    private var highWater = 400_000
    private var lowWater = 100_000
    private var floorBytes = 8_000        // smallest fragment that carries a picture, see setBitrate
    // counters
    private var counters = (pictures: 0, sent: 0, skipped: 0, overflows: 0, fragments: 0, bytes: 0, attaches: 0)
    var onKeyRequest: (() -> Void)?       // the next picture must be a key picture
    var onCongestion: (() -> Void)?       // the send queue overflowed: pictures are being skipped
    var onReset: ((String) -> Void)?      // "configuration" or "stall": the receiver has to load the stream again
    var onReady: (() -> Void)?            // the first initialization segment exists

    init(audioEncoder: NPAudioPacketEncoder) { self.audioEncoder = audioEncoder }

    var isReady: Bool { lock.lock(); defer { lock.unlock() }; return initialization != nil }
    // Time stamp, in seconds from the stream origin, of the newest picture produced.
    var newestPictureSeconds: Double { lock.lock(); defer { lock.unlock() }; return newestPicture }
    var statistics: [String: Any] {
        lock.lock(); defer { lock.unlock() }
        return ["pictures": counters.pictures, "sent": counters.sent, "skipped": counters.skipped, "overflows": counters.overflows, "fragments": counters.fragments,
                "bytes": counters.bytes, "attaches": counters.attaches, "silenceMs": Int(timeline.filled * 1000 / NPAudioTimeline.rate), "soundSkippedMs": Int(timeline.skipped * 1000 / NPAudioTimeline.rate),
                "width": size.width, "height": size.height]
    }
    // Send queue limits follow the bit rate: skip pictures above 0.35 s of stream waiting, resume below 0.1 s.
    // So does the smallest fragment: Chromium hands a response to its demuxer in blocks of 32 KB, so a still or simple
    // picture (a few hundred bytes) would reach the player a block at a time, seconds late (measured on Google's receiver
    // page: 4 to 17 s to start on a still screen). Padding keeps bytes flowing: up to 8 KB per picture, 60 % of the mean.
    func setBitrate(_ bitsPerSecond: Int) {
        lock.lock(); highWater = max(96_000, bitsPerSecond / 8 * 35 / 100); lowWater = max(24_000, bitsPerSecond / 80)
        floorBytes = max(2_000, min(8_000, bitsPerSecond / 8 / 60 * 6 / 10)); lock.unlock()
    }

    func consume(_ packet: Data, at now: TimeInterval = ProcessInfo.processInfo.systemUptime) {
        guard let kind = packet.first else { return }
        run {
            switch kind {
            case 3: configure(packet)
            case 4: picture(packet, now)
            case 5: sound(packet)
            default: break
            }
        }
    }
    // A receiver connection asks for the stream. False until the first configuration is known.
    // It starts on the next key picture, which is requested at once.
    func attach(send: @escaping (Data) -> Void, pending: @escaping () -> Int, at now: TimeInterval = ProcessInfo.processInfo.systemUptime) -> Bool {
        var accepted = false
        run {
            guard initialization != nil else { return }
            self.send = send; self.pending = pending; phase = .waitingKey; keyRequested = true
            ready.removeAll(); lastPending = 0; lastDrain = now; counters.attaches += 1; accepted = true
            deferred.append { [weak self] in self?.onKeyRequest?() }
        }
        return accepted
    }
    func detach() { run { send = nil; pending = nil; phase = .none } }

    private func run(_ body: () -> Void) {
        lock.lock(); body(); let after = deferred; deferred.removeAll(); lock.unlock()
        after.forEach { $0() }
    }
    private func configure(_ packet: Data) {
        let base = packet.startIndex
        guard packet.count > 10 else { return }
        let width = Int(packet[base + 1]) << 8 | Int(packet[base + 2]), height = Int(packet[base + 3]) << 8 | Int(packet[base + 4])
        let avcC = packet.subdata(in: (base + 10)..<packet.endIndex)
        guard avcC != configuration || width != size.width || height != size.height,
              let config = NPFragmentedMP4.aacSpecificConfig(sampleRate: Int(NPAudioTimeline.rate), channels: 2) else { return }
        let first = initialization == nil
        configuration = avcC; size = NPSize(width: width, height: height)
        initialization = NPFragmentedMP4.initialization(width: width, height: height, avcC: avcC, audio: .init(specificConfig: config, channels: 2, sampleRate: Int(NPAudioTimeline.rate)))
        if first { deferred.append { [weak self] in self?.onReady?() } }
        else if phase != .none { reset("configuration") } // a stream cannot change its picture size: the receiver loads again
    }
    private func reset(_ reason: String) {
        send = nil; pending = nil; phase = .none
        deferred.append { [weak self] in self?.onReset?(reason) }
    }
    private func picture(_ packet: Data, _ now: TimeInterval) {
        let base = packet.startIndex
        guard packet.count > 10 else { return }
        let micro = Self.u64(packet, base + 1), key = packet[base + 9] & 1 == 1
        let ticks = micro * 9 / 100
        let duration = lastPictureTicks.map { UInt32(min(9_000, max(750, Int64(ticks) - Int64($0)))) } ?? 1_500
        lastPictureTicks = ticks; newestPicture = Double(micro) / 1_000_000; counters.pictures += 1
        let fill = timeline.follow(picture: Int64(micro) * 48 / 1_000)
        if fill > 0 { appendSound(Data(count: fill * 4)) }
        guard phase != .none, let pending else { ready.removeAll(); return }
        let queued = pending()
        if queued == 0 || queued < lastPending { lastDrain = now }
        lastPending = queued
        if queued > highWater, now - lastDrain > Self.stallSeconds { reset("stall"); return }
        let sample = NPFragmentedMP4.Sample(data: packet.subdata(in: (base + 10)..<packet.endIndex), duration: duration, key: key)
        switch phase {
        case .waitingKey:
            guard key, let initialization, let send else { ready.removeAll(); requestKey(); return }
            send(initialization); phase = .live; keyRequested = false
            emit(picture: sample, ticks: ticks)
        case .live:
            if queued > highWater {
                phase = .dropping; keyRequested = false; counters.skipped += 1; counters.overflows += 1
                deferred.append { [weak self] in self?.onCongestion?() }
                emit(picture: nil, ticks: ticks)
            } else { emit(picture: sample, ticks: ticks) }
        case .dropping:
            if key, queued <= lowWater { phase = .live; keyRequested = false; emit(picture: sample, ticks: ticks) }
            else {
                // A key picture that came while the queue was still full is spent: another one is asked for once the queue is low.
                if key { keyRequested = false }
                counters.skipped += 1; if queued <= lowWater { requestKey() }; emit(picture: nil, ticks: ticks)
            }
        case .none: break
        }
    }
    private func requestKey() {
        guard !keyRequested else { return }
        keyRequested = true; deferred.append { [weak self] in self?.onKeyRequest?() }
    }
    private func sound(_ packet: Data) {
        let base = packet.startIndex, frames = (packet.count - 9) / 4
        guard frames > 0 else { return }
        let start = Int64(Self.u64(packet, base + 1)) * 48 / 1_000
        let expected = timeline.next
        let placed = timeline.place(start: start, count: frames)
        if let expected, start - expected - Int64(placed.silence) > NPAudioTimeline.jitter {
            // A hole longer than one fill: the track jumps, an unfinished block is dropped.
            block.removeAll(keepingCapacity: true)
            if let base = audioBase { audioBase = base + (start - expected - Int64(placed.silence)) }
        }
        if placed.silence > 0 { appendSound(Data(count: placed.silence * 4)) }
        if placed.take > 0 {
            let from = base + 9 + placed.skip * 4
            appendSound(packet.subdata(in: from..<(from + placed.take * 4)))
        }
        // Sound with no picture for a while (a still screen whose pictures stopped): it keeps flowing by itself.
        if ready.count >= 6, phase == .live || phase == .dropping { emit(picture: nil, ticks: 0) }
    }
    private func appendSound(_ samples: Data) {
        if audioBase == nil, let next = timeline.next { audioBase = next - Int64(samples.count / 4) - Self.aacPriming }
        block.append(samples)
        let size = Self.blockFrames * 4
        while block.count >= size {
            let chunk = block.prefix(size); block.removeFirst(size)
            for packet in audioEncoder.encode(block: Data(chunk)) {
                let time = (audioBase ?? 0) + packets * Int64(Self.blockFrames); packets += 1
                if time >= 0 { ready.append((time, packet)) } // packets before the origin only prime the decoder
            }
        }
        if ready.count > 96 { ready.removeFirst(ready.count - 96) }
    }
    // One fragment: the picture if any, then the sound packets that are due, as runs of contiguous packets.
    private func emit(picture: NPFragmentedMP4.Sample?, ticks: UInt64) {
        guard let send else { return }
        var runs: [NPFragmentedMP4.Run] = []
        if let picture { runs.append(.init(track: NPFragmentedMP4.videoTrack, decodeTime: ticks, samples: [picture])); counters.sent += 1 }
        var index = 0
        while index < ready.count {
            var end = index + 1
            while end < ready.count, ready[end].time == ready[end - 1].time + Int64(Self.blockFrames) { end += 1 }
            let samples = ready[index..<end].map { NPFragmentedMP4.Sample(data: $0.data, duration: UInt32(Self.blockFrames), key: true) }
            let run = NPFragmentedMP4.Run(track: NPFragmentedMP4.audioTrack, decodeTime: UInt64(ready[index].time), samples: samples)
            if index == 0 { runs.append(run) } else { flush(runs, send); runs = [run] } // a jump in the sound: its own fragment
            index = end
        }
        ready.removeAll(keepingCapacity: true)
        flush(runs, send)
    }
    private func flush(_ runs: [NPFragmentedMP4.Run], _ send: (Data) -> Void) {
        guard !runs.isEmpty else { return }
        sequence &+= 1
        let fragment = NPFragmentedMP4.fragment(sequence: sequence, runs: runs, minimumSize: runs.contains { $0.track == NPFragmentedMP4.videoTrack } ? floorBytes : 0)
        counters.fragments += 1; counters.bytes += fragment.count
        send(fragment)
    }
    private static func u64(_ data: Data, _ at: Int) -> UInt64 { (0..<8).reduce(UInt64(0)) { $0 << 8 | UInt64(data[at + $1]) } }
}
