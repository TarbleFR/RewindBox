import Foundation
import Darwin
#if os(iOS)
import AVFoundation
#endif

// "[MeloNX:freeze]" and "[MeloNX:live]" lines in MeloNX-performance.log, and the same journal sent to a computer on
// the local network while the game runs. Measurement only: nothing here changes emulation, and nothing here runs on
// the render thread except two ring writes (a presentation, a drawable request) under an uncontended lock.
//
// IPA 729 (Core 743): the per-second journal shows a 733 ms gap in the second a background collection starts, with
// 11 288 pages decompressed, but one line per second cannot tell which thread worked during the gap, nor whether the
// time went to the collector, to pages being decompressed or to waiting. This keeps, for the last 40 s:
//   - every presentation (host time, frame number) and every drawable request (host time, wait);
//   - every 50 ms, the process's decompression, fault and compression counters and, for the twelve busiest threads
//     (plus the collector and the engine's render and GPU threads by name), CPU time, kernel run state and where the
//     thread is (program counter and three return addresses, read without stopping it).
// A gap of 100 ms or more between two presentations, a manual mark (a volume button on the iPhone, or the computer's
// "mark" datagram) and, once a minute, a smooth stretch write one bounded record: the presentations and requests
// around it, per thread the CPU spent inside the gap and where, and the 50 ms samples. At most 40 records per kind
// and session (10 smooth ones), one automatic record per 3 s.
//
// Live copy: when the player entered the computer's address (game menu, "Live capture"), every line written to the
// performance journal, and the engine's events, are also queued (512 lines, 512 KiB; the oldest is dropped and
// counted) and sent by this file's own utility thread as numbered UDP datagrams to that private IPv4 address. The
// socket never blocks; a computer that is absent, asleep or refusing costs nothing but the dropped count. The files
// on the iPhone stay complete: they are the record, the datagrams are a copy. Datagram: "RBL1 <stream> <sequence>
// <part> <parts> <host time us>\n" then at most 1100 bytes of the line. A "[MeloNX:live]" line every 10 s gives what
// was sent and dropped and this thread's own CPU time, so the cost of the measurement is in the journal.
final class MeloNXLiveCapture {
    static let shared = MeloNXLiveCapture()
    static let defaultsKey = "RewindBoxMeloNXLiveCapture"
    static let threadName = "RewindBox.MeloNX.Live"
    static let queueLineLimit = 512
    static let queueByteLimit = 512 * 1024
    static let payloadLimit = 1100
    static let frameCapacity = 1024
    static let sampleCapacity = 800
    static let keyThreadLimit = 12
    static let tickSeconds = 0.05
    static let refreshSeconds = 2.0
    static let statsSeconds = 10.0
    static let smoothSeconds = 60.0
    // The two periods a host check shortens; production keeps the values above.
    var statsInterval = MeloNXLiveCapture.statsSeconds
    var smoothInterval = MeloNXLiveCapture.smoothSeconds
    static let gapTriggerMs = 100.0
    static let captureLimit = 40
    static let smoothLimit = 10
    static let automaticSpacingSeconds = 3.0
    static let returnAddresses = 3
    // Sampled whatever their CPU share (names as the journal writes them: blanks, ':' and '/' become '_').
    static let alwaysSampled = [".NET_BGC", "GPU.MainThread", "NeoStation.MeloNX.Render", "AudioManager.Worker"]

    struct Ring<T> {
        private var items: [T] = []
        private var next = 0
        let capacity: Int
        init(capacity: Int) { self.capacity = max(1, capacity); items.reserveCapacity(self.capacity) }
        mutating func append(_ item: T) {
            if items.count < capacity { items.append(item) } else { items[next] = item }
            next = (next + 1) % capacity
        }
        // Oldest first.
        func ordered() -> [T] { items.count < capacity ? items : Array(items[next...]) + Array(items[..<next]) }
        mutating func removeAll() { items.removeAll(keepingCapacity:true); next = 0 }
    }
    struct Frame { var time: Double; var index: UInt64 }
    struct Acquire { var time: Double; var waitMs: Double }
    struct ThreadPoint { var id: UInt64; var cpuNs: UInt64; var systemNs: UInt64; var state: Int32; var stack: [UInt64] }
    struct Sample { var time: Double; var decompressions: Int64; var faults: Int64; var compressedBytes: UInt64; var threads: [ThreadPoint] }
    struct Trigger { var kind: String; var time: Double; var gapMs: Double; var frame: UInt64; var note: String }
    private struct KeyThread { let port: thread_act_t; let id: UInt64 }

