#!/usr/bin/env python3
"""Execute production Vulkan tables and pipeline keys with real Silk.NET types."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_pipeline_lookup import apply, UPSTREAM

FILES = ['src/Ryujinx.Graphics.Vulkan/' + name for name in UPSTREAM]
FILES += ['src/Ryujinx.Common/Memory/StructArrayHelpers.cs', 'src/Ryujinx.Common/Memory/IArray.cs']
pins = dict(('src/Ryujinx.Graphics.Vulkan/' + p, h) for p, h in UPSTREAM.items())
pins.update({
    FILES[2]: 'ee9871e0099b206b7306214402b7241cc61d22632e5709708122f581b2d7074a',
    FILES[3]: '0b4ba835fe89f680b0e4faff63e2f736727647a68a32f37d6ee0b193498c563b',
})
for path, digest in pins.items():
    assert hashlib.sha256((SOURCE / path).read_bytes()).hexdigest() == digest, path
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
packages = ET.parse(SOURCE / 'Directory.Packages.props').getroot()
silk = next(node.attrib['Version'] for node in packages.iter('PackageVersion')
            if node.attrib.get('Include') == 'Silk.NET.Vulkan')
assert silk == '2.22.0', silk
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-pipeline-lookup-') as temporary:
    for variant in ('control', 'table', 'candidate'):
        work = Path(temporary).resolve() / variant
        source = work / 'source'
        for path in FILES:
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        if variant != 'control':
            apply(source)
            if variant == 'table':
                shutil.copyfile(SOURCE / FILES[1], source / FILES[1])
        for path in FILES:
            shutil.copyfile(source / path, work / Path(path).name)
        shutil.copyfile(ROOT / 'test/melonx_pipeline_lookup/Program.cs', work / 'Program.cs')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableNETAnalyzers>false</EnableNETAnalyzers>
</PropertyGroup><ItemGroup><Compile Remove="source/**" />
<PackageReference Include="Silk.NET.Vulkan" Version="{silk}" /></ItemGroup></Project>''')
        feed = os.environ.get('MELONX_TEST_PACKAGE_FEED')
        if feed:
            import html
            (work / 'nuget.config').write_text('<configuration><packageSources><clear />'
                f'<add key="local" value="{html.escape(feed, quote=True)}" /></packageSources></configuration>')
        environment = os.environ.copy()
        environment.update(DOTNET_TieredCompilation='0', DOTNET_CLI_TELEMETRY_OPTOUT='1')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'),
                                 '-c', 'Release', '--', variant], cwd=work,
                                capture_output=True, text=True, timeout=240, env=environment)
        if result.returncode:
            print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        reports.append(json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{'))))
control, table, candidate = reports
assert table['insertionAllocatedBytes'] < control['insertionAllocatedBytes'] * .35, reports
assert candidate['pipelineInsertionAllocatedBytes'] < control['pipelineInsertionAllocatedBytes'] * .05, reports
assert candidate['pipelineEqualityChecks'] < control['pipelineEqualityChecks'] * .05, reports
assert control['pipelineDistinctHashes'] == 1, reports
assert candidate['pipelineDistinctHashes'] > candidate['pipelineCount'] * .98, reports
inputs = ['build-utils/melonx/adapt_pipeline_lookup.py', 'test/melonx_pipeline_lookup_test.py',
          'test/melonx_pipeline_lookup/Program.cs']
receipt = {'result': 'passed', 'reports': reports, 'physicalDeviceTested': False,
           'completeProductionClasses': True, 'nativeCallsUsed': False,
           'silkVulkanVersion': silk, 'runtimeEnvironment': {'DOTNET_TieredCompilation': '0'},
           'inputs': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
           'upstreamInputs': pins}
out = ROOT / 'dist/melonx/pipeline-lookup-checks.json'
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt), flush=True)
