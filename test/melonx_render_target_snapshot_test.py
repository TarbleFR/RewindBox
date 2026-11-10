#!/usr/bin/env python3
"""Execute the complete production GAL command and TableRef against a fake backend.

The renderer transport is a deterministic two-slot FIFO. Command conversion,
reference consumption, ArrayPool and cleanup are production code. Check both
unchanged semantics and the old retention/exception-ownership failure. No GPU
or physical-device performance claim follows from this allocation test.
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
from adapt_render_target_snapshot import apply, RELATIVE, UPSTREAM

FILES = [RELATIVE,
         'src/Ryujinx.Graphics.GAL/Multithreading/Model/TableRef.cs',
         'src/Ryujinx.Graphics.GAL/Multithreading/Commands/IGALCommand.cs']
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert hashlib.sha256((SOURCE / RELATIVE).read_bytes()).hexdigest() == UPSTREAM
reports, postimages = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-render-target-snapshot-') as directory:
    for variant in ('control', 'candidate'):
        work = Path(directory) / variant
        for relative in FILES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in changed}
        shutil.copyfile(ROOT / 'test/melonx_render_target_snapshot/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers>
<NuGetAudit>false</NuGetAudit><NoWarn>0649;0162</NoWarn>
<DefineConstants>''' + ('ADAPTED' if variant == 'candidate' else '') + '''</DefineConstants>
</PropertyGroup></Project>''')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'disable'}}))
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1',
                           DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'test.csproj'),
                                 '-c', 'Release'], cwd=work, capture_output=True, text=True,
                                env=environment, timeout=120)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

control, candidate = reports['control'], reports['candidate']
assert control['semantics'] == candidate['semantics']
assert control['exceptions'] == candidate['exceptions']
assert not control['successCleared'] and candidate['successCleared']
assert not control['conversionReturned'] and candidate['conversionReturned']
assert not control['backendReturned'] and candidate['backendReturned']
assert control['poolRetainsResource'] and not candidate['poolRetainsResource']
assert control['warmAllocatedBytes'] == candidate['warmAllocatedBytes'] == 0
inputs = ['build-utils/melonx/adapt_render_target_snapshot.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/source.json', 'test/melonx_render_target_snapshot_test.py',
          'test/melonx_render_target_snapshot/Program.cs']
receipt = dict(result='passed', reports=reports, completeProductionCommandAndTableRef=True,
               rendererTransportDoubled=True, backendDoubled=True, physicalDeviceTested=False,
               upstreamRevision=PIN['revision'], dotnet=PIN['dotnet'],
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
               postimages=postimages)
output = ROOT / 'dist/melonx/render-target-snapshot-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Render-target snapshot ownership, retention and warm allocation checks passed.', flush=True)
