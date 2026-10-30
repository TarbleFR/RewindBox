#!/usr/bin/env python3
"""Trace scopes preserve action/error identity and never alter cache policy."""
import hashlib,json,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
from adapt_startup_trace import apply
paths=['src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs','src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs','src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs']
with tempfile.TemporaryDirectory(prefix='melonx-startup-')as tmp:
 w=Path(tmp);a=w/'source'
 for name in paths:
  p=a/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/name,p)
 # Caller passes retained prepared source, not another original-source adaptation.
 changed=apply(a);assert len(changed)==3
 for name in paths:
  before=(SOURCE/name).read_text(encoding='utf-8-sig');after=(a/name).read_text()
  if name.endswith('NativePageTable.cs'):
   assert 'else\n            {\n                throw new InvalidMemoryRegionException('in after
   assert after.replace('throw new InvalidMemoryRegionException($"Native page-table guard: relativeOffset=0x{address:X}; size={size}; write={write}; tableBytes=0x{_nativePageTable.Size - _hostPageSize:X}.");','throw new InvalidMemoryRegionException();')==before
  elif name.endswith('PipelineCacheManager.cs'):
   assert 'mainPipelineCache'in after and 'workerPipelineCache'in after
   assert after.count('CreateCache(')==before.count('CreateCache(')
   assert after.count('OpenSnapshot(')==before.count('OpenSnapshot(')
  else:assert after.count('new Ryujinx.Common.EmbeddedStartupTrace(')==6
 shutil.copyfile(ROOT/'native/melonx/EmbeddedStartupTrace.cs',w/'EmbeddedStartupTrace.cs')
 (w/'Program.cs').write_text('''using System; using System.Collections.Generic; using System.Text.Json;
namespace Ryujinx.Common { public static class EmbeddedLaunchDiagnostics {
 public static List<string> Events=new(); public static bool Fail; public static string Stage="gpu";
 public static void Record(string stage,string status,string detail) { if(Fail)throw new Exception("journal");if(status=="begin")Stage=stage;Events.Add(stage+":"+status+":"+detail); } } }
class Program { static int checks;static void C(bool b) {checks++;if(!b)throw new Exception("trace contract");}
static void Main() {
 var e=Ryujinx.Common.EmbeddedLaunchDiagnostics.Events;
 var trace=new Ryujinx.Common.EmbeddedStartupTrace("device");C(e.Count==1&&e[0]=="gpuStartup:scopeBegin:device");
 trace.Dispose();trace.Dispose();C(e.Count==2&&e[1].StartsWith("gpuStartup:scopeEnd:device; elapsedMs="));
 var original=new InvalidOperationException("native failure");
 try { using var t=new Ryujinx.Common.EmbeddedStartupTrace("mainPipelineCache");throw original; }
 catch(Exception x) {C(ReferenceEquals(original,x));}
 C(e.Count==4);C(!string.Join(" ",e).Contains("passed"));
 Ryujinx.Common.EmbeddedLaunchDiagnostics.Fail=true;
 try {using var t=new Ryujinx.Common.EmbeddedStartupTrace("surface");throw original;}
 catch(Exception x) {C(ReferenceEquals(original,x));}
 C(e.Count==4);C(Ryujinx.Common.EmbeddedLaunchDiagnostics.Stage=="gpu");Console.WriteLine(JsonSerializer.Serialize(new {result="passed",checks,nativeVulkanExecuted=false})); } }
''')
 (w/'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit></PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
 (w/'global.json').write_text(json.dumps({'sdk':{'version':'10.0.100','rollForward':'disable'}}))
 r=subprocess.run(['dotnet','run','--project',str(w),'-c','Release','-v','q'],capture_output=True,text=True,timeout=180)
 if r.returncode:print(r.stdout,r.stderr);r.check_returncode()
 report=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('{')))
 report.update(physicalDeviceTested=False,inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),ROOT/'build-utils/melonx/adapt_startup_trace.py',ROOT/'native/melonx/EmbeddedStartupTrace.cs']},postimages={n:hashlib.sha256((a/n).read_bytes()).hexdigest()for n in paths})
 out=ROOT/'dist/melonx/startup-trace-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
