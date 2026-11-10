#!/usr/bin/env python3
"""The forced CPU-side syncpoint wait waits while the GPU progresses (adapt_forced_syncpoint_wait), before and after.

Usage: melonx_forced_syncpoint_wait_test.py <Core 658 prepared MeloNX tree>
       melonx_forced_syncpoint_wait_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 658 preparation, candidate adds the adapter. For each, the production Ryujinx.Library assembly is
built (with it Ryujinx.HLE, Ryujinx.Graphics.Gpu and Ryujinx.Graphics.GAL), and a fixture loads the built assemblies
and runs the real NvHostEvent.Wait forced path (the guest cancelled the fence twice) on a "{Nv}" thread whose kernel
thread is a KThread, against the real SynchronizationManager, GpuContext and GPFifoDevice, with a GPU double driving the
production progress members (test/melonx_forced_syncpoint_wait/Program.cs). Required, control against candidate (Hogwarts
policy on):
- a syncpoint that advances to the fence in 2.5 s: control answers after 1 s with the fence not reached (the false
  completion of pid 11152), candidate when it is reached, with its true value;
- GPU command buffers without increments for 3.2 s, or the render thread completing commands while the GPU thread waits
  on it for 3.2 s, then the fence: candidate waits for it;
- GPU idle with nothing queued: both give up after one slice (1 s), the candidate journals it once in a session;
- progress for 2 s, then the GPU drains short of the fence: candidate gives up one or two slices after the drain;
- busy without any progress: candidate gives up after the 10 s deadlock guard, journaled once;
- guest termination 300 ms into a wait while the GPU works: candidate ends it by the termination poll within the first
  slice, sees the flag within one 50 ms poll plus the host's timed-wait lateness measured over the same window, and
  returns within 10 ms of seeing it; control after 1 s;
- progress that never reaches the threshold ends at the absolute 30 s cap (short cap in the fixture), counted and
  journaled once; a value reached without the callback is Reached at the slice end with its true value;
- already reached: no wait; policy off: the control's behaviour; a GPU-side WaitOnSyncpoint keeps the 1 s cap and its
  error line; the counters line is bounded (64 notable lines a session, then every 256 forced waits).
Static: the candidate's files are the preparation once the adapter's replacements are undone, WaitOnSyncpoint and the
GPU-side callers (GPFifoClass, Host1xClass) are unchanged, the flag is off by default and the Library assigns it once from
the launched title. No device. Writes dist/melonx/forced-syncpoint-wait-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_forced_syncpoint_wait', _HOLD)
import adapt_forced_syncpoint_wait  # noqa: E402
from adapt_forced_syncpoint_wait import apply, BASELINE  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
SYNC = 'src/Ryujinx.Graphics.Gpu/Synchronization/SynchronizationManager.cs'
EVENT = 'src/Ryujinx.HLE/HOS/Services/Nv/NvDrvServices/NvHostCtrl/Types/NvHostEvent.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
CONFIG = 'src/Ryujinx.Graphics.Gpu/GraphicsConfig.cs'
GPU_SIDE = ['src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs', 'src/Ryujinx.Graphics.Host1x/Host1xClass.cs',
            'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/Types/AndroidFence.cs',
            'src/Ryujinx.HLE/HOS/Services/Nv/NvDrvServices/NvHostCtrl/NvHostCtrlDeviceFile.cs']
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


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

replacements = []
original_once = adapt_forced_syncpoint_wait.once
reports, texts = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-forced-syncpoint-wait-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            def recording_once(path, old, new):
                replacements.append((path.relative_to(work).as_posix(), old, new))
                original_once(path, old, new)

            adapt_forced_syncpoint_wait.once = recording_once
            try:
                changed = apply(work)
            finally:
                adapt_forced_syncpoint_wait.once = original_once
            check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_forced_syncpoint_wait')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
            for name in BASELINE:
                undone = (work / name).read_text(encoding='utf-8-sig')
                for path, old, new in reversed(replacements):
                    if path == name:
                        check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                        undone = undone.replace(new, old)
                check(undone == (SOURCE / name).read_text(encoding='utf-8-sig'), name + ' is the preparation but the adapter\'s replacements')
            for name in GPU_SIDE:
                check((work / name).read_bytes() == (SOURCE / name).read_bytes(), 'GPU-side wait caller unchanged: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}

        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo',
                                 '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Library (HLE, Gpu, GAL) builds')
        binaries = work / 'src/Ryujinx.HLE/bin/Release/net10.0'
        check((binaries / 'Ryujinx.HLE.dll').is_file() and (binaries / 'Ryujinx.Graphics.Gpu.dll').is_file(), 'built assemblies present')

        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        shutil.copyfile(ROOT / 'test/melonx_forced_syncpoint_wait/Program.cs', fixture / 'Program.cs')
        references = ''.join(f'<Reference Include="{binaries / name}" />' for name in (
            'Ryujinx.HLE.dll', 'Ryujinx.Graphics.Gpu.dll', 'Ryujinx.Graphics.GAL.dll', 'Ryujinx.Common.dll'))
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>' +
            ('<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else '') +
            '</PropertyGroup><ItemGroup>' + references + '</ItemGroup></Project>\n')
        result = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ' fixture builds against the production assemblies')
        output = fixture / 'bin/Release/net10.0'
        for dll in binaries.glob('*.dll'):  # the production assemblies' own dependencies (LibHac, ...)
            if not (output / dll.name).exists():
                shutil.copyfile(dll, output / dll.name)
        result = subprocess.run([DOTNET, str(output / 'Fixture.dll'), variant], capture_output=True, text=True, timeout=600,
                                env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ' fixture runs')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
check(not c['policyFlag'] and not c['progressMembers'] and k['policyFlag'] and k['progressMembers'], 'variants are the right assemblies')
for name in ('progressing', 'gpuWorkThenFence', 'renderWorkThenFence', 'idle', 'idleAgain', 'drainedShort', 'stuckBusy',
             'termination', 'alreadyReached'):
    check(c[name]['WaitReturned'] is False and k[name]['WaitReturned'] is False, name + ': forced path answers Success (false) in both')
# The false completion of pid 11152, and its correction.
cp, kp = c['progressing'], k['progressing']
check(900 <= cp['Ms'] <= 1300 and not cp['TrueCompletion'] and cp['ValueAtReturn'] < cp['Threshold'],
      'control: released after 1 s before the fence: ' + json.dumps(cp))
check(any('took more than 1000ms, resuming execution' in line for line in cp['Lines']), 'control logs the timeout')
check(kp['TrueCompletion'] and kp['ValueAtReturn'] == kp['Threshold'] and 2300 <= kp['Ms'] <= 3200,
      'candidate: released when the fence is reached, with its true value: ' + json.dumps(kp))
check(any('1 forced, 2 slices, 1 false completions avoided, 0 fallbacks with the GPU idle, 0 without progress' in line
          for line in kp['Lines']), 'candidate counts the false completion avoided: ' + str(kp['Lines']))
for name in ('gpuWorkThenFence', 'renderWorkThenFence'):
    check(not c[name]['TrueCompletion'] and 900 <= c[name]['Ms'] <= 1300, 'control: ' + name + ' released after 1 s')
    check(k[name]['TrueCompletion'] and 3000 <= k[name]['Ms'] <= 4300, 'candidate: ' + name + ' waits for the fence: ' + json.dumps(k[name]))
# Deadlock guard: idle after one slice (today's 1 s), wedged after 10 s; journaled once.
for name in ('idle', 'idleAgain'):
    check(900 <= c[name]['Ms'] <= 1300 and 900 <= k[name]['Ms'] <= 1300 and not k[name]['TrueCompletion'],
          name + ': both give up after one slice: ' + json.dumps(k[name]))
check(sum(line.startswith('Warning') and 'GPU idle with nothing queued' in line for line in k['idle']['Lines'] + k['idleAgain']['Lines']) == 1,
      'idle fallback journaled once per session')
check(any('2 forced, 2 slices, 0 false completions avoided, 2 fallbacks with the GPU idle' in line for line in k['idleAgain']['Lines']),
      'idle fallbacks counted: ' + str(k['idleAgain']['Lines']))
kd = k['drainedShort']
check(not kd['TrueCompletion'] and kd['ValueAtReturn'] == kd['Threshold'] - 80 and 2800 <= kd['Ms'] <= 4300,
      'candidate: gives up one or two slices after the GPU drained short of the fence: ' + json.dumps(kd))
ks = k['stuckBusy']
check(9900 <= ks['Ms'] <= 11500 and not ks['TrueCompletion'] and 900 <= c['stuckBusy']['Ms'] <= 1300,
      'busy without progress: candidate gives up after the 10 s guard: ' + json.dumps(ks))
check(sum('no GPU progress for 10000 ms' in line and line.startswith('Warning') for line in ks['Lines']) == 1 and
      any('1 without progress' in line for line in ks['Lines']), 'wedged fallback journaled once and counted: ' + str(ks['Lines']))
kt, ct = k['termination'], c['termination']
# The production wait checks the termination flag before each poll of at most ProgressWaitPollMs (50 ms) and returns
# right after it sees it. On the macOS Core runner timed waits wake late (Core CI runs 42397176037-42625064149: the
# fixture's own 300 ms wait 3-59 ms late, the control's 1 000 ms waits 8-154 ms late, the candidate back 27-195 ms after
# the flag; locally <= 44 ms with every core busy), so a fixed 150 ms bound measured the host's wake-ups. Checked instead:
# the wait ended by the termination poll within its first slice, returned right after it saw the flag, and saw it within
# one 50 ms poll of the write plus how late this host woke an identical 50 ms timed wait over the same window.
check(any('1 ended by termination' in line and ', 0 slices,' in line for line in kt['Lines']) and kt['Ms'] < 600 and
      not kt['TrueCompletion'], 'candidate: the wait ended by the termination poll within its first slice: ' + json.dumps(kt))
check(0 <= kt['DetectionToReturnMs'] <= 10, 'candidate returns right after it sees the termination: ' + json.dumps(kt))
check(0 <= kt['TerminationToReturnMs'] and 0 <= kt['FlagToDetectionMs'] <= 50 + max(kt['HostLateMs'], 0) + 25,
      'candidate sees the termination within one 50 ms poll and the host\'s timed-wait lateness of the same window: ' +
      json.dumps(kt))
check(900 <= ct['Ms'] <= 1300, 'control ignores termination for its 1 s: ' + json.dumps(ct))
check(c['alreadyReached']['Ms'] < 100 and k['alreadyReached']['Ms'] < 100 and k['alreadyReached']['TrueCompletion'], 'already reached: no wait')
off = k['policyOff']
check(900 <= off['Ms'] <= 1300 and not off['TrueCompletion'] and any('resuming execution' in line for line in off['Lines']) and
      not any('adapt_forced_syncpoint_wait' in line for line in off['Lines']), 'policy off: the control\'s path')
for variant in ('control', 'candidate'):
    side = reports[variant]['gpuSideWait']
    check(side['timedOut'] is True and 900 <= side['ms'] <= 1300 and any('took more than 1000ms' in line for line in side['lines']),
          variant + ': a GPU-side WaitOnSyncpoint keeps the 1 s cap')
budget = k['lineBudget']
check(budget['reachedLines'] == 1, 'reached waits: one counters line at the 256th forced wait')
check(budget['idleLines'] == 65 and budget['idleWarnings'] == 1 and ': 64 forced, ' in budget['lastLine'],
      'notable waits: 64 counter lines (the last at the 64th of 100) and one journal line: ' + str(budget))

cap = k['cap']
check(cap['outcome'] == 'Capped' and 1400 <= cap['ms'] <= 2300 and cap['capConstantMs'] == 30000,
      'progress that never reaches the threshold ends at the absolute cap (30 s in production): ' + json.dumps(cap))
check(sum(line.startswith('Warning') and 'cap after' in line for line in cap['lines']) == 1 and
      any('2 at the cap' in line for line in cap['lines']) and not any('without progress' in line and ' 1 without' in line for line in cap['lines']),
      'cap fallback counted and journaled once: ' + str(cap['lines']))
kv = k['valueNoCallback']
check(kv['outcome'] == 'Reached' and kv['value'] == kv['target'] + 2 and 300 <= kv['ms'] <= 700,
      'a value reached without the callback is Reached at the slice end, with the true value: ' + json.dumps(kv))

# Static: unchanged callers and members, the gate.
check(member(texts['candidate'][SYNC], 'public bool WaitOnSyncpoint(') == member(texts['control'][SYNC], 'public bool WaitOnSyncpoint('),
      'WaitOnSyncpoint (GPU-side waits) unchanged')
event = member(texts['candidate'][EVENT], 'public bool Wait(GpuContext gpuContext, NvFence fence)')
check(event.count('WaitOnSyncpointWhileProgressing(') == 1 and
      'if (GraphicsConfig.ProgressAwareForcedSyncpointWait && Fence.IsValid())' in event and
      event.count('Fence.Wait(gpuContext, Timeout.InfiniteTimeSpan);') == 1 and 'return false;' in event,
      'NvHostEvent: the progress-aware wait under the policy only, the result unchanged')
check('public static bool ProgressAwareForcedSyncpointWait { get; set; }\n' in texts['candidate'][CONFIG], 'flag off by default')
library = texts['candidate'][LIBRARY]
check(library.count('GraphicsConfig.ProgressAwareForcedSyncpointWait') == 1 and
      'Ryujinx.Graphics.Gpu.GraphicsConfig.ProgressAwareForcedSyncpointWait = hogwarts;' in library and
      library.index('bool hogwarts = EmbeddedIsHogwarts(options.InputPath);') < library.index('ProgressAwareForcedSyncpointWait = hogwarts;') <
      library.index('renderer = renderer.TryMakeThreaded(options.BackendThreading);'),
      'the Library assigns the flag once per session from the launched title')

device = texts['candidate']['src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs']
dispatch = member(device, 'public void DispatchCalls()')
check(dispatch.index('_context.NoteDispatching(true);') < dispatch.index('try') < dispatch.index('DispatchCallsCore();') <
      dispatch.index('finally') < dispatch.index('_context.NoteDispatching(false);') and device.count('NoteDispatching(false)') == 1 and
      device.count('NoteDispatching(true)') == 1, 'GPFifoDevice: the dispatch mark is cleared in a finally')

inputs = ['build-utils/melonx/adapt_forced_syncpoint_wait.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_forced_syncpoint_wait_test.py', 'test/melonx_forced_syncpoint_wait/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=['Ryujinx.Library', 'Ryujinx.HLE',
               'Ryujinx.Graphics.Gpu', 'Ryujinx.Graphics.GAL'], sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host fixture with a GPU double driving the production progress members; the GPFIFO dispatch '
                          'marks and the threaded renderer counter are bound statically and by build, not run on a real GPU '
                          'thread. Whether the black flashes of Hogwarts Legacy go, and how long the {Nv} thread now waits '
                          'in a build burst, are known only from a device run.')
out = ROOT / 'dist/melonx/forced-syncpoint-wait-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
