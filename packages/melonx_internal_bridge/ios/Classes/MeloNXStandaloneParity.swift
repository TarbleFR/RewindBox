import Foundation
import Darwin

// Host behaviour carried over from the standalone MeloNX app.

// Standalone MeloNX writes the process's stdout and stderr to its own log file
// (RyujinxController.redirectStdIOToFile). MoltenVK reports there, including
// "Resumed VkDevice after MTLCommandBuffer ... failed", which RewindBox's
// journal never saw. While a MeloNX session runs, stderr is teed into its classified log
// as "[MeloNX:stderr]" lines and still reaches the original stderr. Lines are
// written directly (no NSLog, no Flutter hop), bounded per session.
// While fd 2 is a pipe, NSLog copies its messages there too, and .NET's
// Console (Ryujinx's console log target: stubs, info) goes through NSLog on
// iOS. Those lines carry this process's NSLog banner and get a budget of
// their own, so they never crowd out MoltenVK's direct writes. An NSLog message
// already copied (a stub logged every frame) is counted, not copied again; the
// most repeated ones are listed at the end.
enum MeloNXStdioCapture {
    static let lineLimit = 2000
    static let nslogLineLimit = 500
    static let repeatLimit = 256
    private static let lock = NSLock()
    private static var journal: String?
    private static var savedStderr: Int32 = -1

    // This lock must remain distinct from capture's lock. end() flushes stderr
    // while holding capture's lock, and a full pipe must still be drained by
    // pump -> appendLine. appendLine NEVER acquires the capture lock.
    private static let routeLock = NSLock()
    private static let appendLock = NSLock()
    private static var diagnosticsDirectory: URL?
    private static var pendingContext: [String:String] = [:]
    private static var contexts: [Int64:[String:String]] = [:]

    static func configureDiagnostics(directory: URL) throws {
        try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
        routeLock.lock(); diagnosticsDirectory = directory; routeLock.unlock()
    }
    private static func diagnosticPath(_ name: String) -> String? {
        routeLock.lock(); defer { routeLock.unlock() }
        return diagnosticsDirectory?.appendingPathComponent(name).path
    }
    static var coreJournalPath: String? {
        if let path = diagnosticPath("MeloNX-core.log") { return path }
        lock.lock(); defer { lock.unlock() }; return journal
    }
    static func prepareSession(titleID: String?, info: [String:Any], identity: [String:Any]) {
        let core = identity["sourceCoreIdentity"] as? [String:Any] ?? [:]
        let context: [String:String] = ["session":UUID().uuidString,
            "pid":String(ProcessInfo.processInfo.processIdentifier),
            "titleId":titleID ?? "unavailable", "console":"Switch",
            "build":info["CFBundleVersion"] as? String ?? "unavailable",
            "version":info["CFBundleShortVersionString"] as? String ?? "unavailable",
            "coreSource":core["host"] as? String ?? "unavailable",
            "coreSHA256":core["sha256"] as? String ?? "unavailable"]
        routeLock.lock(); pendingContext = context; routeLock.unlock()
    }
    static var sessionContext: [String:String] {
        routeLock.lock(); defer { routeLock.unlock() }; return pendingContext
    }
    static func bindGeneration(_ generation: Int64, context: [String:String]) {
        var owned = context; owned["generation"] = String(generation)
        routeLock.lock(); defer { routeLock.unlock() }
        contexts[generation] = owned
        for old in contexts.keys.sorted().dropLast(8) { contexts.removeValue(forKey:old) }
    }
    static func context(generation: Int64) -> [String:String] {
        routeLock.lock(); defer { routeLock.unlock() }
        return contexts[generation] ?? ["generation":String(generation),
            "pid":String(ProcessInfo.processInfo.processIdentifier), "context":"unavailable"]
    }
    static func contextualLine(_ text: String, context: [String:String]) -> String {
        guard !context.isEmpty else { return text }
        var fields = context
        fields["timestamp"] = ISO8601DateFormatter().string(from:Date())
        guard let data = try? JSONSerialization.data(withJSONObject:fields,options:[.sortedKeys]),
              let value = String(data:data,encoding:.utf8) else { return text }
        return text + " context=" + value
    }

