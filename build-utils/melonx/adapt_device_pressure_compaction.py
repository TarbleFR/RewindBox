"""The existing heap compaction also runs while the DEVICE is short of memory: in a presentation gap of 250 ms or more,
bounded by a pause budget (every title).

Evidence (private journals of IPA 822, Hogwarts Legacy, 96 s of play; counts and durations only):
- The first-frame compaction (adapt_safe_point_compaction) gave the large object heap's free space back: LOH 497 MiB
  (237 free) -> 264 MiB (0 free), footprint 2 634 -> 2 402 MiB, 83 ms. After it the LOH was 452 MiB with 115 to 250 MiB
  free after each background collection of the play (217 MiB free in the last memoryInventory sample, gen2 plus LOH
  free 228 MiB); nothing gave it back.
- The play-time compaction (adapt_stall_compaction, "presentationGap") never ran: adapt_streaming_memory lets it run only
  at a PROCESS headroom of 256 MiB or less, and the process headroom stayed 2.2 to 2.35 GB while the DEVICE had 7 to 10 %
  available from t = 52 s (memoryWarning at 8 %), footprint 4.4 to 4.6 GB, iOS compressing up to 4.9 GB; one 1 400 ms
  freeze held 24 638 page decompressions and 70 594 page faults in 1.27 s.
- Gaps of the session (performance log freezes): 18 of 100 ms or more, 5 of 250 ms or more (433, 400, 1 400, 483, 867
  ms), three of them after t = 52 s.

Change (src/Ryujinx.Library/EmbeddedMemory.cs only; the class's other rules, their gates and its line are unchanged):
- The keep-alive's poll (every 250 ms) also asks a device-pressure rule, before the presentation-gap rule and only where
  that rule cannot run (a process headroom over its 256 MiB: at 256 MiB or less the presentation-gap rule decides, as
  before). It holds when all of these do: the device reports 10 % or less available (kern.memorystatus_level, read once per poll only while a
  gap of 250 ms or more lasts), gen2 plus the LOH had 192 MiB or more free at the last collection, no frame was presented
  for 250 ms, the render thread is not in one drain of 125 ms or more (a compile freeze or a GPU wait: adapt_stall_
  compaction_drain_guard's measure), no background collection is in progress (a blocking collection asked during one
  would first wait for it and then stop the engine outside the gap), the session's first frame is 20 s old, the last
  compaction of any kind is 60 s old, fewer than 3 such compactions ran in the session, their pauses total under 600 ms,
  its pause is predicted at 300 ms or less, and no stop is requested. The prediction is the live gen2 and LOH bytes of the
  last collection times the pause per live MiB of the session's last compaction (every session's first-frame one: IPA
  822, 83 ms for 264 + 107 MiB, 0.22 ms per MiB, so about 125 ms for the 246 + 314 MiB of its play), 0.5 ms per MiB
  before any (the gate's host). It then runs the existing compaction (Compact: one blocking compacting gen2, the LOH once,
  behind its gate) with the reason "devicePressure"; inside the gate, right before collecting, it is refused if a frame
  was presented, a host pause began, the render thread entered a drain of 125 ms or more, a background collection
  started or a stop was requested since the poll.
- Bounds: a pressure compaction whose pause passes 300 ms, or that gives back under 64 MiB of committed memory, or that
  spends the 600 ms budget, closes the rule for the session (journaled once). Never in a host pause (its own rule),
  never after a stop request or the session's end, never before the first frame's 20th second.
- Journal: each such compaction writes the existing "memory heapCompacted" line, reason "devicePressure <gap> ms gap,
  device <n>%, render drain <ms> ms, predicted pause <ms> ms, <native large buffers>"; a closed rule writes "memory pressureCompactionClosed";
  the session's end writes "memory pressureCompactions" once: gaps of 250 ms or more seen under pressure, compactions,
  pause total, refusals by reason, and the native large buffers of adapt_large_buffer_native (read through AppContext,
  so this adapter builds and runs without it).

Why a compaction costs less than it prevents (estimates from the log, not measured on an iPhone): it runs only inside a
gap of 250 ms or more that the game already shows, so it lengthens a freeze instead of adding one; its pause is bounded
by the session's budget (600 ms, 300 at most each; first frame 83 ms for 264 MiB of live LOH and 107 MiB of gen2). It
gives back what the first frame's gave (232 MiB of footprint for 237 MiB free), about 3 % of the device's memory, for
the rest of the session's play: memory iOS no longer compresses, and the LOH's holes no longer decompressed when reused.
Host (test/melonx_device_pressure_compaction_test.py, CoreCLR with the segments GC library and the Core's settings, the
IPA 822 situation with 211 MiB of LOH holes): the control compacts nothing in 1.5 s of gap; the candidate compacts at the
first poll past 250 ms (412-440 ms), LOH free 211 -> 0 MiB, committed 554 -> 343 MiB, resident 587 -> 382 MiB, pause
150-160 ms for 232 MiB of live LOH and 109 MiB of gen2 (this host's time); a heap of 900 MiB live is refused on its
prediction (410 ms); a pause of 321-347 ms closes the rule; nothing in a background gen2, a drain, a host pause, a stop.
Not changed: the first-frame and host-pause compactions, the presentation-gap rule and its process-headroom gate, the
keep-alive, the GC settings. Expected on the device (Hogwarts Legacy, same route): one or two "devicePressure"
heapCompacted lines after t = 20 s, each with pause under 300 ms and committed down by 150 MiB or more; the session's
"memory pressureCompactions" line. Refuted (and removed) if the pauses pass 300 ms (the line closes the rule), if the
footprint after a compaction is back within 30 s, or if freezes over 250 ms per minute rise above IPA 822's.
Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift: the file must be the Core 827
preparation's.
"""
import hashlib
from adapt_session import once

