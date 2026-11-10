#!/usr/bin/env python3
"""Compile the pinned production pool/FIFO; exercise allocations, leases and exceptional returns.

Usage: python3 test/melonx_gpu_allocations_test.py <pinned MeloNX checkout>
This is a host allocation/ownership check, not an iPhone frame-rate benchmark.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_gpu_allocations import adapt_fifo, adapt_owner

SOURCE = Path(sys.argv[1]).resolve()
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == PIN['revision']
paths = [Path('src/Ryujinx.Common/Memory/MemoryOwner.cs'),
         Path('src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs')]
with tempfile.TemporaryDirectory(prefix='melonx-allocation-test-') as directory:
    work = Path(directory)
    for path in paths:
        destination = work / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / path, destination)
    owner, fifo = adapt_owner(work), adapt_fifo(work)
    needle = 'System.Buffers.ArrayPool<int>.Shared;'
    text = fifo.read_text()
    assert text.count(needle) == 1
    # Count exact rents/returns without relying on Shared pool bucket ordering.
    fifo.write_text(text.replace(needle, 'TrackingPool.Shared;'))
    for name in ['Program.cs', 'Fakes.cs']:
        shutil.copyfile(ROOT / 'test/melonx_gpu_allocations' / name, work / name)
    (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
  </PropertyGroup><ItemGroup>
    <Compile Include="Program.cs"/><Compile Include="Fakes.cs"/>
    <Compile Include="src/Ryujinx.Common/Memory/MemoryOwner.cs"/>
    <Compile Include="src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs"/>
  </ItemGroup>
</Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'latestPatch'}}))
    subprocess.run(['dotnet', 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                   cwd=work, check=True, timeout=120)
    result = subprocess.run(['dotnet', 'bin/Release/net10.0/Probe.dll'], cwd=work,
                            check=True, capture_output=True, text=True, timeout=60)
    report = json.loads(result.stdout.strip().splitlines()[-1])
    report['sourceSha256'] = {str(path): hashlib.sha256((SOURCE / path).read_bytes()).hexdigest() for path in paths}
    print(json.dumps(report, sort_keys=True))
