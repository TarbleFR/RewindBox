#!/usr/bin/env python3
"""Exercise whole production threaded array classes and commands.

Only renderer transport and host resources are doubled. Both variants retain
the exact-length deferred snapshot contract. No Vulkan/iPhone result is claimed.
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
from adapt_single_resource_bindings import apply, BACKEND_INPUTS

GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
FILES = [GAL + '/ITextureArray.cs', GAL + '/IImageArray.cs',
         MULTI + '/Model/TableRef.cs', MULTI + '/Commands/IGALCommand.cs',
         MULTI + '/Resources/ThreadedTextureArray.cs',
         MULTI + '/Resources/ThreadedImageArray.cs',
         MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs',
         MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
         MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs',
         MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
         MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs']
reports, postimages = {}, {}
backend_drift_controls = 0
with tempfile.TemporaryDirectory(prefix='melonx-single-resource-') as temporary:
    negative = Path(temporary).resolve() / 'backend-drift'
    for relative in [*FILES, *BACKEND_INPUTS]:
        target = negative / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)
    for relative in BACKEND_INPUTS:
        target = negative / relative
        original = target.read_bytes()
        target.write_bytes(original + b'\n// changed backend contract\n')
        try:
            apply(negative)
        except AssertionError:
            backend_drift_controls += 1
        else:
            raise AssertionError('changed backend contract accepted: ' + relative)
        assert all((negative / p).read_bytes() == (SOURCE / p).read_bytes() for p in FILES)
        target.write_bytes(original)
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        for relative in [*FILES, *BACKEND_INPUTS]:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {p.relative_to(work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in changed}
        shutil.copyfile(ROOT / 'test/melonx_single_resource_bindings/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="src/Ryujinx.Graphics.Vulkan/**;src/Ryujinx.Graphics.OpenGL/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release', '--', variant],
                                cwd=work, capture_output=True, text=True, timeout=180, env=environment)
        if result.returncode:
            print(result.stdout, result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

control, candidate = reports['control'], reports['candidate']
assert candidate['functionalDigest'] == control['functionalDigest']
for old, new in zip(control['allocations'], candidate['allocations'], strict=True):
    assert (old['kind'], old['length']) == (new['kind'], new['length'])
    if new['length'] == 1:
        assert new['bytes'] == 0 and old['bytes'] > 0, (old, new)
    else:
        assert new['bytes'] == old['bytes'], (old, new)
inputs = ['build-utils/melonx/adapt_single_resource_bindings.py',
          'test/melonx_single_resource_bindings_test.py',
          'test/melonx_single_resource_bindings/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               rendererTransportDoubled=True, wholeProductionClasses=True,
               backendDriftControls=backend_drift_controls,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               baselineInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in [*FILES, *BACKEND_INPUTS]},
               postimages=postimages)
out = ROOT / 'dist/melonx/single-resource-binding-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
