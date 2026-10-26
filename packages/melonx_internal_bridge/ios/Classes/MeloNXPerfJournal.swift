import Foundation
import Darwin

// One "[MeloNX:perf]" line per second in app.log while a MeloNX game runs, to
// compare a stutter report with the standalone app on the same scene.
// Measurement only: nothing here changes emulation. Each line covers the
// interval since the previous one:
//   t=     seconds since the game's controls were installed
//   fps=   the engine's game FPS / frame time ms / FIFO %
//   pres=  frames presented / longest gap between two presentations ms /
//          gaps over 20 ms / gaps over 40 ms (at 60 fps a gap over 20 ms is a
//          held frame; at 30 fps every frame exceeds 20 ms, read over 40)
//   dsp=   5 ms audio DSP periods / late episodes (a stall over 2 ms and its
//          catch-up periods count once) / their lateness ms / the longest ms /
//          periods skipped
//   out=   audio buffers played / queue starvations / silence ms / longest ms
//   cpu=   process CPU % (100 = one core), then the busiest threads as
//          name:CPU %/base priority (47 user-interactive, 37 user-initiated,
//          31 default, 20 utility, 4 background)
//   th= lp= thermal state and Low Power Mode; "paused" while the game is paused
final class MeloNXPerfJournal {
    struct Presentation {
        var frames: UInt64 = 0, maxGapMs = 0.0, over20: UInt64 = 0, over40: UInt64 = 0
    }
    struct ThreadSample { let id: UInt64; let name: String; let cpuNs: UInt64; let priority: Int32 }
    static let topThreads = 6
    // app.log's general cap is 5 MiB; this journal is bounded (lineLimit lines
    // per game), so it may write past that up to here and is not cut off by
    // a long stderr capture.
    static let fileLimit: Int64 = 8 * 1024 * 1024
    static let thermalNames = ["nominal", "fair", "serious", "critical"]

    private let path: String
    private let interval: Double
    private let lineLimit: Int
    private let fps: () -> [String: Any]
    private let presentation: () -> Presentation
    private let audio: () -> [Int64]?
    private let queue = DispatchQueue(label:"RewindBox.MeloNX.Perf", qos:.utility)
    private let lock = NSLock()
    private var paused = false
    // Confined to the queue.
    private var timer: DispatchSourceTimer?
    private var started = 0.0, last = 0.0
    private var lines = 0, samples = 0
    private var previousShown = Presentation()
    private var previousAudio: [Int64]?
    private var previousThreads: [UInt64: UInt64] = [:]
    private var fpsTotal = 0.0, fpsCount = 0
    private var totalFrames: UInt64 = 0, totalOver20: UInt64 = 0, totalOver40: UInt64 = 0
    private var totalLate: Int64 = 0, totalLateNs: Int64 = 0, totalSkipped: Int64 = 0
    private var totalStarved: Int64 = 0, totalStarvedNs: Int64 = 0
    private var hottest = 0

    init(path: String, interval: Double = 1, lineLimit: Int = 1800,
         fps: @escaping () -> [String: Any], presentation: @escaping () -> Presentation,
         audio: @escaping () -> [Int64]?) {
        self.path = path; self.interval = interval; self.lineLimit = lineLimit
        self.fps = fps; self.presentation = presentation; self.audio = audio
    }

    func setPaused(_ value: Bool) { lock.lock(); paused = value; lock.unlock() }

    func start() {
        queue.async { [self] in
            guard timer == nil, started == 0 else { return }
            started = ProcessInfo.processInfo.systemUptime; last = started
            // Baselines; this read also clears the engine's audio maxima.
            previousShown = presentation()
            previousAudio = audio()
            for thread in Self.threads() { previousThreads[thread.id] = thread.cpuNs }
            MeloNXStdioCapture.appendLine("[MeloNX:perf] begin: every \(interval) s, \(ProcessInfo.processInfo.activeProcessorCount) cores, audio counters \(previousAudio == nil ? "unavailable" : "available")", to:path, limit:Self.fileLimit)
            let source = DispatchSource.makeTimerSource(queue:queue)
            source.schedule(deadline:.now() + interval, repeating:interval, leeway:.milliseconds(100))
            source.setEventHandler { [weak self] in self?.sample() }
            timer = source
            source.resume()
        }
    }

    // Asynchronous: never waits on the sampler from the caller's thread.
    func stop() {
        queue.async { [self] in
            guard let timer else { return }
            timer.cancel(); self.timer = nil
            let average = fpsCount > 0 ? fpsTotal / Double(fpsCount) : 0
            MeloNXStdioCapture.appendLine("[MeloNX:perf] end: \(samples) s sampled, \(lines) lines; game FPS \(Self.decimal(average)) on average while running; \(totalFrames) frames presented, \(totalOver20) gaps over 20 ms, \(totalOver40) over 40 ms; \(totalLate) late DSP episodes (\(Self.decimal(Double(totalLateNs) / 1e6)) ms), \(totalSkipped) skipped; \(totalStarved) audio starvations (\(Self.decimal(Double(totalStarvedNs) / 1e6)) ms); hottest thermal state \(Self.thermal(hottest))", to:path, limit:Self.fileLimit)
        }
    }

