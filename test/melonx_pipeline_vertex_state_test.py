#!/usr/bin/env python3
"""Run the complete production Vulkan converter/state/key against stride rules.

Requires an already prepared exact engine. Compiles actual Vulkan/Common/GAL/
Shader/Spv sources in isolated temporary copies; physical driver capabilities
are populated by the fixture, with no Vulkan or Metal entry point invoked.
"""
from pathlib import Path
import contextlib, hashlib, json, os, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_pipeline_vertex_state import apply, BASELINE

relative = 'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs'
assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == BASELINE
projects = ['Ryujinx.Graphics.Vulkan', 'Ryujinx.Common', 'Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Shader', 'Spv.Generator']
reports = []
temporary_root = os.environ.get('MELONX_TEST_WORKDIR')
with (contextlib.nullcontext(temporary_root) if temporary_root else
      tempfile.TemporaryDirectory(prefix='melonx-pipeline-vertex-')) as temporary:
    for variant in ('control', 'candidate'):
        # macOS aliases /var to /private/var; keep MSBuild project identities canonical.
        work = Path(temporary).resolve() / variant
        work.mkdir()
        for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', '.editorconfig'):
            if (SOURCE / name).exists(): shutil.copyfile(SOURCE / name, work / name)
        for project in projects:
            shutil.copytree(SOURCE / 'src' / project, work / 'src' / project,
                ignore=shutil.ignore_patterns('bin', 'obj'))
        if variant == 'candidate': apply(work)
        project = work / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'
        tree = ET.parse(project)
        group = ET.SubElement(tree.getroot(), 'PropertyGroup')
        for name, value in [('OutputType', 'Exe'), ('StartupObject', 'Program'),
                            ('NuGetAudit', 'false'), ('EnableNETAnalyzers', 'false')]:
            ET.SubElement(group, name).text = value
        tree.write(project)
        shutil.copyfile(ROOT / 'test/melonx_pipeline_vertex_state/Program.cs', project.parent / 'Program.cs')
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1')
        feed = os.environ.get('MELONX_TEST_PACKAGE_FEED')
        if feed:
            import html
            (work / 'nuget.config').write_text('<configuration><packageSources><clear />'
                f'<add key="offline" value="{html.escape(feed, quote=True)}" /></packageSources></configuration>')
        for command in [
            ['dotnet', 'restore', str(project), '--disable-parallel', '-m:1'],
            ['dotnet', 'build', str(project), '-c', 'Release', '--no-restore', '-m:1'],
            ['dotnet', str(project.parent / 'bin/Release/net10.0/Ryujinx.Graphics.Vulkan.dll'), variant],
        ]:
            result = subprocess.run(command, capture_output=True, text=True, timeout=240,
                env=environment, cwd=work)
            if result.returncode: print(result.stdout, result.stderr, flush=True)
            result.check_returncode()
        report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(report), flush=True)
        reports.append(report)
inputs = ['build-utils/melonx/adapt_pipeline_vertex_state.py', 'test/melonx_pipeline_vertex_state_test.py',
          'test/melonx_pipeline_vertex_state/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, nativeCallsUsed=False,
    fullProductionVulkanAssembly=True,
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    converterInput=BASELINE,
    runtimeOracleSources={p: hashlib.sha256((SOURCE / 'src/Ryujinx.Graphics.Vulkan' / p).read_bytes()).hexdigest()
        for p in ['PipelineBase.cs', 'VertexBufferState.cs', 'VulkanRenderer.cs']},
    limitation='Oracle covers fresh bindings, not retained scalar alignment on historically unused buffers; no device FPS measured.')
out = ROOT / 'dist/melonx/pipeline-vertex-state-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
