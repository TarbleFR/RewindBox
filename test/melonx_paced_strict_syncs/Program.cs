// Host fixture of adapt_paced_strict_syncs. Two production texts are compiled with it by the test:
//   AutoFlushCounter.cs  the whole file of the control (CONTROL defined) or of the candidate, its clock reads replaced
//                        by FakeClock (asserted by the test), against the doubles below;
//   Pacer.cs             the candidate's StrictSyncPacer, as GpuContext.cs holds it (the control has none: every strict
//                        sync submits).
// One Hogwarts Legacy frame as IPA 729 measured it is replayed on a fake clock: 760 draws over 34 ms of render thread
// in 82 render passes (three long ones of 250, 250 and 150 draws, the others of one or two draws), fast flush mode on,
// 12.4 guest syncpoint increments and 3.3 SetReference per frame that each find a pending sync, 1.1 forced
// counter-report syncs. A submission is what PipelineFull.SubmitCommands does to the counter (RegisterFlush). Nothing
// depends on real time.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }
    public sealed class Log { public void PrintMsg(LogClass logClass, string message) { } }
    public static class Logger { public static Log Debug => null; }
}

namespace Ryujinx.Graphics.Vulkan
{
    static class FakeClock
    {
        public const long Frequency = 1_000_000_000;
        public static long Now;
    }

    class SyncManager
    {
        public long WaitTicks;
        public long GetAndResetWaitTicks() => WaitTicks;
    }

    class VulkanRenderer
    {
        public bool RelaxQueryFlushing;
        public SyncManager SyncManager = new();
    }

    static class RenderStageTimer
    {
        public static void NoteFlushMode(bool fast, long waitTicks) { }
    }

#if CONTROL
    static class SubmitPacing { public static bool Paced { get; set; } } // the candidate's file defines its own
#endif
}

namespace Ryujinx.Graphics.Gpu
{
    static class GpuContext { public static bool PaceStrictHostSyncs { get; set; } }
}

static class Program
{
    const long Us = 1000; // FakeClock ticks per microsecond

    sealed class Frame
    {
        public int Strict, Kept, DrawAuto, AttachmentAuto, Forced;
        public double LongestGapMs;
        public List<string> Decisions = new();
        public int Total => Strict + DrawAuto + AttachmentAuto + Forced + 1; // + the present
    }

    // Replays `frames` frames; returns the last one's counts (the first ones settle the counter's timers).
    static Frame Replay(bool pacedSubmits, bool pacedSyncs, int frames, bool fastFlush = true)
    {
        Ryujinx.Graphics.Vulkan.SubmitPacing.Paced = pacedSubmits;
        Ryujinx.Graphics.Gpu.GpuContext.PaceStrictHostSyncs = pacedSyncs;
        var gd = new Ryujinx.Graphics.Vulkan.VulkanRenderer();
        var counter = new Ryujinx.Graphics.Vulkan.AutoFlushCounter(gd);
        Ryujinx.Graphics.Vulkan.FakeClock.Now = 1_000_000 * Us;
        // Fast flush mode is entered when the average sync wait of the last 20 frames passes 1.5 ms (IPA 729: on in
        // 72-84 of 77-84 frames).
        gd.SyncManager.WaitTicks = fastFlush ? 2_000 * Us : 0;
        for (int i = 0; i < 20; i++) counter.Present();
#if !CONTROL
        var pacer = new Ryujinx.Graphics.Gpu.StrictSyncPacer();
#endif
        ulong draws = 0;
        Frame frame = null;
        for (int f = 0; f < frames; f++)
        {
            frame = new Frame();
            long lastSubmit = Ryujinx.Graphics.Vulkan.FakeClock.Now;
            void Submit(string cause)
            {
                long now = Ryujinx.Graphics.Vulkan.FakeClock.Now;
                frame.LongestGapMs = Math.Max(frame.LongestGapMs, (now - lastSubmit) / (double)(1000 * Us));
                lastSubmit = now;
                counter.RegisterFlush(draws);
                frame.Decisions.Add(cause);
            }
            const int Draws = 760;
            // Guest sync requests of the frame, by draw index: 12.4 syncpoint increments, 3.3 SetReference, 1.1 forced.
            var syncs = new SortedDictionary<int, List<(string Caller, bool Force)>>();
            void At(double share, string caller, bool force)
            {
                int index = Math.Min(Draws - 1, (int)(share * Draws));
                if (!syncs.TryGetValue(index, out var list)) syncs[index] = list = new();
                list.Add((caller, force));
            }
            int increments = f % 5 < 2 ? 13 : 12, references = f % 10 < 3 ? 4 : 3;
            for (int i = 0; i < increments; i++) At((i + 0.5) / increments, "IncrementSyncpoint", false);
            for (int i = 0; i < references; i++) At((i + 0.8) / references, "SetReference", false);
            At(0.97, "FlushCounterReports", true);
            if (f % 10 == 0) At(0.5, "FlushCounterReports", true);
            // Where a render pass starts: 20 short passes, a long one, 10 short, a long one, 10 short, a long one, 39 short.
            var passStarts = new HashSet<int>();
            int at = 0;
            void Short(int count) { for (int i = 0; i < count; i++) { passStarts.Add(at); at += 1 + (i & 1) * (at < 600 ? 1 : 0); } }
            void Long(int count) { passStarts.Add(at); at += count; }
            Short(20); Long(250); Short(10); Long(250); Short(10); Long(150); Short(39);
            for (int d = 0; d < Draws; d++)
            {
                Ryujinx.Graphics.Vulkan.FakeClock.Now += 45 * Us; // 34 ms of render thread per 760 draws
                if (passStarts.Contains(d) && counter.ShouldFlushAttachmentChange(draws)) { frame.AttachmentAuto++; Submit("attachment"); }
                draws++;
                if (counter.ShouldFlushDraw(draws)) { frame.DrawAuto++; Submit("draw"); }
                if (syncs.TryGetValue(d, out var list))
                {
                    foreach ((string caller, bool force) in list)
                    {
                        bool strict = true;
#if !CONTROL
                        if (!force && pacer.Defer(caller, Ryujinx.Graphics.Vulkan.FakeClock.Now, Ryujinx.Graphics.Vulkan.FakeClock.Frequency)) strict = false;
#endif
                        if (!strict) { frame.Kept++; frame.Decisions.Add("kept:" + caller); continue; }
                        if (force) frame.Forced++; else frame.Strict++;
                        Submit(force ? "forced" : "strict:" + caller);
                    }
                }
            }
            Submit("present");
            Ryujinx.Graphics.Vulkan.FakeClock.Now += 26_000 * Us; // the rest of a 60 ms frame
            gd.SyncManager.WaitTicks = fastFlush ? 1_150 * Us : 0; // IPA 729: 1.15 ms of sync wait per frame
            counter.Present();
        }
        return frame;
    }

