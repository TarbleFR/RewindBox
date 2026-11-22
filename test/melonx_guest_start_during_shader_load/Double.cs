// Doubles for melonx_guest_start_during_shader_load_test.py. The real GpuContext members of the GPU initialization
// (its fields and states, RegisterProcess, UnregisterProcess, InitializeShaderCache, CancelShaderCacheInitialization,
// WaitUntilGpuReady, RunDeferredActions, Dispose and, in the candidate, WaitUntilGuestMayStart,
// ReleaseGuestForShaderLoad, WaitForShaderCacheLoader and GetShaderLoadPhase), the real PhysicalMemory.Dispose and
// Destroy, and the whole real ArmProcessContext.cs, SynchronizationManager.cs, Syncpoint.cs, SyncpointWaiterHandle.cs
// and ISynchronizationManager.cs are compiled with these doubles. The shader cache is a loader that takes a set time,
// fills a table program by program and records what happens while it runs; the guest is a thread that submits
// "GPU commands" as soon as it executes.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Shader;

// One launch: what the loader, the guest threads, the GPU thread and the session owner observed.
class World
{
    public static World Current;

    public readonly long Origin = Stopwatch.GetTimestamp();
    public double Now => Stopwatch.GetElapsedTime(Origin).TotalMilliseconds;

    // The loader double.
    public int Programs = 60, ProgramMs = 10, FailAt = -1, UnwindMs;
    public bool ThrowOnCancel;
    public int LoadsRunning, LoadsBegun, LoadsEnded, Table, Snapshots;
    public double LoadBeginMs = -1, LoadEndMs = -1;
    public volatile bool LoadedEventSeen;

    // The guest double.
    public int GuestExitAfterMs = -1;
    public volatile bool TerminateRequested, GuestForbidden, HostInitializedSet;
    public int GuestThreadsRan, GuestStartsDuringLoad, GuestStartsBeforeLoadEnded, GuestStartsBeforeSnapshot, GuestStartsBeforeHostInitialized;
    public int ForbiddenGuestRuns, ThreadsEndedWithoutRunning, KernelExits;
    public double FirstGuestStartMs = -1;
    private int _guestStarted;

    // The GPU thread's loop after InitializeShaderCache (WindowBase.Render).
    public readonly ConcurrentQueue<int> Fifo = new();
    public int CommandsProcessed, CommandsDuringLoad, CommandsWithPartialTable;
    public double FirstCommandMs = -1;

    // Fences: the syncpoint the GPU thread increments for each command it processes (-1: none), and the engine's lines.
    public int FenceSyncpoint = -1;
    public int ErrorLines, WarningLines, InfoLines;

    // What must follow the loader.
    public int HandlersRemovedDuringLoad, DestroysQueuedDuringLoad, DestroysQueued, CachesDisposed, CachesDisposedDuringLoad, EventsDisposedDuringLoad;
    public readonly List<string> Journal = new();

    public void Load(CancellationToken token, Action<ShaderCacheState, int, int> progress)
    {
        Interlocked.Increment(ref LoadsRunning);
        Interlocked.Increment(ref LoadsBegun);
        LoadBeginMs = Now;
        bool interrupted = true;
        try
        {
            progress(ShaderCacheState.Start, 0, Programs);
            for (int index = 0; index < Programs; index++)
            {
                if (token.IsCancellationRequested)
                {
                    // ParallelDiskCacheLoader stops at its next check (Active) or leaves a cancelled queue wait.
                    if (ThrowOnCancel) token.ThrowIfCancellationRequested();
                    return;
                }
                if (index == FailAt) throw new InvalidOperationException("shader cache loader failure (fixture)");
                if (ProgramMs > 0) Thread.Sleep(ProgramMs);
                Interlocked.Increment(ref Table); // one more cached program is in the tables
                progress(ShaderCacheState.Loading, index + 1, Programs);
            }
            interrupted = false;
            progress(ShaderCacheState.Loaded, Programs, Programs);
        }
        finally
        {
            // The loader joins its translation threads before it returns, also when it fails or is cancelled.
            if (interrupted && UnwindMs > 0) Thread.Sleep(UnwindMs);
            LoadEndMs = Now;
            Interlocked.Increment(ref LoadsEnded);
            Interlocked.Decrement(ref LoadsRunning);
        }
    }

