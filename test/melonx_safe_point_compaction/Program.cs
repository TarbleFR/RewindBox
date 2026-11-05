using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Ryujinx.Library;

// The production EmbeddedHeapCompaction class (from the candidate EmbeddedMemory.cs) is compiled unchanged next to two
// doubles: HostMemoryBudget (iOS constrained, device share set by the fixture, footprint = this process's RSS) and the
// launch journal. The test runs it with the segments GC library (libclrgc.so, as iOS NativeAOT: no regions) and the
// Core's GC settings (ConserveMemory 5, HighMemoryPercent 99).
namespace Ryujinx.Memory
{
    public static class HostMemoryBudget
    {
        public static bool IsConstrained => true;
        public static int Device = 11;
        public static int DeviceAvailablePercent => Device;
        public static ulong FootprintBytes => (ulong)Fixture.RssBytes();
    }
}

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Lines = new();
        public static volatile bool Hold;
        public static readonly ManualResetEventSlim InGate = new(), Proceed = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            if (Hold && status == "heapCompacted") { InGate.Set(); Proceed.Wait(); }
            lock (Lines) Lines.Add(stage + " " + status + ": " + detail);
        }
    }
}

static class Fixture
{
    const long MiB = 1024 * 1024;
    static readonly List<byte[]> Live = new();

    public static long RssBytes()
    {
        // Resident bytes on every host (Linux /proc RSS, the macOS task's resident size): the Core CI runs this on macOS.
        return Environment.WorkingSet;
    }

