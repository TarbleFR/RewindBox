import Foundation
import Darwin

// "[MeloNX:hot]" lines in MeloNX-performance.log: where the busiest threads of the process are while the game runs
// below its target, and while it runs on target, to compare. IPA 725 (Hogwarts Legacy): 20 s at 30 FPS with about
// 240 million instructions per frame, stretches at 20 FPS with 460 to 530 million; the engine's own timers say which
// subsystem the GPU thread is in (bindings, compute), not which code, and say nothing of the guest's threads.
//
// The per-second sampler asks for a profile (observe): after three lines in a row under 26 FPS ("slow", at most four a
// session) or at 28.5 FPS and more ("base", at most two), never within 40 s of the start or 20 s of another profile,
// never while paused. A profile reads the six busiest threads of that line 300 times, 10 ms apart, from a native thread
// that never calls the engine and suspends nothing (thread_get_state stops a running thread for the read only, in the
// kernel): the kernel run state, the program counter and up to six frame-pointer return addresses. Then, per thread:
//   run= wait=  samples found running or runnable / waiting (missed= reads that failed: a thread that ended)
//   self=       where the program counter was, running samples only: place:samples, the 32 most frequent; program
//               counters within the same 64 bytes of an image are counted together, under the first one read (an
//               exact address per instruction spreads a hot function over dozens of entries of one sample each)
//   stack=      the return addresses present in a running sample (each counted once per sample): the 48 most frequent.
//               A return address is a call site: its count is the time spent in what that site called, callees
//               included, and it names both the caller (the function it is in) and, for a direct call, the callee
//   waiting=    the same for the waiting samples (the kernel's and pthread's own frames left out): the 12 most frequent
// A place is image+offset (the library file's name), "jit" for executable anonymous memory (translated guest code, all
// addresses together) or "anon". Offsets inside the engine read with the Core artifact's symbol map
// (tools/melonx/hot_spots.py). At most 7 lines a profile, 42 a session. Measurement only.
final class MeloNXHotSpots {
    static let rounds = 300
    static let periodMicroseconds: UInt32 = 10_000
    static let maxThreads = 6, maxFrames = 6
    static let maxSlow = 4, maxBase = 2
    static let minSecond = 40, gapSeconds = 20, streak = 3
    static let slowBelow = 26.0, baseFrom = 28.5
    static let selfPlaces = 32, stackPlaces = 48, waitPlaces = 12
    static let selfBlockBytes: UInt64 = 64

    struct Target { let id: UInt64; let name: String; let priority: Int32 }
    struct Request { let number: Int; let kind: String; let second: Int; let fps: Double; let targets: [Target] }

    private let path: String
    private let context: [String:String]
    private let lock = NSLock()
    private let wake = DispatchSemaphore(value:0)
    // Guarded by lock.
    private var running = false, busy = false
    private var pending: Request?
    // Confined to the sampler queue (observe).
    private var slowStreak = 0, baseStreak = 0, slowDone = 0, baseDone = 0, lastSecond = -1_000, profiles = 0

    init(path: String, context: [String:String]) {
        self.path = path; self.context = context
    }

    func start() {
        lock.lock(); defer { lock.unlock() }
        guard !running else { return }
        running = true
        let thread = Thread { [self] in work() }
        thread.name = "RewindBox.MeloNX.HotSpots"
        thread.qualityOfService = .userInteractive
        thread.start()
    }

    // Asynchronous: the thread ends once the profile it may be taking is written.
    func stop() {
        lock.lock(); running = false; lock.unlock()
        wake.signal()
    }

    /// What one per-second line asks for: nothing, a "slow" profile or a "base" one. The streaks are the caller's.
    static func decide(second: Int, fps: Double, paused: Bool, slowStreak: inout Int, baseStreak: inout Int,
                       slowDone: Int, baseDone: Int, lastSecond: Int) -> String? {
        guard !paused, fps > 0, second >= minSecond else { slowStreak = 0; baseStreak = 0; return nil }
        slowStreak = fps < slowBelow ? slowStreak + 1 : 0
        baseStreak = fps >= baseFrom ? baseStreak + 1 : 0
        guard second - lastSecond >= gapSeconds else { return nil }
        if slowStreak >= streak && slowDone < maxSlow { return "slow" }
        if baseStreak >= streak && baseDone < maxBase { return "base" }
        return nil
    }

    /// From the sampler, once per line, with the line's busiest threads first. Never blocks.
    func observe(second: Int, fps: Double?, paused: Bool, threads: [Target]) {
        guard let kind = Self.decide(second:second, fps:fps ?? 0, paused:paused, slowStreak:&slowStreak, baseStreak:&baseStreak,
                                     slowDone:slowDone, baseDone:baseDone, lastSecond:lastSecond), !threads.isEmpty else { return }
        lock.lock()
        let free = running && !busy && pending == nil
        if free {
            profiles += 1
            pending = Request(number:profiles, kind:kind, second:second, fps:fps ?? 0, targets:Array(threads.prefix(Self.maxThreads)))
        }
        lock.unlock()
        guard free else { return }
        if kind == "slow" { slowDone += 1 } else { baseDone += 1 }
        lastSecond = second; slowStreak = 0; baseStreak = 0
        wake.signal()
    }

