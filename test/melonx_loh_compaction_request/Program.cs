// Fixture of test/melonx_loh_compaction_request_test.py: the production LargeObjectHeapRequest (Switch.cs, between its
// markers) with the host's segments collector and the Core's GC settings. Modes: control (no request), candidate.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime;
using System.Text.Json;

namespace Ryujinx.HLE
{
    internal static class Program
    {
        private const int MiB = 1024 * 1024;

        private static Dictionary<string, object> State()
        {
            GCMemoryInfo info = GC.GetGCMemoryInfo();
            ReadOnlySpan<GCGenerationInfo> g = info.GenerationInfo;
            return new Dictionary<string, object>
            {
                ["index"] = info.Index,
                ["lohMiB"] = g.Length > 3 ? g[3].SizeAfterBytes / MiB : -1,
                ["lohFreeMiB"] = g.Length > 3 ? g[3].FragmentationAfterBytes / MiB : -1,
                ["committedMiB"] = info.TotalCommittedBytes / MiB,
                ["rssMiB"] = Process.GetCurrentProcess().WorkingSet64 / MiB,
                ["mode"] = GCSettings.LargeObjectHeapCompactionMode.ToString(),
            };
        }

        private static int Main(string[] args)
        {
            string mode = args[0];
            long m = LargeObjectHeapRequest.MinimumFreeBytes;
            var policy = new Dictionary<string, bool>
            {
                ["free256MiBDevice15"] = LargeObjectHeapRequest.ShouldRequest(m, 15, 5, -1, false),
                ["freeUnder256MiB"] = LargeObjectHeapRequest.ShouldRequest(m - 1, 15, 5, -1, false),
                ["device16"] = LargeObjectHeapRequest.ShouldRequest(m, 16, 5, -1, false),
                ["deviceUnknown"] = LargeObjectHeapRequest.ShouldRequest(m, -1, 5, -1, false),
                ["sameCollection"] = LargeObjectHeapRequest.ShouldRequest(m, 15, 5, 5, false),
                ["noCollectionYet"] = LargeObjectHeapRequest.ShouldRequest(m, 15, 0, -1, false),
                ["pending"] = LargeObjectHeapRequest.ShouldRequest(m, 15, 5, -1, true),
            };

            // A large object heap with about 320 MiB of free space after a sweep: 640 arrays of 1 MiB, every other one kept.
            var all = new byte[640][];
            for (int i = 0; i < all.Length; i++)
            {
                all[i] = new byte[MiB];
                // Every page written, as a heap's live and dead large objects are.
                Array.Fill(all[i], (byte)(i * 3 + 1));
                all[i][0] = (byte)i;
                all[i][MiB - 1] = (byte)(i * 7);
            }
            var kept = new List<byte[]>();
            for (int i = 0; i < all.Length; i += 2) kept.Add(all[i]);
            Array.Clear(all);
            GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: false);
            GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: false);
            var before = State();

            var results = new Dictionary<string, object>();
            if (mode == "candidate")
            {
                results["notConstrained"] = LargeObjectHeapRequest.OnHostPressure(false, 9);
                results["deviceNotShort"] = LargeObjectHeapRequest.OnHostPressure(true, 40);
                results["modeAfterRefusals"] = GCSettings.LargeObjectHeapCompactionMode.ToString();
                results["request"] = LargeObjectHeapRequest.OnHostPressure(true, 9);
                results["modeAfterRequest"] = GCSettings.LargeObjectHeapCompactionMode.ToString();
                results["secondWhilePending"] = LargeObjectHeapRequest.OnHostPressure(true, 9);
                results["requests"] = LargeObjectHeapRequest.Requests;
                results["lastFreeMiB"] = LargeObjectHeapRequest.LastFreeBytes / MiB;
            }

            // The collector's own blocking gen2 (no compaction asked by the caller): what consumes the request.
            GC.Collect(2, GCCollectionMode.Default, blocking: true);
            var after = State();

            if (mode == "candidate")
            {
                // The request was consumed; that collection left little free space: no new request.
                results["afterConsumed"] = LargeObjectHeapRequest.OnHostPressure(true, 9);
                results["requestsAtEnd"] = LargeObjectHeapRequest.Requests;
            }

            bool intact = true;
            for (int k = 0; k < kept.Count; k++)
            {
                int i = k * 2;
                intact &= kept[k].Length == MiB && kept[k][0] == (byte)i && kept[k][MiB - 1] == (byte)(i * 7) &&
                          kept[k][MiB / 2] == (byte)(i * 3 + 1);
            }

            var gcConfig = new Dictionary<string, string>();
            foreach (var pair in GC.GetConfigurationVariables())
            {
                gcConfig[pair.Key] = pair.Value?.ToString();
            }

            Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
            {
                ["mode"] = mode, ["policy"] = policy, ["before"] = before, ["after"] = after, ["results"] = results,
                ["liveIntact"] = intact, ["gcConfig"] = gcConfig,
            }));
            GC.KeepAlive(kept);
            return 0;
        }
    }
}