MEMORY = 'src/Ryujinx.Library/EmbeddedMemory.cs'
# The Core 827 preparation (after adapt_streaming_memory, the last adapter that edits this file).
BASELINE = {MEMORY: '7b2185f7752332af56e8710ba09911b1c6239cef70150706c64b71c76dda8cd9'}

END_OLD = '''    internal static void OnSessionEnd()
    {
        System.Threading.Interlocked.Increment(ref _pauseGeneration);
'''
END_NEW = '''    internal static void OnSessionEnd()
    {
        PressureSessionEnded(); // RewindBox (adapt_device_pressure_compaction): its summary line, once per session
        System.Threading.Interlocked.Increment(ref _pauseGeneration);
'''

WATCH_OLD = '''        ClearDrainRefusals(); // RewindBox (adapt_stall_compaction_drain_guard)
        System.Threading.Volatile.Write(ref _hostPaused, false);
    }
'''
WATCH_NEW = '''        ClearDrainRefusals(); // RewindBox (adapt_stall_compaction_drain_guard)
        ClearPressure(); // RewindBox (adapt_device_pressure_compaction)
        System.Threading.Volatile.Write(ref _hostPaused, false);
    }
'''

POLL_OLD = '''            // In play this is the whole poll: a frame was presented less than StallGapMs ago.
'''
POLL_NEW = '''            // RewindBox (adapt_device_pressure_compaction): the device-pressure rule first; true when it compacted or the
            // rule held (the gap rule, 8 s apart from any compaction, has nothing to add in that poll).
            if (PressurePoll(first, now, stamp, gap))
            {
                return;
            }

            // In play this is the whole poll: a frame was presented less than StallGapMs ago.
'''

RULE_OLD = '''    // RewindBox (adapt_stall_compaction_drain_guard) end

    private static void Compact('''
