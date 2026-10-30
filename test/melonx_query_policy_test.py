#!/usr/bin/env python3
"""Execute AutoFlushCounter and production arena initialization with injected boundaries."""
from pathlib import Path
import hashlib,importlib,json,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
def method(text,signature):
 start=text.index(signature);i=text.index('{',start)+1;depth=1
 while depth:
  if text[i]=='{':depth+=1
  if text[i]=='}':depth-=1
  i+=1
 return text[start:i]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
reports={};compiled={}
with tempfile.TemporaryDirectory(prefix='melonx-policy-') as temp:
 for variant in ('control','candidate'):
  work=Path(temp)/variant;src=work/'engine';src.mkdir(parents=True)
  for mod,contract in [('adapt_query_batching','query-batching-adapter-contract'),('adapt_jit_single_attempt','jit-single-attempt-adapter-contract')]:
   spec=json.loads((ROOT/'build-utils/melonx'/f'{contract}.json').read_text())
   for p,h in spec['before'].items():
    assert sha(SOURCE/p)==h,p
    t=src/p;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/p,t)
   if variant=='candidate':importlib.import_module(mod).apply(src)
  text=(src/'src/Ryujinx.Graphics.Vulkan/AutoFlushCounter.cs').read_text()
  # Only the stopwatch is doubled, so all time thresholds run deterministically.
  (work/'AutoFlushCounter.cs').write_text('using Stopwatch = TestClock;\n'+text)
  text=(src/'src/Ryujinx.Cpu/LightningJit/Cache/DualMappedNoWxCache.cs').read_text()
  fields='''public static bool Txm=true;static ulong DefaultCacheSize=>Txm ? 512UL<<20 : 1024UL<<20;static Allocator _sharedCacheAlloc;static object _arenaGate=new();static bool _arenaAttempted;public static void Reset(){_sharedCacheAlloc=null;_arenaAttempted=false;Allocator.Calls=0;Allocator.Refuse=false;Allocator.FailStage=0;Allocator.NativeState=-1;}public static ulong Size=>_sharedCacheAlloc?.Size??0;'''
  (work/'Arena.cs').write_text('using System;class Arena {'+fields+method(text,'public static void InitMemoryCache()')+'}')
  query_path=SOURCE/'src/Ryujinx.Graphics.Vulkan/Queries/BufferedQuery.cs'
  query_text=query_path.read_text() if variant=='control' else importlib.import_module('adapt_occlusion_reports').edits(SOURCE)[query_path]
  query_methods='\n'.join(method(query_text,s)for s in ['private bool WaitingForValue(', 'public bool TryGetResult('])
  (work/'QueryRead.cs').write_text('using System;using System.Runtime.InteropServices;sealed class QueryRead:IDisposable {const ulong HighMask=0xFFFFFFFF00000000;readonly bool _result32Bit;readonly long _defaultValue;readonly nint _bufferMap;public QueryRead(bool small){_result32Bit=small;_defaultValue=small?0xFFFFFFFE:unchecked((long)0xFFFFFFFEFFFFFFFE);_bufferMap=Marshal.AllocHGlobal(8);}public void Set(long value)=>Marshal.WriteInt64(_bufferMap,value);public void Dispose()=>Marshal.FreeHGlobal(_bufferMap);'+query_methods+'}')
  pipeline_path=SOURCE/'src/Ryujinx.Graphics.Vulkan/PipelineFull.cs'
  pipeline_text=pipeline_path.read_text() if variant=='control' else importlib.import_module('adapt_occlusion_reports').edits(SOURCE)[pipeline_path]
  host=method(pipeline_text,'public bool TryHostConditionalRendering(ICounterEvent value, ulong compare, bool isEqual)')
  guest=method((SOURCE/'src/Ryujinx.Graphics.Gpu/Engine/Threed/ConditionalRendering.cs').read_text(),'private static ConditionalRenderEnabled CounterNonZero(').replace('private static','public static')
  (work/'Conditional.cs').write_text('''using System;using Ryujinx.Graphics.GAL;using Ryujinx.Graphics.Vulkan.Queries;
namespace Ryujinx.Graphics.GAL {enum CounterType{SamplesPassed}interface ICounterEvent{bool ReserveForHostAccess();void Flush();}}
namespace Ryujinx.Graphics.Vulkan.Queries {class CounterQueueEvent:ICounterEvent {public CounterType Type=CounterType.SamplesPassed;public bool ClearCounter=true;public int Reserves,Flushes;public Action Publish;public bool ReserveForHostAccess(){Reserves++;return true;}public void Flush(){Flushes++;Publish?.Invoke();}}}
class Caps {public bool SupportsConditionalRendering;}
class ConditionalProbe {public class Device{public Caps Capabilities=new();}public Device Gd=new();CounterQueueEvent _activeConditionalRender;public int Submits;void FlushPendingQuery()=>Submits++;
'''+host+'''}
enum ConditionalRenderEnabled{False,True,Host}
class MemoryManager {public ulong Value;public CounterQueueEvent Event;public MemoryManager CounterCache=>this;public ICounterEvent FindEvent(ulong a)=>Event;public T Read<T>(ulong a,bool tracked)=>(T)(object)Value;}
class GpuContext {public class RendererStub{public ConditionalProbe Pipeline=new();}public RendererStub Renderer=new();}
class GuestConditional {'''+guest+'}')
  (work/'Boundaries.cs').write_text('''using System;using System.Threading;
static class TestClock {public static long Frequency=1000000,Now;public static long GetTimestamp()=>Now;}
namespace Ryujinx.Common.Logging {enum LogClass{Gpu}class Log{public void PrintMsg(LogClass c,string s){}}static class Logger{public static Log Debug;}}
namespace Ryujinx.Graphics.Vulkan {class VulkanRenderer{public bool RelaxQueryFlushing;public Sync SyncManager=new();}class Sync{public long Wait;public long GetAndResetWaitTicks()=>Wait;}}
static class DualMappedMemory {public static ulong RequestedArenaSize;}
class Allocator {public static int Calls;public static bool Refuse;public static int FailStage,NativeState=-1;public ulong Size;public Allocator(ulong size){Interlocked.Increment(ref Calls);for(int stage=0;stage<5;stage++){NativeState=stage;if(Refuse&&FailStage==stage)throw new Exception("injected native stage "+stage);}Size=size;}}
''')
  program='''using System;using System.Threading.Tasks;using Ryujinx.Graphics.Vulkan;
class Program {
 static int checks;static void Check(bool v,string s){checks++;if(!v)throw new Exception(s);}
 static int Scenario(bool relaxed){var renderer=new VulkanRenderer{RelaxQueryFlushing=relaxed};var c=new AutoFlushCounter(renderer);int submissions=0;ulong draw=0;c.RegisterFlush(0);for(int i=1;i<=1024;i++){draw++;bool flush=c.RegisterPendingQuery();if(i%16==0)flush|=c.ShouldFlushAttachmentChange(draw);if(flush){submissions++;c.RegisterFlush(draw);}}Check(c.ShouldFlushQuery()==(1024%128!=0||!relaxed),"pending query predicate");return submissions;}
 static void Main(){
 foreach(bool cap in new[]{false,true})foreach(ulong result in new[]{0UL,7UL}){var memory=new MemoryManager{Value=123};var evt=new Ryujinx.Graphics.Vulkan.Queries.CounterQueueEvent();evt.Publish=()=>memory.Value=result;memory.Event=evt;var context=new GpuContext();context.Renderer.Pipeline.Gd.Capabilities.SupportsConditionalRendering=cap;var decision=GuestConditional.CounterNonZero(context,memory,0);
#if CANDIDATE
 Check(decision==(result==0?ConditionalRenderEnabled.False:ConditionalRenderEnabled.True),"actual guest visibility comparison");Check(evt.Reserves==0&&evt.Flushes==1&&context.Renderer.Pipeline.Submits==1,"no unencoded host condition or leaked query reservation");
#else
 Check(decision==ConditionalRenderEnabled.Host&&evt.Flushes==0&&evt.Reserves==1,"control bypasses guest comparison without encoding GPU condition");
#endif
 }
 foreach(bool small in new[]{false,true}){using var q=new QueryRead(small);q.Set(small?0xFFFFFFFE:unchecked((long)0xFFFFFFFEFFFFFFFE));Check(!q.TryGetResult(out _),"sentinel pending");foreach(long n in new[]{0L,1L,7L,long.MaxValue}){q.Set(n);Check(q.TryGetResult(out var got)&&got==n,"complete counter available");}q.Set(unchecked((long)0xFFFFFFFE00000007));
#if CANDIDATE
 Check(q.TryGetResult(out _)==small,"partial 64-bit result rejected");
#else
 Check(q.TryGetResult(out _),"control accepts partial high word");
#endif
 }
 int normal=Scenario(false),relaxed=Scenario(true);
#if CANDIDATE
 Check(relaxed<normal,"fewer submissions");Check(normal==64&&relaxed==8,"bounded synthetic submission counts");
#else
 Check(normal==relaxed&&normal==64,"control has no batching policy");
#endif
 var r=new VulkanRenderer{RelaxQueryFlushing=true};var a=new AutoFlushCounter(r);a.RegisterFlush(0);Check(!a.ShouldFlushQuery(),"initial no pending");a.RegisterPendingQuery();Check(a.ShouldFlushQuery(),"explicit query reads still submit");TestClock.Now=10001;Check(a.ShouldFlushAttachmentChange(12),"attachment time budget retained");a.RegisterFlush(12);Check(!a.ShouldFlushQuery(),"flush resets pending");r.SyncManager.Wait=100000;for(int i=0;i<20;i++)a.Present();TestClock.Now+=2000;Check(a.ShouldFlushDraw(24),"fast draw time budget retained");
 foreach(bool txm in new[]{false,true})foreach(ulong hint in new[]{0UL,1024UL<<20}){Arena.Reset();Arena.Txm=txm;DualMappedMemory.RequestedArenaSize=hint;Arena.InitMemoryCache();Arena.InitMemoryCache();Check(Allocator.Calls==1,"one successful arena");Check(Arena.Size==Math.Max(txm?512UL<<20:1024UL<<20,hint),"mapped arena budget");}
#if CANDIDATE
 // Fault injection after arbitrary native allocation stages: every opaque
 // failure is terminal, even if a caller attempts another initialization.
 foreach(bool txm in new[]{false,true})foreach(ulong hint in new[]{0UL,1024UL<<20})for(int stage=0;stage<5;stage++){
 Arena.Reset();Arena.Txm=txm;DualMappedMemory.RequestedArenaSize=hint;Allocator.Refuse=true;Allocator.FailStage=stage;try{Arena.InitMemoryCache();}catch(Exception){}Allocator.Refuse=false;try{Arena.InitMemoryCache();}catch(InvalidOperationException){}Check(Allocator.Calls==1&&Arena.Size==0&&Allocator.NativeState==stage,"no second mapping on failed native state");}
 Arena.Reset();Arena.Txm=true;DualMappedMemory.RequestedArenaSize=1024UL<<20;Parallel.For(0,64,i=>Arena.InitMemoryCache());Check(Allocator.Calls==1,"concurrent arena once");
#endif
 Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{checks,normalSubmissions=normal,batchedSubmissions=relaxed}));}
}'''
  # A flush at the final 16-query boundary means no pending query in both traces.
  program=program.replace('Check(c.ShouldFlushQuery()==(1024%128!=0||!relaxed),"pending query predicate");','Check(!c.ShouldFlushQuery(),"pending query predicate");')
  (work/'Program.cs').write_text(program)
  (work/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><EnableDefaultCompileItems>false</EnableDefaultCompileItems><NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers><DefineConstants>'+('CANDIDATE'if variant=='candidate'else'CONTROL')+'</DefineConstants></PropertyGroup><ItemGroup><Compile Include="*.cs" /></ItemGroup></Project>')
  (work/'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}');(work/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
  compiled[variant]={p.name:sha(p)for p in work.glob('*.cs')}
  r=subprocess.run([os.environ.get('DOTNET','dotnet'),'run','--project',str(work),'-c','Release'],cwd=work,capture_output=True,text=True,timeout=90)
  if r.returncode:print(r.stdout,r.stderr);r.check_returncode()
  reports[variant]=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('{')));print(variant,reports[variant])
inputs=['build-utils/melonx/adapt_occlusion_reports.py','build-utils/melonx/occlusion-adapter-contract.json','test/melonx_query_policy_test.py','build-utils/melonx/adapt_query_batching.py','build-utils/melonx/query-batching-adapter-contract.json','build-utils/melonx/adapt_jit_single_attempt.py','build-utils/melonx/jit-single-attempt-adapter-contract.json']
p=ROOT/'dist/melonx/query-policy-checks.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(dict(result='passed',physicalDeviceTested=False,nativeMappingAndClockDoubled=True,reports=reports,compiledSourceInputs=compiled,inputs={p:sha(ROOT/p)for p in inputs}),indent=2)+'\n')