    private func work() {
        while true {
            wake.wait()
            lock.lock()
            let alive = running, request = pending
            pending = nil; busy = request != nil
            lock.unlock()
            guard alive else { return }
            if let request {
                let lines = Self.profile(request)
                for (index, line) in lines.enumerated() {
                    let text = "[MeloNX:hot] " + line
                    _ = MeloNXStdioCapture.appendLine(index == 0 ? MeloNXStdioCapture.contextualLine(text, context:context) : text,
                                                      to:path, limit:MeloNXPerfJournal.fileLimit)
                }
            }
            lock.lock(); busy = false; lock.unlock()
        }
    }

    private struct Sample { let running: Bool; let addresses: [UInt64] }

    /// One profile, on the calling thread: the header line, then one line per thread asked for.
    static func profile(_ request: Request, rounds: Int = MeloNXHotSpots.rounds,
                        periodMicroseconds: UInt32 = MeloNXHotSpots.periodMicroseconds) -> [String] {
        var list: thread_act_array_t?
        var count: mach_msg_type_number_t = 0
        guard task_threads(mach_task_self_, &list, &count) == KERN_SUCCESS, let list else { return [] }
        defer {
            for index in 0..<Int(count) { mach_port_deallocate(mach_task_self_, list[index]) }
            vm_deallocate(mach_task_self_, vm_address_t(UInt(bitPattern:list)), vm_size_t(Int(count) * MemoryLayout<thread_act_t>.stride))
        }
        let wanted = Set(request.targets.map { $0.id })
        var ports: [UInt64: thread_act_t] = [:]
        for index in 0..<Int(count) {
            var identifier = thread_identifier_info_data_t()
            if MeloNXStallWatch.info(list[index], THREAD_IDENTIFIER_INFO, &identifier), wanted.contains(identifier.thread_id) {
                ports[identifier.thread_id] = list[index]
            }
        }
        // Every read first; the places are named afterwards, so no thread is read late because of a lookup.
        var samples = [[Sample]](repeating:[], count:request.targets.count)
        var missed = [Int](repeating:0, count:request.targets.count)
        let begin = mach_absolute_time()
        for _ in 0..<rounds {
            for (index, target) in request.targets.enumerated() {
                var basic = thread_basic_info_data_t()
                guard let port = ports[target.id], MeloNXStallWatch.info(port, THREAD_BASIC_INFO, &basic),
                      let registers = Self.registers(port) else { missed[index] += 1; continue }
                let frames = MeloNXStallWatch.frames(from:registers.fp, limit:maxFrames)
                samples[index].append(Sample(running:basic.run_state == TH_STATE_RUNNING,
                                             addresses:[registers.pc & MeloNXStallWatch.addressMask] + frames))
            }
            usleep(periodMicroseconds)
        }
        let took = Int(MeloNXStallWatch.milliseconds(mach_absolute_time() &- begin))
        var cache: [UInt64: String] = [:]
        func name(_ address: UInt64) -> String {
            let place = MeloNXStallWatch.place(address, &cache)
            return place.hasPrefix("jit:") ? "jit" : place.hasPrefix("anon:") ? "anon" : place
        }
        // Program counters of one 64-byte block are named after the first one read in it.
        var blocks: [UInt64: UInt64] = [:]
        func block(_ address: UInt64) -> String {
            let key = address / selfBlockBytes
            if let first = blocks[key] { return name(first) }
            blocks[key] = address
            return name(address)
        }
        func top(_ counts: [String: Int], _ limit: Int) -> String {
            let ordered = counts.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }.prefix(limit)
            return ordered.isEmpty ? "-" : ordered.map { "\($0.key):\($0.value)" }.joined(separator:",")
        }
        var lines = ["#\(request.number) \(request.kind) t=\(request.second) fps=\(String(format:"%.1f", request.fps)) " +
                     "\(rounds) samples in \(took) ms, \(request.targets.count) threads"]
        for (index, target) in request.targets.enumerated() {
            var own: [String: Int] = [:], stack: [String: Int] = [:], waiting: [String: Int] = [:]
            var run = 0, wait = 0
            for sample in samples[index] {
                let callers = Set(sample.addresses.dropFirst().map(name))
                if sample.running {
                    run += 1
                    own[block(sample.addresses[0]), default:0] += 1
                    for place in callers { stack[place, default:0] += 1 }
                } else {
                    wait += 1
                    for place in callers where !place.hasPrefix("libsystem_kernel.dylib+") && !place.hasPrefix("libsystem_pthread.dylib+") {
                        waiting[place, default:0] += 1
                    }
                }
            }
            lines.append("#\(request.number) \(target.name) p\(target.priority) run=\(run) wait=\(wait) missed=\(missed[index]) " +
                         "self=\(top(own, selfPlaces)) stack=\(top(stack, stackPlaces)) waiting=\(top(waiting, waitPlaces))")
        }
        return lines
    }

    #if arch(arm64)
    private static func registers(_ thread: thread_act_t) -> (pc: UInt64, fp: UInt64)? {
        var state = arm_thread_state64_t()
        var stateCount = mach_msg_type_number_t(MemoryLayout<arm_thread_state64_t>.size / MemoryLayout<natural_t>.size)
        let read = withUnsafeMutablePointer(to:&state) { pointer in
            pointer.withMemoryRebound(to:natural_t.self, capacity:Int(stateCount)) {
                thread_get_state(thread, thread_state_flavor_t(ARM_THREAD_STATE64), $0, &stateCount)
            }
        }
        return read == KERN_SUCCESS ? (state.__pc, state.__fp) : nil
    }
    #else
    private static func registers(_ thread: thread_act_t) -> (pc: UInt64, fp: UInt64)? { nil }
    #endif
}
