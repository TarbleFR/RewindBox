import Foundation

// "frames" route of the RewindBox Cast receiver (tools/neoplay-cast-receiver): the packets of NPFrameEncoder as they are
// (3 configuration, 4 picture, 5 sound; see its header), each preceded by its length (u32, big-endian), as one endless
// HTTP response that the receiver decodes with WebCodecs. No container and no AAC: the receiver plays the PCM itself.
// One receiver connection at a time. It starts with the configuration and a key picture. When the send queue grows past
// what the link drains, pictures are skipped up to the next key picture (sound keeps flowing); a queue that does not drain
// at all closes the connection, and the receiver opens a new one by itself. A later configuration (an encoder rebuilt for
// a rotation or a tier) goes in band: the receiver reconfigures its decoder without a new connection.
// Pure Foundation, same threading contract as NPDirectStream: one lock; `send` and `pending` are called under it and must
// not call back; the other callbacks run after it is released.
final class NPFramesStream: NPLiveSource {
    static let stallSeconds: TimeInterval = 2.5
    private let lock = NSLock()
    private var deferred: [() -> Void] = []
    private var configuration: Data?
    private var size = NPSize(width: 0, height: 0)
    private var newestPicture = 0.0
    private enum Phase { case none, waitingKey, live, dropping }
    private var phase = Phase.none
    private var send: ((Data) -> Void)?
    private var pending: (() -> Int)?
    private var keyRequested = false
    private var lastPending = 0
    private var lastDrain: TimeInterval = 0
    private var highWater = 400_000
    private var lowWater = 100_000
    private var counters = (pictures: 0, sent: 0, skipped: 0, overflows: 0, sounds: 0, soundsDropped: 0, bytes: 0, attaches: 0, configurations: 0)
    var onKeyRequest: (() -> Void)?       // the next picture must be a key picture
    var onCongestion: (() -> Void)?       // the send queue overflowed: pictures are being skipped
    var onReset: ((String) -> Void)?      // "stall": the connection is being closed, the receiver reconnects
    var onReady: (() -> Void)?            // the first configuration exists: the stream can be served

    var isReady: Bool { lock.lock(); defer { lock.unlock() }; return configuration != nil }
    var newestPictureSeconds: Double { lock.lock(); defer { lock.unlock() }; return newestPicture }
    var statistics: [String: Any] {
        lock.lock(); defer { lock.unlock() }
        return ["pictures": counters.pictures, "sent": counters.sent, "skipped": counters.skipped, "overflows": counters.overflows, "sounds": counters.sounds,
                "soundsDropped": counters.soundsDropped, "bytes": counters.bytes, "attaches": counters.attaches, "configurations": counters.configurations,
                "width": size.width, "height": size.height]
    }
    // Same limits as the direct route: skip pictures above 0.35 s of stream waiting, resume below 0.1 s.
    func setBitrate(_ bitsPerSecond: Int) {
        lock.lock(); highWater = max(96_000, bitsPerSecond / 8 * 35 / 100); lowWater = max(24_000, bitsPerSecond / 80); lock.unlock()
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
    func attach(send: @escaping (Data) -> Void, pending: @escaping () -> Int, at now: TimeInterval) -> Bool {
        var accepted = false
        run {
            guard configuration != nil else { return }
            self.send = send; self.pending = pending; phase = .waitingKey; keyRequested = true
            lastPending = 0; lastDrain = now; counters.attaches += 1; accepted = true
            deferred.append { [weak self] in self?.onKeyRequest?() }
        }
        return accepted
    }
    func detach() { run { send = nil; pending = nil; phase = .none } }

    private func run(_ body: () -> Void) {
        lock.lock(); body(); let after = deferred; deferred.removeAll(); lock.unlock()
        after.forEach { $0() }
    }
    private func emit(_ packet: Data) {
        guard let send else { return }
        var framed = Data(capacity: packet.count + 4)
        let length = UInt32(packet.count).bigEndian
        withUnsafeBytes(of: length) { framed.append(contentsOf: $0) }
        framed.append(packet)
        counters.bytes += framed.count
        send(framed)
    }
    private func configure(_ packet: Data) {
        let base = packet.startIndex
        guard packet.count > 10 else { return }
        let first = configuration == nil
        configuration = packet; counters.configurations += 1
        let width = Int(packet[base + 1]) << 8 | Int(packet[base + 2])
        let height = Int(packet[base + 3]) << 8 | Int(packet[base + 4])
        size = NPSize(width: width, height: height)
        if first { deferred.append { [weak self] in self?.onReady?() } }
        else if phase == .live || phase == .dropping { emit(packet) } // the new encoder's first picture is a key picture
    }
    private func picture(_ packet: Data, _ now: TimeInterval) {
        let base = packet.startIndex
        guard packet.count > 10 else { return }
        let micro = (0..<8).reduce(UInt64(0)) { $0 << 8 | UInt64(packet[base + 1 + $1]) }, key = packet[base + 9] & 1 == 1
        newestPicture = Double(micro) / 1_000_000; counters.pictures += 1
        guard phase != .none, let pending else { return }
        let queued = pending()
        if queued == 0 || queued < lastPending { lastDrain = now }
        lastPending = queued
        if queued > highWater, now - lastDrain > Self.stallSeconds { reset("stall"); return }
        switch phase {
        case .waitingKey:
            guard key, let configuration else { requestKey(); return }
            emit(configuration); emit(packet); phase = .live; keyRequested = false; counters.sent += 1
        case .live:
            if queued > highWater {
                phase = .dropping; keyRequested = false; counters.skipped += 1; counters.overflows += 1
                deferred.append { [weak self] in self?.onCongestion?() }
            } else { emit(packet); counters.sent += 1 }
        case .dropping:
            if key, queued <= lowWater { phase = .live; keyRequested = false; emit(packet); counters.sent += 1 }
            else {
                // A key picture that came while the queue was still full is spent: another one is asked for once it is low.
                if key { keyRequested = false }
                counters.skipped += 1; if queued <= lowWater { requestKey() }
            }
        case .none: break
        }
    }
    // Sound keeps flowing while pictures are skipped (it is a fiftieth of the stream), unless the queue is far beyond the
    // point where pictures are skipped: then the link is not draining at all.
    private func sound(_ packet: Data) {
        guard phase == .live || phase == .dropping, let pending else { return }
        if pending() > highWater * 2 { counters.soundsDropped += 1; return }
        emit(packet); counters.sounds += 1
    }
    private func requestKey() {
        guard !keyRequested else { return }
        keyRequested = true; deferred.append { [weak self] in self?.onKeyRequest?() }
    }
    private func reset(_ reason: String) {
        send = nil; pending = nil; phase = .none
        deferred.append { [weak self] in self?.onReset?(reason) }
    }
}
