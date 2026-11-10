#!/usr/bin/env python3
"""Check the real fallback loop and synchronous descriptor-span consumer.

Both variants include the separately verified scalar-setter optimization.
Production DescriptorSetCollection, dispatch, initialization, fallback, records,
template writer, bitmap and Silk layouts execute. Vulkan/resource ownership is
doubled. No driver, game or physical-device performance is measured.

Usage: melonx_fallback_descriptor_scratch_test.py <source before the scalar adapter>
       melonx_fallback_descriptor_scratch_test.py <delivered prepared source> --candidate-source <final prepared source>

With --candidate-source (build 631) the delivered members are the control and the final ones the
candidate, run with the encoding policy off and on: the same native writes, binds, resource gets,
semantics and allocations are required, the final members may differ only by the reviewed encoding
hunks, and each fallback the real catch enters is counted by set in the final source only.
"""
import argparse
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--candidate-source', type=Path)
args = parser.parse_args()
SOURCE = args.source.resolve()
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from adapt_scalar_texture_descriptors import apply as scalar_apply, BASELINE as SCALAR_BASELINE
from adapt_fallback_descriptor_scratch import apply, BASELINE, RELATIVE, CONSUMER, CONSUMER_HASH, SIGNATURE
from adapt_descriptor_updates import method

FILES = [RELATIVE, CONSUMER,
    'src/Ryujinx.Graphics.Vulkan/DescriptorSetTemplateUpdater.cs',
    'src/Ryujinx.Graphics.Vulkan/NativeArray.cs',
    'src/Ryujinx.Graphics.Vulkan/BitMapStruct.cs',
    'src/Ryujinx.Graphics.Vulkan/ResourceBindingSegment.cs',
    'src/Ryujinx.Common/Memory/IArray.cs',
    'src/Ryujinx.Common/Memory/StructArrayHelpers.cs',
    'src/Ryujinx.Common/Utilities/BitUtils.cs',
    'src/Ryujinx.Graphics.GAL/BufferAssignment.cs',
    'src/Ryujinx.Graphics.GAL/BufferRange.cs',
    'src/Ryujinx.Graphics.GAL/BufferHandle.cs',
    'src/Ryujinx.Graphics.GAL/ResourceLayout.cs',
    'src/Ryujinx.Graphics.Shader/ShaderStage.cs',
]
SIGNATURES = [
    '        private record struct BufferRef',
    '        private record struct TextureRef',
    '        private record struct ImageRef',
    '        private enum DirtyFlags',
    '        private static bool BindingOverlaps(',
    '        internal void Rebind(',
    '        public void AdvancePdSequence(',
    '        public void SetProgram(',
    '        public void CopyFrom(',
    '        public void SetTextureAndSampler(\n',
    '        public void SetTextureAndSamplerIdentitySwizzle(\n',
    '        public void SetImage(CommandBufferScoped cbs, ShaderStage stage, int binding, ITexture image)',
    '        public void SetImage(int binding, Auto<DisposableImageView> image)',
    '        private void SignalDirty(',
    '        public void UpdateAndBindDescriptorSets(',
    '        private static bool UpdateBuffer(',
    '        private void UpdateAndBind(CommandBufferScoped cbs, ShaderCollection program, int setIndex, PipelineBindPoint pbp)',
    SIGNATURE,
    '        private void UpdateAndBindUniformBufferPd(',
    '        private void Initialize(CommandBufferScoped cbs, int setIndex, DescriptorSetCollection dsc)',
    '        private void BindExtraSets(',
    '        public void SignalCommandBufferChange(',
    '        public void ForceTextureDirty(',
    '        public void ForceImageDirty(',
    '        private static void SwapBuffer(',
    '        public void SwapBuffer(',
]


def replace_once(text, old, new):
    assert text.count(old) == 1, (old[:90], text.count(old))
    return text.replace(old, new)


