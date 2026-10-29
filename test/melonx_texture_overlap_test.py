#!/usr/bin/env python3
"""Execute production texture overlap bodies and actual size/range utilities.

The control and candidate use the same pinned sources. Only Texture's unrelated
renderer/storage endpoints are omitted from the host harness; DataOverlaps and
its candidate helper are compiled without rewriting their bodies. The real
SizeCalculator, SizeInfo, MultiRange and MemoryRange execute in both variants.
CPU timings describe warm host calls, not device gameplay or iPhone FPS.
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
from adapt_texture_overlap import apply

UPSTREAM = {
    'src/Ryujinx.Graphics.Gpu/Image/Texture.cs': '2b0efc551b02535fe96a123dca328208313896db558c68cd9af01c7ae31c8f07',
    'src/Ryujinx.Graphics.Gpu/Image/TextureViewCompatibility.cs': '47d65cd1027efd36bcfcd5aad479c948a681cad53a772d1627a3ae83f83bc2a4',
    'src/Ryujinx.Graphics.Texture/SizeInfo.cs': '3e3bcadecbbe9c4fc629fa0aef6629c7b65e8affc7ebcf99dd09be1c016afa89',
    'src/Ryujinx.Graphics.Texture/SizeCalculator.cs': '5eccd413aa26c6bb48ca2d1449998d8bf763a71d9f1e066b301e627f5bcccf8e',
    'src/Ryujinx.Graphics.Texture/Size.cs': '49ca31348f73196428dfe74a7f27bf9fbdfb22896da4ab8416b76d2628592391',
    'src/Ryujinx.Graphics.Texture/Region.cs': 'c09bce72a70eac647f0be22ab3acfd2ab0315697d7daaa605d963be7cf472322',
    'src/Ryujinx.Graphics.Texture/BlockLinearConstants.cs': 'e9dba0f3ef2b704ccce34af1485c31b5e9cd79e5168b8cf7bd3a1f210a6acb50',
    'src/Ryujinx.Memory/Range/MemoryRange.cs': 'f49868746fc1fedea3dbbb18a3e5da10edf7c223a9184191ecd2b7f6fea66da0',
    'src/Ryujinx.Memory/Range/MultiRange.cs': '70c52a73bba5827126c9eb32fb8d66d8342e33b0fa73a90f96137f65ce29c767',
    'src/Ryujinx.Common/Utilities/BitUtils.cs': '3f33297b391f95cfba6d3ec848b69f94534848b74f919310181e0a51eb450261',
}
for path, digest in UPSTREAM.items():
    assert hashlib.sha256((SOURCE / path).read_bytes()).hexdigest() == digest, path


def member(text, signature):
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
reports = {}
postimages = {}
production_members = {}
with tempfile.TemporaryDirectory(prefix='melonx-texture-overlap-') as temporary:
    base = Path(temporary).resolve()
    for mode in ('control', 'candidate'):
        work = base / mode
        source = work / 'source'
        for path in UPSTREAM:
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        if mode == 'candidate':
            changed = apply(source)
            postimages = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in changed}
            # A rejected second application may already have modified earlier
            # anchors. Keep this negative fixture outside the compiled source.
            rejected_source = base / 'rejected-candidate'
            shutil.copytree(source, rejected_source)
            try:
                apply(rejected_source)
            except AssertionError:
                pass
            else:
                raise AssertionError('The adapter must reject an already adapted input')
            for relative, digest in postimages.items():
                assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == digest, relative

        text = (source / 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs').read_text()
        body = member(text, 'private void InitializeTexture(')
        body += '\n' + member(text, 'public bool DataOverlaps(Texture texture, TextureViewCompatibility compatibility)')
        if mode == 'candidate':
            body += '\n        private byte _dataRegionOrder;\n'
            body += '\n' + member(text, 'private bool HasOrderedDataRegions()')
            body += '\n' + member(text, 'private bool DataOverlapsContiguous(Texture texture, MultiRange otherRange)')
            body += '\n' + member(text, 'private bool DataOverlapsUnordered(Texture texture, MultiRange otherRange)')
        production_members[mode] = hashlib.sha256(body.encode()).hexdigest()
        (work / 'ProductionBodies.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Texture;
using Ryujinx.Memory.Range;
namespace Ryujinx.Graphics.Gpu.Image {
partial class Texture {
''' + body + '\n}\n}\n')
        for relative in UPSTREAM:
            if not relative.endswith('/Image/Texture.cs'):
                shutil.copyfile(source / relative, work / Path(relative).name)
        shutil.copyfile(ROOT / 'test/melonx_texture_overlap/Program.cs', work / 'Program.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        environment = os.environ.copy()
        # One stable code generation tier makes the two warm CPU probes comparable.
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        build = subprocess.run([dotnet, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                               cwd=work, capture_output=True, text=True, timeout=120, env=environment)
        if build.returncode:
            print(build.stdout, build.stderr, flush=True)
            build.check_returncode()
        run = subprocess.run([dotnet, 'bin/Release/net10.0/Probe.dll', mode], cwd=work,
                             capture_output=True, text=True, timeout=120, env=environment)
        if run.returncode:
            print(run.stdout, run.stderr, flush=True)
            run.check_returncode()
        reports[mode] = json.loads(run.stdout.strip().splitlines()[-1])
        print(json.dumps(reports[mode]), flush=True)

control, candidate = reports['control'], reports['candidate']
assert control['checks'] == candidate['checks']
assert control['resultDigest'] == candidate['resultDigest']
assert control['covered'] == candidate['covered']
for old, new in zip(control['firstComparisons'], candidate['firstComparisons'], strict=True):
    assert (old['name'], old['result']) == (new['name'], new['result'])
for old, new in zip(control['benchmarks'], candidate['benchmarks'], strict=True):
    assert (old['name'], old['result'], old['regionsPerTexture']) == (new['name'], new['result'], new['regionsPerTexture'])
    if old['name'].startswith('padded-'):
        assert new['bytesPerCall'] < old['bytesPerCall'] * 0.15, (old, new)
        # Timing is reported, not used as a flaky pass/fail gate on shared runners.
    elif old['name'] == 'single-subresource':
        assert new['bytesPerCall'] == 0, (old, new)

inputs = ['build-utils/melonx/adapt_texture_overlap.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/source.json', 'test/melonx_texture_overlap_test.py',
          'test/melonx_texture_overlap/Program.cs']
receipt = dict(result='passed', reports=reports, upstreamRevision=pin['revision'],
               physicalDeviceTested=False, gpuResourcesUsed=False,
               productionBodiesUnchangedByHarness=True, realSizeAndRangeUtilities=True,
               inputs={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in inputs},
               upstreamInputs=UPSTREAM, productionMembers=production_members, postimages=postimages)
output = ROOT / 'dist/melonx/texture-overlap-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Texture overlap behavior and warm CPU checks passed.', flush=True)