RULE_NEW = '''    // RewindBox (adapt_stall_compaction_drain_guard) end

    // RewindBox (adapt_device_pressure_compaction) begin
    // IPA 822, Hogwarts Legacy: the device at 7-10 % available for the last 44 s of play (memoryWarning at 8 %) while the
    // process stayed 2.2-2.35 GB under its own limit, so the presentation-gap rule, gated on the process's headroom, never
    // ran, and the large object heap held 228-262 MiB free after every background collection (the first frame's
    // compaction had given 232 MiB of footprint back in 83 ms). Under device pressure the same compaction runs in a gap
    // the game already shows, bounded per session: see ShouldCompactUnderPressure and NotePressureCompaction.
    internal const int PressureDevicePercent = 10;
    internal const int PressureGapMs = 250;
    internal const int PressureDrainMs = PressureGapMs / 2;
    internal const long PressureReclaimableBytes = 192 * MiB;
    internal const long PressureAfterFirstFrameMs = 20_000;
    internal const long PressureIntervalMs = 60_000;
    internal const int PressureMaxPerSession = 3;
    internal const double PressureSinglePauseMs = 300;
    internal const double PressurePauseBudgetMs = 600;
    internal const long PressureMinimumGainBytes = 64 * MiB;
    // A compaction's pause grows with what it moves: the live gen2 and LOH bytes. The ratio of this session's last
    // compaction (IPA 822's first frame: 83 ms for 264 + 107 MiB live, 0.22 ms per MiB) predicts the next one; before any,
    // 0.5 ms per MiB (the gate's host: 160 ms for 341 MiB). A prediction over PressureSinglePauseMs refuses.
    internal const double PressureDefaultMsPerLiveMiB = 0.5;

    [System.ThreadStatic]
    private static bool _pressureInFlight; // set on the poll's thread around its call of Compact
    private static long _pressureStamp; // the presentation stamp the poll saw (poll thread only)
    private static int _pressureCompactions;
    private static double _pressurePauseMs;
    private static bool _pressureClosed;
    private static string _pressureClosedWhy = string.Empty;
    private static int _pressureSummaryWritten = 1; // no session runs until WatchStalls
    private static double _lastPauseMs; // of the last Compact that collected
    private static double _msPerLiveMiB; // its pause per MiB of live gen2 and LOH after it; 0: none measured
    private static long _lastCommittedGainBytes;
    // The gaps of 250 ms or more seen under pressure (one per presentation stamp) and why each refusal was made.
    private static long _pressureGapStamp;
    private static int _pressureGaps, _refusedFree, _refusedFirstFrame, _refusedInterval, _refusedDrain, _refusedBackground,
        _refusedBudget, _refusedStop, _refusedAtGate, _refusedPredicted;
    // The background-collection watch: a gen2 is counted when it starts (GC.CollectionCount), its record changes when
    // it ends (GCKind.Background, GCKind.FullBlocking). Poll thread only.
    private static long _gen2Baseline = -1, _backgroundIndexSeen = -1, _blockingIndexSeen = -1;

    internal static int PressureCompactions => System.Threading.Volatile.Read(ref _pressureCompactions);
    internal static bool PressureClosed => System.Threading.Volatile.Read(ref _pressureClosed);

    internal static bool ShouldCompactUnderPressure(int devicePercent, long reclaimable, long sinceFirstFrameMs, long gapMs, long drainMs,
        long sinceLastCompactionMs, int done, double pausedMs, bool closed, bool backgroundRunning, double predictedPauseMs) =>
        devicePercent >= 0 && devicePercent <= PressureDevicePercent && !closed && !backgroundRunning &&
        reclaimable >= PressureReclaimableBytes && sinceFirstFrameMs >= PressureAfterFirstFrameMs && gapMs >= PressureGapMs &&
        drainMs < PressureDrainMs && sinceLastCompactionMs >= PressureIntervalMs && done >= 0 && done < PressureMaxPerSession &&
        pausedMs < PressurePauseBudgetMs && predictedPauseMs <= PressureSinglePauseMs;

    // The live gen2 and LOH bytes of a collection's record (size less free space), in MiB.
    internal static double LiveMiB(System.GCMemoryInfo info)
    {
        System.ReadOnlySpan<System.GCGenerationInfo> generations = info.GenerationInfo;
        return generations.Length > 3 ? (double)(generations[2].SizeAfterBytes - generations[2].FragmentationAfterBytes +
            generations[3].SizeAfterBytes - generations[3].FragmentationAfterBytes) / MiB : 0;
    }

    internal static double PredictedPauseMs(System.GCMemoryInfo info)
    {
        double ratio = System.Threading.Volatile.Read(ref _msPerLiveMiB);
        return (ratio > 0 ? ratio : PressureDefaultMsPerLiveMiB) * LiveMiB(info);
    }

    // Every poll of a presenting session: true while a gen2 that started has not ended (or one started and the watch has
    // not seen an end yet). A gen2 that starts and ends within one poll is seen as ended.
    internal static bool BackgroundCollectionRunning()
    {
        long background = System.GC.GetGCMemoryInfo(System.GCKind.Background).Index;
        long blocking = System.GC.GetGCMemoryInfo(System.GCKind.FullBlocking).Index;
        long started = System.GC.CollectionCount(2);

        if (_gen2Baseline < 0 || background != _backgroundIndexSeen || blocking != _blockingIndexSeen)
        {
            _backgroundIndexSeen = background;
            _blockingIndexSeen = blocking;
            _gen2Baseline = started;
            return false;
        }

        return started > _gen2Baseline;
    }

    private static bool PressurePoll(long first, long now, long stamp, long gap)
    {
        bool running = BackgroundCollectionRunning();

        // At a process headroom the presentation-gap rule accepts (adapt_streaming_memory), that rule decides, unchanged:
        // this one covers only the device short while the process is far from its own limit.
        if (gap < PressureGapMs || System.Threading.Volatile.Read(ref _pressureClosed) || !Ryujinx.Memory.HostMemoryBudget.IsConstrained ||
            MayCompactInGap(Ryujinx.Memory.HostMemoryBudget.AvailableBytes))
        {
            return false;
        }

        int device = Ryujinx.Memory.HostMemoryBudget.DeviceAvailablePercent;

        if (device < 0 || device > PressureDevicePercent)
        {
            return false;
        }

        bool newGap = _pressureGapStamp != stamp;
        _pressureGapStamp = stamp;
        _pressureGaps += newGap ? 1 : 0;

        int done = System.Threading.Volatile.Read(ref _pressureCompactions);
        long last = System.Threading.Interlocked.Read(ref _lastCompaction);
        long sinceLast = last == 0 ? long.MaxValue : now - last;
        System.GCMemoryInfo info = System.GC.GetGCMemoryInfo();
        long reclaimable = ReclaimableBytes(info);
        double predicted = PredictedPauseMs(info);
        long drain = Ryujinx.Common.EmbeddedPerformanceDiagnostics.RenderDrainInFlightMs();
        double paused = System.Threading.Volatile.Read(ref _pressurePauseMs);

        if (!ShouldCompactUnderPressure(device, reclaimable, now - first, gap, drain, sinceLast, done, paused, false, running, predicted))
        {
            if (newGap)
            {
                // The first reason that refused it, once per gap.
                if (done >= PressureMaxPerSession || paused >= PressurePauseBudgetMs) _refusedBudget++;
                else if (running) _refusedBackground++;
                else if (now - first < PressureAfterFirstFrameMs) _refusedFirstFrame++;
                else if (sinceLast < PressureIntervalMs) _refusedInterval++;
                else if (reclaimable < PressureReclaimableBytes) _refusedFree++;
                else if (predicted > PressureSinglePauseMs) _refusedPredicted++;
                else if (drain >= PressureDrainMs) _refusedDrain++;
            }

            return false;
        }

        System.Func<bool> stopping = System.Threading.Volatile.Read(ref _stopping);

        if (stopping != null && stopping())
        {
            _refusedStop++;
            return true;
        }

        int before = System.Threading.Volatile.Read(ref Compactions);
        string reason = string.Create(System.Globalization.CultureInfo.InvariantCulture,
            $"devicePressure {gap} ms gap, device {device}%, render drain {drain} ms, predicted pause {predicted:F0} ms, {DescribeLargeBuffers()}");

        _pressureStamp = stamp;
        _pressureInFlight = true;

        try
        {
            Compact(reason);
        }
        finally
        {
            _pressureInFlight = false;
        }

        if (System.Threading.Volatile.Read(ref Compactions) != before)
        {
            NotePressureCompaction();
        }
        else
        {
            _refusedAtGate++;
        }

        return true;
    }

    // Inside the gate, right before collecting, for the device-pressure compaction only: what may have changed since the
    // poll saw the gap.
    private static bool PressureRefusedAtGate()
    {
        if (!_pressureInFlight)
        {
            return false;
        }

        System.Func<bool> stopping = System.Threading.Volatile.Read(ref _stopping);

        return System.Threading.Volatile.Read(ref _lastPresent) != _pressureStamp || System.Threading.Volatile.Read(ref _hostPaused) ||
            System.Threading.Volatile.Read(ref _firstPresent) == 0 || (stopping != null && stopping()) ||
            Ryujinx.Common.EmbeddedPerformanceDiagnostics.RenderDrainInFlightMs() >= PressureDrainMs || BackgroundCollectionRunning();
    }

    private static void NotePressureCompaction()
    {
        double pause = System.Threading.Volatile.Read(ref _lastPauseMs);
        long gain = System.Threading.Interlocked.Read(ref _lastCommittedGainBytes);
        double total = System.Threading.Volatile.Read(ref _pressurePauseMs) + pause;

        System.Threading.Volatile.Write(ref _pressurePauseMs, total);
        System.Threading.Interlocked.Increment(ref _pressureCompactions);

        string why = pause > PressureSinglePauseMs ? Invariant($"a pause of {pause:F1} ms (over {PressureSinglePauseMs} ms)") :
            gain < PressureMinimumGainBytes ? Invariant($"{gain / MiB} MiB of committed memory given back (under {PressureMinimumGainBytes / MiB} MiB)") :
            total >= PressurePauseBudgetMs ? Invariant($"{total:F1} ms paused in the session (budget {PressurePauseBudgetMs} ms)") : null;

        if (why != null)
        {
            _pressureClosedWhy = why;
            System.Threading.Volatile.Write(ref _pressureClosed, true);
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("memory", "pressureCompactionClosed", detail:
                Invariant($"no more device-pressure compactions in this session: {why}; compactions {PressureCompactions}, ") +
                Invariant($"paused {total:F1} ms (adapt_device_pressure_compaction)"));
        }
    }

    private static string Invariant(System.FormattableString text) => text.ToString(System.Globalization.CultureInfo.InvariantCulture);

    // The native large buffers of adapt_large_buffer_native, when that adapter is in the build (it publishes them).
    private static string DescribeLargeBuffers() =>
        System.AppContext.GetData("RewindBox.LargeBuffers") is System.Func<string> describe ? describe() : "native large buffers none";

    private static void ClearPressure()
    {
        System.Threading.Volatile.Write(ref _pressureCompactions, 0);
        System.Threading.Volatile.Write(ref _pressurePauseMs, 0);
        System.Threading.Volatile.Write(ref _pressureClosed, false);
        _pressureClosedWhy = string.Empty;
        _pressureGapStamp = 0;
        _pressureGaps = _refusedFree = _refusedFirstFrame = _refusedInterval = _refusedDrain = _refusedBackground = 0;
        _refusedBudget = _refusedStop = _refusedAtGate = _refusedPredicted = 0;
        _gen2Baseline = _backgroundIndexSeen = _blockingIndexSeen = -1;
        System.Threading.Volatile.Write(ref _pressureSummaryWritten, 0);
    }

    private static void PressureSessionEnded()
    {
        if (System.Threading.Interlocked.Exchange(ref _pressureSummaryWritten, 1) != 0)
        {
            return;
        }

        try
        {
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("memory", "pressureCompactions", detail:
                Invariant($"gaps of {PressureGapMs} ms or more at {PressureDevicePercent}% available or less {_pressureGaps}; compactions ") +
                Invariant($"{PressureCompactions}, paused {System.Threading.Volatile.Read(ref _pressurePauseMs):F1} ms; refused: free under ") +
                Invariant($"{PressureReclaimableBytes / MiB} MiB {_refusedFree}, before {PressureAfterFirstFrameMs / 1000} s of play {_refusedFirstFrame}, ") +
                Invariant($"within {PressureIntervalMs / 1000} s of a compaction {_refusedInterval}, predicted pause over {PressureSinglePauseMs} ms ") +
                Invariant($"{_refusedPredicted} (at {System.Threading.Volatile.Read(ref _msPerLiveMiB):F3} ms per live MiB), render drain {_refusedDrain}, background collection ") +
                Invariant($"{_refusedBackground}, bounds {_refusedBudget}, stop {_refusedStop}, at the gate {_refusedAtGate}; closed ") +
                Invariant($"{(PressureClosed ? _pressureClosedWhy : "no")}; {DescribeLargeBuffers()} (adapt_device_pressure_compaction)"));
        }
        catch
        {
        }
    }
    // RewindBox (adapt_device_pressure_compaction) end

    private static void Compact('''

