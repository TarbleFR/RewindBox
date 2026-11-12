// Fixture of test/melonx_submit_causes_test.py: the production RenderStageTimer of PipelineBase.cs (the control's or the
// candidate's, spliced at __RENDER_STAGE_TIMER__) and, for the candidate, the production host sync members of GpuContext.cs
// (spliced at __HOST_SYNC_MEMBERS__), their clock reads replaced by FakeClock.Now (RenderStageTimer.Now and the host sync
// window's Stopwatch.GetTimestamp), with the logger, the engine journal, the Metal GPU timer and RenderDetail replaced by
// doubles. Prints one JSON object: the render stages lines of two windows and
// the host sync line.
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }

    public struct Log
    {
        public void Print(LogClass logClass, string message) => Captured.Lines.Add(message);
        public void PrintMsg(LogClass logClass, string message) => Captured.Lines.Add(message);
    }

    public static class Logger
    {
        public static Log? Warning = new Log();
        public static Log? Info = new Log();
    }

    public static class Captured
    {
        public static readonly List<string> Lines = new();
    }
}

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
        }
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    static class MetalGpuTimer
    {
        public static void Poll()
        {
        }
    }

    static class RenderDetail
    {
        public static void Log(string window, long frames)
        {
        }
    }

//__RENDER_STAGE_TIMER__
}

namespace Ryujinx.Graphics.Gpu
{
    using Ryujinx.Common.Logging;

    static class FakeClock
    {
        public static long Now = 1;
    }

#if CANDIDATE
    class HostSyncs
    {
//__HOST_SYNC_MEMBERS__

        // As GpuContext.CreateHostSyncIfNeeded: the caller's name is the compiler's, the sync counted when created.
        public void CreateHostSyncIfNeeded(bool strict, [CallerMemberName] string caller = "") => NoteHostSync(caller, strict);

        public void Syncpointb() => CreateHostSyncIfNeeded(true);
        public void IncrementSyncpoint() => CreateHostSyncIfNeeded(true);
        public void SetReference() => CreateHostSyncIfNeeded(true);
        public void FlushCounterReports() => CreateHostSyncIfNeeded(true);
        public void QueueSyncpointBehindReports() => CreateHostSyncIfNeeded(true);
        public void TryReadBackGpuRegion() => CreateHostSyncIfNeeded(true);
        public void TryReadBackIntoBuffer() => CreateHostSyncIfNeeded(false);
        public void SignalModifying() => CreateHostSyncIfNeeded(false);
        public void CreatePendingSyncs() => CreateHostSyncIfNeeded(false);
        public void SomewhereElse() => CreateHostSyncIfNeeded(false);
        public void SomewhereElseStrict() => CreateHostSyncIfNeeded(true);
    }
#endif
}

namespace Probe
{
    using Ryujinx.Common.Logging;
    using Ryujinx.Graphics.Vulkan;

    public static class Program
    {
        private static long Tick(double ms) => (long)(ms * System.Diagnostics.Stopwatch.Frequency / 1000);

        // One emulated FlushCommandsImpl: the production body's counters (PipelineFull.cs), the cause named before it.
        private static void Submit(int cause, double ms)
        {
#if CANDIDATE
            if (cause >= 0)
            {
                RenderStageTimer.NextSubmitCause = (RenderStageTimer.SubmitCause)cause;
            }
#endif
            RenderStageTimer.SubmitTicks += Tick(ms);
            RenderStageTimer.Submits++;
#if CANDIDATE
            RenderStageTimer.NoteSubmit();
#endif
        }

        // The window's draw, pass and present counters, the same in both trees, then presents: the first one 6 s after the
        // window began logs the line (the clock is FakeClock, spliced into RenderStageTimer.Now).
        private static string Window(int frames)
        {
            RenderStageTimer.Prepares += 1000;
            RenderStageTimer.PrepareTicks += Tick(7.5);
            RenderStageTimer.Pipelines += 900;
            RenderStageTimer.PipelineTicks += Tick(0.5);
            RenderStageTimer.DescriptorTicks += Tick(5.25);
            RenderStageTimer.AutoFlushes += 11;
            RenderStageTimer.AutoFlushTicks += Tick(1.5);
            RenderStageTimer.PassBegins += 80;
            RenderStageTimer.PassResumes += 22;
            RenderStageTimer.QueueTicks += Tick(2.0);
            int before = Captured.Lines.Count;

            for (int frame = 0; frame < frames; frame++)
            {
                Ryujinx.Graphics.Gpu.FakeClock.Now += Tick(frame == 0 ? 6000 : 16);
                long start = Ryujinx.Graphics.Gpu.FakeClock.Now - Tick(1);
                RenderStageTimer.NotePresent(start, start, start, start);
            }

            return Captured.Lines.Count == before + 1 ? Captured.Lines[before] : "missing: " + (Captured.Lines.Count - before);
        }

