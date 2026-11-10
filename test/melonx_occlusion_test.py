#!/usr/bin/env python3
"""Execute production reports/cache/queue and extracted FIFO/mapping methods."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
import adapt_occlusion_reports as adapter

def method(text, signature):
 start=text.index(signature);left=text.index('{',start);depth=1;i=left+1
 while depth:
  if text[i]=='{':depth+=1
  if text[i]=='}':depth-=1
  i+=1
 return text[start:i]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
reports={};compiled={}
with tempfile.TemporaryDirectory(prefix='melonx-occlusion-') as temp:
 for variant in ('control','candidate'):
  work=Path(temp)/variant;src=work/'engine';src.mkdir(parents=True)
  spec=json.loads((ROOT/'build-utils/melonx/occlusion-adapter-contract.json').read_text())
  for p,h in spec['before'].items():
   if h is None:continue
   assert sha(SOURCE/p)==h,p
   target=src/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/p,target)
  if variant=='candidate':adapter.apply(src);adapter.apply(src)
  for rel in ['Ryujinx.Graphics.Gpu/Memory/CounterCache.cs','Ryujinx.Graphics.Gpu/Engine/Threed/SemaphoreUpdater.cs','Ryujinx.Graphics.Vulkan/Queries/CounterQueue.cs','Ryujinx.Graphics.Vulkan/Queries/CounterQueueEvent.cs']:
   shutil.copyfile(src/'src'/rel,work/Path(rel).name)
  if variant=='candidate':
   shutil.copyfile(src/'src/Ryujinx.Graphics.Gpu/Memory/DeferredCounterReport.cs',work/'DeferredCounterReport.cs')
   s=(src/'src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs').read_text()
   methods='\n'.join(method(s,k) for k in ['internal DeferredCounterReport BeginCounterReport(', 'internal void WriteCounterReport<T>('])
   (work/'Memory.cs').write_text('namespace Ryujinx.Graphics.Gpu.Memory {partial class MemoryManager {'+methods+'}}')
   s=(src/'src/Ryujinx.Graphics.Gpu/GpuContext.cs').read_text()
   (work/'Context.cs').write_text('using System;namespace Ryujinx.Graphics.Gpu {partial class GpuContext {'+method(s,'internal bool FlushCounterReports(')+'}}')
  s=(src/'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs').read_text()
  (work/'Fifo.cs').write_text('using System;using System.Threading;namespace Ryujinx.Graphics.Gpu {partial class FifoProbe {'+method(s,'public void Syncpointb(')+'}}')
  for n in ('Boundaries.cs','Program.cs'):shutil.copyfile(ROOT/'test/melonx_occlusion'/n,work/n)
  # The src copy is evidence/input to extraction, not another compilation unit.
  (work/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><EnableDefaultCompileItems>false</EnableDefaultCompileItems><EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><DefineConstants>'+('CANDIDATE' if variant=='candidate' else 'CONTROL')+'</DefineConstants></PropertyGroup><ItemGroup><Compile Include="*.cs" /></ItemGroup></Project>')
  (work/'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
  (work/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
  compiled[variant]={p.name:sha(p)for p in work.glob('*.cs')}
  run=subprocess.run([os.environ.get('DOTNET','dotnet'),'run','--project',str(work),'-c','Release'],cwd=work,text=True,capture_output=True,timeout=90)
  if run.returncode:print(run.stdout,run.stderr);run.check_returncode()
  reports[variant]=json.loads(next(s for s in run.stdout.splitlines()if s.startswith('{')))
  print(variant,reports[variant],flush=True)
inputs=['test/melonx_occlusion_test.py','test/melonx_occlusion/Program.cs','test/melonx_occlusion/Boundaries.cs','build-utils/melonx/adapt_occlusion_reports.py','build-utils/melonx/occlusion-adapter-contract.json']
out=ROOT/'dist/melonx/occlusion-checks.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(dict(result='passed',physicalDeviceTested=False,nativeQueryBoundariesDoubled=True,reports=reports,compiledSourceInputs=compiled,inputs={p:sha(ROOT/p)for p in inputs}),indent=2)+'\n')
