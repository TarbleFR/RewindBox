#!/usr/bin/env python3
"""Per-second MeloNX performance journal ("[MeloNX:perf]" lines in app.log).

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
check('static func appendLine(_ text: String, to path: String, limit: Int64 = 5 * 1024 * 1024) -> Bool' in parity and 'appendLine("[MeloNX:stderr] " + safe, to:path)' in parity, 'shared writer')
check(journal.count('MeloNXStdioCapture.appendLine(') == journal.count(', to:path, limit:Self.fileLimit)') == 4 and 'open(' not in journal, 'journal writes outside the shared writer or under the general cap')
check('static let fileLimit: Int64 = 8 * 1024 * 1024' in journal and 'if !isPaused && rate > 0 {' in journal, 'journal cap or FPS average')
check('qos:.utility' in journal and 'func stop() {\n        queue.async' in journal, 'sampler priority or synchronous stop')
check('mach_port_deallocate(mach_task_self_, list[index])' in journal and 'vm_deallocate(mach_task_self_' in journal, 'thread ports leak')

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
let journal = MeloNXPerfJournal(path:path, interval:0.25, lineLimit:6,
    fps:{ ["gameFps":59.5,"gameFrameTimeMs":16.8,"fifoPercent":40.0] },
    presentation:{
        calls += 1
        return MeloNXPerfJournal.Presentation(frames:UInt64(calls * 60), maxGapMs:34.5, over20:UInt64(calls * 2), over40:0)
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
            check('dsp=200/3/7.5/3.1/1' in fields and 'out=200/1/12.0/12.0' in fields, line)
            check(re.search(r' th=(nominal|fair|serious|critical) lp=[01]( paused)?$', line), line)
            worker = re.search(r' Perf_Busy_Worker_1:(\d+)/(\d+)', line)
            check(worker and int(worker.group(1)) >= 40, line)
            check(int(re.search(r' cpu=(\d+)', line).group(1)) >= int(worker.group(1)), line)
            check(len(re.findall(r' \S+:\d+/\d+', line)) <= 6, line)
        check('paused' not in samples[0] and 'paused' in samples[-1], samples)
        total = int(re.search(r'^end: (\d+) s sampled, 6 lines;', body[-1]).group(1))
        check(total >= 9, body[-1])
        check(f'{total * 60} frames presented, {total * 2} gaps over 20 ms, 0 over 40 ms' in body[-1], body[-1])
        check(f'{total * 3} late DSP episodes ({total * 7.5:.1f} ms), {total} skipped' in body[-1], body[-1])
        check(f'{total} audio starvations ({total * 12:.1f} ms)' in body[-1] and 'game FPS 59.5 on average' in body[-1], body[-1])
    print('Executed the performance journal on macOS.')

print(f'PASS {checks} performance journal checks')
