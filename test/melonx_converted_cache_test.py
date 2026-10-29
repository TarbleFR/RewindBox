#!/usr/bin/env python3
"""Compile the full converted-buffer cache and test lookups/lifetime/missing ranges.

The GPU payload and transport are doubled; all cache methods, production key
implementations and dependency dispatch are unmodified production source in
the control. Missing-range retention is measured explicitly; normal miss+Add
and stable-hit paths are measured too, not advertised as allocation savings.
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
from adapt_converted_cache import apply

PREIMAGES = {'src/Ryujinx.Graphics.Vulkan/CacheByRange.cs': '4791ea9c7560be75dcb1be2cc08cf486bbde243b6bee920d721342b172baeca1'}
CALLERS = {'src/Ryujinx.Graphics.Vulkan/BufferHolder.cs': '08aecc7d52238889a2a7ec242844b2242ff766301a3f15b13b9712b6589e6b40', 'src/Ryujinx.Graphics.Vulkan/BufferManager.cs': '73bb8f6d328039d495a4944be52dfb6b1b1dfcb661198e05a74fcd3084b05d36'}

for relative, expected in {**PREIMAGES, **CALLERS}.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
dotnet = os.environ.get('DOTNET', 'dotnet')
reports = {}
postimages = {}
compiled = {}
with tempfile.TemporaryDirectory(prefix='melonx-converted-cache-') as temporary:
    base = Path(temporary)
    for variant in ('control', 'candidate'):
        work = base / variant
        for relative in PREIMAGES:
            target = work / relative; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest() for path in changed}
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(ROOT / 'test/melonx_converted_cache' / name, work / name)
        sources = list(PREIMAGES) + ['Program.cs', 'Boundaries.cs']
        compiled[variant] = {p: hashlib.sha256((work / p).read_bytes()).hexdigest() for p in sources}
        includes = ''.join(f'<Compile Include="{p}" />' for p in sources)
        (work / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            '<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
            '</PropertyGroup><ItemGroup>' + includes + '</ItemGroup></Project>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        subprocess.run([dotnet, 'build', 'Probe.csproj', '-c', 'Release', '--nologo', '-v', 'quiet'],
                       cwd=work, check=True, timeout=120)
        result = subprocess.run([dotnet, 'bin/Release/net10.0/Probe.dll'], cwd=work, text=True,
                                capture_output=True, timeout=90)
        if result.returncode:
            print(result.stdout, result.stderr)
        result.check_returncode()
        reports[variant] = json.loads(result.stdout.strip().splitlines()[-1])
        print(json.dumps({variant: reports[variant]}, sort_keys=True), flush=True)
for key in reports['control']:
    if key != 'allocations':
        assert reports['control'][key] == reports['candidate'][key], key
for old, new in zip(reports['control']['allocations'], reports['candidate']['allocations'], strict=True):
    assert (old['mode'], old['count']) == (new['mode'], new['count'])
    if old['mode'] in ('miss', 'remove', 'dependency'):
        assert old['allocatedBytes'] > 0 and new['allocatedBytes'] == 0, (old, new)
        assert new['retainedRanges'] == 0, new
    else:
        assert old == new, (old, new)
inputs = ['build-utils/melonx/adapt_converted_cache.py', 'test/melonx_converted_cache_test.py',
          'test/melonx_converted_cache/Program.cs', 'test/melonx_converted_cache/Boundaries.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               completeProductionCacheAndKeysAndDependency=True,
               gpuPayloadAndInvalidationBoundaryDoubled=True,
               arbitraryDictionaryEnumerationOrderNotPreserved=True,
               upstreamRevision=pin['revision'], upstreamInputs=PREIMAGES, callerInputs=CALLERS,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               postimages=postimages, compiledSources=compiled)
out = ROOT / 'dist/melonx/converted-cache-checks.json'; out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production converted-buffer cache checks passed.')