    private func sample() {
        let now = ProcessInfo.processInfo.systemUptime
        let elapsed = max(0.001, now - last); last = now
        lock.lock(); let isPaused = paused; lock.unlock()
        samples += 1
        var fields = ["t=" + String(Int((now - started).rounded()))]

        let engine = fps()
        if let rate = engine["gameFps"] as? Double {
            let time = engine["gameFrameTimeMs"] as? Double ?? 0, fifo = engine["fifoPercent"] as? Double ?? 0
            fields.append("fps=\(Self.decimal(rate))/\(Self.decimal(time))/\(Int(fifo.rounded()))")
            // Boot seconds before the first measured frame read 0.
            if !isPaused && rate > 0 { fpsTotal += rate; fpsCount += 1 }
        } else { fields.append("fps=-") }

        let shown = presentation()
        let frames = shown.frames &- previousShown.frames
        let over20 = shown.over20 &- previousShown.over20, over40 = shown.over40 &- previousShown.over40
        previousShown = shown
        totalFrames &+= frames; totalOver20 &+= over20; totalOver40 &+= over40
        fields.append("pres=\(frames)/\(Self.decimal(shown.maxGapMs))/\(over20)/\(over40)")

        if let values = audio(), values.count == 9 {
            let before = previousAudio ?? values
            previousAudio = values
            func delta(_ index: Int) -> Int64 { max(0, values[index] - before[index]) }
            totalLate += delta(1); totalLateNs += delta(2); totalSkipped += delta(4)
            totalStarved += delta(6); totalStarvedNs += delta(7)
            fields.append("dsp=\(delta(0))/\(delta(1))/\(Self.decimal(Double(delta(2)) / 1e6))/\(Self.decimal(Double(values[3]) / 1e6))/\(delta(4))")
            fields.append("out=\(delta(5))/\(delta(6))/\(Self.decimal(Double(delta(7)) / 1e6))/\(Self.decimal(Double(values[8]) / 1e6))")
        } else { fields.append("dsp=- out=-") }

        var current: [UInt64: UInt64] = [:]
        var busy: [(name: String, ns: UInt64, priority: Int32)] = []
        var total: UInt64 = 0
        for thread in Self.threads() {
            current[thread.id] = thread.cpuNs
            // A thread created during the interval counts from zero.
            let before = previousThreads[thread.id] ?? 0
            guard thread.cpuNs >= before else { continue }
            let used = thread.cpuNs - before
            total &+= used
            busy.append((name:thread.name, ns:used, priority:thread.priority))
        }
        previousThreads = current
        busy.sort { $0.ns > $1.ns }
        func percent(_ ns: UInt64) -> Int { Int((Double(ns) / (elapsed * 1e9) * 100).rounded()) }
        var cpu = "cpu=\(percent(total))"
        for thread in busy.prefix(Self.topThreads) where thread.ns > 0 {
            cpu += " \(thread.name):\(percent(thread.ns))/\(thread.priority)"
        }
        fields.append(cpu)

        let thermal = ProcessInfo.processInfo.thermalState.rawValue
        hottest = max(hottest, thermal)
        fields.append("th=" + Self.thermal(thermal))
        fields.append("lp=" + (ProcessInfo.processInfo.isLowPowerModeEnabled ? "1" : "0"))
        if isPaused { fields.append("paused") }

        guard lines < lineLimit else { return }
        lines += 1
        MeloNXStdioCapture.appendLine("[MeloNX:perf] " + fields.joined(separator:" "), to:path, limit:Self.fileLimit)
        if lines == lineLimit {
            MeloNXStdioCapture.appendLine("[MeloNX:perf] limit: \(lineLimit) lines; only the end summary follows", to:path, limit:Self.fileLimit)
        }
    }

    private static func decimal(_ value: Double) -> String { String(format:"%.1f", value) }
    private static func thermal(_ value: Int) -> String { value >= 0 && value < thermalNames.count ? thermalNames[value] : String(value) }

    // Every thread of this process: kernel identifier, name, total CPU time
    // and base scheduling priority, read without touching the threads.
    static func threads() -> [ThreadSample] {
        var list: thread_act_array_t?
        var count: mach_msg_type_number_t = 0
        guard task_threads(mach_task_self_, &list, &count) == KERN_SUCCESS, let list else { return [] }
        defer {
            for index in 0..<Int(count) { mach_port_deallocate(mach_task_self_, list[index]) }
            vm_deallocate(mach_task_self_, vm_address_t(UInt(bitPattern:list)), vm_size_t(Int(count) * MemoryLayout<thread_act_t>.stride))
        }
        var result: [ThreadSample] = []
        for index in 0..<Int(count) {
            var identifier = thread_identifier_info_data_t()
            var extended = thread_extended_info_data_t()
            guard info(list[index], THREAD_IDENTIFIER_INFO, &identifier),
                  info(list[index], THREAD_EXTENDED_INFO, &extended) else { continue }
            var bytes = extended.pth_name
            var name = withUnsafeBytes(of:&bytes) { raw in String(decoding:raw.prefix(while:{ $0 != 0 }), as:UTF8.self) }
            name = String(name.map { $0.isWhitespace || $0 == ":" || $0 == "/" ? "_" : $0 }.prefix(24))
            if name.isEmpty { name = "thread\(identifier.thread_id)" }
            // THREAD_EXTENDED_INFO reports CPU times in nanoseconds.
            result.append(ThreadSample(id:identifier.thread_id, name:name,
                                       cpuNs:extended.pth_user_time &+ extended.pth_system_time,
                                       priority:extended.pth_priority))
        }
        return result
    }

    private static func info<T>(_ thread: thread_act_t, _ flavor: Int32, _ value: inout T) -> Bool {
        var count = mach_msg_type_number_t(MemoryLayout<T>.size / MemoryLayout<natural_t>.size)
        return withUnsafeMutablePointer(to:&value) {
            $0.withMemoryRebound(to:integer_t.self, capacity:Int(count)) {
                thread_info(thread, thread_flavor_t(flavor), $0, &count) == KERN_SUCCESS
            }
        }
    }
}
