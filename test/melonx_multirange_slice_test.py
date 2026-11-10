#!/usr/bin/env python3
"""Compare the complete production MultiRange implementation and an independent interval oracle."""
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
from adapt_multirange_slice import apply

PREIMAGES = {
    'src/Ryujinx.Memory/Range/MultiRange.cs': '70c52a73bba5827126c9eb32fb8d66d8342e33b0fa73a90f96137f65ce29c767',
    'src/Ryujinx.Memory/Range/MemoryRange.cs': 'f49868746fc1fedea3dbbb18a3e5da10edf7c223a9184191ecd2b7f6fea66da0',
}
for relative, expected in PREIMAGES.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
reports, postimages, compiled = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-multirange-slice-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        for relative in PREIMAGES:
            path = work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, path)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest() for path in changed}
        shutil.copyfile(ROOT / 'test/melonx_multirange_slice/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers></PropertyGroup></Project>''')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
            cwd=work, env=environment, capture_output=True, text=True, timeout=180)
        if result.returncode: print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        compiled[variant] = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(work.rglob('*.cs')) if 'obj' not in path.relative_to(work).parts}
        print(variant, json.dumps(reports[variant]), flush=True)
assert reports['control']['semanticDigest'] == reports['candidate']['semanticDigest']
assert reports['control']['cases'] == reports['candidate']['cases']
assert reports['control']['semanticBytes'] == reports['candidate']['semanticBytes']
for before, after in zip(reports['control']['benchmark'], reports['candidate']['benchmark'], strict=True):
    assert before['name'] == after['name']
    if 'single' in after['name'] or after['name'] == 'empty-input': assert after['bytesPerSlice'] == 0, after
    else:
        expected = {'fragmented-two': 56, 'fragmented-whole': 8216}[after['name']]
        assert after['bytesPerSlice'] == expected and after['bytesPerSlice'] < before['bytesPerSlice'], (before, after)
inputs = ['build-utils/melonx/adapt_multirange_slice.py', 'build-utils/melonx/adapt_session.py',
    'build-utils/melonx/source.json', 'test/melonx_multirange_slice_test.py', 'test/melonx_multirange_slice/Program.cs']
receipt = dict(result='passed', upstreamRevision=pin['revision'], dotnet=pin['dotnet'], reports=reports,
    physicalDeviceTested=False, productionBodiesUninstrumented=True, independentOracle=True,
    inputs={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in inputs},
    upstreamInputs=PREIMAGES, postimages=postimages, compiledSourceInputs=compiled)
output = ROOT / 'dist/melonx/multirange-slice-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('MultiRange slice equivalence, independent interval oracle and allocation checks passed.', flush=True)