    // Host time, seconds: the clock of CAMetalDrawable.presentedTime and CACurrentMediaTime.
    static func now() -> Double { ProcessInfo.processInfo.systemUptime }

    /// "a.b.c.d:port" of a private IPv4 address (10/8, 172.16/12, 192.168/16, link-local, loopback), else nil: the
    /// journal is never sent outside the local network.
    static func parse(_ text: String) -> (host: String, port: UInt16)? {
        let parts = text.trimmingCharacters(in:.whitespacesAndNewlines).split(separator:":", omittingEmptySubsequences:false)
        guard parts.count == 1 || parts.count == 2 else { return nil }
        let port = parts.count == 2 ? UInt16(parts[1]) : 47800
        let numbers = parts[0].split(separator:".", omittingEmptySubsequences:false).map { UInt8($0) }
        guard let port, port >= 1024, numbers.count == 4, !numbers.contains(where:{ $0 == nil }) else { return nil }
        let a = numbers[0]!, b = numbers[1]!
        guard a == 10 || a == 127 || (a == 172 && (16...31).contains(b)) || (a == 192 && b == 168) || (a == 169 && b == 254) else { return nil }
        return (numbers.map { String($0!) }.joined(separator:"."), port)
    }
    static var preferred: String {
        get { UserDefaults.standard.string(forKey:defaultsKey) ?? "" }
        set { UserDefaults.standard.set(parse(newValue) == nil ? "" : newValue.trimmingCharacters(in:.whitespacesAndNewlines), forKey:defaultsKey) }
    }

    // Presentations, requests and pending triggers: written by the display's and the engine's threads.
    private let frameLock = NSLock()
    private var frames = Ring<Frame>(capacity:frameCapacity)
    private var acquires = Ring<Acquire>(capacity:frameCapacity)
    private var lastFrameTime = 0.0, lastFrameIndex: UInt64 = 0
    private var pending: [Trigger] = []
    private var active = false, paused = false
    private var lastMarkTime = 0.0

    // The queue to the computer and the run's identity: any thread.
    private let stateLock = NSLock()
    private var queue: [[UInt8]] = []
    private var queueBytes = 0
    private var droppedLines: UInt64 = 0
    private var epoch = 0
    private var networking = false
    private var owner: ObjectIdentifier?
    private var lastStart: (path: String, context: [String:String])?
    private let wake = DispatchSemaphore(value:0)
    // One capture thread at a time: a start waits (at most 1 s) for the previous run's thread to leave.
    private let idle = NSCondition()
    private var busy = false

    // Owned by the capture thread.
    private var path = ""
    private var context: [String:String] = [:]
    private var socketFd: Int32 = -1
    private var stream = ""
    private var sequence: UInt64 = 0
    private var sentLines: UInt64 = 0, sentDatagrams: UInt64 = 0, sentBytes: UInt64 = 0, sendErrors: UInt64 = 0
    private var samples = Ring<Sample>(capacity:sampleCapacity)
    private var keys: [KeyThread] = []
    private var names: [UInt64:String] = [:]
    private var previousCpu: [UInt64:UInt64] = [:]
    private var scheduled: [Trigger] = []
    private var counts: [String:Int] = [:]
    private var records = 0
    private var lastAutomatic = 0.0, lastTrigger = 0.0
    #if os(iOS)
    private var volumeObservation: NSKeyValueObservation?
    #endif

