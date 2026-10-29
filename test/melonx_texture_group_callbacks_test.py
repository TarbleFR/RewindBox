#!/usr/bin/env python3
"""Execute complete texture-group visitor methods against deterministic boundaries.

The production range walk, synchronous callbacks, dirty flags, reprotection,
partial/full decisions, flush bookkeeping and copy-pair loop are verbatim.
Texture/region/GPU endpoints are doubles; no native GPU or frame-rate claim.
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
from adapt_texture_group_callbacks import apply

RELATIVE = 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'
UPSTREAM = '76e452b1f09ec95e6280c2d8518f1c1b318555f9e1c124008082ac4420ea01d9'
assert hashlib.sha256((SOURCE / RELATIVE).read_bytes()).hexdigest() == UPSTREAM
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
METHODS = [
    'public bool CheckDirty(', 'public void DiscardData(',
    'public void SynchronizeMemory(',
    'public void SynchronizeDependents(', 'public bool FlushModified(',
    'public void SignalModified(', 'public void SignalModifying(',
    'private (int Index, int Count) Get3DLevelRange(',
    'public void CreateCopyDependency(Texture other,',
]


def extract(text):
    # The header retains every real field and the complete production constructor.
    header_end = text.index('\n        /// <summary>\n        /// Initialize a new texture group\'s')
    header = text[:header_end].replace('class TextureGroup : IDisposable', 'partial class TextureGroup')
    pieces = {}
    for marker in METHODS:
        start = text.index('        ' + marker)
        end = text.index('\n        /// <summary>', start)
        pieces[marker] = text[start:end]
    for marker in ('private void EvaluateRelevantHandles',):
        start = 0
        for index in range(2):
            start = text.index('        ' + marker, start)
            end = text.index('\n        /// <summary>', start)
            pieces[marker + str(index)] = text[start:end]
            start = end
    return header + '\n' + '\n'.join(pieces.values()) + '\n    }\n}\n', pieces

reports, extraction, postimages = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-texture-group-callbacks-') as directory:
    for variant in ('control', 'candidate'):
        work = Path(directory) / variant
        target = work / RELATIVE
        target.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / RELATIVE, target)
        if variant == 'candidate':
            apply(work)
            postimages[RELATIVE] = hashlib.sha256(target.read_bytes()).hexdigest()
        program, pieces = extract(target.read_text())
        (work / 'Extracted.cs').write_text(program)
        extraction[variant] = dict(
            completeClassHeaderAndConstructor=True,
            compiledExtractSha256=hashlib.sha256(program.encode()).hexdigest(),
            completeMethods={name: hashlib.sha256(body.encode()).hexdigest() for name, body in pieces.items()})
        shutil.copyfile(ROOT / 'test/melonx_texture_group_callbacks/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>
<NoWarn>0169;0414;0649</NoWarn><DefineConstants>''' + ('ADAPTED' if variant == 'candidate' else '') + '''</DefineConstants></PropertyGroup><ItemGroup><Compile Remove="src/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'disable'}}))
        env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'test.csproj'),
                                 '-c', 'Release', '--', variant], cwd=work, env=env,
                                capture_output=True, text=True, timeout=180)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

assert reports['control']['semantics'] == reports['candidate']['semantics']
assert reports['control']['scenarioCount'] == reports['candidate']['scenarioCount']
assert reports['control']['exceptions'] == reports['candidate']['exceptions']
for before, after in zip(reports['control']['allocations'], reports['candidate']['allocations'], strict=True):
    assert before['name'] == after['name']
    if before['name'] in ('sync', 'dependents', 'flush', 'modified'):
        assert before['bytes'] > 0 and after['bytes'] == 0, (before, after)
    else:
        assert after['bytes'] <= before['bytes'], (before, after)
assert reports['candidate']['groupConstructionBytes'] < reports['control']['groupConstructionBytes']
inputs = ['build-utils/melonx/adapt_texture_group_callbacks.py', 'build-utils/melonx/source.json',
          'build-utils/melonx/adapt_session.py', 'test/melonx_texture_group_callbacks_test.py',
          'test/melonx_texture_group_callbacks/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               completeProductionRangeWalkers=True, completeProductionVisitorMethods=True,
               textureRegionGpuBoundariesDoubled=True, timingGate=False,
               upstreamRevision=PIN['revision'], dotnet=PIN['dotnet'],
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={RELATIVE: UPSTREAM}, postimages=postimages, extraction=extraction)
out = ROOT / 'dist/melonx/texture-group-callbacks-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Texture-group visitors: identical traces, independent nested state, allocations recorded.', flush=True)
