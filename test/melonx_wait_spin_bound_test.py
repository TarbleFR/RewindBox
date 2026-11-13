#!/usr/bin/env python3
"""adapt_wait_spin_bound on the final preparation, against its predecessor as control.

Usage: melonx_wait_spin_bound_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]
       melonx_wait_spin_bound_test.py --fixture-only   (the executed part and its checks, no preparation)

IPA 733 / Core 745, Hogwarts Legacy: 46-48 % of the busiest threads' running samples spin before a wait, 44 % of all
samples inside the spin's yield; the waits are the guest scheduler's KThread.SchedulerWaitEvent and the threaded
renderer's _galWorkAvailable and _invokeRun, ManualResetEventSlim at the runtime's default spin.

Static: only AsyncWorkQueue.cs (the class appended), KThread.cs and ThreadedRenderer.cs change, each replacement once
and reversing to the control; the three events are the class and no other ManualResetEventSlim changes; the class's
wait returns only after its event is observed set (inside the spin) or after the underlying event's own Wait, whose
spin is 0; its default spin is the runtime's (35) and its reduced spin the pause iterations (10); Set reads the clock
only while a waiter blocks; the decision state is written only by the waiter.
Built: the production Ryujinx.Common, Ryujinx.Graphics.GAL and Ryujinx.HLE of the candidate.
Executed (test/melonx_wait_spin_bound/Program.cs with the adapter's class text, unchanged; three runs per point,
medians): two threads handing over as KScheduler does, with the control's event and the candidate's:
- partner answers in 1 or 5 us (the spin's yields pay): the candidate keeps the full spin and at least 80 % of the
  control's handoffs per second;
- partner answers in 40 or 300 us (both block): the candidate drops to the pause iterations and spends at least 15 %
  less CPU per handoff beyond the work, at 90 % or more of the control's handoffs per second;
- half short and half long slices: at 90 % or more of the control's handoffs per second;
- a ring of eight threads with slices of 0-300 us: no lost wakeup (laps made, every thread ends), one token holder
  at a time; a wait on an event nobody sets stays blocked, and returns after Set.
This measures the mechanism on the host's scheduler; what it saves on the iPhone is read from the next IPA's sw=,
en=, cpu= and [MeloNX:hot] lines.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, statistics, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import adapt_wait_spin_bound as adapter  # noqa: E402

FIXTURE_ONLY = '--fixture-only' in sys.argv
FINAL_PREPARATION = False
if not FIXTURE_ONLY:
    SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
    from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
    _HOLD = []
    FINAL_SOURCE = SOURCE
    SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_wait_spin_bound', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
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


POINTS = (('short1', 1, 1, 100), ('short5', 5, 5, 100), ('long40', 40, 40, 100), ('long300', 300, 300, 100), ('mixed', 1, 200, 50))


def execute(temporary):
    fixture = temporary / 'fixture'
    fixture.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_wait_spin_bound/Program.cs', fixture / 'Program.cs')
    (fixture / 'Class.cs').write_text('namespace Ryujinx.Common\n{\n' + adapter.CLASS + '}\n', encoding='utf-8')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><InvariantGlobalization>true</InvariantGlobalization>'
        '<NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection></PropertyGroup></Project>\n')
    run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-v', 'q', '-o', str(fixture / 'out')], fixture)
    probe = [DOTNET, str(fixture / 'out/Fixture.dll')]
    results = {}
    for name, short, long, share in POINTS:
        for kind in ('control', 'adaptive'):
            runs = [json.loads(run(probe + [kind, str(short), str(long), str(share), '1200'], fixture).strip().splitlines()[-1]) for _ in range(3)]
            results[(name, kind)] = {
                'handoffsPerSecond': statistics.median(r['handoffsPerSecond'] for r in runs),
                'overheadCpuUsPerHandoff': statistics.median(r['overheadCpuUsPerHandoff'] for r in runs),
                'voluntarySwitchesPerHandoff': statistics.median(r['voluntarySwitchesPerHandoff'] for r in runs),
                'wakeUsP50': statistics.median(r['wakeUsP50'] for r in runs),
                'wakeUsP99': statistics.median(r['wakeUsP99'] for r in runs),
                'spinBudgets': [r.get('spinBudgets') for r in runs],
            }
    ring = json.loads(run(probe + ['ring', '1500'], fixture).strip().splitlines()[-1])
    return results, ring


ignore = shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX')
if FIXTURE_ONLY:
    with tempfile.TemporaryDirectory(prefix='melonx-wait-spin-bound-') as temporary:
        results, ring = execute(Path(temporary).resolve())
else:
    with tempfile.TemporaryDirectory(prefix='melonx-wait-spin-bound-') as temporary:
        temporary = Path(temporary).resolve()
        candidate = temporary / 'candidate'
        shutil.copytree(SOURCE, candidate, ignore=ignore, symlinks=True)
        for name, digest in adapter.BASELINE.items():
            check(sha(candidate / name) == digest, 'control is the predecessor\'s output: ' + name)
        before = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
        changed = adapter.apply(candidate)
        check(sorted(str(path.relative_to(candidate)) for path in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
        try:
            adapter.apply(candidate)
            refused = False
        except AssertionError:
            refused = True
        check(refused, 'fail closed: an adapted tree is refused')
        after = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
        for name, pairs in adapter.FILE_PAIRS.items():
            restored = after[name]
            for old, new in reversed(pairs):
                check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
                restored = restored.replace(new, old)
            check(restored == before[name], 'nothing else changes in ' + name)

        postimages = {}
        if FINAL_PREPARATION:
            later = files_edited_later('adapt_wait_spin_bound')
            for name, pairs in adapter.FILE_PAIRS.items():
                final_text = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
                for _, new in pairs:
                    check(final_text.count(new) == 1, 'replacement in the final preparation: ' + new.strip().splitlines()[0][:70])
                if name not in later:
                    check((candidate / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
            shutil.rmtree(candidate)
            shutil.copytree(FINAL_SOURCE, candidate, ignore=ignore, symlinks=True)
            after = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
            postimages = {name: sha(candidate / name) for name in adapter.BASELINE}

        # --- static ---
        klass = adapter.CLASS
        common, thread, renderer = after[adapter.COMMON], after[adapter.THREAD], after[adapter.RENDERER]
        check(common.count(klass) == 1 and common.rstrip().endswith('}') and 'namespace Ryujinx.Common' in common,
              'the class is appended once inside Ryujinx.Common\'s namespace')
        check('PauseIterations = 10;' in klass and 'FullIterations = 35;' in klass and 'ManualResetEventSlim(initialState, 0)' in klass,
              'the default spin is the runtime\'s (35), the reduced one the pause iterations (10); the underlying event does not spin')
        wait = body(klass, 'public void Wait()')
        returns = [m.start() for m in re.finditer(r'\breturn;', wait)]
        check(len(returns) == 2 and wait.index('if (_event.IsSet)') < returns[0] and
              wait.rindex('if (_event.IsSet)', 0, returns[1]) < returns[1] and wait.index('_event.Wait();') > returns[1],
              'a wait returns only after seeing its event set, or after the underlying event\'s Wait')
        code = '\n'.join(line for line in klass.splitlines() if not line.strip().startswith('//'))
        check(wait.count('_event.Wait();') == 1 and 'Thread.Sleep(' not in code and 'Timeout' not in code and 'CancellationToken' not in code,
              'one blocking wait without a timeout; nothing else changes how a wait ends')
        set_body = body(klass, 'public void Set()')
        check(set_body.index('Volatile.Read(ref _blocking) != 0') < set_body.index('Stopwatch.GetTimestamp()') and
              set_body.strip('{} \n').endswith('_event.Set();'), 'Set reads the clock only while a waiter blocks, then sets')
        check('_score' not in set_body and 'public void Reset() => _event.Reset();' in klass and
              all(m.start() > klass.index('public void Wait()') for m in re.finditer(r'_score = ', klass)),
              'only the waiter writes the decision state')
        check(re.search(r'private Ryujinx\.Common\.AdaptiveSpinEvent _schedulerWaitEvent;', thread) and
              'public Ryujinx.Common.AdaptiveSpinEvent SchedulerWaitEvent => _schedulerWaitEvent;' in thread and
              'Ryujinx.Common.AdaptiveSpinEvent schedulerWaitEvent = new(false);' in thread,
              'the guest scheduler\'s event is the class')
        check('internal readonly ManualResetEventSlim DebugHalt' in thread, 'the debugger\'s halt event is unchanged')
        check('readonly Ryujinx.Common.AdaptiveSpinEvent _galWorkAvailable;' in renderer and 'readonly Ryujinx.Common.AdaptiveSpinEvent _invokeRun;' in renderer and
              renderer.count('ManualResetEventSlim') == before[adapter.RENDERER].count('ManualResetEventSlim') - 4,
              'the renderer\'s work and invoke events are the class; its other events are unchanged')

        # --- built ---
        warnings = []
        for project in ('Ryujinx.Common', 'Ryujinx.Graphics.GAL', 'Ryujinx.HLE'):
            out = run([DOTNET, 'build', str(candidate / f'src/{project}/{project}.csproj'), '-c', 'Release', '-nologo', '-m:1',
                       '-p:NuGetAudit=false'], candidate)
            check(' error ' not in out, f'production {project} assembly builds')
            warnings += sorted(set(line.split(': warning ')[1].split(':')[0] for line in out.splitlines()
                                   if ': warning ' in line and any(Path(name).name in line for name in adapter.BASELINE)))
        check(not warnings, 'no warning in the changed files: %s' % warnings)

        # --- executed ---
        results, ring = execute(temporary)

print(json.dumps({f'{n}/{k}': v for (n, k), v in results.items()}), json.dumps(ring), flush=True)

c, a = results, None
def point(name, kind): return results[(name, kind)]
for name in ('short1', 'short5'):
    ctl, cand = point(name, 'control'), point(name, 'adaptive')
    check(cand['handoffsPerSecond'] >= 0.8 * ctl['handoffsPerSecond'] and all(b == [35, 35] for b in cand['spinBudgets']),
          f'{name}: the partner answers inside the spin: the candidate keeps the full spin and 80 % or more of the control\'s '
          f'handoffs per second ({cand["handoffsPerSecond"]:.0f} against {ctl["handoffsPerSecond"]:.0f}, budgets {cand["spinBudgets"]})')
for name in ('long40', 'long300'):
    ctl, cand = point(name, 'control'), point(name, 'adaptive')
    check(all(b == [10, 10] for b in cand['spinBudgets']) and cand['overheadCpuUsPerHandoff'] <= 0.85 * ctl['overheadCpuUsPerHandoff'] and
          cand['handoffsPerSecond'] >= 0.9 * ctl['handoffsPerSecond'],
          f'{name}: both block: the candidate keeps the pause iterations and spends 15 % or more less CPU per handoff beyond the work '
          f'({cand["overheadCpuUsPerHandoff"]:.2f} against {ctl["overheadCpuUsPerHandoff"]:.2f} us) at 90 % or more of the handoffs '
          f'({cand["handoffsPerSecond"]:.0f} against {ctl["handoffsPerSecond"]:.0f})')
ctl, cand = point('mixed', 'control'), point('mixed', 'adaptive')
check(cand['handoffsPerSecond'] >= 0.9 * ctl['handoffsPerSecond'],
      f'mixed slices: 90 % or more of the control\'s handoffs ({cand["handoffsPerSecond"]:.0f} against {ctl["handoffsPerSecond"]:.0f})')
check(ring['joined'] and ring['laps'] >= 50 and ring['maxHolders'] == 1 and ring['unsetStayedBlocked'] and ring['returnedAfterSet'],
      'ring of eight threads: no lost wakeup, one holder at a time; a wait on an unset event stays blocked and returns at Set: %s' % ring)

if FIXTURE_ONLY:
    print(f'PASS {checks} wait spin bound fixture checks on {platform.system()} {platform.machine()}')
    raise SystemExit(0)

saving = {name: round(1 - point(name, 'adaptive')['overheadCpuUsPerHandoff'] / point(name, 'control')['overheadCpuUsPerHandoff'], 3)
          for name in ('long40', 'long300')}
inputs = ['build-utils/melonx/adapt_wait_spin_bound.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_wait_spin_bound_test.py',
          'test/melonx_wait_spin_bound/Program.cs', 'test/melonx_adapter_control.py']
report = {
    'result': 'passed', 'checks': checks, 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'postimages': postimages, 'physicalDeviceTested': False, 'productionAssembliesBuilt': True, 'host': platform.system(),
    'sourceBaseline': adapter.BASELINE, 'shortHandoffsKeptFullSpin': True, 'ringNoLostWakeup': True,
    'overheadCpuSavedLongHandoffs': saving, 'results': {f'{n}/{k}': v for (n, k), v in results.items()}, 'ring': ring,
    'deviceEvidence': 'IPA 733 Hogwarts Legacy (private journal, pid 61839, session 4AC66D23): 46-48 % of the busiest threads\' '
                      'running samples spinning before a wait, 44 % of all [MeloNX:hot] samples in the spin\'s yield; '
                      '150 000 system calls and 69 600 context switches per second; CPU 2.06 W',
    'inputs': {path: sha(ROOT / path) for path in inputs},
    'limitation': 'Host: the mechanism with the runtime\'s ManualResetEventSlim and the adapter\'s class on the host\'s '
                  'scheduler. The energy saved on the iPhone, and that frame pacing is unchanged, are read from the next IPA.',
}
out = ROOT / 'dist/melonx/wait-spin-bound-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} wait spin bound checks')
