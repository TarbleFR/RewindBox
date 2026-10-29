#!/usr/bin/env python3
"""Run complete production uniform updater against original and scalar oracles.

Register storage, translation, memory writes and bindings are explicit test
boundaries. The real updater and GPU-address packer execute; trace bytes,
flush addresses, dirty events, translation calls and pending fields are checked.
The FIFO and shadow register paths are unchanged and not simulated as proof.
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
from adapt_uniform_buffer_spans import apply, RELATIVE, BASELINE

GPUVA = 'src/Ryujinx.Graphics.Gpu/Engine/Types/GpuVa.cs'
STATE = 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClassState.cs'
PREIMAGES = {
    RELATIVE: BASELINE,
    GPUVA: '3b016ed92eea63abd9a0c61bb1951360839ae35f25d57054c9a088968dd7cc45',
    STATE: '7e3bdbadec947a1082bd341d9149028b60ed129c725ac67544505f3d8ca6d274',
}
for relative, expected in PREIMAGES.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
text = (SOURCE / STATE).read_text()
signature = '    struct UniformBufferState\n'
assert text.count(signature) == 1
start = text.index(signature)
end = text.index('{', start) + 1
depth = 1
while depth:
    depth += (text[end] == '{') - (text[end] == '}')
    end += 1
uniform_state = text[start:end]
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
reports, postimages, compiled = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-uniform-spans-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        for relative in (RELATIVE, GPUVA):
            path = work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, path)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        (work / 'UniformBufferState.cs').write_text('using Ryujinx.Graphics.Gpu.Engine.Types;\n'
            'namespace Ryujinx.Graphics.Gpu.Engine.Threed\n{\n' + uniform_state + '\n}\n')
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(ROOT / 'test/melonx_uniform_buffer_spans' / name, work / name)
        (work / 'Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><NoWarn>0649</NoWarn>
<DefineConstants>{'ADAPTED' if variant == 'candidate' else ''}</DefineConstants></PropertyGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release'],
            cwd=work, env=environment, text=True, capture_output=True, timeout=180)
        if result.returncode:
            print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        compiled[variant] = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in work.rglob('*.cs') if 'obj' not in p.relative_to(work).parts}
        print(variant, json.dumps(reports[variant]), flush=True)

assert reports['control']['smallDigest'] == reports['candidate']['smallDigest']
assert reports['control']['smallCases'] == reports['candidate']['smallCases']
assert reports['control']['unsupported'] == reports['candidate']['largeCases']
assert all(row['allocatedBytes'] == 0 for report in reports.values() for row in report['measurements'])
inputs = ['build-utils/melonx/adapt_uniform_buffer_spans.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/source.json', 'test/melonx_uniform_buffer_spans_test.py',
          'test/melonx_uniform_buffer_spans/Program.cs', 'test/melonx_uniform_buffer_spans/Boundaries.cs']
receipt = dict(result='passed', upstreamRevision=pin['revision'], dotnet=pin['dotnet'], reports=reports,
    physicalDeviceTested=False, fifoAndShadowPathsChanged=False,
    memoryAndRegisterStorageDoubled=True, upstreamInputs=PREIMAGES, postimages=postimages,
    compiledSourceInputs=compiled, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/uniform-buffer-span-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Uniform span bounds, scalar-equivalent large packets and unchanged small packets passed.', flush=True)
