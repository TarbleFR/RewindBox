#!/usr/bin/env python3
"""Exercise the actual indirect caller through boxed cache keys and dirty propagation.

The complete GetBufferTopologyConversionIndirect production method constructs,
sets and boxes the key. Full CacheByRange dispatches real dependency/key cleanup.
DirtyIndexBuffer and BoundEquals are exact production methods. Native allocation,
shader conversion and binding are explicitly doubled boundaries; no rendering
performance claim is made by this cache-coherence test.
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
from adapt_indirect_cache_key import apply
from adapt_converted_cache import apply as prepare_baseline

PREIMAGES = {'src/Ryujinx.Graphics.Vulkan/CacheByRange.cs': '4791ea9c7560be75dcb1be2cc08cf486bbde243b6bee920d721342b172baeca1', 'src/Ryujinx.Graphics.GAL/BufferRange.cs': 'b16dcaed8fd814ade5e46cf2ff3c8a7fe149996a65a49cddb3e8566af4a0c669', 'src/Ryujinx.Graphics.GAL/BufferHandle.cs': '71da4d0600c311fc3c7fb6e313eedf9ee012ada58ad2e300138d518b98b6f17f'}
CALLERS = {'src/Ryujinx.Graphics.Vulkan/BufferManager.cs': '73bb8f6d328039d495a4944be52dfb6b1b1dfcb661198e05a74fcd3084b05d36', 'src/Ryujinx.Graphics.Vulkan/BufferHolder.cs': '08aecc7d52238889a2a7ec242844b2242ff766301a3f15b13b9712b6589e6b40', 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': '2382603b280d31a3cb96be0340930a61a72af8a4b12e7fe8e8ecd3a6f39943d2', 'src/Ryujinx.Graphics.Vulkan/IndexBufferState.cs': '804a97614c0ac1645b25eb03eb6afb2e3755a0a016c1c7839192b797b0fdbfef'}

for relative, expected in {**PREIMAGES, **CALLERS}.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
dotnet = os.environ.get('DOTNET', 'dotnet')
def method(relative, signature):
    text = (SOURCE / relative).read_text()
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    index = text.index('{', start)
    depth, end = 1, index + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]
extracted = {
    'PRODUCTION_INDIRECT_CONVERSION': method('src/Ryujinx.Graphics.Vulkan/BufferManager.cs',
        '        public (Auto<DisposableBuffer>, Auto<DisposableBuffer>) GetBufferTopologyConversionIndirect('),
    'PRODUCTION_DIRTY_INDEX': method('src/Ryujinx.Graphics.Vulkan/PipelineBase.cs',
        '        public void DirtyIndexBuffer(Auto<DisposableBuffer> buffer)'),
    'PRODUCTION_BOUND_EQUALS': method('src/Ryujinx.Graphics.Vulkan/IndexBufferState.cs',
        '        public readonly bool BoundEquals(Auto<DisposableBuffer> buffer)'),
}
wrappers = [
    '        public bool TryGetCachedConvertedBuffer(int offset, int size, ICacheKey key, out BufferHolder holder)',
    '        public void AddCachedConvertedBuffer(int offset, int size, ICacheKey key, BufferHolder holder)',
    '        public void AddCachedConvertedBufferDependency(int offset, int size, ICacheKey key, Dependency dependency)',
    '        public void RemoveCachedConvertedBuffer(int offset, int size, ICacheKey key)',
]
wrapper_methods = {signature: method('src/Ryujinx.Graphics.Vulkan/BufferHolder.cs', signature) for signature in wrappers}
extracted['PRODUCTION_CACHE_WRAPPERS'] = '\n\n'.join(wrapper_methods.values())
reports, postimages, compiled = {}, {}, {}
control_hash = None
with tempfile.TemporaryDirectory(prefix='melonx-indirect-cache-key-') as temporary:
    base = Path(temporary)
    for variant in ('control', 'candidate'):
        work = base / variant
        for relative in PREIMAGES:
            target = work / relative; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        prepare_baseline(work)
        baseline_hash = hashlib.sha256((work / 'src/Ryujinx.Graphics.Vulkan/CacheByRange.cs').read_bytes()).hexdigest()
        if control_hash is not None: assert baseline_hash == control_hash
        control_hash = baseline_hash
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest() for path in changed}
        for name in ('Program.cs', 'Boundaries.cs'):
            text = (ROOT / 'test/melonx_indirect_cache_key' / name).read_text()
            if name == 'Boundaries.cs':
                for marker, source_method in extracted.items():
                    placeholder = '        /* ' + marker + ' */'
                    assert text.count(placeholder) == 1, marker
                    text = text.replace(placeholder, source_method)
            (work / name).write_text(text)
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
        result = subprocess.run([dotnet, 'bin/Release/net10.0/Probe.dll'], cwd=work, text=True, capture_output=True, timeout=90)
        if result.returncode: print(result.stdout, result.stderr)
        result.check_returncode()
        reports[variant] = json.loads(result.stdout.strip().splitlines()[-1])
        print(json.dumps({variant: reports[variant]}, sort_keys=True), flush=True)
old, new = reports['control'], reports['candidate']
for field in old:
    if field != 'missedBoundIndexInvalidations': assert old[field] == new[field], field
assert old['missedBoundIndexInvalidations'] == old['lifecycleCases']
assert new['missedBoundIndexInvalidations'] == 0
inputs = ['build-utils/melonx/adapt_converted_cache.py', 'build-utils/melonx/adapt_indirect_cache_key.py',
          'test/melonx_indirect_cache_key_test.py', 'test/melonx_indirect_cache_key/Program.cs',
          'test/melonx_indirect_cache_key/Boundaries.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               completeProductionIndirectCaller=True, completeProductionCacheAndKeys=True,
               productionInvalidationAndEqualityMethods=True, graphicsBoundariesDoubled=True,
               upstreamRevision=pin['revision'], upstreamInputs=PREIMAGES, callerInputs=CALLERS,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               controlCacheSha256=control_hash, postimages=postimages, compiledSources=compiled,
               extractedMethodSha256={p: hashlib.sha256(v.encode()).hexdigest() for p, v in extracted.items()},
               wrapperMethodSha256={p: hashlib.sha256(v.encode()).hexdigest() for p, v in wrapper_methods.items()})
out = ROOT / 'dist/melonx/indirect-cache-key-checks.json'; out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production indirect conversion key invalidation checks passed.')
