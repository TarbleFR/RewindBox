#!/usr/bin/env python3
"""Exercise whole production GAL producers, commands, TableRef and bounded pool.

The backend and renderer transport are doubled; command payloads, snapshot
capture, conversion and cache ownership are unmodified production classes.
Compare exact outputs and allocations against the six-change candidate before
this adapter. Host timings include slower cases and establish no iPhone gain.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_bounded_binding_snapshots import apply, BASELINE, BACKEND_INPUTS

GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
FILES = [GAL + '/ITextureArray.cs', GAL + '/IImageArray.cs',
         MULTI + '/Model/TableRef.cs', MULTI + '/Commands/IGALCommand.cs',
         *(MULTI + '/' + name for name in BASELINE),
         MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs',
         MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs']
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
reports, postimages = {}, {}
drift_controls = 0
with tempfile.TemporaryDirectory(prefix='melonx-bounded-binding-snapshots-') as temporary:
    negative = Path(temporary).resolve() / 'drift'
    for relative in [*FILES, *BACKEND_INPUTS]:
        target = negative / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)
    for relative in [*BACKEND_INPUTS, *(MULTI + '/' + name for name in BASELINE)]:
        target = negative / relative
        original = target.read_bytes()
        target.write_bytes(original + b'\n// contract drift\n')
        try:
            apply(negative)
        except AssertionError:
            drift_controls += 1
        else:
            raise AssertionError('modified contract accepted: ' + relative)
        for other in FILES:
            if other != relative:
                assert (negative / other).read_bytes() == (SOURCE / other).read_bytes()
        assert not (negative / MULTI / 'Model/ThreadedArrayPool.cs').exists()
        target.write_bytes(original)
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        for relative in [*FILES, *BACKEND_INPUTS]:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {p.relative_to(work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        shutil.copyfile(ROOT / 'test/melonx_bounded_binding_snapshots/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>
<DefineConstants>''' + ('POOLED' if variant == 'candidate' else '') + '''</DefineConstants>
</PropertyGroup><ItemGroup><Compile Remove="src/Ryujinx.Graphics.Vulkan/**;src/Ryujinx.Graphics.OpenGL/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'disable'}}))
        environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'test.csproj'),
                                 '-c', 'Release', '--', variant], cwd=work, capture_output=True, text=True,
                                timeout=180, env=environment)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

    # Reuse both already prepared source trees in one runner process. Aliased
    # library references preserve identical production namespaces and switch
    # measurement order each sample, limiting independent-process CPU bias.
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copyfile(ROOT / 'test/melonx_bounded_binding_snapshots/PairedBridge.cs', work / 'PairedBridge.cs')
        project = work / 'test.csproj'
        (work / (variant + '.csproj')).write_text(project.read_text().replace(
            '<OutputType>Exe</OutputType>', '<OutputType>Library</OutputType><AssemblyName>BindingSnapshot'
            + variant.title() + '</AssemblyName>'))
    paired = Path(temporary).resolve() / 'paired'
    paired.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_bounded_binding_snapshots/PairedProgram.cs', paired / 'Program.cs')
    (paired / 'paired.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit>
<EnableNETAnalyzers>false</EnableNETAnalyzers></PropertyGroup><ItemGroup>
<ProjectReference Include="../control/control.csproj" Aliases="Control" />
<ProjectReference Include="../candidate/candidate.csproj" Aliases="Candidate" />
</ItemGroup></Project>''')
    (paired / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'disable'}}))
    (paired / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    build = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'build', str(paired / 'paired.csproj'),
                            '-c', 'Release', '--nologo', '-m:1', '-p:RestoreDisableParallel=true',
                            '-p:BuildInParallel=false'], cwd=paired, capture_output=True, text=True,
                           timeout=180, env=environment)
    if build.returncode:
        print(build.stdout, build.stderr, flush=True)
    build.check_returncode()
    result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), str(paired / 'bin/Release/net10.0/paired.dll')],
                            cwd=paired, capture_output=True, text=True,
                            timeout=180, env=environment)
    if result.returncode:
        print(result.stdout, result.stderr, flush=True)
    result.check_returncode()
    paired_report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

control, candidate = reports['control'], reports['candidate']
assert control['functionalDigest'] == candidate['functionalDigest']
assert candidate['concurrentCommands'] == control['concurrentCommands']
timings = []
for old, new in zip(control['allocations'], candidate['allocations'], strict=True):
    assert (old['kind'], old['length']) == (new['kind'], new['length'])
    if 2 <= new['length'] <= 4096:
        assert old['bytes'] > 0 and new['bytes'] == 0, (old, new)
    else:
        assert old['bytes'] == new['bytes'], (old, new)
    before, after = statistics.median(old['elapsedNs']), statistics.median(new['elapsedNs'])
    timings.append(dict(kind=old['kind'], length=old['length'], controlMedianNs=before,
                        candidateMedianNs=after, ratio=after / before if before else None))
paired_timings = []
for case in paired_report['cases']:
    if 2 <= case['length'] <= 4096:
        assert all(value == 0 for value in case['candidateBytes']), case
        assert all(value > 0 for value in case['controlBytes']), case
    else:
        assert case['candidateBytes'] == case['controlBytes'], case
    before, after = statistics.median(case['controlNs']), statistics.median(case['candidateNs'])
    paired_timings.append(dict(kind=case['kind'], length=case['length'], controlMedianNs=before,
                               candidateMedianNs=after, ratio=after / before if before else None))
inputs = ['build-utils/melonx/adapt_bounded_binding_snapshots.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/adapt_single_resource_bindings.py', 'build-utils/melonx/source.json',
          'test/melonx_bounded_binding_snapshots_test.py', 'test/melonx_bounded_binding_snapshots/Program.cs',
          'test/melonx_bounded_binding_snapshots/PairedBridge.cs', 'test/melonx_bounded_binding_snapshots/PairedProgram.cs']
receipt = dict(result='passed', reports=reports, timings=timings, pairedReport=paired_report,
               pairedTimings=paired_timings, physicalDeviceTested=False,
               rendererTransportDoubled=True, backendDoubled=True, wholeProductionClasses=True,
               backendAndSourceDriftControls=drift_controls, maxCachedArraysPerType=8,
               maximumCachedLength=4096, maximumCachedReferenceSlotBytesArm64=2 * 8 * 4096 * 8,
               inFlightSnapshotsBoundedByExistingCommandQueue=True,
               upstreamRevision=PIN['revision'], dotnet=PIN['dotnet'],
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               baselineInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in [*FILES, *BACKEND_INPUTS]},
               postimages=postimages)
output = ROOT / 'dist/melonx/bounded-binding-snapshot-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Bounded binding snapshots: production ownership, concurrency, exact lengths and allocations passed.', flush=True)
