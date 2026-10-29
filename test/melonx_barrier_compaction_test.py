#!/usr/bin/env python3
"""Compare complete production barrier batching before/after stable compaction.

The exact upstream and candidate classes share one test assembly, real Vulkan
structs and the production NativeArray. The driver/render-pass boundaries are
doubled. Every emitted API barrier and ordering is compared; timing covers only
Flush after queues and list capacity are warm.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_barrier_compaction import apply, BASELINE

relative = 'src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs'
assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == BASELINE
with tempfile.TemporaryDirectory(prefix='melonx-barrier-compaction-') as temporary:
    work = Path(temporary)
    source = work / 'source'
    target = source / relative
    target.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / relative, target)
    original = target.read_text()
    assert original.count('namespace Ryujinx.Graphics.Vulkan') == 1
    (work / 'Control.cs').write_text(original.replace('namespace Ryujinx.Graphics.Vulkan',
        'namespace Ryujinx.Graphics.Vulkan.Control'))
    apply(source)
    postimage = hashlib.sha256(target.read_bytes()).hexdigest()
    shutil.copyfile(target, work / 'Candidate.cs')
    native = 'src/Ryujinx.Graphics.Vulkan/NativeArray.cs'
    shutil.copyfile(SOURCE / native, work / 'NativeArray.cs')
    for path in (ROOT / 'test/melonx_barrier_compaction').glob('*.cs'):
        shutil.copyfile(path, work / path.name)
    (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableNETAnalyzers>false</EnableNETAnalyzers>
</PropertyGroup><ItemGroup><Compile Remove="source/**" />
<PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
    environment = os.environ.copy()
    environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_TieredCompilation='0')
    feed = os.environ.get('MELONX_TEST_PACKAGE_FEED')
    if feed:
        import html
        (work / 'nuget.config').write_text('<configuration><packageSources><clear />'
            f'<add key="offline" value="{html.escape(feed, quote=True)}" /></packageSources></configuration>')
    for command in [
        ['dotnet', 'restore', str(work / 'test.csproj'), '--disable-parallel', '-m:1'],
        ['dotnet', 'build', str(work / 'test.csproj'), '-c', 'Release', '--no-restore', '-m:1'],
        ['dotnet', str(work / 'bin/Release/net10.0/test.dll')],
    ]:
        result = subprocess.run(command, capture_output=True, text=True, timeout=240,
            env=environment, cwd=work)
        if result.returncode: print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    print(json.dumps(report), flush=True)
inputs = ['build-utils/melonx/adapt_barrier_compaction.py', 'test/melonx_barrier_compaction_test.py',
          'test/melonx_barrier_compaction/Program.cs', 'test/melonx_barrier_compaction/Boundaries.cs']
receipt = dict(result='passed', report=report, physicalDeviceTested=False, vulkanCallsDoubled=True,
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    productionInputs={relative: BASELINE, native: hashlib.sha256((SOURCE / native).read_bytes()).hexdigest()},
    productionPostimage=postimage)
out = ROOT / 'dist/melonx/barrier-compaction-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
