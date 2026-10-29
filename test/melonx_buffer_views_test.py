#!/usr/bin/env python3
"""Execute the full production TextureBuffer with counted native view I/O.

The original and adapted classes run the same storage/reuse sequence. Native
view allocation and fences are doubled; this is not an iPhone/GPU benchmark.
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
from adapt_buffer_views import apply

paths = ['src/Ryujinx.Graphics.Vulkan/' + name + '.cs'
         for name in ('TextureBuffer', 'BufferManager')]
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-buffer-views-') as temporary:
    for control in (True, False):
        work = Path(temporary) / ('control' if control else 'fixed')
        source = work / 'source'
        for path in paths:
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        if not control:
            apply(source)
        shutil.copyfile(source / paths[0], work / 'TextureBuffer.cs')
        for path in (ROOT / 'test/melonx_buffer_views').glob('*.cs'):
            shutil.copyfile(path, work / path.name)
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'),
                                 '-c', 'Release', '--', 'control' if control else 'fixed'],
                                capture_output=True, text=True, timeout=120)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
        result.check_returncode()
        reports.append(json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{'))))
inputs = ['build-utils/melonx/adapt_buffer_views.py', 'test/melonx_buffer_views_test.py',
          'test/melonx_buffer_views/Double.cs', 'test/melonx_buffer_views/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, nativeViewDouble=True,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in paths})
out = ROOT / 'dist/melonx/buffer-view-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
