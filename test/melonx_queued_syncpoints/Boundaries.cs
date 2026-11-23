// Boundaries of the queued syncpoint fixture: everything the compiled regions call that is not under test.
// The host sync, the threaded renderer, the syncpoint manager, the logger, the FIFO's event and the backend counter
// events are doubles; the queue, the reports, the cache's pending list and the GPU call sites are the adapters' text.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;

namespace Ryujinx.Graphics.GAL
{
    public interface ICounterEvent : IDisposable
    {
        bool Invalid { get; set; }
        bool ReserveForHostAccess();
        void Flush();
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    public static class EncodingPolicy
    {
        public static bool IncrementalArrayDescriptors;
    }
}

namespace Ryujinx.Common
{
    // Diagnostic counters only (the prepared CounterCache and GPFifoDevice call them); nothing is measured here.
    public static class EmbeddedPerformanceDiagnostics
    {
        public enum Phase { GpuFifoWait, CounterReports, GpuDispatch }
        public enum Counter { CounterReportsFlushed }
        public static IDisposable Measure(Phase phase) => Scope.Instance;
        public static void ReportBatch(int count) { }
        public static void Count(Counter counter) { }
        public static void Count(Counter counter, long value) { }

        private sealed class Scope : IDisposable
        {
            public static readonly Scope Instance = new();
            public void Dispose() { }
        }
    }
}

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }

    public sealed class Log
    {
        public readonly List<string> Lines = new();
        public void PrintMsg(LogClass logClass, string message) { lock (Lines) Lines.Add(message); }
    }

    public static class Logger
    {
        public static Log Info = new();
    }
}

namespace Ryujinx.Graphics.Gpu.Memory
{
    public class UnmapEventArgs
    {
        public ulong Address { get; }
        public ulong Size { get; }
        public UnmapEventArgs(ulong address, ulong size) { Address = address; Size = size; }
    }

    partial class CounterCache
    {
        // Boundary for CounterCache.AddOrUpdate as adapt_occlusion_reports writes it: a deferred report joins the
        // pending list under the cache's lock.
        internal void AddReport(DeferredCounterReport report)
        {
            lock (_gate) _pending.Add(report);
        }
    }
}

namespace Ryujinx.Graphics.Gpu
{
    // The production values (Synchronization/HostSyncFlags.cs): a sync that is not Strict is created on the open command
    // buffer and submitted with it later; a Strict one submits it.
    [Flags]
    public enum HostSyncFlags { None = 0, Syncpoint = 1 << 0, Strict = 1 << 1, Force = 1 << 2, StrictSyncpoint = Strict | Syncpoint }

    // Ordered record of what the guest and the backend observe.
    public static class FixtureTrace
    {
        private static readonly List<string> Events = new();
        public static void Add(string value) { lock (Events) Events.Add(value); }
        public static void Reset() { lock (Events) Events.Clear(); }
        public static string[] Snapshot() { lock (Events) return Events.ToArray(); }
    }

    public sealed class SyncBoundary
    {
        public void IncrementSyncpoint(uint id) => FixtureTrace.Add("inc:" + id);
        public void WaitOnSyncpoint(uint id, uint threshold, TimeSpan timeout) => FixtureTrace.Add("wait:" + id);
    }

    // The threaded GAL: commands run in order on a render thread (with an optional delay per submission, a render
    // thread behind the GPU thread); BackgroundContextAction returns once the render thread has run everything queued.
    public sealed class RendererBoundary : IDisposable
    {
        private readonly bool _threaded;
        private readonly BlockingCollection<Action> _commands = new();
        private readonly Thread _thread;
        private int _submitted;
        public int SubmitsQueued, Drains, Updates, SubmitDelayMs;

        public RendererBoundary(bool threaded)
        {
            _threaded = threaded;
            if (threaded)
            {
                _thread = new Thread(() => { foreach (var command in _commands.GetConsumingEnumerable()) command(); }) { IsBackground = true };
                _thread.Start();
            }
        }

