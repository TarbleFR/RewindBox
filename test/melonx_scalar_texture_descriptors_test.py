#!/usr/bin/env python3
"""Compare scalar texture/image setters with real descriptor template dispatch.

Production records, setters, invalidations, normal dispatch and template writer
execute verbatim; actual Silk.NET structures retain their layouts. Resource
getters, hazard/barrier calls and the native API are explicit boundaries. This
does not execute a Vulkan driver or measure iPhone FPS.

Usage: melonx_scalar_texture_descriptors_test.py <source before the scalar adapter>
       melonx_scalar_texture_descriptors_test.py <delivered prepared source> --candidate-source <final prepared source>

With --candidate-source (build 631) the delivered members (with the scalar adapter) are the
control and the final ones the candidate, run with the encoding policy off and on: the same
semantics, resource trace and operation counts are required, the final members may differ only by
the reviewed encoding hunks, and a fragment texture at binding 64 and a fragment image at binding
32 (past the one-stage template scratch) take the fallback without the policy and the template
with it. The scratch doubles are sized as each variant's constructor sizes them (checked).
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


def run_final():
    """Build 631: the delivered members against the final ones, the final run with the encoding policy off and on."""
    import melonx_descriptor_encoding_final as final
    files = [*FILES, final.CONSTANTS]
    members, member_hashes = final.check_sources(SOURCE, CANDIDATE, SIGNATURES)
    pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
    dotnet = os.environ.get('DOTNET', 'dotnet')
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
    reports, compiled = {}, {}
    with tempfile.TemporaryDirectory(prefix='melonx-scalar-texture-descriptors-final-') as temporary:
        for variant, tree in (('control', SOURCE), ('candidate', CANDIDATE)):
            work = Path(temporary) / variant
            work.mkdir()
            (work / 'Production.cs').write_text(PRODUCTION_HEADER + '\n\n'.join(members[variant]) + '\n} }\n')
            for relative in files[1:]:
                shutil.copyfile(tree / relative, work / Path(relative).name)
            for name in ('Program.cs', 'Boundaries.cs', 'Encoding.cs'):
                shutil.copyfile(ROOT / 'test/melonx_scalar_texture_descriptors' / name, work / name)
            define = 'ADAPTED;SCALAR_FINAL' + (';ENCODING' if variant == 'candidate' else '')
            (work / 'Probe.csproj').write_text(PROJECT.replace('__DEFINES__', define))
            (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
            (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
            compiled[variant] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(work.glob('*.cs'))}
            if variant == 'control':
                reports['control'] = final.run(work / 'Probe.csproj', dotnet, environment, ['off'], build=True)
            else:
                reports['candidateOff'] = final.run(work / 'Probe.csproj', dotnet, environment, ['off'], build=True)
                reports['candidateOn'] = final.run(work / 'Probe.csproj', dotnet, environment, ['on'], build=False)
            print(variant, json.dumps({key: value for key, value in reports.items()}), flush=True)
    control = reports['control']
    for name in ('candidateOff', 'candidateOn'):
        report = reports[name]
        assert report['adapted'] and control['adapted']
        for key in ('semanticDigest', 'resourceTrace'):
            assert report[key] == control[key], (name, key)
        for old, new in zip(control['measurements'], report['measurements'], strict=True):
            for key in ('kind', 'iterations', 'descriptorUpdates', 'descriptorBinds', 'normalGets', 'identityGets', 'samplerGets',
                        'prepares', 'clears', 'barriers', 'allocatedBytes'):
                assert old[key] == new[key], (name, old['kind'], key)
            assert new['descriptorUpdates'] == new['descriptorBinds'] == new['allocatedBytes'] == 0
    fallback = dict(textureFallbacks=1, imageFallbacks=1, outOfRange=2, textureUpdates=0, imageUpdates=0)
    assert {key: control['beyondStage'][key] for key in fallback} == fallback and not control['beyondStage']['policy']
    assert control['beyondStage']['templateFallbacks'] == [0, 0, 0, 0]
    off = reports['candidateOff']['beyondStage']
    assert {key: off[key] for key in fallback} == fallback and not off['policy'] and off['templateFallbacks'] == [0, 0, 1, 1]
    on = reports['candidateOn']['beyondStage']
    assert on == dict(policy=True, textureFallbacks=0, imageFallbacks=0, outOfRange=0, textureUpdates=1, textureImage=64,
                      textureSampler=164, imageUpdates=1, imageView=10032, templateFallbacks=[0, 0, 0, 0]), on
    inputs = ['build-utils/melonx/adapt_scalar_texture_descriptors.py', 'build-utils/melonx/adapt_descriptor_updates.py',
              'build-utils/melonx/adapt_session.py', 'build-utils/melonx/source.json',
              'test/melonx_scalar_texture_descriptors_test.py', 'test/melonx_scalar_texture_descriptors/Program.cs',
              'test/melonx_scalar_texture_descriptors/Boundaries.cs', *final.INPUTS]
    receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, fpsGainProven=False,
        sourceKind='deliveredPreparedWithFinalCandidate', finalPreparedSourceBound=True,
        productionMethodsVerbatim=True, normalDescriptorDispatchAndTemplateWriterExecuted=True,
        actualSilkStructures=True, nativeApiAndResourceBoundariesDoubled=True, encodingPolicyRuns=['off', 'on'],
        finalMembersAreDeliveredWithEncodingHunks=True, scratchDoublesSizedAsConstructors=True,
        beyondStage=dict(control=control['beyondStage'], candidateOff=off, candidateOn=on),
        upstreamInputs={p: final.sha(SOURCE / p) for p in files},
        preimages={RELATIVE: final.sha(SOURCE / RELATIVE)},
        postimages={RELATIVE: final.sha(CANDIDATE / RELATIVE), final.PIPELINE_BASE: final.sha(CANDIDATE / final.PIPELINE_BASE)},
        inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
        productionMemberHashes=member_hashes, compiledSourceInputs=compiled)
    out = ROOT / 'dist/melonx/scalar-texture-descriptor-checks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    print('Scalar descriptor checks passed on the final source, encoding policy off and on.', flush=True)


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
if CANDIDATE:
    run_final()
    sys.exit(0)
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
