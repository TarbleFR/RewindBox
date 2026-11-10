#!/usr/bin/env python3
"""Compile the real bindless cache, producers, commands and FIFO table references.

Only the GPU resources, memory and renderer transport are doubled. Both whole
production cache methods run unchanged against controllable pools/backends;
the control uses the same source before this adapter, not a rewritten model.
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
from adapt_bindless_allocations import apply

GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
FILES = [
    'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs',
    'src/Ryujinx.Graphics.Gpu/Image/TextureBindingInfo.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/Types/SamplerIndex.cs',
    'src/Ryujinx.Graphics.Shader/TextureHandle.cs',
    'src/Ryujinx.Graphics.Shader/TextureUsageFlags.cs',
    'src/Ryujinx.Graphics.Shader/ShaderStage.cs',
    GAL + '/Target.cs', GAL + '/ITextureArray.cs', GAL + '/IImageArray.cs',
    MULTI + '/Model/TableRef.cs', MULTI + '/Commands/IGALCommand.cs',
    MULTI + '/Resources/ThreadedTextureArray.cs',
    MULTI + '/Resources/ThreadedImageArray.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs',
]

reports = {}
postimages = {}
with tempfile.TemporaryDirectory(prefix='melonx-bindless-allocations-') as temporary:
    # macOS may expose the same temporary directory through /var and /private/var.
    temporary = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = temporary / variant
        for relative in FILES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in changed}
        shutil.copyfile(ROOT / 'test/melonx_bindless_allocations/Program.cs', work / 'Program.cs')
        define = '<DefineConstants>ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162</NoWarn>{define}
</PropertyGroup></Project>''')
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                                capture_output=True, text=True, timeout=120, env=environment)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines()
                                         if line.startswith('{')))

control, candidate = reports['control'], reports['candidate']
assert not control['imageCallerMutationIsolated']
assert candidate['imageCallerMutationIsolated']
for old, new in zip(control['allocations'], candidate['allocations'], strict=True):
    assert (old['length'], old['image']) == (new['length'], new['image'])
    # Includes the full production pool update, producer snapshots and consumer.
    limit = 0.56 if new['image'] else 0.38
    assert new['bytesPerUpdate'] < old['bytesPerUpdate'] * limit, (old, new)
assert candidate['mixedLengthBytesPerUpdate'] < control['mixedLengthBytesPerUpdate'] * 0.38

inputs = ['build-utils/melonx/adapt_bindless_allocations.py',
          'test/melonx_bindless_allocations_test.py',
          'test/melonx_bindless_allocations/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               rendererTransportDoubled=True, gpuResourcesDoubled=True,
               completeProductionClasses=True,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
               postimages=postimages)
out = ROOT / 'dist/melonx/bindless-allocation-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Bindless array ownership and allocation checks passed.', flush=True)