def boundaries():
    # Reuse the already audited resource doubles; compile the full real
    # DescriptorSetCollection instead of its previous test boundary.
    text = (ROOT / 'test/melonx_scalar_texture_descriptors/Boundaries.cs').read_text()
    text = replace_once(text, method(text, '    sealed class DescriptorSetCollection'), '')
    text = replace_once(text, 'new(new DescriptorSetCollection());',
        'new(new DescriptorSetCollection(new DescriptorSetManager.DescriptorPoolHolder(), new[] { new DescriptorSet(77) }));')
    text = replace_once(text, 'public bool HasMinimalLayout = true;', 'public bool HasMinimalLayout = true;\n        public bool NewCollection;')
    text = replace_once(text, 'NewSets++; isNew = false;', 'NewSets++; isNew = NewCollection;')
    text = replace_once(text, '    sealed class TextureArray\n    {', '''    sealed class TextureArray
    {
        public DescriptorImageInfo[] Images;
        public BufferView[] Buffers;
        public int ImageGets, BufferGets;''')
    text = replace_once(text,
        'public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView texture, SamplerHolder sampler) => ReadOnlySpan<DescriptorImageInfo>.Empty;',
        'public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView texture, SamplerHolder sampler) { ImageGets++; return Images; }')
    text = replace_once(text,
        'public ReadOnlySpan<BufferView> GetBufferViews(CommandBufferScoped cbs) => ReadOnlySpan<BufferView>.Empty;\n        public DescriptorSet[] GetDescriptorSets(Device device, CommandBufferScoped cbs, DescriptorSetTemplateUpdater updater,\n            ShaderCollection shader, int set, TextureView texture, SamplerHolder sampler)',
        'public ReadOnlySpan<BufferView> GetBufferViews(CommandBufferScoped cbs) { BufferGets++; return Buffers; }\n        public DescriptorSet[] GetDescriptorSets(Device device, CommandBufferScoped cbs, DescriptorSetTemplateUpdater updater,\n            ShaderCollection shader, int set, TextureView texture, SamplerHolder sampler)')
    text = replace_once(text,
        '        private void UpdateAndBind(CommandBufferScoped cbs, int set, PipelineBindPoint point) => throw new InvalidOperationException("unexpected descriptor fallback");', '')
    return text


PRODUCTION_HEADER = '''using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;
using Buffer = Silk.NET.Vulkan.Buffer;
namespace Ryujinx.Graphics.Vulkan { partial class DescriptorSetUpdater {
'''
PROJECT = '''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162</NoWarn>
<NuGetAudit>false</NuGetAudit><DefineConstants>__DEFINES__</DefineConstants></PropertyGroup>
<ItemGroup><Compile Remove="source/**" /><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>'''


