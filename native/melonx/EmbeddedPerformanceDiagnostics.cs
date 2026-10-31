using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace Ryujinx.Common;

// Completed CPU wall-time scopes, not physical GPU timestamps. Nested/parallel
// phases overlap and must not be summed as frame time. No hot-path formatting,
// callbacks, locks or IO. Per-command counters use bounded owner-thread slots.
public static partial class EmbeddedPerformanceDiagnostics
{
    public enum Phase { GpuDispatch, GpuFifoWait, RenderDrain, RenderIdle, SyncInvoke,
        FrameWait, QueueBackpressure, QueryReadback, BufferReadback,
        GraphicsPipelineBuild, ComputePipelineBuild, CounterReports, CacheSizeProbe, CacheSave, Count }
    public enum Counter { Draws, Dispatches, BarrierRequests, SpanFallbacks,
        SpanFallbackBytes, CounterReportBatches, CounterReportsFlushed, CacheExports, CacheExportBytes,
        VirtualDependencySingle, VirtualDependencyMultiple, Count }
    private const int ThreadSlots = 16;
    private const double IntervalSeconds = 5;
    private static readonly string[] PhaseNames = { "gpuDispatch", "gpuFifoWait", "renderDrain", "renderIdle",
        "syncInvoke", "frameWait", "queueBackpressure", "queryReadback", "bufferReadback",
        "graphicsPipelineBuild", "computePipelineBuild", "counterReports", "cacheSizeProbe", "cacheSave" };
    private static readonly string[] CounterNames = { "draws", "dispatches", "barrierRequests", "spanFallbacks",
        "spanFallbackBytes", "counterReportBatches", "counterReportsFlushed", "cacheExports", "cacheExportBytes",
        "virtualDependencySingle", "virtualDependencyMultiple" };

    private sealed class Epoch
    {
        public readonly long Generation;
        public readonly long[] Calls = new long[(int)Phase.Count], Ticks = new long[(int)Phase.Count],
            Bytes = new long[(int)Phase.Count], LastCalls = new long[(int)Phase.Count],
            LastTicks = new long[(int)Phase.Count], LastBytes = new long[(int)Phase.Count];
        public readonly long[][] Counters = new long[ThreadSlots][];
        public readonly long[] LastCounters = new long[(int)Counter.Count];
        public readonly long[] FirstStarts = new long[(int)Phase.Count];
        public readonly int[] Active = new int[(int)Phase.Count];
        public readonly long[] MaxReportBatch = new long[ThreadSlots];
        public int Slots, DroppedThreadRegistrations, Sampling, StopRequested, Finalized;
        public long PreviousTimestamp, PreviousAllocation, PreviousPauseTicks;
        public readonly int[] PreviousCollections = new int[3];
        public Epoch(long generation)
        {
            Generation = generation;
            for (int i = 0; i < ThreadSlots; i++) Counters[i] = new long[(int)Counter.Count];
            PreviousTimestamp = Stopwatch.GetTimestamp();
            PreviousAllocation = GC.GetTotalAllocatedBytes(false);
            PreviousPauseTicks = GC.GetTotalPauseDuration().Ticks;
            for (int i = 0; i < 3; i++) PreviousCollections[i] = GC.CollectionCount(i);
        }
    }
    private static Epoch _current;
    [ThreadStatic] private static Epoch _counterEpoch;
    [ThreadStatic] private static int _counterSlot;

    // Accepted session ownership serializes Start/Stop. Scopes retain their own
    // epoch, so late completion cannot charge a later game's counters.
    public static void Start(long generation)
    {
        try
        {
            EmbeddedLaunchDiagnostics.BeginPerformance(generation);
            Interlocked.Exchange(ref _current, new Epoch(generation));
            EmbeddedLaunchDiagnostics.PerformanceObserver = PollCurrent;
        }
        catch { Interlocked.Exchange(ref _current, null); }
    }

    public static void Stop(long generation)
    {
        Epoch epoch = Volatile.Read(ref _current);
        if (epoch == null || epoch.Generation != generation) return;
        Volatile.Write(ref epoch.StopRequested, 1);
        // Never wait for a reader. Its finally publishes the final partial
        // window if it was already capturing when Stop detached the epoch.
        Interlocked.CompareExchange(ref _current, null, epoch);
        Emit(epoch, Stopwatch.GetTimestamp(), final: true);
    }

