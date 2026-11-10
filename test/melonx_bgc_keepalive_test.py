#!/usr/bin/env python3
"""adapt_bgc_keepalive on the final preparation, against the Core 691 file as control.

Usage: melonx_bgc_keepalive_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 690/691: every in-play blocking gen2 fell back from a background one (148/557 ms, 151/439/718 ms), each more than
20 s after the previous background gen2: the .NET 10.0.0 workstation BGC thread had left after its 20 s idle wait and
its re-creation raced the start check. For control and candidate the production Ryujinx.Library assembly (which compiles the session file) is built. The
candidate's real BackgroundGcKeepAlive class, taken from the final preparation, runs in
test/melonx_bgc_keepalive/Program.cs: (1) its policy table (nothing before the session's first background gen2,
nothing before 12 s, a request from 12 to 16 s, nothing after 16 s, nothing under a 384 MiB heap); (2) its real loop on
fake seams (virtual clock, background record, heap): one request per window, none after a missed window, none after
Stop, the journal lines; (3) its real loop on the host .NET 10.0.0 runtime with a 448 MiB live heap for 45 s: its
requests are background collections (the background record advances, no blocking gen2 is added). Source: the session
start (after the diagnostics epoch, before the game loads) and stop (in the finally, after the epoch) wiring, the official GC call (blocking false, compacting false), no other collection, no lock or wait on
an emulator thread. Writes dist/melonx/bgc-keepalive-checks.json. No device; the device race itself is not reproduced.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_bgc_keepalive', _HOLD)
import adapt_bgc_keepalive as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 691 preparation: ' + name)

texts = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-bgc-keepalive-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in adapter.BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = (work / adapter.SESSION).read_text(encoding='utf-8-sig')
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Library assembly builds')

    control, candidate = texts['control'], texts['candidate']
    marker = '// RewindBox (adapt_bgc_keepalive): keeps the workstation background GC thread'
    check(marker not in control and candidate.count(marker) == 1, 'the class is the candidate\'s only addition')
    klass = candidate[candidate.index(marker):]
    check(klass.rstrip().endswith('}') and klass.count('public static class BackgroundGcKeepAlive') == 1, 'one class at the end')
    check(candidate.replace(adapter.START_NEW, adapter.START_OLD).replace(adapter.STOP_NEW, adapter.STOP_OLD)
          .replace(adapter.TAIL_NEW, adapter.TAIL_OLD) == control, 'nothing else in the file changes')
    check(klass.count('GC.Collect(') == 1 and 'GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false)' in klass,
          'the only collection is a non-blocking, non-compacting gen2 request')
    check('lock (' not in klass and '.Wait(' not in klass and 'Monitor.' not in klass, 'no lock or wait in the keep-alive')
    check('Priority = System.Threading.ThreadPriority.BelowNormal' in klass and 'IsBackground = true' in klass, 'its own background thread')
    start = candidate.index('EmbeddedPerformanceDiagnostics.Start(generation);')
    check(candidate.index('BackgroundGcKeepAlive.Start(generation);') == start + len('EmbeddedPerformanceDiagnostics.Start(generation);\n                ')
          and candidate.index('BackgroundGcKeepAlive.Start(generation);') < candidate.index('try { Load(options);'), 'started with the session, before the game loads')
    stop = candidate.index('EmbeddedPerformanceDiagnostics.Stop(generation);')
    check(candidate.index('BackgroundGcKeepAlive.Stop(generation);') == stop + len('EmbeddedPerformanceDiagnostics.Stop(generation);\n                    ')
          and candidate.count('BackgroundGcKeepAlive.Stop(generation);') == 1, 'stopped in the finally, right after the epoch')

    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    program = (ROOT / 'test/melonx_bgc_keepalive/Program.cs').read_text()
    (fixture / 'Program.cs').write_text(program.replace('//__CLASS__\n', klass + '\n'))
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection>'
        '<ConcurrentGarbageCollection>true</ConcurrentGarbageCollection></PropertyGroup></Project>\n')
    for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                    [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
print(json.dumps(report), flush=True)

policy = report['policy']
check(policy == {'none': 'NotSeen', '0': 'Wait', '11999': 'Wait', '12000': 'Induce', '16000': 'Induce', '16001': 'Missed',
                 '30000': 'Missed', '14000small': 'SmallHeap', '14000at384': 'Induce'}, 'policy table')
sim = report['simulated']
check(sim['beforeFirst'] == 0, 'nothing before the session\'s first background gen2')
check(sim['at11'] == 0, 'nothing 11 s after it')
check(sim['at14'] == 1 and 20_000 + 12_000 <= sim['firstAtMs'] <= 20_000 + 12_500, 'one request 12 s after it')
check(sim['second'] == 2 and 34_000 + 12_000 <= sim['secondAtMs'] <= 34_000 + 12_500, 'one more 12 s after the next')
check(sim['smallHeap'] == 2, 'none for a small heap')
check(sim['missed'] == 2, 'none after a missed window')
check(sim['afterStop'] == 2, 'none after Stop')
check(any('gcKeepAlive/started' in line for line in sim['lines']) and
      any(line.startswith('gcKeepAlive/summary: background gen2 requests 2, windows missed 1, small-heap skips 1') for line in sim['lines']),
      'journal: first request and session summary')
real = report['real']
check(real['requested'] >= 2, 'requests on the host runtime')
check(real['backgroundAdvanced'] >= real['requested'], 'each request is a background gen2 on the host runtime')
check(real['blockingAdvanced'] == 0, 'no blocking gen2 added on the host runtime')
check(real['heapMiB'] >= 384, 'the live heap is large enough')

inputs = ['build-utils/melonx/adapt_bgc_keepalive.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_bgc_keepalive_test.py', 'test/melonx_bgc_keepalive/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core691Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               report=report, sdk=sdk, physicalDeviceTested=False, productionLibraryAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/bgc-keepalive-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
