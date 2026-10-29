#!/usr/bin/env python3
"""Exercise production native-memory allocation ownership and block bookkeeping.

Compile the full allocator, block ranges and allocation handles. The Vulkan
native driver is doubled with strict allocation/map/free tracking. Separate
instrumented ownership/count probes from uninstrumented timing; fault injection
before managed block construction/publication is explicit in the receipt.
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
from adapt_allocator_blocks import apply

PREIMAGES = {'src/Ryujinx.Graphics.Vulkan/MemoryAllocatorBlockList.cs': 'e59268ccf087f483e28557de1c5c9faa2e90c24d2f73d4f49479cb8084ff0b3c', 'src/Ryujinx.Graphics.Vulkan/MemoryAllocation.cs': '8e871eedcbc45750022c45a497fc4c1a482ea908f1c04e3ae7cd5a8ab8e022b2', 'src/Ryujinx.Graphics.Vulkan/VulkanException.cs': '979b68380d45dfe405df08d78a1bb6376493855585fdecea1b6b603050adb15c', 'src/Ryujinx.Common/Utilities/BitUtils.cs': '3f33297b391f95cfba6d3ec848b69f94534848b74f919310181e0a51eb450261'}
CALLERS = {'src/Ryujinx.Graphics.Vulkan/MemoryAllocator.cs': '15833c21c16b3698de4f872d547f0d2b050cde28843695d972c366777512f9b3', 'src/Ryujinx.Graphics.Vulkan/DonatedBufferAllocator.cs': '0c84a345748de604d66c9d94adc4a4dcc7709832cddc416a7c755855406003ee'}

for relative, expected in {**PREIMAGES, **CALLERS}.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
dotnet = os.environ.get('DOTNET', 'dotnet')
reports, postimages, compiled = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-allocator-blocks-') as temporary:
    base = Path(temporary)
    for variant in ('control', 'candidate'):
        reports[variant], compiled[variant] = {}, {}
        for mode in ('instrumented', 'timing'):
            work = base / variant / mode
            for relative in PREIMAGES:
                target = work / relative; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / relative, target)
            if variant == 'candidate':
                changed = apply(work)
                hashes = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest() for path in changed}
                if postimages: assert postimages == hashes
                postimages = hashes
            if mode == 'instrumented':
                path = work / 'src/Ryujinx.Graphics.Vulkan/MemoryAllocatorBlockList.cs'
                text = path.read_text()
                assert text.count('Block newBlock = new(deviceMemory, hostPointer, blockSize, dedicated);') == 1
                assert text.count('InsertBlock(newBlock);') == 1
                text = text.replace('Block newBlock = new(deviceMemory, hostPointer, blockSize, dedicated);',
                                    'AllocationProbe.BeforeBlock();\n                Block newBlock = new(deviceMemory, hostPointer, blockSize, dedicated);')
                text = text.replace('InsertBlock(newBlock);', 'AllocationProbe.BeforePublication();\n                    InsertBlock(newBlock);')
                text = text.replace('Block block = _blocks[i];', 'Block block = AllocationProbe.Visit(_blocks[i]);')
                text = text.replace('if (_blocks[i] == block)', 'if (AllocationProbe.Visit(_blocks[i]) == block)')
                text = text.replace('_dedicatedBlocks[index] == block', 'AllocationProbe.Visit(_dedicatedBlocks[index]) == block')
                text = text.replace('Block replacement = _dedicatedBlocks[last];', 'Block replacement = AllocationProbe.Visit(_dedicatedBlocks[last]);')
                text = text.replace('return Size.CompareTo(other.Size);', 'AllocationProbe.Comparisons++; return Size.CompareTo(other.Size);')
                path.write_text(text)
            for name in ('Program.cs', 'Boundaries.cs'):
                shutil.copyfile(ROOT / 'test/melonx_allocator_blocks' / name, work / name)
            sources = list(PREIMAGES) + ['Program.cs', 'Boundaries.cs']
            compiled[variant][mode] = {p: hashlib.sha256((work / p).read_bytes()).hexdigest() for p in sources}
            includes = ''.join(f'<Compile Include="{p}" />' for p in sources)
            (work / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                '<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
                '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
                '<EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
                '</PropertyGroup><ItemGroup>' + includes + '</ItemGroup></Project>')
            (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
            (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
            subprocess.run([dotnet, 'build', 'Probe.csproj', '-c', 'Release', '--nologo', '-v', 'quiet'],
                           cwd=work, check=True, timeout=120)
            result = subprocess.run([dotnet, 'bin/Release/net10.0/Probe.dll', mode], cwd=work, text=True,
                                    capture_output=True, timeout=180)
            if result.returncode:
                print(result.stdout, result.stderr)
            result.check_returncode()
            reports[variant][mode] = json.loads(result.stdout.strip().splitlines()[-1])
            print(json.dumps({variant + '/' + mode: reports[variant][mode]}, sort_keys=True), flush=True)
for mode in ('instrumented', 'timing'):
    old, new = [reports[v][mode] for v in ('control', 'candidate')]
    for field in ('imported', 'concurrent'):
        assert old[field] == new[field], (mode, field)
    for a, b in zip(old['random'], new['random'], strict=True):
        for field in ('poolSize', 'allocated', 'released', 'payloadBytesChecked', 'requestTraceSha256'):
            assert a[field] == b[field], (mode, field)
        assert b['Allocations'] == b['Frees'] and b['Maps'] == b['Unmaps'], b
        if a['poolSize'] == 16:
            assert a == b, 'Dedicated-only production regime must preserve exact allocation trace and footprint'
    for a, b in zip(old['failures'], new['failures'], strict=True):
        assert (a['mode'], a['attempts'], a['caught'], a['Allocations'], a['Maps']) == (b['mode'], b['attempts'], b['caught'], b['Allocations'], b['Maps'])
        assert b['nativeLeaks'] == 0 and b['mappedLeaks'] == 0, b
        assert b['Allocations'] == b['Frees'] and b['Maps'] == b['Unmaps'], b
        if a['mode'] != 'allocate-result': assert a['nativeLeaks'] == a['attempts'], a
    for a, b in zip(old['searches'], new['searches'], strict=True):
        assert (a['mode'], a['dedicatedCount'], a['queries'], a['allocatedBytes']) == (b['mode'], b['dedicatedCount'], b['queries'], b['allocatedBytes'])
# Count probes establish the recurring-work reduction without relying on noisy timers.
old, new = [reports[v]['instrumented'] for v in ('control', 'candidate')]
for a, b in zip(old['churn'], new['churn'], strict=True):
    assert (a['liveBlocks'], a['operations']) == (b['liveBlocks'], b['operations'])
    assert b['operations'] <= b['blockVisits'] <= 2 * b['operations'] and b['comparisons'] == 0, b
    if a['liveBlocks'] == 2048:
        assert a['blockVisits'] > b['blockVisits'] * 100 and a['comparisons'] > 0, (a, b)
for a, b in zip(old['searches'], new['searches'], strict=True):
    assert b['blockVisits'] == b['queries'], b
    if a['mode'] in ('small-dedicated', 'equal-dedicated'):
        assert a['blockVisits'] > b['blockVisits'] * 100, (a, b)

inputs = ['build-utils/melonx/adapt_allocator_blocks.py', 'test/melonx_allocator_blocks_test.py',
          'test/melonx_allocator_blocks/Program.cs', 'test/melonx_allocator_blocks/Boundaries.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               completeProductionAllocatorAndHandlesAndRanges=True,
               nativeDriverDoubled=True,
               managedBlockAndPublicationFailuresInjected=True,
               timingGate=False,
               equivalentPooledBlockSelectionMayDiffer=True,
               dedicatedOnlyTraceAndNativeBytesIdentical=True,
               upstreamRevision=pin['revision'], upstreamInputs=PREIMAGES, callerInputs=CALLERS,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               postimages=postimages, compiledSources=compiled)
out = ROOT / 'dist/melonx/allocator-blocks-checks.json'; out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production allocator block checks passed.')