    public readonly struct Scope : IDisposable
    {
        private readonly Epoch _epoch;
        private readonly int _phase;
        private readonly long _start, _allocated;
        private Scope(Epoch epoch, Phase phase)
        {
            _epoch = epoch; _phase = (int)phase;
            _start = Stopwatch.GetTimestamp();
            _allocated = GC.GetAllocatedBytesForCurrentThread();
            if (Interlocked.Increment(ref epoch.Active[_phase]) == 1)
                Interlocked.Exchange(ref epoch.FirstStarts[_phase], _start);
        }
        // All call sites are synchronous scopes on the creating thread: no
        // await, boxed IDisposable or captured delegate enters the hot path.
        public void Dispose()
        {
            if (_epoch == null) return;
            long elapsed = Stopwatch.GetTimestamp() - _start;
            long bytes = GC.GetAllocatedBytesForCurrentThread() - _allocated;
            Interlocked.Add(ref _epoch.Ticks[_phase], elapsed);
            Interlocked.Add(ref _epoch.Bytes[_phase], Math.Max(0, bytes));
            Interlocked.Increment(ref _epoch.Calls[_phase]);
            long first = Volatile.Read(ref _epoch.FirstStarts[_phase]);
            if (Interlocked.Decrement(ref _epoch.Active[_phase]) == 0)
                Interlocked.CompareExchange(ref _epoch.FirstStarts[_phase], 0, first);
        }
        internal static Scope Create(Phase phase)
        {
            Epoch epoch = Volatile.Read(ref _current);
            return epoch == null ? default : new Scope(epoch, phase);
        }
    }
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static Scope Measure(Phase phase) => Scope.Create(phase);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    private static int Slot(Epoch epoch)
    {
        if (!ReferenceEquals(_counterEpoch, epoch))
        {
            int slot = Interlocked.Increment(ref epoch.Slots) - 1;
            _counterEpoch = epoch;
            _counterSlot = slot < ThreadSlots ? slot : -1;
            if (slot >= ThreadSlots) Interlocked.Increment(ref epoch.DroppedThreadRegistrations);
        }
        return _counterSlot;
    }
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static void Count(Counter counter, long amount = 1)
    {
        Epoch epoch = Volatile.Read(ref _current);
        if (epoch == null) return;
        int slot = Slot(epoch);
        if (slot >= 0) epoch.Counters[slot][(int)counter] += amount;
    }
    public static void ReportBatch(int count)
    {
        Epoch epoch = Volatile.Read(ref _current);
        if (epoch == null) return;
        int slot = Slot(epoch);
        if (slot < 0) return;
        epoch.Counters[slot][(int)Counter.CounterReportBatches]++;
        epoch.MaxReportBatch[slot] = Math.Max(epoch.MaxReportBatch[slot], count);
    }

    [LibraryImport("libc", EntryPoint = "pthread_main_np")]
    private static partial int IsDarwinMainThread();

