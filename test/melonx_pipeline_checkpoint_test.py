#!/usr/bin/env python3
"""Run complete PipelineCacheManager against real snapshot files and an explicit Vulkan double."""
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
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('source',type=Path)
parser.add_argument('--candidate-source',type=Path)
args=parser.parse_args()
SOURCE=args.source.resolve()
CANDIDATE=args.candidate_source.resolve() if args.candidate_source else None
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
from adapt_pipeline_checkpoint_pacing import apply, RELATIVE, BEFORE, DIRTY_BEFORE

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
preimages={RELATIVE:sha(SOURCE/RELATIVE)}
reports,compiled,postimages={},{},{}
collector='src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
with tempfile.TemporaryDirectory(prefix='melonx-pipeline-checkpoint-') as temporary:
    base=Path(temporary)
    for variant in ('control','candidate'):
        work=base/variant;target=work/RELATIVE;target.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE/RELATIVE,target)
        if variant=='candidate':
            apply(work);optimized=target.read_text();before=sha(target);apply(work)
            assert sha(target)==before,'non-idempotent checkpoint adapter'
            if CANDIDATE:
                final=(CANDIDATE/RELATIVE).read_text();plain=final
                hooks=[
                    ('using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n',''),
                    ('            using var sizeMeasurement = PD.Measure(PD.Phase.CacheSizeProbe);\n',''),
                    ('            using var saveMeasurement = PD.Measure(PD.Phase.CacheSave);\n',''),
                    ('                PD.Count(PD.Counter.CacheExports);\n',''),
                    ('                PD.Count(PD.Counter.CacheExportBytes, written);\n',''),
                ]
                for old,new in hooks:
                    assert plain.count(old)==1,'unreviewed instrumentation: '+old
                    plain=plain.replace(old,new)
                assert plain==optimized,'final pipeline class changes beyond pacing and declared observers'
                target.write_text(final)
                shutil.copyfile(CANDIDATE/collector,work/'EmbeddedPerformanceDiagnostics.cs')
                postimages[collector]=sha(CANDIDATE/collector)
            postimages[RELATIVE]=sha(target)
        for name in ('Program.cs','Boundaries.cs'):shutil.copyfile(ROOT/'test/melonx_pipeline_checkpoint'/name,work/name)
        define='<DefineConstants>INSTRUMENTED_CANDIDATE</DefineConstants>' if variant=='candidate' and CANDIDATE else ''
        (work/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>'+define+'</PropertyGroup></Project>')
        (work/'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
        (work/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        compiled[variant]={p.relative_to(work).as_posix():sha(p) for p in work.rglob('*.cs')}
        run=subprocess.run([os.environ.get('DOTNET','dotnet'),'run','--project',str(work),'-c','Release','-v','q','--',variant],cwd=work,text=True,capture_output=True,timeout=120)
        if run.returncode:print(run.stdout,run.stderr);run.check_returncode()
        reports[variant]=json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
    assert reports['control']['scenarios']==reports['candidate']['scenarios']
    assert reports['control']['assertions']==reports['candidate']['assertions']
    assert reports['control']['results'][0]['exportsIncludingFinal']==193
    assert reports['candidate']['results'][0]['exportsIncludingFinal']==2
    assert reports['control']['results'][0]['creationProbes']==reports['candidate']['results'][0]['creationProbes']==193
    negatives=0
    for old,new in ((BEFORE,'// missing gate'),(BEFORE,BEFORE+'\n'+BEFORE),(DIRTY_BEFORE,'// missing dirty gate')):
        path=base/'negative'/RELATIVE;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text((SOURCE/RELATIVE).read_text().replace(old,new));before=sha(path)
        try:apply(base/'negative')
        except RuntimeError:negatives+=1
        else:raise AssertionError('source drift accepted')
        assert sha(path)==before,'mutation before drift rejection'
local=['build-utils/melonx/adapt_pipeline_checkpoint_pacing.py','test/melonx_pipeline_checkpoint_test.py','test/melonx_pipeline_checkpoint/Program.cs','test/melonx_pipeline_checkpoint/Boundaries.cs']
bindings=[dict(variant='candidate',reportPath=['compiledSourceInputs','candidate',RELATIVE],productionPath=RELATIVE)]
if CANDIDATE:bindings.append(dict(variant='candidate',reportPath=['compiledSourceInputs','candidate','EmbeddedPerformanceDiagnostics.cs'],productionPath=collector))
receipt=dict(result='passed',sourceKind='baselinePreparedWithFinalInstrumentedCandidate' if CANDIDATE else 'baselinePrepared',physicalDeviceTested=False,fpsGainProven=False,completeProductionClasses=True,vulkanBoundaryDoubled=True,realFileMappingAndSnapshots=True,adapterIdempotent=True,sourceDriftControlsPassed=negatives,reports=reports,inputs={p:sha(ROOT/p) for p in local},upstreamInputs=preimages,preimages=preimages,postimages=postimages,compiledSourceInputs=compiled,compiledBindings=bindings)
out=ROOT/'dist/melonx/pipeline-checkpoint-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