        public static int Main(string[] args)
        {
            var result = new Dictionary<string, object>();
            // The first present only opens the first window.
            Ryujinx.Graphics.Gpu.FakeClock.Now = Tick(10000);
            RenderStageTimer.NotePresent(Ryujinx.Graphics.Gpu.FakeClock.Now, Ryujinx.Graphics.Gpu.FakeClock.Now,
                Ryujinx.Graphics.Gpu.FakeClock.Now, Ryujinx.Graphics.Gpu.FakeClock.Now);

            // Window 1: 25 submissions: 6 strict syncs, 2 sync waits, 9 draw auto-flushes, 3 attachment auto-flushes, 1 query,
            // 1 disposed weight, 1 present and 2 with no cause named (other).
            int[] causes = { 1, 1, 1, 1, 1, 1, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 5, 6, 11, -1, -1 };
            foreach (int cause in causes)
            {
                Submit(cause, 0.25);
            }
#if CANDIDATE
            RenderStageTimer.SubmittingSyncs += 6;
            RenderStageTimer.WaitingSyncs += 14;
            RenderStageTimer.NoteFlushMode(true, Tick(2.5));
            RenderStageTimer.NoteFlushMode(true, Tick(1.0));
            RenderStageTimer.NoteFlushMode(false, Tick(0.5));
            result["causeAfterSubmit"] = RenderStageTimer.NextSubmitCause.ToString();
#endif
            result["first"] = Window(2);

            // Window 2: three submissions with no cause and nothing else: every cause count starts again from zero.
            Submit(-1, 0.25);
            Submit(-1, 0.25);
            Submit(-1, 0.25);
            result["second"] = Window(2);

#if CANDIDATE
            var syncs = new Ryujinx.Graphics.Gpu.HostSyncs();
            Ryujinx.Graphics.Gpu.FakeClock.Now = 1000;
            int linesBefore = Captured.Lines.Count;
            syncs.CreatePendingSyncs(); // opens the window (counted)
            for (int i = 0; i < 7; i++) syncs.Syncpointb();
            for (int i = 0; i < 3; i++) syncs.IncrementSyncpoint();
            for (int i = 0; i < 2; i++) syncs.SetReference();
            syncs.FlushCounterReports();
            syncs.QueueSyncpointBehindReports();
            for (int i = 0; i < 2; i++) syncs.TryReadBackGpuRegion();
            syncs.TryReadBackIntoBuffer();
            for (int i = 0; i < 4; i++) syncs.SignalModifying();
            for (int i = 0; i < 3; i++) syncs.CreatePendingSyncs();
            syncs.SomewhereElse();
            Ryujinx.Graphics.Gpu.FakeClock.Now = 1000 + System.Diagnostics.Stopwatch.Frequency * 5 - 1;
            syncs.SomewhereElseStrict(); // 1 tick short of 5 s: no line yet
            result["linesBeforeFiveSeconds"] = Captured.Lines.Count - linesBefore;
            Ryujinx.Graphics.Gpu.FakeClock.Now = 1000 + System.Diagnostics.Stopwatch.Frequency * 5;
            syncs.Syncpointb(); // 5 s after the first: counted, then the line
            result["hostSyncs"] = Captured.Lines.Count == linesBefore + 1 ? Captured.Lines[linesBefore] : "missing";
            Ryujinx.Graphics.Gpu.FakeClock.Now += System.Diagnostics.Stopwatch.Frequency * 6;
            syncs.SetReference(); // the next window: alone, 6 s later
            result["hostSyncsNext"] = Captured.Lines.Count == linesBefore + 2 ? Captured.Lines[linesBefore + 1] : "missing";
            var sites = new Dictionary<string, int>();
            foreach (string name in new[] { "Syncpointb", "IncrementSyncpoint", "SetReference", "FlushCounterReports",
                         "QueueSyncpointBehindReports", "TryReadBackGpuRegion", "TryReadBackIntoBuffer", "SignalModifying",
                         "CreatePendingSyncs", "Dispatch", "" })
            {
                sites[name] = Ryujinx.Graphics.Gpu.HostSyncs.HostSyncSite(name);
            }
            result["sites"] = sites;
#endif
            Console.WriteLine(JsonSerializer.Serialize(result));
            return 0;
        }
    }
}
