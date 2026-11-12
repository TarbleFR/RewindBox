using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Ryujinx.Library;

// The production EmbeddedHeapCompaction class (the candidate EmbeddedMemory.cs, between its markers, unchanged) next to
// three doubles: HostMemoryBudget (constrained, device share set by the fixture, footprint = this process's resident
// bytes), the launch journal and the Library's retention note.
// "policy": the rule at its limits. "replay": the rule on a recorded session (frames presented per second, free space
// after each collection, device share), polled every 250 ms as the keep-alive does, under the two placements of a
// second's single frame and with the seconds the journal has no record for counted as presenting or as gaps. "live": the render loop's stamps
// and the poll against the real collector: a heap with free large-object space is compacted once in a presentation
// gap, never while frames are presented, never when a stop is requested, never in a host pause, never after the
// session ended nor before the next one's first frame.
namespace Ryujinx.Memory
{
    public static class HostMemoryBudget
    {
        public static bool Constrained = true;
        public static bool IsConstrained => Constrained;
        public static int Device = 9;
        public static int DeviceAvailablePercent => Device;
        public static ulong FootprintBytes => (ulong)Environment.WorkingSet;
    }
}

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Lines = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            lock (Lines) Lines.Add(stage + " " + status + ": " + detail);
        }
    }
}

namespace Ryujinx.Library
{
    internal static class Library
    {
        internal static void RecordRetentionChain(string moment) { }
    }
}

static class Fixture
{
    const long MiB = 1024 * 1024;
    static readonly List<byte[]> Live = new();

