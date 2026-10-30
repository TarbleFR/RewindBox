using System;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Gpu.Engine.Threed;
using Ryujinx.Graphics.Gpu.Engine.Types;
using Ryujinx.Graphics.OpenGL.Queries;
using VkPipeline=Ryujinx.Graphics.Vulkan.PipelineFull;
using GlPipeline=Ryujinx.Graphics.OpenGL.Pipeline;
static class Program {
 static int checks,scenarios,lateSyncReproduced,falseHostReproduced,leakedReservationReproduced;
#if CANDIDATE
 const bool Candidate=true;
#else
 const bool Candidate=false;
#endif
 static void Check(bool ok,string why){checks++;if(!ok)throw new Exception(why);}
 sealed class Session:IDisposable{
  public DirectRenderer Native;public ThreadedRenderer Threaded;public GpuContext Context;
  public Session(bool threaded,IPipeline pipeline=null){Native=new(pipeline??new VkPipeline());Threaded=threaded?new(Native):null;Context=new((IRenderer)Threaded??Native);}
  public void Drain()=>Context.Renderer.BackgroundContextAction(()=>{});
  public void Dispose(){Threaded?.Dispose();}
 }
 sealed class NativeCounter:ICounterEvent{
  public bool Invalid{get;set;}public Action OnFlush;public int Flushes;public bool ReserveForHostAccess()=>false;public void Flush(){Flushes++;OnFlush?.Invoke();}public void Dispose(){}
 }
 static void Signal(GpuContext c,bool threed){if(threed)new ThreedProbe(c).IncrementSyncpoint(unchecked((int)0xABCD0007));else new FifoProbe(c).Syncpointb(0);}
 static void SyncCases(){
  foreach(bool threaded in new[]{false,true})foreach(bool threed in new[]{false,true})foreach(string state in new[]{"ready","delayed","invalid","failed","none","off"})foreach(ulong value in new ulong[]{0,91}){
   using var s=new Session(threaded);var c=s.Context;c.SynchronizeOcclusionReports=state!="off";
   int writes=0,releases=0;ulong visible=123;bool submitted=false;var cache=new CounterCache();
   s.Native.OnSubmit=()=>submitted=true;
   DeferredCounterReport report=null;
   if(state!="none"){
    report=new(v=>{visible=v;writes++;},()=>releases++);
    var counter=new NativeCounter();counter.OnFlush=()=>{Check(submitted,"query submitted before synchronous report wait");if(state!="failed")report.Complete(null,value);};
    report.Attach(counter);cache.AddOrUpdate(0x1000,report);c.TrackCounterReports(cache);
    if(state=="ready")report.Complete(null,value);
    if(state=="invalid")report.Invalid=true;
   }
   bool drain=state!="off"&&(!threed||Candidate),valid=state is "ready" or "delayed";
   c.Synchronization.OnSignal=id=>{Check(id==7,"syncpoint id masks high bits");if(valid&&drain)Check(writes==1&&visible==value,"guest report visible before syncpoint");else Check(writes==0,"no unexpected guest report");};
   bool threw=false;try{Signal(c,threed);}catch(InvalidOperationException){threw=true;}
   Check(threw==(drain&&state=="failed"),"failed report withholds syncpoint");
   Check(c.Synchronization.Signals==(threw?0:1),"signal count");
   if(valid&&!drain&&state!="off"){lateSyncReproduced++;Check(!Candidate,"only baseline misses 3D publication");}
   Check(c.Syncs.Count==1,"one host submission per syncpoint");
   Check(c.Syncs[0]==(drain&&state!="none"?HostSyncFlags.StrictSyncpoint|HostSyncFlags.Force:HostSyncFlags.StrictSyncpoint),"force only pending enabled reports");
   s.Drain();Check(s.Native.Polls==(threed&&!threw?1:0),"preserve original counter polling");
   if(report!=null){report.Dispose();Check(releases==1,"report lease released exactly once");}
   Check(c.Sequence==(threed||!threw?1:0),"retain sequence ordering");scenarios++;
  }
  foreach(bool threaded in new[]{false,true})foreach(bool threed in new[]{false,true}){
   using var s=new Session(threaded);var c=s.Context;c.SynchronizeOcclusionReports=true;int writes=0,releases=0;
   for(int i=0;i<3;i++){var cache=new CounterCache();var r=new DeferredCounterReport(v=>writes++,()=>releases++);r.Complete(null,(ulong)i);cache.AddOrUpdate(0x1000,r);c.TrackCounterReports(cache);}
   c.Synchronization.OnSignal=_=>Check(writes==((Candidate||!threed)?3:0),"all tracked channels visible");Signal(c,threed);
   if(!Candidate&&threed){lateSyncReproduced++;foreach(var cache in c._counterReportCaches)cache.CancelPendingReports();}
   Check(releases==3,"cross-channel leases");scenarios++;
  }
  // A delayed native completion gates the actual report Flush, never a timer.
  foreach(bool threaded in new[]{false,true})foreach(bool threed in new[]{false,true}){
   using var s=new Session(threaded);var c=s.Context;c.SynchronizeOcclusionReports=true;
   using var entered=new ManualResetEventSlim();using var allow=new ManualResetEventSlim();int writes=0;
   var report=new DeferredCounterReport(v=>writes++,()=>{});report.Attach(new NativeCounter{OnFlush=()=>{entered.Set();if(!allow.Wait(5000))throw new Exception("completion gate timed out");report.Complete(null,3);}});
   var cache=new CounterCache();cache.AddOrUpdate(0x1000,report);c.TrackCounterReports(cache);
   var task=Task.Run(()=>Signal(c,threed));
   if(Candidate||!threed){Check(entered.Wait(5000),"report wait reached");Check(c.Synchronization.Signals==0&&writes==0,"late completion cannot publish or signal early");allow.Set();Check(task.Wait(5000),"syncpoint released after completion");Check(c.Synchronization.Signals==1&&writes==1,"one completed report");}
   else {Check(task.Wait(5000),"baseline increment completes early");Check(!entered.IsSet&&c.Synchronization.Signals==1&&writes==0,"baseline bypassed report wait");lateSyncReproduced++;}
   report.Dispose();scenarios++;
  }
 }
 static ConditionalRenderEnabled Decide(GpuContext c,MemoryManager m,Condition condition=Condition.ResultNonZero)=>ConditionalRendering.GetRenderEnable(c,m,new GpuVa(0x1000),condition);
 static ConditionalRenderEnabled DecideAfterCreation(Session s,MemoryManager memory,ManualResetEventSlim allow) {
  if(allow==null)return Decide(s.Context,memory);
  var task=Task.Run(()=>Decide(s.Context,memory));
  Check(SpinWait.SpinUntil(()=>Volatile.Read(ref s.Threaded.Queued)>0,5000),"conditional queued behind creation");
  allow.Set();Check(task.Wait(5000),"conditional unblocked after creation");return task.Result;
 }
 static void ConditionalCases(){
  foreach(bool threaded in new[]{false,true})foreach(bool created in new[]{false,true})foreach(ulong value in new ulong[]{0,29}){
   var vk=new VkPipeline();using var s=new Session(threaded,vk);var memory=new MemoryManager();bool submitted=false;using var allow=threaded&&!created?new ManualResetEventSlim():null;if(allow!=null)s.Threaded.EnqueueAction(()=>{if(!allow.Wait(5000))throw new Exception("creation gate");});
   vk.OnFlush=()=>submitted=true;
   var native=new CounterQueueEvent{Publish=()=>{Check(submitted,"backend flush precedes CPU visibility");memory.Values[0x1000]=value;}};
   ICounterEvent evt=native;
   if(threaded){if(created)evt=new ThreadedCounterEvent(s.Threaded,CounterType.SamplesPassed,true){Base=native};else{s.Native.CreateCounter=(t,cb,r)=>{if(r)native.ReserveForHostAccess();return native;};evt=s.Threaded.ReportCounter(CounterType.SamplesPassed,(a,b)=>{},1,false);}}
   memory.CounterCache.AddOrUpdate(0x1000,evt);
   var result=DecideAfterCreation(s,memory,allow);s.Drain();
   if(threaded&&!Candidate){Check(result==ConditionalRenderEnabled.Host,"baseline incorrectly claims host predicate");Check(native.Flushes==0&&memory.Reads==0,"baseline bypasses CPU condition");Check(native.Reserved,"baseline leaked backend reservation");falseHostReproduced++;leakedReservationReproduced++;native.ReleaseHostAccess();}
   else {Check(result==(value==0?ConditionalRenderEnabled.False:ConditionalRenderEnabled.True),"actual zero/nonzero guest visibility decision");Check(native.Flushes==1&&memory.Reads==1,"CPU comparison consumes available report");Check(!native.Reserved&&native.ReserveCalls==0,"unsupported backend acquired no reservation");}
   Check(vk.Flushes==1,"one backend conditional flush");scenarios++;
  }
  // Eligible OpenGL keeps its real host path and owns a balanced reservation.
  foreach(bool ready in new[]{false,true})foreach(bool created in new[]{false,true}){
   using var s=new Session(true,new GlPipeline());var memory=new MemoryManager();using var allow=!created?new ManualResetEventSlim():null;if(allow!=null)s.Threaded.EnqueueAction(()=>{if(!allow.Wait(5000))throw new Exception("GL creation gate");});var native=new CounterQueueEvent{Ready=ready,Publish=()=>memory.Values[0x1000]=17};
   ThreadedCounterEvent evt;
   if(created)evt=new(s.Threaded,CounterType.SamplesPassed,true){Base=native};else{s.Native.CreateCounter=(t,cb,r)=>{if(r)native.ReserveForHostAccess();return native;};evt=(ThreadedCounterEvent)s.Threaded.ReportCounter(CounterType.SamplesPassed,(a,b)=>{},1,false);}
   memory.CounterCache.AddOrUpdate(0x1000,evt);var result=DecideAfterCreation(s,memory,allow);s.Drain();
   // A baseline reservation made before Base exists bypasses its readiness check.
   bool host=!ready||(!Candidate&&!created);
   Check(result==(host?ConditionalRenderEnabled.Host:ConditionalRenderEnabled.True),"supported backend or expired-query fallback");
   if(host&&ready){Check(!Candidate&&!created&&!native.Reserved,"baseline ignored backend expiration result");falseHostReproduced++;}
   else if(host){Check(native.Reserved,"host backend owns reservation");s.Context.Renderer.Pipeline.EndHostConditionalRendering();s.Drain();Check(!native.Reserved&&native.ReleaseCalls==1,"end condition releases once");}
   else Check(!native.Reserved&&native.Flushes==1,"expired event CPU fallback has no reservation");
   scenarios++;
  }
  // Ineligible one-event and two-event comparisons retain the false/flush path.
  foreach(string kind in new[]{"nonzeroConstant","notClear","otherType","pairEqual","pairUnequal","deferred"}){
   var vk=new VkPipeline();using var s=new Session(true,vk);var memory=new MemoryManager();
   var first=new CounterQueueEvent{Publish=()=>memory.Values[0x1000]=5};
   ICounterEvent evt=new ThreadedCounterEvent(s.Threaded,kind=="otherType"?CounterType.PrimitivesGenerated:CounterType.SamplesPassed,kind!="notClear"){Base=first};
   if(kind=="deferred"){var report=new DeferredCounterReport(v=>memory.Values[0x1000]=v,()=>{});report.Complete(null,5);evt=report;}
   memory.CounterCache.AddOrUpdate(0x1000,evt);Condition condition=Condition.ResultNonZero;
   if(kind=="nonzeroConstant"){memory.Values[0x1010]=5;condition=Condition.Equal;}
   if(kind.StartsWith("pair")){var second=new CounterQueueEvent{Publish=()=>memory.Values[0x1010]=kind=="pairEqual"?5UL:7UL};memory.CounterCache.AddOrUpdate(0x1010,new ThreadedCounterEvent(s.Threaded,CounterType.SamplesPassed,true){Base=second});condition=Condition.Equal;}
   var result=Decide(s.Context,memory,condition);s.Drain();Check(result==(kind=="pairUnequal"?ConditionalRenderEnabled.False:ConditionalRenderEnabled.True),"ineligible comparison retains CPU decision");Check(first.ReserveCalls==0,"ineligible path does not reserve");Check(vk.Flushes==1,"ineligible path flushes once");scenarios++;
  }
  // The actual InvokeCommand rethrows a render failure instead of reading a
  // default ResultBox value and treating failure as ordinary CPU fallback.
  {
   var error=new InvalidOperationException("native conditional failure");var vk=new VkPipeline{OnFlush=()=>throw error};using var s=new Session(true,vk);var memory=new MemoryManager();var native=new CounterQueueEvent();memory.CounterCache.AddOrUpdate(0x1000,new ThreadedCounterEvent(s.Threaded,CounterType.SamplesPassed,true){Base=native});
   Exception caught=null;ConditionalRenderEnabled? decision=null;try{decision=Decide(s.Context,memory);}catch(Exception e){caught=e;}
   if(Candidate){Check(ReferenceEquals(caught,error)&&decision==null,"original render error propagated before decision");Check(memory.Reads==0&&native.Flushes==0&&!native.Reserved,"failure cannot consume default false");}
   else{Check(decision==ConditionalRenderEnabled.Host,"baseline claims host before command failure");try{s.Drain();}catch(Exception e){caught=e;}Check(ReferenceEquals(caught,error),"later barrier observes original error");falseHostReproduced++;if(native.Reserved)native.ReleaseHostAccess();}
   scenarios++;
  }
 }
 static void Main(){SyncCases();ConditionalCases();Check(Candidate?lateSyncReproduced==0:lateSyncReproduced>0,"3D regression reproduction");Check(Candidate?falseHostReproduced==0:falseHostReproduced>0,"threaded regression reproduction");Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new {checks,scenarios,lateSyncReproduced,falseHostReproduced,leakedReservationReproduced}));}
}
