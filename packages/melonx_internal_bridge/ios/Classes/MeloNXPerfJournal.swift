import Foundation
import Darwin

// One "[MeloNX:perf]" line per second in MeloNX-performance.log while a game runs, to
// compare a stutter report with the standalone app on the same scene.
// Measurement only: nothing here changes emulation. Each line covers the
// interval since the previous one:
//   t=     seconds since the game's controls were installed
//   fps=   the engine's game FPS / frame time ms / FIFO %
//   mgd=   how long that engine call took, ms: entering the managed engine waits
//          while a GC suspends it, so a long value is a stop-the-world in progress
//          (read with the .NET_BGC CPU of the same line: a background GC that
//          marks shows its CPU; a suspension waiting for a thread shows none)
//   pres=  frames presented / longest gap between two presentations ms /
//          gaps over 20 ms / gaps over 40 ms (at 60 fps a gap over 20 ms is a
//          held frame; at 30 fps every frame exceeds 20 ms, read over 40)
//   long=  gaps over 50 ms / gaps over 100 ms (pauses at a 30 fps target)
//   gaps=  every gap between two presentations in the interval, ms rounded
//          (at most 240), for frame-time percentiles over any stretch of play
//   acq=   every interval between two drawable requests in the interval
//          (host time when the engine asked CAMetalLayer.nextDrawable for a
//          drawable; requests that got none are skipped), ms rounded (at most
//          240): the engine's own frame cadence, to tell a gap the game
//          produced from one the display added after it
//   acqw=  the longest wait inside nextDrawable in the interval, ms (every
//          drawable still held by the display or compositor); a request that
//          waited delays the engine's next one, so the acq= interval after
//          it includes that wait
//   dsp=   5 ms audio DSP periods / late episodes (a stall over 2 ms and its
//          catch-up periods count once) / their lateness ms / the longest ms /
//          periods skipped
//   out=   audio buffers played / queue starvations / silence ms / longest ms
//   cpu=   process CPU % (100 = one core), then the busiest threads as
//          name:CPU %/base priority (47 user-interactive, 37 user-initiated,
//          31 default, 20 utility, 4 background)
//   mem=   footprint MiB / headroom MiB / device available % / live donors
//          (host-supplied; absent when the host gives none)
//   in=    input the session's router handled in the interval (absent when
//          none): tL/tR touch and pL/pR controller events for the left/right
//          stick as count/largest magnitude; oL/oR the largest magnitude sent
//          to the engine for that stick (a source moving while oL stays 0 was
//          overridden); b button changes sent; d inputs dropped while paused
//          or closed; e writes the engine refused, count:last code
//   th= lp= thermal state and Low Power Mode; "paused" while the game is paused
// "[MeloNX:stall]" lines (MeloNXStallWatch, below): every thread of the process while one of these engine calls
// has been in flight 300 ms, 1.3 s and 3.3 s, then the call's duration.
// "[MeloNX:memory]" lines (MeloNXMemoryBreakdown, below): the footprint's ledgers and regions, every 60 s.
final class MeloNXPerfJournal {
    struct Presentation {
        var frames: UInt64 = 0, maxGapMs = 0.0, over20: UInt64 = 0, over40: UInt64 = 0
        var over50: UInt64 = 0, over100: UInt64 = 0, gapsMs: [UInt16] = []
        var acquireGapsMs: [UInt16] = []
        var maxAcquireWaitMs = 0.0
        static let gapLimit = 240
    }
    struct ThreadSample { let id: UInt64; let name: String; let cpuNs: UInt64; let priority: Int32 }
    static let topThreads = 6
    // The classified journal rotates at 8 MiB, retaining one previous file.
    // Host samples are also bounded to lineLimit lines per game. Native
    // performance events share this journal, independent of stderr volume.
    static let fileLimit: Int64 = 8 * 1024 * 1024
    static let thermalNames = ["nominal", "fair", "serious", "critical"]

