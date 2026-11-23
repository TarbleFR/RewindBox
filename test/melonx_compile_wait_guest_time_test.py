#!/usr/bin/env python3
"""The guest's clock stands still while the guest's GPU path waits for a pipeline compile beyond 33 ms
(adapt_compile_wait_guest_time), before and after, the production TickSource.cs and GuestTimeHold.cs.

Usage: melonx_compile_wait_guest_time_test.py <final preparation containing the adapter>
       melonx_compile_wait_guest_time_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control); candidate is the adapter applied to it,
which must give the final preparation's files.
Static: each replacement once and reversible, GuestTimeHold.cs added, fail closed (an adapted or drifted file, an
existing GuestTimeHold.cs refused); TickSource: readers add host ticks to the snapshot still published after reading
them and wait out a transition (the counter and the scalar), a writer publishes the transition before reading its host
ticks and publishes the previous snapshot again on a failure, pause and hold freeze the snapshot (the stopwatch is never
stopped), a freeze starts a lead ahead, the tick source attaches itself; GuestTimeHold: the clock is held only by the
33 ms timer or within 250 ms of a held wait's end, nested waits count once, stale tokens ignored, the timer callback and
the clock calls cannot throw out, the line is written outside the lock, the three delegates published to AppContext;
the scheduler: WaitForPipelineAtDraw holds around its unchanged body (renamed WaitForPipelineAtDrawHeld) through
AppContext only, the draw-wait text gains the hold text; nothing else changes.
Built: the production Ryujinx.HLE (with Ryujinx.Cpu and Ryujinx.Common) and Ryujinx.Graphics.Vulkan assemblies of the
candidate, no warning in the edited files.
Executed (test/melonx_compile_wait_guest_time/Program.cs, production TickSource.cs, ITickSource.cs, ICounter.cs and the
candidate's GuestTimeHold.cs): 200 000 short waits (no drift); 20 000 held waits of 0 to 0.2 ms with scalar
replacements and a thread pausing and resuming, under 2 counter readers and a scalar reader (never back, never 0); a
600 ms and a 10 ms wait; nested waits with a thread sleeping inside; Unreal's heartbeat scaled to 2 s (a frame of 16
compile waits of 150 ms); pause inside a hold and alone; the long-wait line and the journal; session lifetime (a new
clock, a stale token); the cost of a read. No device. Writes dist/melonx/compile-wait-guest-time-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_compile_wait_guest_time', _HOLD)
import adapt_compile_wait_guest_time as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_compile_wait_guest_time'
COMPILED = [adapter.TICKS, 'src/Ryujinx.Cpu/ITickSource.cs', 'src/ARMeilleure/State/ICounter.cs']
PROJECTS = ['src/Ryujinx.HLE/Ryujinx.HLE.csproj', 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj']
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def code(text):
    return re.sub(r'//[^\n]*', '', text)


def project_closure(tree, project):
    found, pending = [], [Path(project)]
    while pending:
        current = pending.pop()
        directory = current.parent.as_posix()
        if directory in found:
            continue
        found.append(directory)
        text = (tree / current).read_text(encoding='utf-8-sig')
        for reference in re.findall(r'<ProjectReference Include="([^"]+)"', text):
            pending.append(Path(os.path.normpath((current.parent / reference.replace('\\', '/')).as_posix())))
    return found


# 0. The control and the candidate texts.
EDITED = list(adapter.BASELINE)
OWN = EDITED + adapter.ADDED
check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in adapter.BASELINE.items():
    check(sha(SOURCE / name) == expected, "not the adapter's preparation: " + name)
for name in adapter.ADDED:
    check(not (SOURCE / name).exists() or (SOURCE / name).read_text(encoding='utf-8') == adapter.HOLD_SOURCE,
          'the control has no ' + name + ' but the adapter\'s (a reversed control keeps the file it adds)')
control = {name: (SOURCE / name).read_text(encoding='utf-8-sig') for name in EDITED}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports, compiled_inputs = {}, {}

with tempfile.TemporaryDirectory(prefix='melonx-compile-wait-guest-time-') as temporary:
    temporary = Path(temporary).resolve()
    tree = temporary / 'candidate-tree'
    for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', 'nuget.config'):
        if (SOURCE / name).exists():
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, tree / name)
    directories = []
    for project in PROJECTS:
        directories += [d for d in project_closure(SOURCE, project) if d not in directories]
    for directory in directories:
        shutil.copytree(SOURCE / directory, tree / directory, ignore=shutil.ignore_patterns('bin', 'obj'), symlinks=True)
    for name in EDITED + COMPILED:
        check((tree / name).exists(), 'the built projects hold ' + name)
    for name in adapter.ADDED:
        (tree / name).unlink(missing_ok=True)
    changed = adapter.apply(tree)
    check(sorted(p.relative_to(tree).as_posix() for p in changed) == sorted(OWN), 'the adapter changes its two files and adds GuestTimeHold.cs')
    later = files_edited_later('adapt_compile_wait_guest_time')
    for name in OWN:
        if name not in later:
            check((tree / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'the final preparation is the control plus the adapter: ' + name)
    candidate = {name: (tree / name).read_text(encoding='utf-8-sig') for name in OWN}
    try:
        adapter.apply(tree)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted file is refused')
    for drifted in (adapter.TICKS, adapter.HOLD):
        drift = temporary / ('drift-' + Path(drifted).stem)
        for name in EDITED:
            (drift / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, drift / name)
        if drifted == adapter.TICKS:
            (drift / drifted).write_bytes((drift / drifted).read_bytes() + b'\n// unreviewed drift\n')
        else:
            (drift / drifted).parent.mkdir(parents=True, exist_ok=True)
            (drift / drifted).write_text('// an existing file\n')
        try:
            adapter.apply(drift)
            refused = False
        except AssertionError:
            refused = True
        check(refused, 'fail closed: refused with ' + ('a drifted TickSource.cs' if drifted == adapter.TICKS else 'an existing GuestTimeHold.cs'))
    for old, new in adapter.FILE_PAIRS[adapter.SCHEDULER]:
        check(control[adapter.SCHEDULER].count(old) == 1 and candidate[adapter.SCHEDULER].count(new) == 1, 'each replacement is exact: ' + new.strip()[:70])
    reverted = candidate[adapter.SCHEDULER]
    for old, new in reversed(adapter.FILE_PAIRS[adapter.SCHEDULER]):
        reverted = reverted.replace(new, old, 1)
    check(reverted == control[adapter.SCHEDULER], 'the scheduler\'s replacements reverse to the control')
    old_class = adapter.tick_source_old(control[adapter.TICKS])
    check(candidate[adapter.TICKS] == control[adapter.TICKS].replace(old_class, adapter.TICKS_CLASS_NEW) and
          candidate[adapter.TICKS].startswith(control[adapter.TICKS][:control[adapter.TICKS].index(adapter.TICKS_CLASS_START)]),
          'TickSource.cs: the usings and namespace kept, the class replaced')
    check(candidate[adapter.HOLD] == adapter.HOLD_SOURCE, 'GuestTimeHold.cs is the adapter\'s text')

    for project in PROJECTS:
        result = subprocess.run([DOTNET, 'build', str(tree / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=2400, env=environment, cwd=tree)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, 'candidate production assembly builds: ' + project)
        warnings = sorted({line for line in result.stdout.splitlines() if 'warning' in line and
                           any(Path(name).name + '(' in line for name in OWN)})
        check(not warnings, 'no compiler warning in the edited files: ' + '\n'.join(warnings[:5]))

    for variant, source in (('control', SOURCE), ('candidate', tree)):
        fixture = temporary / ('fixture-' + variant)
        for name in COMPILED + (adapter.ADDED if variant == 'candidate' else []):
            (fixture / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, fixture / name)
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        define = 'CANDIDATE' if variant == 'candidate' else 'CONTROL'
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<LangVersion>preview</LangVersion><Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers>'
            '<NoWarn>CS0649;CS0414;CS0169;CS8321;CS1998</NoWarn>'
            f'<DefineConstants>$(DefineConstants);{define}</DefineConstants></PropertyGroup></Project>\n')
        compiled_inputs[variant] = {p.relative_to(fixture).as_posix(): sha(p) for p in sorted(fixture.rglob('*.cs'))}
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), '20000']):
            result = subprocess.run(command, capture_output=True, text=True, timeout=1200, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant, json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']

# 1. Static: what changed in the production text.
ticks_c, ticks_k = control[adapter.TICKS], candidate[adapter.TICKS]
elapsed = member(ticks_k, 'private long ElapsedTicks')
check(re.search(r'TickSnapshot snapshot = Volatile\.Read\(ref _snapshot\);\s*if \(!ReferenceEquals\(snapshot, _transition\)\)\s*\{\s*'
                r'long hostTicks = _tickCounter\.ElapsedTicks;\s*if \(ReferenceEquals\(Volatile\.Read\(ref _snapshot\), snapshot\)\)\s*\{\s*'
                r'return snapshot\.GetElapsedTicks\(hostTicks\);', elapsed) is not None,
      'a reader adds the host ticks to the snapshot still published after reading them, and waits out a transition')
check('get => Current().TickScalar;' in ticks_k and 'if (!ReferenceEquals(snapshot, _transition))' in member(ticks_k, 'private TickSnapshot Current()') and
      'new(0, 0, ITickSource.RealityTickScalar, true)' in ticks_k, 'the scalar is never read from a transition (and the transition\'s is 100)')
replace = member(ticks_k, 'private void Replace(long tickScalar, bool frozen, long lead)')
check(re.search(r'TickSnapshot next = snapshot;\s*Volatile\.Write\(ref _snapshot, _transition\);\s*try\s*\{\s*Interlocked\.MemoryBarrier\(\);\s*'
                r'long hostTicks = _tickCounter\.ElapsedTicks;', replace) is not None and
      re.search(r'finally\s*\{\s*Volatile\.Write\(ref _snapshot, next\);', replace) is not None,
      'a writer publishes the transition before reading its host ticks, and the previous snapshot again on a failure')
check('long ahead = snapshot.Frozen ? 0 : lead * snapshot.TickScalar / ITickSource.RealityTickScalar;' in replace and
      'next = new TickSnapshot(hostTicks, snapshot.GetElapsedTicks(hostTicks) + ahead, tickScalar, frozen);' in replace,
      'a freeze starts a lead ahead; a thaw goes on from the frozen value')
check('return Frozen ? ElapsedTicks : ElapsedTicks + Math.Max(0, hostTicks - HostTicks) * TickScalar / ITickSource.RealityTickScalar;' in ticks_k,
      'a frozen snapshot returns one value; host ticks read before a snapshot add nothing')
freeze, thaw = member(ticks_k, 'private void Freeze(int reason)'), member(ticks_k, 'private void Thaw(int reason)')
check(freeze.index('Replace(') < freeze.index('_frozen |= reason;') and thaw.index('Replace(') < thaw.index('_frozen &= ~reason;') and
      'if (_frozen == reason)' in thaw, 'two reasons (pause, hold); the reason is recorded once the snapshot is replaced')
for signature, reason in (('public void Suspend()', 'Freeze(FrozenByPause);'), ('public void Resume()', 'Thaw(FrozenByPause);'),
                          ('public void Hold()', 'Freeze(FrozenByHold);'), ('public void Release()', 'Thaw(FrozenByHold);')):
    body = member(ticks_k, signature)
    check('lock (_tickScalarLock)' in body and reason in body and '_tickCounter.Stop' not in body, signature + ': in the snapshot, under the lock')
check('_tickCounter.Stop()' in ticks_c and '_tickCounter.Stop()' not in ticks_k and ticks_k.count('_tickCounter.Start();') == 1,
      'the stopwatch is started once and never stopped under its readers')
ctor = member(ticks_k, 'public TickSource(ulong frequency)')
check(ctor.index('_tickCounter.Start();') < ctor.index('Ryujinx.Common.GuestTimeHold.Attach(this);'), 'the tick source attaches itself once started')
check('public ulong Counter => (ulong)(ElapsedSeconds * Frequency);' in ticks_c and 'public ulong Counter => (ulong)(ElapsedSeconds * Frequency);' in ticks_k and
      'public TimeSpan ElapsedTime => Stopwatch.GetElapsedTime(0, ElapsedTicks);' in ticks_k and
      'public double ElapsedSeconds => ElapsedTicks * _hostTickFreq;' in ticks_k, 'the values the guest reads are the same expressions')
hold = candidate[adapter.HOLD]
begin, end = member(hold, 'public static long Begin()'), member(hold, 'public static void End(long token)')
check('if (_depth++ != 0)' in begin and '_start - _lastHeldEnd < Ticks(BurstGapMilliseconds)' in begin and
      '_timer.Change(VisibleMilliseconds, Timeout.Infinite);' in begin and begin.count('HoldLocked(') == 1,
      'a wait is held from its start only within the burst gap of a held one; otherwise the 33 ms timer is armed')
check('if (token != _generation || _depth == 0 || --_depth != 0)' in end and '_timer.Change(Timeout.Infinite, Timeout.Infinite);' in end and
      'ReleaseLocked(now, true);' in end, 'the outermost wait of the current clock ends the hold; a stale token is ignored')
check(end.index('Logger.Warning?.Print') > end.index('_longWaits++;') and end.rindex('}', 0, end.index('Logger.Warning?.Print')) > end.index('_longWaits++;'),
      'the long-wait line is written outside the lock')
timer = member(hold, 'private static void OnTimer(object state)')
check('catch (Exception)' in timer and 'if (_depth == 0 || _holding || _clock == null)' in timer and 'if (remaining > 0)' in timer and
      'HoldLocked(now);' in timer, 'the timer holds a wait still running at 33 ms, re-arms if early, cannot throw out')
check('catch (Exception)' in member(hold, 'private static void HoldLocked(long now)') and 'catch (Exception)' in member(hold, 'private static void ReleaseLocked(long now, bool count)'),
      'a failed clock call leaves GuestTimeHold consistent')
attach = member(hold, 'public static void Attach(IClock clock)')
check('ReleaseLocked(Stopwatch.GetTimestamp(), false);' in attach and '_generation++;' in attach and '_depth = 0;' in attach and 'Hold()' not in attach,
      'a new clock ends the previous one\'s hold, resets the depth and invalidates earlier tokens; it is not held')
check(all('AppContext.SetData(%s, ' % key in hold for key in ('BeginKey', 'EndKey', 'TextKey')) and 'public const int VisibleMilliseconds = 33;' in hold and
      'public const int BurstGapMilliseconds = 250;' in hold, 'the delegates published to AppContext; 33 ms visible; 250 ms burst gap')
sched_c, sched_k = control[adapter.SCHEDULER], candidate[adapter.SCHEDULER]
outer = member(sched_k, 'public void WaitForPipelineAtDraw(Task task)')
check(re.search(r'long hold = CompileWaitGuestTime\.Begin\(\);\s*try\s*\{\s*WaitForPipelineAtDrawHeld\(task\);\s*\}\s*finally\s*\{\s*CompileWaitGuestTime\.End\(hold\);',
                outer) is not None, 'the draw and dispatch wait is held, released in a finally')
inner_k = member(sched_k, 'private void WaitForPipelineAtDrawHeld(Task task)')
inner_c = member(sched_c, 'public void WaitForPipelineAtDraw(Task task)')
check(inner_k.replace('private void WaitForPipelineAtDrawHeld(Task task)', 'public void WaitForPipelineAtDraw(Task task)') == inner_c,
      'the wait itself is unchanged')
glue = member(sched_k, 'static class CompileWaitGuestTime')
check(glue.count('AppContext.GetData(') == 3 and 'Ryujinx.Common.GuestTimeHold' not in code(glue) and
      all(key in glue for key in ('"RewindBox.GuestTimeHold.Begin"', '"RewindBox.GuestTimeHold.End"', '"RewindBox.GuestTimeHold.Text"')) and
      all('public const string %s = "%s";' % (name, key) in hold for name, key in
          (('BeginKey', 'RewindBox.GuestTimeHold.Begin'), ('EndKey', 'RewindBox.GuestTimeHold.End'), ('TextKey', 'RewindBox.GuestTimeHold.Text'))),
      'the backend reaches GuestTimeHold through AppContext only, with its three keys')
check('CompileWaitGuestTime.TakeText(); // RewindBox (adapt_compile_wait_guest_time)' in member(sched_k, 'public static string TakeText()'),
      'the draw-wait text gains the hold text (empty when unset)')

# 2. Executed.
check(c['failures'] == [] and k['failures'] == [], 'every probe check passed: ' + json.dumps([c['failures'], k['failures']]))
km = k['monotonic']
check(km['violations'] == 0 and km['perThreadViolations'] == 0 and km['scalarZero'] == 0 and km['cycles'] == 20000 and km['reads'] > 100000,
      'candidate: never back from any thread, the scalar never 0, under 20 000 held waits, scalar replacements and pauses: ' + json.dumps(km))
check(abs(k['shortWaits']['guestMs'] - k['shortWaits']['hostMs']) < 0.5 + k['shortWaits']['hostMs'] * 0.001,
      'candidate: 200 000 short waits leave the clock on host time: ' + json.dumps(k['shortWaits']))
check(595 < c['longWait']['guestMs'] < 900, 'control: the guest saw the whole 600 ms wait: ' + json.dumps(c['longWait']))
check(32 < k['longWait']['guestMs'] < 60 and k['longWait']['hostMs'] >= 595, 'candidate: the guest saw the first 33 ms of the 600 ms wait: ' + json.dumps(k['longWait']))
for report in (c, k):
    check(abs(report['tenMsWait']['guestMs'] - report['tenMsWait']['hostMs']) < 0.5, report['variant'] + ': a 10 ms wait is seen in full')
check(c['nested']['guestMs'] > 190, 'control: the guest saw the nested waits')
check(32 < k['nested']['guestMs'] < 60 and 32 < k['nested']['sleeperGuestMs'] < 60 and k['nested']['sleeperHostMs'] >= 75,
      'candidate: nested waits count once; a sleeper wakes on host time and reads the held clock: ' + json.dumps(k['nested']))
check(c['heartbeat']['hung'] and c['heartbeat']['longestGapS'] > 2.0, 'control: the scaled heartbeat reports the frame of compile waits hung')
check(not k['heartbeat']['hung'] and k['heartbeat']['longestGapS'] < 0.5 and k['heartbeat']['frameGuestMs'][0] < 120 and
      k['heartbeat']['frameGuestMs'][1] < 60, 'candidate: no hang; a frame of 16 waits shows the first 33 ms and the rendering between them: ' + json.dumps(k['heartbeat']))
check(k['pause']['heldGuestMs'] < 60 and c['pause']['aloneGuestMs'] < 30 and k['pause']['aloneGuestMs'] < 30, 'pause: its time stays out: ' + json.dumps([c['pause'], k['pause']]))
journal = k['journal']
waited = re.search(r'^Gpu: Pipeline compile wait of (\d+) ms on the guest\'s GPU path: the guest\'s clock counted (\d+) ms of it \(adapt_compile_wait_guest_time\)$',
                   journal['lines'])
check(waited is not None and 1095 <= int(waited.group(1)) <= 1300 and 32 <= int(waited.group(2)) <= 60,
      'one Gpu line for the 1.1 s wait (33 ms counted), none for the short one: ' + journal['lines'])
check(re.search(r"^; compile waits held from the guest's clock 1 of 2 \((10[3-9]\d|1[1-2]\d\d) ms not counted, longest wait 1[0-2]\d\d ms\)$", journal['text']) is not None,
      'the journal counts the waits, the held one and the time not counted: ' + journal['text'])
life = k['lifetime']
check(life['previousRunsAfterNewClockMs'] > 25 and 30 < life['laterClockWaitGuestMs'] < 60 and life['laterClockRunsMs'] > 35,
      'session lifetime: a new clock releases the previous one, holds its own waits, ignores a stale token: ' + json.dumps(life))
check(k['readCostNs'] < c['readCostNs'] + 25, 'a read costs under 25 ns more: ' + json.dumps([c['readCostNs'], k['readCostNs']]))

inputs = ['build-utils/melonx/adapt_compile_wait_guest_time.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_compile_wait_guest_time_test.py',
          'test/melonx_compile_wait_guest_time/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, probeChecks={'control': c['checks'], 'candidate': k['checks']},
               finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: sha(FINAL_SOURCE / p) for p in OWN}, sourceBaseline=adapter.BASELINE,
               physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, productionHleAssemblyBuilt=True,
               visibleMilliseconds=33, burstGapMilliseconds=250, control=c, candidate=k, sdk=sdk, compiledSourceInputs=compiled_inputs,
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host threads and the production clock; the compile waits are sleeps and spins, Unreal\'s heartbeat '
                          'a scaled model (2 s, 20 ms checks). Whether Hogwarts Legacy then passes its first gameplay frame '
                          'with an empty Metal cache, and how long the picture stays frozen, only a device session shows '
                          '("Pipeline compile wait of" lines, no write to address 3 on the heartbeat thread).')
out = ROOT / 'dist/melonx/compile-wait-guest-time-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, longWait=[c['longWait'], k['longWait']], heartbeat=[c['heartbeat'], k['heartbeat']],
                      monotonic=[c['monotonic'], k['monotonic']], readCostNs=[c['readCostNs'], k['readCostNs']])))
