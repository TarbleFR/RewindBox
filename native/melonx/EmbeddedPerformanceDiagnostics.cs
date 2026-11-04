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
        VirtualDependencySingle, VirtualDependencyMultiple, ReadCopies, ReadCopyBytes, PooledReads, PooledReadBytes, Count }
    // Inclusive CPU work per GPU subsystem: draws, compute, copies, texture/buffer/pool
    // synchronization and flushes, shader lookup and binding commits. Nested and
    // cross-thread scopes overlap; bytes are the executing thread's allocations.
    public enum Work { Draw, Compute, Dma, InlineToMemory, TextureSync, TextureFlush, TextureFlushAction,
        BufferLoad, BufferFlush, PoolSync, ShaderLookup, Bindings, Count }
    private const int ThreadSlots = 16;
    private const double IntervalSeconds = 5;
    private static readonly string[] WorkNames = { "draw", "compute", "dma", "i2m", "texSync", "texFlush",
        "texFlushAction", "bufLoad", "bufFlush", "poolSync", "shader", "bindings" };
    private static readonly string[] PhaseNames = { "gpuDispatch", "gpuFifoWait", "renderDrain", "renderIdle",
        "syncInvoke", "frameWait", "queueBackpressure", "queryReadback", "bufferReadback",
        "graphicsPipelineBuild", "computePipelineBuild", "counterReports", "cacheSizeProbe", "cacheSave" };
    private static readonly string[] CounterNames = { "draws", "dispatches", "barrierRequests", "spanFallbacks",
        "spanFallbackBytes", "counterReportBatches", "counterReportsFlushed", "cacheExports", "cacheExportBytes",
        "virtualDependencySingle", "virtualDependencyMultiple", "readCopies", "readCopyBytes", "pooledReads", "pooledReadBytes" };

    private sealed class Epoch
    {
        public readonly long Generation;
        public readonly long[] Calls = new long[(int)Phase.Count], Ticks = new long[(int)Phase.Count],
            Bytes = new long[(int)Phase.Count], LastCalls = new long[(int)Phase.Count],
            LastTicks = new long[(int)Phase.Count], LastBytes = new long[(int)Phase.Count];
        public readonly long[] WorkCalls = new long[(int)Work.Count], WorkTicks = new long[(int)Work.Count],
            WorkBytes = new long[(int)Work.Count], LastWorkCalls = new long[(int)Work.Count],
            LastWorkTicks = new long[(int)Work.Count], LastWorkBytes = new long[(int)Work.Count];
        public readonly long[][] Counters = new long[ThreadSlots][];
        public readonly long[] LastCounters = new long[(int)Counter.Count];
        public readonly long[] FirstStarts = new long[(int)Phase.Count];
        public readonly int[] Active = new int[(int)Phase.Count];
        public readonly long[] MaxReportBatch = new long[ThreadSlots];
        public int Slots, DroppedThreadRegistrations, Sampling, StopRequested, Finalized;
        public long PreviousTimestamp, PreviousAllocation, PreviousPauseTicks;
        public readonly int[] PreviousCollections = new int[3];
        // Gen2 collections already seen and written by the gcEvent journal lines (sampler-only state).
        public long SeenFullBlockingGcIndex, SeenBackgroundGcIndex, WrittenFullBlockingGcIndex, WrittenBackgroundGcIndex;
        public int SeenGen2Collections, GcEventLines, FullBlockingGcEventLines, BackgroundGcEventLines, SuppressedGcEventLines;
        public Epoch(long generation)
        {
            Generation = generation;
            for (int i = 0; i < ThreadSlots; i++) Counters[i] = new long[(int)Counter.Count];
            PreviousTimestamp = Stopwatch.GetTimestamp();
            PreviousAllocation = GC.GetTotalAllocatedBytes(false);
            PreviousPauseTicks = GC.GetTotalPauseDuration().Ticks;
            for (int i = 0; i < 3; i++) PreviousCollections[i] = GC.CollectionCount(i);
            // Collections that completed before this session are not its events.
            SeenFullBlockingGcIndex = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
            SeenBackgroundGcIndex = GC.GetGCMemoryInfo(GCKind.Background).Index;
            WrittenFullBlockingGcIndex = SeenFullBlockingGcIndex; WrittenBackgroundGcIndex = SeenBackgroundGcIndex;
            SeenGen2Collections = PreviousCollections[2];
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

    // Same completion contract as Scope, without in-flight tracking: these
    // scopes run per draw and per synchronization, so they stay three adds.
    public readonly struct WorkScope : IDisposable
    {
        private readonly Epoch _epoch;
        private readonly int _work;
        private readonly long _start, _allocated;
        private WorkScope(Epoch epoch, Work work)
        {
            _epoch = epoch; _work = (int)work;
            _start = Stopwatch.GetTimestamp();
            _allocated = GC.GetAllocatedBytesForCurrentThread();
        }
        public void Dispose()
        {
            if (_epoch == null) return;
            long elapsed = Stopwatch.GetTimestamp() - _start;
            long bytes = GC.GetAllocatedBytesForCurrentThread() - _allocated;
            Interlocked.Add(ref _epoch.WorkTicks[_work], elapsed);
            Interlocked.Add(ref _epoch.WorkBytes[_work], Math.Max(0, bytes));
            Interlocked.Increment(ref _epoch.WorkCalls[_work]);
        }
        internal static WorkScope Create(Work work)
        {
            Epoch epoch = Volatile.Read(ref _current);
            return epoch == null ? default : new WorkScope(epoch, work);
        }
    }
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static WorkScope Track(Work work) => WorkScope.Create(work);

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
            RecordGcEvents(epoch, finalReport);
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
    // One durable Core journal line per newly completed gen2 collection seen
    // by a sample: the latest blocking (GCKind.FullBlocking) and the latest
    // background collection, each when its index changed since the previous
    // sample, in index order. Only the latest of each kind is visible to a
    // sample; gen2CollectionsInWindow counts the gen2s since the previous one.
    // Each kind has its own budget per session, so background lines cannot
    // starve blocking ones; a line over budget is counted in suppressedLines
    // (carried by every later line). The final sample is never bounded and also
    // reports the latest collection of a kind whose line was suppressed, so the
    // collections after teardown and the suppressed count always reach the
    // journal: at most 2 * 16 + 2 lines per session. Sampler-only reads; never
    // on a hot path.
    private const int MaxGcEventLinesPerKind = 16;
    private static void RecordGcEvents(Epoch epoch, bool final)
    {
        try
        {
            GCMemoryInfo blocking = GC.GetGCMemoryInfo(GCKind.FullBlocking), background = GC.GetGCMemoryInfo(GCKind.Background);
            int gen2 = GC.CollectionCount(2), window = Math.Max(0, gen2 - epoch.SeenGen2Collections);
            bool newBlocking = blocking.Index != epoch.SeenFullBlockingGcIndex, newBackground = background.Index != epoch.SeenBackgroundGcIndex;
            epoch.SeenFullBlockingGcIndex = blocking.Index; epoch.SeenBackgroundGcIndex = background.Index;
            epoch.SeenGen2Collections = gen2;
            bool reportBlocking = newBlocking || (final && blocking.Index != epoch.WrittenFullBlockingGcIndex);
            bool reportBackground = newBackground || (final && background.Index != epoch.WrittenBackgroundGcIndex);
            bool backgroundFirst = reportBackground && background.Index < blocking.Index;
            if (backgroundFirst) RecordGcEvent(epoch, false, background, newBackground, window, final);
            if (reportBlocking) RecordGcEvent(epoch, true, blocking, newBlocking, window, final);
            if (reportBackground && !backgroundFirst) RecordGcEvent(epoch, false, background, newBackground, window, final);
        }
        catch { } // Observability must never change the emulator's result.
    }
    private static void RecordGcEvent(Epoch epoch, bool fullBlocking, GCMemoryInfo memory, bool newInWindow, int window, bool final)
    {
        string kind = fullBlocking ? "fullBlocking" : "background";
        int kindLines = fullBlocking ? epoch.FullBlockingGcEventLines : epoch.BackgroundGcEventLines;
        if (!final && kindLines >= MaxGcEventLinesPerKind) { epoch.SuppressedGcEventLines++; return; }
        if (fullBlocking) { epoch.FullBlockingGcEventLines = ++kindLines; epoch.WrittenFullBlockingGcIndex = memory.Index; }
        else { epoch.BackgroundGcEventLines = ++kindLines; epoch.WrittenBackgroundGcIndex = memory.Index; }
        int line = ++epoch.GcEventLines;
        using var stream = new MemoryStream(1024);
        using (var json = new Utf8JsonWriter(stream))
        {
            // Starts with '{': the journal redactor drops "name=value" lines.
            json.WriteStartObject();
            json.WriteNumber("schema", 1); json.WriteNumber("sessionGeneration", epoch.Generation);
            json.WriteNumber("line", line); json.WriteNumber("kindLine", kindLines);
            json.WriteNumber("maxLinesPerKind", MaxGcEventLinesPerKind); json.WriteNumber("suppressedLines", epoch.SuppressedGcEventLines);
            json.WriteBoolean("finalSample", final);
            json.WriteString("kind", kind); json.WriteBoolean("newInWindow", newInWindow);
            json.WriteNumber("index", memory.Index); json.WriteNumber("generation", memory.Generation);
            json.WriteNumber("concurrent", memory.Concurrent ? 1 : 0); json.WriteNumber("compacted", memory.Compacted ? 1 : 0);
            json.WriteStartArray("pauseMs");
            ReadOnlySpan<TimeSpan> pauses = memory.PauseDurations;
            for (int i = 0; i < 2; i++) json.WriteNumberValue(i < pauses.Length ? Math.Round(pauses[i].TotalMilliseconds, 3) : 0);
            json.WriteEndArray();
            json.WriteNumber("promotedBytes", memory.PromotedBytes);
            json.WriteNumber("heapSizeBytes", memory.HeapSizeBytes);
            ReadOnlySpan<GCGenerationInfo> generations = memory.GenerationInfo;
            for (int i = 2; i <= 3; i++)
            {
                json.WriteStartArray(i == 2 ? "gen2" : "loh");
                if (i < generations.Length)
                {
                    json.WriteNumberValue(generations[i].SizeBeforeBytes); json.WriteNumberValue(generations[i].FragmentationBeforeBytes);
                    json.WriteNumberValue(generations[i].SizeAfterBytes); json.WriteNumberValue(generations[i].FragmentationAfterBytes);
                }
                json.WriteEndArray();
            }
            json.WriteString("generationColumns", "sizeBeforeBytes,fragmentationBeforeBytes,sizeAfterBytes,fragmentationAfterBytes");
            json.WriteNumber("memoryLoadBytes", memory.MemoryLoadBytes);
            json.WriteNumber("highMemoryLoadThresholdBytes", memory.HighMemoryLoadThresholdBytes);
            json.WriteNumber("totalCommittedBytes", memory.TotalCommittedBytes);
            json.WriteNumber("gen2CollectionsInWindow", window);
            json.WriteEndObject();
        }
        EmbeddedLaunchDiagnostics.Record("gcEvent", kind, detail: Encoding.UTF8.GetString(stream.GetBuffer(), 0, (int)stream.Length));
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
            json.WriteStartObject("gpuWork");
            for (int i = 0; i < (int)Work.Count; i++)
            {
                long calls = Volatile.Read(ref epoch.WorkCalls[i]), ticks = Volatile.Read(ref epoch.WorkTicks[i]), bytes = Volatile.Read(ref epoch.WorkBytes[i]);
                json.WriteStartArray(WorkNames[i]);
                json.WriteNumberValue(calls - epoch.LastWorkCalls[i]);
                json.WriteNumberValue(Math.Round((ticks - epoch.LastWorkTicks[i]) * 1000.0 / Stopwatch.Frequency, 1));
                json.WriteNumberValue((bytes - epoch.LastWorkBytes[i]) >> 10); json.WriteEndArray();
                epoch.LastWorkCalls[i] = calls; epoch.LastWorkTicks[i] = ticks; epoch.LastWorkBytes[i] = bytes;
            }
            json.WriteEndObject();
            json.WriteString("gpuWorkColumns", "completedCalls,wallMs,allocatedKiB");
            json.WriteStartObject("managed");
            json.WriteNumber("allocatedBytesApprox", Math.Max(0, allocated - epoch.PreviousAllocation));
            json.WriteNumber("gcPauseMs", Math.Max(0, (pause - epoch.PreviousPauseTicks) / (double)TimeSpan.TicksPerMillisecond));
            json.WriteNumber("lastGcIndex", memory.Index);
            json.WriteNumber("lastGcHeapBytes", memory.HeapSizeBytes);
            json.WriteNumber("lastGcCommittedBytes", memory.TotalCommittedBytes);
            json.WriteNumber("lastGcFragmentedBytes", memory.FragmentedBytes);
            // The GC's own inputs for its gen2 decisions at that collection:
            // memory load versus its high-load threshold (device-wide on Apple
            // platforms), promotions, and which kind ran last. Numbers only.
            json.WriteNumber("lastGcGeneration", memory.Generation);
            json.WriteNumber("lastGcConcurrent", memory.Concurrent ? 1 : 0);
            json.WriteNumber("lastGcCompacted", memory.Compacted ? 1 : 0);
            json.WriteNumber("lastGcPromotedBytes", memory.PromotedBytes);
            json.WriteNumber("lastGcMemoryLoadBytes", memory.MemoryLoadBytes);
            json.WriteNumber("lastGcHighMemoryLoadThresholdBytes", memory.HighMemoryLoadThresholdBytes);
            json.WriteNumber("lastGcTotalAvailableMemoryBytes", memory.TotalAvailableMemoryBytes);
            json.WriteNumber("lastBackgroundGcIndex", GC.GetGCMemoryInfo(GCKind.Background).Index);
            json.WriteNumber("lastFullBlockingGcIndex", GC.GetGCMemoryInfo(GCKind.FullBlocking).Index);
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
