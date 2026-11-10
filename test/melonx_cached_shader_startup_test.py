#!/usr/bin/env python3
"""Exercise cache startup with production constructors, queues and draw decisions.

Accept pristine pinned sources or the exact preceding full-engine postimages.
Prepare every prerequisite of the compiled Vulkan files before either variant.
Native Vulkan calls, descriptor layout construction and pipeline-state packing
are controlled boundaries. Scheduling, program readiness, cache ownership,
demand/skip decisions, error interpretation and teardown ordering are real code.
No GPU timing, image correctness or physical-device performance is claimed.
"""
from pathlib import Path
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_cached_shader_startup import apply, BASELINE

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
PREREQUISITES = [
    ('adapt_runtime', 'disable_ios_host_import'),
    ('adapt_pipeline', 'apply'),
    ('adapt_shader_warmup', 'apply'),
    ('adapt_attachmentless_framebuffer', 'apply'),
    ('adapt_pipeline_cache', 'apply'),
    ('adapt_pipeline_lookup', 'apply'),
]
FILES = [VULKAN + name + '.cs' for name in (
    'ShaderCollection', 'VulkanRenderer', 'PipelineBase', 'Shader',
    'BackgroundCompilationScheduler', 'PipelineState', 'VulkanException',
    'HashTableSlim', 'PipelineUid', 'VulkanInitialization', 'FramebufferParams',
    'PipelineCacheManager', 'MoltenVK/MVKInitialization')]
FILES += ['src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs', 'src/Ryujinx.Library/Library.cs']
WHOLE_FILES = [VULKAN + name + '.cs' for name in (
    'BackgroundCompilationScheduler', 'VulkanException', 'HashTableSlim')]
WHOLE_FILES += ['src/Ryujinx.Graphics.GAL/' + name + '.cs' for name in (
    'ShaderInfo', 'ShaderSource', 'ResourceLayout', 'ProgramLinkStatus')]
WHOLE_FILES += ['src/Ryujinx.Graphics.Shader/ShaderStage.cs',
                'src/Ryujinx.Graphics.Shader/Translation/TargetLanguage.cs']
FILES = list(dict.fromkeys(FILES + WHOLE_FILES))
PREPARED = dict(BASELINE, **{
    'BackgroundCompilationScheduler.cs': 'baaea1872ffb991b5fcbc0fd967264206faba221c71f4c9107be1068c8a479d4',
    'Shader.cs': 'dd059fc858076933f960f840eae7b52f67ecdad429ef2491d7dcc4fd672fdd87',
    'PipelineState.cs': '27a2e43f31b476f3d5df9e9b9de67d49ac4531b73bbea82f4fdccfe17e5bc2b1',
    'VulkanException.cs': '6a889a31001fa3973eebcaafe9eb82615a840a791edb823ef0379c5db1120294',
    'HashTableSlim.cs': 'e9fb1db8eac79c9aa8d16eafd4ff6b09f0b555197fad197d71c7adc1140fe624',
})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member(text, signature):
    assert text.count(signature) == 1, (signature, text.count(signature))
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


