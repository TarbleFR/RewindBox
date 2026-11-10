#!/usr/bin/env python3
"""Measure exact production bindless-key collision chains and warmed cache hits.

Compile the complete cache and key structs, plus the real BufferBounds,
MultiRange and MemoryRange. Reuse the GPU boundary doubles from the allocation
test; no production equality/lookup code is extracted or instrumented.
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
from adapt_binding_lookup import apply
from adapt_bindless_allocations import apply as apply_allocations_baseline

CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
PRISTINE_CACHE_SHA256 = '98091c9d255bb7b37c17cd9aa0bf70465f165647d0c54c960dae49636b6ea08e'
BASELINE_CACHE_SHA256 = '8f2ff30af6f8577e3c8102118543ac52915d62c80eeee134f2eec7866f4dde6a'
CANDIDATE_CACHE_SHA256 = 'b27962d8c7fcb4316ac45be63a91525f58e8215808b8a78c9dbcef6c897217d3'
input_cache_sha256 = hashlib.sha256((SOURCE / CACHE).read_bytes()).hexdigest()
assert input_cache_sha256 in (PRISTINE_CACHE_SHA256, BASELINE_CACHE_SHA256), (
    'unknown TextureBindingsArrayCache baseline', input_cache_sha256)
prepare_allocations_baseline = input_cache_sha256 == PRISTINE_CACHE_SHA256

GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
FILES = [
    CACHE,
    'src/Ryujinx.Graphics.Gpu/Image/TextureBindingInfo.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/BufferBounds.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/Types/SamplerIndex.cs',
    'src/Ryujinx.Memory/Range/MultiRange.cs', 'src/Ryujinx.Memory/Range/MemoryRange.cs',
    'src/Ryujinx.Graphics.Shader/TextureHandle.cs',
    'src/Ryujinx.Graphics.Shader/TextureUsageFlags.cs',
    'src/Ryujinx.Graphics.Shader/BufferUsageFlags.cs',
    'src/Ryujinx.Graphics.Shader/ShaderStage.cs',
    GAL + '/Target.cs', GAL + '/ITextureArray.cs', GAL + '/IImageArray.cs',
    MULTI + '/Model/TableRef.cs', MULTI + '/Commands/IGALCommand.cs',
    MULTI + '/Resources/ThreadedTextureArray.cs', MULTI + '/Resources/ThreadedImageArray.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs',
]

support = (ROOT / 'test/melonx_bindless_allocations/Program.cs').read_text()
replacements = {
    '    struct BufferBounds { public TestRange Range; }\n': '',
    '        readonly BufferBounds[] _bounds = { new() { Range = new(0) }, new() { Range = new(1) } };':
        '        readonly BufferBounds[] _bounds = { new(new MultiRange(0, 8192)), new(new MultiRange(1UL << 32, 8192)) };',
    '        public ReadOnlySpan<byte> GetSpan(TestRange range) => MemoryMarshal.AsBytes(Buffers[range.Slot].AsSpan());':
        '        public ReadOnlySpan<byte> GetSpan(MultiRange range) => MemoryMarshal.AsBytes(Buffers[(int)(range.GetSubRange(0).Address >> 32)].AsSpan());',
    '        public readonly int[][] Buffers = { new int[32768], new int[32768] };':
        '        public readonly int[][] Buffers = { new int[2048], new int[2048] };',
}
for old, new in replacements.items():
    assert support.count(old) == 1, old
    support = support.replace(old, new)
support = 'using Ryujinx.Memory.Range;\n' + support

reports, postimages, prepared_baseline_inputs = {}, {}, {}
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-binding-lookup-') as temporary:
    temporary = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = temporary / variant
        for relative in FILES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if prepare_allocations_baseline:
            apply_allocations_baseline(work)
        assert hashlib.sha256((work / CACHE).read_bytes()).hexdigest() == BASELINE_CACHE_SHA256
        baseline_inputs = {p: hashlib.sha256((work / p).read_bytes()).hexdigest() for p in FILES}
        if prepared_baseline_inputs:
            assert baseline_inputs == prepared_baseline_inputs, 'control/candidate baseline differs'
        else:
            prepared_baseline_inputs = baseline_inputs
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in changed}
            assert postimages[CACHE] == CANDIDATE_CACHE_SHA256, 'candidate differs from the full-engine postimage'
        (work / 'Support.cs').write_text(support)
        shutil.copyfile(ROOT / 'test/melonx_binding_lookup/Program.cs', work / 'Program.cs')
        define = '<DefineConstants>LOOKUP_ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<StartupObject>BindingLookupProgram</StartupObject><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162</NoWarn><NuGetAudit>false</NuGetAudit>{define}
</PropertyGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                                cwd=work, capture_output=True, text=True, timeout=120, env=environment)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

for old, new in zip(reports['control']['collisionCases'], reports['candidate']['collisionCases'], strict=True):
    assert (old['kind'], old['count']) == (new['kind'], new['count'])
    if old['count'] >= 32:
        assert new['comparisonsPerHit'] < old['comparisonsPerHit'] / 8, (old, new)
        assert new['distinctHashes'] >= old['count'] * 0.9, (old, new)
assert reports['control']['behavior'] == reports['candidate']['behavior']

inputs = ['build-utils/melonx/adapt_binding_lookup.py', 'build-utils/melonx/adapt_bindless_allocations.py',
          'test/melonx_binding_lookup_test.py',
          'test/melonx_binding_lookup/Program.cs', 'test/melonx_bindless_allocations/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               completeProductionCache=True, completeProductionKeysAndBounds=True,
               gpuBoundaryDoubles=True, timingGate=False,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
               baselinePreparation=dict(inputCacheSha256=input_cache_sha256,
                                        allocationsAdapterApplied=prepare_allocations_baseline,
                                        controlCacheSha256=BASELINE_CACHE_SHA256),
               preparedBaselineInputs=prepared_baseline_inputs,
               postimages=postimages)
out = ROOT / 'dist/melonx/binding-lookup-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production binding lookup, equality and lifetime checks passed.', flush=True)
