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
      journal.count('task_flavor_t(TASK_EVENTS_INFO)') == 2 and 'vm.compressed_lifetime' in journal and 'vm.decompressions' in journal,
      'vm= field: compression, decompression, faults and page-ins over the interval, read only')
# hw= field (lot 11): how the CPU time of the interval was served (clock, instructions per cycle, share on performance
# cores, time waiting for a core, then the clocks of the performance cores and of the others), from one
# proc_pid_rusage call looked up at run time; after vm=, before th=. The kernel's runnable time counts the time running
# too (xnu thread.h: "time the thread is runnable (including running)"): the CPU time is taken off it.
check('let served = hwActivity(cpuNs:total, seconds:elapsed)\n        if let text = served.hw { fields.append("hw=" + text) }' in journal and
      journal.index('fields.append("vm=" + text)') < journal.index('fields.append("hw=" + text)') < journal.index('fields.append("th=" + ') and
      journal.count('dlsym(UnsafeMutableRawPointer(bitPattern:-2), "proc_pid_rusage")') == 1 and journal.count('RUSAGE_INFO_V6') == 2 and
      'info.ri_user_ptime &+ info.ri_system_ptime' in journal and 'info.ri_runnable_time' in journal and
      'guard let before = previousHw else { return (nil, nil, nil) }' in journal,
      'hw= field: one read-only call, optional, absent on the first line')
check('waiting = String(Int((max(0, Double(now.runnable - before.runnable) - time) / time * 100).rounded()))' in journal and
      'performanceCycles:info.ri_pcycles' in journal and 'mach_timebase_info(&base) == KERN_SUCCESS' in journal and
      'return "\\(clock)/\\(perCycle)/\\(performance)/\\(waiting)/\\(performanceClock)/\\(otherClock)"' in journal,
      'hw= field: six values, the time running taken off the runnable time, both clocks from the kernel\'s own times')
# en= and sw= fields (lot 13, thermal): the watts of the process's CPU work from the kernel's energy accounting (the same
# proc_pid_rusage answer as hw=), and its context switches, system calls and interrupt wakeups per second; after hw=,
# read only, absent on the first line; en= absent where the host counts no energy.
check('if let text = served.energy { fields.append("en=" + text) }\n        if let text = served.switches { fields.append("sw=" + text) }' in journal and
      journal.index('fields.append("hw=" + text)') < journal.index('fields.append("en=" + text)') < journal.index('fields.append("sw=" + text)')
      < journal.index('fields.append("pc=" + text)') and
      'counters.energy = info.ri_energy_nj; counters.performanceEnergy = info.ri_penergy_nj' in journal and
      'counters.wakeups = info.ri_interrupt_wkups' in journal and 'guard seconds > 0, now.energy > 0, now.energy >= before.energy else { return nil }' in journal and
      'now.switches &- before.switches' in journal and 'now.calls &- before.calls' in journal,
      'en= and sw= fields: from the same answer as hw= and the task\'s events, wrapping counters subtracted as such')
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

# Engine calls made from the utility queues (the sampler's two, the plugin's diagnostics drain every 300 ms) are made
# by a thread of the user-interactive class the caller waits for, one at a time.
plugin = (CLASSES / 'MeloNXInternalBridgePlugin.swift').read_text()
helper = journal[journal.index('enum MeloNXEngineCallClass {'):journal.index('final class MeloNXPerfJournal {')]
check('thread.name = threadName' in helper and 'thread.qualityOfService = .userInteractive' in helper and
      helper.index('thread.qualityOfService = .userInteractive') < helper.index('thread.start()') and
      'let thread = Thread { while true { ready.wait(); body?(); done.signal() } }' in helper and
      helper.index('body = { result = escapable() }') < helper.index('ready.signal()') < helper.index('done.wait()') < helper.index('body = nil'),
      'the call is handed to a user-interactive thread and waited for')
check('gate.lock(); defer { gate.unlock() }' in helper and 'if Thread.current.name == threadName { return call() }' in helper and
      'pthread_set_qos_class_self_np' not in helper and 'pthread_override_qos_class_start_np' not in helper,
      'one call at a time, a call within a call in place; the queue thread\'s own class is not changed')
check(journal.count('MeloNXEngineCallClass.interactive { fps() }') == 1 and journal.count('MeloNXEngineCallClass.interactive { audio() }') == 2 and
      not re.search(r'(?<!interactive \{ )\b(fps|audio)\(\)(?! \})', journal[journal.index('final class MeloNXPerfJournal {'):journal.index('static func threads()')]),
      'every engine call of the sampler runs under the override')
drain = plugin[plugin.index('private func drainDiagnostics'):plugin.index('// Accessed only on libraryQueue. Success includes')]
check('let report = MeloNXEngineCallClass.interactive { runtime.diagnostics() }' in drain and drain.count('runtime.diagnostics()') == 1 and
      'DispatchQueue(label:"com.neogamelab.neostation.melonx.diagnostics",qos:.utility)' in plugin and
      'timer.schedule(deadline:.now(),repeating:.milliseconds(300))' in plugin, 'the diagnostics drain calls the engine under the override')

# The diagnostics poll (lot 14): MeloNXDiagnosticsReader (in MeloNXRuntimeAPI.swift) reads the engine's report into one
# kept buffer and decodes it only when its bytes differ from the previous read's; the runtime's poll goes through it.
api = (CLASSES / 'MeloNXRuntimeAPI.swift').read_text()
reader = api[api.index('// BEGIN MeloNXDiagnosticsReader'):api.index('// END MeloNXDiagnosticsReader')]
check('func diagnostics() -> [String: Any] { diagnosticsReader.read() }' in api and reader.count('JSONSerialization.jsonObject(') == 1 and
      api.count('[CChar](repeating:0,count:524288)') == 0 and reader.count('[CChar](repeating:0,count:MeloNXDiagnosticsReader.capacity)') == 1 and
      'lock.lock(); defer { lock.unlock() }' in reader and
      reader.index('if length == bytes.count, memcmp(buffer,bytes,length) == 0 { return report }') < reader.index('JSONSerialization.jsonObject(') and
      'bytes = decoded == nil ? [] : Array(buffer[0..<length])' in reader,
      'the diagnostics report is decoded only when its bytes changed, in a kept buffer, under a lock')