    /// Starts the rings and the capture thread for one game session. `target`: "a.b.c.d:port" or empty (no live copy).
    func start(path: String, context: [String:String], target: String = MeloNXLiveCapture.preferred, owner: ObjectIdentifier? = nil) {
        stateLock.lock()
        epoch += 1
        let mine = epoch
        queue.removeAll(); queueBytes = 0; droppedLines = 0
        networking = false
        self.owner = owner
        lastStart = (path, context)
        stateLock.unlock()
        wake.signal()
        idle.lock()
        let deadline = Date().addingTimeInterval(1)
        while busy, idle.wait(until:deadline) {}
        let free = !busy
        if free { busy = true }
        idle.unlock()
        guard free else { return }
        MeloNXStdioCapture.setLiveTee({ [weak self] line in self?.forward(line) }, wanted:{ [weak self] in self?.isForwarding ?? false })
        frameLock.lock()
        frames.removeAll(); acquires.removeAll(); pending.removeAll()
        lastFrameTime = 0; lastFrameIndex = 0; paused = false; active = true
        frameLock.unlock()
        let thread = Thread { [self] in run(epoch:mine, path:path, context:context, target:Self.parse(target)) }
        thread.name = Self.threadName
        thread.qualityOfService = .utility
        thread.start()
        #if os(iOS)
        // A volume button is the manual mark: reachable with a controller in hand, and it needs no control on screen.
        volumeObservation = AVAudioSession.sharedInstance().observe(\.outputVolume, options:[.new]) { [weak self] _, _ in
            self?.mark(kind:"volume")
        }
        #endif
    }

    /// Stops the run. With an owner, only that owner's run (a closed session's controller must not stop the next one's).
    func stop(owner: ObjectIdentifier? = nil) {
        stateLock.lock()
        guard owner == nil || owner == self.owner else { stateLock.unlock(); return }
        epoch += 1
        self.owner = nil
        stateLock.unlock()
        #if os(iOS)
        volumeObservation?.invalidate(); volumeObservation = nil
        #endif
        frameLock.lock(); active = false; frameLock.unlock()
        wake.signal()
    }

    /// The same session with the address the player just entered.
    func restart() {
        stateLock.lock(); let last = lastStart; let owner = self.owner; stateLock.unlock()
        guard let last else { return }
        stop()
        start(path:last.path, context:last.context, owner:owner)
    }

    /// Whether lines are being queued for a computer (the engine's events are only serialized when they are).
    var isForwarding: Bool { stateLock.lock(); defer { stateLock.unlock() }; return networking }

    // A pause is not a held frame: the next presentation starts a new gap.
    func setPaused(_ value: Bool) {
        frameLock.lock(); paused = value; lastFrameTime = 0; frameLock.unlock()
    }

    func notePresented(time: Double, frame: UInt64) {
        frameLock.lock(); defer { frameLock.unlock() }
        guard active else { return }
        frames.append(Frame(time:time, index:frame))
        if lastFrameTime > 0, !paused {
            let gap = (time - lastFrameTime) * 1000
            if gap >= Self.gapTriggerMs, pending.count < 8 {
                pending.append(Trigger(kind:"gap", time:time, gapMs:gap, frame:frame, note:""))
            }
        }
        lastFrameTime = max(lastFrameTime, time); lastFrameIndex = frame
    }

    func noteAcquire(time: Double, waitMs: Double) {
        frameLock.lock(); defer { frameLock.unlock() }
        guard active else { return }
        acquires.append(Acquire(time:time, waitMs:waitMs))
    }

    /// A manual mark ("volume" from the iPhone, "pc" from the computer): one record around now. Marks of one kind
    /// within 1.5 s count once (a volume press up then down marks once and restores the volume).
    func mark(kind: String, note: String = "") {
        let time = Self.now()
        frameLock.lock(); defer { frameLock.unlock() }
        guard active, time - lastMarkTime >= 1.5, pending.count < 8 else { return }
        lastMarkTime = time
        pending.append(Trigger(kind:kind, time:time, gapMs:0, frame:lastFrameIndex, note:String(note.prefix(64))))
    }

    /// A journal line for the computer. Never blocks and never fails the caller: a full queue drops its oldest line.
    func forward(_ line: String) {
        stateLock.lock()
        guard networking else { stateLock.unlock(); return }
        let bytes = Array(line.utf8)
        queue.append(bytes); queueBytes += bytes.count
        while queue.count > Self.queueLineLimit || queueBytes > Self.queueByteLimit, !queue.isEmpty {
            queueBytes -= queue.removeFirst().count; droppedLines += 1
        }
        stateLock.unlock()
        wake.signal()
    }

    private func current(_ mine: Int) -> Bool { stateLock.lock(); defer { stateLock.unlock() }; return epoch == mine }

