#!/usr/bin/env python3
"""Compare complete production buffer range/migration classes across ownership exits.

GPU fence completion and buffer handles are boundaries; range search, locks,
snapshots, migration and flush selection are real production implementations.
Pool instrumentation changes only the rental provider, with a separate run
using the real shared pool to measure allocations. No physical-device claim.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_buffer_range_snapshots import apply

PATHS = [
    'src/Ryujinx.Graphics.Gpu/Memory/BufferModifiedRangeList.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/BufferMigration.cs',
    'src/Ryujinx.Memory/Range/IRange.cs',
    'src/Ryujinx.Memory/Range/INonOverlappingRange.cs',
    'src/Ryujinx.Memory/Range/RangeListBase.cs',
    'src/Ryujinx.Memory/Range/NonOverlappingRangeList.cs',
]
dotnet = os.environ.get('DOTNET', 'dotnet')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
upstream = {path: hashlib.sha256((SOURCE / path).read_bytes()).hexdigest() for path in PATHS}
assert upstream == {
    PATHS[0]: '606809c5963a3ce1302a0f22615841476bc2c495a18176f59e40f71e265f178e',
    PATHS[1]: '7a28ddf2306df5d82cb2a0d8b21208cb4bc835e0d4a47e9c8c8760cd7cdc3584',
    PATHS[2]: 'd7b661592c0820bba0e7ff19b7d882383f46fd7fe70a0f5f4e5bdadc6e032651',
    PATHS[3]: '15d4eb27f4f4e25eb4f3bf369fb6cdc6a68ab1874990505bba0b8dd75eeaac95',
    PATHS[4]: '32e1108eb72704f942fe62ceb361f60e2df8b6e4450f11dbb6fcb89f04b156e3',
    PATHS[5]: 'cecd0546d26c60f64c62ec3438b71bd64bf4981dbd9c92ef6dbae3a9403adf95',
}, 'Production buffer range input changed'
reports, compiled, postimages = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-buffer-range-snapshots-') as temporary:
    for variant in ('control', 'candidate'):
        reports[variant] = {}
        for mode in ('ownership', 'allocation'):
            work = Path(temporary) / variant / mode
            for path in PATHS:
                dest = work / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / path, dest)
            if variant == 'candidate':
                changed = apply(work)
                current = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
                if postimages:
                    assert postimages == current
                postimages = current
            if mode == 'ownership':
                for path in PATHS:
                    dest = work / path
                    text = dest.read_text(encoding='utf-8-sig')
                    text = text.replace('ArrayPool<BufferModifiedRange>.Shared', 'ProbePool<BufferModifiedRange>.Shared')
                    text = text.replace('ArrayPool<T>.Shared', 'ProbePool<T>.Shared')
                    dest.write_text(text)
            for name in ('Program.cs', 'Boundaries.cs'):
                shutil.copyfile(ROOT / 'test/melonx_buffer_range_snapshots' / name, work / name)
            flags = ';'.join([*(['ADAPTED'] if variant == 'candidate' else []),
                              *(['POOL_PROBE'] if mode == 'ownership' else [])])
            (work / 'Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>
<DefineConstants>{flags}</DefineConstants></PropertyGroup></Project>''')
            (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
            (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
            environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
            result = subprocess.run([dotnet, 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release'],
                cwd=work, env=environment, capture_output=True, text=True, timeout=180)
            if result.returncode:
                print(result.stdout, result.stderr, flush=True)
            result.check_returncode()
            reports[variant][mode] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
            compiled[f'{variant}/{mode}'] = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(work.rglob('*.cs')) if 'obj' not in path.relative_to(work).parts}
            print(variant, mode, json.dumps(reports[variant][mode]), flush=True)

assert len({r['semanticDigest'] for v in reports.values() for r in v.values()}) == 1
assert reports['candidate']['allocation']['measurements']['allocatedBytes'] == 0
assert reports['control']['allocation']['measurements']['allocatedBytes'] > 0
inputs = ['build-utils/melonx/adapt_buffer_range_snapshots.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/source.json', 'test/melonx_buffer_range_snapshots_test.py',
          'test/melonx_buffer_range_snapshots/Program.cs', 'test/melonx_buffer_range_snapshots/Boundaries.cs']
receipt = dict(result='passed', upstreamRevision=pin['revision'], dotnet=pin['dotnet'], reports=reports,
    physicalDeviceTested=False, fenceAndBufferHandlesDoubled=True, upstreamInputs=upstream,
    postimages=postimages, compiledSourceInputs=compiled,
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
output = ROOT / 'dist/melonx/buffer-range-snapshot-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Buffer range snapshots: production equivalence, ownership and allocations passed.', flush=True)
