#!/usr/bin/env python3
"""Run production Vulkan buffer setters, invalidations and descriptor dispatch.

The selected methods are copied verbatim into a fixture with a test constructor.
The template writer/updater, native scratch, bitmap, buffer assignments and
buffer ranges are complete production files. Vulkan calls and resource managers
are boundary doubles. The actual normal descriptor update loop is executed.
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
from adapt_descriptor_updates import apply, method

UPDATER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
FILES = [UPDATER,
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
    '        public void SetUniformBuffers(CommandBuffer commandBuffer, ReadOnlySpan<BufferAssignment> buffers)',
    '        public void SetStorageBuffers(CommandBuffer commandBuffer, ReadOnlySpan<BufferAssignment> buffers)',
    '        public void SetStorageBuffers(CommandBuffer commandBuffer, int first, ReadOnlySpan<Auto<DisposableBuffer>> buffers)',
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

reports, member_hashes, postimages = {}, {}, {}
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-descriptor-updates-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        for relative in FILES:
            target = work / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work / 'source')
            postimages = {str(p.relative_to(work / 'source')): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in changed}
        text = (work / 'source' / UPDATER).read_text()
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
        shutil.copyfile(ROOT / 'test/melonx_descriptor_updates/Program.cs', work / 'Program.cs')
        define = '<DefineConstants>DESCRIPTOR_ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162</NoWarn>
<NuGetAudit>false</NuGetAudit>{define}</PropertyGroup>
<ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
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

for signature in SIGNATURES:
    if not signature.strip().startswith(('public void SetUniformBuffers', 'public void SetStorageBuffers')):
        assert member_hashes['control'][signature.strip()] == member_hashes['candidate'][signature.strip()]
for old, new in zip(reports['control']['measurements'], reports['candidate']['measurements'], strict=True):
    assert old['kind'] == new['kind']
    assert old['bufferLookups'] == new['bufferLookups']
    expected_updates = 0 if old['kind'] == 'uniformPush' else old['iterations']
    expected_binds = old['iterations'] * (1 if old['kind'] == 'uniformPush' else 2)
    assert old['descriptorUpdates'] == expected_updates and new['descriptorUpdates'] == 0
    assert old['descriptorBinds'] == expected_binds and new['descriptorBinds'] == 0

inputs = ['build-utils/melonx/adapt_descriptor_updates.py', 'test/melonx_descriptor_updates_test.py',
          'test/melonx_descriptor_updates/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               productionMethodsVerbatim=True, normalDescriptorUpdateLoopExecuted=True,
               nativeVulkanCallsDoubled=True, resourceManagersDoubled=True, timingGate=False,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
               productionMemberHashes=member_hashes, postimages=postimages)
out = ROOT / 'dist/melonx/descriptor-update-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production descriptor update and invalidation checks passed.', flush=True)
