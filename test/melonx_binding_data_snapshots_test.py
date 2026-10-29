#!/usr/bin/env python3
"""Execute the complete bindless cache with private snapshot reuse.

GPU resources, mapping and command transport are existing reviewed boundaries.
The cache, key structs, memory ranges and threaded commands are production code.
Only the two clone boundaries gain failure/call counters; they still invoke the
real ReadOnlySpan.ToArray. No timing claim or physical-device test follows.
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
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_binding_data_snapshots import apply, RELATIVE, BASELINE

GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
FILES = [RELATIVE,
    'src/Ryujinx.Graphics.Gpu/Image/TextureBindingInfo.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/BufferBounds.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/Types/SamplerIndex.cs',
    'src/Ryujinx.Memory/Range/MultiRange.cs', 'src/Ryujinx.Memory/Range/MemoryRange.cs',
    'src/Ryujinx.Graphics.Shader/TextureHandle.cs',
    'src/Ryujinx.Graphics.Shader/TextureUsageFlags.cs',
    'src/Ryujinx.Graphics.Shader/BufferUsageFlags.cs',
    'src/Ryujinx.Graphics.Shader/ShaderStage.cs',
    GAL + '/Target.cs', GAL + '/ITextureArray.cs', GAL + '/IImageArray.cs',
    MULTI + '/Model/TableRef.cs', MULTI + '/Model/ThreadedArrayPool.cs',
    MULTI + '/Commands/IGALCommand.cs',
    MULTI + '/Resources/ThreadedTextureArray.cs', MULTI + '/Resources/ThreadedImageArray.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs',
]
PREIMAGES = {'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs': 'b27962d8c7fcb4316ac45be63a91525f58e8215808b8a78c9dbcef6c897217d3', 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingInfo.cs': '40b2bfc915ba2cbfaa8feab47ea94d9b457ea1d25e66bca3c6ba483e5be49111', 'src/Ryujinx.Graphics.Gpu/Memory/BufferBounds.cs': '5bdb7da532d62b8975c703e5384bee3fd4041fdbf083ccb115b54cfa65b957e3', 'src/Ryujinx.Graphics.Gpu/Engine/Types/SamplerIndex.cs': '3a2bfb55d0f7bb4e5bb29c32259d87f7bbfaa6808c780e8e467b39cb6600c335', 'src/Ryujinx.Memory/Range/MultiRange.cs': 'c945e4d62500263742db07c2c8afbd0c783b1fcfe811179a232ec30ac09e826b', 'src/Ryujinx.Memory/Range/MemoryRange.cs': 'f49868746fc1fedea3dbbb18a3e5da10edf7c223a9184191ecd2b7f6fea66da0', 'src/Ryujinx.Graphics.Shader/TextureHandle.cs': 'e72ac096d6dddcb57db0831fbf2e6d1269708f6e08446cc5f0ac5b9815c931d3', 'src/Ryujinx.Graphics.Shader/TextureUsageFlags.cs': '4526e5f4fa048afdc1b7c3da31d4c4c89f32b52f75858a5676842774b1340c1d', 'src/Ryujinx.Graphics.Shader/BufferUsageFlags.cs': 'e02fbe338d658331ddccd46181c65f9cb6b1c89043c8fd027795cc18641e233f', 'src/Ryujinx.Graphics.Shader/ShaderStage.cs': 'bbf921732d94ce25c928a9e7ea955bcb60e26245b150046869f939940e2a25d8', 'src/Ryujinx.Graphics.GAL/Target.cs': 'efd7e8d90b9613b320051106f0c25fa3441ecc9490fd2eb11d9f01a1280dab4a', 'src/Ryujinx.Graphics.GAL/ITextureArray.cs': '5dd236e731089d04967d4c6ba7551a7b69450154e4800d925dc022c01883f3db', 'src/Ryujinx.Graphics.GAL/IImageArray.cs': '9f030d7bbe15ed180d92b1f588635100a7e9ffff040f6450df24bf08d7f778ea', 'src/Ryujinx.Graphics.GAL/Multithreading/Model/TableRef.cs': 'a27b66790c4afe58a41d95c75875bd550aaf8739cbebe7ab2983796ccceccce9', 'src/Ryujinx.Graphics.GAL/Multithreading/Model/ThreadedArrayPool.cs': '1e73a4faefb413eac267e6718c18c98313ceac4f0493dd41ad680692695df467', 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/IGALCommand.cs': 'eaa488cca3edf751a90bc88c82542970150e0bcf3317f779e085a660168ac8ec', 'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ThreadedTextureArray.cs': 'a3a116c083ce487b981d4481527be72708fc32d50b2185f072204e8057ec31e6', 'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ThreadedImageArray.cs': '15f70d0656ff7fcf3d0281a3259de39e861d18ba0d8e8b375e56d3b05394eba4', 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/TextureArray/TextureArraySetTexturesCommand.cs': 'b2be1fafb698eb603eb4d540815abdac646c7ef387a48073c1d6bb5dad69e9c8', 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/TextureArray/TextureArraySetSamplersCommand.cs': '1d84607a4098f775bcb912353c825263af938d6f35485d3447f9d3d5fa965903', 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/TextureArray/TextureArrayDisposeCommand.cs': '99447090c4a79a7a0a766a49de05d283a4bbc55a4e91d7158837c172b2a1ff50', 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/ImageArray/ImageArraySetImagesCommand.cs': 'b7afc71a94426cc33def157caa6bb3cab4b13862cb6ed742ecf80496fa3eef31', 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/ImageArray/ImageArrayDisposeCommand.cs': 'f8e139f1db1c81ec0df9ce7205e21ccf9a691bef4ab6aea06644d1b74740c3d4'}


def validate_inputs(base):
    actual = {p: hashlib.sha256((base / p).read_bytes()).hexdigest() for p in FILES}
    assert actual == PREIMAGES, "Prepared binding snapshot dependencies changed"
    return actual


validate_inputs(SOURCE)

support = (ROOT / 'test/melonx_bindless_allocations/Program.cs').read_text()
for old, new in {
    '    struct BufferBounds { public TestRange Range; }\n': '',
    '        readonly BufferBounds[] _bounds = { new() { Range = new(0) }, new() { Range = new(1) } };':
        '        readonly BufferBounds[] _bounds = { new(new MultiRange(0, 131072)), new(new MultiRange(1UL << 32, 131072)) };',
    '        public ReadOnlySpan<byte> GetSpan(TestRange range) => MemoryMarshal.AsBytes(Buffers[range.Slot].AsSpan());':
        '        public ReadOnlySpan<byte> GetSpan(MultiRange range) => MemoryMarshal.AsBytes(Buffers[(int)(range.GetSubRange(0).Address >> 32)].AsSpan());',
}.items():
    assert support.count(old) == 1, old
    support = support.replace(old, new)
support = 'using Ryujinx.Memory.Range;\n' + support
reports, compiled, postimages = {}, {}, {}
drift_controls = 0
with tempfile.TemporaryDirectory(prefix='melonx-binding-data-snapshots-') as temporary:
    negative = Path(temporary) / 'negative'
    for relative in FILES:
        target = negative / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)
    for relative in (RELATIVE, 'src/Ryujinx.Graphics.Shader/TextureHandle.cs'):
        path = negative / relative
        original = path.read_bytes()
        path.write_bytes(original + b'\n// changed snapshot contract\n')
        try:
            (apply if relative == RELATIVE else validate_inputs)(negative)
        except AssertionError:
            drift_controls += 1
        else:
            raise AssertionError('Unknown prepared input accepted: ' + relative)
        assert path.read_bytes() == original + b'\n// changed snapshot contract\n'
        path.write_bytes(original)
    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        for relative in FILES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        cache = work / RELATIVE
        text = cache.read_text()
        old_texture = 'cachedTextureBuffer.ToArray()'
        old_sampler = 'cachedSamplerBuffer.ToArray()'
        assert text.count(old_texture) == text.count(old_sampler) == 1
        # Counters/failures surround the real clone calls; no other production
        # body changes. The nonallocating copy path remains uninstrumented.
        cache.write_text(text.replace(old_texture, 'SnapshotCloneProbe.Texture(cachedTextureBuffer)')
                             .replace(old_sampler, 'SnapshotCloneProbe.Sampler(cachedSamplerBuffer)'))
        (work / 'Support.cs').write_text(support)
        shutil.copyfile(ROOT / 'test/melonx_binding_data_snapshots/Program.cs', work / 'Program.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<StartupObject>BindingSnapshotProgram</StartupObject><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162</NoWarn><NuGetAudit>false</NuGetAudit>
</PropertyGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
        environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release'],
            cwd=work, env=environment, capture_output=True, text=True, timeout=180)
        if result.returncode:
            print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        reports[variant] = report
        compiled[variant] = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in work.rglob('*.cs') if 'obj' not in p.relative_to(work).parts}
        print(variant, json.dumps(report), flush=True)

assert reports['control']['semanticDigest'] == reports['candidate']['semanticDigest']
assert reports['control']['behavior'] == reports['candidate']['behavior']
for before, after in zip(reports['control']['allocations'], reports['candidate']['allocations'], strict=True):
    assert (before['length'], before['separate']) == (after['length'], after['separate'])
    assert after['allocatedBytes'] == after['textureCopies'] == after['samplerCopies'] == 0, after
    assert before['allocatedBytes'] > 0 and before['textureCopies'] == before['iterations'], before
    assert before['samplerCopies'] == (before['iterations'] if before['separate'] else 0), before
inputs = ['build-utils/melonx/adapt_binding_data_snapshots.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_binding_data_snapshots_test.py', 'test/melonx_binding_data_snapshots/Program.cs',
          'test/melonx_bindless_allocations/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
    completeProductionCache=True, gpuMappingResourcesAndTransportDoubled=True,
    cloneBoundaryCountersAndFailures=True, timingClaim=False,
    changedInputControls=drift_controls,
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    baselineInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
    postimages=postimages, compiledSourceInputs=compiled)
output = ROOT / 'dist/melonx/binding-data-snapshot-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Private bindless snapshot reuse, validation and allocation checks passed.', flush=True)
