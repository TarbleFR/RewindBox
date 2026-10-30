"""Execute production graphics parsing/apply/live ratio with real pinned enums.
The window is a double; there is no GPU or guest gameplay claim here.
"""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
source=Path(sys.argv[1])
with tempfile.TemporaryDirectory(prefix='melonx-display-') as d:
 w=Path(d)
 paths=['native/melonx/EmbeddedGraphicsSettings.cs','native/melonx/EmbeddedSessionCoordinator.cs','native/melonx/EmbeddedMemory.cs','native/melonx/EmbeddedPerformance.cs','native/melonx/EmbeddedNativeLibraries.cs']
 for p in paths:shutil.copyfile(ROOT/p,w/Path(p).name)
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 from adapt_memory import apply
 allocator=w/'source/src/Ryujinx.Memory/DonatedMemory.cs';allocator.parent.mkdir(parents=True)
 shutil.copyfile(source/'src/Ryujinx.Memory/DonatedMemory.cs',allocator)
 apply(w/'source');shutil.move(allocator,w/'DonatedMemory.cs')
 enums=[]
 for name in ['AspectRatioExtensions','ScalingFilter','BackendThreading']:
  text=(source/'src/Ryujinx.Common/Configuration'/f'{name}.cs').read_text()
  enums.append(re.search(r'public enum \w+\s*\{[^}]*\}',text)[0])
 text=(source/'src/Ryujinx.Common/Configuration/VSyncMode.cs').read_text()
 enums.append(re.search(r'public enum \w+\s*\{[^}]*\}',text)[0])
 options=(source/'src/Ryujinx.Library/Options.cs').read_text()
 production=(ROOT/paths[0]).read_text()
 fields=[]
 for name in sorted(set(re.findall(r'options\.(\w+)\s*=',production))):
  m=re.search(r'public\s+([\w.]+)\s+'+name+r'\s*\{\s*get;',options);assert m,name
  fields.append('public '+m[1]+' '+name+' {get;set;}')
 (w/'test.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup></Project>')
 (w/'Stubs.cs').write_text('''using System;using Ryujinx.Common.Configuration;
namespace Ryujinx.Memory {static class MemoryBlock {public static ulong GetPageSize()=>16384;}}
namespace Ryujinx.Common.Logging {enum LogClass {Cpu} class Log {public void Print(LogClass c,string s){}} static class Logger {public static Log Warning=new();}}
namespace Ryujinx.Common.Configuration {'''+''.join(enums)+'''}
namespace Ryujinx.Common {static class EmbeddedLaunchDiagnostics {public static void Fail(string a,string b,Exception e){}}}
namespace Ryujinx.Library {
public class Options {'''+''.join(fields)+'''}
class Configuration {public AspectRatio AspectRatio {get;set;}}
// Same accessors as Ryujinx.HLE.PerformanceStatistics; frame time is 1000 / FPS.
class PerformanceStatistics {public double Fps,Fifo;public double GetGameFrameRate()=>Fps;public double GetGameFrameTime()=>1000/Fps;public double GetFifoPercent()=>Fifo;}
class Device {public Configuration Configuration=new();public PerformanceStatistics Statistics;}
// Ryujinx.HLE.Switch's present-cap entry point (Switch.cs:193).
class Switch {public int PresentTargetFps;public void SetUnboundedPresentTargetFps(int fps)=>PresentTargetFps=fps;}
class Window {public Device Device=new();}
class GameInfo {public string TitleId;}
static class GameInfoLoader {public static string NextTitle;public static bool Fail;public static GameInfo GetGameInfo(object fs,System.IO.Stream s,string ext){if(Fail)throw new Exception("metadata unavailable");return new GameInfo{TitleId=NextTitle};}}
partial class Library {
 internal static object _virtualFileSystem;
 internal static bool TestHogwarts(string path)=>EmbeddedIsHogwarts(path);
 static readonly object EmbeddedHostGate=new();
 internal static EmbeddedSessionCoordinator EmbeddedSessions=new();
 internal static Window _window;
 internal static Switch _emulationContext;
}}
''')
 (w/'Program.cs').write_text(r'''using System;using Ryujinx.Library;using Ryujinx.Common.Configuration;using System.Runtime.InteropServices;using Ryujinx.Memory;using Ryujinx.Common;
unsafe class Program {static void Main(){
int checks=0;void Check(bool v){if(!v)throw new Exception("display assertion "+checks);checks++;}
var defaults=EmbeddedGraphicsSettings.Parse("{}");Check(!defaults.OcclusionQuerySync&&!defaults.RelaxQueryFlushing);
var experiments=EmbeddedGraphicsSettings.Parse("{\"occlusionQuerySync\":true,\"relaxQueryFlushing\":true}");Check(experiments.OcclusionQuerySync&&experiments.RelaxQueryFlushing);
Check(!EmbeddedGraphicsSettings.Parse("{}").OcclusionQuerySync);
string identityFile=System.IO.Path.GetTempFileName();try{
GameInfoLoader.NextTitle="0100f7e00c70e000";Check(Library.TestHogwarts(identityFile));
GameInfoLoader.NextTitle="0100F7E00C70E001";Check(!Library.TestHogwarts(identityFile));
GameInfoLoader.NextTitle=null;Check(!Library.TestHogwarts(identityFile));
GameInfoLoader.Fail=true;Check(!Library.TestHogwarts(identityFile));GameInfoLoader.Fail=false;
}finally{System.IO.File.Delete(identityFile);}
Check(!Library.TestHogwarts("/absent/rewindbox-game.nsp"));
var old=new Options {AspectRatio=AspectRatio.Fixed21x9,EnableHostMemoryBudgetTracking=false,EnableTextureRecompression=false};
EmbeddedGraphicsSettings.Parse("{}").Apply(old);
Check(old.AspectRatio==AspectRatio.Fixed21x9 && !old.EnableHostMemoryBudgetTracking && !old.EnableTextureRecompression);
// Build 531 regression: missing settings must not enable async draw-skipping
// (observed on Persona 5 Royal), and completed shaders must be cacheable.
var safeDefault = new Options {DisableShaderCache=true,EnableAsyncShaderCompilation=true};
EmbeddedGraphicsSettings.Parse("{}").Apply(safeDefault);
Check(!safeDefault.DisableShaderCache && !safeDefault.EnableAsyncShaderCompilation);
// Respect deliberate pre-existing per-game overrides; do not silently mutate
// migrated standalone profiles or already persisted user preferences.
var explicitOld = EmbeddedGraphicsSettings.Parse("{\"shaderCache\":false,\"asyncShaders\":true}")
    .Apply(new Options {DisableShaderCache=false,EnableAsyncShaderCompilation=false});
Check(explicitOld.DisableShaderCache && explicitOld.EnableAsyncShaderCompilation);
var explicitSafe = EmbeddedGraphicsSettings.Parse("{\"shaderCache\":true,\"asyncShaders\":false}")
    .Apply(new Options {DisableShaderCache=true,EnableAsyncShaderCompilation=true});
Check(!explicitSafe.DisableShaderCache && !explicitSafe.EnableAsyncShaderCompilation);
foreach(int ratio in new[]{0,1,2,3,4,5}) {
 var options=EmbeddedGraphicsSettings.Parse("{\"aspectRatio\":"+ratio+",\"hostMemoryBudget\":true,\"textureRecompression\":true}").Apply(new());
 Check((int)options.AspectRatio==ratio && options.EnableHostMemoryBudgetTracking && options.EnableTextureRecompression);
}
// Backend threading: an absent key means On, as the standalone forces before every
// launch whatever its saved config says; explicit false is the per-game escape hatch.
var threadedDefault=EmbeddedGraphicsSettings.Parse("{}").Apply(new(){BackendThreading=BackendThreading.On});
Check(threadedDefault.BackendThreading==BackendThreading.On);
// An Off base (an imported standalone config.json) is not honoured: standalone forces On.
var importedOff=EmbeddedGraphicsSettings.Parse("{}").Apply(new(){BackendThreading=BackendThreading.Off});
Check(importedOff.BackendThreading==BackendThreading.On);
var threadedOff=EmbeddedGraphicsSettings.Parse("{\"backendThreading\":false}").Apply(new(){BackendThreading=BackendThreading.On});
Check(threadedOff.BackendThreading==BackendThreading.Off);
var threadedOn=EmbeddedGraphicsSettings.Parse("{\"backendThreading\":true}").Apply(new(){BackendThreading=BackendThreading.Off});
Check(threadedOn.BackendThreading==BackendThreading.On);
foreach(var text in new[]{"{\"aspectRatio\":-1}","{\"aspectRatio\":6}","{\"aspectRatio\":1.5}","{\"aspectRatio\":\"stretch\"}","{\"hostMemoryBudget\":1}","{\"textureRecompression\":null}","{\"showRamGraph\":true}","{\"backendThreading\":1}"}) {
 bool rejected=false;try{EmbeddedGraphicsSettings.Parse(text);}catch(Exception){rejected=true;}Check(rejected);
}
var restored=EmbeddedGraphicsSettings.Parse("{\"aspectRatio\":1,\"hostMemoryBudget\":false,\"textureRecompression\":false}").Apply(new(){EnableHostMemoryBudgetTracking=true,EnableTextureRecompression=true});
Check(!restored.EnableHostMemoryBudgetTracking && !restored.EnableTextureRecompression);
delegate* unmanaged<long,int,int> set=&Library.EmbeddedSetAspectRatio;
Check(set(1,5)==2);var generation=Library.EmbeddedSessions.Prepare();
Check(set(generation,5)==2);
// Game FPS for the RAM overlay: the same session gate as the live ratio.
delegate* unmanaged<long,double*,int,int> performance=&Library.EmbeddedPerformanceSnapshot;
double* fps=stackalloc double[3];
Check(performance(generation,null,3)==1 && performance(generation,fps,2)==1);
Check(performance(generation,fps,3)==2);Library._window=new();
Check(performance(generation,fps,3)==2);
Library._window.Device.Statistics=new();
Check(performance(generation,fps,3)==0 && fps[0]==0 && fps[1]==0 && fps[2]==0);
Library._window.Device.Statistics.Fps=59.94;Library._window.Device.Statistics.Fifo=37.5;
Check(performance(generation,fps,3)==0 && fps[0]==59.94 && fps[1]==1000/59.94 && fps[2]==37.5);
Library._window.Device.Statistics.Fps=double.NaN;Library._window.Device.Statistics.Fifo=double.PositiveInfinity;
Check(performance(generation,fps,3)==0 && fps[0]==0 && fps[1]==0 && fps[2]==0);
Library._window.Device.Statistics.Fps=30;
Check(performance(generation+1,fps,3)==2 && fps[0]==0);
// Unbounded-present cap: argument checks, no emulation context yet, live, stale.
delegate* unmanaged<long,int,int> presentCap=&Library.EmbeddedSetPresentTargetFps;
Check(presentCap(generation,0)==1 && presentCap(generation,1001)==1);
Check(presentCap(generation,120)==2);Library._emulationContext=new();
Check(presentCap(generation,120)==0 && Library._emulationContext.PresentTargetFps==120);
Check(presentCap(generation+1,60)==2 && Library._emulationContext.PresentTargetFps==120);
Check(set(generation,5)==0 && Library._window.Device.Configuration.AspectRatio==AspectRatio.Stretched);
Check(set(generation,0)==0 && Library._window.Device.Configuration.AspectRatio==AspectRatio.Fixed4x3);
Check(set(generation,6)==1 && Library._window.Device.Configuration.AspectRatio==AspectRatio.Fixed4x3);
Check(set(generation+1,1)==2 && Library._window.Device.Configuration.AspectRatio==AspectRatio.Fixed4x3);
Library.EmbeddedSessions.Stop(generation);Check(set(generation,5)==2 && performance(generation,fps,3)==2 && presentCap(generation,60)==2);
Library.EmbeddedSessions.CancelPrepared(generation);var second=Library.EmbeddedSessions.Prepare();
Check(set(generation,5)==2 && set(second,1)==0);
Library.EmbeddedSessions.CancelPrepared(second);
var region=(nint)NativeMemory.AlignedAlloc(65536,16384);
try {
 delegate* unmanaged<nint,ulong,int> offer=&Library.EmbeddedMemoryOffer;
 delegate* unmanaged<int> withdraw=&Library.EmbeddedMemoryWithdraw;
 delegate* unmanaged<ulong*,int,int> snapshot=&Library.EmbeddedMemorySnapshot;
 Check(offer(region+1,65536)==1);Check(offer(region,65535)==1);
 Check(offer(region,65536)==0);Check(offer(region,65536)==1);
 Check(DonatedMemory.TryAllocate(16384,out var block)&&block==region);
 *(byte*)block=123;
 Check(withdraw()==1 && DonatedMemory.Owns(block));
 Check(offer(region,65536)==1 && DonatedMemory.Owns(block));
 System.Threading.Tasks.Parallel.For(0,100,_=>{if(DonatedMemory.TryWithdraw()||!DonatedMemory.Owns(block))throw new Exception("live region withdrawn");});checks++;
 ulong* stats=stackalloc ulong[3];Check(snapshot(stats,3)==0 && stats[0]==65536 && stats[1]==16384 && stats[2]==1);
 Check(snapshot(stats,2)==1);Check(snapshot(null,3)==1);
 Check(DonatedMemory.Free(block));
 Check(DonatedMemory.TryAllocate(16384,out var reused)&&reused==block && *(byte*)reused==0);
 Check(DonatedMemory.Free(reused));
 var live=Library.EmbeddedSessions.Prepare();Check(withdraw()==2);Check(offer(region,65536)==2);
 Library.EmbeddedSessions.CancelPrepared(live);Check(withdraw()==0);
 Check(snapshot(stats,3)==0 && stats[0]==0 && stats[1]==0 && stats[2]==0);
 Check(offer(region,65536)==0 && withdraw()==0);
 Check(!DonatedMemory.TryAllocate(1,out _));
} finally {NativeMemory.AlignedFree((void*)region);}
// MoltenVK selection: only 0 and 1; the selected framework is the one that must
// exist; once a root is fixed the choice cannot change. Runs last: it fixes
// the process-wide native root.
bool Throws<T>(Action action) where T:Exception {try{action();return false;}catch(T){return true;}}
Check(Throws<ArgumentOutOfRangeException>(()=>EmbeddedNativeLibraries.SelectMoltenVk(2)));
EmbeddedNativeLibraries.SelectMoltenVk(1);Check(EmbeddedNativeLibraries.MoltenVk=="MeloNXMoltenVKStandalone");
var frameworks=System.IO.Directory.CreateTempSubdirectory("melonx-frameworks-").FullName;
foreach(var name in new[]{"MeloNXMoltenVK","MeloNXSDL3","MeloNXAvCodec","MeloNXAvUtil","MeloNXJitSupport"}) {
 System.IO.Directory.CreateDirectory(System.IO.Path.Combine(frameworks,name+".framework"));
 System.IO.File.WriteAllBytes(System.IO.Path.Combine(frameworks,name+".framework",name),new byte[16]);
}
// The standalone framework is missing: nothing is fixed, another choice is still possible.
Check(Throws<System.IO.FileNotFoundException>(()=>EmbeddedNativeLibraries.Configure(frameworks)));
EmbeddedNativeLibraries.SelectMoltenVk(0);Check(EmbeddedNativeLibraries.MoltenVk=="MeloNXMoltenVK");
// Every framework present: the root is fixed before loading (these stand-ins
// are not loadable), so MoltenVK can no longer be switched in this process.
Check(Throws<Exception>(()=>EmbeddedNativeLibraries.Configure(frameworks)));
Check(Throws<InvalidOperationException>(()=>EmbeddedNativeLibraries.SelectMoltenVk(1)));
EmbeddedNativeLibraries.SelectMoltenVk(0);Check(EmbeddedNativeLibraries.MoltenVk=="MeloNXMoltenVK");
Console.WriteLine($"PASS {checks} graphics, FPS snapshot, generation and real donated allocator cases; window double, no gameplay claim.");
}}''')
 result=subprocess.check_output(['dotnet','run','--project',str(w/'test.csproj'),'-c','Release'],text=True,stderr=subprocess.STDOUT,timeout=120)
 print(result)
 out=ROOT/'dist/melonx/display-checks.json';out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(dict(result='passed',summary=result,inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths+['build-utils/melonx/adapt_memory.py',str(Path(__file__).relative_to(ROOT))]},gameplayTested=False),indent=2)+'\n')
