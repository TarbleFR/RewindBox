// Gate of adapt_bgc_suspension_pending: what a thread that allocates sees while background gen2 collections run, on
// the NativeAOT 10.0.0 runtime with the Core's own sched_yield linked in (control: as prepared; candidate: adapted).
//
// load <seconds> <liveMiB> <requestEveryMs>
//   A long-lived graph of 40-byte objects with two references each (what the background collector has to mark), two
//   threads that allocate small objects, 256 KiB arrays (large object heap) and rewrite references of the old graph
//   and of a large array, and the main thread, which asks for a background gen2 every <requestEveryMs> (the
//   keep-alive's own call) and reads the record of each ephemeral collection. Reports the ephemeral pauses as the runtime measured them (GCMemoryInfo.PauseDurations), those from the
//   first request on apart, the allocating thread's longest stall, and whether the graph is intact at the end.
// quiet <count> <liveMiB> <gapMs>
//   No allocating thread: <count> background gen2s, <gapMs> apart, and the process's processor time for them (the
//   background collector's own work, with the mode changes the raised flag adds at each allow_fgc).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;

static class Program
{
    sealed class Node { public Node A, B; public long Tag; }

    const int Allocators = 2;

    static volatile bool _stop, _measuring;
    static long _maxStallTicks, _loops;
    static byte[][] _held;

    static int Main(string[] args)
    {
        string mode = args[0];
        int first = int.Parse(args[1]);
        int liveMb = int.Parse(args[2]);
        int third = int.Parse(args[3]);

        int count = (int)(liveMb * 1024L * 1024L / 40);
        Node[] nodes = new Node[count];
        Random random = new(7);
        for (int i = 0; i < count; i++) nodes[i] = new Node { Tag = i };
        for (int i = 0; i < count; i++) { nodes[i].A = nodes[random.Next(count)]; nodes[i].B = nodes[random.Next(count)]; }
        // A large object heap of 128 MiB that stays, as an engine's does: what is allocated there during one background
        // collection stays far under its size (past it, the collector makes the allocating thread wait for the end).
        byte[][] held = new byte[256][];
        for (int i = 0; i < held.Length; i++) held[i] = new byte[512 * 1024];
        GC.Collect(2, GCCollectionMode.Forced, true, true);
        GC.Collect(2, GCCollectionMode.Forced, true, true);
        GC.KeepAlive(held);
        _held = held;

        return mode == "quiet" ? Quiet(nodes, first, third) : Load(nodes, first, liveMb, third);
    }

    static int Quiet(Node[] nodes, int requests, int gapMs)
    {
        long gen2Before = GC.CollectionCount(2), blockingBefore = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
        // The first request creates the background collector's thread (and may fall back to a blocking gen2: .NET 10.0.0).
        GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
        Thread.Sleep(gapMs);
        TimeSpan before = Environment.CpuUsage.TotalTime;
        Stopwatch clock = Stopwatch.StartNew();
        for (int i = 0; i < requests; i++)
        {
            GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
            Thread.Sleep(gapMs);
        }
        double cpuMs = (Environment.CpuUsage.TotalTime - before).TotalMilliseconds;
        Console.WriteLine(FormattableString.Invariant(
            $"RESULT mode=quiet requests={requests} cpuMs={cpuMs:F0} wallMs={clock.ElapsedMilliseconds} gen2={GC.CollectionCount(2) - gen2Before} fullBlocking={(GC.GetGCMemoryInfo(GCKind.FullBlocking).Index != blockingBefore ? 1 : 0)} badNodes={Bad(nodes)}"));
        return 0;
    }