    // A loading-like large object heap: arrays of 128 KiB to 8 MiB, every page touched, about half of them dying,
    // swept by a collection that does not compact (what the background collections do).
    static void LoadingBurst(int seed, long total)
    {
        Random random = new(seed);
        List<byte[]> all = new();
        long allocated = 0;
        while (allocated < total)
        {
            int size = random.Next(4) == 0 ? random.Next(1, 9) * (int)MiB : 128 * 1024 * random.Next(1, 8);
            byte[] array = new byte[size];
            for (int i = 0; i < size; i += 4096) array[i] = 1;
            all.Add(array);
            allocated += size;
        }
        for (int i = 0; i < all.Count; i += 2) Live.Add(all[i]);
        all.Clear();
        GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: false);
    }

    static long Reclaimable() => EmbeddedHeapCompaction.ReclaimableBytes(GC.GetGCMemoryInfo());
    static int Compactions => Volatile.Read(ref EmbeddedHeapCompaction.Compactions);

    // The render loop presenting at 30 frames per second and the keep-alive polling every 250 ms, for a duration.
    static void Play(int milliseconds)
    {
        long end = Environment.TickCount64 + milliseconds, nextPoll = Environment.TickCount64;
        while (Environment.TickCount64 < end)
        {
            EmbeddedHeapCompaction.NotePresented();
            if (Environment.TickCount64 >= nextPoll) { EmbeddedHeapCompaction.OnPoll(); nextPoll += 250; }
            Thread.Sleep(33);
        }
    }

    // Nothing presented: the poll alone, until a compaction ran or the duration passed. Returns ms until the compaction, or -1.
    static long Stall(int milliseconds)
    {
        int before = Compactions;
        long start = Environment.TickCount64;
        while (Environment.TickCount64 - start < milliseconds)
        {
            EmbeddedHeapCompaction.OnPoll();
            if (Compactions != before) return Environment.TickCount64 - start;
            Thread.Sleep(250);
        }
        return -1;
    }

    static object Policy()
    {
        long need = EmbeddedHeapCompaction.StallReclaimableBytes;
        bool Rule(long reclaimable = long.MaxValue, int device = 9, long first = 10_000, long present = 700, long compaction = 8_000, int done = 0) =>
            EmbeddedHeapCompaction.ShouldCompactInStall(reclaimable == long.MaxValue ? need : reclaimable, device, first, present, compaction, done);
        return new
        {
            atEveryLimit = Rule(), freeBelow = Rule(reclaimable: need - 1), device15 = Rule(device: 15), device16 = Rule(device: 16),
            deviceUnknown = Rule(device: -1), firstFrame9999 = Rule(first: 9_999), gap699 = Rule(present: 699), interval7999 = Rule(compaction: 7_999),
            neverCompacted = Rule(compaction: long.MaxValue), third = Rule(done: 2), fourth = Rule(done: 3),
            limits = new { freeMiB = need / MiB, gapMs = EmbeddedHeapCompaction.StallGapMs, afterFirstFrameMs = EmbeddedHeapCompaction.StallAfterFirstFrameMs,
                           intervalMs = EmbeddedHeapCompaction.StallIntervalMs, perSession = EmbeddedHeapCompaction.StallMaxPerSession },
        };
    }

    // The rule on a recorded session. fps[i]: frames presented during second i + 1 (null: no record for that second);
    // device[i]: device share that second; free[w]: gen2 + LOH free MiB after the last collection of the 5 s window w.
    static object Replay(string path, bool missingIsGap, bool sparseAtEnd)
    {
        using JsonDocument document = JsonDocument.Parse(File.ReadAllText(path));
        JsonElement root = document.RootElement;
        double?[] fps = root.GetProperty("fps").EnumerateArray().Select(e => e.ValueKind == JsonValueKind.Null ? (double?)null : e.GetDouble()).ToArray();
        int?[] device = root.GetProperty("device").EnumerateArray().Select(e => e.ValueKind == JsonValueKind.Null ? (int?)null : e.GetInt32()).ToArray();
        long[] free = root.GetProperty("freeMiB").EnumerateArray().Select(e => e.GetInt64()).ToArray();
        double firstFrameCompaction = root.GetProperty("firstFrameCompactionAt").GetDouble();

        List<double> presents = new();
        for (int second = 0; second < fps.Length; second++)
        {
            double frames = fps[second] ?? (missingIsGap ? 0 : 30);
            int count = (int)Math.Round(frames);
            // Evenly spaced within the second; a second with a single frame has it in its middle, or at its end
            // (the journal does not say where: the two bounds of the gap around it).
            for (int k = 0; k < count; k++) presents.Add(second + (count == 1 && sparseAtEnd ? 0.98 : (k + 0.5) / count));
        }

        List<double> fired = new();
        double lastCompaction = firstFrameCompaction;
        int next = 0, done = 0, lastDevice = device.First(d => d.HasValue).Value;
        double lastPresent = -1, first = presents[0];
        for (double now = first; now < fps.Length; now += 0.25)
        {
            while (next < presents.Count && presents[next] <= now) lastPresent = presents[next++];
            int second = (int)now;
            if (device[second].HasValue) lastDevice = device[second].Value;
            int window = second / 5 - 1; // the last completed 5 s window
            long reclaimable = window >= 0 && window < free.Length ? free[window] * MiB : 0;
            if (EmbeddedHeapCompaction.ShouldCompactInStall(reclaimable, lastDevice, (long)((now - first) * 1000), (long)((now - lastPresent) * 1000),
                    (long)((now - lastCompaction) * 1000), done))
            {
                fired.Add(Math.Round(now, 2));
                lastCompaction = now;
                done++;
            }
        }
        return new { missingIsGap, sparseAtEnd, firstPresentedFrame = Math.Round(first, 2), fired };
    }

    static object LiveRun()
    {
        Ryujinx.Memory.HostMemoryBudget.Device = 9;
        bool stop = false;
        EmbeddedHeapCompaction.WatchStalls(() => stop);

        // Before the session presents anything the poll does nothing, whatever the heap holds.
        LoadingBurst(1, 420 * MiB);
        long freeBefore = Reclaimable();
        long idle = Stall(1000);

        // The session's first frame, then 10.4 s of frames at 30 per second with the poll: no compaction while frames come.
        int atStart = Compactions;
        Play(10_400);
        int duringPlay = Compactions - atStart;

        // The game stops presenting: the first poll past the gap compacts, once.
        long rssBefore = Environment.WorkingSet;
        long waited = Stall(3000);
        long rssAfter = Environment.WorkingSet, freeAfter = Reclaimable();
        int afterFirstStall = Compactions - atStart;
        long again = Stall(1500); // still nothing presented, heap compact, interval not passed

        // A second loading burst; the device no longer short: nothing. Short again, a stop requested: nothing.
        LoadingBurst(2, 420 * MiB);
        long freeSecond = Reclaimable();
        Play(8_200);
        Ryujinx.Memory.HostMemoryBudget.Device = 16;
        long notShort = Stall(1500);
        Ryujinx.Memory.HostMemoryBudget.Device = 9;
        stop = true;
        long stopping = Stall(1500);
        stop = false;

        // A host pause keeps its own rule (held 3 s): the poll does nothing while it lasts, with the space and the gap
        // there. A resume counts as a frame: no gap right after it.
        EmbeddedHeapCompaction.OnHostPause(true, () => false);
        long paused = Stall(1500);
        EmbeddedHeapCompaction.BeforeResume();
        EmbeddedHeapCompaction.OnHostPause(false, () => false);
        int beforeResumePoll = Compactions;
        EmbeddedHeapCompaction.OnPoll();
        int rightAfterResume = Compactions - beforeResumePoll;

        // The session ends: nothing, even with the gap and the free space there.
        Thread.Sleep(800);
        EmbeddedHeapCompaction.OnSessionEnd();
        long ended = Stall(1500);

        // A last frame of the closing session comes after its end; the next session's run starts: nothing of the
        // earlier session is left, so nothing before the new session's own first frame, 11 s of gap notwithstanding.
        EmbeddedHeapCompaction.NotePresented();
        EmbeddedHeapCompaction.WatchStalls(() => stop);
        long beforeNextFirstFrame = Stall(11_000);

        // The next session: its first frame, its own count; the second burst's space is given back in its first gap.
        Play(10_400);
        long nextSession = Stall(3000);
        int total = Compactions - atStart;

        string[] lines;
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines) lines = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.ToArray();
        return new
        {
            freeBeforeMiB = freeBefore / MiB, idleBeforeFirstFrame = idle, duringPlay, waitedMs = waited, afterFirstStall,
            rssBeforeMiB = rssBefore / MiB, rssAfterMiB = rssAfter / MiB, freeAfterMiB = freeAfter / MiB, againWithoutSpace = again,
            freeSecondMiB = freeSecond / MiB, notShort, stopping, pausedPoll = paused, rightAfterResume, ended, beforeNextFirstFrame,
            nextSessionWaitedMs = nextSession, total,
            stallCompactionsOfTheNextSession = EmbeddedHeapCompaction.StallCompactions, lines,
        };
    }

    static int Main(string[] arguments)
    {
        object report = arguments[0] switch
        {
            "policy" => Policy(),
            "replay" => new { presenting = Replay(arguments[1], false, false), sparseAtEnd = Replay(arguments[1], false, true),
                              gaps = Replay(arguments[1], true, true) },
            "live" => LiveRun(),
            _ => throw new ArgumentException(arguments[0]),
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
