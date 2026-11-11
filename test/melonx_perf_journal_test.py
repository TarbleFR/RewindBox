#!/usr/bin/env python3
"""Per-second MeloNX performance journal (Diagnostics/Switch/MeloNX-performance.log).

The wiring and the engine/host counter contract are checked anywhere. The
Swift sampler is compiled and executed only where xcrun exists (macOS CI):
real thread enumeration with a busy named thread, fake engine counters, the
pause flag, the line limit, the end summary and the release of thread ports.
Gameplay, Metal presentation and the device's thermal behaviour are not tested.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/melonx_internal_bridge/ios/Classes'
checks = 0


def check(condition, message):
    global checks
    assert condition, message
    checks += 1


journal = (CLASSES / 'MeloNXPerfJournal.swift').read_text()
runtime = (CLASSES / 'MeloNXRuntimeAPI.swift').read_text()
controller = (CLASSES / 'MeloNXMetalSessionViewController.swift').read_text()
parity = (CLASSES / 'MeloNXStandaloneParity.swift').read_text()
header = (CLASSES / 'MeloNXSessionABI.h').read_text()
pacing = (ROOT / 'native/melonx/EmbeddedAudioPacing.cs').read_text()
export = (ROOT / 'native/melonx/EmbeddedAudioPacingExport.cs').read_text()
build = (ROOT / 'build-utils/melonx/build_core.sh').read_text()

# Engine/host contract: nine cumulative values, optional on the host.
check('public const int Count = 9;' in pacing and 'count != EmbeddedAudioPacing.Count' in export, 'engine count')
check('"neostation_melonx_audio_pacing"' in export and "'neostation_melonx_audio_pacing'" in build, 'export not required by the build')
check('int32_t neostation_melonx_audio_pacing(int64_t *values, int32_t count);' in header, 'C prototype')
check('audioPacingFunction = dlsym(handle, "neostation_melonx_audio_pacing")' in runtime, 'audio pacing must stay optional')
check('[Int64](repeating:0,count:9)' in runtime and 'audioPacingFunction(&values,9) == 0' in runtime, 'host count')
order = re.findall(r'values\[(\d)\] = Interlocked\.(Read|Exchange)\(ref (_\w+)', pacing)
check([int(i) for i, _, _ in order] == list(range(9)), order)
check([kind for _, kind, _ in order].count('Exchange') == 2 and order[3][1] == order[8][1] == 'Exchange', 'maxima reset on read')
# The smoke app compiles MeloNXRuntimeAPI.swift without the journal or parity file.
check('MeloNXPerfJournal' not in runtime and 'MeloNXStdioCapture' not in runtime, 'runtime API depends on the host journal')
# The engine's gen0 GC budget (64 MiB, hex for the NativeAOT runtime) is in the environment before its first load,
# without overriding an existing value.
check('static let gen0BudgetVariable = "DOTNET_GCgen0size"' in runtime and 'static let gen0BudgetHex = "4000000"' in runtime and
      runtime.count('setenv(') == 1 and runtime.index('setenv(Self.gen0BudgetVariable, Self.gen0BudgetHex, 0)') <
      runtime.index('session = try MeloNXNativeSessionAPI(libraryURL: library)'), 'gen0 budget not set before the engine loads')

# Controller wiring: started with the controls, paused with the game, stopped
# before the capture ends and on deinit. Writes go through the shared writer.
install = controller[controller.index('private func installControls'):controller.index('private func refreshControls')]
check(install.index('guard let runtime else { return }') < install.index('startPerfJournal(runtime:runtime,generation:generation)'), 'journal start')
check('guard perf == nil, let path = MeloNXStdioCapture.journalPath else { return }' in controller, 'journal path')
completion = controller.index('self?.perf?.stop(); self?.perf = nil')
check(completion < controller.index('MeloNXStdioCapture.end(); UIApplication.shared.isIdleTimerDisabled = false', completion), 'journal stop')
pause = controller[controller.index('private func applyPause()'):]
check(pause.index('perf?.setPaused(!pauseReasons.isEmpty)') < pause.index('host.setPaused('), 'pause flag')
check('surface.metalLayer.restartPacing()' in pause[:400], 'pause counted as a held frame')
check(controller[controller.index('deinit {'):].startswith('deinit {\n        perf?.stop()'), 'journal not stopped on deinit')
# Presentation pacing: gaps over 50 and 100 ms and the bounded list of gaps, reset on each read.
check('if gap > 50 { self.pacing.over50 += 1 }' in controller and 'if gap > 100 { self.pacing.over100 += 1 }' in controller,
      'long-gap counters')
check('self.pacing.gapsMs.count < MeloNXPerfJournal.Presentation.gapLimit' in controller and
      'pacing.gapsMs.removeAll(keepingCapacity: true)' in controller and 'static let gapLimit = 240' in journal,
      'bounded gap list reset on read')
check('fields.append("long=\\(over50)/\\(over100)")' in journal and 'fields.append("gaps=" + ' in journal, 'journal fields')
check('if let text = vmActivity() { fields.append("vm=" + text) }' in journal and
      journal.index('fields.append("mem=" + text)') < journal.index('fields.append("vm=" + text)') < journal.index('fields.append("th=" + ') and
      journal.count('task_flavor_t(TASK_EVENTS_INFO)') == 1 and 'vm.compressed_lifetime' in journal and 'vm.decompressions' in journal,
      'vm= field: compression, decompression, faults and page-ins over the interval, read only')
# hw= field (lot 11): how the CPU time of the interval was served (clock, instructions per cycle, share on performance
# cores, time waiting for a core, then the clocks of the performance cores and of the others), from one
# proc_pid_rusage call looked up at run time; after vm=, before th=. The kernel's runnable time counts the time running
# too (xnu thread.h: "time the thread is runnable (including running)"): the CPU time is taken off it.
check('if let text = hwActivity(cpuNs:total) { fields.append("hw=" + text) }' in journal and
      journal.index('fields.append("vm=" + text)') < journal.index('fields.append("hw=" + text)') < journal.index('fields.append("th=" + ') and
      journal.count('dlsym(UnsafeMutableRawPointer(bitPattern:-2), "proc_pid_rusage")') == 1 and journal.count('RUSAGE_INFO_V6') == 2 and
      'info.ri_user_ptime &+ info.ri_system_ptime' in journal and 'info.ri_runnable_time' in journal and
      'guard let before = previousHw else { return nil }' in journal,
      'hw= field: one read-only call, optional, absent on the first line')
check('waiting = String(Int((max(0, Double(now.runnable - before.runnable) - time) / time * 100).rounded()))' in journal and
      'performanceCycles:info.ri_pcycles' in journal and 'mach_timebase_info(&base) == KERN_SUCCESS' in journal and
      'return "\\(clock)/\\(perCycle)/\\(performance)/\\(waiting)/\\(performanceClock)/\\(otherClock)"' in journal,
      'hw= field: six values, the time running taken off the runnable time, both clocks from the kernel\'s own times')
# pc= field (lot 11): the share of each listed thread's CPU time on performance cores, in the order of cpu=, from
# proc_pidinfo's per-thread counts by performance level (flavor 34), looked up at run time; bounded, optional.
check('if let text = performanceShares(threads:busy.map { (id:$0.id, ns:$0.ns) }, listed:listed) { fields.append("pc=" + text) }' in journal and
      journal.index('fields.append("hw=" + text)') < journal.index('fields.append("pc=" + text)') < journal.index('fields.append("th=" + ') and
      journal.count('dlsym(UnsafeMutableRawPointer(bitPattern:-2), "proc_pidinfo")') == 1 and 'counts(getpid(), 34, id, $0.baseAddress!, size)' in journal and
      'static let levelThreads = 48' in journal and 'threads.prefix(Self.levelThreads) where thread.ns >= 1_000_000' in journal and
      'if String(cString:name) == "Performance" { return (index:index, levels:Int(levels)) }' in journal and
      'return shares.contains { $0 != "-" } ? shares.joined(separator:",") : nil' in journal,
      'pc= field: per-thread share on performance cores, bounded calls, absent when nothing is known')
# Lot 9: the engine call's own duration (a GC suspension in progress blocks it), timed around fps() only.
check('let callStart = ProcessInfo.processInfo.systemUptime\n        let engine = MeloNXEngineCallClass.interactive { fps() }\n        let callMs = ' in journal and
      'fields.append("mgd=" + Self.decimal(callMs))' in journal, 'journal mgd field around the engine call')
check('static func appendLine(_ text: String, to path: String, limit: Int64 = 5 * 1024 * 1024) -> Bool' in parity and 'appendLine(contextualLine("[MeloNX:stderr] " + safe,context:context), to:path)' in parity, 'shared writer')
# Lot 9: the stall watch writes its two kinds of lines, and the memory breakdown its one, through the same writer under
# the same cap.
check(journal.count('MeloNXStdioCapture.appendLine(') == 7 and journal.count(', to:path, limit:Self.fileLimit)') == 4 and
      journal.count(', to:path, limit:MeloNXPerfJournal.fileLimit)') == 3 and 'open(' not in journal,
      'journal writes outside the shared writer or under the general cap')
check('static let fileLimit: Int64 = 8 * 1024 * 1024' in journal and 'if !isPaused && rate > 0 {' in journal, 'journal cap or FPS average')
check('qos:.utility' in journal and 'func stop() {\n        queue.async' in journal, 'sampler priority or synchronous stop')
check('mach_port_deallocate(mach_task_self_, list[index])' in journal and 'vm_deallocate(mach_task_self_' in journal, 'thread ports leak')

# Stall watch (lot 9): the three engine calls of a sample are announced; the watch never calls the engine, never
# suspends a thread, and is bounded.
check('stalls.enter("fps")\n        let callStart = ProcessInfo.processInfo.systemUptime\n        let engine = MeloNXEngineCallClass.interactive { fps() }\n'
      '        let callMs = (ProcessInfo.processInfo.systemUptime - callStart) * 1000\n        stalls.exit()\n' in journal,
      'the fps() call is announced around the mgd= measure')
check('stalls.enter("audio")\n        let pacing = MeloNXEngineCallClass.interactive { audio() }\n        stalls.exit()\n' in journal and
      'stalls.enter("memory")\n        let footprint = memory()\n        stalls.exit()\n' in journal, 'audio() and memory() announced')
watch = journal[journal.index('final class MeloNXStallWatch {'):]
check(all(name not in watch for name in ('fps(', 'audio(', 'memory(', 'presentation(', 'thread_suspend', 'thread_resume',
                                         'task_suspend', 'DispatchQueue.main')), 'the watch calls no engine closure and suspends nothing')
check('static let stagesMs: [Double] = [300, 1300, 3300]' in watch and 'static let maxStalls = 6' in watch and
      'static let maxFrames = 8' in watch and 'usleep(50_000)' in watch, 'stall bounds')
check(watch.count('vm_read_overwrite(') == 1 and 'thread_get_state(thread, thread_state_flavor_t(ARM_THREAD_STATE64)' in watch and
      'guard thread != me else { continue }' in watch and watch.count('mach_port_deallocate(mach_task_self_, list[index])') == 1 and
      'mach_port_deallocate(mach_task_self_, me)' in watch, 'safe reads, own thread skipped, ports released')
check(journal.index('            stalls.start()\n') < journal.index('    func stop() {') and
      'queue.async { [self] in\n            stalls.stop()\n' in journal, 'watch started with the journal and stopped with it')
watch_only = journal[journal.index('final class MeloNXStallWatch {'):journal.index('final class MeloNXMemoryBreakdown {')]
check(watch_only.count('MeloNXStdioCapture.appendLine(') == 2, 'the stall watch writes its two lines')

# Memory breakdown (lot 9, RAM): the footprint's ledgers and regions, bounded, from its own utility queue, started and
# stopped with the journal; it reads the process's own VM map and calls no engine closure.
breakdown = journal[journal.index('final class MeloNXMemoryBreakdown {'):]
check('            stalls.start()\n            breakdown.start()\n' in journal and
      '            stalls.stop()\n            breakdown.stop()\n' in journal, 'breakdown started and stopped with the journal')
check(all(name not in breakdown for name in ('fps(', 'audio(', 'memory(', 'presentation(', 'thread_suspend', 'task_suspend',
                                             'vm_write', 'vm_protect', 'mach_vm_protect', 'DispatchQueue.main', 'vm_deallocate')),
      'the breakdown calls no engine closure and changes no memory')
check('static let maxRegions = 400_000' in breakdown and 'static let maxWalkMs = 1200.0' in breakdown and
      'static let maxPageWalkBytes: UInt64 = 256 << 20' in breakdown and 'static let minSharedQueryBytes: UInt64 = 1 << 20' in breakdown and
      'first: Double = 30, every: Double = 60, maxLines: Int = 30' in breakdown and
      'guard lines < maxLines else { timer?.cancel(); timer = nil; return }' in breakdown and
      'qos:.utility' in breakdown and breakdown.count('MeloNXStdioCapture.appendLine(') == 1, 'breakdown bounds')
check(breakdown.count('malloc_zone_statistics(zone, &statistics)') == 1 and breakdown.count('malloc_get_all_zones(mach_task_self_, nil, &addresses, &count)') == 1 and
      'found.prefix(4)' in breakdown and all(name not in breakdown for name in ('malloc_zone_pressure_relief', 'malloc_zone_batch_free', 'malloc_destroy_zone', 'free(')),
      'malloc zones are read (statistics only), four at most')
check('task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO)' in breakdown and
      'vm_region_recurse_64(mach_task_self_, &address, &size, &depth, $0, &count)' in breakdown and
      'vm_region_submap_short_info_data_64_t()' in breakdown and 'VM_REGION_TOP_INFO' in breakdown and
      'if info.is_submap != 0 { continue }' in breakdown and 'sharedObjects[info.object_id]' in breakdown,
      'ledgers, one O(1) query per top-level region (the shared region skipped), shared objects counted once')
# The page walk (resident and compressed pages) is for private anonymous regions under the size bound only; a small
# shared region (the guest lease) costs the one O(1) query.
walk = breakdown[breakdown.index('            if shared && UInt64(size) < minSharedQueryBytes {'):breakdown.index('            if shared {\n                // Every mapping')]
check(breakdown.count('vm_region_submap_info_data_64_t()') == 1 and
      walk.index('if shared && UInt64(size) < minSharedQueryBytes {') < walk.index('if !shared && !file && UInt64(size) <= maxPageWalkBytes {') <
      walk.index('vm_region_submap_info_data_64_t()') < walk.index('} else {') < walk.index('VM_REGION_TOP_INFO') and
      'compressed = UInt64(full.pages_swapped_out) * page' in walk and 'resident = UInt64(full.pages_resident) * page' in walk,
      'page walk for private anonymous regions under the bound only')

# Engine calls made from the utility queues (the sampler's two, the plugin's diagnostics drain every 300 ms) run in
# the user-interactive class for their duration: an override on the calling thread, ended when the call returns.
plugin = (CLASSES / 'MeloNXInternalBridgePlugin.swift').read_text()
helper = journal[journal.index('enum MeloNXEngineCallClass {'):journal.index('final class MeloNXPerfJournal {')]
check('let override: pthread_override_t? = pthread_override_qos_class_start_np(pthread_self(), QOS_CLASS_USER_INTERACTIVE, 0)' in helper and
      'defer { if let override { pthread_override_qos_class_end_np(override) } }' in helper and
      helper.index('pthread_override_qos_class_start_np') < helper.index('defer {') < helper.index('return try call()'),
      'the override starts before the call and ends when it returns or throws')
check('pthread_set_qos_class_self_np' not in helper, 'the queue thread\'s requested class is not changed')
check(journal.count('MeloNXEngineCallClass.interactive { fps() }') == 1 and journal.count('MeloNXEngineCallClass.interactive { audio() }') == 2 and
      not re.search(r'(?<!interactive \{ )\b(fps|audio)\(\)(?! \})', journal[journal.index('final class MeloNXPerfJournal {'):journal.index('static func threads()')]),
      'every engine call of the sampler runs under the override')
drain = plugin[plugin.index('private func drainDiagnostics'):plugin.index('// Accessed only on libraryQueue. Success includes')]
check('let report = MeloNXEngineCallClass.interactive { runtime.diagnostics() }' in drain and drain.count('runtime.diagnostics()') == 1 and
      'DispatchQueue(label:"com.neogamelab.neostation.melonx.diagnostics",qos:.utility)' in plugin and
      'timer.schedule(deadline:.now(),repeating:.milliseconds(300))' in plugin, 'the diagnostics drain calls the engine under the override')

if shutil.which('xcrun'):
    with tempfile.TemporaryDirectory(prefix='melonx-perf-') as temporary:
        work = Path(temporary)
        log = work / 'app.log'
        (work / 'main.swift').write_text(r'''import Foundation
import Darwin
let path = CommandLine.arguments[1]
var calls = 0, audioCalls: Int64 = 0
let busy = Thread {
    var x = 0.0
    while !Thread.current.isCancelled { for i in 0..<100_000 { x += sqrt(Double(i)) } }
    if x < 0 { print(x) }
}
busy.name = "Perf Busy:Worker/1"
busy.start()
usleep(200_000)
let threads = MeloNXPerfJournal.threads()
guard let worker = threads.first(where: { $0.name == "Perf_Busy_Worker_1" }), worker.cpuNs > 0 else { print(threads.map(\.name)); exit(3) }
guard Set(threads.map(\.id)).count == threads.count, threads.count >= 2 else { exit(4) }
// task_threads returns a send right per thread: all must be released.
let me = mach_thread_self()
var before: mach_port_urefs_t = 0, after: mach_port_urefs_t = 0
mach_port_get_refs(mach_task_self_, me, MACH_PORT_RIGHT_SEND, &before)
for _ in 0..<200 { _ = MeloNXPerfJournal.threads() }
mach_port_get_refs(mach_task_self_, me, MACH_PORT_RIGHT_SEND, &after)
mach_port_deallocate(mach_task_self_, me)
guard before == after else { print("refs", before, after); exit(5) }
// vm= field: real counters readable, differences formatted, a wrapped counter written "-".
guard let vmNow = MeloNXPerfJournal.vmCounters(), vmNow.faults > 0 else { print("vm counters"); exit(6) }
let vmBefore = MeloNXPerfJournal.VmCounters(compressedBytes:10 << 20, decompressions:100, faults:1_000, pageins:5)
print("vmField " + MeloNXPerfJournal.vmField(from:vmBefore, to:MeloNXPerfJournal.VmCounters(compressedBytes:42 << 20, decompressions:350, faults:1_900, pageins:5)))
print("vmField " + MeloNXPerfJournal.vmField(from:vmBefore, to:MeloNXPerfJournal.VmCounters(compressedBytes:5 << 20, decompressions:99, faults:2_000, pageins:6)))
// hw= field: the call exists and answers; ratios formatted; a counter that went backwards written "-"; no line without CPU time.
guard let hwNow = MeloNXPerfJournal.hwCounters(), hwNow.time > 0 else { print("hw counters"); exit(7) }
// A time unit of 1 000 ns here: 1 000 units of CPU time are the millisecond given as cpuNs.
let hwBefore = MeloNXPerfJournal.HwCounters(cycles:1_000, instructions:2_000, time:100, performanceTime:40, runnable:110, performanceCycles:400)
func hw(_ now: MeloNXPerfJournal.HwCounters, _ cpuNs: UInt64) -> String { MeloNXPerfJournal.hwField(from:hwBefore, to:now, cpuNs:cpuNs, timeUnitNs:1_000) ?? "nil" }
// Three quarters of the time on performance cores with 3 000 000 of the 3 200 000 cycles; runnable a quarter longer than running.
print("hwField " + hw(MeloNXPerfJournal.HwCounters(cycles:3_201_000, instructions:6_402_000, time:1_100, performanceTime:790, runnable:1_360, performanceCycles:3_000_400), 1_000_000))
// No cycle counted, the performance time went backwards, runnable shorter than the CPU time (threads that ended).
print("hwField " + hw(MeloNXPerfJournal.HwCounters(cycles:1_000, instructions:2_000, time:1_100, performanceTime:20, runnable:1_010, performanceCycles:400), 2_000_000))
// All the time on performance cores: no other clock; waiting twice the CPU time.
print("hwField " + hw(MeloNXPerfJournal.HwCounters(cycles:2_001_000, instructions:2_002_000, time:1_100, performanceTime:1_040, runnable:3_110, performanceCycles:2_000_400), 1_000_000))
// The runnable time and the performance cycles went backwards.
print("hwField " + hw(MeloNXPerfJournal.HwCounters(cycles:3_201_000, instructions:6_402_000, time:1_100, performanceTime:790, runnable:5, performanceCycles:300), 1_000_000))
print("hwField " + hw(MeloNXPerfJournal.HwCounters(cycles:9_000, instructions:9_000, time:100, performanceTime:40, runnable:110, performanceCycles:400), 1_000_000))
print("hwField " + hw(MeloNXPerfJournal.HwCounters(cycles:9_000, instructions:9_000, time:1_100, performanceTime:40, runnable:110, performanceCycles:400), 0))
print("timeUnit " + (MeloNXPerfJournal.timeUnitNs > 0 ? "positive" : "zero"))
// pc= field: the share is formatted from two samples; no CPU time or a counter that went backwards gives "-". The
// per-level counts of the busy thread are read when the host has them (a virtual machine may not).
func share(_ now: MeloNXPerfJournal.LevelTimes) -> String { MeloNXPerfJournal.performanceShare(from:MeloNXPerfJournal.LevelTimes(performance:100, total:200), to:now) }
print("pcShare " + share(MeloNXPerfJournal.LevelTimes(performance:400, total:600)))
print("pcShare " + share(MeloNXPerfJournal.LevelTimes(performance:100, total:200)))
print("pcShare " + share(MeloNXPerfJournal.LevelTimes(performance:50, total:600)))
if let levels = MeloNXPerfJournal.levelTimes(thread:worker.id) { print("pcLevels " + (levels.performance <= levels.total && levels.total > 0 ? "plausible" : "implausible")) }
else { print("pcLevels unavailable") }
// Engine-call class: on a utility queue's thread the call runs at the user-interactive priority, nested calls too,
// and the queue's priority is back when the call returns or throws.
struct EngineCallFailure: Error {}
let classDone = DispatchSemaphore(value:0)
var classLine = "engineClass unavailable"
DispatchQueue(label:"Perf.Utility", qos:.utility).async {
    let before = MeloNXPerfJournal.currentPriorities()
    let (inside, value) = MeloNXEngineCallClass.interactive { (MeloNXPerfJournal.currentPriorities(), 42) }
    let nested = MeloNXEngineCallClass.interactive { MeloNXEngineCallClass.interactive { MeloNXPerfJournal.currentPriorities() } }
    let between = MeloNXPerfJournal.currentPriorities()
    var thrown = false
    do { try MeloNXEngineCallClass.interactive { throw EngineCallFailure() } } catch { thrown = true }
    let after = MeloNXPerfJournal.currentPriorities()
    if let before, let inside, let nested, let between, let after {
        classLine = "engineClass \(before.base) \(inside.base) \(nested.base) \(between.base) \(after.base) \(value) \(thrown) \(inside.scheduled > before.scheduled)"
    }
    classDone.signal()
}
classDone.wait()
print(classLine)
let journal = MeloNXPerfJournal(path:path, interval:0.25, lineLimit:6,
    fps:{ ["gameFps":59.5,"gameFrameTimeMs":16.8,"fifoPercent":40.0] },
    presentation:{
        calls += 1
        return MeloNXPerfJournal.Presentation(frames:UInt64(calls * 60), maxGapMs:34.5, over20:UInt64(calls * 2), over40:0,
                                              over50:UInt64(calls), over100:0, gapsMs:[17, 34])
    },
    audio:{
        audioCalls += 1
        let n = audioCalls
        return [n * 200, n * 3, n * 7_500_000, 3_100_000, n, n * 200, n, n * 12_000_000, 12_000_000]
    })
journal.start()
usleep(1_200_000)
journal.setPaused(true)
usleep(1_500_000)
journal.stop()
busy.cancel()
for _ in 0..<100 {
    if (try? String(contentsOfFile:path, encoding:.utf8))?.contains("[MeloNX:perf] end:") == true { exit(0) }
    usleep(50_000)
}
exit(2)
''')
        executable = work / 'perf'
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(CLASSES / 'MeloNXStandaloneParity.swift'),
                        str(CLASSES / 'MeloNXPerfJournal.swift'), str(work / 'main.swift'), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable), str(log)], capture_output=True, text=True, timeout=60)
        check(result.returncode == 0, result)
        lines = log.read_text().splitlines()
        check(all(line.startswith('[MeloNX:perf] ') for line in lines), lines[:3])
        body = [line.removeprefix('[MeloNX:perf] ') for line in lines]
        check(body[0] == f'begin: every 0.25 s, {body[0].split(", ")[1]}, audio counters available', body[0])
        samples = [line for line in body if line.startswith('t=')]
        check(len(samples) == 6 and body[7] == 'limit: 6 lines; only the end summary follows' and body[-1].startswith('end: '), body)
        for line in samples:
            fields = line.split(' ')
            check('fps=59.5/16.8/40' in fields and 'pres=60/34.5/2/0' in fields, line)
            check('long=1/0' in fields and 'gaps=17,34' in fields, line)
            check(any(field.startswith('mgd=') for field in fields), line)
            check('dsp=200/3/7.5/3.1/1' in fields and 'out=200/1/12.0/12.0' in fields, line)
            check(re.search(r' th=(nominal|fair|serious|critical) lp=[01]( paused)?$', line), line)
            # The spinning thread is the busiest one listed (threads are sorted by CPU time): it comes first,
            # with a share above zero and at least that of every other listed thread. Its share of a 0.25 s
            # sample depends on the shared runner's load (39 % in run 41523517233, 7 % in delivery run
            # 42819476474), so no fixed floor is asked: the order and a measured share are what is checked.
            worker = re.search(r' cpu=\d+ Perf_Busy_Worker_1:(\d+)/(\d+)', line)
            check(worker and int(worker.group(1)) >= 1, line)
            check(all(int(share) <= int(worker.group(1)) for share in re.findall(r' \S+:(\d+)/\d+', line)), line)
            check(int(re.search(r' cpu=(\d+)', line).group(1)) >= int(worker.group(1)), line)
            check(len(re.findall(r' \S+:\d+/\d+', line)) <= 6, line)
        check('paused' not in samples[0] and 'paused' in samples[-1], samples)
        # vm= (the kernel's compression, decompression, fault and page-in counts over the interval): absent on the first
        # line, four counts on the others, before th=.
        check(' vm=' not in samples[0] and all(re.search(r' vm=\d+/\d+/\d+/\d+ (hw=\S+ )?(pc=\S+ )?(in=\S+ )?th=', line) for line in samples[1:]), samples)
        # pc= (per cent of each listed thread's CPU time on performance cores, in the order of cpu=): absent on the first
        # line and where the host gives no per-level counts; never more values than threads listed.
        levels = [line for line in result.stdout.splitlines() if line.startswith('pcLevels ')]
        check(levels in (['pcLevels plausible'], ['pcLevels unavailable']), result.stdout)
        check(' pc=' not in samples[0], samples[0])
        for line in samples[1:]:
            shares = re.search(r' pc=(\S+) ', line)
            if levels == ['pcLevels unavailable']:
                check(shares is None, line)
            elif shares:
                values = shares.group(1).split(',')
                check(all(re.fullmatch(r'\d+|-', value) and (value == '-' or int(value) <= 100) for value in values) and
                      len(values) == len(re.findall(r' \S+:\d+/-?\d+', line)), line)
        check([line for line in result.stdout.splitlines() if line.startswith('pcShare ')] == ['pcShare 75', 'pcShare -', 'pcShare -'], result.stdout)
        # hw= (clock in GHz, instructions per cycle, per cent on performance cores, per cent waiting for a core, the clocks
        # of the performance cores and of the others):
        # absent on the first line; on the others four values, "-" where the host counts no cycles (a virtual machine).
        check(' hw=' not in samples[0] and
              all(re.search(r' hw=\d+\.\d/(\d+\.\d\d|-)/(\d+|-)/(\d+|-)/(\d+\.\d|-)/(\d+\.\d|-) ', line) for line in samples[1:]), samples)
        check([line for line in result.stdout.splitlines() if line.startswith('hwField ')] ==
              ['hwField 3.2/2.00/75/25/4.0/0.8', 'hwField 0.0/-/-/0/-/-', 'hwField 2.0/1.00/100/200/2.0/-', 'hwField 3.2/2.00/75/-/-/-',
               'hwField nil', 'hwField nil'] and 'timeUnit positive' in result.stdout.splitlines(), result.stdout)
        check([line for line in result.stdout.splitlines() if line.startswith('vmField ')] == ['vmField 32/250/900/0', 'vmField -/-/1000/1'],
              result.stdout)
        # Engine-call class (base priorities: 47 user-interactive, 20 utility): the utility queue's thread is at the
        # user-interactive priority inside the call and inside a nested one, and back at its own between and after
        # (after a call that threw as well); the call's value is returned.
        engine_class = [line.split(' ')[1:] for line in result.stdout.splitlines() if line.startswith('engineClass ')]
        check(len(engine_class) == 1 and len(engine_class[0]) == 8, result.stdout)
        before, inside, nested, between, after = map(int, engine_class[0][:5])
        check(before <= 31 and inside >= 45 and nested == inside and between == before and after == before and
              engine_class[0][5:] == ['42', 'true', 'true'], 'engine call class on a utility queue: ' + ' '.join(engine_class[0]))
        total = int(re.search(r'^end: (\d+) s sampled, 6 lines;', body[-1]).group(1))
        check(total >= 9, body[-1])
        check(f'{total * 60} frames presented, {total * 2} gaps over 20 ms, 0 over 40 ms, {total} over 50 ms, 0 over 100 ms'
              in body[-1], body[-1])
        check(f'{total * 3} late DSP episodes ({total * 7.5:.1f} ms), {total} skipped' in body[-1], body[-1])
        check(f'{total} audio starvations ({total * 12:.1f} ms)' in body[-1] and 'game FPS 59.5 on average' in body[-1], body[-1])
        # Stall watch: one engine call blocked 1.6 s while a named thread spins and another waits, then seven of
        # 500 ms (only six stalls are recorded), then quick calls.
        stall_log = work / 'stall.log'
        (work / 'stall').mkdir()
        # Top-level code is only allowed in main.swift: the second program has its own directory.
        (work / 'stall' / 'main.swift').write_text(r'''import Foundation
import Darwin
let path = CommandLine.arguments[1]
let spinner = Thread {
    var x = 0.0
    while !Thread.current.isCancelled { for i in 0..<100_000 { x += sqrt(Double(i)) } }
    if x < 0 { print(x) }
}
spinner.name = "Stall Spinner"
spinner.start()
let gate = DispatchSemaphore(value:0)
let waiter = Thread { gate.wait() }
waiter.name = "Stall Waiter"
waiter.start()
usleep(100_000)
let lock = NSLock()
var calls = 0
let journal = MeloNXPerfJournal(path:path, interval:0.1, lineLimit:100,
    fps:{
        lock.lock(); calls += 1; let call = calls; lock.unlock()
        if call == 1 { usleep(1_600_000) } else if call <= 8 { usleep(500_000) }
        return ["gameFps":30.0,"gameFrameTimeMs":33.3,"fifoPercent":10.0]
    },
    presentation:{ MeloNXPerfJournal.Presentation() }, audio:{ nil })
journal.start()
while true { lock.lock(); let done = calls >= 11; lock.unlock(); if done { break }; usleep(20_000) }
journal.stop()
usleep(400_000)
spinner.cancel(); gate.signal()
exit(0)
''')
        stall_executable = work / 'stall' / 'stall'
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(CLASSES / 'MeloNXStandaloneParity.swift'),
                        str(CLASSES / 'MeloNXPerfJournal.swift'), str(work / 'stall' / 'main.swift'), '-o', str(stall_executable)], check=True)
        result = subprocess.run([str(stall_executable), str(stall_log)], capture_output=True, text=True, timeout=120)
        check(result.returncode == 0, result)
        stall_lines = [line.removeprefix('[MeloNX:stall] ') for line in stall_log.read_text().splitlines() if line.startswith('[MeloNX:stall] ')]
        headers = [line for line in stall_lines if re.match(r'#\d+\.\d+ \w+ in flight \d+ ms, \d+ threads', line)]
        check([h.split(' ')[0] for h in headers] == ['#1.0', '#1.1', '#2.0', '#3.0', '#4.0', '#5.0', '#6.0'], headers)
        check(300 <= int(re.search(r'in flight (\d+) ms', headers[0]).group(1)) < 600 and
              1300 <= int(re.search(r'in flight (\d+) ms', headers[1]).group(1)) < 1600, headers[:2])
        ends = [line for line in stall_lines if re.match(r'#\d+ end: fps returned after', line)]
        check([e.split(' ')[0] for e in ends] == ['#1', '#2', '#3', '#4', '#5', '#6'], ends)
        first = float(re.search(r'after ([\d.]+) ms', ends[0]).group(1))
        check(1590 <= first < 1900 and all(490 <= float(re.search(r'after ([\d.]+) ms', e).group(1)) < 900 for e in ends[1:]), ends)
        def row(stage, thread):
            found = [line for line in stall_lines if line.startswith(stage + ' t') and (' ' + thread + ' ') in line]
            check(len(found) == 1, (stage, thread, found))
            return found[0]
        spin0, spin1 = row('#1.0', 'Stall_Spinner'), row('#1.1', 'Stall_Spinner')
        wait0, wait1 = row('#1.0', 'Stall_Waiter'), row('#1.1', 'Stall_Waiter')
        check(re.search(r' Stall_Spinner R s0 p\d+/\d+ c[\d.]+ pc=\S+\+0x[0-9a-f]+ lr=', spin0), spin0)
        check(float(re.search(r' c\+([\d.]+) ', spin1).group(1)) >= 200, 'the spinner ran between the two records: ' + spin1)
        check(re.search(r' Stall_Waiter W s0 p\d+/\d+ c[\d.]+ pc=libsystem_kernel\.dylib\+0x[0-9a-f]+ ', wait0), wait0)
        check(float(re.search(r' c\+([\d.]+) ', wait1).group(1)) < 20, 'the waiter did not run: ' + wait1)
        check(all(len(re.search(r' bt=(\S+)', line).group(1).split(',')) <= 8 for line in stall_lines if ' bt=' in line), 'frames bounded')
        check(not any(' RewindBox.MeloNX.StallWa ' in line for line in stall_lines), 'the watch does not list itself')
        # The blocked engine call is visible too: the journal's queue thread waits (usleep) with the stall.
        check(any(re.search(r' W s0 p\d+/\d+ c[\d.]+ pc=libsystem_kernel\.dylib\+0x', line) and line.startswith('#1.0') for line in stall_lines),
              'a waiting thread in the kernel')
        perf = [line for line in stall_log.read_text().splitlines() if line.startswith('[MeloNX:perf] t=')]
        check(perf and float(re.search(r' mgd=([\d.]+)', perf[0]).group(1)) >= 1590, perf[:1])

        # Memory breakdown: 96 MiB tagged app-specific 3 (64 MiB written) and 32 MiB of shared memory tagged
        # app-specific 4, written and mapped twice more without a tag (mach_vm_remap takes none): one object, counted
        # once in the tagged mapping's group; then the schedule's bound.
        memory_log = work / 'memory.log'
        (work / 'memory').mkdir()
        (work / 'memory' / 'main.swift').write_text(r'''import Foundation
import Darwin
let path = CommandLine.arguments[1]
func tag(_ value: UInt32) -> Int32 { Int32(bitPattern:value << 24) }
var tagged: mach_vm_address_t = 0
guard mach_vm_allocate(mach_task_self_, &tagged, 96 << 20, VM_FLAGS_ANYWHERE | tag(242)) == KERN_SUCCESS else { exit(3) }
memset(UnsafeMutableRawPointer(bitPattern:UInt(tagged))!, 1, 64 << 20)
let sharedSize = 32 << 20
guard let shared = mmap(nil, sharedSize, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, tag(243), 0),
      shared != UnsafeMutableRawPointer(bitPattern:-1) else { exit(4) }
memset(shared, 2, sharedSize)
for _ in 0..<2 {
    var alias: mach_vm_address_t = 0
    var current: vm_prot_t = 0, maximum: vm_prot_t = 0
    guard mach_vm_remap(mach_task_self_, &alias, mach_vm_size_t(sharedSize), 0, VM_FLAGS_ANYWHERE, mach_task_self_,
                        mach_vm_address_t(UInt(bitPattern:shared)), 0, &current, &maximum, VM_INHERIT_SHARE) == KERN_SUCCESS else { exit(5) }
    let bytes = UnsafePointer<UInt8>(bitPattern:UInt(alias))!
    var sum = 0
    for offset in stride(from:0, to:sharedSize, by:16384) { sum &+= Int(bytes[offset]) }
    if sum == 0 { exit(6) }
}
print("TAGGED 0x" + String(tagged, radix:16))
print("LINE " + MeloNXMemoryBreakdown.describe(seconds:0))
let breakdown = MeloNXMemoryBreakdown(path:path, context:[:], first:0.2, every:0.3, maxLines:3)
breakdown.start()
usleep(6_000_000)
breakdown.stop()
usleep(300_000)
exit(0)
''')
        memory_executable = work / 'memory' / 'memory'
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(CLASSES / 'MeloNXStandaloneParity.swift'),
                        str(CLASSES / 'MeloNXPerfJournal.swift'), str(work / 'memory' / 'main.swift'), '-o', str(memory_executable)], check=True)
        result = subprocess.run([str(memory_executable), str(memory_log)], capture_output=True, text=True, timeout=120)
        check(result.returncode == 0, result)
        tagged = next(line for line in result.stdout.splitlines() if line.startswith('TAGGED ')).split(' ')[1]
        line = next(line for line in result.stdout.splitlines() if line.startswith('LINE ')).removeprefix('LINE ')
        print(line, flush=True)
        check(re.match(r't=0 footprint=(\d+)/(\d+) graphics=\d+\+\d+ internal=\d+ compressed=\d+ device=\d+ media=\d+ neural=\d+ '
                       r'purgeable=\d+\+\d+ regions=(\d+)/[\d.]+ms private=(\d+)\+(\d+) unwalked=(\d+)/(\d+) sharedSmall=(\d+)/(\d+) '
                       r'zones=\S+ groups=\S+ top=\S+$', line), line)
        zones = [(z.split(':')[0], *map(int, z.split(':')[1].split('/'))) for z in re.search(r' zones=(\S+)', line).group(1).split(',')]
        check(1 <= len(zones) <= 4 and all(used <= held for _, used, held in zones) and zones == sorted(zones, key=lambda z: (-z[2], z[0])),
              'malloc zones: in use within held, largest first: ' + str(zones))
        # The dyld shared region is skipped (a submap): a small macOS process still has a few dozen top-level regions.
        check(int(re.search(r' footprint=(\d+)/', line).group(1)) >= 96 and int(re.search(r' regions=(\d+)/', line).group(1)) > 20, line)
        # name:resident+compressed/regions -> [resident, compressed, regions]
        groups = {g.split(':')[0]: [int(v) for v in re.split(r'[+/]', g.split(':')[1])] for g in re.search(r' groups=(\S+)', line).group(1).split(',')}
        check('app3' in groups and 64 <= groups['app3'][0] + groups['app3'][1] < 80 and groups['app3'][2] == 1, 'the tagged private region: ' + str(groups))
        check('app4~s' in groups and 32 <= groups['app4~s'][0] < 48 and groups['app4~s'][1] == 0 and groups['app4~s'][2] == 1,
              'the shared object mapped three times counts once: ' + str(groups))
        private = [int(v) for v in re.search(r' private=(\d+)\+(\d+) ', line).groups()]
        # macOS run 42926914192: 4 private regions over the bound (allocator reservations, 418 808 MiB of address space)
        # are not page-walked; the 96 MiB tagged region is under it and is.
        unwalked = [int(v) for v in re.search(r' unwalked=(\d+)/(\d+) ', line).groups()]
        check(private[0] + private[1] >= 64 and (unwalked[0] == 0 or unwalked[1] / unwalked[0] > 256),
              'the written private memory is in the private total; only regions over 256 MiB are left unwalked: ' + line)
        check(float(re.search(r' regions=\d+/([\d.]+)ms', line).group(1)) < 80, 'the walk is quick (private regions only are page-walked): ' + line)
        top = re.search(r' top=(\S+)', line).group(1).split(',')
        check(len(top) <= 10 and any(entry.startswith(tagged + ':96:app3:private:') and sum(map(int, entry.split(':')[4].split('+'))) >= 64 for entry in top),
              'the tagged region is among the largest: ' + str(top))
        written = [l for l in memory_log.read_text().splitlines() if l.startswith('[MeloNX:memory] ')]
        check(len(written) == 3 and all(re.match(r'\[MeloNX:memory\] t=\d+ footprint=', l) for l in written), 'three scheduled lines, then the bound: ' + str(written))
    print('Executed the performance journal on macOS.')

print(f'PASS {checks} performance journal checks')
