// Host for test/melonx_gc_latency_test.py (adapt_gc_latency). Published with NativeAOT for linux-x64 carrying the GC
// knobs (System.GC.*) that the production Ryujinx.Library project gives ILC (its evaluated RuntimeHostConfigurationOption
// items, copied by the test), so the knobs reach the GC through the same path as in the iOS build (--runtimeknob).
//
// Workload: a long-lived graph like a running game's heap (caches of small objects and byte arrays, some large objects),
// then cycles of a steady gameplay window (about 45 MiB of short-lived allocations) and a scene transition: part of the
// long-lived entries released at once (scene unload, scattered through the heap), then about 720 MiB of short-lived
// arrays in 120 frames, a share of them kept alive for a few frames, while the next scene's entries are added. Measures
// every collection seen (GCMemoryInfo per kind, polled after each MiB), the total pause (GC.GetTotalPauseDuration) and
// its split between steady and transition frames, blocking gen2 collections (GCKind.FullBlocking), frame wall times and
// the heap, then runs Load's teardown sequence (GC.Collect(2, Aggressive, blocking, compacting), finalizers,
// GC.Collect()). --sustained (evaluation only) runs the session under GCLatencyMode.SustainedLowLatency, restored before
// the teardown collections.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime;
using System.Text.Json;

namespace RewindBoxGcHost
{
    sealed class Node
    {
        public byte[] Payload;
        public object[] Links;
        public Node Next;
    }

    static class Host
    {
        static readonly Dictionary<string, long> SeenIndex = new() { ["ephemeral"] = 0, ["fullBlocking"] = 0, ["background"] = 0 };
        static readonly List<(string Kind, int Generation, bool Compacted, double PauseMs)> Seen = new();
        static int _lastGen0;
        static long _observedPeakHeap, _observedPeakCommitted;

        static void Poll()
        {
            int gen0 = GC.CollectionCount(0);
            if (gen0 == _lastGen0) return;
            _lastGen0 = gen0;
            foreach ((string name, GCKind kind) in new[] { ("ephemeral", GCKind.Ephemeral), ("fullBlocking", GCKind.FullBlocking), ("background", GCKind.Background) })
            {
                GCMemoryInfo info = GC.GetGCMemoryInfo(kind);
                if (info.Index <= SeenIndex[name]) continue;
                SeenIndex[name] = info.Index;
                double pause = 0;
                foreach (TimeSpan span in info.PauseDurations) pause = Math.Max(pause, span.TotalMilliseconds);
                Seen.Add((name, info.Generation, info.Compacted, pause));
                _observedPeakHeap = Math.Max(_observedPeakHeap, info.HeapSizeBytes);
                _observedPeakCommitted = Math.Max(_observedPeakCommitted, info.TotalCommittedBytes);
            }
        }

        static object Allocate(Random random, int bytes)
        {
            // Mostly small arrays of references or bytes (binding scratch, command arrays), some up to the LOH threshold.
            return (random.Next(3) == 0) ? new object[Math.Max(1, bytes / 8)] : new byte[bytes];
        }

        static bool _noLargeObjects;

        static int NextSize(Random random)
        {
            int roll = random.Next(_noLargeObjects ? 99 : 100);
            if (roll < 70) return 16 + random.Next(496);
            if (roll < 95) return 1024 + random.Next(15 * 1024);
            if (roll < 99) return 32 * 1024 + random.Next(48 * 1024);
            return 100 * 1024 + random.Next(300 * 1024); // a few short-lived large objects
        }

        static Node NewLongLived(Random random)
        {
            int size = !_noLargeObjects && random.Next(200) == 0 ? 90 * 1024 + random.Next(110 * 1024) : 256 + random.Next(1792);
            return new Node { Payload = new byte[size], Links = new object[1 + random.Next(6)] };
        }