# Hot spots (lot 12): "[MeloNX:hot]" profiles asked for by the sampler and taken by a native thread that calls no engine
# closure and suspends nothing; bounded in samples, threads, places and profiles; written through the shared writer.
hot = (CLASSES / 'MeloNXHotSpots.swift').read_text()
check('            stalls.start()\n            breakdown.start()\n            hot.start()\n' in journal and
      '            stalls.stop()\n            breakdown.stop()\n            hot.stop()\n' in journal and journal.count('hot.observe(') == 1 and
      journal.index('fields.append(cpu)') < journal.index('hot.observe(') < journal.index('stalls.enter("memory")'),
      'the profiler starts and stops with the journal and is asked once per line, after the thread shares')
check(all(name not in hot for name in ('fps(', 'audio(', 'memory(', 'presentation(', 'thread_suspend', 'thread_resume', 'task_suspend',
                                       'DispatchQueue.main', 'MeloNXEngineCallClass')), 'the profiler calls no engine closure and suspends nothing')
# Heap sample (lot 13): "[MeloNX:heap]" lines. libmalloc's logging hook for a bounded window at the start of a session;
# the hook allocates nothing, has no thread-local storage, one lock taken for sampled blocks only.
sampler = (CLASSES / 'MeloNXHeapSampler.m').read_text()
sampler_header = (CLASSES / 'MeloNXHeapSampler.h').read_text()
heap = (CLASSES / 'MeloNXHeapSample.swift').read_text()
controller = (CLASSES / 'MeloNXMetalSessionViewController.swift').read_text()
check('#define INTERVAL ((uint64_t)256 << 10)' in sampler and '#define SLOTS (1u << 16)' in sampler and '#define PROBES 16u' in sampler and
      '#define STACKS 4096u' in sampler and '#define MeloNXHeapSamplerFrames 14' in sampler_header, 'sampler bounds')
hook_code = sampler[sampler.index('static inline uint64_t mix('):sampler.index('MELONX_HEAP_SAMPLER_EXPORT int MeloNXHeapSamplerStart(void)')]
check(all(name not in hook_code for name in ('malloc(', 'calloc(', 'realloc(', 'free(', 'printf', 'NSLog', 'os_log', 'dispatch_', '__thread', '_Thread_local',
                                             'pthread_getspecific', 'dladdr', '@')) and
      hook_code.count('os_unfair_lock_lock(&gLock)') == 2 and hook_code.count('os_unfair_lock_unlock(&gLock)') == 2,
      'between the hook and the tables: no allocation, no logging, no thread-local storage, one lock')
check('address < low || address + 16 > high || (address & 7) != 0' in hook_code and 'if (next <= address) break;' in hook_code,
      'frames are read inside the calling thread\'s own stack only')
check('if (*gLogger != NULL) { atomic_store(&gActive, 0); return -1; }' in sampler and 'extern' not in sampler and
      'gLogger = (malloc_logger_t **)dlsym(RTLD_DEFAULT, "malloc_logger");' in sampler and
      sampler.count('*gLogger = hook;') == 1 and '    int ours = gLogger != NULL && *gLogger == hook;\n    if (ours) *gLogger = NULL;\n'
      '    return atomic_exchange(&gActive, 0) && ours ? 1 : 0;' in sampler,
      'the hook is looked up, set only when no other logger owns it, and removed only when it is ours; a window always ends')
check('#define MELONX_HEAP_SAMPLER_EXPORT __attribute__((visibility("default"), used))' in sampler and
      all(('MELONX_HEAP_SAMPLER_EXPORT int MeloNXHeapSampler' + name + '(') in sampler for name in ('Start', 'Stop', 'Report')),
      'the three functions Swift looks up are kept and exported')
HEAP = {name: float(value) for name, value in re.findall(r'static let (windowSeconds|maxStacks|maxPlaces)(?:: \w+)? = ([\d.]+)', heap) +
        re.findall(r'\b(maxPlaces) = ([\d.]+)', heap)}
check(HEAP == dict(windowSeconds=120, maxStacks=24, maxPlaces=10) and 'static let totalsWords = 8, stackWords = 19, frames = 14' in heap,
      'window and report bounds: ' + str(HEAP))
check(heap.count('MeloNXHeapSamplerLink.start()') == 1 and heap.count('MeloNXHeapSamplerLink.stop()') == 1 and
      'queue.asyncAfter(deadline:.now() + seconds) { [self] in if open && window == mine { finish("window") } }' in heap and
      'func end() { queue.async { [self] in if open { finish("sessionEnd") } } }' in heap and
      heap.index('MeloNXHeapSamplerLink.stop()') < heap.index('Self.write(Self.lines(reason:reason, seconds:seconds)'),
      'one window: closed by its timer or by the end of the session, the hook removed before the report')
check(heap.count('MeloNXStdioCapture.appendLine(') == 1 and 'to:path, limit:MeloNXPerfJournal.fileLimit)' in heap and 'open(' not in heap,
      'heap lines written through the shared writer')
check(controller.index('MeloNXStdioCapture.begin()\n') < controller.index('MeloNXHeapSample.shared.begin(path:MeloNXStdioCapture.journalPath,context:MeloNXStdioCapture.sessionContext)')
      < controller.index('try host.start(game:game,locale:locale,') and controller.count('MeloNXHeapSample.shared.end()') == 2 and
      controller.count('MeloNXHeapSample.shared.begin(') == 1, 'the window opens before the engine is launched and ends with the session, failed launch included')

