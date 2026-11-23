#!/usr/bin/env python3
"""Compare the delivered streaming code and the final preparation on a .NET 10 host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import adapt_streaming_memory as adapter
from melonx_adapter_control import control_source, files_edited_later, later_sharing, postimage


def method(source, signature):
    start = source.index(signature)
    body = source.index('{', start)
    depth = 0
    for index in range(body, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[start:index + 1]
    raise ValueError(signature)


def setup(tree, directory, candidate):
    directory.mkdir()
    for name in (adapter.ARRAY_API, adapter.SNAPSHOTS, adapter.POOL):
        shutil.copyfile(tree / name, directory / Path(name).name)
    shutil.copyfile(ROOT / 'test/melonx_streaming_memory/Probe.cs', directory / 'Probe.cs')
    source = (tree / adapter.BINDINGS).read_text('utf-8-sig')
    start = source.index('private const int ItemPageSize' if candidate else 'public Texture[] DeltaItems;')
    fields = source[start:source.index('public int DeltaLength;', start)]
    entry = fields + '\n' + method(source, 'public long DeltaBytes()') + '\n' + method(source, 'public void PrepareDelta(')
    binding = '\n'.join(method(source, signature) for signature in (
        'private static T[] RentBindingScratch<T>(', 'private static void ReturnBindingScratch<T>(',
        'private void FlushDeltaRun('))
    gc = (tree / adapter.MEMORY).read_text('utf-8-sig')
    gap = ''
    if candidate:
        gap = gc[gc.index('private const ulong CriticalProcessHeadroom'):gc.index('internal static int StallCompactions')]
        assert gc.count('!MayCompactInGap(Ryujinx.Memory.HostMemoryBudget.AvailableBytes)') == 2
    unit = 'using System;\nusing System.Collections.Generic;\nusing System.Threading;\nusing Ryujinx.Graphics.GAL;\n'
    (directory / 'Methods.cs').write_text(unit + 'partial class CacheEntry {\n' + entry + '\n}\npartial class Bindings {\n' +
                                          binding + '\n}\nclass Gap {\n' + gap + '\n}', encoding='utf-8')
    (directory / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
        '<TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
        '<DefineConstants>' + ('CANDIDATE' if candidate else '') + '</DefineConstants></PropertyGroup></Project>')
    (directory / 'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--candidate-source', required=True, type=Path)
    args = parser.parse_args()
    final = args.candidate_source.resolve()
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    control = args.source.resolve()
    temporary_trees = []
    if not all((control / name).is_file() and digest(control / name) == sha
               for name, sha in adapter.BASELINE.items()):
        control, reversed_final = control_source(final, 'adapt_streaming_memory', temporary_trees)
        assert reversed_final
    with tempfile.TemporaryDirectory() as temp:
        forward = Path(temp) / 'forward'
        for name in adapter.BASELINE:
            (forward / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(control / name, forward / name)
        adapter.apply(forward)
        # Later adapters edit some of these files (files_edited_later): the adapter's own postimage is the final
        # preparation with exactly those later adapters reversed, latest first (postimage). Control plus this adapter
        # must be that postimage for every file, and the final preparation's bytes where no later adapter edits it.
        own = Path(temp) / 'postimage'
        later = postimage('adapt_streaming_memory', final, own)
        edited_later = files_edited_later('adapt_streaming_memory')
        assert later == later_sharing('adapt_streaming_memory') and edited_later <= set(adapter.BASELINE)
        for name in adapter.BASELINE:
            # Path.write_text uses host line endings on Windows. Compare the actual source text.
            assert (forward / name).read_text('utf-8') == (own / name).read_text('utf-8'), name
            if name not in edited_later:
                assert (forward / name).read_text('utf-8') == (final / name).read_text('utf-8'), name
    results = {}
    keys = ['commonBytes', 'threeAliasPagesBytes', 'uploadAllocatedBytes', 'directAllocatedBytes', 'threadedAllocatedBytes']
    with tempfile.TemporaryDirectory() as temp:
        for variant, tree in [('control', control), ('candidate', final)]:
            directory = Path(temp) / variant
            setup(tree, directory, variant == 'candidate')
            dotnet = os.environ.get('DOTNET', 'dotnet')
            run = subprocess.run([dotnet, 'run', '-c', 'Release', '--project', 'Probe.csproj', '-p:NuGetAudit=false'],
                                 cwd=directory, check=True, text=True, stdout=subprocess.PIPE)
            results[variant] = dict(zip(keys, map(int, run.stdout.strip().splitlines()[-1].split(',')), strict=True))
    old, new = results['control'], results['candidate']
    assert old['commonBytes'] - new['commonBytes'] == 524288 * 8
    assert new['threeAliasPagesBytes'] < old['threeAliasPagesBytes']
    assert old['uploadAllocatedBytes'] - new['uploadAllocatedBytes'] >= 262144
    assert new['threadedAllocatedBytes'] < old['threadedAllocatedBytes']
    report = dict(result='passed', sourceKind='finalPreparationWithReversedControl', finalPreparationBound=True,
                  physicalDeviceTested=False, streamingMemory={'executed': True, **results},
                  inputs={path: digest(ROOT / path) for path in (
                      'test/melonx_streaming_memory_test.py', 'test/melonx_streaming_memory/Probe.cs',
                      'test/melonx_adapter_control.py', 'build-utils/melonx/adapt_streaming_memory.py',
                      'build-utils/melonx/adapt_session.py')},
                  postimages={name: digest(final / name) for name in adapter.BASELINE})
    out = ROOT / 'dist/melonx/streaming-memory-checks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
