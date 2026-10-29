using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using Ryujinx.Cpu;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.HLE.HOS;
using Ryujinx.HLE.HOS.Kernel;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.HLE.HOS.Kernel.Threading;

namespace ARMeilleure.Memory { interface IMemoryManager { } }
namespace Ryujinx.Memory
{
    interface IVirtualMemoryManager { }
    interface IRefCounted { void IncrementReferenceCount(); void DecrementReferenceCount(); }
}
namespace Ryujinx.Cpu
{
    interface IVirtualMemoryManagerTracked : Ryujinx.Memory.IVirtualMemoryManager { }
    interface IDiskCacheLoadState { }
    struct ExceptionCallbacks { }
    interface IExecutionContext : IDisposable { void StopRunning(); void RequestInterrupt(); }
    interface ICpuContext : IDisposable
    {
        IExecutionContext CreateExecutionContext(ExceptionCallbacks callbacks);
        void Execute(IExecutionContext context, ulong address);
        void PrepareCodeRange(ulong address, ulong size);
        IDiskCacheLoadState LoadDiskCache(string title, string version, bool enabled, string selector);
        void InvalidateCacheRegion(ulong address, ulong size);
    }
    interface ICpuEngine { ICpuContext CreateCpuContext(IVirtualMemoryManagerTracked memory, bool for64Bit); }
    sealed class ExecutionContext : IExecutionContext
    {
        public int Stops, Interrupts, Disposals;
        public void StopRunning() => Interlocked.Increment(ref Stops);
        public void RequestInterrupt() => Interlocked.Increment(ref Interrupts);
        public void Dispose()
        {
            if (Stops == 0) throw new Exception("Execution context disposed without kernel exit");
            Interlocked.Increment(ref Disposals);
        }
    }
    sealed class Cpu : ICpuEngine, ICpuContext
    {
        public int Executions, Disposals;
        public ICpuContext CreateCpuContext(IVirtualMemoryManagerTracked memory, bool for64Bit) => this;
        public IExecutionContext CreateExecutionContext(ExceptionCallbacks callbacks) => new ExecutionContext();
        public void Execute(IExecutionContext context, ulong address)
        {
            Interlocked.Increment(ref Executions);
            KernelStatic.GetCurrentThread().Exit();
        }
        public void PrepareCodeRange(ulong address, ulong size) { }
        public IDiskCacheLoadState LoadDiskCache(string title, string version, bool enabled, string selector) => null;
        public void InvalidateCacheRegion(ulong address, ulong size) { }
        public void Dispose() => Disposals++;
    }
    sealed class Memory : IVirtualMemoryManagerTracked, ARMeilleure.Memory.IMemoryManager, Ryujinx.Memory.IRefCounted
    {
        public int References;
        public Action<CancellationToken> InitializeShaderCache = _ => { };
        public void IncrementReferenceCount() => Interlocked.Increment(ref References);
        public void DecrementReferenceCount() => Interlocked.Decrement(ref References);
    }
}
namespace Ryujinx.Graphics.Gpu.Shader
{
    enum ShaderCacheState { Start, Loaded }
    sealed class ShaderCache
    {
        readonly Ryujinx.Cpu.Memory _memory;
        public int Loading, Calls, Disposed;
        public event Action<ShaderCacheState, int, int> ShaderCacheStateChanged;
        public ShaderCache(Ryujinx.Cpu.Memory memory) => _memory = memory;
        public void Initialize(CancellationToken token)
        {
            Interlocked.Increment(ref Loading);
            Interlocked.Increment(ref Calls);
            try { _memory.InitializeShaderCache(token); }
            finally { Interlocked.Decrement(ref Loading); }
        }
    }
}
namespace Ryujinx.Graphics.Gpu.Memory
{
    sealed class PhysicalMemory : IDisposable
    {
        readonly GpuContext _context;
        readonly Ryujinx.Cpu.Memory _memory;
        public ShaderCache ShaderCache;
        public int Disposals;
        public PhysicalMemory(GpuContext context, IVirtualMemoryManagerTracked memory)
        {
            _context = context;
            _memory = (Ryujinx.Cpu.Memory)memory;
            _memory.IncrementReferenceCount();
            ShaderCache = new(_memory);
        }
        public void Dispose()
        {
            if (ShaderCache.Loading != 0) throw new Exception("Guest memory unregistered during cache initialization");
            if (Interlocked.Exchange(ref Disposals, 1) != 0) return;
            _context.DeferredActions.Enqueue(() => { ShaderCache.Disposed++; _memory.DecrementReferenceCount(); });
        }
    }
}
namespace Ryujinx.Graphics.GAL.Multithreading
{
    class ThreadedRenderer : IDisposable
    {
        public int Flushes, Disposals;
        public void FlushThreadedCommands() => Interlocked.Increment(ref Flushes);
        public void Dispose() => Interlocked.Increment(ref Disposals);
    }
}
namespace Ryujinx.Graphics.Gpu
{
    sealed class DisposableBoundary : IDisposable { public void Dispose() { } }
    partial class GpuContext : IDisposable
    {
        public ManualResetEvent HostInitalized { get; } = new(false);
        public ConcurrentDictionary<ulong, PhysicalMemory> PhysicalMemoryRegistry = new();
        public ConcurrentQueue<Action> DeferredActions = new();
        public Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer Renderer = new();
        public DisposableBoundary GPFifo = new(), SupportBufferUpdater = new();
        public event Action<ShaderCacheState, int, int> ShaderCacheStateChanged;
        public GpuContext() => _gpuReadyEvent = new(false);
        public void SetGpuThread() { }
        public bool TerminalSignalled => _gpuReadyEvent.WaitOne(0);
        public void ReleaseLegacyWaitersForCleanup() => _gpuReadyEvent.Set();
#if GPU_STARTUP_ADAPTED
        public bool InitializationActive { get { lock (_gpuInitializationLock) return _gpuInitializationState == GpuInitializationState.Initializing; } }
#endif
    }
}
namespace Ryujinx.HLE.HOS.Kernel
{
    sealed class CriticalSection
    {
        readonly object _gate = new();
        public void Enter() => Monitor.Enter(_gate);
        public void Leave() => Monitor.Exit(_gate);
    }
    sealed class Synchronization
    {
        public void WaitFor(object[] objects, long timeout, out int index) => throw new Exception("Unexpected self termination wait");
    }
    sealed class KernelContext
    {
        public CriticalSection CriticalSection = new();
        public Synchronization Synchronization = new();
    }
    static class KernelStatic
    {
        [ThreadStatic] static KThread _thread;
        public static void SetKernelContext(KernelContext context, KThread thread) => _thread = thread;
        public static KThread GetCurrentThread() => _thread;
    }
    enum KernelResult { ThreadTerminating }
    enum LimitableResource { Thread }
    sealed class ResourceLimit { public int Releases; public void Release(LimitableResource kind, int count, int hint) => Releases++; }
}
namespace Ryujinx.HLE.HOS.Kernel.Process
{
    interface IProcessContext : IDisposable { void Execute(IExecutionContext context, ulong address); }
    partial class KProcess
    {
        readonly object _threadingLock = new();
        readonly List<KThread> _threads = new();
        public KernelContext KernelContext;
        public KThread[] PinnedThreads = new KThread[4];
        public ResourceLimit ResourceLimit = new();
        public IProcessContext Context;
        public KProcess(KernelContext kernel, IProcessContext context) { KernelContext = kernel; Context = context; }
        public void Add(KThread thread) => _threads.Add(thread);
        public void UnpinThread(KThread thread) { }
        public void StopAll() => UnpauseAndTerminateAllThreadsExcept(null);
    }
}
namespace Ryujinx.HLE.HOS.Kernel.Threading
{
    class KSynchronizationObject { }
    partial class KThread : KSynchronizationObject
    {
        public KernelContext KernelContext;
        public KProcess Owner;
        public IExecutionContext Context;
        public Thread HostThread;
        public ManualResetEventSlim DebugHalt = new(true);
        ManualResetEventSlim _schedulerWaitEvent = new(true);
        ThreadStart _customThreadStart;
        ulong _entrypoint;
        public int CurrentCore, BasePriority = 32, Decrements, Increments;
        public object SignaledObj;
        public KernelResult ObjSyncResult;
        int _shallBeTerminated, _hasExited;
        bool _hasBeenReleased;
        ThreadSchedState _forcePauseFlags, _forcePausePermissionFlags;
        public ThreadSchedState SchedFlags = ThreadSchedState.Running;
        public bool TerminationRequested => _shallBeTerminated != 0 || SchedFlags == ThreadSchedState.TerminationPending;
        public bool Exited => Volatile.Read(ref _hasExited) != 0;
        public KThread(KProcess owner, IExecutionContext context)
        {
            Owner = owner; KernelContext = owner.KernelContext; Context = context;
            HostThread = new Thread(ThreadStart) { IsBackground = true };
            owner.Add(this);
        }
        public void IncrementReferenceCount() => Interlocked.Increment(ref Increments);
        public void DecrementReferenceCount() => Interlocked.Increment(ref Decrements);
        void SetPriority(int priority) => BasePriority = priority;
        void AdjustScheduling(ThreadSchedState previous) { }
        void LeaveSyncWaitList() { }
        void ReleaseAndResume() { }
        void CombineForcePauseFlags() { }
        void SetNewSchedFlags(ThreadSchedState state) => SchedFlags = state;
        void Signal() { }
    }
}
namespace Ryujinx.Library
{
    static class Library { public static void WithdrawEmbeddedControls() { } }
    sealed class HorizonBoundary : IDisposable
    {
        readonly KProcess _process;
        readonly KThread[] _threads;
        public ManualResetEventSlim Entered = new();
        public int Disposals;
        public HorizonBoundary(KProcess process, KThread[] threads) { _process = process; _threads = threads; }
        public void Dispose()
        {
            Entered.Set();
            _process.StopAll();
            foreach (var thread in _threads) thread.HostThread.Join();
            _process.Context.Dispose();
            Disposals++;
        }
    }
    sealed class DeviceBoundary
    {
        public GpuContext Gpu;
        public HorizonBoundary System;
        public Action Frame;
        public int Frames;
        public void ProcessFrame() { Frames++; Frame(); Thread.Yield(); }
        public void DisposeGpu() => Gpu.Dispose();
    }
    partial class WindowBase : IDisposable
    {
        readonly Stopwatch _chrono = new();
        readonly CancellationTokenSource _gpuCancellationTokenSource = new();
        readonly EmbeddedWindowLifetime _embeddedLifetime = new();
        public DeviceBoundary Device;
        public Action BeforeRender;
        public bool EmbeddedGpuReleased, EmbeddedExecutionFailed;
        public Exception EmbeddedExecutionFailure;
        public WindowBase(DeviceBoundary device) { Device = device; Device.Frame = _embeddedLifetime.RequestStop; }
        public void RequestStop() => _embeddedLifetime.RequestStop();
        void InitializeWindow() { }
        void FinalizeWindowRenderer() { }
        void MainLoop() { while (_embeddedLifetime.InputAllowed) Thread.Yield(); }
        void Render() { BeforeRender?.Invoke(); RunGpuCallback(); }
        public void Dispose() => _embeddedLifetime.Dispose(_gpuCancellationTokenSource.Dispose);
    }
}
