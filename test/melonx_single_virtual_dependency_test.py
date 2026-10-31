#!/usr/bin/env python3
"""Test exact physical/virtual buffer classes and compare one-dependency allocations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--candidate-source', type=Path)
parser.add_argument('--repo-root', type=Path, default=ROOT, help='Only for isolated staging: location of retained fixture inputs.')
args = parser.parse_args()
SOURCE, REPO = args.source.resolve(), args.repo_root.resolve()
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_single_virtual_dependency import apply, RELATIVE, CONSUMERS

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
paths = ['src/Ryujinx.Graphics.Gpu/Memory/' + name + '.cs' for name in ('Buffer','MultiRangeBuffer','BufferModifiedRangeList','BufferMigration')]
paths += ['src/Ryujinx.Memory/Range/' + name + '.cs' for name in ('IRange','INonOverlappingRange','RangeListBase','NonOverlappingRangeList','MemoryRange','MultiRange','IMultiRangeItem')]
paths += ['src/Ryujinx.Graphics.GAL/' + name + '.cs' for name in ('BufferHandle','BufferRange','PinnedSpan','BufferAccess')]
paths += ['src/Ryujinx.Graphics.Gpu/Synchronization/ISyncActionHandler.cs']
preimages = {p: sha(SOURCE / p) for p in paths}
retained = ['test/melonx_virtual_buffer_readback/Program.cs','test/melonx_virtual_buffer_readback/Boundaries.cs']
owned = ['build-utils/melonx/adapt_single_virtual_dependency.py','test/melonx_single_virtual_dependency_test.py',
         'test/melonx_single_virtual_dependency/Extra.cs','test/melonx_single_virtual_dependency/CostRunner.cs','test/melonx_single_virtual_dependency/JournalBoundary.cs']
reports, compiled, postimages, binaries = {}, {}, {}, []
environment = dict(os.environ, DOTNET_TieredCompilation='0', DOTNET_CLI_TELEMETRY_OPTOUT='1')
dotnet = os.environ.get('DOTNET', 'dotnet')

def run(command, work, timeout=180):
    process = subprocess.run(command, cwd=work, env=environment, text=True, capture_output=True, timeout=timeout)
    if process.returncode: print(process.stdout, process.stderr); process.check_returncode()
    return process.stdout

def project(work, define='', library=False):
    (work / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>' + ('Library' if library else 'Exe') + '</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>' + define + '</PropertyGroup></Project>')
    (work / 'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
    (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')

with tempfile.TemporaryDirectory(prefix='melonx-single-dependency-') as temporary:
    base = Path(temporary)
    drift = 0
    for changed in [RELATIVE, *CONSUMERS]:
        negative = base / 'drift'
        for path in [RELATIVE, *CONSUMERS]:
            target = negative / path; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        (negative / changed).write_bytes((negative / changed).read_bytes() + b'\n// changed boundary\n')
        before = sha(negative / RELATIVE)
        try: apply(negative)
        except RuntimeError: drift += 1
        else: raise AssertionError('changed boundary accepted: ' + changed)
        assert sha(negative / RELATIVE) == before, 'mutated rejected source'
    for variant in ('control','candidate'):
        work = base / variant
        for path in paths:
            target = work / path; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        if variant == 'candidate':
            apply(work)
            optimized = (work / RELATIVE).read_text()
            before = sha(work / RELATIVE); apply(work)
            assert sha(work / RELATIVE) == before, 'adapter not idempotent'
            if CANDIDATE:
                final = (CANDIDATE / RELATIVE).read_text()
                plain = final
                alias = 'using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n'
                assert plain.count(alias) == 1; plain = plain.replace(alias,'')
                for counter in ('VirtualDependencySingle','VirtualDependencyMultiple'):
                    hook = '                PD.Count(PD.Counter.' + counter + ');\n'
                    assert plain.count(hook) == 2, 'wrong observer scope: ' + counter
                    plain = plain.replace(hook,'')
                assert plain == optimized, 'final Buffer changes beyond reviewed branch and counters'
                for path in paths:
                    if path != RELATIVE: assert sha(CANDIDATE / path) == preimages[path], 'changed retained consumer: ' + path
                    shutil.copyfile(CANDIDATE / path, work / path)
                collector = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
                shutil.copyfile(CANDIDATE / collector, work / 'EmbeddedPerformanceDiagnostics.cs')
                shutil.copyfile(ROOT / 'test/melonx_single_virtual_dependency/JournalBoundary.cs', work / 'JournalBoundary.cs')
                postimages[collector] = sha(CANDIDATE / collector)
            postimages.update({path: sha(work / path) for path in paths})
        program = (REPO / retained[0]).read_text()
        assert program.count('static class Program') == 1 and program.count('        bool overcopyCorrected = Clamp() & FragmentedClamp(); Functional(); VolatileLease();') == 1
        program = program.replace('static class Program','static partial class Program')
        program = program.replace('        bool overcopyCorrected = Clamp() & FragmentedClamp(); Functional(); VolatileLease();', '        SingleDependencyCases();\n        bool overcopyCorrected = Clamp() & FragmentedClamp(); Functional(); VolatileLease();')
        (work / 'Program.cs').write_text(program)
        shutil.copyfile(REPO / retained[1], work / 'Boundaries.cs')
        shutil.copyfile(ROOT / 'test/melonx_single_virtual_dependency/Extra.cs', work / 'Extra.cs')
        define = '<DefineConstants>INSTRUMENTED_CANDIDATE</DefineConstants>' if variant == 'candidate' and CANDIDATE else ''
        project(work,define)
        compiled[variant] = {p.relative_to(work).as_posix(): sha(p) for p in work.rglob('*.cs')}
        output = run([dotnet,'run','--project',str(work),'-c','Release','-v','q','--','candidate'],work)
        reports[variant] = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
        reports[variant]['retainedFixtureMode'] = reports[variant].pop('variant')
        reports[variant]['variant'] = variant
        binaries.append(str(work / 'bin/Release/net10.0/Probe.dll'))
    assert reports['control']['overcopyCorrected'] and reports['candidate']['overcopyCorrected'], 'retained readback fix regressed'
    assert reports['control']['assertions'] == reports['candidate']['assertions']
    assert reports['control']['semanticDigest'] == reports['candidate']['semanticDigest'], 'production behavior changed'
    savings = []
    for control,candidate in zip(reports['control']['allocations'],reports['candidate']['allocations'],strict=True):
        key = ('length','dependencies','dirty','gpuSync','flushes')
        assert all(control[k] == candidate[k] for k in key)
        saved = control['bytes'] - candidate['bytes']
        assert saved == (304 * control['flushes'] if control['dependencies'] == 1 else 0), (control,candidate)
        savings.append({k:control[k] for k in key} | dict(savedBytesPerCall=saved/control['flushes']))
    cost = base / 'cost'; cost.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_single_virtual_dependency/CostRunner.cs',cost/'Program.cs')
    project(cost)
    output = run([dotnet,'run','--project',str(cost),'-c','Release','-v','q','--',*binaries],cost,240)
    timing = json.loads(next(line for line in output.splitlines() if line.startswith('{')))

receipt = dict(result='passed', sourceKind='baselinePreparedWithFinalInstrumentedCandidate' if CANDIDATE else 'baselinePrepared',
    completeProductionClasses=True, physicalDeviceTested=False, fpsGainProven=False, rendererAndTrackingDoubled=True,
    adapterIdempotent=True, sourceDriftControlsPassed=drift, reports=reports, savings=savings, hostCost=timing,
    inputs={p:sha(ROOT/p) for p in owned} | {p:sha(REPO/p) for p in retained}, upstreamInputs=preimages,
    preimages={RELATIVE:preimages[RELATIVE]}, postimages=postimages, compiledSourceInputs=compiled,
    compiledBindings=[dict(variant='candidate',reportPath=['compiledSourceInputs','candidate',p],productionPath=p) for p in paths] +
        ([dict(variant='candidate',reportPath=['compiledSourceInputs','candidate','EmbeddedPerformanceDiagnostics.cs'],
               productionPath='src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs')] if CANDIDATE else []),
    timingScope='Paired same-process host algorithm probe; no production GC policy change or iPhone prediction')
out=ROOT/('dist/melonx/single-virtual-dependency-final-checks.json' if CANDIDATE else 'dist/melonx/single-virtual-dependency-checks.json')
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
