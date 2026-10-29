#!/usr/bin/env python3
"""Compare real ordered overlap bodies with historical and value cursors.

Reuse the established overlap fixture because its production inputs change;
add iterator protocol, malformed layout and mutation cases for the new cursor.
The LINQ oracle still uses unchanged SizeInfo.AllRegions in both variants.
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
from adapt_texture_overlap import apply as baseline
from adapt_texture_region_cursor import apply
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
for p, digest in UPSTREAM.items():
    assert hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() == digest, p
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())

def member(text, signature):
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    for index in range(brace + 1, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0: return text[start:index + 1]
    raise AssertionError(signature)

reports, postimages, extraction, baseline_inputs = {}, {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-texture-region-cursor-') as directory:
    for variant in ('control', 'candidate'):
        work = Path(directory) / variant
        source = work / 'source'
        for p in UPSTREAM:
            target = source / p; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / p, target)
        baseline(source)
        before = {p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in UPSTREAM}
        if baseline_inputs: assert before == baseline_inputs
        else: baseline_inputs = before
        if variant == 'candidate':
            changed = apply(source)
            postimages = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        text = (source / 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs').read_text()
        methods = ('private void InitializeTexture(',
                   'public bool DataOverlaps(Texture texture, TextureViewCompatibility compatibility)',
                   'private bool HasOrderedDataRegions()',
                   'private bool DataOverlapsContiguous(Texture texture, MultiRange otherRange)',
                   'private bool DataOverlapsUnordered(Texture texture, MultiRange otherRange)')
        pieces = {m: member(text, m) for m in methods}
        body = '\n'.join(pieces.values()) + '\n        private byte _dataRegionOrder;\n'
        code = ('using System;\nusing System.Collections.Generic;\nusing System.Linq;\n'
                'using Ryujinx.Graphics.Gpu.Memory;\nusing Ryujinx.Graphics.Texture;\nusing Ryujinx.Memory.Range;\n'
                'namespace Ryujinx.Graphics.Gpu.Image { partial class Texture {\n' + body + '\n} }\n')
        (work / 'ProductionBodies.cs').write_text(code)
        extraction[variant] = dict(compiledExtractSha256=hashlib.sha256(code.encode()).hexdigest(),
                                   completeMethods={k: hashlib.sha256(v.encode()).hexdigest() for k, v in pieces.items()})
        for p in UPSTREAM:
            if not p.endswith('/Image/Texture.cs'): shutil.copyfile(source / p, work / Path(p).name)
        shutil.copyfile(ROOT / 'test/melonx_texture_overlap/Program.cs', work / 'Program.cs')
        shutil.copyfile(ROOT / 'test/melonx_texture_region_cursor/CursorProgram.cs', work / 'CursorProgram.cs')
        define = 'ADAPTED' if variant == 'candidate' else ''
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<StartupObject>CursorProgram</StartupObject><Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers>
<NuGetAudit>false</NuGetAudit><DefineConstants>{define}</DefineConstants>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'disable'}}))
        env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        run = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'test.csproj'), '-c', 'Release', '--', variant],
                             cwd=work, env=env, capture_output=True, text=True, timeout=180)
        print(run.stdout, flush=True)
        if run.returncode: print(run.stderr, flush=True)
        run.check_returncode()
        data = [json.loads(line) for line in run.stdout.splitlines() if line.startswith('{')]
        assert len(data) == 2
        reports[variant] = dict(overlap=data[0], cursor=data[1])
control, candidate = reports['control'], reports['candidate']
for key in ('checks', 'resultDigest', 'covered'):
    assert control['overlap'][key] == candidate['overlap'][key], key
assert control['cursor']['digest'] == candidate['cursor']['digest']
assert control['cursor']['cases'] == candidate['cursor']['cases']
for old, new in zip(control['overlap']['benchmarks'], candidate['overlap']['benchmarks'], strict=True):
    assert (old['name'], old['result']) == (new['name'], new['result'])
    if old['name'] not in ('single-subresource', 'fragmented-first-match'):
        assert old['bytesPerCall'] > 0 and new['bytesPerCall'] == 0, (old, new)
    else: assert old['bytesPerCall'] == new['bytesPerCall'], (old, new)
assert candidate['cursor']['allocatedBytes'] == 0 < control['cursor']['allocatedBytes']
inputs = ['build-utils/melonx/adapt_texture_region_cursor.py', 'build-utils/melonx/adapt_texture_overlap.py',
          'build-utils/melonx/adapt_session.py', 'build-utils/melonx/source.json',
          'test/melonx_texture_region_cursor_test.py', 'test/melonx_texture_region_cursor/CursorProgram.cs',
          'test/melonx_texture_overlap/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               unchangedEnumerableOracle=True, completeSizeInfo=True, productionOverlapBodiesVerbatim=True,
               gpuResourcesUsed=False, upstreamRevision=PIN['revision'], dotnet=PIN['dotnet'],
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs=UPSTREAM, preparedBaselineInputs=baseline_inputs,
               postimages=postimages, extraction=extraction)
out = ROOT / 'dist/melonx/texture-region-cursor-checks.json'; out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Texture region cursor protocol, real overlap oracle and allocation checks passed.', flush=True)