    [ThreadStatic] public static bool RanGuestCode;

    // CPU code of the guest: it submits GPU commands at once, then runs until it is terminated or exits by itself.
    public void GuestCode()
    {
        double start = Now;
        RanGuestCode = true;
        if (Interlocked.Exchange(ref _guestStarted, 1) == 0) FirstGuestStartMs = start;
        Interlocked.Increment(ref GuestThreadsRan);
        if (Volatile.Read(ref LoadsRunning) != 0) Interlocked.Increment(ref GuestStartsDuringLoad);
        if (Volatile.Read(ref LoadsEnded) == 0) Interlocked.Increment(ref GuestStartsBeforeLoadEnded);
        if (Volatile.Read(ref Snapshots) == 0) Interlocked.Increment(ref GuestStartsBeforeSnapshot);
        if (!HostInitializedSet) Interlocked.Increment(ref GuestStartsBeforeHostInitialized);
        for (int command = 0; command < 3; command++) Fifo.Enqueue(command);
        while (!TerminateRequested && (GuestExitAfterMs < 0 || Now - start < GuestExitAfterMs)) Thread.Sleep(1);
    }
}

namespace Ryujinx.Common
{
    static class EmbeddedLaunchDiagnostics
    {
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            World world = World.Current;
            lock (world.Journal) world.Journal.Add(stage + " " + status + " " + detail);
        }
    }
}
namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    class Log
    {
        private readonly int _level;
        public Log(int level) { _level = level; }
        public void Print(LogClass logClass, string message)
        {
            World world = World.Current;
            if (_level == 0) Interlocked.Increment(ref world.ErrorLines);
            else if (_level == 1) Interlocked.Increment(ref world.WarningLines);
            else Interlocked.Increment(ref world.InfoLines);
        }
    }
    static class Logger { public static Log Error = new(0), Warning = new(1), Info = new(2); }
}
namespace ARMeilleure.Memory { interface IMemoryManager { } }
namespace Ryujinx.Memory
{
    interface IVirtualMemoryManager { }
    interface IRefCounted { void IncrementReferenceCount(); void DecrementReferenceCount(); }
}
namespace Ryujinx.Cpu
{
    using ARMeilleure.Memory;
    using Ryujinx.Memory;

    interface IVirtualMemoryManagerTracked : IVirtualMemoryManager { }
    interface IExecutionContext { }
    interface IDiskCacheLoadState { }
    class ExceptionCallbacks { }
    interface ICpuContext : IDisposable
    {
        IExecutionContext CreateExecutionContext(ExceptionCallbacks exceptionCallbacks);
        void Execute(IExecutionContext context, ulong address);
        void InvalidateCacheRegion(ulong address, ulong size);
        IDiskCacheLoadState LoadDiskCache(string titleIdText, string displayVersion, bool enabled, string cacheSelector);
        void PrepareCodeRange(ulong address, ulong size);
    }
    interface ICpuEngine { ICpuContext CreateCpuContext(IMemoryManager memoryManager, bool for64Bit); }

