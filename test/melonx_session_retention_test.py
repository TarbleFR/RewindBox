#!/usr/bin/env python3
"""A closed session no longer held by the statistics timer or the process-wide time and Bluetooth statics
(adapt_session_retention).

Usage: melonx_session_retention_test.py <Core 658 prepared MeloNX tree>
       melonx_session_retention_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the Core 658 preparation and builds the production Ryujinx.Library (with Ryujinx.HLE).
Static checks bind that every file equals the preparation once the adapter's replacements are undone (nothing else
changes), that the statistics timer is disposed by Switch.Dispose right after Horizon, that the time and Bluetooth
releases run in Horizon.Dispose after every process is terminated and joined and after KernelContext.Dispose, that each
release is identity-checked (only the closing session's device, kernel events and handles), and that the probe adds no
collection, keeps its statuses and touches no session state. In the preparation it binds the mechanism: a timer started
in the constructor that nothing stops, a Switch.Dispose that does not touch it, a singleton initialised by every Horizon
and never released.

Behaviour (test/melonx_session_retention/Program.cs), control and candidate: the REAL PerformanceStatistics.cs,
PerformanceCounter.cs, time service (TimeManager, TimeSharedMemory, Clock/, Types/), BluetoothEventManager.cs,
KEvent.cs and KWritableEvent.cs, the REAL Switch.Dispose members, the REAL lines added to Horizon.Dispose and the REAL
sessionRetention probe run with doubles keeping the production reference chains. Session A plays and closes, session B
re-initialises the time service, registers a clock operation event and opens btdrv events, closes, and session C
opens. The control keeps A reachable through the running timer after B re-initialised time (and B through the timer,
the time singleton, the operation event and the Bluetooth statics); the candidate collects both, the probe reports them
released and the census zero, and B and C read the same time as in the control from their own shared memory. No device.
Writes dist/melonx/session-retention-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_session_retention', _HOLD)
import adapt_session_retention  # noqa: E402
from adapt_session_retention import apply, BASELINE  # noqa: E402

HLE = 'src/Ryujinx.HLE/'
STATISTICS = HLE + 'PerformanceStatistics.cs'
SWITCH = HLE + 'Switch.cs'
HORIZON = HLE + 'HOS/Horizon.cs'
TIME = HLE + 'HOS/Services/Time/'
MANAGER = TIME + 'TimeManager.cs'
SHARED = TIME + 'TimeSharedMemory.cs'
USER = TIME + 'Clock/StandardUserSystemClockCore.cs'
CALLBACK = TIME + 'Clock/SystemClockContextUpdateCallback.cs'
WRITABLE = HLE + 'HOS/Kernel/Threading/KWritableEvent.cs'
BLUETOOTH = HLE + 'HOS/Services/Bluetooth/BluetoothDriver/BluetoothEventManager.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

# The mechanism, in the preparation.
control_text = {name: read(SOURCE, name) for name in BASELINE}
statistics_c = control_text[STATISTICS]
check(re.search(r'_resetTimer = new\(750\);\s*_resetTimer\.Elapsed \+= ResetTimerElapsed;\s*_resetTimer\.AutoReset = true;\s*'
                r'_resetTimer\.Start\(\);', statistics_c) is not None and 'Dispose' not in statistics_c and
      'Stop(' not in statistics_c and statistics_c.count('_device') == 2, 'control: a timer started and never stopped, an unread Switch')
switch_c = control_text[SWITCH]
check('Statistics        = new PerformanceStatistics(this);' in switch_c and
      'Statistics' not in member(switch_c, 'protected virtual void Dispose(bool disposing)'), 'control: Switch.Dispose leaves the statistics')
horizon_c = control_text[HORIZON]
check('TimeServiceManager.Instance.Initialize(device, this, timeSharedMemory, timeStorage, TimeSize);' in horizon_c and
      'TimeServiceManager' not in member(horizon_c, 'protected virtual void Dispose(bool disposing)'), 'control: Horizon initialises, never releases')
check('_instance ??= new TimeManager();' in control_text[MANAGER] and '_device = device;' in control_text[SHARED] and
      '_autoCorrectionEvent = new KEvent(system.KernelContext);' in control_text[USER] and
      'Remove' not in control_text[CALLBACK] and 'public static KEvent InitializeBleEvent;' in control_text[BLUETOOTH],
      'control: process-wide time and Bluetooth state holding session objects')

replacements = {}
original_once = adapt_session_retention.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-session-retention-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.setdefault(path.relative_to(work).as_posix(), []).append((old, new))
        original_once(path, old, new)

    adapt_session_retention.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapt_session_retention.once = original_once
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        later = files_edited_later('adapt_session_retention')
        for name in BASELINE:
            if name not in later:
                check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    texts = {'control': control_text, 'candidate': {name: read(work, name) for name in BASELINE}}
    candidate = texts['candidate']
    for name in BASELINE:
        undone = candidate[name]
        for old, new in reversed(replacements.get(name, [])):
            check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
            undone = undone.replace(new, old)
        check(undone == control_text[name], name + ' is the preparation but the adapter\'s replacements')
        check('RewindBox (adapt_session_retention)' in ''.join(new for _, new in replacements[name]), name + ': added code is marked')

    # Statistics: disposable, no stored device, constructor unchanged.
    statistics = candidate[STATISTICS]
    dispose = member(statistics, 'public void Dispose()')
    check('public class PerformanceStatistics : System.IDisposable' in statistics and '_device' not in statistics and
          'public PerformanceStatistics(Switch device)' in statistics, 'statistics: IDisposable, no Switch stored, same constructor')
    check(dispose.index('_resetTimer.Elapsed -= ResetTimerElapsed;') < dispose.index('_resetTimer.Dispose();'), 'Dispose unhooks, disposes')
    for signature in ('private void ResetTimerElapsed(', 'public void RecordGameFrameTime()', 'public double GetGameFrameRate()'):
        if signature in statistics_c:
            check(member(statistics, signature) == member(statistics_c, signature), 'unchanged: ' + signature)
    # Switch: disposed right after Horizon, inside the disposing branch.
    switch_dispose = member(candidate[SWITCH], 'protected virtual void Dispose(bool disposing)')
    check(switch_dispose.index('if (disposing)') < switch_dispose.index('System.Dispose();') <
          switch_dispose.index('Statistics?.Dispose();') < switch_dispose.index('AudioDeviceDriver.Dispose();'),
          'Switch.Dispose disposes the statistics after Horizon')
    # Horizon: releases after every process is terminated and joined and the kernel disposed.
    horizon_dispose = member(candidate[HORIZON], 'protected virtual void Dispose(bool disposing)')
    check(horizon_dispose.index('if (!_isDisposed && disposing)') < horizon_dispose.index('terminationThread.HostThread.Join();') <
          horizon_dispose.index('INvDrvServices.Destroy();') < horizon_dispose.index('KernelContext.Dispose();') <
          horizon_dispose.index('TimeServiceManager.Instance.ReleaseSession(Device, KernelContext);') <
          horizon_dispose.index('BluetoothEventManager.ReleaseSession(KernelContext);'), 'Horizon releases after the session is gone')
    release_start = candidate[HORIZON].index('\n                // RewindBox (adapt_session_retention): every process')
    release_end = candidate[HORIZON].index('BluetoothEventManager.ReleaseSession(KernelContext);\n', release_start) + \
        len('BluetoothEventManager.ReleaseSession(KernelContext);\n')
    horizon_release = candidate[HORIZON][release_start:release_end]
    check(candidate[HORIZON][:release_start].endswith('KernelContext.Dispose();\n'), 'release directly after KernelContext.Dispose')
    # Identity checks.
    check(re.search(r'internal void Release\(Switch device\)\s*\{\s*if \(_device == device\)\s*\{\s*_device = null;\s*'
                    r'_sharedMemory = null;\s*_timeSharedMemoryStorage = null;', candidate[SHARED]) is not None, 'time memory: only its own device')
    check(re.search(r'if \(HoldsAutomaticCorrectionEvent\(context\)\)\s*\{\s*_autoCorrectionEvent = null;', candidate[USER]) and
          '_autoCorrectionEvent != null && _autoCorrectionEvent.WritableEvent.OwnerContext == context' in candidate[USER],
          'correction event: only the closing kernel\'s')
    check(re.search(r'lock \(_operationEventList\)\s*\{\s*_operationEventList\.RemoveAll\(e => e\.OwnerContext == context\);',
                    candidate[CALLBACK]) is not None, 'operation events: only the closing kernel\'s, under the list monitor')
    check('internal KernelContext OwnerContext => KernelContext;' in candidate[WRITABLE], 'read-only owner accessor')
    check(candidate[BLUETOOTH].count('Release(ref ') == 7 and 'if (!Owned(kEvent, context))' in candidate[BLUETOOTH] and
          'kEvent != null && kEvent.WritableEvent.OwnerContext == context' in candidate[BLUETOOTH], 'Bluetooth: only the closing kernel\'s events')
    for name in (SHARED, USER, CALLBACK, WRITABLE, BLUETOOTH, MANAGER):
        added = ''.join(new.replace(old, '') for old, new in replacements[name])
        check(not re.search(r'GC\.|Signal\(|Thread|Task', added), name + ': releases signal nothing and start nothing')
    # Probe: journal only.
    library = candidate[LIBRARY]
    probe_start = library.index('        // RewindBox (adapt_binder_teardown): whether a closed session')
    probe_end = library.index(member(library, 'private static void RecordSessionRetention()')) + \
        len(member(library, 'private static void RecordSessionRetention()')) + 1
    probe = library[probe_start:probe_end]
    probe_c_start = control_text[LIBRARY].index('        // RewindBox (adapt_binder_teardown): whether a closed session')
    probe_c = control_text[LIBRARY][probe_c_start:control_text[LIBRARY].index(
        member(control_text[LIBRARY], 'private static void RecordSessionRetention()')) +
        len(member(control_text[LIBRARY], 'private static void RecordSessionRetention()')) + 1]
    check(library.replace(probe, probe_c) == control_text[LIBRARY], 'Library unchanged outside the probe')
    check(not re.search(r'GC\.(Collect|WaitForPendingFinalizers|KeepAlive|GetTotalMemory\(true\))|GCHandle|Dispose\(|_emulationContext|_window\b', probe),
          'probe adds no collection and touches no session state')
    check(re.findall(r'private static (?:readonly )?([^\n=]+?) _\w+ = ', probe) ==
          ['List<(WeakReference Device, WeakReference Gpu, WeakReference Statistics, WeakReference System)>', 'object'],
          'only weak references are kept')
    check(library.count('EmbeddedLaunchDiagnostics.Record(') == control_text[LIBRARY].count('EmbeddedLaunchDiagnostics.Record(') and
          'tracked == 0 ? "none" : latestDevice ? "retained" : "released", devices,' in probe, 'same line, same statuses')

    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Library (with Ryujinx.HLE) builds with the adapter')
    print('candidate: production Ryujinx.Library built', flush=True)

    # Behaviour.
    program = (ROOT / 'test/melonx_session_retention/Program.cs').read_text()
    trees = {'control': SOURCE, 'candidate': work}
    for variant, tree in trees.items():
        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        source = texts[variant]
        real = [STATISTICS, 'src/Ryujinx.Common/PerformanceCounter.cs', MANAGER, SHARED, TIME + 'ResultCode.cs', BLUETOOTH,
                HLE + 'HOS/Kernel/Threading/KEvent.cs', WRITABLE]
        real += sorted(p.relative_to(tree).as_posix() for folder in ('Types', 'Clock', 'Clock/Types')
                       for p in (tree / TIME / folder).glob('*.cs') if p.name != 'ClockSnapshot.cs')
        for index, name in enumerate(real):
            (fixture / f'{index:02d}_{Path(name).name}').write_text(read(tree, name))
        switch_members = member(source[SWITCH], 'public void Dispose()') + '\n\n' + \
            member(source[SWITCH], 'protected virtual void Dispose(bool disposing)')
        text = program.replace('//__SWITCH_DISPOSE__\n', switch_members + '\n')
        text = text.replace('//__HORIZON_RELEASE__\n', horizon_release if variant == 'candidate' else '')
        variant_probe = probe if variant == 'candidate' else probe_c
        text = text.replace('//__PROBE__\n', variant_probe)
        check(all(marker not in text for marker in ('//__SWITCH_DISPOSE__', '//__HORIZON_RELEASE__', '//__PROBE__')), 'markers filled')
        (fixture / 'Program.cs').write_text(text)
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<NoWarn>CS0067;CS0414;CS0649;CS0169;CS8321;CS0162</NoWarn></PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant + ': ' + json.dumps(reports[variant])[:3000], flush=True)

    # The fixture's Horizon calls the time service as production does.
    for line in re.findall(r'^\s*(TimeServiceManager\.Instance\.\w+\(.*\);)$', program, flags=re.M):
        check(line in horizon_c, 'fixture Horizon calls the time service as Horizon.cs does: ' + line)

control, candidate_report = reports['control'], reports['candidate']
for name, report in reports.items():
    for session, posix_key in (('timeA', 'A'), ('timeB', 'B'), ('timeC', 'C')):
        time = report[session]
        check(time['sharedMemoryIsSession'] and time['sharedMemoryWritten'] and time['automaticCorrectionEventIsSession'] and
              time['automaticCorrectionSignalled'] and time['automaticCorrectionEnabled'] and time['automaticCorrectionByte'] == 1 and
              time['currentTime'] == 'Success' and time['currentTimeMinusPosix'] == 0 and
              time['sharedLocalClockSource'] == '36a0328702ce8bc11608eaba02333284',
              name + ': ' + session + ' reads its own time from its own shared memory: ' + json.dumps(time))
    check(report['timerRunningA'], name + ': the statistics timer runs during the session')
check(control['timeA']['sharedLocalOffsetMinusPosix'] == control['timeB']['sharedLocalOffsetMinusPosix'] ==
      control['timeC']['sharedLocalOffsetMinusPosix'], 'each session writes its own local clock offset')
for session in ('timeA', 'timeB', 'timeC'):
    check(control[session] == candidate_report[session], 'same time in control and candidate: ' + session)

# Control: the roots exist.
check(control['timerEnabledAfterCloseA'] and control['timeHoldsAAfterClose']['timeSharedMemoryDevice'] and
      control['timeHoldsAAfterClose']['automaticCorrectionEvent'] and control['timeHoldsAAfterClose']['statisticsStoresDevice'],
      'control: after the close the timer runs and the time singleton holds the session')
check(control['afterCloseA']['switch'] and control['afterCloseA']['gpu'], 'control: closed session A reachable')
check(control['afterCloseB_A']['switch'] and control['afterCloseB_A']['census']['statisticsTimerEnabled'] and
      not control['afterCloseB_A']['census']['timeSharedMemoryDevice'] and not control['afterCloseB_A']['census']['automaticCorrectionEvent'] and
      control['afterCloseB_A']['census']['operationEvents'] == 0 and control['afterCloseB_A']['census']['bluetoothEvents'] == 0,
      'control: once B re-initialised time, A is held by its running timer alone')
census_b = control['afterCloseB_B']['census']
check(control['afterCloseB_B']['switch'] and census_b['statisticsTimerEnabled'] and census_b['timeSharedMemoryDevice'] and
      census_b['automaticCorrectionEvent'] and census_b['operationEvents'] == 1 and census_b['bluetoothEvents'] == 3,
      'control: B held by the timer, the time singleton, its operation event and the Bluetooth statics')
check(control['afterOpenC_A']['switch'] and control['afterOpenC_B']['switch'] and control['afterOpenC_B']['census']['operationEvents'] == 1 and
      control['afterOpenC_B']['census']['bluetoothEvents'] == 3, 'control: both closed sessions still reachable after C opens')
check(control['closedSessionEventSignalledBySessionC'] >= 1 and control['bluetoothCOwned'] == 0 and
      control['bluetoothHandlesAfterCloseB'] != [0, 0, 0], 'control: C signals B\'s event and is handed B\'s Bluetooth events and handles')

# Candidate: released, and the next sessions set up their own.
check(not candidate_report['timerEnabledAfterCloseA'] and candidate_report['timeHoldsAAfterClose'] == dict(
    statisticsTimerEnabled=False, statisticsStoresDevice=False, timeSharedMemoryDevice=False, timeSharedMemoryStorage=False,
    automaticCorrectionEvent=False, operationEvents=0, bluetoothEvents=0), 'candidate: nothing process-wide holds A after its close')
for key in ('afterCloseA', 'afterCloseB_A', 'afterCloseB_B', 'afterOpenC_A', 'afterOpenC_B'):
    check(candidate_report[key] == dict(switch=False, gpu=False, statistics=False, horizon=False), 'candidate: collected: ' + key)
check(candidate_report['censusBAfterClose'] == dict(statisticsTimerEnabled=False, statisticsStoresDevice=False, timeSharedMemoryDevice=False,
                                                    timeSharedMemoryStorage=False, automaticCorrectionEvent=False, operationEvents=0,
                                                    bluetoothEvents=0) and
      candidate_report['bluetoothHandlesAfterCloseB'] == [0, 0, 0] and candidate_report['bluetoothBOwned'] == 3,
      'candidate: B\'s events, handles and time references released at its close')
check(candidate_report['closedSessionEventSignalledBySessionC'] == 0 and candidate_report['operationEventsAfterC'] == 0 and
      candidate_report['bluetoothCOwned'] == 3, 'candidate: C signals no closed session and creates its own Bluetooth events')

check(control['censusOfLiveC'] is None and candidate_report['censusOfLiveC'] == 6,
      'census counts the references the statics hold to a session: ' + str(candidate_report['censusOfLiveC']))
journal_c, journal = control['journal'], candidate_report['journal']
check(len(journal_c) == 2 and journal_c[0].startswith('sessionRetention retained 1 after the final collection: closed sessions tracked 1; '
      'Switch still reachable 1/1 (latest yes); GpuContext still reachable 1/1') and
      journal_c[1].startswith('sessionRetention retained 2 after the final collection: closed sessions tracked 2; Switch still reachable 2/2'),
      'control probe: 1/1 then 2/2: ' + str(journal_c))
check(len(journal) == 2 and journal[0].startswith(
    'sessionRetention released 0 after the final collection: closed sessions tracked 1; Switch still reachable 0/1 (latest no); '
    'GpuContext still reachable 0/1 (latest no); PerformanceStatistics still reachable 0/1; Horizon still reachable 0/1; '
    'time service and Bluetooth references to closed sessions 0; binder registry entries 0; managed heap ') and
      journal[1].startswith('sessionRetention released 0 after the final collection: closed sessions tracked 2; Switch still reachable 0/2 '
                            '(latest no); GpuContext still reachable 0/2 (latest no); PerformanceStatistics still reachable 0/2; '
                            'Horizon still reachable 0/2; time service and Bluetooth references to closed sessions 0; '),
      'candidate probe: released 0/1 then 0/2 with the census: ' + str(journal))

inputs = ['build-utils/melonx/adapt_session_retention.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_session_retention_test.py',
          'test/melonx_session_retention/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionLibraryBuilt=True, productionHleAssemblyBuilt=True,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Executed with the real statistics, time-service, Bluetooth-event and probe sources and doubles for the '
                          'kernel, Horizon and Switch; whether the device line reads released 0/n, and how far the managed heap '
                          'after a close falls below 455 MB, are known only from a device run with two launches in one process. '
                          'Other roots of the real HLE graph, if any, are named by the census and the sub-object counts of that line.')
out = ROOT / 'dist/melonx/session-retention-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