        public int Submitted => Volatile.Read(ref _submitted);

        private void Queue(Action action)
        {
            if (_threaded) _commands.Add(action); else action();
        }

        public void Submit()
        {
            SubmitsQueued++;
            int delay = SubmitDelayMs;
            Queue(() =>
            {
                if (delay > 0) Thread.Sleep(delay);
                Interlocked.Increment(ref _submitted);
            });
        }

        public void BackgroundContextAction(Action action)
        {
            Drains++;
            FixtureTrace.Add("renderer-barrier");
            if (!_threaded)
            {
                action();
                return;
            }
            using var done = new ManualResetEventSlim();
            Queue(() => { action(); done.Set(); });
            if (!done.Wait(10000)) throw new Exception("render barrier timeout");
        }

        public void UpdateCounters() => Updates++;

        public void Dispose()
        {
            if (!_threaded) return;
            _commands.CompleteAdding();
            if (!_thread.Join(10000)) throw new Exception("render thread did not stop");
        }
    }

    public sealed class FifoBoundary
    {
        public void Dispose() => FixtureTrace.Add("fifo-dispose");
    }

    // GpuContext.Window, as GPFifoDevice.WaitForCommands reads it under the pacing policy (a frame waits to be presented).
    public sealed class WindowBoundary
    {
        public bool IsFrameAvailable;
    }

    public partial class GpuContext
    {
        public readonly RendererBoundary Renderer;
        public readonly SyncBoundary Synchronization = new();
        public readonly FifoBoundary GPFifo = new();
        public readonly List<HostSyncFlags> HostSyncs = new();

        public GpuContext(bool threaded) { Renderer = new RendererBoundary(threaded); }

        public readonly List<string> HostSyncCallers = new();
        // What the prepared GPFifoDevice.WaitForCommands reads besides the queue.
        public readonly ConcurrentQueue<Action> DeferredActions = new();
        public readonly WindowBoundary Window = new();
        // adapt_paced_strict_syncs' policy flag (Hogwarts Legacy only, set with the queue's by the Library).
        public static bool PaceStrictHostSyncs { get; set; }
        // Syncs created on the open command buffer and not submitted yet (not Strict), and how many were.
        public int KeptOnOpenCommandBuffer, SyncsKept;
#if STRICT_SYNC_PACER
        private StrictSyncPacer _strictSyncPacer; // the production pacer (Pacer.cs, from the prepared GpuContext.cs)
#endif
        private static readonly System.Reflection.FieldInfo LastStrictSubmission = typeof(GpuContext).GetField("_lastStrictSubmission",
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        private static readonly System.Reflection.FieldInfo DeferredReportSince = typeof(GpuContext).GetField("_deferredReportSince",
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);

        // The production CreateHostSyncIfNeeded, for what the queue relies on: a Strict sync submits the open command buffer
        // (the renderer runs the submission), any other sync is created on it and waits for the next submission; a Strict,
        // unforced sync of a paced site may lose its Strict flag (the production pacer, when the prepared tree has one);
        // under the pacing policy a Strict submission is noted in the two fields the prepared queue reads (when it has them).
        public void CreateHostSyncIfNeeded(HostSyncFlags flags, [System.Runtime.CompilerServices.CallerMemberName] string caller = "")
        {
            HostSyncs.Add(flags);
            HostSyncCallers.Add(caller);
            FixtureTrace.Add("sync:" + flags);
            bool strict = (flags & HostSyncFlags.Strict) != 0, force = (flags & HostSyncFlags.Force) != 0;
#if STRICT_SYNC_PACER
            if (strict && !force && _strictSyncPacer.Defer(caller, System.Diagnostics.Stopwatch.GetTimestamp(), System.Diagnostics.Stopwatch.Frequency))
            {
                strict = false;
            }
#endif
            if (!strict)
            {
                KeptOnOpenCommandBuffer++;
                SyncsKept++;
                FixtureTrace.Add("kept:" + caller);
                return;
            }
            KeptOnOpenCommandBuffer = 0;
            FixtureTrace.Add("submit:" + caller);
            Renderer.Submit();
            if (PaceStrictHostSyncs)
            {
                LastStrictSubmission?.SetValue(this, System.Diagnostics.Stopwatch.GetTimestamp());
                DeferredReportSince?.SetValue(this, 0L);
            }
        }

        public void AdvanceSequence() { }
    }