    private func run(epoch mine: Int, path: String, context: [String:String], target: (host: String, port: UInt16)?) {
        self.path = path; self.context = context
        samples.removeAll(); names = [:]; previousCpu = [:]; scheduled = []; counts = [:]; records = 0
        sequence = 0; sentLines = 0; sentDatagrams = 0; sentBytes = 0; sendErrors = 0
        stream = String(format:"%08x", UInt32.random(in:0...UInt32.max))
        var copy = "off"
        if let target {
            let connected = connectSocket(host:target.host, port:target.port)
            copy = (connected ? "to " : "refused for ") + target.host + ":" + String(target.port)
            if connected { stateLock.lock(); if epoch == mine { networking = true }; stateLock.unlock() }
        }
        let started = Self.now()
        var nextSample = started, nextRefresh = started, nextStats = started + statsInterval, nextSmooth = started + smoothInterval
        var ownCpu = Self.ownCpuNs()
        write("[MeloNX:live] begin: stream \(stream), live copy \(copy); " +
              "samples every \(Int(Self.tickSeconds * 1000)) ms, record on a gap of \(Int(Self.gapTriggerMs)) ms or a mark", withContext:true)
        while current(mine) {
            _ = wake.wait(timeout:.now() + Self.tickSeconds)
            drain()
            receive()
            let time = Self.now()
            if time >= nextRefresh { refresh(); nextRefresh = time + Self.refreshSeconds }
            if time >= nextSample { sample(time:time); nextSample = max(nextSample + Self.tickSeconds, time) }
            frameLock.lock(); let fresh = pending; pending.removeAll(keepingCapacity:true); frameLock.unlock()
            for trigger in fresh {
                lastTrigger = max(lastTrigger, trigger.time)
                if trigger.kind == "gap" {
                    guard trigger.time - lastAutomatic >= Self.automaticSpacingSeconds else { counts["gapSkipped", default:0] += 1; continue }
                    lastAutomatic = trigger.time
                }
                guard counts[trigger.kind, default:0] < Self.captureLimit else { counts[trigger.kind + "Skipped", default:0] += 1; continue }
                counts[trigger.kind, default:0] += 1
                scheduled.append(trigger)
            }
            if time >= nextSmooth {
                nextSmooth = time + smoothInterval
                frameLock.lock(); let flowing = !paused && time - lastFrameTime < 0.2; let frame = lastFrameIndex; frameLock.unlock()
                if flowing, time - lastTrigger >= 10, counts["smooth", default:0] < Self.smoothLimit {
                    counts["smooth", default:0] += 1
                    scheduled.append(Trigger(kind:"smooth", time:time, gapMs:0, frame:frame, note:""))
                }
            }
            // A record is written one second after its trigger, so it holds what followed.
            while let first = scheduled.first, time >= first.time + 1.0 {
                scheduled.removeFirst()
                record(first)
            }
            if time >= nextStats {
                nextStats = time + statsInterval
                let cpu = Self.ownCpuNs()
                stateLock.lock(); let dropped = droppedLines; let waiting = queue.count; stateLock.unlock()
                write("[MeloNX:live] t=\(Int(time - started)) lines=\(sentLines)/\(dropped) datagrams=\(sentDatagrams) bytes=\(sentBytes) errors=\(sendErrors) " +
                      "queued=\(waiting) samples=\(samples.ordered().count) threads=\(keys.count) records=\(records) " +
                      "gap=\(counts["gap", default:0])+\(counts["gapSkipped", default:0]) marks=\(counts["volume", default:0] + counts["pc", default:0]) " +
                      "smooth=\(counts["smooth", default:0]) ownCpuMs=\(String(format:"%.1f", Double(cpu &- ownCpu) / 1e6))", withContext:false)
                ownCpu = cpu
            }
        }
        drain()
        stateLock.lock(); networking = false; queue.removeAll(); queueBytes = 0; stateLock.unlock()
        release()
        if socketFd >= 0 { close(socketFd); socketFd = -1 }
        idle.lock(); busy = false; idle.broadcast(); idle.unlock()
    }

    // MARK: journal and datagrams

    private func write(_ text: String, withContext: Bool) {
        guard !path.isEmpty else { return }
        _ = MeloNXStdioCapture.appendLine(withContext ? MeloNXStdioCapture.contextualLine(text, context:context) : text, to:path, limit:MeloNXPerfJournal.fileLimit)
    }