HOT = {name: float(value) for name, value in re.findall(r'\b(rounds|maxThreads|maxFrames|maxSlow|maxBase|minSecond|gapSeconds|streak|slowBelow|baseFrom|'
                                                         r'selfPlaces|stackPlaces|waitPlaces) = ([\d.]+)', hot)}
check(HOT == dict(rounds=300, maxThreads=6, maxFrames=6, maxSlow=4, maxBase=2, minSecond=40, gapSeconds=20, streak=3, slowBelow=26, baseFrom=28.5,
                  selfPlaces=32, stackPlaces=48, waitPlaces=12) and 'static let periodMicroseconds: UInt32 = 10_000' in hot and
      'static let selfBlockBytes: UInt64 = 64' in hot, 'profile bounds: ' + str(HOT))
check(hot.count('MeloNXStdioCapture.appendLine(') == 1 and 'to:path, limit:MeloNXPerfJournal.fileLimit)' in hot and 'open(' not in hot and
      'index == 0 ? MeloNXStdioCapture.contextualLine(text, context:context) : text' in hot, 'profiles written through the shared writer, the header with the context')
check(hot.count('mach_port_deallocate(mach_task_self_, list[index])') == 1 and hot.count('vm_deallocate(mach_task_self_') == 1 and
      'thread_get_state(thread, thread_state_flavor_t(ARM_THREAD_STATE64)' in hot and 'MeloNXStallWatch.frames(from:registers.fp, limit:maxFrames)' in hot and
      hot.index('let took = ') < hot.index('func name(_ address: UInt64) -> String'),
      'thread ports released; registers read without suspension; places named after the sampling')
check('static func frames(from start: UInt64, limit: Int = maxFrames) -> [UInt64]' in journal and
      'static func place(_ raw: UInt64, _ cache: inout [UInt64: String]) -> String' in journal, 'the stall watch\'s readers are shared with the profiler')


def hot_decisions(lines):
    """The profiler's decision rule, from its constants: [(kind, second)] for (second, fps, paused) lines."""
    slow = base = slow_done = base_done = 0
    last, out = -1000, []
    for second, fps, paused in lines:
        if paused or fps <= 0 or second < HOT['minSecond']:
            slow = base = 0
            continue
        slow = slow + 1 if fps < HOT['slowBelow'] else 0
        base = base + 1 if fps >= HOT['baseFrom'] else 0
        if second - last < HOT['gapSeconds']:
            continue
        kind = 'slow' if slow >= HOT['streak'] and slow_done < HOT['maxSlow'] else 'base' if base >= HOT['streak'] and base_done < HOT['maxBase'] else None
        if kind:
            out.append(f'{kind}@{second}')
            slow_done, base_done = slow_done + (kind == 'slow'), base_done + (kind == 'base')
            last, slow, base = second, 0, 0
    return out


HOT_LINES = ([(second, 20.0, False) for second in range(30, 60)] + [(second, 30.0, False) for second in range(60, 66)] +
             [(66, 20.0, False), (67, 20.0, True), (68, 20.0, False), (69, 20.0, False)] +
             [(second, 20.0 if second % 50 < 25 else 30.0, False) for second in range(70, 200)] +
             [(second, 20.0, False) for second in range(200, 400)] + [(second, 0.0 if second % 7 == 0 else 30.0, False) for second in range(400, 500)])
