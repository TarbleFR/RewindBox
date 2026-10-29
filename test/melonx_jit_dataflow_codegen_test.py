#!/usr/bin/env python3
"""Compile ARM64 twice against one function table, comparing every output byte.

Baseline is the already-delivered decoder/context/block-split adaptations.
A test-only switch selects either exact dataflow solver in one real CPU
assembly, using one real AddressTable. Embedded host pointers are identical
and no generated instruction needs normalization.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_jit_decoder import apply as decoder_apply
from adapt_jit_context import apply as context_apply
from adapt_jit_block_split import apply as split_apply
from adapt_jit_dataflow import apply as dataflow_apply

pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--',
                                    'src/Ryujinx.Cpu', 'src/ARMeilleure', 'src/Ryujinx.Memory'], text=True).strip()
adapters = ['adapt_jit_decoder.py', 'adapt_jit_context.py', 'adapt_jit_block_split.py', 'adapt_jit_dataflow.py']
with tempfile.TemporaryDirectory(prefix='melonx-dataflow-codegen-') as temporary:
    # macOS aliases /var to /private/var. Use one canonical root for MSBuild's
    # transitive project references, as the existing decoder probe does.
    work = Path(temporary).resolve()
    source = work / 'source'
    for filename in ['Directory.Build.props', 'Directory.Packages.props', 'global.json', 'nuget.config']:
        if (SOURCE / filename).exists():
            source.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / filename, source / filename)
    for project in ('Ryujinx.Cpu', 'ARMeilleure', 'Ryujinx.Memory', 'Ryujinx.Common'):
        shutil.copytree(SOURCE / 'src' / project, source / 'src' / project,
                        ignore=shutil.ignore_patterns('bin', 'obj'))
    decoder_apply(source)
    context_apply(source)
    split_apply(source)
    dataflow = source / 'src/Ryujinx.Cpu/LightningJit/Graph/DataFlow.cs'
    baseline = dataflow.read_text()
    (dataflow.parent / 'BaselineDataFlow.cs').write_text(baseline.replace('static class DataFlow', 'static class BaselineDataFlow', 1))
    dataflow_apply(source)
    text = dataflow.read_text()
    text = text.replace('    static class DataFlow\n    {', '    static class DataFlow\n    {\n        internal static bool ProbeBaseline;', 1)
    text = text.replace('            int count = blocks.Count;', '''            if (ProbeBaseline) return BaselineDataFlow.GetGlobalUses(blocks);
            int count = blocks.Count;''', 1)
    dataflow.write_text(text)
    cpu = source / 'src/Ryujinx.Cpu/Ryujinx.Cpu.csproj'
    text = cpu.read_text(encoding='utf-8-sig')
    cpu.write_text(text.replace('</Project>', '''
<ItemGroup><InternalsVisibleTo Include="MeloNXDataFlowCodegenProbe" /></ItemGroup></Project>'''))
    probe = work / 'probe'
    probe.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_jit_dataflow_codegen/Program.cs', probe / 'Program.cs')
    (probe / 'MeloNXDataFlowCodegenProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn></PropertyGroup><ItemGroup>
<ProjectReference Include="{source}/src/Ryujinx.Cpu/Ryujinx.Cpu.csproj" />
</ItemGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'latestFeature'}}))
    build = subprocess.run(['dotnet', 'build', str(probe), '-c', 'Release', '-m:1', '-nologo', '-v', 'q'],
                           capture_output=True, text=True, timeout=600)
    if build.returncode:
        print(build.stdout[-10000:], build.stderr[-4000:])
        build.check_returncode()
    run = subprocess.run(['dotnet', str(probe / 'bin/Release/net10.0/MeloNXDataFlowCodegenProbe.dll')],
                         capture_output=True, text=True, timeout=180)
    if run.returncode:
        print(run.stdout[-5000:], run.stderr[-5000:])
        run.check_returncode()
    report = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
    report.update(result='passed', generatedArm64Executed=False, physicalDeviceTested=False,
                  upstreamRevision=pin['revision'],
                  inputs={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [*(ROOT / 'build-utils/melonx' / name for name in adapters), Path(__file__),
                                       ROOT / 'test/melonx_jit_dataflow_codegen/Program.cs']})
    output = ROOT / 'dist/melonx/jit-dataflow-codegen-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
