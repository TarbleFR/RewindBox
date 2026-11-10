using System;
using System.Threading;

namespace Ryujinx.Common;

// Audio pacing counters for the host's per-second performance journal.
// The audio renderer's DSP thread is paced by wall clock in 5 ms periods
// (AudioProcessor.Wait, waking every 1 ms); the Apple backend plays what the
// DSP produced. A late DSP wake-up or an empty host queue is heard as a gap.
// Totals are cumulative (the host takes deltas); maxima reset when read.
public static class EmbeddedAudioPacing
{
    public const int Count = 9;
    // A DSP period that ends more than this after its due time counts as late.
    public const long LateThresholdNs = 2_000_000;
    // A host pause stops the guest and its audio. On resume, DSP periods due
    // and output starvations begun before it, plus this catch-up, are the
    // pause, not a stutter.
    public const long ResumeGraceNs = 50_000_000;

    private static long _dspPeriods, _dspLate, _dspLateNs, _dspMaxLateNs, _dspSkipped;
    // Only the audio renderer's DSP thread calls DspPeriod.
    private static bool _dspWasLate;
    private static long _hostCompleted, _hostStarvations, _hostStarvedNs, _hostMaxStarvedNs;
    private static long _resumedAtNs;

    // The guest resumed from a host pause (Horizon.TogglePauseEmulation).
    public static void Resumed(long nowNs) => Interlocked.Exchange(ref _resumedAtNs, Math.Max(1, nowNs));

    private static bool SpansPause(long ns)
    {
        long resumed = Interlocked.Read(ref _resumedAtNs);
        return resumed != 0 && ns < resumed + ResumeGraceNs;
    }

    // One DSP period, due at `dueNs`, finished waiting at `nowNs`. After a
    // stall the next periods run back to back and are late by less and less:
    // one late episode, counted once with its first (largest) lateness.
    public static void DspPeriod(long dueNs, long nowNs)
    {
        Interlocked.Increment(ref _dspPeriods);
        long lateNs = nowNs - dueNs;
        bool late = lateNs > LateThresholdNs && !SpansPause(dueNs), continuing = _dspWasLate;
        _dspWasLate = late;
        if (!late) return;
        Max(ref _dspMaxLateNs, lateNs);
        if (continuing) return;
        Interlocked.Increment(ref _dspLate);
        Interlocked.Add(ref _dspLateNs, lateNs);
    }

    // The DSP skipped `frames` periods, the first due at `dueNs`, because it
    // judged the backend too far ahead.
    public static void DspSkipped(long frames, long dueNs)
    {
        if (frames > 0 && !SpansPause(dueNs)) Interlocked.Add(ref _dspSkipped, frames);
    }

    // Each output session owns `starvedSince` (0 when no interval is open), so
    // concurrent sessions and a closed session never measure each other.

    // The host finished playing one buffer; `queueEmpty` when nothing else is
    // scheduled, so the output plays silence until the next buffer arrives.
    public static void HostCompleted(ref long starvedSince, bool queueEmpty, long nowNs)
    {
        Interlocked.Increment(ref _hostCompleted);
        if (queueEmpty) Interlocked.CompareExchange(ref starvedSince, Math.Max(1, nowNs), 0);
    }

    // The host received a buffer; ends a starvation interval if one is open.
    public static void HostQueued(ref long starvedSince, long nowNs)
    {
        long since = Interlocked.Exchange(ref starvedSince, 0);
        if (since == 0 || SpansPause(since)) return;
        long gap = Math.Max(0, nowNs - since);
        Interlocked.Increment(ref _hostStarvations);
        Interlocked.Add(ref _hostStarvedNs, gap);
        Max(ref _hostMaxStarvedNs, gap);
    }

    // The guest stopped the output: its silence is not a starvation.
    public static void HostIdle(ref long starvedSince) => Interlocked.Exchange(ref starvedSince, 0);

    // [0] DSP periods, [1] late episodes, [2] their total lateness ns (each by
    // its first period), [3] max lateness ns since the last read, [4] skipped periods, [5] host buffers completed,
    // [6] host starvations, [7] total starved ns, [8] max starved ns since the last read.
    public static void Snapshot(Span<long> values)
    {
        if (values.Length != Count) throw new ArgumentException("Audio pacing snapshot needs " + Count + " values.");
        values[0] = Interlocked.Read(ref _dspPeriods);
        values[1] = Interlocked.Read(ref _dspLate);
        values[2] = Interlocked.Read(ref _dspLateNs);
        values[3] = Interlocked.Exchange(ref _dspMaxLateNs, 0);
        values[4] = Interlocked.Read(ref _dspSkipped);
        values[5] = Interlocked.Read(ref _hostCompleted);
        values[6] = Interlocked.Read(ref _hostStarvations);
        values[7] = Interlocked.Read(ref _hostStarvedNs);
        values[8] = Interlocked.Exchange(ref _hostMaxStarvedNs, 0);
    }

    private static void Max(ref long target, long value)
    {
        long current = Interlocked.Read(ref target);
        while (value > current)
        {
            long seen = Interlocked.CompareExchange(ref target, value, current);
            if (seen == current) return;
            current = seen;
        }
    }
}
