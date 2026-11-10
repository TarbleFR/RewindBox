#!/usr/bin/env python3
"""adapt_bgc_fragmentation_guard on the final preparation, against the Core 717 preparation as control.

Usage: melonx_bgc_fragmentation_guard_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 718, Super Smash Bros. Ultimate (pid 45272): an in-play gen2 ran fullBlocking and compacting, 355.873 ms, at a
gen2 + LOH fragmentation of 0.51 (LOH 0.57). With System.GC.ConserveMemory 5 (Ryujinx.Library.csproj) the .NET 10 GC
makes every gen2 it decides blocking above 0.5, compacting the LOH above that ratio of its own; the keep-alive of Core
693 asks for a non-blocking gen2 every 12-16 s, which is then that blocking collection. For control and candidate the
production Ryujinx.Library assembly is built. The candidate's and the control's real BackgroundGcKeepAlive classes,
taken from their preparations, run in test/melonx_bgc_fragmentation_guard/Program.cs on the host .NET 10 runtime with
ConserveMemory 5 (fake clock and background record, real GC and heap):
(1) the candidate's policy table (Fragmented above the limit 0.48, the old answers otherwise, the 2-argument decision
unchanged); (2) control on a fragmented heap (ratio above 0.5): its request runs blocking and compacting (the device
case reproduced); (3) candidate on the same heap: no request, no blocking gen2, the skip counted in the summary;
(4) candidate on a compact heap: one request, a background gen2, no blocking one; (5) candidate with the fragmentation
read forced low on a fragmented heap: the request runs blocking and is journaled (gcKeepAlive/elevated) and counted.
Source: only the keep-alive class changes; the only collection is still the non-blocking request. Writes
dist/melonx/bgc-fragmentation-guard-checks.json. Host runtime, not an iPhone.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_bgc_fragmentation_guard', _HOLD)
import adapt_bgc_fragmentation_guard as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
MARKER = '// RewindBox (adapt_bgc_keepalive): keeps the workstation background GC thread'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 717 preparation: ' + name)
project = (SOURCE / 'src/Ryujinx.Library/Ryujinx.Library.csproj').read_text()
check(f'<RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="{adapter.CONSERVE_MEMORY}" />' in project,
      'the Core still sets ConserveMemory to the value the guard assumes')

texts = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-bgc-fragmentation-') as temporary:
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
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800,
                                env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Library assembly builds')

    control, candidate = texts['control'], texts['candidate']
    restored = candidate
    for old, new in ((adapter.ENUM_OLD, adapter.ENUM_NEW), (adapter.RUN_OLD, adapter.RUN_NEW), (adapter.SEAMS_OLD, adapter.SEAMS_NEW),
                     (adapter.SUMMARY_OLD, adapter.SUMMARY_NEW), (adapter.LOOP_OLD, adapter.LOOP_NEW)):
        check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:60])
        restored = restored.replace(new, old)
    check(restored == control, 'nothing else in the file changes')
    klass, control_class = candidate[candidate.index(MARKER):], control[control.index(MARKER):]
    check(klass.count('GC.Collect(') == 1 and 'GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false)' in klass,
          'the only collection is still the non-blocking request')
    check('lock (' not in klass and '.Wait(' not in klass and 'GCSettings' not in klass, 'no lock, wait or GC setting')

    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    program = (ROOT / 'test/melonx_bgc_fragmentation_guard/Program.cs').read_text()
    (fixture / 'Program.cs').write_text(program.replace('//__CANDIDATE__\n', klass + '\n').replace('//__CONTROL__\n', control_class + '\n'))
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection>'
        '<ConcurrentGarbageCollection>true</ConcurrentGarbageCollection></PropertyGroup><ItemGroup>'
        f'<RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="{adapter.CONSERVE_MEMORY}" />'
        '<RuntimeHostConfigurationOption Include="System.GC.HighMemoryPercent" Value="99" /></ItemGroup></Project>\n')
    for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                    [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
print(json.dumps(report), flush=True)

check(abs(report['limit'] - 0.48) < 1e-9, 'limit 1 - 5/10 - 0.02')
check(report['policy'] == {'14000/0.60': 'Fragmented', '14000/0.49': 'Fragmented', '14000/0.47': 'Induce', '14000/0.0': 'Induce',
                           '11999/0.9': 'Wait', '30000/0.9': 'Missed', 'none/0.9': 'NotSeen', 'small/0.9': 'SmallHeap',
                           '2arg': 'Induce'}, 'policy table')
c = report['controlFragmented']
check(c['ratio'] > 0.5 and c['requests'] == 1 and c['blockingAdded'] >= 1 and c['compacted'],
      'control: on a heap above 0.5 its request runs blocking and compacting (the device case reproduced): ' + json.dumps(c)[:300])
f = report['candidateFragmented']
check(f['ratio'] > 0.5 and f['requests'] == 0 and f['blockingAdded'] == 0, 'candidate: no request, no blocking gen2: ' + json.dumps(f)[:300])
check(any(re.search(r'fragmented skips 1, requests run blocking 0', line) for line in f['journal']), 'the skip is in the summary')
k = report['candidateCompact']
check(k['ratio'] < 0.45 and k['requests'] == 1 and k['blockingAdded'] == 0 and k['backgroundAdded'] >= 1,
      'candidate: a compact heap still gets its background request: ' + json.dumps(k)[:300])
a = report['candidateAttribution']
check(a['requests'] == 1 and a['blockingAdded'] >= 1 and any(line.startswith('gcKeepAlive/elevated: a requested background gen2 ran blocking')
                                                           for line in a['journal'])
      and any('requests run blocking 1' in line for line in a['journal']), 'a request that ran blocking is journaled: ' + json.dumps(a)[:400])

inputs = ['build-utils/melonx/adapt_bgc_fragmentation_guard.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_bgc_fragmentation_guard_test.py', 'test/melonx_bgc_fragmentation_guard/Program.cs',
          'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core717Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               report=report, sdk=sdk, physicalDeviceTested=False, productionLibraryAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               comparison=dict(controlRequestRanBlocking=True, candidateRequestsOnFragmentedHeap=0,
                               candidateBackgroundOnCompactHeap=True, elevatedRequestJournaled=True,
                               controlRatio=report['controlFragmented']['ratio'],
                               controlBlockingPauseMs=report['controlFragmented']['blockingPauseMs']),
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/bgc-fragmentation-guard-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