    private let path: String
    private let context: [String:String]
    private let interval: Double
    private let lineLimit: Int
    private let fps: () -> [String: Any]
    private let presentation: () -> Presentation
    private let audio: () -> [Int64]?
    private let memory: () -> String?
    private let stalls: MeloNXStallWatch
    private let breakdown: MeloNXMemoryBreakdown
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
    private var totalOver50: UInt64 = 0, totalOver100: UInt64 = 0
    private var totalLate: Int64 = 0, totalLateNs: Int64 = 0, totalSkipped: Int64 = 0
    private var totalStarved: Int64 = 0, totalStarvedNs: Int64 = 0
    private var hottest = 0
    // in= comes from the running session's input router (one at a time); the
    // router installs it with its controls and removes it when it closes.
    private static let inputLock = NSLock()
    private static var inputOwner: ObjectIdentifier?
    private static var inputSource: (() -> String?)?

    init(path: String, context: [String:String] = [:], interval: Double = 1, lineLimit: Int = 1800,
         fps: @escaping () -> [String: Any], presentation: @escaping () -> Presentation,
         audio: @escaping () -> [Int64]?, memory: @escaping () -> String? = { nil }) {
        self.path = path; self.interval = interval; self.lineLimit = lineLimit
        self.context = context
        self.fps = fps; self.presentation = presentation; self.audio = audio; self.memory = memory
        self.stalls = MeloNXStallWatch(path:path, context:context)
        self.breakdown = MeloNXMemoryBreakdown(path:path, context:context)
    }

    func setPaused(_ value: Bool) { lock.lock(); paused = value; lock.unlock() }

    static func setInput(owner: AnyObject, _ source: (() -> String?)?) {
        inputLock.lock(); defer { inputLock.unlock() }
        if let source { inputOwner = ObjectIdentifier(owner); inputSource = source }
        else if inputOwner == ObjectIdentifier(owner) { inputOwner = nil; inputSource = nil }
    }
    private static func input() -> String? {
        inputLock.lock(); let source = inputSource; inputLock.unlock()
        return source?()
    }

    func start() {
        queue.async { [self] in
            guard timer == nil, started == 0 else { return }
            started = ProcessInfo.processInfo.systemUptime; last = started
            // Baselines; this read also clears the engine's audio maxima.
            previousShown = presentation()
            previousAudio = audio()
            for thread in Self.threads() { previousThreads[thread.id] = thread.cpuNs }
            MeloNXStdioCapture.appendLine(MeloNXStdioCapture.contextualLine("[MeloNX:perf] begin: every \(interval) s, \(ProcessInfo.processInfo.activeProcessorCount) cores, audio counters \(previousAudio == nil ? "unavailable" : "available")",context:context), to:path, limit:Self.fileLimit)
            let source = DispatchSource.makeTimerSource(queue:queue)
            source.schedule(deadline:.now() + interval, repeating:interval, leeway:.milliseconds(100))
            source.setEventHandler { [weak self] in self?.sample() }
            timer = source
            source.resume()
            stalls.start()
            breakdown.start()
        }
    }

    // Asynchronous: never waits on the sampler from the caller's thread.
    func stop() {
        queue.async { [self] in
            stalls.stop()
            breakdown.stop()
            guard let timer else { return }
            timer.cancel(); self.timer = nil
            let average = fpsCount > 0 ? fpsTotal / Double(fpsCount) : 0
            MeloNXStdioCapture.appendLine(MeloNXStdioCapture.contextualLine("[MeloNX:perf] end: \(samples) s sampled, \(lines) lines; game FPS \(Self.decimal(average)) on average while running; \(totalFrames) frames presented, \(totalOver20) gaps over 20 ms, \(totalOver40) over 40 ms, \(totalOver50) over 50 ms, \(totalOver100) over 100 ms; \(totalLate) late DSP episodes (\(Self.decimal(Double(totalLateNs) / 1e6)) ms), \(totalSkipped) skipped; \(totalStarved) audio starvations (\(Self.decimal(Double(totalStarvedNs) / 1e6)) ms); hottest thermal state \(Self.thermal(hottest))",context:context), to:path, limit:Self.fileLimit)
        }
    }