expected_decisions = hot_decisions(HOT_LINES)
check(expected_decisions[:2] == ['slow@42', 'base@62'] and sum(d.startswith('slow') for d in expected_decisions) == 4 and
      sum(d.startswith('base') for d in expected_decisions) == 2, 'the rule on the scripted session: ' + ','.join(expected_decisions))

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
// en= and sw= fields: 3 J of 4.5 J on performance cores in 1.5 s; no energy counted; counters that went backwards or wrapped.
var powerBefore = hwBefore, powerNow = hwBefore
powerBefore.energy = 1_000_000_000; powerBefore.performanceEnergy = 500_000_000; powerBefore.wakeups = 100
powerBefore.switches = 4_294_967_000; powerBefore.calls = 1_000; powerBefore.events = true
powerNow.energy = 5_500_000_000; powerNow.performanceEnergy = 3_500_000_000; powerNow.wakeups = 1_600
powerNow.switches = 2_704; powerNow.calls = 46_000; powerNow.events = true
func power(_ now: MeloNXPerfJournal.HwCounters, _ seconds: Double) -> String {
    (MeloNXPerfJournal.energyField(from:powerBefore, to:now, seconds:seconds) ?? "nil") + " " + (MeloNXPerfJournal.switchField(from:powerBefore, to:now, seconds:seconds) ?? "nil")
}
print("power " + power(powerNow, 1.5))
var powerBack = powerNow; powerBack.performanceEnergy = 1; powerBack.wakeups = 1
print("power " + power(powerBack, 1.5))
var powerNone = powerNow; powerNone.energy = 0; powerNone.events = false
print("power " + power(powerNone, 1.5))
print("power " + power(powerNow, 0))
print("powerLive " + (hwNow.events ? "events" : "noEvents") + " " + (hwNow.switches > 0 ? "switches" : "noSwitches"))
// pc= field: the share is formatted from two samples; no CPU time or a counter that went backwards gives "-". The
// per-level counts of the busy thread are read when the host has them (a virtual machine may not).
func share(_ now: MeloNXPerfJournal.LevelTimes) -> String { MeloNXPerfJournal.performanceShare(from:MeloNXPerfJournal.LevelTimes(performance:100, total:200), to:now) }
print("pcShare " + share(MeloNXPerfJournal.LevelTimes(performance:400, total:600)))
print("pcShare " + share(MeloNXPerfJournal.LevelTimes(performance:100, total:200)))
print("pcShare " + share(MeloNXPerfJournal.LevelTimes(performance:50, total:600)))
if let levels = MeloNXPerfJournal.levelTimes(thread:worker.id) { print("pcLevels " + (levels.performance <= levels.total && levels.total > 0 ? "plausible" : "implausible")) }
else { print("pcLevels unavailable") }
// Engine-call class: from a utility queue's thread the call is made by the dedicated thread, whose requested class is
// user-interactive (a call within a call too), and the queue's thread keeps its own class, between and after the calls.
// The scheduled priority depends on the host (a build machine may clamp the whole process): the dedicated thread's is
// compared with that of a reference thread created in the user-interactive class here.
var referenceBase: Int32 = -1
let referenceDone = DispatchSemaphore(value:0)
let reference = Thread { referenceBase = MeloNXPerfJournal.currentPriorities()?.base ?? -1; referenceDone.signal() }
reference.qualityOfService = .userInteractive
reference.start()
referenceDone.wait()
let classDone = DispatchSemaphore(value:0)
var classLine = "engineClass unavailable"
DispatchQueue(label:"Perf.Utility", qos:.utility).async {
    let before = qos_class_self().rawValue, beforeBase = MeloNXPerfJournal.currentPriorities()?.base ?? -1
    let (inside, insideBase, value, thread) = MeloNXEngineCallClass.interactive {
        (qos_class_self().rawValue, MeloNXPerfJournal.currentPriorities()?.base ?? -1, 42, Thread.current.name ?? "") }
    let nested = MeloNXEngineCallClass.interactive { MeloNXEngineCallClass.interactive { qos_class_self().rawValue } }
    let between = qos_class_self().rawValue
    var sum = 0
    for index in 0..<200 { sum += MeloNXEngineCallClass.interactive { index } }
    let after = qos_class_self().rawValue
    classLine = "engineClass \(before) \(inside) \(nested) \(between) \(after) \(value) \(sum) \(thread) \(beforeBase) \(insideBase) \(referenceBase)"
    classDone.signal()
}
classDone.wait()
print(classLine)
// Hot spots: the decision per line, on the scripted session the test also runs through its own copy of the rule.
var slowStreak = 0, baseStreak = 0, slowDone = 0, baseDone = 0, lastHot = -1_000
var decisions: [String] = []
func hotLine(_ second: Int, _ fps: Double, _ paused: Bool = false) {
    guard let kind = MeloNXHotSpots.decide(second:second, fps:fps, paused:paused, slowStreak:&slowStreak, baseStreak:&baseStreak,
                                           slowDone:slowDone, baseDone:baseDone, lastSecond:lastHot) else { return }
    decisions.append("\(kind)@\(second)")
    if kind == "slow" { slowDone += 1 } else { baseDone += 1 }
    lastHot = second; slowStreak = 0; baseStreak = 0
}
for second in 30..<60 { hotLine(second, 20) }
for second in 60..<66 { hotLine(second, 30) }
hotLine(66, 20); hotLine(67, 20, true); hotLine(68, 20); hotLine(69, 20)
for second in 70..<200 { hotLine(second, second % 50 < 25 ? 20 : 30) }
for second in 200..<400 { hotLine(second, 20) }
for second in 400..<500 { hotLine(second, second % 7 == 0 ? 0 : 30) }
print("hotDecide " + decisions.joined(separator:","))
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
                        str(CLASSES / 'MeloNXPerfJournal.swift'), str(CLASSES / 'MeloNXHotSpots.swift'), str(work / 'main.swift'), '-o', str(executable)], check=True)
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
        check(' vm=' not in samples[0] and all(re.search(r' vm=\d+/\d+/\d+/\d+ (hw=\S+ )?(en=\S+ )?(sw=\S+ )?(pc=\S+ )?(in=\S+ )?th=', line) for line in samples[1:]), samples)
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
        # en= (watts, all cores / performance cores) only where the host counts energy; sw= (context switches, system
        # calls and interrupt wakeups per second) on every line after the first.
        check(' en=' not in samples[0] and ' sw=' not in samples[0] and
              all(re.search(r' sw=\d+/\d+/(\d+|-) ', line) for line in samples[1:]) and
              all(re.search(r' en=\d+\.\d\d/(\d+\.\d\d|-) ', line) for line in samples[1:] if ' en=' in line), samples)
        print('en= on the runner: ' + str(sum(' en=' in line for line in samples[1:])) + ' of ' + str(len(samples) - 1) + ' lines; ' +
              str([re.search(r' (en=\S+ )?sw=\S+', line).group(0).strip() for line in samples[1:3]]), flush=True)
        check([line for line in result.stdout.splitlines() if line.startswith('power')] ==
              ['power 3.00/2.00 2000/30000/1000', 'power 3.00/- 2000/30000/-', 'power nil nil', 'power nil nil', 'powerLive events switches'],
              [line for line in result.stdout.splitlines() if line.startswith('power')])
        check([line for line in result.stdout.splitlines() if line.startswith('hwField ')] ==
              ['hwField 3.2/2.00/75/25/4.0/0.8', 'hwField 0.0/-/-/0/-/-', 'hwField 2.0/1.00/100/200/2.0/-', 'hwField 3.2/2.00/75/-/-/-',
               'hwField nil', 'hwField nil'] and 'timeUnit positive' in result.stdout.splitlines(), result.stdout)
        check([line for line in result.stdout.splitlines() if line.startswith('vmField ')] == ['vmField 32/250/900/0', 'vmField -/-/1000/1'],
              result.stdout)
        check([line for line in result.stdout.splitlines() if line.startswith('hotDecide ')] == ['hotDecide ' + ','.join(expected_decisions)],
              'the profiler decides as the rule: ' + result.stdout)
        # Engine-call class (requested classes: 0x21 user-interactive, 0x11 utility): the call made from a utility queue's
        # thread runs on the dedicated thread, in the user-interactive class, a call within a call too; the queue's thread
        # is in its own class before, between and after; the calls' values are returned (200 in a row). The dedicated
        # thread is scheduled as a reference user-interactive thread of the same process is (on a host that clamps the
        # process both read the clamp: macOS runs 42991898055 and 42993028058 read 20 for every thread), and above the
        # queue's thread wherever the reference is.
        engine_class = [line.split(' ')[1:] for line in result.stdout.splitlines() if line.startswith('engineClass ')]
        check(len(engine_class) == 1 and len(engine_class[0]) == 11, result.stdout)
        before, inside, nested, between, after = map(int, engine_class[0][:5])
        before_base, inside_base, reference_base = map(int, engine_class[0][8:])
        print('engine call priorities (queue thread, dedicated thread, reference user-interactive thread):', before_base, inside_base, reference_base, flush=True)
        check(before == 0x11 and inside == 0x21 and nested == 0x21 and between == 0x11 and after == 0x11 and
              engine_class[0][5:8] == ['42', str(sum(range(200))), 'RewindBox.MeloNX.EngineCalls'],
              'engine call class from a utility queue: ' + ' '.join(engine_class[0]))
        check(inside_base == reference_base and reference_base > 0 and (reference_base <= before_base or inside_base > before_base),
              'the dedicated thread is scheduled as a user-interactive thread of this process: ' + ' '.join(engine_class[0]))
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
// Hot spots: one profile of the spinner, of the waiter and of a thread that does not exist.
let known = MeloNXPerfJournal.threads()
func hotTarget(_ name: String) -> MeloNXHotSpots.Target {
    guard let thread = known.first(where: { $0.name == name }) else { print("no thread", name); exit(7) }
    return MeloNXHotSpots.Target(id:thread.id, name:thread.name, priority:thread.priority)
}
let profile = MeloNXHotSpots.profile(MeloNXHotSpots.Request(number:1, kind:"slow", second:42, fps:19.5,
    targets:[hotTarget("Stall_Spinner"), hotTarget("Stall_Waiter"), MeloNXHotSpots.Target(id:0xFFFF_FFFF_FFFF, name:"gone", priority:31)]),
    rounds:80, periodMicroseconds:5_000)
