#!/usr/bin/env python3
"""Compile both exact production pool managers. Only the Vulkan API boundary is simulated."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'build-utils/melonx'), str(ROOT / 'test')]
import adapt_descriptor_pool_capacity as adapter
from melonx_adapter_control import control_source

BOUNDARY = 'test/melonx_buffer_mirror_windows/DescriptorPools.cs'
PROBE = 'test/melonx_descriptor_pool_capacity/Program.cs'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(source, variant, project):
    project.mkdir()
    shutil.copyfile(source / adapter.MANAGER, project / 'DescriptorSetManager.cs')
    shutil.copyfile(ROOT / PROBE, project / 'Program.cs')
    boundary = (ROOT / BOUNDARY).read_text().replace('namespace AfterPool', 'namespace Ryujinx.Graphics.Vulkan')
    (project / 'Boundary.cs').write_text(boundary)
    (project / 'Pool.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
  </PropertyGroup>
</Project>''')
    dotnet = os.environ.get('DOTNET', 'dotnet')
    subprocess.run([dotnet, 'build', '-c', 'Release', '-p:NuGetAudit=false'], cwd=project, check=True)
    raw = subprocess.check_output([dotnet, str(project / 'bin/Release/net10.0/Pool.dll'), variant], text=True)
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('--candidate-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/melonx/descriptor-pool-capacity-checks.json')
    args = parser.parse_args()
    final = args.candidate_source.resolve()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Only these two source files enter the adapter. Avoid copying an entire NativeAOT checkout.
        subset = root / 'source'
        for name in adapter.BASELINE:
            (subset / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(final / name, subset / name)
        holders = []
        before, bound = control_source(subset, 'adapt_descriptor_pool_capacity', holders)
        assert bound
        control = measure(before, 'control', root / 'control')
        candidate = measure(final, 'candidate', root / 'candidate')
    assert control == {'pools': 65, 'sets': 65} and candidate == {'pools': 9, 'sets': 65}
    inputs = [BOUNDARY, PROBE, 'build-utils/melonx/adapt_descriptor_pool_capacity.py',
              'test/melonx_adapter_control.py', 'test/melonx_descriptor_pool_capacity_test.py']
    receipt = dict(result='passed', finalPreparationBound=True, physicalDeviceTested=False,
                   sourceKind='finalPreparationWithReversedControl', controlPools=control['pools'],
                   candidatePools=candidate['pools'], setsPerRun=65, sourceBaseline=adapter.BASELINE,
                   inputs={p: sha(ROOT / p) for p in inputs}, postimages={p: sha(final / p) for p in adapter.BASELINE})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
