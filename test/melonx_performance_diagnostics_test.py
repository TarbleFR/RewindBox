#!/usr/bin/env python3
"""Run actual collector/journal and bind observers to the final prepared source.

The complete Common production classes execute, including their native append
calls. Other hook files are source-composition checked, not claimed as compiled
by this fixture; the full NativeAOT build is a separate mandatory CI step.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

LOCAL = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='Prepared delivered Ada baseline')
parser.add_argument('--candidate-source', type=Path, help='Actual final prepared source')
parser.add_argument('--repository-root', type=Path, default=LOCAL, help='Only for staged local reconstruction; CI uses the checkout')
args = parser.parse_args()
ROOT = args.repository_root.resolve()
SOURCE = args.source.resolve()
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
optimization_root = Path(os.environ.get('MELONX_OPTIMIZATION_ADAPTERS', str(ROOT / 'build-utils/melonx')))
sys.path[:0] = [str(LOCAL / 'build-utils/melonx'), str(optimization_root)]
from adapt_performance_diagnostics import apply, NAMES
from adapt_pipeline_checkpoint_pacing import apply as pacing
from adapt_counter_report_compaction import apply as compact
from adapt_single_virtual_dependency import apply as single, CONSUMERS


def local(relative):
    path = LOCAL / relative
    return path if path.exists() else ROOT / relative


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


native = {
    'native/melonx/EmbeddedPerformanceDiagnostics.cs': 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs',
    'native/melonx/EmbeddedLaunchDiagnostics.cs': 'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs',
    'native/melonx/EmbeddedSession.cs': 'src/Ryujinx.Library/EmbeddedSession.cs',
}
unchanged = 'src/Ryujinx.Library/EmbeddedPerformance.cs'
existing = [*NAMES, *CONSUMERS, native['native/melonx/EmbeddedLaunchDiagnostics.cs'],
            native['native/melonx/EmbeddedSession.cs'], unchanged]
upstream = {path: sha(SOURCE / path) for path in existing}
postimages = {}
source_checks = 0
with tempfile.TemporaryDirectory(prefix='melonx-performance-diagnostics-') as temporary:
    work = Path(temporary)
    expected = work / 'prepared'
    for relative in existing:
        target = expected / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)
    pacing(expected); compact(expected); single(expected)
    original = {path: (expected / path).read_bytes() for path in NAMES}
    apply(expected)
    for relative, target in native.items():
        destination = expected / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local(relative), destination)
    paths = list(dict.fromkeys([*existing, *native.values()]))
    for path in paths:
        if CANDIDATE:
            assert (expected / path).read_bytes() == (CANDIDATE / path).read_bytes(), 'Final prepared source differs: ' + path
        postimages[path] = sha((CANDIDATE or expected) / path)
        source_checks += 1
    # Observer drift and repeat application reject without partial file writes.
    before = {path: sha(expected / path) for path in NAMES}
    try:
        apply(expected)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Repeated observer application accepted')
    assert {path: sha(expected / path) for path in NAMES} == before
    source_checks += 1
    drift = work / 'drift'
    for path, data in original.items():
        target = drift / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    broken = drift / NAMES[0]
    broken.write_text(broken.read_text().replace('public void DispatchCalls()', 'public void ChangedDispatchCalls()'))
    before = {path: sha(drift / path) for path in NAMES}
    try:
        apply(drift)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Missing observer anchor accepted')
    assert {path: sha(drift / path) for path in NAMES} == before
    source_checks += 1
    # Accepted-run ownership and finally are unchanged except observer calls.
    session_before = (SOURCE / native['native/melonx/EmbeddedSession.cs']).read_text()
    session_after = (expected / native['native/melonx/EmbeddedSession.cs']).read_text()
    normalized = session_after.replace('                EmbeddedPerformanceDiagnostics.Start(generation);\n', '').replace('                    EmbeddedPerformanceDiagnostics.Stop(generation);\n', '')
    assert normalized == session_before, 'Unexpected session policy change'
    assert session_after.index('return EmbeddedSessions.Run(generation') < session_after.index('EmbeddedPerformanceDiagnostics.Start(generation)') < session_after.index('try { Load(options)')
    assert session_after.index('finally\n                {\n                    EmbeddedPerformanceDiagnostics.Stop(generation);') > session_after.index('try { Load(options)')
    source_checks += 3
    assert (expected / unchanged).read_bytes() == (SOURCE / unchanged).read_bytes(), 'UIKit sampler changed'
    source_checks += 1
    source = CANDIDATE or expected
    compiled = {}
    for filename in ('EmbeddedPerformanceDiagnostics.cs', 'EmbeddedLaunchDiagnostics.cs'):
        path = source / 'src/Ryujinx.Common' / filename
        shutil.copyfile(path, work / filename)
        compiled[filename] = sha(path)
    shutil.copyfile(LOCAL / 'test/melonx_performance_diagnostics/Program.cs', work / 'Program.cs')
    compiled['Program.cs'] = sha(work / 'Program.cs')
    (work / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableDefaultCompileItems>false</EnableDefaultCompileItems><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit></PropertyGroup><ItemGroup><Compile Include="*.cs" /></ItemGroup></Project>')
    (work / 'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
    (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    env = os.environ.copy(); env['DOTNET_TieredCompilation'] = '0'
    run = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work), '-c', 'Release', '-v', 'q'],
                         text=True, capture_output=True, timeout=120, env=env)
    if run.returncode:
        print(run.stdout, run.stderr)
        run.check_returncode()
    result = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))

input_paths = [*native, 'build-utils/melonx/adapt_performance_diagnostics.py',
               'build-utils/melonx/adapt_pipeline_checkpoint_pacing.py',
               'build-utils/melonx/adapt_counter_report_compaction.py',
               'build-utils/melonx/adapt_single_virtual_dependency.py',
               'test/melonx_performance_diagnostics_test.py', 'test/melonx_performance_diagnostics/Program.cs']
inputs = {}
for path in input_paths:
    file = local(path)
    if not file.exists() and path.startswith('build-utils/melonx/'):
        file = optimization_root / Path(path).name
    inputs[path] = sha(file)
report = dict(result='passed', sourceKind='finalPrepared' if CANDIDATE else 'reconstructedPreparedCandidate',
              physicalDeviceTested=False, gameplayTested=False, fpsGainProven=False,
              sourceChecks=source_checks, resultDetails=result, inputs=inputs,
              upstreamInputs=upstream, preimages=upstream, postimages=postimages,
              compiledSourceInputs=compiled,
              compiledBindings=[dict(productionPath='src/Ryujinx.Common/' + name,
                  reportPath=['compiledSourceInputs', name]) for name in ('EmbeddedPerformanceDiagnostics.cs', 'EmbeddedLaunchDiagnostics.cs')],
              sourceOnlyHooks=NAMES,
              compilationScope='Complete production collector and journal; other hook source composition verified, full NativeAOT compilation remains a separate gate.',
              hostRuntime='dotnet-10.0.100 Release; tiered compilation disabled')
output = LOCAL / 'dist/melonx/performance-diagnostics-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