    private func sample() {
        let now = ProcessInfo.processInfo.systemUptime
        let elapsed = max(0.001, now - last); last = now
        lock.lock(); let isPaused = paused; lock.unlock()
        samples += 1
        var fields = ["t=" + String(Int((now - started).rounded()))]

        stalls.enter("fps")
        let callStart = ProcessInfo.processInfo.systemUptime
        let engine = fps()
        let callMs = (ProcessInfo.processInfo.systemUptime - callStart) * 1000
        stalls.exit()
        if let rate = engine["gameFps"] as? Double {
            let time = engine["gameFrameTimeMs"] as? Double ?? 0, fifo = engine["fifoPercent"] as? Double ?? 0
            fields.append("fps=\(Self.decimal(rate))/\(Self.decimal(time))/\(Int(fifo.rounded()))")
            // Boot seconds before the first measured frame read 0.
            if !isPaused && rate > 0 { fpsTotal += rate; fpsCount += 1 }
        } else { fields.append("fps=-") }
        fields.append("mgd=" + Self.decimal(callMs))

        let shown = presentation()
        let frames = shown.frames &- previousShown.frames
        let over20 = shown.over20 &- previousShown.over20, over40 = shown.over40 &- previousShown.over40
        let over50 = shown.over50 &- previousShown.over50, over100 = shown.over100 &- previousShown.over100
        previousShown = shown
        totalFrames &+= frames; totalOver20 &+= over20; totalOver40 &+= over40
        fields.append("pres=\(frames)/\(Self.decimal(shown.maxGapMs))/\(over20)/\(over40)")
        totalOver50 &+= over50; totalOver100 &+= over100
        fields.append("long=\(over50)/\(over100)")
        if !shown.gapsMs.isEmpty { fields.append("gaps=" + shown.gapsMs.map { String($0) }.joined(separator:",")) }
        if !shown.acquireGapsMs.isEmpty { fields.append("acq=" + shown.acquireGapsMs.map { String($0) }.joined(separator:",")) }
        if !shown.acquireGapsMs.isEmpty { fields.append("acqw=" + Self.decimal(shown.maxAcquireWaitMs)) }

        stalls.enter("audio")
        let pacing = audio()
        stalls.exit()
        if let values = pacing, values.count == 9 {
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

        stalls.enter("memory")
        let footprint = memory()
        stalls.exit()
        if let text = footprint { fields.append("mem=" + text) }
        if let text = Self.input() { fields.append("in=" + text) }

        let thermal = ProcessInfo.processInfo.thermalState.rawValue
        hottest = max(hottest, thermal)
        fields.append("th=" + Self.thermal(thermal))
        fields.append("lp=" + (ProcessInfo.processInfo.isLowPowerModeEnabled ? "1" : "0"))
        if isPaused { fields.append("paused") }

        guard lines < lineLimit else { return }
        lines += 1
        MeloNXStdioCapture.appendLine(MeloNXStdioCapture.contextualLine("[MeloNX:perf] " + fields.joined(separator:" "),context:context), to:path, limit:Self.fileLimit)
        if lines == lineLimit {
            MeloNXStdioCapture.appendLine(MeloNXStdioCapture.contextualLine("[MeloNX:perf] limit: \(lineLimit) lines; only the end summary follows",context:context), to:path, limit:Self.fileLimit)
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

// RewindBox (lot 9): who holds the engine during a long stop. IPA 718, Hogwarts Legacy: a background GC's final pause of
// 3666.692 ms and another of about 2.3 s seconds later, while the per-second journal itself ran 2-4 s late because its
// own call into the managed engine waited (entering managed code waits while a GC suspends it). The journal tells it
// enters one of its engine calls (enter/exit around fps(), audio() and memory()); a native thread that never calls the
// engine and takes no lock the engine takes looks every 50 ms. Once a call has been in flight 300 ms it records every
// thread of the process once: kernel run state (R running, W waiting, U uninterruptible, T stopped, H halted; i idle),
// suspend count, base/current priority, CPU ms (total, then +ms since the previous record of the same stall), and where
// it is: program counter, link register and up to 8 frame-pointer return addresses, each as image+offset (the library
// file's name), "jit:" for executable anonymous memory (translated guest code) or "anon:". Again at 1.3 s and 3.3 s of
// the same call (who progressed meanwhile), then one line with the call's duration. At most 6 stalls per journal.
// Reading: a GC suspension that waits for a thread shows the collecting thread in its suspension loop, the other managed
// threads parked in the runtime's wait, and the one it waits for elsewhere; a GC that works shows its thread running.
// Offsets inside the engine read with the Core artifact's symbol map (Ryujinx.Library.symbols.txt.gz,
// build_core.sh). It never suspends a thread itself: thread_get_state stops a running thread for the read only, in the
// kernel. Measurement only.
final class MeloNXStallWatch {
    static let stagesMs: [Double] = [300, 1300, 3300]
    static let maxStalls = 6
    static let maxFrames = 8
    static let addressMask: UInt64 = 0x0000_FFFF_FFFF_FFFF
    private static let timebase: mach_timebase_info_data_t = {
        var info = mach_timebase_info_data_t()
        mach_timebase_info(&info)
        return info
    }()

    private let path: String
    private let context: [String:String]
    private let lock = NSLock()
    // Guarded by lock: the call in flight (0 when none), the call the watch records (flagged) and when it returned.
    private var callStart: UInt64 = 0, callName = ""
    private var flagged: UInt64 = 0, flaggedEnd: UInt64 = 0
    private var running = false
    // Confined to the watch thread.
    private var watched: UInt64 = 0, watchedName = "", stage = 0, stalls = 0
    private var previousCpu: [UInt64: UInt64] = [:]

    init(path: String, context: [String:String]) {
        self.path = path; self.context = context
    }

    static func milliseconds(_ ticks: UInt64) -> Double {
        Double(ticks) * Double(timebase.numer) / Double(timebase.denom) / 1e6
    }

    func enter(_ name: String) {
        let now = mach_absolute_time()
        lock.lock(); callStart = now; callName = name; lock.unlock()
    }

    func exit() {
        let now = mach_absolute_time()
        lock.lock()
        if callStart != 0 && callStart == flagged { flaggedEnd = now }
        callStart = 0
        lock.unlock()
    }

    func start() {
        lock.lock(); defer { lock.unlock() }
        guard !running else { return }
        running = true
        let thread = Thread { [self] in watch() }
        thread.name = "RewindBox.MeloNX.StallWatch"
        thread.qualityOfService = .userInteractive
        thread.start()
    }

    // Asynchronous: the watch thread ends at its next look (after writing the end of a stall it was recording).
    func stop() { lock.lock(); running = false; lock.unlock() }

    private func watch() {
        while true {
            usleep(50_000)
            lock.lock()
            let alive = running, start = callStart, name = callName, ended = flaggedEnd
            lock.unlock()
            if watched != 0 && start != watched {
                let took = ended != 0 ? Self.decimal(Self.milliseconds(ended &- watched)) : "?"
                header("#\(stalls) end: \(watchedName) returned after \(took) ms")
                watched = 0; stage = 0
            }
            guard alive else { return }
            guard start != 0 else { continue }
            let age = Self.milliseconds(mach_absolute_time() &- start)
            if start != watched {
                guard stalls < Self.maxStalls, age >= Self.stagesMs[0] else { continue }
                stalls += 1; watched = start; watchedName = name; stage = 0; previousCpu = [:]
                lock.lock()
                // The call may have returned since it was read: its end is then unknown ("?"), never another call's.
                if callStart == start { flagged = start; flaggedEnd = 0 } else { flagged = 0; flaggedEnd = 0 }
                lock.unlock()
            }
            if stage < Self.stagesMs.count && age >= Self.stagesMs[stage] {
                snapshot(age: age)
                stage += 1
            }
        }
    }

    private func header(_ text: String) {
        _ = MeloNXStdioCapture.appendLine(MeloNXStdioCapture.contextualLine("[MeloNX:stall] " + text, context:context), to:path, limit:MeloNXPerfJournal.fileLimit)
    }

    private func snapshot(age: Double) {
        var list: thread_act_array_t?
        var count: mach_msg_type_number_t = 0
        guard task_threads(mach_task_self_, &list, &count) == KERN_SUCCESS, let list else { return }
        defer {
            for index in 0..<Int(count) { mach_port_deallocate(mach_task_self_, list[index]) }
            vm_deallocate(mach_task_self_, vm_address_t(UInt(bitPattern:list)), vm_size_t(Int(count) * MemoryLayout<thread_act_t>.stride))
        }
        let me = mach_thread_self()
        defer { mach_port_deallocate(mach_task_self_, me) }
        var lines: [String] = []
        var places: [UInt64: String] = [:]
        var cpu: [UInt64: UInt64] = [:]
        // Every thread is read first; the file is written after, so no thread is read late because of a write.
        for index in 0..<Int(count) {
            let thread = list[index]
            guard thread != me else { continue }
            var identifier = thread_identifier_info_data_t()
            var extended = thread_extended_info_data_t()
            var basic = thread_basic_info_data_t()
            guard Self.info(thread, THREAD_IDENTIFIER_INFO, &identifier), Self.info(thread, THREAD_EXTENDED_INFO, &extended),
                  Self.info(thread, THREAD_BASIC_INFO, &basic) else { continue }
            let id = identifier.thread_id
            let used = extended.pth_user_time &+ extended.pth_system_time
            cpu[id] = used
            let spent = previousCpu[id].map { "+" + Self.decimal(Double(used &- $0) / 1e6) } ?? Self.decimal(Double(used) / 1e6)
            var bytes = extended.pth_name
            var name = withUnsafeBytes(of:&bytes) { raw in String(decoding:raw.prefix(while:{ $0 != 0 }), as:UTF8.self) }
            name = String(name.map { $0.isWhitespace || $0 == ":" || $0 == "/" ? "_" : $0 }.prefix(24))
            if name.isEmpty { name = "thread\(id)" }
            var text = "t\(id) \(name) \(Self.state(basic.run_state))\(basic.flags & TH_FLAGS_IDLE != 0 ? "i" : "")" +
                " s\(basic.suspend_count) p\(extended.pth_priority)/\(extended.pth_curpri) c\(spent)"
            #if arch(arm64)
            var state = arm_thread_state64_t()
            var stateCount = mach_msg_type_number_t(MemoryLayout<arm_thread_state64_t>.size / MemoryLayout<natural_t>.size)
            let read = withUnsafeMutablePointer(to:&state) { pointer in
                pointer.withMemoryRebound(to:natural_t.self, capacity:Int(stateCount)) {
                    thread_get_state(thread, thread_state_flavor_t(ARM_THREAD_STATE64), $0, &stateCount)
                }
            }
            if read == KERN_SUCCESS {
                text += " pc=" + place(state.__pc, &places) + " lr=" + place(state.__lr, &places)
                let frames = Self.frames(from:state.__fp)
                if !frames.isEmpty { text += " bt=" + frames.map { place($0, &places) }.joined(separator:",") }
            }
            #endif
            lines.append(text)
        }
        previousCpu = cpu
        header("#\(stalls).\(stage) \(watchedName) in flight \(Int(age)) ms, \(lines.count) threads")
        for line in lines { _ = MeloNXStdioCapture.appendLine("[MeloNX:stall] #\(stalls).\(stage) " + line, to:path, limit:MeloNXPerfJournal.fileLimit) }
    }

    private static func state(_ value: Int32) -> String {
        switch value {
        case TH_STATE_RUNNING: return "R"
        case TH_STATE_STOPPED: return "T"
        case TH_STATE_WAITING: return "W"
        case TH_STATE_UNINTERRUPTIBLE: return "U"
        case TH_STATE_HALTED: return "H"
        default: return "?\(value)"
        }
    }

    // The frame records from fp: each is {previous fp, return address}; read with vm_read_overwrite, which fails on an
    // unmapped address instead of faulting; stops on a null, misaligned or non-increasing fp.
    private static func frames(from start: UInt64) -> [UInt64] {
        var result: [UInt64] = []
        var fp = start & addressMask
        while result.count < maxFrames, fp != 0, fp & 0xF == 0 {
            var record = (UInt64(0), UInt64(0))
            var size = vm_size_t(0)
            let status = withUnsafeMutableBytes(of:&record) { raw in
                vm_read_overwrite(mach_task_self_, vm_address_t(fp), 16, vm_address_t(UInt(bitPattern:raw.baseAddress)), &size)
            }
            guard status == KERN_SUCCESS, size == 16, record.1 != 0 else { break }
            result.append(record.1 & addressMask)
            let next = record.0 & addressMask
            guard next > fp else { break }
            fp = next
        }
        return result
    }

    private func place(_ raw: UInt64, _ cache: inout [UInt64: String]) -> String {
        let address = raw & Self.addressMask
        guard address != 0 else { return "0" }
        if let known = cache[address] { return known }
        var info = Dl_info()
        let text: String
        if let pointer = UnsafeRawPointer(bitPattern:UInt(address)), dladdr(pointer, &info) != 0, let file = info.dli_fname {
            let image = (String(cString:file) as NSString).lastPathComponent
            text = image + "+0x" + String(address &- UInt64(UInt(bitPattern:info.dli_fbase)), radix:16)
        } else {
            text = (Self.executable(address) ? "jit:0x" : "anon:0x") + String(address, radix:16)
        }
        cache[address] = text
        return text
    }

    private static func executable(_ address: UInt64) -> Bool {
        var region = vm_address_t(address)
        var size = vm_size_t(0)
        var info = vm_region_basic_info_data_64_t()
        var count = mach_msg_type_number_t(MemoryLayout<vm_region_basic_info_data_64_t>.size / MemoryLayout<Int32>.size)
        var object: mach_port_t = 0
        let status = withUnsafeMutablePointer(to:&info) { pointer in
            pointer.withMemoryRebound(to:Int32.self, capacity:Int(count)) {
                vm_region_64(mach_task_self_, &region, &size, VM_REGION_BASIC_INFO_64, $0, &count, &object)
            }
        }
        return status == KERN_SUCCESS && UInt64(region) <= address && info.protection & VM_PROT_EXECUTE != 0
    }

    private static func info<T>(_ thread: thread_act_t, _ flavor: Int32, _ value: inout T) -> Bool {
        var count = mach_msg_type_number_t(MemoryLayout<T>.size / MemoryLayout<natural_t>.size)
        return withUnsafeMutablePointer(to:&value) {
            $0.withMemoryRebound(to:integer_t.self, capacity:Int(count)) {
                thread_info(thread, thread_flavor_t(flavor), $0, &count) == KERN_SUCCESS
            }
        }
    }

    private static func decimal(_ value: Double) -> String { String(format:"%.1f", value) }
}

// Lot 9, RAM: what the footprint is made of. One "[MeloNX:memory]" line 30 s after the journal starts, then every 60 s, at
// most 30, from the journal's own utility queue:
//   footprint= phys_footprint / its peak MiB (the figure iOS kills the process on)
//   graphics=  the kernel's graphics ledger (Metal and IOAccelerator memory charged to the process) + its compressed part
//   internal= compressed= device= media= neural= purgeable=  the other TASK_VM_INFO ledgers, MiB
//   regions=   regions walked / walk time ms ("partial" when the walk hit its region or time bound)
//   groups=    the 8 largest groups of regions by VM tag, name:dirty+compressed MiB/resident MiB/regions; a name ending
//              in "~s" is shared memory, counted per object (an object mapped more than once counts once, in the group
//              of its tagged mapping, else of its largest one)
//   top=       the 6 largest regions: address:virtual MiB:group:share mode:dirty+compressed MiB/resident MiB
// Measurement only: it reads the process's own VM map and calls no engine closure.
final class MeloNXMemoryBreakdown {
    static let maxRegions = 400_000
    static let maxWalkMs = 400.0
    static let topGroups = 8
    static let topRegions = 6

    private let path: String
    private let context: [String:String]
    private let first: Double, every: Double, maxLines: Int
    private let queue = DispatchQueue(label:"RewindBox.MeloNX.Memory", qos:.utility)
    // Confined to the queue.
    private var timer: DispatchSourceTimer?
    private var started = 0.0
    private var lines = 0

    init(path: String, context: [String:String], first: Double = 30, every: Double = 60, maxLines: Int = 30) {
        self.path = path; self.context = context; self.first = first; self.every = every; self.maxLines = maxLines
    }

    func start() {
        queue.async { [self] in
            guard timer == nil, started == 0 else { return }
            started = ProcessInfo.processInfo.systemUptime
            let source = DispatchSource.makeTimerSource(queue:queue)
            source.schedule(deadline:.now() + first, repeating:every, leeway:.seconds(1))
            source.setEventHandler { [weak self] in self?.record() }
            timer = source
            source.resume()
        }
    }

    // Asynchronous, like the journal's stop.
    func stop() { queue.async { [self] in timer?.cancel(); timer = nil } }

    private func record() {
        guard lines < maxLines else { timer?.cancel(); timer = nil; return }
        lines += 1
        let seconds = Int((ProcessInfo.processInfo.systemUptime - started).rounded())
        _ = MeloNXStdioCapture.appendLine(MeloNXStdioCapture.contextualLine("[MeloNX:memory] " + Self.describe(seconds:seconds), context:context), to:path, limit:MeloNXPerfJournal.fileLimit)
    }

    private struct Group { var dirty: UInt64 = 0, resident: UInt64 = 0, regions = 0 }
    private struct Region { let address: UInt64, size: UInt64, group: String, share: UInt8, dirty: UInt64, resident: UInt64 }

    static func describe(seconds: Int) -> String {
        var parts = ["t=\(seconds)"]
        var vm = task_vm_info_data_t()
        var vmCount = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
        let vmStatus = withUnsafeMutablePointer(to:&vm) {
            $0.withMemoryRebound(to:integer_t.self, capacity:Int(vmCount)) { task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &vmCount) }
        }
        if vmStatus == KERN_SUCCESS {
            parts.append("footprint=\(mib(vm.phys_footprint))/\(mib(vm.ledger_phys_footprint_peak))")
            parts.append("graphics=\(mib(vm.ledger_tag_graphics_footprint))+\(mib(vm.ledger_tag_graphics_footprint_compressed))")
            parts.append("internal=\(mib(vm.internal)) compressed=\(mib(vm.compressed)) device=\(mib(vm.device))")
            parts.append("media=\(mib(vm.ledger_tag_media_footprint)) neural=\(mib(vm.ledger_tag_neural_footprint))")
            parts.append("purgeable=\(mib(vm.ledger_purgeable_nonvolatile))+\(mib(vm.ledger_purgeable_volatile))")
        } else {
            parts.append("ledgers=\(vmStatus)")
        }

        let page = UInt64(vm_page_size)
        let begin = DispatchTime.now().uptimeNanoseconds
        var groups: [String: Group] = [:]
        var sharedObjects: [UInt32: (group: String, tagged: Bool, dirty: UInt64, resident: UInt64)] = [:]
        var largest: [Region] = []
        var address: vm_address_t = 0
        var depth: natural_t = 0
        var regions = 0
        var partial = false
        while true {
            if regions >= maxRegions || Double(DispatchTime.now().uptimeNanoseconds - begin) / 1e6 > maxWalkMs { partial = true; break }
            var size: vm_size_t = 0
            var info = vm_region_submap_info_data_64_t()
            var count = mach_msg_type_number_t(MemoryLayout<vm_region_submap_info_data_64_t>.size / MemoryLayout<natural_t>.size)
            let status = withUnsafeMutablePointer(to:&info) {
                $0.withMemoryRebound(to:integer_t.self, capacity:Int(count)) {
                    vm_region_recurse_64(mach_task_self_, &address, &size, &depth, $0, &count)
                }
            }
            guard status == KERN_SUCCESS else { break } // past the last region
            if info.is_submap != 0 { depth += 1; continue }
            regions += 1
            let dirty = (UInt64(info.pages_dirtied) + UInt64(info.pages_swapped_out)) * page
            let resident = UInt64(info.pages_resident) * page
            let share = UInt8(truncatingIfNeeded:info.share_mode)
            let mode = Int32(share)
            let shared = mode == SM_SHARED || mode == SM_TRUESHARED || mode == SM_SHARED_ALIASED
            let name = group(info.user_tag) + (shared ? "~s" : "")
            if shared {
                // Every mapping of one object sees the same pages: the object counts once, in the group of a tagged mapping
                // when it has one, else of its largest mapping.
                let tagged = info.user_tag != 0
                if let previous = sharedObjects[info.object_id] {
                    let better = (tagged && !previous.tagged) || (tagged == previous.tagged && dirty > previous.dirty)
                    sharedObjects[info.object_id] = (better ? name : previous.group, previous.tagged || tagged,
                                                     max(dirty, previous.dirty), max(resident, previous.resident))
                } else {
                    sharedObjects[info.object_id] = (name, tagged, dirty, resident)
                }
            } else {
                groups[name, default:Group()].dirty += dirty
                groups[name, default:Group()].resident += resident
                groups[name, default:Group()].regions += 1
            }
            if dirty > 0 && (largest.count < topRegions || dirty > largest[largest.count - 1].dirty) {
                largest.append(Region(address:UInt64(address), size:UInt64(size), group:name, share:share, dirty:dirty, resident:resident))
                largest.sort { $0.dirty > $1.dirty }
                if largest.count > topRegions { largest.removeLast() }
            }
            address &+= size
            if address == 0 { break } // wrapped past the top of the address space
        }
        for object in sharedObjects.values {
            groups[object.group, default:Group()].dirty += object.dirty
            groups[object.group, default:Group()].resident += object.resident
            groups[object.group, default:Group()].regions += 1
        }
        let walkMs = Double(DispatchTime.now().uptimeNanoseconds - begin) / 1e6
        parts.append("regions=\(regions)/\(String(format:"%.1f", walkMs))ms" + (partial ? "/partial" : ""))
        let ranked = groups.sorted { $0.value.dirty != $1.value.dirty ? $0.value.dirty > $1.value.dirty : $0.key < $1.key }
        parts.append("groups=" + ranked.prefix(topGroups).map { "\($0.key):\(mib($0.value.dirty))/\(mib($0.value.resident))/\($0.value.regions)" }.joined(separator:","))
        parts.append("top=" + largest.map { "0x" + String($0.address, radix:16) + ":\(mib($0.size)):\($0.group):\(shareName($0.share)):\(mib($0.dirty))/\(mib($0.resident))" }.joined(separator:","))
        return parts.joined(separator:" ")
    }

    private static func mib<T: BinaryInteger>(_ bytes: T) -> String { String(Int64(clamping:bytes) >> 20) }

    // VM tags (mach/vm_statistics.h): the malloc zones together, the app-specific ones by number.
    private static func group(_ tag: UInt32) -> String {
        switch tag {
        case 0: return "untagged"
        case 1...13: return "malloc"
        case 20: return "mach_msg"
        case 21: return "iokit"
        case 30: return "stack"
        case 31: return "guard"
        case 32, 35: return "pmap"
        case 33: return "dylib"
        case 60, 61: return "dyld"
        case 82, 83: return "swift"
        case 88: return "iosurface"
        case 100: return "ioaccelerator"
        case 240...255: return "app\(tag - 239)"
        default: return "tag\(tag)"
        }
    }

    private static func shareName(_ mode: UInt8) -> String {
        switch Int32(mode) {
        case SM_COW: return "cow"
        case SM_PRIVATE: return "private"
        case SM_EMPTY: return "empty"
        case SM_SHARED: return "shared"
        case SM_TRUESHARED: return "trueshared"
        case SM_PRIVATE_ALIASED: return "aliased"
        case SM_SHARED_ALIASED: return "sharedaliased"
        case SM_LARGE_PAGE: return "large"
        default: return String(mode)
        }
    }
}