        static int Main(string[] args)
        {
            bool sustained = args.Contains("--sustained");
            _noLargeObjects = args.Contains("--no-large-objects");
            int cycles = int.Parse(args.SkipWhile(a => a != "--cycles").Skip(1).FirstOrDefault() ?? "5");
            int seed = int.Parse(args.SkipWhile(a => a != "--seed").Skip(1).FirstOrDefault() ?? "650");
            int adds = int.Parse(args.SkipWhile(a => a != "--adds").Skip(1).FirstOrDefault() ?? "330");
            int drops = int.Parse(args.SkipWhile(a => a != "--drops").Skip(1).FirstOrDefault() ?? "300");
            double retain = double.Parse(args.SkipWhile(a => a != "--retain").Skip(1).FirstOrDefault() ?? "0.10", System.Globalization.CultureInfo.InvariantCulture);
            var random = new Random(seed);
            GCLatencyMode initial = GCSettings.LatencyMode;

            // Long-lived heap of a running game (about 350 MiB, references between entries).
            var longLived = new List<Node>();
            long longLivedBytes = 0;
            while (longLivedBytes < 350L << 20)
            {
                Node node = NewLongLived(random);
                if (longLived.Count > 0) { node.Next = longLived[random.Next(longLived.Count)]; node.Links[0] = longLived[random.Next(longLived.Count)]; }
                longLived.Add(node);
                longLivedBytes += node.Payload.Length + 64;
            }
            GC.Collect(); // boot finished; the session starts from a settled heap in both runs

            if (sustained) GCSettings.LatencyMode = GCLatencyMode.SustainedLowLatency;
            GCLatencyMode during = GCSettings.LatencyMode;

            _lastGen0 = GC.CollectionCount(0);
            foreach (string name in SeenIndex.Keys.ToArray()) SeenIndex[name] = GC.GetGCMemoryInfo(name switch
            { "ephemeral" => GCKind.Ephemeral, "fullBlocking" => GCKind.FullBlocking, _ => GCKind.Background }).Index;
            int[] countsBefore = { GC.CollectionCount(0), GC.CollectionCount(1), GC.CollectionCount(2) };
            TimeSpan pauseBefore = GC.GetTotalPauseDuration();
            long allocatedBefore = GC.GetTotalAllocatedBytes(true);
            var frames = new List<double>();
            var transitionFrames = new List<double>();
            double steadyPauseMs = 0, transitionPauseMs = 0;
            int steadyGen0 = 0, transitionGen0 = 0;
            int ringFrames = int.Parse(args.SkipWhile(a => a != "--ring").Skip(1).FirstOrDefault() ?? "8");
            var ring = new object[ringFrames][];
            int frameIndex = 0;
            var wall = Stopwatch.StartNew();

            void Frame(long bytes, double retainShare, int liveAdds, int liveDrops, bool transition)
            {
                long start = Stopwatch.GetTimestamp();
                TimeSpan framePause = GC.GetTotalPauseDuration();
                int frameGen0 = GC.CollectionCount(0);
                var kept = new List<object>();
                long done = 0, sincePoll = 0;
                while (done < bytes)
                {
                    int size = NextSize(random);
                    object item = Allocate(random, size);
                    if (random.NextDouble() < retainShare) kept.Add(item); // alive for the next frames
                    done += size; sincePoll += size;
                    if (sincePoll >= 1 << 20) { sincePoll = 0; Poll(); }
                }
                ring[frameIndex++ % ring.Length] = kept.ToArray();
                for (int i = 0; i < liveAdds; i++)
                {
                    Node node = NewLongLived(random);
                    node.Next = longLived[random.Next(longLived.Count)];
                    longLived.Add(node);
                }
                for (int i = 0; i < liveDrops && longLived.Count > 1; i++)
                {
                    int victim = random.Next(longLived.Count);
                    longLived[victim] = longLived[^1];
                    longLived.RemoveAt(longLived.Count - 1);
                }
                Poll();
                double ms = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
                frames.Add(ms);
                double pausedMs = (GC.GetTotalPauseDuration() - framePause).TotalMilliseconds;
                int collected = GC.CollectionCount(0) - frameGen0;
                if (transition) { transitionFrames.Add(ms); transitionPauseMs += pausedMs; transitionGen0 += collected; }
                else { steadyPauseMs += pausedMs; steadyGen0 += collected; }
            }

            double unload = double.Parse(args.SkipWhile(a => a != "--unload").Skip(1).FirstOrDefault() ?? "0.4", System.Globalization.CultureInfo.InvariantCulture);
            for (int cycle = 0; cycle < cycles; cycle++)
            {
                for (int f = 0; f < 150; f++) Frame(300 << 10, 0.02, 2, 2, false);         // steady: ~45 MiB per 5 s
                // Scene unload: a share of the long-lived entries, scattered through the heap, becomes garbage at once.
                int unloadCount = (int)(longLived.Count * unload), reload = unloadCount / 120;
                for (int i = 0; i < unloadCount; i++)
                {
                    int victim = random.Next(longLived.Count);
                    longLived[victim] = longLived[^1];
                    longLived.RemoveAt(longLived.Count - 1);
                }
                for (int f = 0; f < 120; f++) Frame(6 << 20, retain, adds + reload, drops, true);        // transition: ~720 MiB, next scene loaded
            }

            double seconds = wall.Elapsed.TotalSeconds;
            TimeSpan pause = GC.GetTotalPauseDuration() - pauseBefore;
            int[] counts = { GC.CollectionCount(0) - countsBefore[0], GC.CollectionCount(1) - countsBefore[1], GC.CollectionCount(2) - countsBefore[2] };
            long allocated = GC.GetTotalAllocatedBytes(true) - allocatedBefore;
            GCMemoryInfo any = GC.GetGCMemoryInfo(GCKind.Any);
            long fullBlockingIndex = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
            GC.KeepAlive(ring);

            // Teardown as in Load: mode restored first (candidate), then the explicit full collections.
            GCSettings.LatencyMode = initial;
            GCLatencyMode atTeardown = GCSettings.LatencyMode;
            longLived = null; ring = null;
            GC.Collect(2, GCCollectionMode.Aggressive, blocking: true, compacting: true);
            GCMemoryInfo teardown = GC.GetGCMemoryInfo(GCKind.FullBlocking);
            GC.WaitForPendingFinalizers();
            GC.Collect();

            var sorted = frames.OrderBy(x => x).ToArray();
            var sortedTransition = transitionFrames.OrderBy(x => x).ToArray();
            var report = new Dictionary<string, object>
            {
                ["sustainedRequested"] = sustained,
                ["initialMode"] = initial.ToString(),
                ["modeDuringSession"] = during.ToString(),
                ["modeAtTeardown"] = atTeardown.ToString(),
                ["teardownFullBlocking"] = teardown.Index > fullBlockingIndex && teardown.Generation == 2 && !teardown.Concurrent,
                ["teardownCompacted"] = teardown.Compacted,
                ["gcConfig"] = GC.GetConfigurationVariables().Where(kv => kv.Key is "ConcurrentGC" or "GCConserveMem" or "GCHighMemPercent"
                    or "GCGen0MaxBudget" or "GCgen0size" or "ServerGC" or "GCHeapHardLimit").ToDictionary(kv => kv.Key, kv => kv.Value.ToString()),
                ["allocatedMiB"] = allocated >> 20,
                ["seconds"] = Math.Round(seconds, 2),
                ["gcCounts"] = counts,
                ["totalPauseMs"] = Math.Round(pause.TotalMilliseconds, 1),
                ["observedCollections"] = Seen.Count,
                ["steadyPauseMs"] = Math.Round(steadyPauseMs, 1),
                ["transitionPauseMs"] = Math.Round(transitionPauseMs, 1),
                ["steadyCollections"] = steadyGen0,
                ["transitionCollections"] = transitionGen0,
                ["maxPauseMs"] = Math.Round(Seen.Count == 0 ? 0 : Seen.Max(s => s.PauseMs), 2),
                ["maxEphemeralPauseMs"] = Math.Round(Seen.Where(s => s.Kind == "ephemeral").Select(s => s.PauseMs).DefaultIfEmpty().Max(), 2),
                ["blockingGen2"] = Seen.Count(s => s.Kind == "fullBlocking"),
                ["blockingGen2Compacted"] = Seen.Count(s => s.Kind == "fullBlocking" && s.Compacted),
                ["blockingGen2PauseMs"] = Math.Round(Seen.Where(s => s.Kind == "fullBlocking").Sum(s => s.PauseMs), 1),
                ["backgroundGen2"] = Seen.Count(s => s.Kind == "background"),
                ["ephemeralPauseMs"] = Math.Round(Seen.Where(s => s.Kind == "ephemeral").Sum(s => s.PauseMs), 1),
                ["frameMaxMs"] = Math.Round(sorted[^1], 2),
                ["frameP99Ms"] = Math.Round(sorted[(int)(sorted.Length * 0.99)], 2),
                ["transitionFrameP50Ms"] = Math.Round(sortedTransition[sortedTransition.Length / 2], 2),
                ["transitionFrameMaxMs"] = Math.Round(sortedTransition[^1], 2),
                ["framesOver33Ms"] = frames.Count(x => x > 33.3),
                ["peakHeapMiB"] = _observedPeakHeap >> 20,
                ["peakCommittedMiB"] = _observedPeakCommitted >> 20,
                ["finalHeapMiB"] = any.HeapSizeBytes >> 20,
                ["fragmentedMiB"] = any.FragmentedBytes >> 20,
            };
            using var stream = new System.IO.MemoryStream();
            using (var json = new Utf8JsonWriter(stream)) Write(json, report);
            Console.WriteLine(System.Text.Encoding.UTF8.GetString(stream.ToArray()));
            return 0;
        }

        // NativeAOT has no reflection-based serializer: the few value kinds of the report, written by hand.
        static void Write(Utf8JsonWriter json, object value)
        {
            switch (value)
            {
                case bool b: json.WriteBooleanValue(b); break;
                case string s: json.WriteStringValue(s); break;
                case int i: json.WriteNumberValue(i); break;
                case long l: json.WriteNumberValue(l); break;
                case double d: json.WriteNumberValue(d); break;
                case int[] values: json.WriteStartArray(); foreach (int v in values) json.WriteNumberValue(v); json.WriteEndArray(); break;
                case List<string> lines: json.WriteStartArray(); foreach (string v in lines) json.WriteStringValue(v); json.WriteEndArray(); break;
                case Dictionary<string, string> map:
                    json.WriteStartObject(); foreach (var kv in map) json.WriteString(kv.Key, kv.Value); json.WriteEndObject(); break;
                case Dictionary<string, object> map:
                    json.WriteStartObject(); foreach (var kv in map) { json.WritePropertyName(kv.Key); Write(json, kv.Value); } json.WriteEndObject(); break;
                default: throw new InvalidOperationException(value?.GetType().Name);
            }
        }
    }
}