    // A boot-like large object heap: arrays of 128 KiB to 8 MiB, every page touched, about half of them dying, then
    // swept by a non-compacting gen2 (what the background collections do on the device) and one gen0 collection.
    static void BootLikeHeap(int seed, long total)
    {
        Random random = new(seed);
        List<byte[]> all = new();
        long allocated = 0;
        while (allocated < total)
        {
            int size = random.Next(4) == 0 ? random.Next(1, 9) * (int)MiB : 128 * 1024 * random.Next(1, 8);
            byte[] array = new byte[size];
            for (int k = 0; k < array.Length; k += 4096) array[k] = 1;
            all.Add(array);
            allocated += size;
        }
        foreach (byte[] array in all) if (random.Next(2) == 0) Live.Add(array);
        all.Clear();
        GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: false);
        GC.Collect(0, GCCollectionMode.Forced, blocking: true);
    }

    static Dictionary<string, long> State()
    {
        GCMemoryInfo info = GC.GetGCMemoryInfo();
        return new()
        {
            ["rssMiB"] = RssBytes() / MiB,
            ["committedMiB"] = info.TotalCommittedBytes / MiB,
            ["lohMiB"] = info.GenerationInfo[3].SizeAfterBytes / MiB,
            ["lohFreeMiB"] = info.GenerationInfo[3].FragmentationAfterBytes / MiB,
            ["gen2FreeMiB"] = info.GenerationInfo[2].FragmentationAfterBytes / MiB,
            ["lastGcGeneration"] = info.Generation,
            ["reclaimableMiB"] = EmbeddedHeapCompaction.ReclaimableBytes(info) / MiB,
            ["liveMiB"] = Live.Sum(a => (long)a.Length) / MiB,
        };
    }

    static int Main(string[] args)
    {
        string mode = args[0];
        Dictionary<string, object> result = new() { ["mode"] = mode, ["gcConfig"] = GC.GetConfigurationVariables().ToDictionary(p => p.Key, p => p.Value.ToString()) };

        // Policy, as compiled.
        result["policy"] = new Dictionary<string, bool>
        {
            ["firstFrame63MiB"] = EmbeddedHeapCompaction.ShouldCompactAfterFirstFrame(63 * MiB),
            ["firstFrame64MiB"] = EmbeddedHeapCompaction.ShouldCompactAfterFirstFrame(64 * MiB),
            ["pauseDevice15"] = EmbeddedHeapCompaction.ShouldCompactInPause(200 * MiB, 15, long.MaxValue),
            ["pauseDevice16"] = EmbeddedHeapCompaction.ShouldCompactInPause(200 * MiB, 16, long.MaxValue),
            ["pauseDeviceUnknown"] = EmbeddedHeapCompaction.ShouldCompactInPause(200 * MiB, -1, long.MaxValue),
            ["pauseSmall"] = EmbeddedHeapCompaction.ShouldCompactInPause(63 * MiB, 10, long.MaxValue),
            ["pause59s"] = EmbeddedHeapCompaction.ShouldCompactInPause(200 * MiB, 10, 59_999),
            ["pause60s"] = EmbeddedHeapCompaction.ShouldCompactInPause(200 * MiB, 10, 60_000),
        };

        BootLikeHeap(7, 530 * MiB);
        result["beforeFirstFrame"] = State();

        if (mode == "candidate")
        {
            EmbeddedHeapCompaction.AfterFirstFrame();
        }
        result["afterFirstFrame"] = State();
        result["compactionsAfterFirstFrame"] = EmbeddedHeapCompaction.Compactions;

        if (mode == "candidate")
        {
            // A second first-frame call with nothing to reclaim does nothing.
            EmbeddedHeapCompaction.AfterFirstFrame();
            result["compactionsAfterSecondFirstFrame"] = EmbeddedHeapCompaction.Compactions;

            // Pause flow (the 60 s interval since the first-frame compaction holds every pause below off).
            BootLikeHeap(11, 300 * MiB);
            HostMemoryBudget_Device(11);
            EmbeddedHeapCompaction.OnHostPause(true, () => false);
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs + 700);
            result["pauseWithin60s"] = EmbeddedHeapCompaction.Compactions;
            EmbeddedHeapCompaction.OnHostPause(false, () => false);
        }
        else if (mode == "pause")
        {
            int c0 = EmbeddedHeapCompaction.Compactions;
            HostMemoryBudget_Device(40);
            EmbeddedHeapCompaction.OnHostPause(true, () => false);
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs + 700);
            EmbeddedHeapCompaction.OnHostPause(false, () => false);
            result["pauseDevice40"] = EmbeddedHeapCompaction.Compactions - c0;

            HostMemoryBudget_Device(11);
            EmbeddedHeapCompaction.OnHostPause(true, () => false);
            Thread.Sleep(1000);
            EmbeddedHeapCompaction.OnHostPause(false, () => false);
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs);
            result["pauseResumedAfter1s"] = EmbeddedHeapCompaction.Compactions - c0;

            EmbeddedHeapCompaction.OnHostPause(true, () => true);
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs + 700);
            EmbeddedHeapCompaction.OnHostPause(false, () => false);
            result["pauseWhileStopping"] = EmbeddedHeapCompaction.Compactions - c0;

            result["beforeHeldPause"] = State();
            EmbeddedHeapCompaction.OnHostPause(true, () => false);
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs + 1500);
            result["heldPause"] = EmbeddedHeapCompaction.Compactions - c0;
            result["afterHeldPause"] = State();
            EmbeddedHeapCompaction.OnHostPause(false, () => false);

            BootLikeHeap(13, 300 * MiB);
            EmbeddedHeapCompaction.OnHostPause(true, () => false);
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs + 700);
            EmbeddedHeapCompaction.OnHostPause(false, () => false);
            result["secondHeldPauseWithin60s"] = EmbeddedHeapCompaction.Compactions - c0;
        }

        else if (mode == "race")
        {
            HostMemoryBudget_Device(11);

            // A resume during the delay: no collection.
            EmbeddedHeapCompaction.OnHostPause(true, () => false);
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs - 1500);
            EmbeddedHeapCompaction.BeforeResume();
            EmbeddedHeapCompaction.OnHostPause(false, () => false);
            Thread.Sleep(2500);
            result["resumeDuringDelay"] = EmbeddedHeapCompaction.Compactions;

            // A resume landing after the worker's generation check and before its collection: the worker's own stopping()
            // callback (called after the check, outside the gate) performs the resume.
            EmbeddedHeapCompaction.OnHostPause(true, () => { EmbeddedHeapCompaction.BeforeResume(); return false; });
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs + 1000);
            result["resumeBetweenCheckAndCollect"] = EmbeddedHeapCompaction.Compactions;
            EmbeddedHeapCompaction.OnHostPause(false, () => false);

            // A close, then a new session whose stop flag is clear, within the delay: the old worker must not collect.
            EmbeddedHeapCompaction.OnHostPause(true, () => false);
            Thread.Sleep(500);
            EmbeddedHeapCompaction.OnSessionEnd();
            Thread.Sleep(EmbeddedHeapCompaction.PauseDelayMs + 700);
            result["closeThenNewSession"] = EmbeddedHeapCompaction.Compactions;

            // A resume arriving while the collection runs waits for it. The journal double (called by Compact while it holds
            // the gate, after the collection) signals that the worker holds the gate and blocks it until the resume thread
            // has started; nothing polls the gate.
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Hold = true;
            EmbeddedHeapCompaction.OnHostPause(true, () => false);
            bool seen = Ryujinx.Common.EmbeddedLaunchDiagnostics.InGate.Wait(EmbeddedHeapCompaction.PauseDelayMs + 5000);
            bool released = false, returnedAfterRelease = false;
            int compactionsAtResume = -1;
            using ManualResetEventSlim resumeStarted = new();
            System.Diagnostics.Stopwatch wait = System.Diagnostics.Stopwatch.StartNew();
            Thread resume = new(() =>
            {
                resumeStarted.Set();
                EmbeddedHeapCompaction.BeforeResume();
                returnedAfterRelease = Volatile.Read(ref released);
                compactionsAtResume = EmbeddedHeapCompaction.Compactions;
            });
            resume.Start();
            resumeStarted.Wait();
            Thread.Sleep(300);
            Volatile.Write(ref released, true);
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Proceed.Set();
            resume.Join();
            result["inFlightSeen"] = seen;
            result["resumeReturnedAfterRelease"] = returnedAfterRelease;
            result["resumeWaitMs"] = wait.ElapsedMilliseconds;
            result["resumeWaitedForInFlight"] = compactionsAtResume;
            EmbeddedHeapCompaction.OnHostPause(false, () => false);
        }

        // Every surviving array still holds what was written into it (a compaction moves, never alters, objects).
        result["liveIntact"] = Live.All(a =>
        {
            for (int k = 0; k < a.Length; k += 4096) if (a[k] != 1) return false;
            return true;
        });
        result["journal"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.ToArray();
        Console.WriteLine(JsonSerializer.Serialize(result));
        return 0;
    }

    static void HostMemoryBudget_Device(int percent) => Ryujinx.Memory.HostMemoryBudget.Device = percent;
}
