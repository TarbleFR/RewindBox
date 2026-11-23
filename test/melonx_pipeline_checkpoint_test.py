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
from adapt_host_qos_pipeline_budget import PIPELINE_BUDGET_NEW, PIPELINE_BUDGET_OLD
sys.path.insert(0,str(ROOT/'test'))
import importlib
from melonx_adapter_control import ORDER, apply_present, reverse_present
# Core 661: adapters later in the preparation that edit this file (adapt_teardown_cache: the main cache saved before
# program disposal) are reversed first, latest first, then the declared observers; each runs its own gate.
LATER=[name for name in ORDER if RELATIVE in importlib.import_module(name).BASELINE]

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
                final=(CANDIDATE/RELATIVE).read_text()
                with tempfile.TemporaryDirectory(prefix='melonx-pipeline-checkpoint-later-') as later_root:
                    copy=Path(later_root)/RELATIVE;copy.parent.mkdir(parents=True);shutil.copyfile(CANDIDATE/RELATIVE,copy)
                    for name in reversed(LATER):
                        assert reverse_present(Path(later_root),name,only=[RELATIVE])==[RELATIVE],name
                    plain=copy.read_text()
                    # reverse_present may put back an adapter's recorded preimage instead of undoing its text in the
                    # final file: the same adapters applied forward again, each on the bytes it pins, must give the
                    # final file back byte for byte, so that `plain` is bound to the final preparation.
                    for name in LATER:
                        assert apply_present(Path(later_root),name,only=[RELATIVE])==[RELATIVE],name
                    assert copy.read_bytes()==(CANDIDATE/RELATIVE).read_bytes(),'the final pipeline class is not the reversed file plus the later adapters'
                hooks=[
                    ('using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n',''),
                    ('            using var sizeMeasurement = PD.Measure(PD.Phase.CacheSizeProbe);\n',''),
                    ('            using var saveMeasurement = PD.Measure(PD.Phase.CacheSave);\n',''),
                    ('                PD.Count(PD.Counter.CacheExports);\n',''),
                    ('                PD.Count(PD.Counter.CacheExportBytes, written);\n',''),
                    # Later in the preparation: the 1 GiB budget (adapt_host_qos_pipeline_budget).
                    (PIPELINE_BUDGET_NEW,PIPELINE_BUDGET_OLD),
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
        if variant=='candidate' and CANDIDATE:
            # The final manager reads the encoding policy since Core 771 (later adapters: adapt_hogwarts_frame_budget,
            # adapt_hogwarts_pipeline_replay; the fixture's EncodingPolicy double). The run above has it off, as every
            # title but the one the launch sets it for; the same build runs again with it on: the checkpoint pacing and
            # every scenario's assertions must hold either way.
            base_text=(CANDIDATE/'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs').read_text(encoding='utf-8-sig')
            policy=base_text[base_text.index('    public static class EncodingPolicy'):base_text.index('    static class RenderDetail')]
            assert 'public static bool BindingSizedDescriptorScratch { get; set; }\n' in policy and 'public static bool IncrementalArrayDescriptors { get; set; }\n' in policy,'the policy flags of the final source, off unless set'
            used=set(__import__('re').findall(r'EncodingPolicy\.(\w+)',final))
            assert used<={'BindingSizedDescriptorScratch','IncrementalArrayDescriptors'},'policy member the double lacks: '+str(used)
            run=subprocess.run([os.environ.get('DOTNET','dotnet'),'run','--no-build','--project',str(work),'-c','Release','-v','q','--',variant,'on'],cwd=work,text=True,capture_output=True,timeout=120)
            if run.returncode:print(run.stdout,run.stderr);run.check_returncode()
            reports['candidatePolicyOn']=json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
    if CANDIDATE:
        on=reports['candidatePolicyOn']
        assert on['scenarios']==reports['candidate']['scenarios'] and on['assertions']==reports['candidate']['assertions'],'the encoding policy changes the scenarios or their assertions'
        assert on['results'][0]['exportsIncludingFinal']==2 and on['results'][0]['creationProbes']==193,'the encoding policy changes the checkpoint pacing'
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
local=['build-utils/melonx/adapt_pipeline_checkpoint_pacing.py','build-utils/melonx/adapt_host_qos_pipeline_budget.py','test/melonx_pipeline_checkpoint_test.py','test/melonx_pipeline_checkpoint/Program.cs','test/melonx_pipeline_checkpoint/Boundaries.cs']
if CANDIDATE:local+=['test/melonx_adapter_control.py',*('build-utils/melonx/'+name+'.py' for name in LATER)]
bindings=[dict(variant='candidate',reportPath=['compiledSourceInputs','candidate',RELATIVE],productionPath=RELATIVE)]
if CANDIDATE:bindings.append(dict(variant='candidate',reportPath=['compiledSourceInputs','candidate','EmbeddedPerformanceDiagnostics.cs'],productionPath=collector))
receipt=dict(result='passed',encodingPolicyRuns=['off','on'] if CANDIDATE else [],laterAdaptersReapplied=LATER if CANDIDATE else [],sourceKind='baselinePreparedWithFinalInstrumentedCandidate' if CANDIDATE else 'baselinePrepared',physicalDeviceTested=False,fpsGainProven=False,completeProductionClasses=True,vulkanBoundaryDoubled=True,realFileMappingAndSnapshots=True,adapterIdempotent=True,sourceDriftControlsPassed=negatives,reports=reports,inputs={p:sha(ROOT/p) for p in local},upstreamInputs=preimages,preimages=preimages,postimages=postimages,compiledSourceInputs=compiled,compiledBindings=bindings)
out=ROOT/'dist/melonx/pipeline-checkpoint-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
