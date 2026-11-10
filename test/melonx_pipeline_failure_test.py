#!/usr/bin/env python3
"""Execute production shader lifetime/result paths with deterministic Vulkan I/O.

Both original and adapted methods run. This is not a GPU pixel or game test.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_pipeline import apply


def method(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


paths = ['src/Ryujinx.Graphics.Vulkan/' + p + '.cs'
         for p in ['ShaderCollection', 'PipelineState', 'VulkanException']]
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-pipeline-failure-') as temporary:
    for old in [True, False]:
        work = Path(temporary) / ('control' if old else 'fixed')
        source = work / 'source'
        for p in paths:
            target = source / p
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / p, target)
        if not old: apply(source)
        text = (source / paths[0]).read_text()
        methods = '\n'.join(method(text, signature) for signature in [
            'private async Task BackgroundCompilation()',
            'private void LogBackgroundPipelineFailure(',
            'private void EnsureShadersReadyLegacy()',
            'private bool EnsureShadersReady(',
            'public PipelineShaderStageCreateInfo[] GetInfos()',
            'public ProgramLinkStatus CheckProgramLink(',
            'public void CreateBackgroundComputePipeline(',
            'public void CreateBackgroundGraphicsPipeline(',
        ])
        template = (ROOT / 'test/melonx_pipeline/Double.cs').read_text()
        (work / 'Double.cs').write_text(template.replace('/* PRODUCTION_METHODS */', methods))
        shutil.copyfile(source / paths[2], work / 'VulkanException.cs')
        # Execute the exact graphics API-result handling block too. Native
        # structs and vkCreateGraphicsPipelines itself are deliberately doubled.
        state = (source / paths[1]).read_text()
        graphics = method(state, 'public unsafe Auto<DisposablePipeline> CreateGraphicsPipeline(')
        start = graphics.index('                if (result == Result.PipelineCompileRequired)')
        fatal = '                if (result is Result.ErrorDeviceLost'
        if fatal in graphics: start = graphics.index(fatal)
        end = graphics.index('\n            }\n\n            if (gd.PipelineCacheManager', start)
        (work / 'Result.cs').write_text('''using Ryujinx.Common.Logging;
using Silk.NET.Vulkan;
namespace Ryujinx.Graphics.Vulkan {
partial class PipelineState {
object Interpret(Result result, ShaderCollection program, bool throwOnError, bool cachePipelineFailure) {
''' + graphics[start:end] + '\n return new object();\n}\n}\n}\n')
        shutil.copyfile(ROOT / 'test/melonx_pipeline/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NoWarn>CS0649;CS0414</NoWarn>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release', '--', 'control' if old else 'fixed'],
                                capture_output=True, text=True, timeout=120)
        print(result.stdout, flush=True)
        if result.returncode: print(result.stderr, flush=True)
        result.check_returncode()
        reports.append(json.loads(next(s for s in result.stdout.splitlines() if s.startswith('{'))))
inputs = ['build-utils/melonx/adapt_pipeline.py', 'test/melonx_pipeline_failure_test.py',
          'test/melonx_pipeline/Double.cs', 'test/melonx_pipeline/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, vulkanDouble=True,
    inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
    upstreamInputs={p:hashlib.sha256((SOURCE/p).read_bytes()).hexdigest() for p in paths})
out = ROOT / 'dist/melonx/pipeline-failure-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
