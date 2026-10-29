#!/usr/bin/env python3
"""Execute real key methods and count actual NativeArray host allocations.

One complete Vulkan production assembly contains the original key method under
a fixture-only name and the candidate method. The existing vertex-state corpus
is reused in that same assembly. Only Marshal's allocation/free boundary gains
test counters; the wrapped host allocations still occur. No Vulkan/Metal API is
called, no shader is compiled and no device-performance claim follows.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_pipeline_key_allocation import apply, BASELINE


def method(text, signature):
    assert text.count(signature) == 1
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


vulkan = SOURCE / 'src/Ryujinx.Graphics.Vulkan'
for name, digest in BASELINE.items():
    assert hashlib.sha256((vulkan / name).read_bytes()).hexdigest() == digest, name
original = method((vulkan / 'ShaderCollection.cs').read_text(), '        private PipelineUid GetInitialGraphicsPipelineKey()')
projects = ['Ryujinx.Graphics.Vulkan', 'Ryujinx.Common', 'Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Shader', 'Spv.Generator']
with tempfile.TemporaryDirectory(prefix='melonx-pipeline-key-') as temporary:
    work = Path(temporary)
    for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', '.editorconfig'):
        if (SOURCE / name).exists(): shutil.copyfile(SOURCE / name, work / name)
    for project in projects:
        shutil.copytree(SOURCE / 'src' / project, work / 'src' / project,
            ignore=shutil.ignore_patterns('bin', 'obj'))
    apply(work)
    directory = work / 'src/Ryujinx.Graphics.Vulkan'
    postimages = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in BASELINE}
    collection = directory / 'ShaderCollection.cs'
    text = collection.read_text()
    marker = '        private PipelineUid GetInitialGraphicsPipelineKey()'
    assert text.count(marker) == 1
    control = original.replace(marker, '        private PipelineUid ControlGetInitialGraphicsPipelineKey()')
    collection.write_text(text.replace(marker, control + '\n\n' + marker))
    native = directory / 'NativeArray.cs'
    text = native.read_text()
    for old, new in [
        ('Marshal.AllocHGlobal(checked(length * Unsafe.SizeOf<T>()))',
         'global::NativeStageAllocationMeter.Allocate(checked(length * Unsafe.SizeOf<T>()))'),
        ('Marshal.FreeHGlobal((nint)Pointer)', 'global::NativeStageAllocationMeter.Free((nint)Pointer)'),
    ]:
        assert text.count(old) == 1
        text = text.replace(old, new)
    native.write_text(text)
    # These fixture-only access modifiers reuse the exact existing cases and
    # driver boundary setup without copying their implementation into a new test.
    corpus = (ROOT / 'test/melonx_pipeline_vertex_state/Program.cs').read_text()
    for signature in ['static VulkanRenderer Renderer(', 'static ProgramPipelineState State(', 'static void Main(']:
        assert corpus.count(signature) == 1
        corpus = corpus.replace(signature, 'internal ' + signature)
    (directory / 'Program.cs').write_text(corpus)
    shutil.copyfile(ROOT / 'test/melonx_pipeline_key_allocation/Program.cs', directory / 'KeyAllocationProgram.cs')
    project = directory / 'Ryujinx.Graphics.Vulkan.csproj'
    tree = ET.parse(project)
    group = ET.SubElement(tree.getroot(), 'PropertyGroup')
    for name, value in [('OutputType', 'Exe'), ('StartupObject', 'KeyAllocationProgram'),
                        ('NuGetAudit', 'false'), ('EnableNETAnalyzers', 'false')]:
        ET.SubElement(group, name).text = value
    tree.write(project)
    environment = os.environ.copy()
    environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_TieredCompilation='0')
    feed = os.environ.get('MELONX_TEST_PACKAGE_FEED')
    if feed:
        import html
        (work / 'nuget.config').write_text('<configuration><packageSources><clear />'
            f'<add key="offline" value="{html.escape(feed, quote=True)}" /></packageSources></configuration>')
    for command in [
        ['dotnet', 'restore', str(project), '--disable-parallel', '-m:1'],
        ['dotnet', 'build', str(project), '-c', 'Release', '--no-restore', '-m:1'],
        ['dotnet', str(directory / 'bin/Release/net10.0/Ryujinx.Graphics.Vulkan.dll')],
    ]:
        result = subprocess.run(command, capture_output=True, text=True, timeout=240,
            env=environment, cwd=work)
        if result.returncode: print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
    reports = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    assert len(reports) == 2
    for report in reports: print(json.dumps(report), flush=True)
inputs = ['build-utils/melonx/adapt_pipeline_key_allocation.py', 'test/melonx_pipeline_key_allocation_test.py',
          'test/melonx_pipeline_key_allocation/Program.cs', 'test/melonx_pipeline_vertex_state/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, vulkanOrMetalCallsUsed=False,
    fullProductionVulkanAssembly=True, hostNativeAllocatorCounted=True,
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    productionInputs=BASELINE, unchangedNativeArrayInput=hashlib.sha256((vulkan / 'NativeArray.cs').read_bytes()).hexdigest(),
    productionPostimages=postimages,
    limitation='Host allocation counts and key equality only; no iPhone FPS/RAM measurements.')
out = ROOT / 'dist/melonx/pipeline-key-allocation-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