    static func configure(path: String) {
        guard path.hasPrefix("/"), URL(fileURLWithPath:path).lastPathComponent == "app.log" else { return }
        lock.lock(); journal = path; lock.unlock()
    }
    static var journalPath: String? {
        if let path = diagnosticPath("MeloNX-performance.log") { return path }
        lock.lock(); defer { lock.unlock() }; return journal
    }

    static func begin() {
        lock.lock(); defer { lock.unlock() }
        guard savedStderr < 0, let journal = diagnosticPath("MeloNX-stderr.log") ?? journal else { return }
        var fds: [Int32] = [-1, -1]
        guard pipe(&fds) == 0 else { return }
        let saved = dup(STDERR_FILENO)
        let mirror = saved >= 0 ? dup(saved) : -1
        guard saved >= 0, mirror >= 0, dup2(fds[1], STDERR_FILENO) >= 0 else {
            for fd in [fds[0], fds[1], saved, mirror] where fd >= 0 { close(fd) }
            return
        }
        close(fds[1])
        savedStderr = saved
        let source = fds[0]
        var context = sessionContext
        if diagnosticPath("MeloNX-stderr.log") != nil {
            context["capture"] = UUID().uuidString
            context["pid"] = String(ProcessInfo.processInfo.processIdentifier)
        } else { context = [:] }
        let capturedContext = context
        let thread = Thread { MeloNXStdioCapture.pump(source, mirror: mirror, journal: journal, context:capturedContext) }
        thread.name = "RewindBox.MeloNX.Stderr"
        // Above the writers' default, so little is left in the pipe if the
        // process ends abruptly.
        thread.qualityOfService = .userInitiated
        thread.start()
    }

    // Restoring fd 2 drops the pipe's last writer: the pump drains and stops.
    static func end() {
        lock.lock(); defer { lock.unlock() }
        guard savedStderr >= 0 else { return }
        fflush(stderr)
        dup2(savedStderr, STDERR_FILENO)
        close(savedStderr)
        savedStderr = -1
    }

