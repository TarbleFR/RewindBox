#!/usr/bin/env python3
"""adapt_darwin_timed_waits on the final preparation, against its predecessor as control.

Usage: melonx_darwin_timed_waits_test.py <predecessor preparation> --candidate-source <final preparation containing the adapter>

IPA 733 / Core 745, Hogwarts Legacy (44 s of play): the guest timer thread 3.0 % of a core, the nanosleep helper threads
2.5 %, the compositor 0.6 %, all user-interactive. On iOS a sub-millisecond guest deadline is served by a helper thread
that nanosleeps and signals the timer thread; the compositor wakes 150-300 us early and spins until each 60 Hz interval.

Static: only PreciseSleepHelper.cs changes, each replacement once and reversing to the control; the Apple paths are
taken only when DarwinTimedWait.Applies (Apple platforms); SleepUntil returns false only for a deadline already
reached (the caller's existing spin then returns at once); a signal posts the semaphore once until a wait consumes it;
after a wake the waiter takes any count left, then clears the mark (the reverse order lost signals: a signal between
the clear and the drain left the mark set without a count, and later signals posted nothing); a Signal after Dispose
does nothing, the semaphore is released once by the last holder; the compositor's spin loop is kept after the timed
wait (it only finishes a wait that ended early); no thread, class, rate or deadline value is set by the change.
Built: the production Ryujinx.Common and Ryujinx.HLE of the candidate.
Executed on every host (test/melonx_darwin_timed_waits/protocol/Program.cs): the adapter's DarwinSleepEvent text with a
stand-in for the libSystem semaphore calls (it records releases and refuses any use after one). Two producers signal a
waiter that alternates Sleep() and a far SleepUntil: every one of 3 x 1 000 000 signals is seen within 200 ms (the
first version of the event lost one within 2 000-6 000 signals on Linux x86_64 and its waiter never woke again); a
thread signals in a loop while the owner disposes, 5 000 times: no exception, no use after release, one release per
event; a reached deadline returns false, a timed wait ends at its deadline, a prior signal ends it at once, signals
made while none is consumed count once.
Executed (test/melonx_darwin_timed_waits/Program.cs with the control's and the candidate's PreciseSleep files,
unchanged): the guest timer thread's loop (KTimeManager's) fed by four threads scheduling deadlines 50 us to 5 ms ahead,
and the compositor's loop (SurfaceFlinger's) at 60 Hz.
- On an Apple host (the Core CI's macOS arm64; the workflow melonx-collection-class.yml): the candidate's event is
  DarwinSleepEvent and starts no helper thread (control: up to eight, counted in the event's pool), every deadline
  fires, its lateness p50 and p90 are within 100 us of the control's or below, CPU per deadline and per frame are lower
  than the control's.
- On another host: the candidate takes the control's path (same event type and helper threads): unchanged.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, statistics, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import adapt_darwin_timed_waits as adapter  # noqa: E402
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402

SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_darwin_timed_waits', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
APPLE = platform.system() == 'Darwin'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, timeout=2400):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'))
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        raise SystemExit('FAILED: ' + ' '.join(str(part) for part in command[:4]))
    return result.stdout


def body(text, signature):
    start = text.index('{', text.index(signature))
    depth, at = 1, start + 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[at], 0)
        at += 1
    return text[start:at]


def protocol(directory):
    directory.mkdir(parents=True)
    marker = "    // RewindBox (adapt_darwin_timed_waits): the guest timer thread's event on Apple platforms"
    check(adapter.CLASS.count(marker) == 1, 'the event\'s text is found in the adapter')
    shutil.copyfile(ROOT / 'test/melonx_darwin_timed_waits/protocol/Program.cs', directory / 'Program.cs')
    (directory / 'Event.cs').write_text('namespace Ryujinx.Common.PreciseSleep\n{\n' + adapter.CLASS[adapter.CLASS.index(marker):] + '}\n')
    (directory / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><InvariantGlobalization>true</InvariantGlobalization>'
        '<NuGetAudit>false</NuGetAudit></PropertyGroup></Project>\n')
    run([DOTNET, 'build', str(directory / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-v', 'q', '-o', str(directory / 'out')], directory)
    probe = [DOTNET, str(directory / 'out/Fixture.dll')]
    def last(arguments):
        return json.loads(run(probe + arguments, directory, timeout=600).strip().splitlines()[-1])
    return {'semantics': last(['semantics']), 'dispose': last(['dispose', '5000']),
            'lost': [last(['lost', '500000']) for _ in range(3)]}


def fixture(directory, tree):
    directory.mkdir(parents=True)
    shutil.copytree(tree / 'src/Ryujinx.Common/PreciseSleep', directory / 'PreciseSleep')
    shutil.copyfile(tree / 'src/Ryujinx.Common/PerformanceCounter.cs', directory / 'PerformanceCounter.cs')
    shutil.copyfile(ROOT / 'test/melonx_darwin_timed_waits/Program.cs', directory / 'Program.cs')
    (directory / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><InvariantGlobalization>true</InvariantGlobalization>'
        '<NuGetAudit>false</NuGetAudit><NoWarn>CA1416;CS8981;CS0162</NoWarn><RootNamespace>Fixture</RootNamespace></PropertyGroup></Project>\n')
    run([DOTNET, 'build', str(directory / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-v', 'q', '-o', str(directory / 'out')], directory)
    probe = [DOTNET, str(directory / 'out/Fixture.dll')]
    timers = [json.loads(run(probe + ['timers', '1500'], directory).strip().splitlines()[-1]) for _ in range(3)]
    vsync = [json.loads(run(probe + ['vsync', '1500'], directory).strip().splitlines()[-1]) for _ in range(3)]
    def median(rows, key):
        return statistics.median(row[key] for row in rows)
    return {
        'timers': {'event': timers[0]['event'], 'deadlines': median(timers, 'deadlines'), 'cpuUsPerDeadline': median(timers, 'cpuUsPerDeadline'),
                   'threadsStarted': max(row['threadsStarted'] for row in timers), 'helperThreads': max(row['helperThreads'] for row in timers),
                   'latenessUsP50': median(timers, 'latenessUsP50'),
                   'latenessUsP90': median(timers, 'latenessUsP90'), 'latenessUsP99': median(timers, 'latenessUsP99')},
        'vsync': {'frames': median(vsync, 'frames'), 'cpuUsPerFrame': median(vsync, 'cpuUsPerFrame'),
                  'latenessUsP50': median(vsync, 'latenessUsP50'), 'latenessUsP90': median(vsync, 'latenessUsP90'),
                  'latenessUsP99': median(vsync, 'latenessUsP99')},
        'runs': {'timers': timers, 'vsync': vsync},
    }


ignore = shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX')
name = adapter.HELPER
with tempfile.TemporaryDirectory(prefix='melonx-darwin-timed-waits-') as temporary:
    temporary = Path(temporary).resolve()
    control_tree = temporary / 'control'
    shutil.copytree(SOURCE, control_tree, ignore=ignore, symlinks=True)
    check(sha(control_tree / name) == adapter.BASELINE[name], 'control is the predecessor\'s output')
    candidate = temporary / 'candidate'
    shutil.copytree(control_tree, candidate, symlinks=True)
    before = (candidate / name).read_text(encoding='utf-8-sig')
    changed = adapter.apply(candidate)
    check([str(path.relative_to(candidate)) for path in changed] == [name], 'adapter changed other files')
    try:
        adapter.apply(candidate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    after = (candidate / name).read_text(encoding='utf-8-sig')
    restored = after
    for old, new in reversed(adapter.PAIRS):
        check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
        restored = restored.replace(new, old)
    check(restored == before, 'nothing else changes in ' + name)
    others = [path for path in (control_tree / 'src').rglob('*.cs') if path.relative_to(control_tree).as_posix() != name]
    check(all((candidate / path.relative_to(control_tree)).read_bytes() == path.read_bytes() for path in others), 'no other source file changes')

    postimages = {}
    if FINAL_PREPARATION:
        if name not in files_edited_later('adapt_darwin_timed_waits'):
            check((candidate / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        shutil.rmtree(candidate)
        shutil.copytree(FINAL_SOURCE, candidate, ignore=ignore, symlinks=True)
        after = (candidate / name).read_text(encoding='utf-8-sig')
        postimages = {name: sha(candidate / name)}

    # --- static ---
    klass = adapter.CLASS
    code = '\n'.join(line for line in klass.splitlines() if not line.strip().startswith('//'))
    check(after.count(klass) == 1, 'the classes are appended once')
    create = body(after, 'public static IPreciseSleepEvent CreateEvent()')
    check(create.index('if (DarwinTimedWait.Applies)') < create.index('return new DarwinSleepEvent();') < create.index('return new NanosleepEvent();'),
          'CreateEvent: the Darwin event on Apple platforms only, the previous choice otherwise')
    spin = body(after, 'public static void SpinWaitUntilTimePoint(long timePoint)')
    check(spin.index('if (DarwinTimedWait.Applies)') < spin.index('DarwinTimedWait.WaitUntil(timePoint);') < spin.index('while (PerformanceCounter.ElapsedTicks < timePoint)'),
          'the compositor\'s spin: a timed sleep first on Apple platforms, then the same loop (it finishes an early wake)')
    check('System.OperatingSystem.IsIOS() || System.OperatingSystem.IsMacOS()' in klass, 'Applies is Apple platforms')
    sleep_until = body(klass, 'public bool SleepUntil(long timePoint)')
    check(re.search(r'if \(ns <= 0\)\s*\{\s*return false;\s*\}', sleep_until) and sleep_until.count('return true;') == 1 and
          sleep_until.index('dispatch_semaphore_wait') < sleep_until.index('Consume();') < sleep_until.index('return true;'),
          'SleepUntil: false only for a deadline already reached; otherwise one timed wait, then the signal consumed')
    signal = body(klass, 'public void Signal()')
    check('Interlocked.Exchange(ref _signalled, 1) == 0' in signal and signal.count('dispatch_semaphore_signal') == 1 and
          signal.index('if (references == 0)') < signal.index('CompareExchange(ref _references') < signal.index('dispatch_semaphore_signal') <
          signal.index('Release();'), 'a signal posts once until a wait consumes it, holding a reference; none after Dispose')
    consume = body(klass, 'private void Consume()')
    check(consume.index('dispatch_semaphore_wait(_semaphore, DarwinTimedWait.TimeNow)') < consume.index('Interlocked.Exchange(ref _signalled, 0)'),
          'the waiter takes any count left, then clears the mark (a signal after the clear posts again)')
    check('Interlocked.Exchange(ref _disposed, 1) == 0' in body(klass, 'public void Dispose()') and
          body(klass, 'private void Release()').count('dispatch_release(_semaphore)') == 1 and klass.count('dispatch_release(') == 2,
          'the semaphore is released once, by the last of Dispose and the signals in progress')
    check('pthread_set_qos' not in code and 'Priority' not in code and 'new System.Threading.Thread' not in code and 'Thread.Sleep' not in code,
          'no thread, class or sleep of its own')

    # --- built ---
    warnings = []
    for project in ('Ryujinx.Common', 'Ryujinx.HLE'):
        out = run([DOTNET, 'build', str(candidate / f'src/{project}/{project}.csproj'), '-c', 'Release', '-nologo', '-m:1',
                   '-p:NuGetAudit=false'], candidate)
        check(' error ' not in out, f'production {project} assembly builds')
        warnings += sorted(set(line.split(': warning ')[1].split(':')[0] for line in out.splitlines()
                               if ': warning ' in line and 'PreciseSleepHelper.cs' in line))
    check(not warnings, 'no warning in PreciseSleepHelper.cs: %s' % warnings)

    # --- executed ---
    proto = protocol(temporary / 'protocol')
    control = fixture(temporary / 'fx-control', control_tree)
    result = fixture(temporary / 'fx-candidate', candidate)

print(json.dumps({'control': {k: v for k, v in control.items() if k != 'runs'}, 'candidate': {k: v for k, v in result.items() if k != 'runs'}}), flush=True)

print(json.dumps({'protocol': proto}), flush=True)
sem, disposal = proto['semantics'], proto['dispose']
check(sem['pastIsFalse'] and sem['slept'] and 29 <= sem['timedMs'] <= 80 and sem['signalledMs'] < 5 and sem['afterCoalescedMs'] >= 25 and
      sem['unchangedTimePoint'], 'protocol: a reached deadline returns false; a 30 ms wait ends at its deadline; a prior signal ends '
      'a wait at once; signals made while none is consumed count once; the time point is not adjusted: %s' % sem)
check(disposal['created'] == disposal['released'] == 5000 and disposal['misuses'] == 0 and disposal['exceptions'] == 0,
      'protocol: signals racing Dispose: no exception, no use after release, one release per event: %s' % disposal)
check(all(row['lost'] == 0 and row['signals'] == 1_000_000 and row['waiterEnded'] for row in proto['lost']),
      'protocol: no lost signal (3 x 1 000 000 signals from two producers, each seen within 200 ms): %s' % proto['lost'])
ct, rt, cv, rv = control['timers'], result['timers'], control['vsync'], result['vsync']
check(ct['event'] == 'NanosleepEvent', 'the control\'s timer event is NanosleepEvent')
check(ct['deadlines'] >= 500 and rt['deadlines'] >= 500 and cv['frames'] >= 60 and rv['frames'] >= 60, 'deadlines fire and frames compose in both')
if APPLE:
    check(rt['event'] == 'DarwinSleepEvent' and rt['helperThreads'] == 0 and ct['helperThreads'] > 0,
          'Apple host: the candidate\'s timer event is DarwinSleepEvent and starts no helper thread (control: %s)' % ct['helperThreads'])
    check(rt['latenessUsP50'] <= ct['latenessUsP50'] + 100 and rt['latenessUsP90'] <= ct['latenessUsP90'] + 100,
          'Apple host: deadline lateness p50/p90 within 100 us of the control\'s or below: %s' % {'control': ct, 'candidate': rt})
    check(rt['cpuUsPerDeadline'] < ct['cpuUsPerDeadline'],
          'Apple host: less CPU per deadline (%.2f against %.2f us)' % (rt['cpuUsPerDeadline'], ct['cpuUsPerDeadline']))
    check(rv['cpuUsPerFrame'] < cv['cpuUsPerFrame'] and rv['latenessUsP90'] <= cv['latenessUsP90'] + 100,
          'Apple host: the compositor spends less CPU per frame (%.2f against %.2f us), lateness p90 within 100 us: %s'
          % (rv['cpuUsPerFrame'], cv['cpuUsPerFrame'], {'control': cv, 'candidate': rv}))
else:
    check(rt['event'] == ct['event'] == 'NanosleepEvent' and rt['helperThreads'] > 0 and ct['helperThreads'] > 0,
          'another host: the candidate takes the control\'s path (the same event, with its helper threads: %s against %s)'
          % (rt['helperThreads'], ct['helperThreads']))

inputs = ['build-utils/melonx/adapt_darwin_timed_waits.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_darwin_timed_waits_test.py',
          'test/melonx_darwin_timed_waits/Program.cs', 'test/melonx_darwin_timed_waits/protocol/Program.cs',
          'test/melonx_adapter_control.py']
report = {
    'result': 'passed', 'checks': checks, 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'postimages': postimages, 'physicalDeviceTested': False, 'productionAssembliesBuilt': True, 'host': platform.system(),
    'appleExecuted': APPLE, 'sourceBaseline': adapter.BASELINE, 'control': control, 'candidate': result, 'protocol': proto,
    'noLostSignal': True, 'signalAfterDisposeSafe': True,
    'deviceEvidence': 'IPA 733 Hogwarts Legacy (private journal, pid 61839): HLE.TimeManager 3.0 %, Common.Nanosleep.* 2.5 %, '
                      'SurfaceFlinger.Composer 0.6 % of a core over 44 s of play, user-interactive',
    'inputs': {path: sha(ROOT / path) for path in inputs},
    'limitation': 'The fixture drives the production timing files with loops copied from KTimeManager and SurfaceFlinger. The '
                  'Apple path is executed on macOS only; the iPhone\'s timer behaviour and the energy saved are read from the '
                  'next IPA\'s per-thread CPU and audio counters.',
}
out = ROOT / 'dist/melonx/darwin-timed-waits-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} darwin timed waits checks on {platform.system()}')