COLLECTION = [
    '        public ShaderCollection(\n            VulkanRenderer gd,\n            Device device,\n            ShaderSource[] shaders,',
    '        public ShaderCollection(\n            VulkanRenderer gd,\n            Device device,\n            ShaderSource[] sources,',
    '        private async Task BackgroundShaderModuleCompilation()',
    '        private async Task BackgroundCompilation()',
    '        public void PromoteBackgroundCompilation()',
    '        private void RegisterInitialBackgroundPipelineTask(',
    '        private void ClearInitialBackgroundPipelineTask()',
    '        private static SpecData GetInitialComputePipelineKey()',
    '        private PipelineUid GetInitialGraphicsPipelineKey()',
    '        private Task RunBackgroundPipelineCompile(',
    '        private void LogBackgroundPipelineFailure(',
    '        private async Task<bool> WaitForShaderModuleCompilation()',
    '        private void EnsureShadersReadyLegacy()',
    '        private bool EnsureShadersReady(',
    '        public bool TryGetInfos(',
    '        public bool WaitForShaderModules(',
    '        public PipelineShaderStageCreateInfo[] GetInfos()',
    '        public void CreateBackgroundComputePipeline(',
    '        public void CreateBackgroundGraphicsPipeline(',
    '        public ProgramLinkStatus CheckProgramLink(',
    '        public Auto<DisposablePipeline> AddComputePipeline(',
    '        public Auto<DisposablePipeline> AddGraphicsPipeline(',
    '        public bool TryGetComputePipeline(',
    '        public bool TryGetGraphicsPipeline(',
    '        public bool TryWaitForBackgroundGraphicsPipeline(',
    '        public bool QueueBackgroundComputePipeline(',
    '        private async Task CompileQueuedComputePipeline(',
    '        private void AddBackgroundComputePipelineFailure(',
    '        public bool QueueBackgroundGraphicsPipeline(',
    '        private async Task CompileQueuedGraphicsPipeline(',
    '        private void AddBackgroundGraphicsPipelineFailure(',
    '        public void CancelPendingWarmUp()',
    '        public void WaitForBackgroundCompilation()',
    '        private void WaitForBackgroundPipelineQueue()',
    '        protected virtual void Dispose(bool disposing)',
    '        public void Dispose()',
]
SHADER = [
    '        public unsafe Shader(Vk api,', '        public unsafe Shader(VulkanRenderer gd,',
    '        private unsafe void Compile(', '        public unsafe PipelineShaderStageCreateInfo GetInfo()',
    '        public void WaitForCompile()', '        public void PromoteCompilation()',
    '        public unsafe void Dispose()',
]
PIPELINE = ['        public void SetProgram(', '        private bool CreatePipeline(',
            '        private bool CanSkipForBackgroundCompile(',
            '        private bool UpdateProgramStagesIfReady(']

