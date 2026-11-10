#!/usr/bin/env python3
"""Exercise production close ordering and compilation scheduler cancellation.

The actual worker queues and shader warm-up methods execute. Shader-module
completion and native pipeline compilation are controllable boundaries; no
GPU compilation or device performance is claimed.
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
from adapt_shader_warmup import apply


def method(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        if text[end] == '{':
            depth += 1
        if text[end] == '}':
            depth -= 1
        end += 1
    return text[start:end]


paths = ['src/Ryujinx.Graphics.Vulkan/' + name + '.cs'
         for name in ('ShaderCollection', 'BackgroundCompilationScheduler', 'VulkanRenderer')]
with tempfile.TemporaryDirectory(prefix='melonx-warmup-close-') as temporary:
    work = Path(temporary)
    source = work / 'source'
    for path in paths:
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / path, target)
    apply(source)
    collection = (source / paths[0]).read_text()
    methods = '\n'.join(method(collection, signature) for signature in (
        'private async Task BackgroundCompilation()',
        'public void PromoteBackgroundCompilation()',
        'private Task RunBackgroundPipelineCompile(',
        'private void LogBackgroundPipelineFailure(',
        'public void CancelPendingWarmUp()',
        'public void WaitForBackgroundCompilation()',
    ))
    renderer = (source / paths[2]).read_text()
    close = method(renderer, 'public unsafe void Dispose()')
    close = close[close.index('{') + 1:close.index('            Api.DeviceWaitIdle(_device);')]
    template = (ROOT / 'test/melonx_warmup_close/Double.cs').read_text()
    (work / 'Double.cs').write_text(template.replace('/* SHADER_METHODS */', methods)
                                  .replace('/* RENDERER_CLOSE_PREFIX */', close))
    shutil.copyfile(source / paths[1], work / 'BackgroundCompilationScheduler.cs')
    shutil.copyfile(ROOT / 'test/melonx_warmup_close/Program.cs', work / 'Program.cs')
    (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NoWarn>CS0649;CS0414</NoWarn>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
    result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                            capture_output=True, text=True, timeout=120)
    print(result.stdout, flush=True)
    if result.returncode:
        print(result.stderr, flush=True)
    result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
inputs = ['build-utils/melonx/adapt_shader_warmup.py', 'test/melonx_warmup_close_test.py',
          'test/melonx_warmup_close/Double.cs', 'test/melonx_warmup_close/Program.cs']
receipt = dict(result='passed', report=report, physicalDeviceTested=False, nativePipelineDouble=True,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in paths})
out = ROOT / 'dist/melonx/warmup-close-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
