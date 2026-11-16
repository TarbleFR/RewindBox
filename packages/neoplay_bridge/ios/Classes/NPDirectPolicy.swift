import Foundation

// Decisions of the direct Chromecast route, as pure state (no Apple framework):
// how far behind the receiver may play and how to bring it back, how the sound
// track stays continuous, and how the bit rate follows the link.

// The receiver's media element plays one endless response and never catches
// up by itself: every stall adds its length to the delay. The sender knows the
// time stamp of the newest picture it produced and reads the receiver's
// position, so `lag` is their difference in seconds. Above the target the
// receiver is asked to play slightly faster (1.1 to 1.5); a stall while or just
// after doing so means the target was below what this receiver can hold, and
// the target rises. A lag no rate can recover in reasonable time, or a stall
// that does not end, asks for a new load, which restarts at the live picture.
struct NPLagController {
    enum Action: Equatable { case none, rate(Float), reload }
    static let floorTarget = 0.45
    static let ceilingTarget = 1.5
    static let reloadLag = 4.0          // further behind than this: loading again is quicker than catching up
    static let stallReload: TimeInterval = 5
    static let commandInterval: TimeInterval = 0.4
    static let reloadInterval: TimeInterval = 10
    static let relaxAfter: TimeInterval = 60 // a minute without a stall lowers the target by one step
    private(set) var target = 0.55
    private(set) var rate: Float = 1
    private(set) var stalls = 0
    private(set) var reloads = 0
    private var lastCommand = -TimeInterval.infinity
    private var lastReload = -TimeInterval.infinity
    private var lastFast = -TimeInterval.infinity
    private var stallSince: TimeInterval?
    private var calmSince: TimeInterval?
    private var holdUntil = -TimeInterval.infinity
    private var recent: [Double] = []

    mutating func sample(lag: Double, stalled: Bool, at now: TimeInterval) -> Action {
        guard lag.isFinite else { return .none }
        if stalled {
            recent.removeAll(); calmSince = nil
            if stallSince == nil {
                stallSince = now; stalls += 1
                if now - lastFast < 3 { target = min(Self.ceilingTarget, target + 0.15) }
                holdUntil = now + 3
            }
            if let since = stallSince, now - since >= Self.stallReload { return reload(at: now) }
            return command(1, at: now)
        }
        stallSince = nil
        if calmSince == nil { calmSince = now }
        recent.append(lag); if recent.count > 5 { recent.removeFirst() }
        let median = recent.sorted()[recent.count / 2]
        if median > Self.reloadLag, recent.count >= 3 { return reload(at: now) }
        if let calm = calmSince, now - calm >= Self.relaxAfter, rate == 1 { target = max(Self.floorTarget, target - 0.05); calmSince = now }
        guard now >= holdUntil else { return command(1, at: now) }
        let excess = median - target
        let wanted: Float
        if excess > 1.2 { wanted = 1.5 } else if excess > 0.45 { wanted = 1.25 } else if excess > 0.12 { wanted = 1.1 }
        else if rate > 1, excess > 0.03 { wanted = min(rate, 1.1) } else { wanted = 1 }
        if wanted > 1 { lastFast = now }
        return command(wanted, at: now)
    }
    // A new load starts from the live picture: forget what was measured on the previous one.
    mutating func restarted(at now: TimeInterval) { rate = 1; recent.removeAll(); stallSince = nil; calmSince = nil; holdUntil = now + 2; lastCommand = -.infinity }
    private mutating func command(_ wanted: Float, at now: TimeInterval) -> Action {
        guard wanted != rate, now - lastCommand >= Self.commandInterval else { return .none }
        rate = wanted; lastCommand = now
        return .rate(wanted)
    }
    private mutating func reload(at now: TimeInterval) -> Action {
        guard now - lastReload >= Self.reloadInterval else { return .none }
        lastReload = now; reloads += 1; restarted(at: now)
        return .reload
    }
}

