#!/usr/bin/env python3
"""Exercise complete production Auto ownership and measure isolated resource allocations.

Native command transport/completion is doubled. CommandBufferScoped, ownership
bitmaps and Auto are production; AddDependant is inserted verbatim from the
pinned pool. Parallel tests exercise supported atomic reference counts, not
unsupported simultaneous writes to command-buffer ownership state.
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
from adapt_auto_ownership import apply

PREIMAGES = {'src/Ryujinx.Graphics.Vulkan/Auto.cs': '79ea043a3d71a72d08ef43eeef5452d2eb01192b38bc483469fda578811b8eb0', 'src/Ryujinx.Graphics.Vulkan/BitMap.cs': '21c19bf38cee4ccdf01480b59b09e63b9d81d32a848fac18f35dbac4aac71230', 'src/Ryujinx.Graphics.Vulkan/BitMapStruct.cs': '7abb5cef85fc75a8e196f94c2c2e3234a2ff66f2fe8d32afc16e24489dd14ee8', 'src/Ryujinx.Graphics.Vulkan/CommandBufferScoped.cs': 'bee489db43c52a323a4da960bf2612acc5c5b83ecdc2d4b058715117c9e519f0', 'src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs': 'beb73c36e5ae5313781d224798375ff4870961b9777e608eb52205bdeb3f5cd5', 'src/Ryujinx.Common/Memory/IArray.cs': '0b4ba835fe89f680b0e4faff63e2f736727647a68a32f37d6ee0b193498c563b', 'src/Ryujinx.Common/Memory/StructArrayHelpers.cs': 'ee9871e0099b206b7306214402b7241cc61d22632e5709708122f581b2d7074a'}

for relative, expected in PREIMAGES.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
dotnet = os.environ.get('DOTNET', 'dotnet')
def method(text, signature):
    assert text.count(signature) == 1
    start = text.index(signature)
    index = text.index('{', start)
    depth = 1
    end = index + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]
add_dependant = method((SOURCE / 'src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs').read_text(),
                       '        public void AddDependant(int cbIndex, IAuto dependant)')
reports = {}
postimages = {}
compiled = {}
with tempfile.TemporaryDirectory(prefix='melonx-auto-ownership-') as temporary:
    base = Path(temporary)
    for variant in ('control', 'candidate'):
        work = base / variant
        for relative in PREIMAGES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest() for path in changed}
        for name in ('Program.cs', 'Boundaries.cs'):
            text = (ROOT / 'test/melonx_auto_ownership' / name).read_text()
            if name == 'Boundaries.cs':
                assert text.count('        /* PRODUCTION_ADD_DEPENDANT */') == 1
                text = text.replace('        /* PRODUCTION_ADD_DEPENDANT */', add_dependant)
            (work / name).write_text(text)
        sources = [p for p in PREIMAGES if not p.endswith('/CommandBufferPool.cs')] + ['Program.cs', 'Boundaries.cs']
        compiled[variant] = {p: hashlib.sha256((work / p).read_bytes()).hexdigest() for p in sources}
        includes = ''.join(f'<Compile Include="{p}" />' for p in sources)
        (work / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            '<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable>'
            '<EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
            '</PropertyGroup><ItemGroup>' + includes + '</ItemGroup></Project>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        subprocess.run([dotnet, 'build', 'Probe.csproj', '-c', 'Release', '--nologo', '-v', 'quiet'],
                       cwd=work, check=True, timeout=120)
        result = subprocess.run([dotnet, 'bin/Release/net10.0/Probe.dll'], cwd=work, check=True,
                                text=True, capture_output=True, timeout=120)
        reports[variant] = json.loads(result.stdout.strip().splitlines()[-1])
        print(json.dumps({variant: reports[variant]}, sort_keys=True), flush=True)
    # A capacity change must fail before modifying Auto.
    capacity = base / 'capacity'
    for relative in ('src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs', 'src/Ryujinx.Graphics.Vulkan/Auto.cs'):
        target = capacity / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((SOURCE / relative).read_bytes())
    pool = capacity / 'src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs'
    pool.write_text(pool.read_text().replace('MaxCommandBuffers = 16;', 'MaxCommandBuffers = 128;'))
    try:
        apply(capacity)
    except AssertionError:
        pass
    else:
        raise AssertionError('capacity drift accepted')
    assert (capacity / 'src/Ryujinx.Graphics.Vulkan/Auto.cs').read_bytes() == (SOURCE / 'src/Ryujinx.Graphics.Vulkan/Auto.cs').read_bytes()

for key in reports['control']:
    if key != 'ownerAllocations':
        assert reports['control'][key] == reports['candidate'][key], key
old, new = [reports[v]['ownerAllocations'] for v in ('control', 'candidate')]
assert old['count'] == new['count']
assert old['bytes'] - new['bytes'] == 32 * new['count'], (old, new)
inputs = ['build-utils/melonx/adapt_auto_ownership.py', 'test/melonx_auto_ownership_test.py',
          'test/melonx_auto_ownership/Program.cs', 'test/melonx_auto_ownership/Boundaries.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               completeProductionAuto=True, completeProductionBitmaps=True,
               commandTransportAndNativeCompletionDoubled=True,
               concurrentOwnershipMutationsTested=False, concurrentAtomicRefcountsTested=True,
               upstreamRevision=pin['revision'], upstreamInputs=PREIMAGES,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               postimages=postimages, compiledSources=compiled,
               extractedAddDependantSha256=hashlib.sha256(add_dependant.encode()).hexdigest(),
               capacityDriftRejectedBeforeMutation=True)
out = ROOT / 'dist/melonx/auto-ownership-checks.json'; out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production Auto ownership checks passed.')