    static Dictionary<string, object> Describe(Frame f) => new()
    {
        ["commandBuffers"] = f.Total, ["strictSyncSubmits"] = f.Strict, ["syncsKeptOnTheOpenCommandBuffer"] = f.Kept,
        ["drawAutoFlushes"] = f.DrawAuto, ["attachmentAutoFlushes"] = f.AttachmentAuto, ["forcedSubmits"] = f.Forced,
        ["longestGapMs"] = Math.Round(f.LongestGapMs, 2), ["decisions"] = Digest(f.Decisions),
    };

    static string Digest(List<string> decisions)
    {
        using var sha = System.Security.Cryptography.SHA256.Create();
        return Convert.ToHexString(sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(string.Join("\n", decisions)))).ToLowerInvariant()[..16];
    }

    static int Main()
    {
        var report = new Dictionary<string, object>();
#if CONTROL
        report["engine"] = "control";
        report["frame"] = Describe(Replay(false, false, 12));
        report["frameNoFastFlush"] = Describe(Replay(false, false, 12, fastFlush: false));
#else
        report["engine"] = "candidate";
        report["policyOff"] = Describe(Replay(false, false, 12));
        report["policyOffNoFastFlush"] = Describe(Replay(false, false, 12, fastFlush: false));
        report["frame"] = Describe(Replay(true, true, 12));
        report["frameNoFastFlush"] = Describe(Replay(true, true, 12, fastFlush: false));
        report["submitsPacedOnly"] = Describe(Replay(true, false, 12));
        report["syncsPacedOnly"] = Describe(Replay(false, true, 12));

        // The pacer alone.
        long second = Ryujinx.Graphics.Vulkan.FakeClock.Frequency, ms = second / 1000;
        var p = new Ryujinx.Graphics.Gpu.StrictSyncPacer();
        Ryujinx.Graphics.Gpu.GpuContext.PaceStrictHostSyncs = true;
        var pacer = new List<bool>
        {
            p.Defer("IncrementSyncpoint", 10 * ms, second),        // first: strict
            p.Defer("SetReference", 10 * ms + 1, second),          // within the interval: kept
            p.Defer("IncrementSyncpoint", 13 * ms + 999_999, second), // 3.999999 ms: kept
            p.Defer("IncrementSyncpoint", 14 * ms, second),        // 4 ms: strict
            p.Defer("FlushCounterReports", 14 * ms + 1, second),   // another site: never paced
            p.Defer("TryReadBackGpuRegion", 14 * ms + 2, second),
            p.Defer("Syncpointb", 14 * ms + 3, second),
            p.Defer("SetReference", 17 * ms, second),              // 3 ms after the last strict one: kept
            p.Defer("SetReference", 18 * ms, second),              // 4 ms: strict
        };
        report["pacer"] = pacer;
        Ryujinx.Graphics.Gpu.GpuContext.PaceStrictHostSyncs = false;
        var off = new Ryujinx.Graphics.Gpu.StrictSyncPacer();
        report["pacerOff"] = new List<bool> { off.Defer("IncrementSyncpoint", 1, second), off.Defer("IncrementSyncpoint", 2, second), off.Defer("SetReference", 3, second) };
        report["intervalMs"] = Ryujinx.Graphics.Gpu.StrictSyncPacer.IntervalMs;
#endif
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