def run_final():
    """Build 631: the delivered members against the final ones, the final run with the encoding policy off and on."""
    import melonx_descriptor_encoding_final as final
    files = [*FILES, final.CONSTANTS]
    assert final.sha(SOURCE / CONSUMER) == final.sha(CANDIDATE / CONSUMER) == CONSUMER_HASH, 'changed descriptor consumer'
    members, member_hashes = final.check_sources(SOURCE, CANDIDATE, SIGNATURES)
    pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
    dotnet = os.environ.get('DOTNET', 'dotnet')
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
    reports, compiled = {}, {}
    with tempfile.TemporaryDirectory(prefix='melonx-fallback-descriptor-scratch-final-') as temporary:
        for variant, tree in (('control', SOURCE), ('candidate', CANDIDATE)):
            work = Path(temporary) / variant
            work.mkdir()
            (work / 'Production.cs').write_text(PRODUCTION_HEADER + '\n\n'.join(members[variant]) + '\n} }\n')
            for relative in files[1:]:
                shutil.copyfile(tree / relative, work / Path(relative).name)
            (work / 'Boundaries.cs').write_text(boundaries())
            shutil.copyfile(ROOT / 'test/melonx_scalar_texture_descriptors/Encoding.cs', work / 'Encoding.cs')
            for name in ('Program.cs', 'NativeBoundary.cs'):
                shutil.copyfile(ROOT / 'test/melonx_fallback_descriptor_scratch' / name, work / name)
            (work / 'Probe.csproj').write_text(PROJECT.replace('__DEFINES__', 'ADAPTED;FALLBACK_FINAL'))
            (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
            (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
            compiled[variant] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(work.glob('*.cs'))}
            if variant == 'control':
                reports['control'] = final.run(work / 'Probe.csproj', dotnet, environment, ['off'], build=True)
            else:
                reports['candidateOff'] = final.run(work / 'Probe.csproj', dotnet, environment, ['off'], build=True)
                reports['candidateOn'] = final.run(work / 'Probe.csproj', dotnet, environment, ['on'], build=False)
            print(variant, json.dumps(reports), flush=True)
    control = reports['control']
    for name in ('candidateOff', 'candidateOn'):
        report = reports[name]
        for key in ('semanticDigest', 'resourceTrace'):
            assert report[key] == control[key], (name, key)
        for old, new in zip(control['measurements'], report['measurements'], strict=True):
            for key in ('kind', 'iterations', 'nativeWrites', 'binds', 'resourceGets', 'digest', 'allocatedBytes'):
                assert old[key] == new[key], (name, old['kind'], key)
            assert new['allocatedBytes'] == 0
    assert control['templateFallbacks'] == [0, 0, 0, 0]
    fallbacks = reports['candidateOff']['templateFallbacks']
    assert fallbacks == reports['candidateOn']['templateFallbacks'] and fallbacks[2] > 0, fallbacks
    assert compiled['control']['DescriptorSetCollection.cs'] == compiled['candidate']['DescriptorSetCollection.cs'] == CONSUMER_HASH
    inputs = ['build-utils/melonx/adapt_fallback_descriptor_scratch.py', 'build-utils/melonx/adapt_scalar_texture_descriptors.py',
              'build-utils/melonx/adapt_descriptor_updates.py', 'build-utils/melonx/adapt_session.py', 'build-utils/melonx/source.json',
              'test/melonx_scalar_texture_descriptors/Boundaries.cs', 'test/melonx_fallback_descriptor_scratch_test.py',
              'test/melonx_fallback_descriptor_scratch/Program.cs', 'test/melonx_fallback_descriptor_scratch/NativeBoundary.cs',
              *final.INPUTS]
    receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, fpsGainProven=False,
        sourceKind='deliveredPreparedWithFinalCandidate', finalPreparedSourceBound=True,
        scalarOptimizationInBothVariants=True, productionFallbackAndConsumerVerbatim=True,
        productionInitializationAndDispatchExecuted=True, actualSilkStructures=True,
        nativeApiAndResourceBoundariesDoubled=True, encodingPolicyRuns=['off', 'on'],
        finalMembersAreDeliveredWithEncodingHunks=True, templateFallbacksCounted=fallbacks,
        upstreamInputs={p: final.sha(SOURCE / p) for p in files},
        preimages={RELATIVE: final.sha(SOURCE / RELATIVE)},
        postimages={RELATIVE: final.sha(CANDIDATE / RELATIVE), final.PIPELINE_BASE: final.sha(CANDIDATE / final.PIPELINE_BASE)},
        inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
        productionMemberHashes=member_hashes, compiledSourceInputs=compiled)
    out = ROOT / 'dist/melonx/fallback-descriptor-scratch-checks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    print('Fallback descriptor scratch checks passed on the final source, encoding policy off and on.', flush=True)


if CANDIDATE:
    run_final()
    sys.exit(0)