    public enum SyncpointbOperation { Wait, Incr }

    public sealed class FifoState
    {
        public SyncpointbOperation SyncpointbOperation;
        public int SyncpointbSyncptIndex;
        public int SyncpointaPayload;
    }

    public sealed class FifoStateHolder
    {
        public FifoState State = new();
    }

    public sealed class TextureManagerBoundary
    {
        public void RefreshModifiedTextures() => FixtureTrace.Add("refresh");
    }

    public sealed class ChannelBoundary
    {
        public readonly TextureManagerBoundary TextureManager = new();
    }

    // GPFifoClass.Syncpointb, compiled from the adapted source, with the state and channel it reads.
    partial class FifoClassProbe
    {
        private readonly GpuContext _context;
        private readonly ChannelBoundary _parent = new();
        private readonly FifoStateHolder _state = new();

        public FifoClassProbe(GpuContext context) { _context = context; }

        public void Increment(uint id)
        {
            _state.State.SyncpointbOperation = SyncpointbOperation.Incr;
            _state.State.SyncpointbSyncptIndex = (int)id;
            Syncpointb(0);
        }

        public void Wait(uint id, uint threshold)
        {
            _state.State.SyncpointbOperation = SyncpointbOperation.Wait;
            _state.State.SyncpointbSyncptIndex = (int)id;
            _state.State.SyncpointaPayload = (int)threshold;
            Syncpointb(0);
        }
    }

    public sealed class EventBoundary
    {
        public readonly List<int> Timeouts = new();
        public bool WaitOne(int milliseconds)
        {
            Timeouts.Add(milliseconds);
            return false;
        }
    }

    // GPFifoDevice.WaitForCommands, compiled from the adapted source, with an empty command queue.
    partial class FifoDeviceProbe
    {
        private readonly GpuContext _context;
        private readonly ConcurrentQueue<int> _commandBufferQueue = new();
        public readonly EventBoundary _event = new();

        public FifoDeviceProbe(GpuContext context) { _context = context; }
    }

    internal sealed class MemoryManagerBoundary
    {
        public readonly Ryujinx.Graphics.Gpu.Memory.CounterCache CounterCache;
        public MemoryManagerBoundary(Ryujinx.Graphics.Gpu.Memory.CounterCache cache) { CounterCache = cache; }
    }

    internal sealed class ReportChannelBoundary
    {
        public MemoryManagerBoundary MemoryManager;
    }

    // SemaphoreUpdater.ReportCounter's guard (adapt_queued_3d_syncpoints), then CounterCache.AddOrUpdate as it follows
    // (compiled from a prepared tree only).
    partial class ReportProbe
    {
        private readonly GpuContext _context;
        private readonly ReportChannelBoundary _channel = new();
        public ReportProbe(GpuContext context, Ryujinx.Graphics.Gpu.Memory.CounterCache cache)
        {
            _context = context;
            _channel.MemoryManager = new MemoryManagerBoundary(cache);
        }
    }

    // GPFifoDevice.DispatchCallsCore's block after each GPFIFO entry (adapt_queued_3d_syncpoints).
    partial class EntryProbe
    {
        private readonly GpuContext _context;
        public EntryProbe(GpuContext context) { _context = context; }
    }

    // ThreedClass.IncrementSyncpoint (the 3D engine's syncpoint method), compiled from the adapted source.
    partial class ThreedProbe
    {
        private readonly GpuContext _context;

        public ThreedProbe(GpuContext context) { _context = context; }

        public void Increment(uint id) => IncrementSyncpoint((int)id);
    }
}
