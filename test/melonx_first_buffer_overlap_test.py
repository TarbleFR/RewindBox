#!/usr/bin/env python3
"""Execute first-buffer lookup against complete production interval/range classes.

The complete BufferCache.GetBuffer method and its stack predicate are inserted
verbatim. Physical buffers, sparse capabilities and GPU modifications are
boundaries. Their call order/arguments execute through the real caller. Native
GPU resource classes are not substituted as evidence of device performance.
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
from adapt_first_buffer_overlap import apply, BASELINE

COMPLETE = {
    'src/Ryujinx.Common/Collections/IntervalTree.cs': BASELINE['src/Ryujinx.Common/Collections/IntervalTree.cs'],
    'src/Ryujinx.Common/Collections/IntrusiveRedBlackTreeImpl.cs': 'f6aafa37bef615541e3395ba7ca3875351a32bb7c311b3bef2da602a316fd8d0',
    'src/Ryujinx.Common/Collections/IntrusiveRedBlackTreeNode.cs': '6ec5648053ca09030f982b62cfbcfe6640a3feac95a4db12b6b36e7e62a6f257',
    'src/Ryujinx.Memory/Range/MultiRangeList.cs': BASELINE['src/Ryujinx.Memory/Range/MultiRangeList.cs'],
    'src/Ryujinx.Memory/Range/MultiRange.cs': 'c945e4d62500263742db07c2c8afbd0c783b1fcfe811179a232ec30ac09e826b',
    'src/Ryujinx.Memory/Range/MemoryRange.cs': 'f49868746fc1fedea3dbbb18a3e5da10edf7c223a9184191ecd2b7f6fea66da0',
    'src/Ryujinx.Memory/Range/IMultiRangeItem.cs': 'f684c2a2d75c85f2e98cb786fdb9edf09420716068ea29e3785ffb8aec6d0e9c',
}
UPSTREAM = {**COMPLETE, **BASELINE}
for relative, expected in UPSTREAM.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())


def member(text, signature):
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


reports, postimages, compiled = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-first-buffer-overlap-') as temporary:
    base = Path(temporary)
    # Drift checks must fail before publishing any partially adapted class.
    negative = base / 'negative'
    for relative in UPSTREAM:
        target = negative / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)
    negative_cases = 0
    for relative in BASELINE:
        path = negative / relative; original = path.read_bytes(); path.write_bytes(original + b'\n// unreviewed drift\n')
        before = {p: (negative / p).read_bytes() for p in UPSTREAM}
        try:
            apply(negative)
        except AssertionError:
            negative_cases += 1
        else:
            raise AssertionError('source drift accepted: ' + relative)
        assert before == {p: (negative / p).read_bytes() for p in UPSTREAM}
        path.write_bytes(original)
    for variant in ('control', 'candidate'):
        work = base / variant
        for relative in UPSTREAM:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        cache = (work / 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs').read_text()
        body = member(cache, '        private MultiRangeBuffer GetBuffer(MultiRange range, BufferStage stage, bool write = false)')
        predicate = member(cache, '        private struct BufferContainsRange : IIntervalTreePredicate<MultiRangeBuffer>') if variant == 'candidate' else ''
        boundaries = (ROOT / 'test/melonx_first_buffer_overlap/Boundaries.cs').read_text()
        boundaries = boundaries.replace('        /* PRODUCTION_GET_BUFFER */', body)
        boundaries = boundaries.replace('        /* PRODUCTION_BUFFER_PREDICATE */', predicate)
        (work / 'Boundaries.cs').write_text(boundaries)
        shutil.copyfile(ROOT / 'test/melonx_first_buffer_overlap/Program.cs', work / 'Program.cs')
        sources = [*COMPLETE, 'Program.cs', 'Boundaries.cs']
        includes = ''.join(f'<Compile Include="{p}" />' for p in sources)
        (work / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            '<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>'
            '<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>'
            '<EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
            f'<DefineConstants>{"CANDIDATE" if variant == "candidate" else ""}</DefineConstants>'
            '</PropertyGroup><ItemGroup>' + includes + '</ItemGroup></Project>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release'],
            cwd=work, env=environment, text=True, capture_output=True, timeout=240)
        if result.returncode:
            print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        compiled[variant] = {p: hashlib.sha256((work / p).read_bytes()).hexdigest() for p in sources}
        print(variant, json.dumps(reports[variant]), flush=True)

assert reports['control']['functionalDigest'] == reports['candidate']['functionalDigest']
assert reports['control']['cases'] == reports['candidate']['cases']
for before, after in zip(reports['control']['benchmark'], reports['candidate']['benchmark'], strict=True):
    assert (before['kind'], before['count'], before['iterations'], before['result']) == \
           (after['kind'], after['count'], after['iterations'], after['result'])
    fallback = after['kind'] in ('late', 'alias') and after['count'] > 8
    assert after['bytes'] == before['bytes'] if fallback else after['bytes'] == 0, (before, after)
inputs = ['build-utils/melonx/adapt_first_buffer_overlap.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/source.json', 'test/melonx_first_buffer_overlap_test.py',
          'test/melonx_first_buffer_overlap/Program.cs', 'test/melonx_first_buffer_overlap/Boundaries.cs']
receipt = dict(result='passed', upstreamRevision=pin['revision'], dotnet=pin['dotnet'],
    physicalDeviceTested=False, completeIntervalAndRangeClasses=True,
    exactProductionBufferCacheMethod=True, resourceAndSparseBoundariesDoubled=True,
    mutableMappingAndNestedLookupCovered=True, independentIntervalOracle=True,
    maximumPureContainsChecksBeforeFallback=8, consumerIdentityDriftControls=negative_cases,
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    baselineInputs=UPSTREAM, postimages=postimages, reports=reports, compiledSourceInputs=compiled)
output = ROOT / 'dist/melonx/first-buffer-overlap-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('First-buffer lookup: identity, order, synchronization, fallback and allocations passed.', flush=True)