    // The guest's memory and CPU: executing is World.GuestCode.
    class GuestMemory : IVirtualMemoryManagerTracked, IMemoryManager, IRefCounted
    {
        public int References;
        public void IncrementReferenceCount() { Interlocked.Increment(ref References); }
        public void DecrementReferenceCount() { Interlocked.Decrement(ref References); }
    }
    class GuestCpu : ICpuEngine, ICpuContext
    {
        private readonly World _world;
        public GuestCpu(World world) { _world = world; }
        public ICpuContext CreateCpuContext(IMemoryManager memoryManager, bool for64Bit) => this;
        public IExecutionContext CreateExecutionContext(ExceptionCallbacks exceptionCallbacks) => null;
        public void Execute(IExecutionContext context, ulong address) { _world.GuestCode(); }
        public void InvalidateCacheRegion(ulong address, ulong size) { }
        public IDiskCacheLoadState LoadDiskCache(string titleIdText, string displayVersion, bool enabled, string cacheSelector) => null;
        public void PrepareCodeRange(ulong address, ulong size) { }
        public void Dispose() { }
    }
}
namespace Ryujinx.HLE.HOS.Kernel
{
    class KThread { public void Exit() { Interlocked.Increment(ref World.Current.KernelExits); } }
    static class KernelStatic { public static KThread GetCurrentThread() => new(); }
}
namespace Ryujinx.HLE.HOS.Kernel.Process
{
    using Ryujinx.Cpu;
    using Ryujinx.Memory;

    interface IProcessContext : IDisposable
    {
        IVirtualMemoryManager AddressSpace { get; }
        ulong AddressSpaceSize { get; }
        IExecutionContext CreateExecutionContext(ExceptionCallbacks exceptionCallbacks);
        void Execute(IExecutionContext context, ulong codeAddress);
        void InvalidateCacheRegion(ulong address, ulong size);
    }
}
namespace Ryujinx.Graphics.Gpu.Shader
{
    enum ShaderCacheState { Start, Loading, Packaging, Loaded }

    class ShaderCache : IDisposable
    {
        private readonly World _world;
        private Action<ShaderCacheState, int, int> _stateChanged;

        public ShaderCache(GpuContext context) { _world = context.World; }

        public event Action<ShaderCacheState, int, int> ShaderCacheStateChanged
        {
            add { lock (this) _stateChanged += value; }
            remove
            {
                if (Volatile.Read(ref _world.LoadsRunning) != 0) Interlocked.Increment(ref _world.HandlersRemovedDuringLoad);
                lock (this) _stateChanged -= value;
            }
        }

        internal void Initialize(CancellationToken cancellationToken)
        {
            _world.Load(cancellationToken, (state, current, total) => { Action<ShaderCacheState, int, int> handler; lock (this) handler = _stateChanged; handler?.Invoke(state, current, total); });
        }

        public void Dispose()
        {
            if (Volatile.Read(ref _world.LoadsRunning) != 0) Interlocked.Increment(ref _world.CachesDisposedDuringLoad);
            Interlocked.Increment(ref _world.CachesDisposed);
        }
    }
}
namespace Ryujinx.Graphics.Gpu.Memory
{
    using Ryujinx.Graphics.Gpu.Shader;
    using Ryujinx.Memory;

    class Cache : IDisposable { public void Dispose() { } }

    class PhysicalMemory : IDisposable
    {
        private readonly GpuContext _context;
        private readonly Cpu.IVirtualMemoryManagerTracked _cpuMemory;
        private readonly object _channelGate = new();
        private int _boundChannels;
        private bool _disposeRequested;
        public ShaderCache ShaderCache { get; }
        public Cache BufferCache { get; } = new();
        public Cache TextureCache { get; } = new();

        public PhysicalMemory(GpuContext context, Cpu.IVirtualMemoryManagerTracked cpuMemory)
        {
            _context = context;
            _cpuMemory = cpuMemory;
            ShaderCache = new ShaderCache(context);
            if (cpuMemory is IRefCounted rc) rc.IncrementReferenceCount();
        }

        public void DecrementReferenceCount() { if (_cpuMemory is IRefCounted rc) rc.DecrementReferenceCount(); }

/* MEMORY_METHODS */
    }
}
namespace Ryujinx.Graphics.Gpu
{
    using Ryujinx.Graphics.Gpu.Memory;
    using Ryujinx.Graphics.Gpu.Shader;
    using Ryujinx.Graphics.Gpu.Synchronization;

    class CounterCache { public void CancelPendingReports() { } }
    class Disposable : IDisposable { public void Dispose() { } }

