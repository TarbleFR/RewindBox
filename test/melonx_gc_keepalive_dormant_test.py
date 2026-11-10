#!/usr/bin/env python3
"""adapt_gc_keepalive_dormant on the final preparation, against the Core 721 preparation as control (F1).

Usage: melonx_gc_keepalive_dormant_test.py <control> --candidate-source <final preparation containing the adapter>

Independent review of Core 719 (main, F1): a 12-16 s window whose every request is refused for fragmentation (above
0.48, adapt_bgc_fragmentation_guard) closes and leaves the keep-alive dormant until the runtime's own next background
gen2, silently, counted as a fragmented skip only. The candidate says it once per window (gcKeepAlive dormant, at most
4 lines) and counts it apart, without any other change. Both production Ryujinx.Library assemblies build. The
candidate's and the control's real BackgroundGcKeepAlive classes run their loops on fake seams
(test/melonx_gc_keepalive_dormant/Program.cs): (1) the ratio held above the limit for 20 s from the window's start,
then low, then the runtime's own background gen2 (both: no request while dormant, one request a window after the record
changed; candidate only: one dormant line, the summary's dormant count 1 and windows missed 0); (2) the fragmentation
falls inside the window: the request is made, nothing dormant; (3) a window missed without a refusal: a miss, not
dormant (control and candidate count it alike); (4) six refused windows: six dormant, four lines. Source: only the
keep-alive class changes, the only collection is still the non-blocking request. Host runtime, not an iPhone.
Writes dist/melonx/gc-keepalive-dormant-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_gc_keepalive_dormant', _HOLD)
import adapt_gc_keepalive_dormant as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
MARKER = '// RewindBox (adapt_bgc_keepalive): keeps the workstation background GC thread'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 721 preparation: ' + name)

texts = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-gc-keepalive-dormant-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
            try:
                adapter.apply(work)
                refused = False
            except AssertionError:
                refused = True
            check(refused, 'fail closed: an adapted tree is refused')
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_gc_keepalive_dormant')
                for name in adapter.BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = (work / adapter.SESSION).read_text(encoding='utf-8-sig')
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800,
                                env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Library assembly builds')

    control, candidate = texts['control'], texts['candidate']
    restored = candidate
    for old, new in reversed(adapter.PAIRS):
        check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:60])
        restored = restored.replace(new, old)
    check(restored == control, 'nothing else in the file changes')
    klass, control_class = candidate[candidate.index(MARKER):], control[control.index(MARKER):]
    check(klass.count('GC.Collect(') == 1 and 'GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false)' in klass,
          'the only collection is still the non-blocking request')
    check('lock (' not in klass and '.Wait(' not in klass and 'GCSettings' not in klass, 'no lock, wait or GC setting')
    loop = klass[klass.index('    private static void Loop(Run run)'):]
    check(loop.count('refusedThisWindow = false;') == 4 and 'bool refusedThisWindow = false;' in loop and loop.count('refusedThisWindow = true;') == 1 and
          loop.index('case Decision.Fragmented:') < loop.index('refusedThisWindow = true;') < loop.index('case Decision.Induce:'),
          'set by a fragmented refusal; cleared by a record change, a request and the dormant line')
    check(loop.count('"gcKeepAlive", "dormant"') == 1 and '++run.Dormant <= MaxDormantLines' in loop, 'one bounded line kind')

    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    program = (ROOT / 'test/melonx_gc_keepalive_dormant/Program.cs').read_text()
    (fixture / 'Program.cs').write_text(program.replace('//__CANDIDATE__\n', klass + '\n').replace('//__CONTROL__\n', control_class + '\n'))
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit></PropertyGroup></Project>\n')
    for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                    [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
print(json.dumps(report)[:3000], flush=True)


def summary(run):
    lines = [line for line in run['journal'] if line.startswith('gcKeepAlive/summary: ')]
    check(len(lines) == 1, 'one summary: ' + str(run['journal']))
    return lines[0]


def dormant(run):
    return [line for line in run['journal'] if line.startswith('gcKeepAlive/dormant: ')]


check(report['maxDormantLines'] == 4 and abs(report['limit'] - 0.48) < 1e-9, 'bounds')
c, k = report['controlHold'], report['candidateHold']
for name, run in (('control', c), ('candidate', k)):
    check(run['requests'] == 1 and run['requestsCounted'] == 1, name + ': no request while dormant, one a window after the record changed: ' + str(run))
    check('fragmented skips 1,' in summary(run) or 'fragmented skips 1 ' in summary(run), name + ': one fragmented skip: ' + summary(run))
    check('windows missed 0,' in summary(run), name + ': the refused window is not a miss: ' + summary(run))
check(dormant(c) == [] and 'dormant after' not in summary(c), 'control: silent (the F1 finding reproduced): ' + str(c['journal']))
check(len(dormant(k)) == 1 and 'fragmentation 0.600 above 0.48' in dormant(k)[0] and
      "no request until the runtime's next background gen2" in dormant(k)[0], 'candidate: one dormant line: ' + str(k['journal']))
check('dormant after a fragmented skip 1 ' in summary(k), 'candidate: counted apart: ' + summary(k))
r = report['candidateRecovers']
check(r['requests'] == 2 and dormant(r) == [] and 'dormant after a fragmented skip 0 ' in summary(r) and 'fragmented skips 1,' in summary(r),
      'fragmentation falling inside the window: requests made, nothing dormant: ' + str(r))
m, mc = report['candidateMissed'], report['controlMissed']
check(m['requests'] == 0 and dormant(m) == [] and 'windows missed 1,' in summary(m) and 'dormant after a fragmented skip 0 ' in summary(m),
      'a plain miss is a miss, not dormant: ' + str(m))
check(mc['requests'] == 0 and 'windows missed 1,' in summary(mc), 'the control counts the plain miss alike: ' + str(mc))
b = report['candidateBound']
check(b['requests'] == 0 and len(dormant(b)) == 4 and 'dormant after a fragmented skip 6 ' in summary(b) and 'fragmented skips 6,' in summary(b),
      'six refused windows: six dormant, four lines: ' + str(b))

inputs = ['build-utils/melonx/adapt_gc_keepalive_dormant.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_gc_keepalive_dormant_test.py', 'test/melonx_gc_keepalive_dormant/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core721Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               report=report, sdk=sdk, physicalDeviceTested=False, productionLibraryAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               comparison=dict(controlSilentWhenDormant=True, candidateDormantLines=1, candidateDormantCounted=1,
                               refusedWindowNotAMiss=True, plainMissCounted=True, dormantLinesBounded=4, requestsUnchanged=True),
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/gc-keepalive-dormant-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
