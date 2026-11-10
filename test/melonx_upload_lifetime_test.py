#!/usr/bin/env python3
"""Compile production upload-pool and texture-sync paths, control versus fixed.

Usage: python3 test/melonx_upload_lifetime_test.py <pinned MeloNX checkout>
The fixed pool is built after the established allocation adaptation. Its idle
clock is advanced in the host harness; no game memory or GPU timing is simulated.
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
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == PIN['revision']
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_gpu_allocations import adapt_owner as established_owner, adapt_fifo
from adapt_upload_lifetime import adapt_owner, adapt_texture

OWNER = Path('src/Ryujinx.Common/Memory/MemoryOwner.cs')
TEXTURE = Path('src/Ryujinx.Graphics.Gpu/Image/Texture.cs')
HARNESS = ROOT / 'test/melonx_upload_lifetime'
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-upload-lifetime-') as directory:
    for mode in ['control', 'fixed']:
        work = Path(directory) / mode
        for path in [OWNER, TEXTURE]:
            (work / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, work / path)
        established_owner(work)
        # Bind the control to the delivered 7be2a83b engine's exact adapted pool.
        assert hashlib.sha256((work / OWNER).read_bytes()).hexdigest() == '07feff3dbb46d14119cef8b04e3047932288b444ba7c7bf143bcb40a8556df0a'
        if mode == 'fixed':
            adapt_owner(work)
            adapt_texture(work)
        text = (work / TEXTURE).read_text(encoding='utf-8-sig')
        start = text.index('        public void SynchronizeFull()')
        end = text.index('\n        /// <summary>', start)
        (work / 'Texture.cs').write_text('using System;\nsealed partial class Texture\n{\n' + text[start:end] + '\n}\n')
        for name in ['Program.cs', 'TextureBoundary.cs']:
            shutil.copyfile(HARNESS / name, work / name)
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<Nullable>enable</Nullable><EnableDefaultCompileItems>false</EnableDefaultCompileItems>
</PropertyGroup><ItemGroup><Compile Include="Program.cs"/><Compile Include="Texture.cs"/>
<Compile Include="TextureBoundary.cs"/><Compile Include="src/Ryujinx.Common/Memory/MemoryOwner.cs"/>
</ItemGroup></Project>''')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'latestPatch'}}))
        subprocess.run(['dotnet', 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                       cwd=work, check=True, timeout=120)
        run = subprocess.run(['dotnet', 'bin/Release/net10.0/Probe.dll', mode], cwd=work,
                             capture_output=True, text=True, check=True, timeout=60)
        report = json.loads(run.stdout.strip().splitlines()[-1])
        reports.append(report)

    # The primary-array lifetime changed: run the established pool/lease/FIFO assertions
    # against the final adapted pool too, without modifying their previously tested inputs.
    legacy = Path(directory) / 'established'
    fifo_path = Path('src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs')
    for path in [OWNER, fifo_path]:
        (legacy / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / path, legacy / path)
    established_owner(legacy)
    adapt_owner(legacy)
    fifo = adapt_fifo(legacy)
    text = fifo.read_text()
    needle = 'System.Buffers.ArrayPool<int>.Shared;'
    assert text.count(needle) == 1
    fifo.write_text(text.replace(needle, 'TrackingPool.Shared;'))
    for name in ['Program.cs', 'Fakes.cs']:
        shutil.copyfile(ROOT / 'test/melonx_gpu_allocations' / name, legacy / name)
    (legacy / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<Nullable>enable</Nullable><EnableDefaultCompileItems>false</EnableDefaultCompileItems>
</PropertyGroup><ItemGroup><Compile Include="Program.cs"/><Compile Include="Fakes.cs"/>
<Compile Include="src/Ryujinx.Common/Memory/MemoryOwner.cs"/>
<Compile Include="src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs"/>
</ItemGroup></Project>''')
    (legacy / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'latestPatch'}}))
    subprocess.run(['dotnet', 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                   cwd=legacy, check=True, timeout=120)
    run = subprocess.run(['dotnet', 'bin/Release/net10.0/Probe.dll'], cwd=legacy,
                         capture_output=True, text=True, check=True, timeout=60)
    established = json.loads(run.stdout.strip().splitlines()[-1])

    def hashes(base, paths):
        return {str(path): hashlib.sha256((base / path).read_bytes()).hexdigest() for path in paths}

    evidence = {
        'result': 'passed', 'reports': reports, 'establishedPoolRegression': established,
        'physicalDeviceTested': False, 'upstreamRevision': PIN['revision'],
        'inputs': hashes(ROOT, [Path('build-utils/melonx/adapt_upload_lifetime.py'),
                               Path('build-utils/melonx/adapt_gpu_allocations.py'),
                               Path('build-utils/melonx/adapt_session.py'),
                               Path('build-utils/melonx/source.json'), Path('test/melonx_upload_lifetime_test.py'),
                               *[path.relative_to(ROOT) for path in sorted(HARNESS.glob('*.cs'))],
                               Path('test/melonx_gpu_allocations/Program.cs'), Path('test/melonx_gpu_allocations/Fakes.cs')]),
        'upstreamInputs': hashes(SOURCE, [OWNER, TEXTURE, fifo_path]),
    }
    output = ROOT / 'dist/melonx/upload-lifetime-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
    print(json.dumps(evidence, sort_keys=True))
