#!/usr/bin/env python3
"""Run production cache persistence against fixed-size mutable Vulkan blobs.

The driver API is doubled; mapping, file persistence, generation/merge policy
and error recovery are the complete adapted production implementation.
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
from adapt_pipeline_cache import apply_cache_manager

upstream = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
with tempfile.TemporaryDirectory(prefix='melonx-pipeline-cache-') as temporary:
    work = Path(temporary)
    manager = work / 'PipelineCacheManager.cs'
    shutil.copyfile(SOURCE / upstream, manager)
    apply_cache_manager(manager)
    for path in (ROOT / 'test/melonx_pipeline_cache').glob('*.cs'):
        shutil.copyfile(path, work / path.name)
    (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
</PropertyGroup></Project>''')
    result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                            capture_output=True, text=True, timeout=120)
    print(result.stdout, flush=True)
    if result.returncode:
        print(result.stderr, flush=True)
    result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
inputs = ['build-utils/melonx/adapt_pipeline_cache.py', 'test/melonx_pipeline_cache_test.py',
          'test/melonx_pipeline_cache/Double.cs', 'test/melonx_pipeline_cache/Program.cs']
receipt = dict(result='passed', report=report, physicalDeviceTested=False, vulkanDouble=True,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={upstream: hashlib.sha256((SOURCE / upstream).read_bytes()).hexdigest()})
out = ROOT / 'dist/melonx/pipeline-cache-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
