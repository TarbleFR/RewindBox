using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Runtime.ExceptionServices;
using System.Threading;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Commands;
using Ryujinx.Graphics.GAL.Multithreading.Commands.CounterEvent;
using Ryujinx.Graphics.GAL.Multithreading.Model;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.Gpu.Memory;

namespace Ryujinx.Graphics.GAL {
 public enum CounterType {SamplesPassed,PrimitivesGenerated}
 public interface IPipeline {
  bool TryHostConditionalRendering(ICounterEvent value,ulong compare,bool equal);
  bool TryHostConditionalRendering(ICounterEvent value,ICounterEvent compare,bool equal);
  void EndHostConditionalRendering();
 }
 public interface IRenderer {
  IPipeline Pipeline{get;}
  void BackgroundContextAction(Action action,bool alwaysBackground=false);
  ICounterEvent ReportCounter(CounterType type,EventHandler<ulong> callback,float divisor,bool reserved);
  void UpdateCounters();void Submit();
 }
 class DirectRenderer:IRenderer {
  public IPipeline Pipeline{get;} public int Submissions,Polls;public Action OnSubmit;
  public Func<CounterType,EventHandler<ulong>,bool,ICounterEvent> CreateCounter;
  public DirectRenderer(IPipeline pipeline){Pipeline=pipeline;}
  public void BackgroundContextAction(Action a,bool b=false)=>a();
  public ICounterEvent ReportCounter(CounterType t,EventHandler<ulong> c,float d,bool r)=>CreateCounter(t,c,r);
  public void UpdateCounters(){Polls++;}
  public void Submit(){Submissions++;OnSubmit?.Invoke();}
 }
}
namespace Ryujinx.Graphics.GAL.Multithreading.Commands {
 interface IGALCommand {CommandType CommandType{get;}}
 interface IGALCommand<T> where T:unmanaged,IGALCommand<T> {static abstract void Run(ref T command,ThreadedRenderer threaded,IRenderer renderer);}
 enum CommandType {TryHostConditionalRendering,TryHostConditionalRenderingFlush,CounterEventDispose,Action}
}
namespace Ryujinx.Graphics.GAL.Multithreading {
 partial class ThreadedPipeline:IPipeline {
  readonly ThreadedRenderer _renderer;
  public ThreadedPipeline(ThreadedRenderer r){_renderer=r;}
  TableRef<T> Ref<T>(T value)=>new(_renderer,value);
  public void EndHostConditionalRendering()=>_renderer.EnqueueAction(()=>_renderer.Base.Pipeline.EndHostConditionalRendering());
 }
 partial class ThreadedRenderer:IRenderer,IDisposable {
  readonly IRenderer _baseRenderer;public IRenderer Base=>_baseRenderer;
  readonly BlockingCollection<Action> _commands=new();readonly Thread _render;
  readonly ConcurrentDictionary<int,object> _refs=new();int _nextRef;
  Action _pending;int _lastProducedPtr,_invokePtr=-1;
  ExceptionDispatchInfo _rendererFailure;bool _running=true;
  readonly ManualResetEventSlim _invokeRun=new(),_rendererFailed=new(),_galWorkAvailable=new();
  readonly AutoResetEvent _frameComplete=new(false),_interruptRun=new(false);
  public IPipeline Pipeline{get;} public int ReservationsAtCreate;public int Queued,Invoked;
  public ThreadedRenderer(IRenderer r){_baseRenderer=r;Pipeline=new ThreadedPipeline(this);_render=new(()=>{
   foreach(var a in _commands.GetConsumingEnumerable()) {try{ThrowIfFailed();a();}catch(Exception e){RecordFailure(e);}}
  });_render.Start();}
  TableRef<T> Ref<T>(T value)=>new(this,value);
  internal int AddTableRef(object value){int id=Interlocked.Increment(ref _nextRef);_refs[id]=value??Null.Value;return id;}
  internal object RemoveTableRef(int id){if(!_refs.TryRemove(id,out var value))throw new Exception("reference consumed twice");return ReferenceEquals(value,Null.Value)?null:value;}
  sealed class Null {public static readonly object Value=new();}
  internal unsafe T* New<T>() where T:unmanaged,IGALCommand<T> {
   ThrowIfFailed();if(_pending!=null)throw new Exception("pending command");
   T* ptr=(T*)Marshal.AllocHGlobal(sizeof(T));*ptr=default;int id=++_lastProducedPtr;
   _pending=()=>{try{T.Run(ref *ptr,this,_baseRenderer);}catch(Exception e){RecordFailure(e);throw;}finally{Marshal.FreeHGlobal((nint)ptr);if(_invokePtr==id){Invoked++;_invokeRun.Set();}}};return ptr;
  }
  internal void QueueCommand(){ThrowIfFailed();var a=_pending??throw new Exception("missing command");_pending=null;Queued++;_commands.Add(a);}
  internal bool IsGpuThread()=>Thread.CurrentThread!=_render;
  public void EnqueueAction(Action action){ThrowIfFailed();_commands.Add(action);}
  public ICounterEvent ReportCounter(CounterType t,EventHandler<ulong> callback,float d,bool reserved){
   var evt=new ThreadedCounterEvent(this,t,true);EnqueueAction(()=>{evt.Create(_baseRenderer,t,callback,d,reserved);});return evt;
  }
  public void UpdateCounters()=>EnqueueAction(_baseRenderer.UpdateCounters);
  public void Submit()=>EnqueueAction(_baseRenderer.Submit);
  public void Dispose(){_commands.CompleteAdding();if(!_render.Join(5000))throw new Exception("render thread stuck");}
 }
 static class ThreadedHelpers {
  public static void SpinUntilNonNull<T>(ref T value,ThreadedRenderer renderer)where T:class{var s=new SpinWait();while(Volatile.Read(ref value)==null){renderer.ThrowIfFailed();s.SpinOnce();}}
  public static void SpinUntilExchange(ref int value,int set,int match,ThreadedRenderer renderer){var s=new SpinWait();while(Interlocked.CompareExchange(ref value,set,match)!=match){renderer.ThrowIfFailed();s.SpinOnce();}}
 }
}
namespace Ryujinx.Common.Logging {
 enum LogClass {Gpu}class Log {public void Print(LogClass c,string s){}}static class Logger {public static Log Warning;}
}
namespace Ryujinx.Graphics.Gpu.Engine.Types {enum Condition{Always,Never,ResultNonZero,Equal,NotEqual}struct GpuVa{readonly ulong _value;public GpuVa(ulong v){_value=v;}public ulong Pack()=>_value;}}
namespace Ryujinx.Graphics.Gpu.Engine.Threed {enum ConditionalRenderEnabled{False,True,Host}}
namespace Ryujinx.Graphics.Gpu.Memory {
 class UnmapEventArgs:EventArgs {public ulong Address,Size;public UnmapEventArgs(ulong a,ulong s){Address=a;Size=s;}}
 class MemoryManager {public CounterCache CounterCache=new();public Dictionary<ulong,ulong> Values=new();public int Reads;public T Read<T>(ulong a,bool tracked=false)where T:unmanaged{Reads++;ulong value=Values.GetValueOrDefault(a);return (T)(object)value;}}
}
namespace Ryujinx.Graphics.Gpu {
 [Flags]enum HostSyncFlags{StrictSyncpoint=3,Force=4}
 class Synchronization {public Action<uint> OnSignal;public int Signals;public uint LastId;public void IncrementSyncpoint(uint id){LastId=id;OnSignal?.Invoke(id);Signals++;}public void WaitOnSyncpoint(uint i,uint t,TimeSpan s){}}
 partial class GpuContext {
  public bool SynchronizeOcclusionReports;internal readonly HashSet<CounterCache> _counterReportCaches=new();
  public IRenderer Renderer;public Synchronization Synchronization=new();public List<HostSyncFlags> Syncs=new();public int Sequence;
  public GpuContext(IRenderer renderer){Renderer=renderer;}
  public void AdvanceSequence()=>Sequence++;
  public void CreateHostSyncIfNeeded(HostSyncFlags flags){Syncs.Add(flags);Renderer.Submit();}
  internal void TrackCounterReports(CounterCache cache)=>_counterReportCaches.Add(cache);
 }
 enum SyncpointbOperation{Wait,Incr}
 class FifoState{public SyncpointbOperation SyncpointbOperation=SyncpointbOperation.Incr;public int SyncpointbSyncptIndex=7,SyncpointaPayload;}
 class DeviceState<T>where T:new(){public T State=new();}
 class TextureManager{public void RefreshModifiedTextures(){}}
 class Channel{public TextureManager TextureManager=new();}
 partial class FifoProbe{public GpuContext _context;public DeviceState<FifoState> _state=new();public Channel _parent=new();public FifoProbe(GpuContext c){_context=c;}}
 partial class ThreedProbe{public GpuContext _context;public ThreedProbe(GpuContext c){_context=c;}}
}
namespace Ryujinx.Graphics.Vulkan {
 partial class PipelineFull:IPipeline {
  public int Flushes;public Action OnFlush;public void FlushPendingQuery(){Flushes++;OnFlush?.Invoke();}
  public void EndHostConditionalRendering(){}
 }
}
namespace Ryujinx.Graphics.OpenGL {
 enum QueryTarget{SamplesPassed,PrimitivesGenerated}enum ConditionalRenderType{QueryNoWaitInverted,QueryNoWait}
 static class GL {public static int Begins,Ends,Flushes;public static void BeginConditionalRender(int q,ConditionalRenderType t)=>Begins++;public static void EndConditionalRender()=>Ends++;public static void Flush()=>Flushes++;}
 partial class Pipeline:IPipeline{Queries.CounterQueueEvent _activeConditionalRender;}
}
namespace Ryujinx.Graphics.OpenGL.Queries {
 class CounterQueueEvent:ICounterEvent {
  public bool Invalid{get;set;}public QueryTarget Type=QueryTarget.SamplesPassed;public bool ClearCounter=true;public int Query=1;
  public bool Ready,Reserved;public int ReserveCalls,ReleaseCalls,Flushes;public Action Publish;
  public bool ReserveForHostAccess(){ReserveCalls++;if(Reserved)return true;if(Ready)return false;Reserved=true;return true;}
  public void ReleaseHostAccess(){if(!Reserved)throw new Exception("release without reserve");Reserved=false;ReleaseCalls++;}
  public void Flush(){Flushes++;Ready=true;Publish?.Invoke();}
  public void Dispose(){}
 }
}
