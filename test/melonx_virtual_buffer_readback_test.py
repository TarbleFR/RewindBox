#!/usr/bin/env python3
"""Compile complete physical/virtual buffer and range production classes.

Memory protection and renderer calls are doubles. The host buffer operations
really copy bytes, and the production flush/range/lock paths run unchanged.
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
from adapt_virtual_buffer_readback import apply, CONSUMERS, RELATIVE

PATHS = ['src/Ryujinx.Graphics.Gpu/Memory/' + name + '.cs' for name in
         ('Buffer', 'MultiRangeBuffer', 'BufferModifiedRangeList', 'BufferMigration')]
PATHS += ['src/Ryujinx.Memory/Range/' + name + '.cs' for name in
          ('IRange', 'INonOverlappingRange', 'RangeListBase', 'NonOverlappingRangeList',
           'MemoryRange', 'MultiRange', 'IMultiRangeItem')]
PATHS += ['src/Ryujinx.Graphics.GAL/' + name + '.cs' for name in ('BufferHandle', 'BufferRange', 'PinnedSpan', 'BufferAccess')]
PATHS += ['src/Ryujinx.Graphics.Gpu/Synchronization/ISyncActionHandler.cs']
reports, postimages = {}, {}
consumer_drift_controls = 0
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-virtual-readback-') as temporary:
    negative = Path(temporary).resolve() / 'consumer-drift'
    for path in [RELATIVE, *CONSUMERS]:
        target = negative / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / path, target)
    for path in CONSUMERS:
        target = negative / path
        original = target.read_bytes()
        target.write_bytes(original + b'\n// synchronous contract changed\n')
        try:
            apply(negative)
        except AssertionError:
            consumer_drift_controls += 1
        else:
            raise AssertionError('consumer drift accepted: ' + path)
        assert (negative / RELATIVE).read_bytes() == (SOURCE / RELATIVE).read_bytes()
        target.write_bytes(original)
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        for path in PATHS:
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {p.relative_to(work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(ROOT / 'test/melonx_virtual_buffer_readback' / name, work / name)
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>
</PropertyGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release', '--', variant],
                                cwd=work, env=environment, capture_output=True, text=True, timeout=180)
        if result.returncode:
            print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
assert reports['candidate']['overcopyCorrected']
assert not reports['control']['overcopyCorrected']
assert reports['candidate']['semanticDigest'] == reports['control']['semanticDigest']
for old, new in zip(reports['control']['allocations'], reports['candidate']['allocations'], strict=True):
    assert (old['length'], old['dependencies'], old['dirty'], old['gpuSync']) == (new['length'], new['dependencies'], new['dirty'], new['gpuSync'])
    if old['dependencies'] and not old['dirty'] and not old['gpuSync']:
        assert old['bytes'] - new['bytes'] >= old['length'] * old['flushes'], (old, new)
inputs = ['build-utils/melonx/adapt_virtual_buffer_readback.py', 'test/melonx_virtual_buffer_readback_test.py',
          'test/melonx_virtual_buffer_readback/Program.cs', 'test/melonx_virtual_buffer_readback/Boundaries.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               consumerDriftControls=consumer_drift_controls,
               rendererAndTrackingDoubled=True, completeProductionClasses=True,
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in PATHS},
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs}, postimages=postimages)
out = ROOT / 'dist/melonx/virtual-buffer-readback-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