    static int Load(Node[] nodes, int seconds, int liveMb, int requestEveryMs)
    {
        Thread[] allocators = new Thread[Allocators];
        for (int i = 0; i < Allocators; i++)
        {
            int seed = 11 + i;
            allocators[i] = new Thread(() => Allocate(nodes, seed)) { IsBackground = true };
            allocators[i].Start();
        }

        List<double> all = new(), after = new();
        List<string> longOnes = new();
        Stopwatch clock = Stopwatch.StartNew();
        long lastEphemeral = GC.GetGCMemoryInfo(GCKind.Ephemeral).Index;
        long lastBackground = GC.GetGCMemoryInfo(GCKind.Background).Index, blockingBefore = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
        long nextRequest = requestEveryMs, backgrounds = 0, requests = 0, smallPromotionLong = 0;

        while (clock.ElapsedMilliseconds < seconds * 1000L)
        {
            Thread.Sleep(1);
            GCMemoryInfo e = GC.GetGCMemoryInfo(GCKind.Ephemeral);
            if (e.Index != lastEphemeral)
            {
                lastEphemeral = e.Index;
                double ms = 0;
                foreach (TimeSpan pause in e.PauseDurations) ms += pause.TotalMilliseconds;
                all.Add(ms);
                if (requests > 0)
                {
                    after.Add(ms);
                    if (ms >= 250 && e.PromotedBytes < 16L * 1024 * 1024) smallPromotionLong++;
                    if (ms >= 100) longOnes.Add(FormattableString.Invariant($"gen{e.Generation}:{ms:F0}ms:{e.PromotedBytes >> 20}MiB"));
                }
            }
            GCMemoryInfo b = GC.GetGCMemoryInfo(GCKind.Background);
            if (b.Index != lastBackground) { lastBackground = b.Index; backgrounds++; }
            if (clock.ElapsedMilliseconds >= nextRequest)
            {
                nextRequest += requestEveryMs;
                // The keep-alive's request (BackgroundGcKeepAlive.RequestBackgroundCollection).
                GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
                if (requests++ == 0) { Interlocked.Exchange(ref _maxStallTicks, 0); _measuring = true; }
            }
        }
        _stop = true;
        foreach (Thread allocator in allocators) allocator.Join();

        after.Sort();
        double sum = 0, sumAfter = 0;
        int over100 = 0, over250 = 0;
        foreach (double p in all) sum += p;
        foreach (double p in after) { sumAfter += p; if (p >= 100) over100++; if (p >= 250) over250++; }
        double max = after.Count > 0 ? after[^1] : 0, median = after.Count > 0 ? after[after.Count / 2] : 0;
        long bad = Bad(nodes);
        Console.WriteLine(FormattableString.Invariant(
            $"RESULT mode=load seconds={seconds} liveMb={liveMb} ephemeralSeen={all.Count} pauseSumMs={sum:F0} afterSeen={after.Count} afterSumMs={sumAfter:F0} afterMedianMs={median:F1} afterMaxMs={max:F1} afterOver100={over100} afterOver250={over250} afterOver250SmallPromotion={smallPromotionLong} allocatorMaxStallMs={Interlocked.Read(ref _maxStallTicks) * 1000.0 / Stopwatch.Frequency:F1} requests={requests} backgroundRecords={backgrounds} fullBlocking={(GC.GetGCMemoryInfo(GCKind.FullBlocking).Index != blockingBefore ? 1 : 0)} loops={Interlocked.Read(ref _loops)} badNodes={bad}"));
        Console.WriteLine("LONG " + string.Join(" ", longOnes));
        return bad == 0 ? 0 : 3;
    }

    // Every node still carries its tag and points at two nodes of the array.
    static long Bad(Node[] nodes)
    {
        long bad = 0;
        for (int i = 0; i < nodes.Length; i++)
        {
            Node n = nodes[i];
            if (n == null || n.Tag != i || n.A == null || n.B == null || (ulong)n.A.Tag >= (ulong)nodes.Length || (ulong)n.B.Tag >= (ulong)nodes.Length ||
                !ReferenceEquals(nodes[n.A.Tag], n.A) || !ReferenceEquals(nodes[n.B.Tag], n.B))
            {
                bad++;
            }
        }
        return bad;
    }

    static void Allocate(Node[] nodes, int seed)
    {
        Random random = new(seed);
        Node[] young = new Node[4096];
        // The large object heap, as the engine uses it: buffers of one size that come and go, and one array of
        // references whose slots keep pointing at young objects.
        byte[][] buffers = new byte[24][];
        Node[] wide = new Node[64 * 1024];
        long last = Stopwatch.GetTimestamp();
        long loops = 0, measuredFrom = -1;
        while (!_stop)
        {
            for (int i = 0; i < 256; i++)
            {
                Node n = new() { Tag = -1 };
                young[(loops + i) & 4095] = n;
                n.A = young[random.Next(4096)];
            }
            // An old reference rewritten, as a running engine does: the collector's cards and revisited pages.
            nodes[random.Next(nodes.Length)].B = nodes[random.Next(nodes.Length)];
            byte[] scratch = new byte[2048];
            scratch[0] = 1;
            wide[random.Next(wide.Length)] = young[random.Next(4096)];
            if ((loops & 511) == 0)
            {
                byte[] buffer = new byte[256 * 1024];
                buffer[loops & 4095] = (byte)loops;
                buffers[(loops >> 9) % buffers.Length] = buffer;
            }
            loops++;
            long now = Stopwatch.GetTimestamp();
            long gap = now - last;
            last = now;
            if (_measuring)
            {
                if (measuredFrom < 0) measuredFrom = loops;
                else
                {
                    long seen = Interlocked.Read(ref _maxStallTicks);
                    while (gap > seen)
                    {
                        long was = Interlocked.CompareExchange(ref _maxStallTicks, gap, seen);
                        if (was == seen) break;
                        seen = was;
                    }
                }
            }
        }
        // Iterations from the first request on.
        Interlocked.Add(ref _loops, measuredFrom < 0 ? 0 : loops - measuredFrom);
        GC.KeepAlive(buffers);
        GC.KeepAlive(wide);
    }
}
