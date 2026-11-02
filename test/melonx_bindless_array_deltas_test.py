#!/usr/bin/env python3
"""Compile the real bindless array cache before and after adapt_bindless_array_deltas.

Usage: melonx_bindless_array_deltas_test.py <prepared MeloNX tree (as delivered in Core b99e754d)>

The production TextureBindingsArrayCache, the threaded array producers and their
commands are compiled unchanged; only pools, textures, memory and the renderer
transport are doubled. Every update of random pool writes, identical rewrites,
invalidations with and without pool removal, sampler replacement and quiet passes
is checked against the pools, and control and candidate must produce identical
backend contents and store/synchronisation sets at every step. Then the cost of a
pool-sized array with the pool written before every dispatch is measured.
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
DOTNET = os.environ.get('DOTNET', 'dotnet')
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_bindless_array_deltas import apply_array_cache

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
    MULTI + '/Model/TableRef.cs', MULTI + '/Model/ThreadedArrayPool.cs', MULTI + '/Commands/IGALCommand.cs',
    MULTI + '/Resources/ThreadedTextureArray.cs',
    MULTI + '/Resources/ThreadedImageArray.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs',
]

reports, postimages = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-bindless-array-deltas-') as temporary:
    temporary = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = temporary / variant
        for relative in FILES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply_array_cache(work)
            postimages = {p: hashlib.sha256((work / p).read_bytes()).hexdigest() for p in changed}
        shutil.copyfile(ROOT / 'test/melonx_bindless_array_deltas/Program.cs', work / 'Program.cs')
        define = '<DefineConstants>ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><ServerGarbageCollection>false</ServerGarbageCollection>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162;0168;0219;8981</NoWarn>{define}
</PropertyGroup></Project>''')
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
        result = subprocess.run([DOTNET, 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                                capture_output=True, text=True, timeout=1200, env=environment)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-4000:], flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

control, candidate = reports['control'], reports['candidate']
checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


check(not control['adapted'] and candidate['adapted'], 'variants swapped')
check(len(control['scenarios']) == len(candidate['scenarios']) == 54, 'scenario inventory')
for old, new in zip(control['scenarios'], candidate['scenarios'], strict=True):
    check({k: v for k, v in old.items() if k != 'digest'} == {k: v for k, v in new.items() if k != 'digest'}, 'scenario pairing')
    check(old['digest'] == new['digest'], f'backend state or synchronisation differs: {new}')
for old, new in zip(control['buffers'], candidate['buffers'], strict=True):
    check(old == new and new['lookupsPerUpdate'] == 64, f'TextureBuffer arrays must keep the full rebuild: {old} {new}')
check(all(f['recovered'] for f in candidate['failures']), 'failure recovery')
rows = []
for old, new in zip(control['measures'], candidate['measures'], strict=True):
    key = {k: old[k] for k in ('threaded', 'kind', 'length', 'changes', 'scattered')}
    check(key == {k: new[k] for k in key}, 'measure pairing')
    check(old['lookupsPerUpdate'] == old['length'], f'control walks the whole pool on every written pool: {old}')
    check(new['lookupsPerUpdate'] <= max(1, new['changes']), f'candidate resolves only changed elements: {new}')
    if old['threaded'] and old['length'] > 4096:
        check(old['producerBytesPerUpdate'] >= 16 * old['length'], f'control allocates per element: {old}')
    check(new['producerBytesPerUpdate'] <= 64 * (new['changes'] + 1) + 4096, f'candidate allocation bounded by changes: {new}')
    rows.append(dict(key, controlBytes=old['producerBytesPerUpdate'], candidateBytes=new['producerBytesPerUpdate'],
                     controlLookups=old['lookupsPerUpdate'], candidateLookups=new['lookupsPerUpdate'],
                     controlBackendElements=old['backendElementsPerUpdate'], candidateBackendElements=new['backendElementsPerUpdate'],
                     candidateBackendCalls=new['backendCallsPerUpdate'],
                     controlMicroseconds=round(old['producerMicrosecondsPerUpdate'], 1),
                     candidateMicroseconds=round(new['producerMicrosecondsPerUpdate'], 1)))

inputs = ['build-utils/melonx/adapt_bindless_array_deltas.py', 'test/melonx_bindless_array_deltas_test.py',
          'test/melonx_bindless_array_deltas/Program.cs']
receipt = dict(result='passed', checks=checks, programChecks=dict(control=control['checks'], candidate=candidate['checks']),
               measures=rows, candidateCounters=candidate['counters'], physicalDeviceTested=False,
               poolsTexturesAndTransportDoubled=True, productionCacheAndCommandsCompiled=True,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
               postimages=postimages)
out = ROOT / 'dist/melonx/bindless-array-delta-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, measures=rows), indent=1))
