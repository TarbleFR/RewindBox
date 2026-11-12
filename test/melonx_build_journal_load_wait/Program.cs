// Fixture of test/melonx_build_journal_load_wait_test.py: the candidate's production members of PipelineState.cs added by
// adapt_build_journal_load_wait (thread-local wait and lookup state, BeginBuildTiming, NoteMainLoadWait, CompiledMs) and its
// NoteMainCacheLookup, spliced at __MEMBERS__, with the logger, the engine journal and PipelineCacheManager.CompiledBuildMs
// replaced by doubles. A creation is played as production orders it: its start, BeginBuildTiming, on a worker the main
// load wait (timed by NoteMainLoadWait from a start moved back by the scripted wait, nothing sleeps) and the lookup, then
// the journal's CompiledMs. The control's journal time is the delivered expression, the creation's elapsed time.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }

    public struct Log
    {
        public void PrintMsg(LogClass logClass, string message)
        {
        }
    }

    public static class Logger
    {
        public static Log? Info = new Log();
    }
}

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Records = new();

        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            Records.Add(stage + " " + status + " " + detail);
        }
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    using Ryujinx.Common.Logging;

    static class PipelineCacheManager
    {
        public const double CompiledBuildMs = 50;
    }

    struct PipelineState
    {
        private static long _workerMainCacheHits;
        private static long _workerMainCacheMisses;

//__MEMBERS__

        private static long Ticks(double ms) => (long)(ms * Stopwatch.Frequency / 1000);

        // One creation: (journal time of the candidate, journal time of the control).
        public static (double Candidate, double Control) Creation(double elapsedMs, double waitMs, bool worker, bool hit, bool lookup = true)
        {
            long buildStart = Stopwatch.GetTimestamp() - Ticks(elapsedMs);
            BeginBuildTiming();

            if (worker)
            {
                NoteMainLoadWait(Stopwatch.GetTimestamp() - Ticks(waitMs));

                if (lookup)
                {
                    NoteMainCacheLookup(hit);
                }
            }

            return (CompiledMs(buildStart), Stopwatch.GetElapsedTime(buildStart).TotalMilliseconds);
        }
    }
}

namespace Probe
{
    using Ryujinx.Graphics.Vulkan;

    public static class Program
    {
        public static int Main(string[] args)
        {
            var result = new Dictionary<string, object>();
            void Play(string name, double elapsedMs, double waitMs, bool worker, bool hit, bool lookup = true)
            {
                (double candidate, double control) = PipelineState.Creation(elapsedMs, waitMs, worker, hit, lookup);
                result[name] = new Dictionary<string, double> { ["candidate"] = Math.Round(candidate, 1), ["control"] = Math.Round(control, 1) };
            }

            // IPA 727's first worker creation of a launch: 1 300 ms waiting for the main load, then served by the main cache.
            Play("servedAfterLoadWait", 1302, 1300, worker: true, hit: true);
            result["recordsAfterFirst"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.ToArray();
            // A render-thread creation (no lookup): a real compilation of 945 ms.
            Play("renderThreadCompile", 945, 0, worker: false, hit: false);
            // A worker that waited 1 300 ms, missed the main cache and compiled for 900 ms.
            Play("compiledAfterLoadWait", 2200, 1300, worker: true, hit: false);
            // A worker served without a wait, then on the same thread a creation whose lookup did not run (the main lock was
            // taken) and compiled after a short wait: BeginBuildTiming cleared the earlier "served".
            Play("servedNoWait", 2, 0, worker: true, hit: true);
            Play("compiledNoLookup", 700, 10, worker: true, hit: false, lookup: false);
            Play("compileAfterServed", 945, 0, worker: true, hit: false);
            // A second long wait in the session: not recorded again.
            Play("secondLongWait", 1500, 1400, worker: true, hit: true);
            result["records"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.ToArray();
            Console.WriteLine(JsonSerializer.Serialize(result));
            return 0;
        }
    }
}
