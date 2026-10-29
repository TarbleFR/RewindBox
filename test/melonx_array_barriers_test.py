#!/usr/bin/env python3
"""Execute the complete upstream/adapted Vulkan array classes with native doubles.

Resource bindings, descriptors and command-buffer changes are exercised; actual
Vulkan calls are doubled. Allocation totals concern these host paths only.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_array_barriers import apply

paths = ['src/Ryujinx.Graphics.Vulkan/' + name + '.cs'
         for name in ('TextureArray', 'ImageArray')]
upstream = dict(zip(paths, (
    '948628754db29845a576c42c3087f7a1727d920b33ec0053cf814f68603500ae',
    '2788a716d836e75300de1dc479b29eb3d0947cc0178b26e7e7f7557e833063cf',
)))
upstream['src/Ryujinx.Graphics.Vulkan/ResourceArray.cs'] = 'b0cf3ed2cb662369493d4fda562dcd79763bb2f3f0e1c1916305a0f97f1310d7'
for path, digest in upstream.items():
    assert hashlib.sha256((SOURCE / path).read_bytes()).hexdigest() == digest, path
paths.append('src/Ryujinx.Graphics.Vulkan/ResourceArray.cs')
reports = []
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-array-barriers-') as temporary:
    for control in (True, False):
        work = Path(temporary).resolve() / ('control' if control else 'candidate')
        source = work / 'source'
        for path in paths:
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        if not control:
            assert [p.relative_to(source).as_posix() for p in apply(source)] == paths[:2]
        for path in paths:
            shutil.copyfile(source / path, work / Path(path).name)
        shutil.copyfile(ROOT / 'test/melonx_array_barriers/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'),
                                 '-c', 'Release', '--', 'control' if control else 'candidate'],
                                cwd=work, capture_output=True, text=True, timeout=180)
        if result.returncode:
            print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        reports.append(json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{'))))
inputs = ['build-utils/melonx/adapt_array_barriers.py', 'test/melonx_array_barriers_test.py',
          'test/melonx_array_barriers/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, vulkanCallsDoubled=True,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in paths})
out = ROOT / 'dist/melonx/array-barrier-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