reports, member_hashes, full_hashes, postimages = {}, {}, {}, {}
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-cached-startup-') as temporary:
    temporary = str(Path(temporary).resolve())
    baseline = Path(temporary) / 'baseline'
    for relative in FILES:
        target = baseline / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)
    input_renderer = digest(SOURCE / VULKAN / 'VulkanRenderer.cs')
    if input_renderer == BASELINE['VulkanRenderer.cs']:
        preparation = 'accepted_exact_preceding_engine'
    else:
        # Each prerequisite fails closed on its own replacement anchors. The
        # final hashes below bind preparation to the full preceding engine.
        for module, function in PREREQUISITES:
            getattr(importlib.import_module(module), function)(baseline)
        preparation = 'prepared_pristine_prerequisites'
    for name, expected in PREPARED.items():
        assert digest(baseline / VULKAN / name) == expected, name
    prepared_inputs = {relative: digest(baseline / relative) for relative in FILES}

    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        source = work / 'source'
        shutil.copytree(baseline, source)
        if variant == 'candidate':
            changed = apply(source)
            postimages = {str(p.relative_to(source)): digest(p) for p in changed}
        member_hashes[variant] = {}
        full_hashes[variant] = {relative: digest(source / relative) for relative in FILES}

        def extract(name, signatures):
            text = (source / VULKAN / (name + '.cs')).read_text()
            parts = [member(text, signature) for signature in signatures]
            member_hashes[variant][name] = {
                signature.strip(): hashlib.sha256(part.encode()).hexdigest()
                for signature, part in zip(signatures, parts, strict=True)}
            return text, '\n\n'.join(parts)

        text, parts = extract('ShaderCollection', COLLECTION)
        header = text[:text.index(COLLECTION[0])].replace('class ShaderCollection :', 'partial class ShaderCollection :')
        (work / 'ShaderCollection.cs').write_text(header + parts + '\n    }\n}\n')
        text, parts = extract('Shader', SHADER)
        header = text[:text.index(SHADER[0])].replace('class Shader :', 'partial class Shader :')
        (work / 'Shader.cs').write_text(header + parts + '\n    }\n}\n')
        renderer_signatures = ['        public IProgram CreateProgram(', '        public void PreFrame()']
        if variant == 'candidate':
            renderer_signatures += ['        internal void RecordBackgroundPipelineFailure(',
                                   '        internal void ThrowIfBackgroundPipelineFailed()']
        text, parts = extract('VulkanRenderer', renderer_signatures)
        close = member(text, '        public unsafe void Dispose()')
        close = close[close.index('{') + 1:close.index('            Api.DeviceWaitIdle(_device);')]
        member_hashes[variant]['VulkanRenderer']['closeBeforeNativeRelease'] = hashlib.sha256(close.encode()).hexdigest()
        prefix = 'using System; using System.Threading; using System.Runtime.ExceptionServices;\n'
        prefix += 'using Ryujinx.Graphics.GAL; using Ryujinx.Graphics.Shader; using Silk.NET.Vulkan;\n'
        (work / 'VulkanRenderer.cs').write_text(prefix + 'namespace Ryujinx.Graphics.Vulkan { partial class VulkanRenderer {\n' + parts + '\n public void JoinBeforeNativeRelease() {\n' + close + '\n} } }\n')
        text, parts = extract('PipelineBase', PIPELINE)
        (work / 'PipelineBase.cs').write_text(prefix + 'namespace Ryujinx.Graphics.Vulkan { partial class PipelineBase {\n' + parts + '\n} }\n')

        # Execute the production native-result interpretation of both actual
        # pipeline kinds; only vkCreate* and native state packing are doubled.
        state = (source / VULKAN / 'PipelineState.cs').read_text()
        for kind in ('Compute', 'Graphics'):
            body = member(state, '        public unsafe Auto<DisposablePipeline> Create' + kind + 'Pipeline(')
            start = body.index('                if (result is Result.ErrorDeviceLost')
            end = body.index('\n            }\n\n            if (gd.PipelineCacheManager', start)
            result_body = body[start:end]
            member_hashes[variant].setdefault('PipelineState', {})[kind + 'Result'] = hashlib.sha256(result_body.encode()).hexdigest()
            (work / (kind + 'Result.cs')).write_text(prefix + 'using Ryujinx.Common.Logging;\nnamespace Ryujinx.Graphics.Vulkan { partial class PipelineState {\n' +
                'private Auto<DisposablePipeline> Interpret' + kind + '(Result result, ShaderCollection program, bool throwOnError, bool cachePipelineFailure) {\n' +
                result_body + '\nreturn new Auto<DisposablePipeline>(new DisposablePipeline());\n} } }\n')
        for relative in WHOLE_FILES:
            shutil.copyfile(source / relative, work / Path(relative).name)
        for filename in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(ROOT / 'test/melonx_cached_shader_startup' / filename, work / filename)
        define = '<DefineConstants>CACHED_STARTUP_ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0414;0162</NoWarn>
<NuGetAudit>false</NuGetAudit>{define}</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_PROCESSOR_COUNT='6')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                                cwd=work, capture_output=True, text=True, timeout=150, env=environment)
        print(result.stdout, flush=True)
        if result.returncode: print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

for relative in WHOLE_FILES:
    assert full_hashes['control'][relative] == full_hashes['candidate'][relative], relative
assert reports['control']['cachePrograms'] == reports['candidate']['cachePrograms'] == 2743
assert reports['control']['pipelineCompilesBeforeLoaderExit'] == 2743
assert reports['candidate']['pipelineCompilesBeforeLoaderExit'] == 0
inputs = ['build-utils/melonx/adapt_cached_shader_startup.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_cached_shader_startup_test.py', 'test/melonx_cached_shader_startup/Program.cs',
          'test/melonx_cached_shader_startup/Boundaries.cs']
inputs += ['build-utils/melonx/' + module + '.py' for module, _ in PREREQUISITES]
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
    nativeVulkanCallsDoubled=True, pipelineStatePackingDoubled=True, descriptorLayoutBuildingDoubled=True,
    productionMembersVerbatim=True, productionSchedulerComplete=True, productionHashTableComplete=True,
    timingGate=False, preparation=preparation, inputs={p: digest(ROOT / p) for p in inputs},
    upstreamInputs={p: digest(SOURCE / p) for p in FILES}, preparedBaselineInputs=prepared_inputs,
    productionMemberHashes=member_hashes, productionInputs=full_hashes, postimages=postimages)
output = ROOT / 'dist/melonx/cached-shader-startup-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production cached shader startup, demand, failure and teardown checks passed.', flush=True)