assert hashlib.sha256((SOURCE / RELATIVE).read_bytes()).hexdigest() == SCALAR_BASELINE
assert hashlib.sha256((SOURCE / CONSUMER).read_bytes()).hexdigest() == CONSUMER_HASH
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
dotnet = os.environ.get('DOTNET', 'dotnet')
reports, member_hashes, postimages, compiled = {}, {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-fallback-descriptor-scratch-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        for relative in FILES:
            target = work / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        scalar_apply(work / 'source')
        assert hashlib.sha256((work / 'source' / RELATIVE).read_bytes()).hexdigest() == BASELINE
        # The consumer guard must fail before touching the source.
        if variant == 'candidate':
            for relative in (RELATIVE, CONSUMER):
                path = work / 'source' / relative
                original = path.read_bytes()
                path.write_bytes(original + b'\n// deliberate drift\n')
                before = (work / 'source' / RELATIVE).read_bytes()
                try:
                    apply(work / 'source')
                except AssertionError:
                    assert (work / 'source' / RELATIVE).read_bytes() == before
                else:
                    raise AssertionError(('drift accepted', relative))
                path.write_bytes(original)
            changed = apply(work / 'source')
            postimages = {str(p.relative_to(work / 'source')): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        text = (work / 'source' / RELATIVE).read_text()
        members = [method(text, signature) for signature in SIGNATURES]
        member_hashes[variant] = {signature.strip(): hashlib.sha256(body.encode()).hexdigest()
                                 for signature, body in zip(SIGNATURES, members, strict=True)}
        (work / 'Production.cs').write_text('''using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;
using Buffer = Silk.NET.Vulkan.Buffer;
namespace Ryujinx.Graphics.Vulkan { partial class DescriptorSetUpdater {
''' + '\n\n'.join(members) + '\n} }\n')
        for relative in FILES[1:]:
            shutil.copyfile(work / 'source' / relative, work / Path(relative).name)
        (work / 'Boundaries.cs').write_text(boundaries())
        for name in ('Program.cs', 'NativeBoundary.cs'):
            shutil.copyfile(ROOT / 'test/melonx_fallback_descriptor_scratch' / name, work / name)
        define = '<DefineConstants>ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (work / 'Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162</NoWarn>
<NuGetAudit>false</NuGetAudit>{define}</PropertyGroup>
<ItemGroup><Compile Remove="source/**" /><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([dotnet, 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release'],
                                cwd=work, capture_output=True, text=True, timeout=180, env=environment)
        if result.returncode:
            print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        compiled[variant] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in work.glob('*.cs')}
        print(variant, json.dumps(reports[variant]), flush=True)

for key in ('semanticDigest', 'resourceTrace'):
    assert reports['control'][key] == reports['candidate'][key], key
for old, new in zip(reports['control']['measurements'], reports['candidate']['measurements'], strict=True):
    assert old['kind'] == new['kind']
    for key in ('iterations', 'nativeWrites', 'binds', 'resourceGets', 'digest'):
        assert old[key] == new[key], (old['kind'], key)
    assert old['allocatedBytes'] == old['iterations'] * old['arraysPerCall'] * old['bytesPerArray']
    assert new['allocatedBytes'] == 0
for signature in SIGNATURES:
    if signature != SIGNATURE:
        assert member_hashes['control'][signature.strip()] == member_hashes['candidate'][signature.strip()], signature
assert compiled['control']['DescriptorSetCollection.cs'] == compiled['candidate']['DescriptorSetCollection.cs'] == CONSUMER_HASH
inputs = ['build-utils/melonx/adapt_fallback_descriptor_scratch.py', 'build-utils/melonx/adapt_scalar_texture_descriptors.py',
          'build-utils/melonx/adapt_descriptor_updates.py', 'build-utils/melonx/adapt_session.py', 'build-utils/melonx/source.json',
          'test/melonx_scalar_texture_descriptors/Boundaries.cs', 'test/melonx_fallback_descriptor_scratch_test.py',
          'test/melonx_fallback_descriptor_scratch/Program.cs', 'test/melonx_fallback_descriptor_scratch/NativeBoundary.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
    scalarOptimizationInBothVariants=True, productionFallbackAndConsumerVerbatim=True,
    productionInitializationAndDispatchExecuted=True, consumerAndUpdaterDriftRejected=True,
    actualSilkStructures=True, nativeApiAndResourceBoundariesDoubled=True,
    upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    productionMemberHashes=member_hashes, postimages=postimages, compiledSourceInputs=compiled)
out = ROOT / 'dist/melonx/fallback-descriptor-scratch-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Fallback descriptor scratch semantics, native call order and allocation checks passed.', flush=True)
