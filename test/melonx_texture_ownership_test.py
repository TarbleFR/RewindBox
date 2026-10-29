#!/usr/bin/env python3
"""Exercise real texture ownership methods and the complete short-cache class.

Usage: melonx_texture_ownership_test.py <pinned MeloNX source snapshot>

The eight explicit upstream SHA-256 checks accept an unchanged source snapshot
as well as a Git checkout. Both variants retain the delivered GPU lifetime
adaptation. Production Texture reference/view methods, TexturePool.Delete,
Pool.Dispose and the full AutoDeleteCache are compiled without rewriting their
bodies. GPU storage, memory tracking and texture-group endpoints are doubles.
No Vulkan/Metal device, guest game, physical memory saving or FPS is simulated.
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
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_gpu_lifetime import apply as lifetime_apply
from adapt_texture_ownership import apply as ownership_apply

UPSTREAM = {
    'src/Ryujinx.Graphics.Gpu/Image/Texture.cs': '2b0efc551b02535fe96a123dca328208313896db558c68cd9af01c7ae31c8f07',
    'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs': 'c1b8e1809347fae5058232a8249b6e650814e0aab22b9ba319f2b383a965091d',
    'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs': 'f353fbc15730730fd442ff49f82f8498ccfa1505d95c33918208b849bf2d5d50',
    'src/Ryujinx.Graphics.Gpu/Image/Pool.cs': 'b07c6db82a95d1485ad21bb6a804f94b803efd0f6600a67d613491ec08d326f0',
    'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs': '76e452b1f09ec95e6280c2d8518f1c1b318555f9e1c124008082ac4420ea01d9',
    'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs': 'ebbf67f1568d2422f1d19ec09bca6f2a17acb3a018ad92770e3dfbf7e3d6ebf5',
    'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs': '926fed78436a4ce587203174d0217933593be627c68055c8cddfc5be32c6cd6f',
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': 'e64798cc48550b7f8408d1fa8c432575618f11337a93b37defea8cec99e72e7b',
}
for path, digest in UPSTREAM.items():
    assert hashlib.sha256((SOURCE / path).read_bytes()).hexdigest() == digest, path


def member(text, signature):
    """Take one complete production member, preserving its exact body."""
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    for index in range(brace + 1, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
dotnet = os.environ.get('DOTNET', 'dotnet')
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-texture-ownership-') as temporary:
    # macOS /var is an alias of /private/var; keep one path identity for MSBuild.
    base = Path(temporary).resolve()
    for mode in ('control', 'fixed'):
        work = base / mode
        source = work / 'source'
        for path in UPSTREAM:
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        lifetime_apply(source)
        if mode == 'fixed':
            ownership_apply(source)

        texture = (source / 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs').read_text()
        pool = (source / 'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs').read_text()
        pool_base = (source / 'src/Ryujinx.Graphics.Gpu/Image/Pool.cs').read_text()
        texture_members = '\n'.join(member(texture, signature) for signature in (
            'private struct TexturePoolOwner',
            'public void IncrementReferenceCount()',
            'public void IncrementReferenceCount(TexturePool pool, int id, ulong gpuVa)',
            'public bool HasOneReference()',
            'public bool DecrementReferenceCount()',
            'public bool DecrementReferenceCount(TexturePool pool, int id = -1)',
            'private void AddView(Texture texture)',
            'private void RemoveView(Texture texture)',
            'private void DeleteIfNotUsed()',
        ))
        # Compile the actual per-slot teardown call chain, not a modeled loop.
        delete = member(pool, 'protected override void Delete(Texture item)')
        dispose = member(pool_base, 'public virtual void Dispose()')
        assert 'item.DecrementReferenceCount(this);' in delete
        assert 'for (int index = 0; index < Items.Length; index++)' in dispose
        assert 'Delete(Items[index]);' in dispose
        (work / 'ProductionBodies.cs').write_text('''using System;
using System.Collections.Generic;
using System.Diagnostics;
namespace Ryujinx.Graphics.Gpu.Image {
partial class Texture {
''' + texture_members + '''
}
partial class TexturePool {
''' + delete + '''
}
abstract partial class Pool<T1, T2> {
''' + dispose + '''
}
}
''')
        shutil.copyfile(source / 'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs', work / 'AutoDeleteCache.cs')
        shutil.copyfile(ROOT / 'test/melonx_texture_ownership/Program.cs', work / 'Program.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414</NoWarn>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        # This probe has no package dependency; do not query external feeds.
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        build = subprocess.run([dotnet, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                               cwd=work, capture_output=True, text=True, timeout=120)
        if build.returncode:
            print(build.stdout, build.stderr, flush=True)
            build.check_returncode()
        run = subprocess.run([dotnet, 'bin/Release/net10.0/Probe.dll', mode], cwd=work,
                             capture_output=True, text=True, timeout=60)
        if run.returncode:
            print(run.stdout, run.stderr, flush=True)
            run.check_returncode()
        reports.append(json.loads(run.stdout.strip().splitlines()[-1]))

control, fixed = reports
assert control['samePoolLeakedReferences'] == 1 and fixed['samePoolLeakedReferences'] == 0
assert control['crossPoolLeakedReferences'] == 1 and fixed['crossPoolLeakedReferences'] == 0
assert control['obsoleteCacheEntriesAfterTwoTicks'] == 1 and fixed['obsoleteCacheEntriesAfterTwoTicks'] == 0
assert control['duplicateShortReferences'] == 2 and fixed['duplicateShortReferences'] == 1
inputs = ['build-utils/melonx/adapt_texture_ownership.py', 'build-utils/melonx/adapt_gpu_lifetime.py',
          'build-utils/melonx/adapt_session.py', 'build-utils/melonx/source.json',
          'test/melonx_texture_ownership_test.py', 'test/melonx_texture_ownership/Program.cs']
receipt = dict(result='passed', reports=reports, upstreamRevision=pin['revision'],
               physicalDeviceTested=False, gpuStorageDoubled=True,
               inputs={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in inputs},
               upstreamInputs=UPSTREAM)
output = ROOT / 'dist/melonx/texture-ownership-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