for line in profile { print("HOT " + line) }
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
                        str(CLASSES / 'MeloNXPerfJournal.swift'), str(CLASSES / 'MeloNXHotSpots.swift'), str(work / 'stall' / 'main.swift'), '-o', str(stall_executable)], check=True)
        result = subprocess.run([str(stall_executable), str(stall_log)], capture_output=True, text=True, timeout=120)
        check(result.returncode == 0, result)
        stall_lines = [line.removeprefix('[MeloNX:stall] ') for line in stall_log.read_text().splitlines() if line.startswith('[MeloNX:stall] ')]
        headers = [line for line in stall_lines if re.match(r'#\d+\.\d+ \w+ in flight \d+ ms, \d+ threads', line)]
        check([h.split(' ')[0] for h in headers] == ['#1.0', '#1.1', '#2.0', '#3.0', '#4.0', '#5.0', '#6.0'], headers)
        ends = [line for line in stall_lines if re.match(r'#\d+ end: fps returned after', line)]
        check([e.split(' ')[0] for e in ends] == ['#1', '#2', '#3', '#4', '#5', '#6'], ends)
        first = float(re.search(r'after ([\d.]+) ms', ends[0]).group(1))
        later = [float(re.search(r'after ([\d.]+) ms', e).group(1)) for e in ends[1:]]
        # The lower bounds are the stages (300 and 1300 ms) and the scripted sleeps (1.6 s, then 0.5 s), which usleep
        # never shortens. A loaded shared runner wakes the watch and the sleepers late, so no fixed upper bound is asked
        # (600, 1600, 1900 and 900 ms were): the two records come in order while the first call is in flight (each at
        # most the call's own measured duration, the end's clock read coming after the record's), and each 0.5 s stall
        # ends shorter than the 1.6 s one.
        flight0 = int(re.search(r'in flight (\d+) ms', headers[0]).group(1))
        flight1 = int(re.search(r'in flight (\d+) ms', headers[1]).group(1))
        check(300 <= flight0 < flight1 and 1300 <= flight1 <= first, (headers[:2], ends[:1]))
        check(first >= 1590 and all(490 <= value < first for value in later), ends)
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
        # Hot spots: the spinner is found running, in the program's own code; the waiter waiting, under libdispatch;
        # a thread that does not exist is only missed; every list is bounded.
        hot_lines = [line.removeprefix('HOT ') for line in result.stdout.splitlines() if line.startswith('HOT ')]
        print('\n'.join(line[:700] for line in hot_lines), flush=True)
        check(len(hot_lines) == 4 and re.fullmatch(r'#1 slow t=42 fps=19\.5 80 samples in \d+ ms, 3 threads', hot_lines[0]), hot_lines[:1])
        rows = {}
        for line in hot_lines[1:]:
            row = re.fullmatch(r'#1 (\S+) p(\d+) run=(\d+) wait=(\d+) missed=(\d+) self=(\S+) stack=(\S+) waiting=(\S+)', line)
            check(row is not None, line)
            rows[row.group(1)] = dict(run=int(row.group(3)), wait=int(row.group(4)), missed=int(row.group(5)),
                                      **{key: [] if row.group(index) == '-' else [(entry.rsplit(':', 1)[0], int(entry.rsplit(':', 1)[1])) for entry in row.group(index).split(',')]
                                         for key, index in (('own', 6), ('stack', 7), ('waiting', 8))})
        spinner_row, waiter_row, gone = rows['Stall_Spinner'], rows['Stall_Waiter'], rows['gone']
        # The spinner (an unoptimised loop that calls into the Swift runtime): found running; its samples are under a
        # call site of the program (the thread's closure), whatever library the program counter is in (macOS run
        # 42994146430: 68 of 80 under stall+0xdd4c, the program counters spread over libswiftCore).
        check(spinner_row['run'] >= 60 and spinner_row['missed'] == 0 and spinner_row['run'] + spinner_row['wait'] == 80 and
              max(count for place, count in spinner_row['stack'] if place.startswith('stall+0x')) >= spinner_row['run'] // 2 and
              sum(count for _, count in spinner_row['own']) <= spinner_row['run'] and
              all(count <= spinner_row['run'] for _, count in spinner_row['stack']),
              'the spinner: running, under the program\'s own call site: ' + hot_lines[1][:600])
        check(waiter_row['wait'] >= 70 and waiter_row['missed'] == 0 and any(place.startswith('libdispatch.dylib+0x') for place, _ in waiter_row['waiting']) and
              not any(place.startswith(('libsystem_kernel.dylib+', 'libsystem_pthread.dylib+')) for place, _ in waiter_row['waiting']) and
              all(count <= waiter_row['wait'] for _, count in waiter_row['waiting']), 'the waiter: waiting under libdispatch: ' + hot_lines[2][:600])
        check(gone == dict(run=0, wait=0, missed=80, own=[], stack=[], waiting=[]), 'a thread that does not exist: ' + hot_lines[3])
        check(all(len(row['own']) <= 32 and len(row['stack']) <= 48 and len(row['waiting']) <= 12 for row in rows.values()) and
              all(len(line) < 6144 for line in hot_lines), 'bounded lists')

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
                        str(CLASSES / 'MeloNXPerfJournal.swift'), str(CLASSES / 'MeloNXHotSpots.swift'), str(work / 'memory' / 'main.swift'), '-o', str(memory_executable)], check=True)
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

        # Heap sample: the real hook under the system's allocator. 64 blocks of 1 MiB of which 32 are freed and one
        # grown to 3 MiB, 100 000 blocks of 2 KiB kept, and four threads allocating and freeing.
        heap_log = work / 'heap.log'
        (work / 'heap').mkdir()
        (work / 'heap' / 'main.swift').write_text(r'''import Foundation
import Darwin
let path = CommandLine.arguments[1]
let bigCount = 64, smallCount = 100_000
let big = UnsafeMutablePointer<UnsafeMutableRawPointer?>.allocate(capacity:bigCount)
let small = UnsafeMutablePointer<UnsafeMutableRawPointer?>.allocate(capacity:smallCount)
@inline(never) func keepBig() { for index in 0..<bigCount { big[index] = malloc(1 << 20) } }
@inline(never) func keepSmall() { for index in 0..<smallCount { small[index] = malloc(2048) } }
@inline(never) func churn(_ rounds: Int, _ size: Int) {
    for _ in 0..<rounds { let block = malloc(size)!; block.storeBytes(of:1, as:UInt8.self); free(block) }
}
@inline(never) func grow() { big[bigCount - 1] = realloc(big[bigCount - 1], 3 << 20) }
func logger() -> UnsafeRawPointer? {
    dlsym(UnsafeMutableRawPointer(bitPattern:-2), "malloc_logger")!.assumingMemoryBound(to:UnsafeRawPointer?.self).pointee
}
// The cost of the hook: nanoseconds per malloc and free of 64 bytes, without it and with it.
@inline(never) func pairs(_ rounds: Int) -> Double {
    let begin = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<rounds { let block = malloc(64)!; block.storeBytes(of:1, as:UInt8.self); free(block) }
    return Double(DispatchTime.now().uptimeNanoseconds - begin) / Double(rounds)
}
_ = pairs(200_000)
let plain = pairs(2_000_000)
print("LOGGER before \(logger() == nil)")
print("START \(MeloNXHeapSamplerLink.start()) \(MeloNXHeapSamplerLink.start())")
print("LOGGER set \(logger() != nil)")
print(String(format:"PAIRS %.1f %.1f", plain, pairs(2_000_000)))
keepBig()
keepSmall()
let threads = (0..<4).map { index -> Thread in
    let thread = Thread { churn(200_000, 3000 + index * 512) }
    thread.name = "Churn_\(index)"; thread.start(); return thread
}
churn(200_000, 5000)
while threads.contains(where: { !$0.isFinished }) { usleep(10_000) }
for index in 0..<32 { free(big[index]) }
grow()
print("STOP \(MeloNXHeapSamplerLink.stop()) \(MeloNXHeapSamplerLink.stop())")
print("LOGGER after \(logger() == nil)")
for line in MeloNXHeapSample.lines(reason:"test", seconds:3) { print("HEAP " + line) }
// The scheduled window, then one ended by the session; a begin while a window is open joins it.
MeloNXHeapSample.shared.begin(path:path, context:["session":"s1"], seconds:0.5)
MeloNXHeapSample.shared.begin(path:path, context:["session":"joined"], seconds:0.1)
print("LOGGER window \(logger() != nil)")
let held = malloc(8 << 20)
usleep(1_500_000)
print("LOGGER closed \(logger() == nil)")
MeloNXHeapSample.shared.begin(path:path, context:["session":"s2"], seconds:60)
usleep(200_000)
MeloNXHeapSample.shared.end()
MeloNXHeapSample.shared.end()
usleep(500_000)
print("LOGGER ended \(logger() == nil)")
free(held)
exit(0)
''')
        sampler_object = work / 'heap' / 'sampler.o'
        subprocess.run(['xcrun', 'clang', '-c', '-O1', '-Wall', '-Wextra', '-Werror', str(CLASSES / 'MeloNXHeapSampler.m'), '-o', str(sampler_object)], check=True)
        heap_executable = work / 'heap' / 'heap'
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(CLASSES / 'MeloNXStandaloneParity.swift'),
                        str(CLASSES / 'MeloNXPerfJournal.swift'), str(CLASSES / 'MeloNXHotSpots.swift'), str(CLASSES / 'MeloNXHeapSample.swift'),
                        str(work / 'heap' / 'main.swift'), str(sampler_object), '-Xlinker', '-export_dynamic', '-o', str(heap_executable)], check=True)
        result = subprocess.run([str(heap_executable), str(heap_log)], capture_output=True, text=True, timeout=300)
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, result)
        out = result.stdout.splitlines()
        check('LOGGER before true' in out and 'START 1 0' in out and 'LOGGER set true' in out and 'STOP 1 0' in out and 'LOGGER after true' in out,
              'the hook is set once and removed: ' + str([l for l in out if not l.startswith('HEAP ')]))
        plain_ns, hooked_ns = map(float, next(l for l in out if l.startswith('PAIRS ')).split(' ')[1:])
        print(f'malloc and free of 64 bytes: {plain_ns} ns without the hook, {hooked_ns} ns with it', flush=True)
        check(0 < plain_ns and hooked_ns - plain_ns < 1000, 'the hook costs well under a microsecond per malloc and free')
        heap_lines = [l.removeprefix('HEAP ') for l in out if l.startswith('HEAP ')]
        head = re.match(r'window 3 s \(test\): live (\d+) MiB in (\d+) samples, allocated (\d+) MiB in (\d+), interval 256 KiB, (\d+) stacks, '
                        r'(\d+) dropped, (\d+) unwalked; zones=\S+$', heap_lines[0])
        check(head, heap_lines[0])
        live, live_samples, total, total_samples, stack_count, dropped, unwalked = map(int, head.groups())
        # nm: the test's own functions by address, to name the first place of each stack.
        table = sorted((int(parts[0], 16), parts[2]) for parts in
                       (l.split(' ', 2) for l in subprocess.run(['xcrun', 'nm', '-n', str(heap_executable)], capture_output=True, text=True, check=True).stdout.splitlines())
                       if len(parts) == 3 and parts[0] and parts[1] in ('t', 'T'))
        base = next(address for address, name in table if name == '__mh_execute_header') if any(name == '__mh_execute_header' for _, name in table) else 0x100000000

        def function(place):
            if not place.startswith('heap+0x'):
                return place.split('+0x')[0]
            address = base + int(place.split('+0x')[1], 16)
            name = None
            for start, symbol in table:
                if start > address:
                    break
                name = symbol
            return next((short for short in ('keepBig', 'keepSmall', 'churn', 'grow') if name and short in name), name or place)

        stacks = []
        for l in heap_lines[1:]:
            m = re.match(r'#(\d+) live=(\d+)/(\d+) total=(\d+)/(\d+) stack=(\S+)$', l)
            check(m, l)
            places = m.group(6).split('<')
            stacks.append(dict(live=int(m.group(2)), liveSamples=int(m.group(3)), total=int(m.group(4)), totalSamples=int(m.group(5)),
                               first=function(places[0]), places=places))
        print([(s['first'], s['live'], s['total']) for s in stacks], flush=True)
        check(1 <= len(stacks) <= 24 and stacks == sorted(stacks, key=lambda s: -s['live']) and
              all(len(s['places']) <= 10 and not s['places'][0].startswith('libsystem_malloc.dylib+') for s in stacks),
              'at most 24 stacks, most live bytes first, each starting at the caller of the allocator')
        bigs = [s for s in stacks if s['first'] == 'keepBig']
        check(len(bigs) == 1 and bigs[0]['live'] == 31 and bigs[0]['liveSamples'] == 31 and bigs[0]['total'] == 64 and bigs[0]['totalSamples'] == 64,
              'blocks of the interval or more are counted exactly: 64 allocated, 32 freed, one moved: ' + str(bigs))
        grown = [s for s in stacks if s['first'] == 'grow']
        check(len(grown) == 1 and grown[0]['live'] == 3 and grown[0]['liveSamples'] == 1, 'a realloc is a free and an allocation: ' + str(grown))
        smalls = [s for s in stacks if s['first'] == 'keepSmall']
        kept = 100_000 * 2048 / (1 << 20)
        check(len(smalls) == 1 and abs(smalls[0]['live'] - kept) <= 0.15 * kept and smalls[0]['total'] == smalls[0]['live'] and
              abs(smalls[0]['liveSamples'] * 256 / 1024 - smalls[0]['live']) <= 1,
              'small blocks are estimated from one sample per 256 KiB: %.1f MiB kept, %s' % (kept, smalls))
        churned = [s for s in stacks if s['first'] == 'churn']
        churn_bytes = sum(200_000 * (3000 + index * 512) for index in range(4)) + 200_000 * 5000
        check(churned and sum(s['live'] for s in churned) <= 2 and
              abs(sum(s['total'] for s in churned) - churn_bytes / (1 << 20)) <= 0.2 * churn_bytes / (1 << 20),
              'freed blocks leave the live count and stay in the allocated one: %.0f MiB churned, %s' % (churn_bytes / (1 << 20), churned))
        check(dropped == 0 and unwalked == 0 and abs(live - (31 + 3 + kept)) <= 0.15 * kept + 8 and stack_count >= 4 and live_samples < total_samples,
              'totals: ' + heap_lines[0])
        check('LOGGER window true' in out and 'LOGGER closed true' in out and 'LOGGER ended true' in out, 'windows set and remove the hook')
        written = [l for l in heap_log.read_text().splitlines() if l.startswith('[MeloNX:heap] ')]
        headers = [l for l in written if l.startswith('[MeloNX:heap] window ')]
        check(len(headers) == 2 and re.match(r'\[MeloNX:heap\] window [01] s \(window\): live \d+ MiB', headers[0]) and '"session":"s1"' in headers[0] and
              '"pid":"' in headers[0] and re.match(r'\[MeloNX:heap\] window 0 s \(sessionEnd\): ', headers[1]) and '"session":"s2"' in headers[1] and
              not any('joined' in l for l in written) and len(written) <= 50,
              'a window closed by its timer, one by the end of the session, a begin inside a window joins it: ' + str(headers))
        first_window = written[written.index(headers[0]) + 1:written.index(headers[1])]
        check(any(re.match(r'\[MeloNX:heap\] #\d+ live=8/1 total=8/1 stack=heap\+0x', l) for l in first_window),
              'the 8 MiB block held through the window is in its report: ' + str(first_window[:4]))

        # Diagnostics reader: the block of MeloNXRuntimeAPI.swift compiled alone, fed by a scripted engine. Every report
        # that changes between two reads is decoded exactly once; an unchanged one is not decoded; a report that does not
        # decode is decoded again; a refusal gives an empty answer. Then the CPU of 1 000 polls of a 24 KiB report, quiet,
        # with the reader and with the poll as it was before lot 14 (a 512 KiB array zeroed, scanned and decoded).
        (work / 'reader').mkdir()
        (work / 'reader' / 'Reader.swift').write_text('import Foundation\n' + reader)
        (work / 'reader' / 'main.swift').write_text(r"""import Foundation
var current = ""
var status: Int32 = 0
let engine: (UnsafeMutablePointer<CChar>, Int32) -> Int32 = { buffer, capacity in
    if status != 0 { return status }
    let utf8 = Array(current.utf8CString)
    guard utf8.count <= Int(capacity) else { return -Int32(utf8.count) }
    utf8.withUnsafeBufferPointer { buffer.update(from:$0.baseAddress!, count:utf8.count) }
    return 0
}
let reader = MeloNXDiagnosticsReader(engine)
var lines: [String] = []
func step(_ name: String, _ text: String?, refuse: Int32 = 0) {
    if let text { current = text }
    status = refuse
    let before = reader.decodes
    let report = reader.read()
    lines.append("\(name) \(reader.decodes - before) \((report["sequence"] as? NSNumber)?.intValue ?? -1)")
}
step("first", #"{"sequence":1,"events":[]}"#)
step("same", nil)
step("same", nil)
step("changed", #"{"sequence":2,"events":[]}"#)
step("sameLengthOtherByte", #"{"sequence":3,"events":[]}"#)
step("shorter", #"{"sequence":4}"#)
step("longer", #"{"sequence":5,"events":[{"stage":"gpu"}]}"#)
step("broken", #"{"sequence":6,"events":["#)
step("brokenAgain", nil)
step("fixed", #"{"sequence":7}"#)
step("refused", nil, refuse: -1)
step("afterRefusal", nil)
step("backToOld", #"{"sequence":1,"events":[]}"#)
for line in lines { print("READER " + line) }
// The CPU of polls of an unchanged 24 KiB report.
let events = (0..<64).map { #"{"sequence":\#($0),"stage":"gpu","status":"engineWarning","diagnostic":"\#(String(repeating:"x", count:340))"}"# }
current = #"{"sequence":64,"events":["# + events.joined(separator:",") + "]}"
status = 0
func cpu() -> Double { var usage = rusage(); getrusage(RUSAGE_SELF, &usage); return Double(usage.ru_utime.tv_sec + usage.ru_stime.tv_sec) * 1e6 + Double(usage.ru_utime.tv_usec + usage.ru_stime.tv_usec) }
_ = reader.read()
var start = cpu()
for _ in 0..<1000 { _ = reader.read() }
let kept = (cpu() - start) / 1000
start = cpu()
for _ in 0..<1000 {
    var output = [CChar](repeating:0,count:524288)
    guard engine(&output,Int32(output.count)) == 0 else { break }
    let data = Data(bytes:output,count:output.prefix { $0 != 0 }.count)
    _ = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
}
let previous = (cpu() - start) / 1000
print(String(format:"READERCPU %.1f %.1f %d", kept, previous, current.utf8.count))
""")
        reader_executable = work / 'reader' / 'reader'
        subprocess.run(['xcrun', 'swiftc', '-O', '-swift-version', '5', str(work / 'reader' / 'Reader.swift'), str(work / 'reader' / 'main.swift'),
                        '-o', str(reader_executable)], check=True)
        result = subprocess.run([str(reader_executable)], capture_output=True, text=True, timeout=300)
        check(result.returncode == 0, result)
        steps = [line.removeprefix('READER ') for line in result.stdout.splitlines() if line.startswith('READER ')]
        check(steps == ['first 1 1', 'same 0 1', 'same 0 1', 'changed 1 2', 'sameLengthOtherByte 1 3', 'shorter 1 4', 'longer 1 5',
                        'broken 1 -1', 'brokenAgain 1 -1', 'fixed 1 7', 'refused 0 -1', 'afterRefusal 0 7', 'backToOld 1 1'],
              'every changed report is decoded once, an unchanged one never, a broken one again: ' + str(steps))
        kept_us, previous_us, size = next(line for line in result.stdout.splitlines() if line.startswith('READERCPU ')).split(' ')[1:]
        print(f'diagnostics poll of an unchanged {size}-byte report: {kept_us} us of CPU with the kept buffer, {previous_us} us as before lot 14', flush=True)
        check(float(kept_us) * 4 < float(previous_us), 'an unchanged report costs much less than the poll before lot 14')
    print('Executed the performance journal on macOS.')

print(f'PASS {checks} performance journal checks')