// Sound of the direct route, counted in samples at 48 kHz from the stream
// origin. The receiver plays sound as its clock: a hole in the sound track
// would stall the picture, and sound that stops (a silent game, a paused
// emulator) would stop everything. So the track is kept continuous: silence
// fills what the capture did not deliver, and capture sound that arrives for a
// span already filled is skipped.
// The capture's sound reaches the stream later than its pictures (its buffers,
// its queue): `lateness` measures by how much, and silence never fills that
// span, otherwise sound that resumes after a silence would always find its
// place taken and be lost for the rest of the session.
struct NPAudioTimeline {
    static let rate: Int64 = 48_000
    static let jitter: Int64 = 96            // 2 ms: treated as contiguous
    static let startWait: Int64 = 9_600      // 0.2 s of pictures without any sound: the track starts with silence
    static let maxBehind: Int64 = 12_000     // 0.25 s behind the pictures beyond the usual lateness: the capture is silent, fill
    static let keepBehind: Int64 = 2_880     // while silent the track follows the pictures 60 ms behind, beyond the lateness
    static let maxFill: Int64 = 96_000       // one fill is at most 2 s
    static let maxLateness: Int64 = 48_000   // 1 s
    private(set) var next: Int64?            // first sample not yet produced
    private(set) var silent = false
    private(set) var filled: Int64 = 0       // samples of silence produced
    private(set) var skipped: Int64 = 0      // capture samples dropped because their span was already filled
    private(set) var lateness: Int64 = 0     // samples: how far behind the newest picture a sound buffer ends when it arrives
    private var newestPicture: Int64?

    // Capture sound [start, start + count): silence to produce first, samples to skip at its head, samples to take.
    mutating func place(start: Int64, count: Int) -> (silence: Int, skip: Int, take: Int) {
        guard count > 0 else { return (0, 0, 0) }
        if let picture = newestPicture {
            // Up at once, down slowly: one early buffer must not let silence overrun the next late ones.
            let late = min(Self.maxLateness, max(0, picture - (start + Int64(count))))
            lateness = late > lateness ? late : lateness - (lateness - late) / 64
        }
        silent = false
        guard let expected = next else { next = start + Int64(count); return (0, 0, count) }
        let gap = start - expected
        if gap > Self.jitter {
            let silence = min(gap, Self.maxFill)
            filled += silence; next = start + Int64(count)
            return (Int(silence), 0, count)
        }
        if gap < -Self.jitter {
            let skip = Int(min(Int64(count), -gap)); skipped += Int64(skip)
            if skip < count { next = expected + Int64(count - skip) }
            return (0, skip, count - skip)
        }
        next = expected + Int64(count)
        return (0, 0, count)
    }
    // A picture at `sample` was produced: silence needed so that the sound track does not fall behind the pictures.
    mutating func follow(picture sample: Int64) -> Int {
        newestPicture = max(newestPicture ?? sample, sample)
        let keep = Self.keepBehind + lateness
        guard let expected = next else {
            guard sample >= Self.startWait else { return 0 }
            let fill = min(sample - keep, Self.maxFill)
            guard fill > 0 else { return 0 }
            next = fill; silent = true; filled += fill
            return Int(fill)
        }
        let behind = sample - expected
        guard behind > (silent ? keep + 1_024 : Self.maxBehind + lateness) else { return 0 }
        let fill = min(behind - keep, Self.maxFill)
        guard fill > 0 else { return 0 }
        next = expected + fill; silent = true; filled += fill
        return Int(fill)
    }
}

// Bit rate of the direct route. A send queue that overflows (pictures had to be
// skipped) lowers the rate by 30 %; thirty quiet seconds raise it by 15 %, up
// to the nominal rate of the picture size.
struct NPBitrateLadder {
    static let floor = 2_500_000
    static let quiet: TimeInterval = 30
    let nominal: Int
    private(set) var current: Int
    private var lastChange = -TimeInterval.infinity
    init(nominal: Int) { self.nominal = max(Self.floor, nominal); current = max(Self.floor, nominal) }
    mutating func congested(at now: TimeInterval) -> Int? {
        guard now - lastChange >= 2 else { return nil } // one overflow is one step
        let lower = max(Self.floor, current * 7 / 10); lastChange = now
        guard lower != current else { return nil }
        current = lower; return lower
    }
    mutating func tick(at now: TimeInterval) -> Int? {
        guard current < nominal, now - lastChange >= Self.quiet else { return nil }
        current = min(nominal, current * 115 / 100); lastChange = now
        return current
    }
}