    private static func pump(_ source: Int32, mirror: Int32, journal: String, context: [String:String]) {
        var pending = [UInt8](), buffer = [UInt8](repeating:0, count:4096)
        var lines = 0, nslogLines = 0, dropped = 0, repeated = 0
        var seen = [String:Int](), driverSeen = [String:Int]()
        var driverRepeated = 0
        func record(_ message: String) { append(message, to:journal, context:context) }
        record("capture begin")
        // NSLog may echo MeloNXLaunchJournal's own events to stderr; app.log
        // already has those as [MeloNX:native] lines.
        let echo = Array("[MeloNX:launch]".utf8)
        let banner = Array("\(ProcessInfo.processInfo.processName)[\(getpid()):".utf8)
        func emit(_ bytes: ArraySlice<UInt8>) {
            guard !bytes.isEmpty, !contains(bytes, echo) else { return }
            if let start = index(of:banner, in:bytes.prefix(96)) {
                // The message follows the banner's "[pid:tid] " and Ryujinx's own
                // clock ("00:00:00.715 "); both timestamps vary between repeats.
                let body = index(of:Array("] ".utf8), in:bytes[start...]).map { bytes[($0 + 2)...] } ?? bytes
                let message = String(decoding:dropClock(body).prefix(512), as:UTF8.self)
                if let count = seen[message] { seen[message] = count + 1; repeated += 1; return }
                if seen.count < repeatLimit { seen[message] = 0 }
                guard nslogLines < nslogLineLimit else { dropped += 1; return }
                nslogLines += 1
            } else {
                let message = String(decoding:bytes.prefix(2048),as:UTF8.self)
                if message.hasPrefix("[mvk-error]") || message.hasPrefix("[mvk-warn]") {
                    if let previous = driverSeen[message] {
                        let count = previous + 1
                        driverSeen[message] = count; driverRepeated += 1
                        if count & (count - 1) == 0 { record("driver repeated \(count) times: \(message)") }
                        return
                    }
                    if driverSeen.count < repeatLimit { driverSeen[message] = 1 }
                }
                guard lines < lineLimit else { dropped += 1; return }
                lines += 1
            }
            record(String(decoding:bytes.prefix(2048), as:UTF8.self))
        }
        while true {
            let count = read(source, &buffer, buffer.count)
            if count < 0 && errno == EINTR { continue }
            guard count > 0 else { break }
            _ = buffer.withUnsafeBytes { write(mirror, $0.baseAddress, count) }
            pending.append(contentsOf:buffer[0..<count])
            while let newline = pending.firstIndex(of:0x0a) {
                emit(pending[..<newline])
                pending.removeSubrange(...newline)
            }
            if pending.count > 2048 { emit(pending[...]); pending.removeAll() }
        }
        if !pending.isEmpty { emit(pending[...]) }
        let most = seen.filter { $0.value > 0 }.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }
        for (message, count) in most.prefix(10) { record("repeated \(count) more times: \(message)") }
        if driverRepeated > 0 { record("driver repeated total \(driverRepeated)") }
        record("capture end: \(lines) lines, \(nslogLines) NSLog lines, \(repeated) repeats, \(dropped) not copied")
        close(source); close(mirror)
    }

    // Drops a leading "hh:mm:ss.fff " (Ryujinx's DefaultLogFormatter clock).
    private static func dropClock(_ bytes: ArraySlice<UInt8>) -> ArraySlice<UInt8> {
        var index = bytes.startIndex, colons = 0
        while index < bytes.endIndex, index - bytes.startIndex < 20 {
            let byte = bytes[index]
            if byte == 0x20 { return colons == 2 ? bytes[(index + 1)...] : bytes }
            if byte == 0x3a { colons += 1 } else if byte != 0x2e && !(0x30...0x39).contains(byte) { return bytes }
            index += 1
        }
        return bytes
    }

    private static func contains(_ bytes: ArraySlice<UInt8>, _ needle: [UInt8]) -> Bool {
        index(of:needle, in:bytes) != nil
    }

    private static func index(of needle: [UInt8], in bytes: ArraySlice<UInt8>) -> Int? {
        guard bytes.count >= needle.count else { return nil }
        var start = bytes.startIndex
        while start + needle.count <= bytes.endIndex {
            if bytes[start..<start + needle.count].elementsEqual(needle) { return start }
            start += 1
        }
        return nil
    }

    private static func append(_ text: String, to path: String, context: [String:String] = [:]) {
        let safe = text
            .replacingOccurrences(of:"(?i)\\b[0-9a-f]{32,}\\b", with:"[redacted]", options:.regularExpression)
            .replacingOccurrences(of:"(?im)^\\s*[a-z0-9_]+\\s*=\\s*[^\\r\\n]+", with:"[redacted key entry]", options:.regularExpression)
        appendLine(contextualLine("[MeloNX:stderr] " + safe,context:context), to:path)
    }

    // O_APPEND per complete line. Canonical logs rotate to one previous file;
    // the compatibility app.log route retains its historical size cap.
    @discardableResult
    static func appendLine(_ text: String, to path: String, limit: Int64 = 5 * 1024 * 1024) -> Bool {
        let line = Array((text + "\n").utf8)
        guard Int64(line.count) <= limit else { return false }
        routeLock.lock()
        let categorized = diagnosticsDirectory.map { directory in
            URL(fileURLWithPath:path).deletingLastPathComponent().standardizedFileURL == directory.standardizedFileURL &&
            ["MeloNX-stderr.log", "MeloNX-performance.log"].contains(URL(fileURLWithPath:path).lastPathComponent)
        } ?? false
        routeLock.unlock()
        appendLock.lock(); defer { appendLock.unlock() }
        if categorized,
           let size = (try? FileManager.default.attributesOfItem(atPath:path)[.size]) as? NSNumber,
           size.int64Value + Int64(line.count) > limit {
            guard rename(path,path + ".previous") == 0 else { return false }
        }
        let fd = open(path, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, S_IRUSR | S_IWUSR)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, Int64(info.st_size) < limit else { return false }
        var offset = 0
        while offset < line.count {
            let count = line.withUnsafeBytes { write(fd, $0.baseAddress!.advanced(by:offset), line.count - offset) }
            if count < 0 && errno == EINTR { continue }
            guard count > 0 else { return false }
            offset += count
        }
        return true
    }
}

