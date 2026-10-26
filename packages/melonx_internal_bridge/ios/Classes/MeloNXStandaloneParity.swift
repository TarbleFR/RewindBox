import Foundation
import Darwin

// Host behaviour carried over from the standalone MeloNX app.

// Standalone MeloNX writes the process's stdout and stderr to its own log file
// (RyujinxController.redirectStdIOToFile). MoltenVK reports there, including
// "Resumed VkDevice after MTLCommandBuffer ... failed", which RewindBox's
// journal never saw. While a MeloNX session runs, stderr is teed into app.log
// as "[MeloNX:stderr]" lines and still reaches the original stderr. Lines are
// written directly (no NSLog, no Flutter hop), bounded per session.
// While fd 2 is a pipe, NSLog copies its messages there too, and .NET's
// Console (Ryujinx's console log target: stubs, info) goes through NSLog on
// iOS. Those lines carry this process's NSLog banner and get a budget of
// their own, so they never crowd out MoltenVK's direct writes.
enum MeloNXStdioCapture {
    static let lineLimit = 2000
    static let nslogLineLimit = 500
    private static let lock = NSLock()
    private static var journal: String?
    private static var savedStderr: Int32 = -1

    static func configure(path: String) {
        guard path.hasPrefix("/"), URL(fileURLWithPath:path).lastPathComponent == "app.log" else { return }
        lock.lock(); journal = path; lock.unlock()
    }

    static func begin() {
        lock.lock(); defer { lock.unlock() }
        guard savedStderr < 0, let journal else { return }
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
        let thread = Thread { MeloNXStdioCapture.pump(source, mirror: mirror, journal: journal) }
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

    private static func pump(_ source: Int32, mirror: Int32, journal: String) {
        var pending = [UInt8](), buffer = [UInt8](repeating:0, count:4096)
        var lines = 0, nslogLines = 0, dropped = 0
        append("capture begin", to:journal)
        // NSLog may echo MeloNXLaunchJournal's own events to stderr; app.log
        // already has those as [MeloNX:native] lines.
        let echo = Array("[MeloNX:launch]".utf8)
        let banner = Array("\(ProcessInfo.processInfo.processName)[\(getpid()):".utf8)
        func emit(_ bytes: ArraySlice<UInt8>) {
            guard !bytes.isEmpty, !contains(bytes, echo) else { return }
            if contains(bytes.prefix(96), banner) {
                guard nslogLines < nslogLineLimit else { dropped += 1; return }
                nslogLines += 1
            } else {
                guard lines < lineLimit else { dropped += 1; return }
                lines += 1
            }
            append(String(decoding:bytes.prefix(2048), as:UTF8.self), to:journal)
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
        append("capture end: \(lines) lines, \(nslogLines) NSLog lines, \(dropped) not copied", to:journal)
        close(source); close(mirror)
    }

    private static func contains(_ bytes: ArraySlice<UInt8>, _ needle: [UInt8]) -> Bool {
        guard bytes.count >= needle.count else { return false }
        var start = bytes.startIndex
        while start + needle.count <= bytes.endIndex {
            if bytes[start..<start + needle.count].elementsEqual(needle) { return true }
            start += 1
        }
        return false
    }

    // Same discipline as MeloNXLaunchJournal: O_APPEND per line, shared with
    // Dart's logger, skipped once app.log reaches 5 MiB.
    private static func append(_ text: String, to path: String) {
        let safe = text
            .replacingOccurrences(of:"(?i)\\b[0-9a-f]{32,}\\b", with:"[redacted]", options:.regularExpression)
            .replacingOccurrences(of:"(?im)^\\s*[a-z0-9_]+\\s*=\\s*[^\\r\\n]+", with:"[redacted key entry]", options:.regularExpression)
        let line = Array(("[MeloNX:stderr] " + safe + "\n").utf8)
        let fd = open(path, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, S_IRUSR | S_IWUSR)
        guard fd >= 0 else { return }
        defer { close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, info.st_size < 5 * 1024 * 1024 else { return }
        var offset = 0
        while offset < line.count {
            let count = line.withUnsafeBytes { write(fd, $0.baseAddress!.advanced(by:offset), line.count - offset) }
            if count < 0 && errno == EINTR { continue }
            guard count > 0 else { return }
            offset += count
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
