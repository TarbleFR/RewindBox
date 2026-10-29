#!/usr/bin/env python3
"""Retire copy links without retiring pending GPU sync owners.

Compile full production TextureGroupHandle/TextureDependency, the complete
ReplaceHandles/InheritHandles pair, and the real GpuContext sync-action walker.
Only native texture, CPU mapping and GPU endpoints are controlled boundaries.
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
from adapt_texture_handle_dependencies import apply

GROUP = 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'
HANDLE = 'src/Ryujinx.Graphics.Gpu/Image/TextureGroupHandle.cs'
CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
FILES = [GROUP, HANDLE, CONTEXT, 'src/Ryujinx.Graphics.Gpu/Image/TextureDependency.cs',
         'src/Ryujinx.Graphics.Gpu/Synchronization/ISyncActionHandler.cs',
         'src/Ryujinx.Graphics.Gpu/Synchronization/HostSyncFlags.cs']
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == PIN['revision']
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', *FILES], text=True).strip()


def member(text, marker):
    start = text.index('        ' + marker)
    end = text.index('\n        /// <summary>', start)
    return text[start:end]


reports, extraction, postimages = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-texture-handle-dependencies-') as directory:
    for variant in ('control', 'candidate'):
        work = Path(directory) / variant
        source = work / 'source'
        for p in FILES:
            target = source / p; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(SOURCE / p, target)
        if variant == 'candidate':
            changed = apply(source)
            postimages = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        g = (source / GROUP).read_text(); c = (source / CONTEXT).read_text()
        parts = {marker: member(g, marker) for marker in ('private void InheritHandles(', 'private void ReplaceHandles(')}
        group_code = 'using System;\nusing Ryujinx.Memory.Tracking;\nnamespace Ryujinx.Graphics.Gpu.Image { partial class TextureGroup {\n' + '\n'.join(parts.values()) + '\n} }\n'
        context_parts = {marker: member(c, marker) for marker in ('internal void RegisterSyncAction(', 'internal void CreateHostSyncIfNeeded(')}
        context_code = 'using System;\nusing Ryujinx.Graphics.Gpu.Synchronization;\nnamespace Ryujinx.Graphics.Gpu { partial class GpuContext {\n' + '\n'.join(context_parts.values()) + '\n} }\n'
        (work / 'Group.cs').write_text(group_code); (work / 'Context.cs').write_text(context_code)
        extraction[variant] = dict(completeGroupMethods={m: hashlib.sha256(b.encode()).hexdigest() for m, b in parts.items()},
            completeContextMethods={m: hashlib.sha256(b.encode()).hexdigest() for m, b in context_parts.items()},
            groupCompileSha256=hashlib.sha256(group_code.encode()).hexdigest(), contextCompileSha256=hashlib.sha256(context_code.encode()).hexdigest())
        for p in FILES:
            if p not in (GROUP, CONTEXT): shutil.copyfile(source / p, work / Path(p).name)
        shutil.copyfile(ROOT / 'test/melonx_texture_handle_dependencies/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>
<NoWarn>0169;0414;0649</NoWarn></PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'disable'}}))
        env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'test.csproj'), '-c', 'Release', '--', variant],
                                cwd=work, env=env, capture_output=True, text=True, timeout=180)
        print(result.stdout, flush=True)
        if result.returncode: print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
control, candidate = reports['control'], reports['candidate']
assert control['functionalDigest'] == candidate['functionalDigest']
assert control['selfDependencyEdges'] == 2 and candidate['selfDependencyEdges'] == 0
assert not control['selfGpuModifiedPreserved'] and candidate['selfGpuModifiedPreserved']
assert control['scenarios'] == candidate['scenarios']
assert control['retiredRetained'] > 0 and candidate['retiredRetained'] == 0
assert control['currentDependenciesAfterRemaps'] > candidate['currentDependenciesAfterRemaps'] == 1
assert control['peerDependenciesAfterRemaps'] > candidate['peerDependenciesAfterRemaps'] == 1
assert control['pendingAlive'] == candidate['pendingAlive']
assert all(control['pendingAlive'])
assert candidate['retiredAfterSyncDrains'] == 0 < control['retiredAfterSyncDrains']
inputs = ['build-utils/melonx/adapt_texture_handle_dependencies.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/source.json', 'test/melonx_texture_handle_dependencies_test.py',
          'test/melonx_texture_handle_dependencies/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
    completeTextureGroupHandle=True, completeTextureDependency=True, completeGpuSyncActionWalker=True,
    nativeTextureAndCpuTrackingBoundariesDoubled=True, upstreamRevision=PIN['revision'], dotnet=PIN['dotnet'],
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
    postimages=postimages, extraction=extraction)
out=ROOT/'dist/melonx/texture-handle-dependencies-checks.json';out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2)+'\n')
print('Texture handle graph retirement, deferred copies and retained sync owners passed.', flush=True)
