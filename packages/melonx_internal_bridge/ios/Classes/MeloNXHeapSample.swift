import Foundation
import Darwin

// "[MeloNX:heap]" lines in MeloNX-performance.log: who allocated the native heap. IPA 725 (Hogwarts Legacy, t=150 s):
// the default malloc zone holds 907 MiB of a 4 640 MiB footprint, most of it compressed, and no journal says whose
// it is; the footprint is already 2.7 to 2.9 GiB at the first frame.
//
// From the start of a session (before the engine) and for 120 s, or until the session ends if sooner, the sampler of
// MeloNXHeapSampler.m is libmalloc's logging hook: it records one block in every 256 KiB allocated on average (a
// block of 256 KiB or more always) with the return addresses of its call, and forgets it when it is freed. At the end
// of the window the hook is removed and the call stacks are written by the bytes still allocated:
//   window ...: live <MiB> in <samples>, allocated <MiB> in <samples> (estimates: a sample of a small block stands for
//               256 KiB), the stacks recorded, the samples dropped (a full table) or not walked (a thread on a stack
//               that is not its own), and the malloc zones' own counts at that moment (zones=name:MiB in use/MiB held)
//   #n live=<MiB>/<samples> total=<MiB>/<samples> stack=place<place<...   the 24 stacks with the most live bytes,
//               innermost caller first, up to ten places; the sampler's and libmalloc's own frames are left out
// A place is image+0xoffset (the library file's name), "jit" for translated guest code or "anon". Offsets inside the
// engine read with the Core artifact's symbol map (tools/melonx/heap_report.py).
// While the hook is set every malloc and free of the process pays a few tens of nanoseconds: the frame times of the
// window are not those of an unobserved session. One window at a time; at most 25 lines. Measurement only.
enum MeloNXHeapSamplerLink {
    private typealias Switch = @convention(c) () -> Int32
    private typealias Report = @convention(c) (UnsafeMutablePointer<UInt64>?, UnsafeMutablePointer<UInt64>?, Int32) -> Int32
    private static func symbol(_ name: String) -> UnsafeMutableRawPointer? { dlsym(UnsafeMutableRawPointer(bitPattern:-2), name) }
    private static let startFunction = symbol("MeloNXHeapSamplerStart").map { unsafeBitCast($0, to:Switch.self) }
    private static let stopFunction = symbol("MeloNXHeapSamplerStop").map { unsafeBitCast($0, to:Switch.self) }
    private static let reportFunction = symbol("MeloNXHeapSamplerReport").map { unsafeBitCast($0, to:Report.self) }

    // The C structures as 64-bit words (MeloNXHeapSampler.h): totals are 8 words; a stack is 4 counts, one word whose
    // low half is the frame count, then 14 frames.
    static let totalsWords = 8, stackWords = 19, frames = 14

    /// 1 set, 0 already set, -1 another logger owns the hook, -2 a build without the sampler, -3 a system without the hook.
    static func start() -> Int32 { startFunction?() ?? -2 }
    @discardableResult static func stop() -> Int32 { stopFunction?() ?? -2 }

    struct Stack { let liveBytes: UInt64, liveSamples: UInt64, totalBytes: UInt64, totalSamples: UInt64, frames: [UInt64] }
    struct Totals { let liveBytes: UInt64, liveSamples: UInt64, totalBytes: UInt64, totalSamples: UInt64,
                    dropped: UInt64, unwalked: UInt64, stacks: UInt64, interval: UInt64 }

    static func report(capacity: Int) -> (totals: Totals, stacks: [Stack])? {
        guard let reportFunction else { return nil }
        let totals = UnsafeMutablePointer<UInt64>.allocate(capacity:totalsWords)
        let stacks = UnsafeMutablePointer<UInt64>.allocate(capacity:stackWords * capacity)
        defer { totals.deallocate(); stacks.deallocate() }
        totals.initialize(repeating:0, count:totalsWords)
        stacks.initialize(repeating:0, count:stackWords * capacity)
        let count = Int(reportFunction(totals, stacks, Int32(capacity)))
        var list: [Stack] = []
        for index in 0..<max(0, min(count, capacity)) {
            let base = stacks + index * stackWords
            let frameCount = min(frames, Int(base[4] & 0xFFFF_FFFF))
            list.append(Stack(liveBytes:base[0], liveSamples:base[1], totalBytes:base[2], totalSamples:base[3],
                              frames:(0..<frameCount).map { base[5 + $0] }))
        }
        return (Totals(liveBytes:totals[0], liveSamples:totals[1], totalBytes:totals[2], totalSamples:totals[3],
                       dropped:totals[4], unwalked:totals[5], stacks:totals[6], interval:totals[7]), list)
    }
}

