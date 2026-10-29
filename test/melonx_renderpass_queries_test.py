#!/usr/bin/env python3
"""Differential full production RenderPassHolder checks and allocation probes.

GPU dispatch/resource objects are doubled; Vulkan structures come from the
engine's actual Silk.NET version. No GPU or physical-device FPS is measured.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_renderpass_queries import apply

RELATIVE = 'src/Ryujinx.Graphics.Vulkan/RenderPassHolder.cs'
reports = {}
postimages = {}
with tempfile.TemporaryDirectory(prefix='melonx-renderpass-queries-') as temp:
    for variant in ('control', 'candidate'):
        work = Path(temp).resolve() / variant
        target = work / RELATIVE
        target.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / RELATIVE, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(ROOT / 'test/melonx_renderpass_queries' / name, work / name)
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649</NoWarn>
</PropertyGroup><ItemGroup><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
        env = os.environ.copy()
        env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                                capture_output=True, text=True, timeout=120, env=env)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

control, candidate = reports['control'], reports['candidate']
assert (control['scenarios'], control['assertions'], control['digest']) == (candidate['scenarios'], candidate['assertions'], candidate['digest'])
for old, new in zip(control['measurements'], candidate['measurements'], strict=True):
    assert old['name'] == new['name']
    assert old['allocatedBytes'] > 0, old
    assert new['allocatedBytes'] == 0, new

inputs = ['build-utils/melonx/adapt_renderpass_queries.py', 'test/melonx_renderpass_queries_test.py',
          'test/melonx_renderpass_queries/Program.cs', 'test/melonx_renderpass_queries/Boundaries.cs']
receipt = dict(result='passed', reports=reports, completeProductionClass=True,
               gpuDispatchDoubled=True, gpuResourcesDoubled=True, physicalDeviceTested=False,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={RELATIVE: hashlib.sha256((SOURCE / RELATIVE).read_bytes()).hexdigest()}, postimages=postimages)
out = ROOT / 'dist/melonx/renderpass-query-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Render-pass query equivalence and allocation checks passed.', flush=True)
