#!/usr/bin/env python3
"""adapt_darwin_spin_yield on the final preparation, against its predecessor as control.

Usage: melonx_darwin_spin_yield_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]
       melonx_darwin_spin_yield_test.py --fixture-only   (the executed part and its checks, with the final class text
                                                         read from --candidate-source when given)

IPA 740 / Core da2525a1, Hogwarts Legacy: 26.2 % of the slow threads' running samples in AdaptiveSpinEvent's yield,
caught at pth_curpri 0 by [MeloNX:stall]: on Apple platforms Thread.Yield is sched_yield, swtch_pri(0) in XNU.

Static: only AsyncWorkQueue.cs changes, each replacement once and reversing to the control; the flag is the Apple
platforms only; the P/Invoke is libSystem's thread_switch(uint, int, uint) called as (MACH_PORT_NULL,
SWITCH_OPTION_NONE, 0); a failed call clears the flag and makes SpinWait's own yield; Wait and Calibrate count their
iterations through the one helper, and every SpinWait.SpinOnce is the helper's; the class's other text (the decision,
the bound, the block, Set) is the wait-spin-bound adapter's.
Built: the production Ryujinx.Common, Ryujinx.Graphics.GAL and Ryujinx.HLE of the final preparation, no warning in the
changed file.
Executed: the wait-spin-bound fixture (test/melonx_wait_spin_bound/Program.cs) with the final class text and the same
points and criteria as the wait-spin-bound gate (on this Linux host the flag is false: SpinWait's iterations); a probe
of the class in the same assembly: two threads hand over 2 000 times through two events with a 3 us partner, as the
platform sets the flag and with the flag forced on (on a host without thread_switch the first yield clears it and the
handoffs complete; on macOS the flag stays set and the handoffs complete).
What it changes on the iPhone is read from the next IPA's [MeloNX:stall] and [MeloNX:hot] lines.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, statistics, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import adapt_darwin_spin_yield as adapter  # noqa: E402
import adapt_wait_spin_bound as bound  # noqa: E402

FIXTURE_ONLY = '--fixture-only' in sys.argv
FINAL_PREPARATION = False
CANDIDATE = Path(sys.argv[sys.argv.index('--candidate-source') + 1]).resolve() if '--candidate-source' in sys.argv else None
if not FIXTURE_ONLY:
    SOURCE = CANDIDATE or Path(sys.argv[1]).resolve()
    from melonx_adapter_control import control_source  # noqa: E402
    _HOLD = []
    FINAL_SOURCE = SOURCE
    SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_darwin_spin_yield', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    if not condition:
        raise SystemExit('FAIL: ' + message)
    checks += 1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, timeout=2400):
    result = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    if result.returncode != 0:
        raise SystemExit('FAIL: command failed: ' + ' '.join(map(str, command)) + '\n' + result.stdout[-4000:])
    return result.stdout


def body(text, signature):
    start = text.index(signature)
    open_brace = text.index('{', start)
    depth = 0
    for index in range(open_brace, len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[open_brace:index + 1]
    raise SystemExit('FAIL: unbalanced ' + signature)


def final_class(text):
    """The AdaptiveSpinEvent class of a prepared AsyncWorkQueue.cs, as the wait-spin-bound adapter appends it."""
    start = text.index('    // RewindBox (adapt_wait_spin_bound)')
    declaration = text.index('    public sealed class AdaptiveSpinEvent')
    braces = body(text, '    public sealed class AdaptiveSpinEvent')
    end = text.index(braces, declaration) + len(braces)
    return text[start:end] + '\n'


POINTS = (('short1', 1, 1, 100), ('short5', 5, 5, 100), ('long100', 100, 100, 100), ('long300', 300, 300, 100),
          ('mixed', 1, 200, 50))

PROBE = r'''using System;
using System.Diagnostics;
using System.Threading;

namespace Ryujinx.Common
{
    static class Probe
    {
        static void Work(double us)
        {
            long end = Stopwatch.GetTimestamp() + (long)(us * Stopwatch.Frequency / 1_000_000);
            while (Stopwatch.GetTimestamp() < end) { }
        }

        static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "force") AdaptiveSpinEvent.YieldWithoutDepression = true;
            bool before = AdaptiveSpinEvent.YieldWithoutDepression;
            var ping = new AdaptiveSpinEvent(false);
            var pong = new AdaptiveSpinEvent(false);
            const int Rounds = 2000;
            int answered = 0;
            var partner = new Thread(() =>
            {
                for (int i = 0; i < Rounds; i++) { ping.Wait(); ping.Reset(); Work(3); answered++; pong.Set(); }
            });
            partner.Start();
            var clock = Stopwatch.StartNew();
            int done = 0;
            for (int i = 0; i < Rounds; i++) { ping.Set(); pong.Wait(); pong.Reset(); done++; }
            bool joined = partner.Join(30000);
            Console.WriteLine("{\"before\":" + (before ? "true" : "false") + ",\"after\":" +
                (AdaptiveSpinEvent.YieldWithoutDepression ? "true" : "false") + ",\"done\":" + done + ",\"answered\":" + answered +
                ",\"joined\":" + (joined ? "true" : "false") + ",\"ms\":" + clock.Elapsed.TotalMilliseconds.ToString("F1",
                System.Globalization.CultureInfo.InvariantCulture) + "}");
            return 0;
        }
    }
}
'''

PROJECT = ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
           '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><InvariantGlobalization>true</InvariantGlobalization>'
           '<NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection></PropertyGroup></Project>\n')


def execute(temporary, klass):
    fixture = temporary / 'fixture'
    fixture.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_wait_spin_bound/Program.cs', fixture / 'Program.cs')
    (fixture / 'Class.cs').write_text('namespace Ryujinx.Common\n{\n' + klass + '}\n', encoding='utf-8')
    (fixture / 'Fixture.csproj').write_text(PROJECT)
    run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-v', 'q', '-o', str(fixture / 'out')], fixture)
    fixture_run = [DOTNET, str(fixture / 'out/Fixture.dll')]
    results = {}
    for name, short, long, share in POINTS:
        for kind in ('control', 'adaptive'):
            runs = [json.loads(run(fixture_run + [kind, str(short), str(long), str(share), '1200'], fixture).strip().splitlines()[-1])
                    for _ in range(5)]
            results[(name, kind)] = {
                'handoffsPerSecond': statistics.median(r['handoffsPerSecond'] for r in runs),
                'overheadCpuUsPerHandoff': statistics.median(r['overheadCpuUsPerHandoff'] for r in runs),
                'spinBudgets': [r.get('spinBudgets') for r in runs],
                'fullSpinUs': [r.get('fullSpinUs') for r in runs],
            }
    ring = json.loads(run(fixture_run + ['ring', '1500'], fixture).strip().splitlines()[-1])
    probe = temporary / 'probe'
    probe.mkdir()
    (probe / 'Probe.cs').write_text(PROBE, encoding='utf-8')
    (probe / 'Class.cs').write_text('namespace Ryujinx.Common\n{\n' + klass + '}\n', encoding='utf-8')
    (probe / 'Probe.csproj').write_text(PROJECT)
    run([DOTNET, 'build', str(probe / 'Probe.csproj'), '-c', 'Release', '-nologo', '-v', 'q', '-o', str(probe / 'out')], probe)
    probes = {mode: json.loads(run([DOTNET, str(probe / 'out/Probe.dll')] + ([mode] if mode == 'force' else []), probe)
                               .strip().splitlines()[-1]) for mode in ('platform', 'force')}
    return results, ring, probes


ignore = shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX')
postimages = {}
with tempfile.TemporaryDirectory(prefix='melonx-darwin-spin-yield-') as temporary:
    temporary = Path(temporary).resolve()
    if FIXTURE_ONLY:
        if CANDIDATE:
            klass = final_class((CANDIDATE / adapter.COMMON).read_text(encoding='utf-8-sig'))
        else:
            tree = temporary / 'tree'
            (tree / adapter.COMMON).parent.mkdir(parents=True)
            (tree / adapter.COMMON).write_text('namespace Ryujinx.Common\n{\n' + bound.CLASS + '}\n', encoding='utf-8')
            for old, new in adapter.PAIRS:
                text = (tree / adapter.COMMON).read_text(encoding='utf-8')
                check(text.count(old) == 1, 'the wait-spin-bound class holds the anchor: ' + old.strip().splitlines()[0][:70])
                (tree / adapter.COMMON).write_text(text.replace(old, new), encoding='utf-8')
            klass = final_class((tree / adapter.COMMON).read_text(encoding='utf-8'))
    else:
        candidate = temporary / 'candidate'
        shutil.copytree(SOURCE, candidate, ignore=ignore, symlinks=True)
        for name, digest in adapter.BASELINE.items():
            check(sha(candidate / name) == digest, 'control is the predecessor\'s output: ' + name)
        before = (candidate / adapter.COMMON).read_text(encoding='utf-8-sig')
        changed = adapter.apply(candidate)
        check([str(path.relative_to(candidate)) for path in changed] == [adapter.COMMON], 'adapter changed other files')
        try:
            adapter.apply(candidate)
            refused = False
        except AssertionError:
            refused = True
        check(refused, 'fail closed: an adapted tree is refused')
        after = (candidate / adapter.COMMON).read_text(encoding='utf-8-sig')
        restored = after
        for old, new in reversed(adapter.PAIRS):
            check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
            restored = restored.replace(new, old)
        check(restored == before, 'nothing else changes in ' + adapter.COMMON)
        if FINAL_PREPARATION:
            check((candidate / adapter.COMMON).read_bytes() == (FINAL_SOURCE / adapter.COMMON).read_bytes(),
                  'final preparation is the adapter: ' + adapter.COMMON)
        postimages = {adapter.COMMON: sha(candidate / adapter.COMMON)}

        # --- static ---
        klass = final_class(after)
        code = '\n'.join(line for line in klass.splitlines() if not line.strip().startswith('//'))
        check('internal static bool YieldWithoutDepression = System.OperatingSystem.IsIOS() || System.OperatingSystem.IsMacOS() ||'
              in klass and 'System.OperatingSystem.IsMacCatalyst() || System.OperatingSystem.IsTvOS();' in klass,
              'the flag is the Apple platforms only')
        check('[System.Runtime.InteropServices.DllImport("/usr/lib/libSystem.B.dylib")]\n        private static extern int '
              'thread_switch(uint threadName, int option, uint optionTime);' in klass and code.count('thread_switch(') == 2 and
              'thread_switch(0, 0, 0);' in code, 'libSystem\'s thread_switch, called once as (MACH_PORT_NULL, SWITCH_OPTION_NONE, 0)')
        helper = body(klass, 'private static void SpinOnce(ref System.Threading.SpinWait spinner, ref int count)')
        check(re.search(r'catch \(System\.Exception\)\s*\{\s*YieldWithoutDepression = false;\s*spinner\.SpinOnce\(sleep1Threshold: -1\);\s*\}',
                        helper) is not None, 'a failed call clears the flag and makes SpinWait\'s own yield')
        check(helper.count('count++;') == 1 and helper.rstrip('} \n').endswith('count++;') and
              'YieldWithoutDepression && count >= PauseIterations' in helper and '((count - PauseIterations) & 1) == 0' in helper,
              'the helper counts every iteration; the Apple yields start past the pause iterations, at every other one')
        check(code.count('spinner.SpinOnce(sleep1Threshold: -1);') == 2 and helper.count('spinner.SpinOnce(sleep1Threshold: -1);') == 2,
              'every SpinWait.SpinOnce is the helper\'s')
        wait, calibrate = body(klass, 'public void Wait()'), body(klass, 'private static void Calibrate()')
        check(wait.count('SpinOnce(ref spinner, ref count);') == 1 and 'while (count < budget)' in wait and
              'if (count == PauseIterations)' in wait and 'spinner.Count' not in wait,
              'Wait counts its iterations through the helper')
        check(calibrate.count('SpinOnce(ref spinner, ref count);') == 2 and 'while (count < PauseIterations)' in calibrate and
              'while (count < FullIterations)' in calibrate and 'spinner.Count' not in calibrate,
              'Calibrate times the same iterations as Wait')
        original = bound.CLASS
        for old, new in adapter.PAIRS:
            check(original.count(old) == 1, 'the anchor is in the wait-spin-bound class: ' + old.strip().splitlines()[0][:70])
            original = original.replace(old, new)
        check(klass.endswith(original) or original in klass, 'the rest of the class is the wait-spin-bound adapter\'s')

        # --- built ---
        shutil.rmtree(candidate)
        shutil.copytree(FINAL_SOURCE, candidate, ignore=ignore, symlinks=True)
        warnings = []
        for project in ('Ryujinx.Common', 'Ryujinx.Graphics.GAL', 'Ryujinx.HLE'):
            out = run([DOTNET, 'build', str(candidate / f'src/{project}/{project}.csproj'), '-c', 'Release', '-nologo', '-m:1',
                       '-p:NuGetAudit=false'], candidate)
            check(' error ' not in out, f'production {project} assembly builds')
            warnings += sorted(set(line.split(': warning ')[1].split(':')[0] for line in out.splitlines()
                                   if ': warning ' in line and 'AsyncWorkQueue.cs' in line))
        check(not warnings, 'no warning in the changed file: %s' % warnings)

    # --- executed ---
    results, ring, probes = execute(temporary, klass)

print(json.dumps({f'{n}/{k}': v for (n, k), v in results.items()}), json.dumps(ring), json.dumps(probes), flush=True)


def point(name, kind):
    return results[(name, kind)]


for name, floor in (('short1', 0.8), ('short5', 0.75)):
    ctl, cand = point(name, 'control'), point(name, 'adaptive')
    check(cand['handoffsPerSecond'] >= floor * ctl['handoffsPerSecond'] and all(b == [35, 35] for b in cand['spinBudgets']),
          f'{name}: the partner answers inside the spin: the full spin kept and {floor:.0%} or more of the control\'s handoffs '
          f'({cand["handoffsPerSecond"]:.0f} against {ctl["handoffsPerSecond"]:.0f}, budgets {cand["spinBudgets"]})')
for name, reduced in (('long100', 1), ('long300', 5)):
    ctl, cand = point(name, 'control'), point(name, 'adaptive')
    check(sum(b == [10, 10] for b in cand['spinBudgets']) >= reduced and
          cand['overheadCpuUsPerHandoff'] <= 0.85 * ctl['overheadCpuUsPerHandoff'] and cand['handoffsPerSecond'] >= 0.9 * ctl['handoffsPerSecond'],
          f'{name}: both block: {reduced} or more runs end with the pause iterations, 15 % or more less CPU per handoff '
          f'({cand["overheadCpuUsPerHandoff"]:.2f} against {ctl["overheadCpuUsPerHandoff"]:.2f} us) at 90 % or more of the '
          f'handoffs ({cand["handoffsPerSecond"]:.0f} against {ctl["handoffsPerSecond"]:.0f}); budgets {cand["spinBudgets"]}')
ctl, cand = point('mixed', 'control'), point('mixed', 'adaptive')
check(cand['handoffsPerSecond'] >= 0.9 * ctl['handoffsPerSecond'],
      f'mixed slices: 90 % or more of the control\'s handoffs ({cand["handoffsPerSecond"]:.0f} against {ctl["handoffsPerSecond"]:.0f})')
check(ring['joined'] and ring['laps'] >= 50 and ring['stalls'] == 0 and ring['windows'] >= 6 and ring['maxHolders'] == 1 and
      ring['unsetStayedBlocked'] and ring['returnedAfterSet'], 'ring of eight threads: no lost wakeup, one holder at a time: %s' % ring)
apple = platform.system() == 'Darwin'
for mode, probe in probes.items():
    check(probe['done'] == 2000 and probe['answered'] == 2000 and probe['joined'], f'{mode}: every handoff completes: {probe}')
check(probes['platform']['before'] == apple and probes['platform']['after'] == apple,
      'the flag is the platform\'s (set on Apple, clear elsewhere) and stays so: %s' % probes['platform'])
check(probes['force']['before'] and probes['force']['after'] == apple,
      'forced on: kept where thread_switch binds (Apple), cleared at the first yield elsewhere: %s' % probes['force'])

if FIXTURE_ONLY:
    print(f'PASS {checks} darwin spin yield fixture checks on {platform.system()} {platform.machine()}')
    raise SystemExit(0)

inputs = ['build-utils/melonx/adapt_darwin_spin_yield.py', 'build-utils/melonx/adapt_wait_spin_bound.py',
          'build-utils/melonx/adapt_session.py', 'test/melonx_darwin_spin_yield_test.py',
          'test/melonx_wait_spin_bound/Program.cs', 'test/melonx_adapter_control.py']
report = {
    'result': 'passed', 'checks': checks, 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'postimages': postimages, 'physicalDeviceTested': False, 'productionAssembliesBuilt': True, 'host': platform.system(),
    'sourceBaseline': adapter.BASELINE, 'shortHandoffsKeptFullSpin': True, 'ringNoLostWakeup': True,
    'unboundExportFallsBack': not apple, 'results': {f'{n}/{k}': v for (n, k), v in results.items()}, 'ring': ring,
    'probes': probes,
    'deviceEvidence': 'IPA 740 Hogwarts Legacy (private journal, pid 5954): 855 of 3 258 running samples of the slow threads '
                      '(26.2 %) in AdaptiveSpinEvent\'s yield; [MeloNX:stall] samples in sched_yield at pth_curpri 0 for a '
                      'base of 31-47 while threads at 4 and 20 ran',
    'inputs': {path: sha(ROOT / path) for path in inputs},
    'limitation': 'Host (Linux): the flag is false, so the other platforms are shown unchanged and the fallback of an unbound '
                  'export is exercised; the thread_switch yield itself runs only on Apple platforms (macOS runner, iPhone). '
                  'What it saves on the iPhone is read from the next IPA.',
}
out = ROOT / 'dist/melonx/darwin-spin-yield-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} darwin spin yield checks')
