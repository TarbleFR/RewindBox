using System;using System.Threading;using System.Threading.Tasks;using Ryujinx.Graphics.Gpu;using Ryujinx.Graphics.Gpu.Memory;using Ryujinx.Graphics.Gpu.Engine.Threed;using Ryujinx.Graphics.GAL;using Ryujinx.Graphics.Vulkan.Queries;
static class Program {
 static int checks,scenarios;static void Check(bool ok,string msg){checks++;if(!ok)throw new Exception(msg);}
 static int ReportSamples=(2|(0x15<<23));
 static void Main(){
  foreach(bool threaded in new[]{false,true}){
   using var rendererScope=new Session(threaded);var ctx=rendererScope.Context;var channel=new GpuChannel();var state=new DeviceStateWithShadow<ThreedClassState>();var updater=new SemaphoreUpdater(ctx,channel,state);var fifo=new FifoProbe(ctx,channel);
#if CANDIDATE
   ctx.SynchronizeOcclusionReports=true;
#endif
   bool signal=false;ctx.Synchronization.OnSignal=()=>{signal=true;
#if CANDIDATE
    Check(channel.MemoryManager.Values.TryGetValue(0x1000,out var x)&&x==7,"write before signal");
#else
    Check(!channel.MemoryManager.Values.ContainsKey(0x1000),"control must expose late publication");
#endif
   };
   updater.Report(ReportSamples);fifo.Syncpointb(0);Check(signal,"sync signaled");ctx.Renderer.PublishWithoutSync();scenarios++;
#if CANDIDATE
   Check(channel.MemoryManager.Physical.References==1,"report ref returned");
   // Invalidation before a result arrives must prevent a write and release its lease.
   state.State.SemaphoreAddress.Value=0x2000;updater.Report(ReportSamples);channel.MemoryManager.Unmap(0x2000,0x1000);int writes=channel.MemoryManager.Writes;
   ctx.Synchronization.OnSignal=()=>Check(channel.MemoryManager.Writes==writes,"unmapped report skipped");fifo.Syncpointb(0);Check(channel.MemoryManager.Physical.References==1,"unmap released lease");scenarios++;
   channel.MemoryManager.Mapped=true;
   // The synchronous backend must also accept already-ready, zero-draw results.
   var cache=channel.MemoryManager.CounterCache;int release=0,publish=0;
   var immediate=new DeferredCounterReport(v=>publish++,()=>release++);immediate.Complete(null,0);cache.AddOrUpdate(0x5000,immediate);cache.FlushPendingReports();immediate.Flush();Check(publish==1&&release==1,"exactly one ready result/release");scenarios++;
   // Entire/partial half-open invalidation, first entry, misses and size zero.
   foreach(ulong address in new ulong[]{0x3000,0x4000,0x4010}){var e=new DeferredCounterReport(v=>{},()=>{});cache.AddOrUpdate(address,e);}
   Check(cache.FindEvent(0x1000)!=null,"index zero found");Check(cache.FindAndFlush(0x1000),"index zero flushed");Check(!cache.FindAndFlush(0x9000),"missing not flushed");
   cache.MemoryUnmappedHandler(null,new(0x4008,8));Check(cache.FindEvent(0x4000)==null&&cache.FindEvent(0x4010)!=null,"overlap and exclusive end");
   cache.MemoryUnmappedHandler(null,new(0x3000,0));Check(cache.Contains(0x3000),"zero unmap");cache.MemoryUnmappedHandler(null,new(0x3000,0x1011));Check(!cache.Contains(0x3000)&&!cache.Contains(0x4010),"nonexact upper bound");scenarios++;
   var late=new DeferredCounterReport(v=>throw new Exception("write after teardown"),()=>release++);cache.AddOrUpdate(0x8000,late);cache.CancelPendingReports();late.Complete(null,88);late.Flush();Check(release==2,"teardown release");scenarios++;
   var failed=new DeferredCounterReport(v=>{},()=>release++);failed.Attach(new FailedCounter());bool rejected=false;try{failed.Flush();}catch(InvalidOperationException){rejected=true;}Check(rejected,"missing callback withholds syncpoint");failed.Dispose();scenarios++;
#endif
  }
#if CANDIDATE
  foreach(bool threaded in new[]{false,true}){using var session=new Session(threaded);var c=session.Context;c.SynchronizeOcclusionReports=true;var first=new GpuChannel();var second=new GpuChannel();var u1=new SemaphoreUpdater(c,first,new());var u2=new SemaphoreUpdater(c,second,new());u1.Report(ReportSamples);u2.Report(ReportSamples);int signal=0;c.Synchronization.OnSignal=()=>{Check(first.MemoryManager.Values.TryGetValue(0x1000,out var x)&&x==7,"first channel published");Check(second.MemoryManager.Values.TryGetValue(0x1000,out var y)&&y==14,"other memory/channel published before sync");signal++;};new FifoProbe(c,first).Syncpointb(0);Check(signal==1&&first.MemoryManager.Physical.References==1&&second.MemoryManager.Physical.References==1,"cross-channel publication and lease release");scenarios++;}
  // Exercise the actual queue with an event already dequeued by its consumer.
  {var pipe=new Ryujinx.Graphics.Vulkan.PipelineFull();using var queue=new CounterQueue(new Ryujinx.Graphics.Vulkan.VulkanRenderer(),default,pipe,CounterType.SamplesPassed);int completed=0;BufferedQuery.AwaitEntered.Reset();queue.QueueReport((s,v)=>Interlocked.Increment(ref completed),1,1,false);Check(BufferedQuery.AwaitEntered.Wait(5000),"consumer holds in-flight event");var flush=Task.Run(()=>queue.Flush(true));Check(completed==0,"unsubmitted query pending");lock(pipe.Copies){foreach(var q in pipe.Copies)q.Submit();}Check(flush.Wait(5000),"blocking queue flush completes outside lock");Check(completed==1,"in-flight callback before blocking flush returns");scenarios++;}
  {var pipe=new Ryujinx.Graphics.Vulkan.PipelineFull();using var queue=new CounterQueue(new Ryujinx.Graphics.Vulkan.VulkanRenderer(),default,pipe,CounterType.SamplesPassed);BufferedQuery.ForceTimeout=true;int completed=0;var evt=queue.QueueReport((s,v)=>completed++,1,1,false);evt.Flush();Check(evt.Invalid&&completed==0,"timed-out query not published as a valid value");BufferedQuery.ForceTimeout=false;scenarios++;}
  // Compare invalidation against an interval oracle, including first/last,
  // absent upper bounds and a report crossing a page boundary.
  for(int seed=0;seed<256;seed++){var cache=new CounterCache();var rng=new Random(seed);var events=new DeferredCounterReport[64];for(int i=0;i<events.Length;i++){events[i]=new(v=>{},()=>{});cache.AddOrUpdate((ulong)(i*32),events[i]);}ulong start=(ulong)rng.Next(0,2048),size=(ulong)rng.Next(0,2048);cache.MemoryUnmappedHandler(null,new(start,size));for(int i=0;i<events.Length;i++){ulong a=(ulong)(i*32);bool overlap=size>0&&a<start+size&&start<a+16;Check(events[i].Invalid==overlap,"interval oracle");}cache.CancelPendingReports();scenarios++;}
  // Deterministic submit/result gate on separate workers, no timing assumptions.
  foreach(bool threaded in new[]{false,true}){
   using var session=new Session(threaded);var c=session.Context;c.SynchronizeOcclusionReports=true;var ch=new GpuChannel();var st=new DeviceStateWithShadow<ThreedClassState>();var u=new SemaphoreUpdater(c,ch,st);var f=new FifoProbe(c,ch);int signals=0;c.Synchronization.OnSignal=()=>Interlocked.Increment(ref signals);
   c.Renderer.AllowResults.Reset();u.Report(ReportSamples);var task=Task.Run(()=>f.Syncpointb(0));Check(c.Renderer.Submitted.Wait(5000),"submitted before wait");Check(Volatile.Read(ref signals)==0&&ch.MemoryManager.Writes==0,"no early publish/signal");c.Renderer.AllowResults.Set();Check(task.Wait(5000),"no GPU/render deadlock");Check(signals==1&&ch.MemoryManager.Writes==1,"late write and signal");scenarios++;
  }
#endif
  Check(BufferedQuery.Outstanding==0,"query pools released");Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new {checks,scenarios,controlLatePublication=
#if CANDIDATE
false
#else
true
#endif
}));
 }
 sealed class Session:IDisposable{public GpuContext Context;public Session(bool t){Context=new(t);}public void Dispose()=>Context.Renderer.Dispose();}
 sealed class FailedCounter:ICounterEvent{public bool Invalid{get;set;}public bool ReserveForHostAccess()=>false;public void Flush(){}public void Dispose(){}}
}
