#!/usr/bin/env python3
"""Compile complete baseline and final CounterCache/report classes with boundary doubles."""
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
args = parser.parse_args()
SOURCE = args.source.resolve()
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_counter_report_compaction import apply, RELATIVE, BEFORE

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
paths = [RELATIVE, 'src/Ryujinx.Graphics.Gpu/Memory/DeferredCounterReport.cs',
         'src/Ryujinx.Graphics.Gpu/Memory/UnmapEventArgs.cs', 'src/Ryujinx.Graphics.GAL/ICounterEvent.cs']
preimages = {p: sha(SOURCE / p) for p in paths}
reports, compiled, postimages = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-report-compaction-') as temporary:
    base = Path(temporary)
    for variant in ('control', 'candidate'):
        work = base / variant
        for p in paths:
            target = work / p
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / p, target)
        if variant == 'candidate':
            apply(work)
            optimized = (work / RELATIVE).read_text()
            before = sha(work / RELATIVE); apply(work)
            assert sha(work / RELATIVE) == before, 'adapter not idempotent'
            if CANDIDATE:
                final = (CANDIDATE / RELATIVE).read_text()
                plain = final
                hooks = [
                    ('using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n', ''),
                    ('            using var reportMeasurement = PD.Measure(PD.Phase.CounterReports);\n', ''),
                    ('            PD.ReportBatch(reports.Length);\n', ''),
                    ('''            foreach (var report in reports)
            {
                report.Flush();
                PD.Count(PD.Counter.CounterReportsFlushed);
            }''', '            foreach (var report in reports) report.Flush();'),
                ]
                for old, new in hooks:
                    assert plain.count(old) == 1, 'unreviewed final instrumentation: ' + old
                    plain = plain.replace(old, new)
                assert plain == optimized, 'final class changes beyond compaction and declared observers'
                for p in paths:
                    if p != RELATIVE: assert sha(CANDIDATE / p) == preimages[p], p
                    shutil.copyfile(CANDIDATE / p, work / p)
                collector = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
                shutil.copyfile(CANDIDATE / collector, work / 'EmbeddedPerformanceDiagnostics.cs')
                postimages[collector] = sha(CANDIDATE / collector)
                shutil.copyfile(ROOT / 'test/melonx_counter_report_compaction/JournalBoundary.cs', work / 'JournalBoundary.cs')
            postimages.update({p: sha(work / p) for p in paths})
        shutil.copyfile(ROOT / 'test/melonx_counter_report_compaction/Program.cs', work / 'Program.cs')
        define = '<DefineConstants>INSTRUMENTED_CANDIDATE</DefineConstants>' if variant == 'candidate' and CANDIDATE else ''
        (work / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>' + define + '</PropertyGroup></Project>')
        (work / 'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        compiled[variant] = {p.relative_to(work).as_posix(): sha(p) for p in work.rglob('*.cs')}
        run = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work), '-c', 'Release', '-v', 'q'],
            cwd=work, env=dict(os.environ, DOTNET_TieredCompilation='0'), text=True, capture_output=True, timeout=120)
        if run.returncode: print(run.stdout, run.stderr); run.check_returncode()
        reports[variant] = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
    assert reports['control']['scenarios'] == reports['candidate']['scenarios'], 'changed publication/release/pending history'
    assert reports['control']['checks'] == reports['candidate']['checks']
    for control, candidate in zip(reports['control']['costs'], reports['candidate']['costs'], strict=True):
        assert control['count'] == candidate['count'] and control['allocatedBytes'] == candidate['allocatedBytes'], 'compaction added allocation'
    negatives = 0
    for marker in ('// anchor removed', BEFORE + '\n' + BEFORE):
        path = base / 'negative' / RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((SOURCE / RELATIVE).read_text().replace(BEFORE, marker))
        before = sha(path)
        try: apply(base / 'negative')
        except RuntimeError: negatives += 1
        else: raise AssertionError('source drift accepted')
        assert sha(path) == before, 'source mutated before rejected drift'
local = ['build-utils/melonx/adapt_counter_report_compaction.py', 'test/melonx_counter_report_compaction_test.py',
         'test/melonx_counter_report_compaction/Program.cs', 'test/melonx_counter_report_compaction/JournalBoundary.cs']
for value in reports.values():
    scenarios = value.pop('scenarios')
    value['scenarios'] = len(scenarios)
    value['semanticSHA256'] = hashlib.sha256(json.dumps(scenarios, separators=(',', ':')).encode()).hexdigest()
receipt = dict(result='passed', sourceKind='baselinePreparedWithFinalInstrumentedCandidate' if CANDIDATE else 'baselinePrepared',
    physicalDeviceTested=False, fpsGainProven=False, gcReductionClaimed=False, completeProductionClasses=True,
    adapterIdempotent=True, sourceDriftControlsPassed=negatives, reports=reports,
    inputs={p: sha(ROOT / p) for p in local}, upstreamInputs=preimages, preimages={RELATIVE: preimages[RELATIVE]},
    postimages=postimages, compiledSourceInputs=compiled,
    compiledBindings=[dict(variant='candidate', reportPath=['compiledSourceInputs','candidate',p], productionPath=p) for p in paths] +
        ([dict(variant='candidate', reportPath=['compiledSourceInputs','candidate','EmbeddedPerformanceDiagnostics.cs'],
               productionPath='src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs')] if CANDIDATE else []),
    timingScope='Independent host processes; timing observations only, not an iOS benchmark')
out = ROOT / ('dist/melonx/counter-report-compaction-final-checks.json' if CANDIDATE else 'dist/melonx/counter-report-compaction-checks.json')
out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
