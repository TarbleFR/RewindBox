#!/usr/bin/env python3
"""Compare scalar texture/image setters with real descriptor template dispatch.

Production records, setters, invalidations, normal dispatch and template writer
execute verbatim; actual Silk.NET structures retain their layouts. Resource
getters, hazard/barrier calls and the native API are explicit boundaries. This
does not execute a Vulkan driver or measure iPhone FPS.
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
from adapt_scalar_texture_descriptors import apply, BASELINE, RELATIVE
from adapt_descriptor_updates import method

FILES = [RELATIVE,
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
    '        private void UpdateAndBindUniformBufferPd(',
    '        private void Initialize(CommandBufferScoped cbs, int setIndex, DescriptorSetCollection dsc)',
    '        private void BindExtraSets(',
    '        public void SignalCommandBufferChange(',
    '        public void ForceTextureDirty(',
    '        public void ForceImageDirty(',
    '        private static void SwapBuffer(',
    '        public void SwapBuffer(',
]
assert hashlib.sha256((SOURCE / RELATIVE).read_bytes()).hexdigest() == BASELINE
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
dotnet = os.environ.get('DOTNET', 'dotnet')
reports, member_hashes, postimages, compiled = {}, {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-scalar-texture-descriptors-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        for relative in FILES:
            target = work / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
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
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(ROOT / 'test/melonx_scalar_texture_descriptors' / name, work / name)
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
    for key in ('normalGets', 'identityGets', 'samplerGets', 'prepares', 'clears', 'barriers'):
        assert old[key] == new[key], (old['kind'], key)
    assert old['descriptorUpdates'] == old['descriptorBinds'] == old['iterations']
    assert new['descriptorUpdates'] == new['descriptorBinds'] == 0
    assert old['allocatedBytes'] == new['allocatedBytes'] == 0
modified = {'public void SetTextureAndSampler(', 'public void SetTextureAndSamplerIdentitySwizzle(',
            'public void SetImage(CommandBufferScoped cbs, ShaderStage stage, int binding, ITexture image)',
            'public void SetImage(int binding, Auto<DisposableImageView> image)'}
for signature in SIGNATURES:
    if signature.strip() not in modified:
        assert member_hashes['control'][signature.strip()] == member_hashes['candidate'][signature.strip()], signature
inputs = ['build-utils/melonx/adapt_scalar_texture_descriptors.py', 'build-utils/melonx/adapt_descriptor_updates.py',
          'build-utils/melonx/adapt_session.py', 'build-utils/melonx/source.json',
          'test/melonx_scalar_texture_descriptors_test.py', 'test/melonx_scalar_texture_descriptors/Program.cs',
          'test/melonx_scalar_texture_descriptors/Boundaries.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
    productionMethodsVerbatim=True, normalDescriptorDispatchAndTemplateWriterExecuted=True,
    actualSilkStructures=True, nativeApiAndResourceBoundariesDoubled=True,
    upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    productionMemberHashes=member_hashes, postimages=postimages, compiledSourceInputs=compiled)
out = ROOT / 'dist/melonx/scalar-texture-descriptor-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Scalar descriptor semantic, side-effect, invalidation and operation-count checks passed.', flush=True)