final class MeloNXHeapSample {
    static let windowSeconds = 120.0
    static let maxStacks = 24, maxPlaces = 10
    static let shared = MeloNXHeapSample()

    private let queue = DispatchQueue(label:"RewindBox.MeloNX.Heap", qos:.utility)
    // Confined to the queue.
    private var open = false
    private var window = 0
    private var started = 0.0
    private var path = ""
    private var context: [String:String] = [:]

    /// At the start of a session, before the engine is launched (the hook is set when this returns). A session that
    /// begins while a window is open joins it.
    func begin(path: String?, context: [String:String], seconds: Double = MeloNXHeapSample.windowSeconds) {
        queue.sync { [self] in
            guard !open, let path else { return }
            var owned = context
            if owned["pid"] == nil { owned["pid"] = String(ProcessInfo.processInfo.processIdentifier) }
            let status = MeloNXHeapSamplerLink.start()
            guard status == 1 else {
                Self.write(["not started: " + (status == -1 ? "another logger owns the hook" : status == -2 ? "no sampler in this build" :
                                             status == -3 ? "the system exports no logging hook" : "already set")],
                           path:path, context:owned)
                return
            }
            open = true; window += 1; started = ProcessInfo.processInfo.systemUptime; self.path = path; self.context = owned
            let mine = window
            queue.asyncAfter(deadline:.now() + seconds) { [self] in if open && window == mine { finish("window") } }
        }
    }

    /// At the end of the session: an open window ends with it.
    func end() { queue.async { [self] in if open { finish("sessionEnd") } } }

    private func finish(_ reason: String) {
        open = false
        MeloNXHeapSamplerLink.stop()
        let seconds = Int((ProcessInfo.processInfo.systemUptime - started).rounded())
        Self.write(Self.lines(reason:reason, seconds:seconds), path:path, context:context)
    }

    private static func write(_ lines: [String], path: String, context: [String:String]) {
        for (index, line) in lines.enumerated() {
            let text = "[MeloNX:heap] " + line
            _ = MeloNXStdioCapture.appendLine(index == 0 ? MeloNXStdioCapture.contextualLine(text, context:context) : text,
                                              to:path, limit:MeloNXPerfJournal.fileLimit)
        }
    }

    /// The report of the window that just ended (the hook is off): the header line, then one line per stack.
    static func lines(reason: String, seconds: Int) -> [String] {
        guard let report = MeloNXHeapSamplerLink.report(capacity:maxStacks) else { return ["window \(seconds) s (\(reason)): no sampler in this build"] }
        func mib(_ bytes: UInt64) -> String { String(bytes >> 20) }
        let totals = report.totals
        var lines = ["window \(seconds) s (\(reason)): live \(mib(totals.liveBytes)) MiB in \(totals.liveSamples) samples, allocated " +
                     "\(mib(totals.totalBytes)) MiB in \(totals.totalSamples), interval \(totals.interval >> 10) KiB, \(totals.stacks) stacks, " +
                     "\(totals.dropped) dropped, \(totals.unwalked) unwalked; zones=\(MeloNXMemoryBreakdown.zones())"]
        var cache: [UInt64: String] = [:]
        for (index, stack) in report.stacks.enumerated() {
            var places = stack.frames.map { address -> String in
                let place = MeloNXStallWatch.place(address & MeloNXStallWatch.addressMask, &cache)
                return place.hasPrefix("jit:") ? "jit" : place.hasPrefix("anon:") ? "anon" : place
            }
            // The innermost frames are the sampler's own, then libmalloc's: the call starts after them.
            if let first = places.firstIndex(where: { $0.hasPrefix("libsystem_malloc.dylib+") }) {
                var end = first
                while end < places.count && places[end].hasPrefix("libsystem_malloc.dylib+") { end += 1 }
                places.removeFirst(end)
            }
            lines.append("#\(index + 1) live=\(mib(stack.liveBytes))/\(stack.liveSamples) total=\(mib(stack.totalBytes))/\(stack.totalSamples) " +
                         "stack=" + (places.isEmpty ? "-" : places.prefix(maxPlaces).joined(separator:"<")))
        }
        return lines
    }
}