    // The loader's snapshot is observable: Values copies, as ConcurrentDictionary's does.
    class MemoryRegistry
    {
        private readonly World _world;
        private readonly ConcurrentDictionary<ulong, PhysicalMemory> _memories = new();
        public MemoryRegistry(World world) { _world = world; }
        public bool TryAdd(ulong pid, PhysicalMemory memory) => _memories.TryAdd(pid, memory);
        public bool TryRemove(ulong pid, out PhysicalMemory memory) => _memories.TryRemove(pid, out memory);
        public void Clear() { _memories.Clear(); }
        public ICollection<PhysicalMemory> Values { get { ICollection<PhysicalMemory> values = _memories.Values; Interlocked.Increment(ref _world.Snapshots); return values; } }
    }

    // GpuContext.DeferredActions: destructions queued for the GPU thread.
    class DeferredQueue
    {
        private readonly World _world;
        private readonly ConcurrentQueue<Action> _actions = new();
        public DeferredQueue(World world) { _world = world; }
        public bool IsEmpty => _actions.IsEmpty;
        public void Enqueue(Action action)
        {
            if (Volatile.Read(ref _world.LoadsRunning) != 0) Interlocked.Increment(ref _world.DestroysQueuedDuringLoad);
            Interlocked.Increment(ref _world.DestroysQueued);
            _actions.Enqueue(action);
        }
        public bool TryDequeue(out Action action) => _actions.TryDequeue(out action);
    }

    // The events are the real ones' type, so a wait or a Set on a disposed event fails as it would in the engine. Those
    // the GPU context owns are tracked (the syncpoint waits' own events, of the same name, are not).
    sealed class ManualResetEvent : IDisposable
    {
        [ThreadStatic] public static bool TrackNew;
        private readonly System.Threading.ManualResetEvent _event;
        private readonly bool _tracked = TrackNew;
        public ManualResetEvent(bool initialState) { _event = new System.Threading.ManualResetEvent(initialState); }
        public System.Threading.WaitHandle Handle => _event;
        public bool Set() => _event.Set();
        public bool WaitOne() => _event.WaitOne();
        public bool WaitOne(int milliseconds) => _event.WaitOne(milliseconds);
        public bool WaitOne(TimeSpan timeout) => _event.WaitOne(timeout);
        public void Dispose()
        {
            World world = World.Current;
            if (_tracked && Volatile.Read(ref world.LoadsRunning) != 0) Interlocked.Increment(ref world.EventsDisposedDuringLoad);
            _event.Dispose();
        }
        public static implicit operator System.Threading.WaitHandle(ManualResetEvent value) => value._event;
    }

    sealed class GpuContext : IDisposable
    {
        public readonly World World;
        public ManualResetEvent HostInitalized { get; }
        internal MemoryRegistry PhysicalMemoryRegistry { get; }
        internal DeferredQueue DeferredActions { get; }
        public event Action<ShaderCacheState, int, int> ShaderCacheStateChanged;
        public SynchronizationManager Synchronization { get; }

        // What the real Dispose releases besides the initialization's own objects.
        private readonly HashSet<CounterCache> _counterReportCaches = new();
        public Disposable GPFifo { get; } = new();
        internal Disposable SupportBufferUpdater { get; } = new();
        public Disposable Renderer { get; } = new();
        private void ReleaseQueuedSyncpoints() { }

/* GPU_FIELDS */

        public GpuContext(World world)
        {
            World = world;
            ManualResetEvent.TrackNew = true;
            HostInitalized = new ManualResetEvent(false);
/* GPU_CONSTRUCTOR */
            ManualResetEvent.TrackNew = false;
            DeferredActions = new DeferredQueue(world);
            PhysicalMemoryRegistry = new MemoryRegistry(world);
        }

        // Read by the fixture only.
        internal string State { get { lock (_gpuInitializationLock) return _gpuInitializationState.ToString(); } }

/* GPU_METHODS */
    }
}