// Priority of the thread that runs the engine (MeloNXSessionHost's session
// queue, user-initiated). Standalone MeloNX starts emulation on a plain
// Thread at default QoS. 0 keeps RewindBox's, 1 lowers the thread to default
// QoS right before the engine runs, so threads it creates may follow; the
// performance journal shows each thread's priority. Applies at the next game.
enum MeloNXEmulationPriority {
    static let key = "RewindBoxMeloNXEmulationPriority"
    private static let lock = NSLock()
    private static var current: Int32?

    static var preferred: Int32 {
        get { UserDefaults.standard.string(forKey:key) == "standalone" ? 1 : 0 }
        set { UserDefaults.standard.set(newValue == 1 ? "standalone" : "rewindbox", forKey:key) }
    }
    /// The choice applied when the running game started; nil before any.
    static var applied: Int32? { lock.lock(); defer { lock.unlock() }; return current }

    /// On the thread that runs the engine: the pthread status (0 when
    /// nothing changes) and the QoS class now in effect.
    static func applyToCurrentThread() -> (status: Int32, qos: qos_class_t) {
        let choice = preferred
        let status = choice == 1 ? pthread_set_qos_class_self_np(QOS_CLASS_DEFAULT, 0) : 0
        lock.lock(); current = status == 0 ? choice : 0; lock.unlock()
        return (status, qos_class_self())
    }

    static func name(_ qos: qos_class_t) -> String {
        switch qos {
        case QOS_CLASS_USER_INTERACTIVE: return "user-interactive"
        case QOS_CLASS_USER_INITIATED: return "user-initiated"
        case QOS_CLASS_DEFAULT: return "default"
        case QOS_CLASS_UTILITY: return "utility"
        case QOS_CLASS_BACKGROUND: return "background"
        default: return "unspecified (\(qos))"
        }
    }
}

// Which MoltenVK the engine loads for this process: 1 is the standalone MeloNX
// app's own libMoltenVK.dylib (MeloNXMoltenVKStandalone.framework, the default
// for parity), 0 RewindBox's source-built Khronos v1.3.0. Applies at the next
// RewindBox start; the engine cannot switch once MoltenVK is loaded.
enum MeloNXMoltenVKChoice {
    static let key = "RewindBoxMeloNXMoltenVK"
    static let names: [Int32: String] = [0: "RewindBox 1.3.0", 1: "MeloNX 1.4.0 (standalone)"]

    static var preferred: Int32 {
        get {
            let stored = UserDefaults.standard.string(forKey:key)
            return stored == "rewindbox" ? 0 : 1
        }
        set { UserDefaults.standard.set(newValue == 0 ? "rewindbox" : "standalone", forKey:key) }
    }

    static func available(_ variant: Int32, frameworks: URL) -> Bool {
        let name = variant == 0 ? "MeloNXMoltenVK" : "MeloNXMoltenVKStandalone"
        return FileManager.default.fileExists(atPath:frameworks.appendingPathComponent("\(name).framework/\(name)").path)
    }
}
