using System;
using System.Collections.Generic;
using System.Threading;
using System.Collections.Concurrent;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Vulkan;
using Ryujinx.Graphics.Vulkan.Queries;
namespace Silk.NET.Vulkan { struct Device {} struct CommandBuffer {} }
namespace Ryujinx.Graphics.GAL {
 public enum CounterType { SamplesPassed, PrimitivesGenerated, TransformFeedbackPrimitivesWritten }
 public interface ICounterEvent : IDisposable { bool Invalid{get;set;} bool ReserveForHostAccess(); void Flush(); }
}
namespace Ryujinx.Graphics.Vulkan {
 class DisposableBuffer {} class Auto<T> {}
 class PipelineFull { public ulong DrawCount; public List<BufferedQuery> Copies=new(); }
 class VulkanRenderer {
  public bool IsAmdWindows;
  public bool RelaxQueryFlushing;
  public SyncBoundary SyncManager=new();
 }
 class SyncBoundary { public long GetAndResetWaitTicks()=>0; }
}
namespace Ryujinx.Common.Logging {
 enum LogClass { Gpu } class Log { public void PrintMsg(LogClass c,string s){} }
 static class Logger { public static Log Debug; }
}
namespace Ryujinx.Graphics.Vulkan.Queries {
 class BufferedQuery : IDisposable {
  readonly PipelineFull pipeline; readonly ManualResetEventSlim ready=new();
  public bool Freed; long value; public static bool ForceTimeout; public static int Outstanding; public static ManualResetEventSlim AwaitEntered=new();
  public BufferedQuery(VulkanRenderer g,Silk.NET.Vulkan.Device d,PipelineFull p,CounterType t,bool w){pipeline=p;Interlocked.Increment(ref Outstanding);}
  public Auto<DisposableBuffer> GetBuffer()=>new();
  public void Begin(int? reset){ready.Reset();value=0;}
  public void End(bool result){if(result) {lock(pipeline.Copies)pipeline.Copies.Add(this);} else{value=0;ready.Set();}}
  public void Reset(){End(false);Begin(null);}
  public void PoolReset(Silk.NET.Vulkan.CommandBuffer c,int s){}
  public bool TryGetResult(out long v){v=value;return ready.IsSet;}
  public long AwaitResult(AutoResetEvent e=null){AwaitEntered.Set();if(ForceTimeout)return long.MinValue;if(!ready.Wait(TimeSpan.FromSeconds(5)))return long.MinValue;return value;}
  public void Submit(){value=7;ready.Set();}
  public void Dispose(){if(Freed)throw new Exception("double query free");Freed=true;ready.Dispose();Interlocked.Decrement(ref Outstanding);}
 }
}
namespace Ryujinx.Graphics.Gpu.Memory {
 class UnmapEventArgs : EventArgs {public ulong Address,Size;public UnmapEventArgs(ulong a,ulong s){Address=a;Size=s;}}
 class PhysicalStub {public int References=1;public void IncrementReferenceCount()=>Interlocked.Increment(ref References);public void DecrementReferenceCount()=>Interlocked.Decrement(ref References);}
 partial class MemoryManager {
  readonly object _pageTable=new(); public readonly CounterCache CounterCache=new(); public PhysicalStub Physical=new();
  public Dictionary<ulong,ulong> Values=new();public int Writes;public bool Mapped=true;
  public bool IsMapped(ulong a)=>Mapped;bool IsMappedOnPhysical(ulong a)=>Mapped;
  public void Write<T>(ulong a,T v)where T:unmanaged {Values[a]=System.Runtime.InteropServices.MemoryMarshal.Read<ulong>(System.Runtime.InteropServices.MemoryMarshal.AsBytes(System.Runtime.InteropServices.MemoryMarshal.CreateSpan(ref v,1)));Writes++;}
  public void Unmap(ulong a,ulong s){lock(_pageTable){CounterCache.MemoryUnmappedHandler(this,new(a,s));Mapped=false;}}
 }
}
namespace Ryujinx.Graphics.Gpu {
 [Flags] enum HostSyncFlags {StrictSyncpoint=3,Force=4}
 class StateAddress {public ulong Value=0x1000;public ulong Pack()=>Value;}
 class ThreedClassState {public StateAddress SemaphoreAddress=new();public int SemaphorePayload=123;}
 class DeviceStateWithShadow<T> where T:new(){public T State=new();}
 class Textures {public float RenderTargetScale=1;public void RefreshModifiedTextures(){}}
 class GpuChannel {public MemoryManager MemoryManager=new();public Textures TextureManager=new();}
 class SyncBoundary {public Action OnSignal;public void IncrementSyncpoint(uint id)=>OnSignal?.Invoke();public void WaitOnSyncpoint(uint i,uint t,TimeSpan s){} }
 partial class GpuContext {
  public bool SynchronizeOcclusionReports;internal readonly HashSet<CounterCache> _counterReportCaches=new();
  public FakeRenderer Renderer;public SyncBoundary Synchronization=new();
  public GpuContext(bool threaded){Renderer=new(threaded);}
  public void AdvanceSequence(){} public ulong GetTimestamp()=>99;
  public void CreateHostSyncIfNeeded(HostSyncFlags flags)=>Renderer.CreateSync();
  internal void TrackCounterReports(CounterCache c)=>_counterReportCaches.Add(c);
 }
 enum SyncpointbOperation {Wait,Incr}
 class FifoState {public SyncpointbOperation SyncpointbOperation=SyncpointbOperation.Incr;public int SyncpointbSyncptIndex=1,SyncpointaPayload;}
 partial class FifoProbe {public GpuContext _context;public GpuChannel _parent;public DeviceStateWithShadow<FifoState> _state=new();public FifoProbe(GpuContext c,GpuChannel p){_context=c;_parent=p;}}
 class FakeRenderer : IDisposable {
  readonly bool threaded;readonly BlockingCollection<Action> commands=new();readonly Thread render;
  readonly PipelineFull pipeline=new();readonly CounterQueue queue;
  public readonly ManualResetEventSlim Submitted=new(),AllowResults=new(true); public int Submissions;
  class Proxy : ICounterEvent {
   public ICounterEvent Base;public bool Invalid{get;set;}public bool ReserveForHostAccess()=>false;public void Dispose(){}public void Flush(){SpinWait.SpinUntil(()=>Base!=null,5000);Base.Flush();}
  }
  public FakeRenderer(bool t){threaded=t;queue=new(new VulkanRenderer(),default,pipeline,CounterType.SamplesPassed);if(t){render=new(()=>{foreach(var a in commands.GetConsumingEnumerable())a();});render.Start();}}
  void Queue(Action a){if(threaded)commands.Add(a);else a();}
  public ICounterEvent ReportCounter(CounterType t,EventHandler<ulong> h,float d,bool r){
   ulong draw=++pipeline.DrawCount;
   if(!threaded)return queue.QueueReport(h,d,draw,r);
   var proxy=new Proxy();Queue(()=>proxy.Base=queue.QueueReport(h,d,draw,r));return proxy;
  }
  public void ResetCounter(CounterType t)=>Queue(()=>queue.QueueReset(pipeline.DrawCount));
  public void CreateSync()=>Queue(()=>{
   Submissions++;Submitted.Set();AllowResults.Wait();lock(pipeline.Copies){foreach(var q in pipeline.Copies)q.Submit();pipeline.Copies.Clear();}
  });
  public void BackgroundContextAction(Action a){if(!threaded){a();return;}using var done=new ManualResetEventSlim();Queue(()=>{a();done.Set();});if(!done.Wait(5000))throw new Exception("render barrier timeout");}
  public void PublishWithoutSync(){AllowResults.Set();CreateSync();BackgroundContextAction(()=>{});}
  public void Dispose(){PublishWithoutSync();if(threaded){commands.CompleteAdding();if(!render.Join(5000))throw new Exception("render did not stop");}queue.Dispose();Submitted.Dispose();AllowResults.Dispose();}
 }
}
