#!/usr/bin/env python3
"""Barrier compaction (build 87) on the final Core 642 BarrierBatch, against the delivered one.

Usage: melonx_barrier_compaction_final_test.py <delivered control tree> --candidate-source <final preparation>

The historical receipt barrier-compaction-checks.json (core87) proved the stable compaction of the complete production
BarrierBatch against upstream: every emitted API barrier, pass end and forced fence equal in 624 scenarios. Core 642
(adapt_moltenvk_barrier_ordering) changes BarrierBatch.cs again, so this gate reruns that comparison on the final source:
control = the delivered BarrierBatch (the compaction postimage), candidate = the final prepared one, both compiled whole
with the production NativeArray, real Silk.NET Vulkan types and doubled driver boundaries
(test/melonx_barrier_compaction_final). With MoltenVK 1.4.0 or earlier, or another driver, every trace is equal. With
MoltenVK 1.4.1 or later, the candidate differs only where an image barrier queued in a tile-based pass is for a
non-attachment: it ends the pass, exactly as the delivered class does for other tile-based GPUs (see Program.cs).
The final BarrierBatch must be the Core 639 preparation plus this adapter (melonx_adapter_control.control_source), and the
Core 639 preparation's BarrierBatch the delivered one. No Metal, MoltenVK or device; no FPS claim.
Writes dist/melonx/barrier-compaction-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTROL = Path(sys.argv[1]).resolve()
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
import adapt_barrier_compaction as compaction  # noqa: E402
import adapt_moltenvk_barrier_ordering as ordering  # noqa: E402

RELATIVE = 'src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs'
NATIVE = 'src/Ryujinx.Graphics.Vulkan/NativeArray.cs'
FIXTURE = ROOT / 'test/melonx_barrier_compaction_final'
_HOLD = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


prepared639, final = control_source(FINAL_SOURCE, 'adapt_moltenvk_barrier_ordering', _HOLD)
check(final, 'the candidate is the final preparation (it contains adapt_moltenvk_barrier_ordering)')
delivered = sha(CONTROL / RELATIVE)
check(delivered == ordering.BASELINE[RELATIVE] == sha(prepared639 / RELATIVE),
      'the delivered BarrierBatch is the Core 639 preparation\'s (the build 87 compaction postimage)')
check(compaction.BASELINE != delivered, 'the compaction adapter pins the upstream bytes, not the delivered ones')
check(sha(CONTROL / NATIVE) == sha(FINAL_SOURCE / NATIVE), 'NativeArray.cs unchanged')

with tempfile.TemporaryDirectory(prefix='melonx-barrier-compaction-final-') as temporary:
    work = Path(temporary)
    original = (CONTROL / RELATIVE).read_text(encoding='utf-8-sig')
    check(original.count('namespace Ryujinx.Graphics.Vulkan') == 1, 'one namespace in the delivered BarrierBatch')
    (work / 'Control.cs').write_text(original.replace('namespace Ryujinx.Graphics.Vulkan', 'namespace Ryujinx.Graphics.Vulkan.Control'))
    shutil.copyfile(FINAL_SOURCE / RELATIVE, work / 'Candidate.cs')
    shutil.copyfile(FINAL_SOURCE / NATIVE, work / 'NativeArray.cs')
    for path in sorted(FIXTURE.glob('*.cs')):
        shutil.copyfile(path, work / path.name)
    (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableNETAnalyzers>false</EnableNETAnalyzers>
</PropertyGroup><ItemGroup><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
    feed = os.environ.get('MELONX_TEST_PACKAGE_FEED')
    if feed:
        import html
        (work / 'nuget.config').write_text('<configuration><packageSources><clear />'
            f'<add key="offline" value="{html.escape(feed, quote=True)}" /></packageSources></configuration>')
    dotnet = os.environ.get('DOTNET', 'dotnet')
    for command in [[dotnet, 'restore', str(work / 'test.csproj'), '--disable-parallel', '-m:1'],
                    [dotnet, 'build', str(work / 'test.csproj'), '-c', 'Release', '--no-restore', '-m:1'],
                    [dotnet, str(work / 'bin/Release/net10.0/test.dll')]]:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    print(json.dumps(report), flush=True)
    check(report['result'] == 'passed' and report['scenarios'] == 2 * 624 and report['endingFlushes'] > 0 and
          report['keptMoltenVkFlushes'] > 0, 'fixture result')
    sdk = subprocess.run([dotnet, '--version'], capture_output=True, text=True, cwd=work, env=environment).stdout.strip()

inputs = ['build-utils/melonx/adapt_barrier_compaction.py', 'build-utils/melonx/adapt_moltenvk_barrier_ordering.py',
          'test/melonx_barrier_compaction_final_test.py', 'test/melonx_adapter_control.py',
          *(str(p.relative_to(ROOT)) for p in sorted(FIXTURE.glob('*.cs')))]
receipt = dict(result='passed', checks=checks, report=report, sdk=sdk, physicalDeviceTested=False, vulkanCallsDoubled=True,
               finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               controlBarrierBatch=delivered, postimages={RELATIVE: sha(FINAL_SOURCE / RELATIVE), NATIVE: sha(FINAL_SOURCE / NATIVE)},
               preimages={RELATIVE: delivered, NATIVE: sha(CONTROL / NATIVE)},
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               supersedes='core87 barrier-compaction-checks.json (upstream control); this rerun takes the delivered class as control')
out = ROOT / 'dist/melonx/barrier-compaction-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