    // Recurring Snapshot calls run on the host's diagnostics utility queue.
    // One-off UIKit requests must not format JSON or inspect GC state there.
    public static void PollCurrent()
    {
        Epoch epoch = Volatile.Read(ref _current);
        if (epoch == null) return;
        if ((OperatingSystem.IsIOS() || OperatingSystem.IsMacOS() || OperatingSystem.IsMacCatalyst()) && IsDarwinMainThread() != 0) return;
        Poll(epoch.Generation);
    }
    public static void Poll(long generation)
    {
        Epoch epoch = Volatile.Read(ref _current);
        if (epoch == null || epoch.Generation != generation) return;
        long now = Stopwatch.GetTimestamp();
        if (now - Volatile.Read(ref epoch.PreviousTimestamp) < Stopwatch.Frequency * IntervalSeconds) return;
        Emit(epoch, now, final: false);
    }
    private static void Emit(Epoch epoch, long now, bool final)
    {
        if (Interlocked.CompareExchange(ref epoch.Sampling, 1, 0) != 0) return;
        bool finalReport = final || Volatile.Read(ref epoch.StopRequested) != 0;
        try
        {
            if (Volatile.Read(ref epoch.Finalized) != 0) return;
            if (!finalReport && !ReferenceEquals(epoch, Volatile.Read(ref _current))) return;
            string report = Capture(epoch, now, finalReport);
            if (report != null) EmbeddedLaunchDiagnostics.Record("performance", finalReport ? "final" : "sample",
                detail: report, performanceGeneration: epoch.Generation);
        }
        catch { } // Observability must never change the emulator's result.
        finally
        {
            if (finalReport) Volatile.Write(ref epoch.Finalized, 1);
            Volatile.Write(ref epoch.Sampling, 0);
            if (Volatile.Read(ref epoch.StopRequested) != 0 && Volatile.Read(ref epoch.Finalized) == 0)
                Emit(epoch, Stopwatch.GetTimestamp(), final: true);
        }
    }
    private static string Capture(Epoch epoch, long now, bool final)
    {
        double window = (now - epoch.PreviousTimestamp) * 1000.0 / Stopwatch.Frequency;
        if (!final && window < IntervalSeconds * 1000) return null;
        long allocated = GC.GetTotalAllocatedBytes(false), pause = GC.GetTotalPauseDuration().Ticks;
        GCMemoryInfo memory = GC.GetGCMemoryInfo();
        using var stream = new MemoryStream(3072);
        using (var json = new Utf8JsonWriter(stream))
        {
            json.WriteStartObject();
            json.WriteNumber("schema", 1); json.WriteNumber("generation", epoch.Generation);
            json.WriteNumber("windowMs", Math.Max(0, Math.Round(window, 3)));
            json.WriteBoolean("final", final);
            json.WriteString("scope", "completed-inclusive-cpu-wall; phases-overlap; allocations-current-thread; approximate-independent-deltas");
            json.WriteStartObject("phases");
            for (int i = 0; i < (int)Phase.Count; i++)
            {
                long calls = Volatile.Read(ref epoch.Calls[i]), ticks = Volatile.Read(ref epoch.Ticks[i]), bytes = Volatile.Read(ref epoch.Bytes[i]);
                json.WriteStartArray(PhaseNames[i]);
                json.WriteNumberValue(calls - epoch.LastCalls[i]);
                json.WriteNumberValue(Math.Round((ticks - epoch.LastTicks[i]) * 1000.0 / Stopwatch.Frequency, 3));
                json.WriteNumberValue(bytes - epoch.LastBytes[i]); json.WriteEndArray();
                epoch.LastCalls[i] = calls; epoch.LastTicks[i] = ticks; epoch.LastBytes[i] = bytes;
            }
            json.WriteEndObject();
            json.WriteString("phaseColumns", "completedCalls,wallMs,allocatedBytes");
            json.WriteStartObject("active");
            for (int i = 0; i < (int)Phase.Count; i++)
            {
                int active = Volatile.Read(ref epoch.Active[i]);
                if (active == 0) continue;
                long first = Volatile.Read(ref epoch.FirstStarts[i]);
                json.WriteStartArray(PhaseNames[i]); json.WriteNumberValue(active);
                // The first registered scope can finish while another overlaps;
                // this is not an exact oldest-active or physical stall timer.
                if (first == 0) json.WriteNullValue();
                else json.WriteNumberValue(Math.Max(0, Math.Round((now - first) * 1000.0 / Stopwatch.Frequency, 3)));
                json.WriteEndArray();
            }
            json.WriteEndObject();
            json.WriteString("activeColumns", "inFlightScopes,firstRegisteredStartAgeMsApprox");
            json.WriteStartObject("counts");
            int slots = Math.Min(ThreadSlots, Volatile.Read(ref epoch.Slots));
            for (int i = 0; i < (int)Counter.Count; i++)
            {
                long sum = 0;
                for (int slot = 0; slot < slots; slot++) sum += Volatile.Read(ref epoch.Counters[slot][i]);
                json.WriteNumber(CounterNames[i], sum - epoch.LastCounters[i]); epoch.LastCounters[i] = sum;
            }
            long maxBatch = 0;
            for (int slot = 0; slot < slots; slot++) maxBatch = Math.Max(maxBatch, Volatile.Read(ref epoch.MaxReportBatch[slot]));
            json.WriteNumber("counterReportBatchMaxSession", maxBatch);
            json.WriteNumber("untrackedCounterThreads", Volatile.Read(ref epoch.DroppedThreadRegistrations)); json.WriteEndObject();
            json.WriteStartObject("managed");
            json.WriteNumber("allocatedBytesApprox", Math.Max(0, allocated - epoch.PreviousAllocation));
            json.WriteNumber("gcPauseMs", Math.Max(0, (pause - epoch.PreviousPauseTicks) / (double)TimeSpan.TicksPerMillisecond));
            json.WriteNumber("lastGcIndex", memory.Index);
            json.WriteNumber("lastGcHeapBytes", memory.HeapSizeBytes);
            json.WriteNumber("lastGcCommittedBytes", memory.TotalCommittedBytes);
            json.WriteNumber("lastGcFragmentedBytes", memory.FragmentedBytes);
            json.WriteStartArray("collections");
            for (int i = 0; i < 3; i++)
            {
                int collections = GC.CollectionCount(i);
                json.WriteNumberValue(collections - epoch.PreviousCollections[i]); epoch.PreviousCollections[i] = collections;
            }
            json.WriteEndArray(); json.WriteEndObject(); json.WriteEndObject();
        }
        // Strings pass through the journal's real redactor and its 4096-char
        // bound. Emit no malformed truncated JSON if this schema ever grows.
        if (stream.Length > 4000) return null;
        epoch.PreviousTimestamp = now; epoch.PreviousAllocation = allocated; epoch.PreviousPauseTicks = pause;
        return Encoding.UTF8.GetString(stream.GetBuffer(), 0, (int)stream.Length);
    }
}