    private func connectSocket(host: String, port: UInt16) -> Bool {
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = port.bigEndian
        guard inet_pton(AF_INET, host, &address.sin_addr) == 1 else { return false }
        let fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        guard fd >= 0 else { return false }
        _ = fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK)
        var one: Int32 = 1
        _ = setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, socklen_t(MemoryLayout<Int32>.size))
        let connected = withUnsafePointer(to:&address) {
            $0.withMemoryRebound(to:sockaddr.self, capacity:1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        guard connected == 0 else { close(fd); return false }
        socketFd = fd
        return true
    }

    private func drain() {
        guard socketFd >= 0 else { return }
        stateLock.lock(); let lines = queue; queue.removeAll(keepingCapacity:true); queueBytes = 0; stateLock.unlock()
        for line in lines {
            sequence += 1
            let parts = max(1, (line.count + Self.payloadLimit - 1) / Self.payloadLimit)
            let stamp = UInt64(Self.now() * 1e6)
            var whole = true
            for part in 0..<parts {
                var datagram = Array("RBL1 \(stream) \(sequence) \(part + 1) \(parts) \(stamp)\n".utf8)
                datagram.append(contentsOf:line[(part * Self.payloadLimit)..<min(line.count, (part + 1) * Self.payloadLimit)])
                let sent = datagram.withUnsafeBytes { send(socketFd, $0.baseAddress, $0.count, 0) }
                if sent == datagram.count { sentDatagrams += 1; sentBytes += UInt64(sent) } else { sendErrors += 1; whole = false }
            }
            if whole { sentLines += 1 }
        }
    }

    // The computer's datagrams: "RBL1 MARK <note>" asks for a record around now.
    private func receive() {
        guard socketFd >= 0 else { return }
        var buffer = [UInt8](repeating:0, count:256)
        while true {
            let count = buffer.withUnsafeMutableBytes { recv(socketFd, $0.baseAddress, $0.count, 0) }
            guard count > 0 else { return }
            let text = String(decoding:buffer[0..<count], as:UTF8.self)
            guard text.hasPrefix("RBL1 MARK") else { continue }
            let note = text.dropFirst("RBL1 MARK".count).filter { $0.isLetter || $0.isNumber || $0 == " " || $0 == "-" || $0 == "_" }
            mark(kind:"pc", note:note.trimmingCharacters(in:.whitespaces))
        }
    }

    // MARK: threads

    private static func ownCpuNs() -> UInt64 {
        let thread = mach_thread_self()
        defer { mach_port_deallocate(mach_task_self_, thread) }
        var extended = thread_extended_info_data_t()
        guard MeloNXStallWatch.info(thread, THREAD_EXTENDED_INFO, &extended) else { return 0 }
        return extended.pth_user_time &+ extended.pth_system_time
    }

    private func release() {
        for key in keys { mach_port_deallocate(mach_task_self_, key.port) }
        keys = []
    }

    // The threads sampled until the next refresh: the named ones and the busiest since the previous refresh. Their
    // ports are kept; every other port is released at once.
    private func refresh() {
        var list: thread_act_array_t?
        var count: mach_msg_type_number_t = 0
        guard task_threads(mach_task_self_, &list, &count) == KERN_SUCCESS, let list else { return }
        defer { vm_deallocate(mach_task_self_, vm_address_t(UInt(bitPattern:list)), vm_size_t(Int(count) * MemoryLayout<thread_act_t>.stride)) }
        let me = mach_thread_self()
        defer { mach_port_deallocate(mach_task_self_, me) }
        var seen: [(index: Int, id: UInt64, name: String, spent: UInt64, cpu: UInt64)] = []
        for index in 0..<Int(count) where list[index] != me {
            var identifier = thread_identifier_info_data_t()
            var extended = thread_extended_info_data_t()
            guard MeloNXStallWatch.info(list[index], THREAD_IDENTIFIER_INFO, &identifier),
                  MeloNXStallWatch.info(list[index], THREAD_EXTENDED_INFO, &extended) else { continue }
            var bytes = extended.pth_name
            var name = withUnsafeBytes(of:&bytes) { raw in String(decoding:raw.prefix(while:{ $0 != 0 }), as:UTF8.self) }
            name = String(name.map { $0.isWhitespace || $0 == ":" || $0 == "/" ? "_" : $0 }.prefix(24))
            if name.isEmpty { name = "thread\(identifier.thread_id)" }
            let cpu = extended.pth_user_time &+ extended.pth_system_time
            seen.append((index, identifier.thread_id, name, previousCpu[identifier.thread_id].map { cpu &- $0 } ?? 0, cpu))
        }
        var chosen = Set<Int>()
        for entry in seen where Self.alwaysSampled.contains(entry.name) && chosen.count < Self.keyThreadLimit { chosen.insert(entry.index) }
        for entry in seen.sorted(by:{ $0.spent > $1.spent }) where chosen.count < Self.keyThreadLimit && entry.spent > 0 { chosen.insert(entry.index) }
        release()
        previousCpu = [:]
        var known: [UInt64:String] = [:]
        for entry in seen {
            previousCpu[entry.id] = entry.cpu
            if chosen.contains(entry.index) { keys.append(KeyThread(port:list[entry.index], id:entry.id)); known[entry.id] = entry.name }
        }
        for index in 0..<Int(count) where !chosen.contains(index) { mach_port_deallocate(mach_task_self_, list[index]) }
        // Names of threads sampled within the ring's 40 s stay known.
        if names.count > 256 { names = known } else { names.merge(known) { _, new in new } }
    }

    private func sample(time: Double) {
        var points: [ThreadPoint] = []
        points.reserveCapacity(keys.count)
        for key in keys {
            var extended = thread_extended_info_data_t()
            guard MeloNXStallWatch.info(key.port, THREAD_EXTENDED_INFO, &extended) else { continue }
            var stack: [UInt64] = []
            #if arch(arm64)
            // Where a thread that is on a core is, read without stopping it: a waiting thread's place does not change.
            if extended.pth_run_state == TH_STATE_RUNNING {
                var state = arm_thread_state64_t()
                var stateCount = mach_msg_type_number_t(MemoryLayout<arm_thread_state64_t>.size / MemoryLayout<natural_t>.size)
                let read = withUnsafeMutablePointer(to:&state) { pointer in
                    pointer.withMemoryRebound(to:natural_t.self, capacity:Int(stateCount)) {
                        thread_get_state(key.port, thread_state_flavor_t(ARM_THREAD_STATE64), $0, &stateCount)
                    }
                }
                if read == KERN_SUCCESS {
                    stack = [state.__pc, state.__lr] + MeloNXStallWatch.frames(from:state.__fp, limit:Self.returnAddresses - 1)
                }
            }
            #endif
            points.append(ThreadPoint(id:key.id, cpuNs:extended.pth_user_time &+ extended.pth_system_time,
                                      systemNs:extended.pth_system_time, state:extended.pth_run_state, stack:stack))
        }
        let vm = MeloNXPerfJournal.vmCounters()
        samples.append(Sample(time:time, decompressions:vm?.decompressions ?? -1, faults:vm?.faults ?? -1,
                              compressedBytes:vm?.compressedBytes ?? 0, threads:points))
    }

    // MARK: records

    private static func stateLetter(_ value: Int32) -> String {
        switch value {
        case TH_STATE_RUNNING: return "R"
        case TH_STATE_STOPPED: return "T"
        case TH_STATE_WAITING: return "W"
        case TH_STATE_UNINTERRUPTIBLE: return "U"
        case TH_STATE_HALTED: return "H"
        default: return "?"
        }
    }
    private static func delta(_ now: Int64, _ before: Int64) -> String { now >= 0 && before >= 0 && now >= before ? String(now - before) : "-" }
    private static func ms(_ value: Double) -> String { String(format:"%.1f", value) }

    /// One record: the presentations and requests around the trigger, what each sampled thread did inside the gap
    /// (or the second before a mark), and the samples. Offsets are milliseconds from the trigger's host time.
    private func record(_ trigger: Trigger) {
        records += 1
        let tag = "[MeloNX:freeze] #\(records) "
        let start = trigger.kind == "gap" ? trigger.time - trigger.gapMs / 1000 : trigger.time - 1.0
        let from = start - 1.0, to = trigger.time + 1.0
        frameLock.lock(); let frameList = frames.ordered(); let acquireList = acquires.ordered(); let wasPaused = paused; frameLock.unlock()
        let window = samples.ordered().filter { $0.time >= from - Self.tickSeconds && $0.time <= to + Self.tickSeconds }
        var lines: [String] = []
        lines.append(MeloNXStdioCapture.contextualLine(tag + "kind=\(trigger.kind) gapMs=\(Self.ms(trigger.gapMs)) atUs=\(UInt64(trigger.time * 1e6)) frame=\(trigger.frame) " +
            "window=\(Int((from - trigger.time) * 1000))..\(Int((to - trigger.time) * 1000)) paused=\(wasPaused ? 1 : 0) samples=\(window.count)" +
            (trigger.note.isEmpty ? "" : " note=\(trigger.note.replacingOccurrences(of:" ", with:"_"))"), context:context))
        let shown = frameList.filter { $0.time >= from && $0.time <= to }
        lines.append(tag + "frames first=\(shown.first?.index ?? 0) offsetsMs=" + shown.map { String(Int(((($0.time - trigger.time) * 1000)).rounded())) }.joined(separator:","))
        let asked = acquireList.filter { $0.time >= from && $0.time <= to }
        lines.append(tag + "requests offsetsMs=" + asked.map { request in
            String(Int(((request.time - trigger.time) * 1000).rounded())) + (request.waitMs >= 1 ? "w" + String(Int(request.waitMs.rounded())) : "")
        }.joined(separator:","))
        // Inside the gap: the samples that bracket it.
        let inside = window.filter { $0.time >= start - Self.tickSeconds && $0.time <= trigger.time + Self.tickSeconds }
        var places: [UInt64:String] = [:]
        if let first = inside.first, let last = inside.last, last.time > first.time {
            var spent: [(name: String, cpu: Double, system: Double, running: Int, seen: Int, stacks: [String:Int])] = []
            for point in last.threads {
                guard let before = first.threads.first(where:{ $0.id == point.id }) else { continue }
                var running = 0, seen = 0
                var stacks: [String:Int] = [:]
                for sample in inside {
                    guard let at = sample.threads.first(where:{ $0.id == point.id }) else { continue }
                    seen += 1
                    if at.state == TH_STATE_RUNNING { running += 1 }
                    if !at.stack.isEmpty {
                        stacks[at.stack.map { MeloNXStallWatch.place($0, &places) }.joined(separator:"<"), default:0] += 1
                    }
                }
                spent.append((names[point.id] ?? "thread\(point.id)", Double(point.cpuNs &- before.cpuNs) / 1e6,
                              Double(point.systemNs &- before.systemNs) / 1e6, running, seen, stacks))
            }
            spent.sort { $0.cpu > $1.cpu }
            lines.append(tag + "inside spanMs=\(Self.ms((last.time - first.time) * 1000)) decompressions=\(Self.delta(last.decompressions, first.decompressions)) " +
                "faults=\(Self.delta(last.faults, first.faults)) compressedKiB=\(last.compressedBytes >= first.compressedBytes ? String((last.compressedBytes - first.compressedBytes) >> 10) : "-") " +
                "cpuMs(name:total/kernel/onCore) " + spent.map { "\($0.name):\(Self.ms($0.cpu))/\(Self.ms($0.system))/\($0.running)of\($0.seen)" }.joined(separator:" "))
            for entry in spent.prefix(4) where !entry.stacks.isEmpty {
                let top = entry.stacks.sorted { $0.value > $1.value }.prefix(5).map { "\($0.value)x " + $0.key }
                lines.append(tag + "where \(entry.name): " + top.joined(separator:"; "))
            }
        }
        var previous: Sample?
        for sample in window {
            defer { previous = sample }
            guard let before = previous else { continue }
            let busy = sample.threads.compactMap { point -> String? in
                guard let earlier = before.threads.first(where:{ $0.id == point.id }) else { return nil }
                let cpu = Double(point.cpuNs &- earlier.cpuNs) / 1e6
                guard cpu >= 1 || point.state == TH_STATE_RUNNING else { return nil }
                return "\(names[point.id] ?? "thread\(point.id)"):\(Self.ms(cpu))\(Self.stateLetter(point.state))"
            }
            lines.append(tag + "s=\(Int(((sample.time - trigger.time) * 1000).rounded())) d=\(Self.delta(sample.decompressions, before.decompressions)) " +
                "f=\(Self.delta(sample.faults, before.faults)) c=\(sample.compressedBytes >= before.compressedBytes ? String((sample.compressedBytes - before.compressedBytes) >> 10) : "-") " +
                busy.joined(separator:" "))
        }
        guard !path.isEmpty else { return }
        for line in lines { _ = MeloNXStdioCapture.appendLine(line, to:path, limit:MeloNXPerfJournal.fileLimit) }
    }
}
