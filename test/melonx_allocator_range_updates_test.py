#!/usr/bin/env python3
"""Check whole allocator classes and count range-list movement separately from timing.

Vulkan allocation/map/free calls are a strict existing native-driver double.
Valid ranges use an independent wide-arithmetic first-fit model. Zero/wrapped/
overlapping histories compare exact legacy states across both executables.
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
from adapt_allocator_range_updates import apply, BASELINE, RELATIVE

PREIMAGES = {
    RELATIVE: BASELINE,
    'src/Ryujinx.Graphics.Vulkan/MemoryAllocation.cs': '8e871eedcbc45750022c45a497fc4c1a482ea908f1c04e3ae7cd5a8ab8e022b2',
    'src/Ryujinx.Graphics.Vulkan/VulkanException.cs': '6a889a31001fa3973eebcaafe9eb82615a840a791edb823ef0379c5db1120294',
    'src/Ryujinx.Common/Utilities/BitUtils.cs': '3f33297b391f95cfba6d3ec848b69f94534848b74f919310181e0a51eb450261',
}
for relative, expected in PREIMAGES.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
boundary = ROOT / 'test/melonx_allocator_blocks/Boundaries.cs'
assert hashlib.sha256(boundary.read_bytes()).hexdigest() == '7b00ad236e58e5335ee51a0abf68d63cf9c896ac56bfc86f456fe79458f01836'
dotnet = os.environ.get('DOTNET', 'dotnet')
reports, postimages, compiled = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-range-updates-') as temporary:
    for variant in ('control', 'candidate'):
        reports[variant] = {}
        for mode in ('movement', 'timing'):
            work = Path(temporary) / variant / mode
            for relative in PREIMAGES:
                target = work / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / relative, target)
            if variant == 'candidate':
                changed = apply(work)
                hashes = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
                if postimages: assert hashes == postimages
                postimages = hashes
            if mode == 'movement':
                path = work / RELATIVE
                text = path.read_text()
                assert text.count('List<Range> _freeRanges') == 1
                path.write_text(text.replace('List<Range> _freeRanges', 'TrackedRangeList<Range> _freeRanges'))
            for name in ('Program.cs', 'RangeListProbe.cs'):
                shutil.copyfile(ROOT / 'test/melonx_allocator_range_updates' / name, work / name)
            shutil.copyfile(boundary, work / 'Boundaries.cs')
            flags = 'RANGE_PROBE' if mode == 'movement' else ''
            (work / 'Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers>
<NuGetAudit>false</NuGetAudit><DefineConstants>{flags}</DefineConstants></PropertyGroup></Project>''')
            (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
            (work / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
            environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
            result = subprocess.run([dotnet, 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release'],
                cwd=work, env=environment, capture_output=True, text=True, timeout=240)
            if result.returncode: print(result.stdout, result.stderr, flush=True)
            result.check_returncode()
            reports[variant][mode] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
            compiled[f'{variant}/{mode}'] = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(work.rglob('*.cs')) if 'obj' not in p.relative_to(work).parts}
            print(variant, mode, json.dumps(reports[variant][mode]), flush=True)

assert len({v['semanticDigest'] for report in reports.values() for v in report.values()}) == 1
old, new = [reports[v]['movement']['benchmarks'] for v in ('control', 'candidate')]
for a, b in zip(old, new, strict=True):
    assert (a['holes'], a['shape'], a['iterations']) == (b['holes'], b['shape'], b['iterations'])
    assert a['allocatedBytes'] == b['allocatedBytes'] == 0
    if a['shape'] == 'prefix-tail':
        assert a['shiftedElements'] == a['iterations'] * a['holes'] * 6
        assert b['shiftedElements'] == b['iterations'] * b['holes'] * 2
    elif a['shape'] in ('prefix', 'tail'):
        assert a['shiftedElements'] == a['iterations'] * a['holes'] * 4
        assert b['shiftedElements'] == 0
    else:
        assert a['shiftedElements'] == b['shiftedElements']
inputs = ['build-utils/melonx/adapt_allocator_range_updates.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_allocator_range_updates_test.py', 'test/melonx_allocator_range_updates/Program.cs',
          'test/melonx_allocator_range_updates/RangeListProbe.cs', 'test/melonx_allocator_blocks/Boundaries.cs']
receipt = dict(result='passed', reports=reports, upstreamRevision='13700519f3abc4e6d7ed8a065b118b2cc59bcd67',
    dotnet='10.0.100', physicalDeviceTested=False, nativeDriverDoubled=True,
    completeProductionAllocator=True, movementInstrumentedSeparately=True,
    upstreamInputs=PREIMAGES, postimages=postimages, compiledSourceInputs=compiled,
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
output = ROOT / 'dist/melonx/allocator-range-update-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Allocator range first-fit, movement, lifecycle and host allocation checks passed.', flush=True)