GATE_OLD = '''            System.GCMemoryInfo before = System.GC.GetGCMemoryInfo();
'''
GATE_NEW = '''            // RewindBox (adapt_device_pressure_compaction): the device-pressure compaction's own checks, right before collecting.
            if (PressureRefusedAtGate())
            {
                return;
            }

            System.GCMemoryInfo before = System.GC.GetGCMemoryInfo();
'''

RESULT_OLD = '''            System.Threading.Interlocked.Increment(ref Compactions);
'''
RESULT_NEW = '''            // RewindBox (adapt_device_pressure_compaction): what this collection cost and gave back, for the pressure rule's bounds.
            System.Threading.Volatile.Write(ref _lastPauseMs, after.PauseDurations[0].TotalMilliseconds);
            System.Threading.Interlocked.Exchange(ref _lastCommittedGainBytes, before.TotalCommittedBytes - after.TotalCommittedBytes);
            double liveAfter = LiveMiB(after);
            if (liveAfter >= 64)
            {
                System.Threading.Volatile.Write(ref _msPerLiveMiB, after.PauseDurations[0].TotalMilliseconds / liveAfter);
            }
            System.Threading.Interlocked.Increment(ref Compactions);
'''

PAIRS = (
    (END_OLD, END_NEW),
    (WATCH_OLD, WATCH_NEW),
    (POLL_OLD, POLL_NEW),
    (RULE_OLD, RULE_NEW),
    (GATE_OLD, GATE_NEW),
    (RESULT_OLD, RESULT_NEW),
)


def apply(source):
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter or a gate records the pairs
    for name, expected in digests:
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(source / MEMORY, old, new)
    return [source / MEMORY]
