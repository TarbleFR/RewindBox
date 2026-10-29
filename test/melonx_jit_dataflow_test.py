#!/usr/bin/env python3
"""Differential test of the pinned production register fixed-point solvers."""
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
from adapt_jit_dataflow import apply

pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
relative = 'src/Ryujinx.Cpu/LightningJit/Graph/DataFlow.cs'
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', relative], text=True).strip()
with tempfile.TemporaryDirectory(prefix='melonx-dataflow-') as temporary:
    work = Path(temporary)
    adapted = work / 'source'
    target = adapted / relative
    target.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / relative, target)
    apply(adapted)
    baseline = (SOURCE / relative).read_text()
    candidate = target.read_text()
    (work / 'Baseline.cs').write_text(baseline.replace('static class DataFlow', 'static class BaselineDataFlow', 1))
    (work / 'Candidate.cs').write_text(candidate)
    # Only replace the scratch-array provider to inject Rent/graph failures;
    # all fixed-point and queue code stays the exact production code.
    (work / 'PoolProbe.cs').write_text(candidate.replace('static class DataFlow', 'static class PoolProbeDataFlow', 1)
                                    .replace('ArrayPool<int>.Shared', 'SpyPool<int>.Shared')
                                    .replace('ArrayPool<byte>.Shared', 'SpyPool<byte>.Shared'))
    files = [SOURCE / ('src/Ryujinx.Cpu/LightningJit/' + name) for name in [
        'Graph/IBlock.cs', 'Graph/IBlockList.cs', 'Graph/RegisterUse.cs', 'Graph/RegisterMask.cs',
        'Arm64/Block.cs', 'Arm64/InstInfo.cs', 'Arm64/InstName.cs', 'Arm64/InstFlags.cs', 'AddressForm.cs']]
    for path in files:
        shutil.copyfile(path, work / path.name)
    shutil.copyfile(ROOT / 'test/melonx_jit_dataflow/Program.cs', work / 'Program.cs')
    (work / 'DataFlowProbe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'latestFeature'}}))
    result = subprocess.run(['dotnet', 'run', '--project', str(work), '-c', 'Release', '-v', 'q'],
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        print(result.stdout, result.stderr)
        result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    report.update(result='passed', generatedArm64Executed=False, physicalDeviceTested=False,
                  upstreamRevision=pin['revision'],
                  inputs={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [ROOT / 'build-utils/melonx/adapt_jit_dataflow.py', Path(__file__),
                                       ROOT / 'test/melonx_jit_dataflow/Program.cs']},
                  upstreamInputs={str(path.relative_to(SOURCE)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in [SOURCE / relative, *files]})
    output = ROOT / 'dist/melonx/jit-dataflow-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
