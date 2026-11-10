#!/usr/bin/env python3
"""Compile retained production report/conditional code with actual changed methods.

Input is the baseline prepared source. Native query readiness and the command
transport are controlled doubles; production command/InvokeCommand, decoder of
conditional decisions, report publication and both syncpoint methods are real.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
from adapt_occlusion_completion import apply

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def member(text,key):
    start=text.index(key);left=text.index('{',start);depth=1
    for i in range(left+1,len(text)):
        depth+=(text[i]=='{')-(text[i]=='}')
        if depth==0:return text[start:i+1]
    raise AssertionError(key)

gal='src/Ryujinx.Graphics.GAL/'
gpu='src/Ryujinx.Graphics.Gpu/'
changed=[gpu+'Engine/Threed/ThreedClass.cs',gal+'Multithreading/ThreadedPipeline.cs',gal+'Multithreading/Commands/TryHostConditionalRenderingCommand.cs']
whole=[gal+'ICounterEvent.cs',gal+'Multithreading/Model/TableRef.cs',gal+'Multithreading/Model/ResultBox.cs',gal+'Multithreading/Resources/ThreadedCounterEvent.cs',gal+'Multithreading/Commands/TryHostConditionalRenderingCommand.cs',gal+'Multithreading/Commands/TryHostConditionalRenderingFlushCommand.cs',gal+'Multithreading/Commands/CounterEvent/CounterEventDisposeCommand.cs',gal+'Multithreading/Commands/Renderer/ActionCommand.cs',gpu+'Memory/CounterCache.cs',gpu+'Memory/DeferredCounterReport.cs',gpu+'Engine/Threed/ConditionalRendering.cs']
extracted=[gpu+'Engine/GPFifo/GPFifoClass.cs',gpu+'Engine/Threed/ThreedClass.cs',gpu+'GpuContext.cs',gal+'Multithreading/ThreadedPipeline.cs',gal+'Multithreading/ThreadedRenderer.cs','src/Ryujinx.Graphics.Vulkan/PipelineFull.cs','src/Ryujinx.Graphics.OpenGL/Pipeline.cs']
inputs=sorted(set(whole+extracted))
preimages={p:sha(SOURCE/p)for p in inputs}
reports={};compiled={};postimages={}
with tempfile.TemporaryDirectory(prefix='melonx-occlusion-completion-')as temp:
    for variant in ('control','candidate'):
        work=Path(temp)/variant;source=work/'source'
        for p in inputs:
            dst=source/p;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/p,dst)
        if variant=='candidate':
            apply(source);first={p:sha(source/p)for p in changed};apply(source)
            assert first=={p:sha(source/p)for p in changed},'idempotence'
            postimages=first
        for p in whole:shutil.copyfile(source/p,work/Path(p).name)
        def wrap(filename,header,path,keys,footer='}}'):
            text=(source/path).read_text()
            (work/filename).write_text(header+'\n'+'\n'.join(member(text,k)for k in keys)+'\n'+footer)
        wrap('Syncpoints.cs','using System;using System.Threading;namespace Ryujinx.Graphics.Gpu {partial class FifoProbe {',gpu+'Engine/GPFifo/GPFifoClass.cs',['public void Syncpointb('])
        wrap('Threed.cs','namespace Ryujinx.Graphics.Gpu {partial class ThreedProbe {',gpu+'Engine/Threed/ThreedClass.cs',['public void IncrementSyncpoint('])
        wrap('Context.cs','using System;namespace Ryujinx.Graphics.Gpu {partial class GpuContext {',gpu+'GpuContext.cs',['internal bool FlushCounterReports('])
        wrap('ThreadedPipeline.cs','using Ryujinx.Graphics.GAL.Multithreading.Commands;using Ryujinx.Graphics.GAL.Multithreading.Model;using Ryujinx.Graphics.GAL.Multithreading.Resources;namespace Ryujinx.Graphics.GAL.Multithreading {partial class ThreadedPipeline {',gal+'Multithreading/ThreadedPipeline.cs',['public unsafe bool TryHostConditionalRendering(ICounterEvent value, ulong','public unsafe bool TryHostConditionalRendering(ICounterEvent value, ICounterEvent'])
        wrap('ThreadedInvokes.cs','using System;using System.Threading;using System.Runtime.ExceptionServices;using Ryujinx.Graphics.GAL.Multithreading.Commands;using Ryujinx.Graphics.GAL.Multithreading.Commands.Renderer;namespace Ryujinx.Graphics.GAL.Multithreading {partial class ThreadedRenderer {',gal+'Multithreading/ThreadedRenderer.cs',['internal void InvokeCommand(','internal void ThrowIfFailed(','private void RecordFailure(','public unsafe void BackgroundContextAction('])
        wrap('VulkanConditional.cs','using Ryujinx.Graphics.GAL;namespace Ryujinx.Graphics.Vulkan {partial class PipelineFull {','src/Ryujinx.Graphics.Vulkan/PipelineFull.cs',['public bool TryHostConditionalRendering(ICounterEvent value, ulong','public bool TryHostConditionalRendering(ICounterEvent value, ICounterEvent'])
        wrap('OpenGLConditional.cs','using Ryujinx.Graphics.GAL;using Ryujinx.Graphics.OpenGL.Queries;namespace Ryujinx.Graphics.OpenGL {partial class Pipeline {','src/Ryujinx.Graphics.OpenGL/Pipeline.cs',['public bool TryHostConditionalRendering(ICounterEvent value, ulong','public bool TryHostConditionalRendering(ICounterEvent value, ICounterEvent','public void EndHostConditionalRendering('])
        for name in ('Program.cs','Boundaries.cs'):shutil.copyfile(ROOT/'test/melonx_occlusion_completion'/name,work/name)
        (work/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableDefaultCompileItems>false</EnableDefaultCompileItems><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><DefineConstants>'+variant.upper()+'</DefineConstants></PropertyGroup><ItemGroup><Compile Include="*.cs" /></ItemGroup></Project>')
        (work/'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
        (work/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        compiled[variant]={p.name:sha(p)for p in work.glob('*.cs')}
        run=subprocess.run([os.environ.get('DOTNET','dotnet'),'run','--project',str(work),'-c','Release','-v','q'],text=True,capture_output=True,timeout=100)
        if run.returncode:print(run.stdout,run.stderr);run.check_returncode()
        reports[variant]=json.loads(next(x for x in run.stdout.splitlines()if x.startswith('{')))
        print(variant,json.dumps(reports[variant]),flush=True)
local=['build-utils/melonx/adapt_occlusion_completion.py','test/melonx_occlusion_completion_test.py','test/melonx_occlusion_completion/Program.cs','test/melonx_occlusion_completion/Boundaries.cs']
report=dict(result='passed',sourceKind='baselinePrepared',physicalDeviceTested=False,nativeQueryBoundariesDoubled=True,commandTransportDoubled=True,hogwartsCrashCauseProven=False,reports=reports,inputs={p:sha(ROOT/p)for p in local},upstreamInputs=preimages,preimages={p:preimages[p]for p in changed},postimages=postimages,compiledSourceInputs=compiled)
out=ROOT/'dist/melonx/occlusion-completion-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
