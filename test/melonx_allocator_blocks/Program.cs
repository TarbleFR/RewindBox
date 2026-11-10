using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Program
{
    static long Checks;
    static void Check(bool value, string message)
    {
        Interlocked.Increment(ref Checks);
        if (!value) throw new InvalidOperationException(message);
    }
    static bool Overlap(MemoryAllocation a, MemoryAllocation b)
        => a.Memory.Handle == b.Memory.Handle && a.Offset < b.Offset + b.Size && b.Offset < a.Offset + a.Size;
    static object RandomLifetimes(int poolSize)
    {
        var api = new Vk { StorePayloads = true }; var allocator = new MemoryAllocatorBlockList(api, default, 3, poolSize, true);
        var random = new Random(8216); var live = new List<MemoryAllocation>(); var ids = new List<int>();
        var trace = new StringBuilder(); var requests = new StringBuilder();
        int allocated = 0, released = 0; long payloadBytesChecked = 0;
        for (int i = 0; i < 16000; i++)
        {
            if (live.Count > 0 && (live.Count > 80 || random.Next(100) < 49))
            {
                int index = random.Next(live.Count); MemoryAllocation entry = live[index];
                int id = ids[index];
                Check(api.CheckPattern(entry.Memory, entry.Offset, entry.Size, id), "payload survives allocation/free traffic");
                payloadBytesChecked += (long)entry.Size;
                live.RemoveAt(index); ids.RemoveAt(index); entry.Dispose(); released++;
                requests.Append('F').Append(id).Append(';');
                trace.Append('F').Append(entry.Memory.Handle).Append(':').Append(entry.Offset).Append(';');
            }
            else
            {
                ulong size = random.Next(6) == 0 ? (ulong)random.Next(2048, 14000) : (ulong)random.Next(16, 1600);
                ulong alignment = 1UL << random.Next(0, 10); bool mapped = random.Next(2) == 0;
                MemoryAllocation entry = allocator.Allocate(size, alignment, mapped); allocated++;
                Check(entry.Memory.Handle != 0 && entry.Offset % alignment == 0 && entry.Size == size,
                      "allocation identity/size/alignment");
                Check((entry.HostPointer != 0) == mapped, "requested host mapping");
                foreach (MemoryAllocation old in live) Check(!Overlap(old, entry), "no overlap of active allocations");
                live.Add(entry); ids.Add(allocated);
                api.StorePattern(entry.Memory, entry.Offset, entry.Size, allocated);
                requests.Append('A').Append(allocated).Append(':').Append(size).Append(':').Append(alignment)
                        .Append(':').Append(mapped ? 1 : 0).Append(';');
                trace.Append('A').Append(entry.Memory.Handle).Append(':').Append(entry.Offset).Append(':').Append(entry.Size)
                     .Append(':').Append(mapped ? 1 : 0).Append(';');
            }
        }
        for (int i = 0; i < live.Count; i++)
        {
            MemoryAllocation entry = live[i];
            Check(api.CheckPattern(entry.Memory, entry.Offset, entry.Size, ids[i]), "final payload intact");
            payloadBytesChecked += (long)entry.Size;
            entry.Dispose(); released++;
        }
        Check(api.Live == 0 && api.Mapped == 0 && api.Allocations == api.Frees && api.Maps == api.Unmaps,
              "normal resources completely released");
        allocator.Dispose();
        foreach (ulong invalid in new ulong[] { 0, 0x80000000UL, 0x100000000UL })
        {
            bool threw = false;
            try { allocator.Allocate(20, invalid, false); } catch (ArgumentOutOfRangeException) { threw = true; }
            Check(threw && api.Live == 0, "invalid alignment rejected before allocation");
        }
        return new { poolSize, allocated, released, payloadBytesChecked, api.Allocations, api.Frees, api.Maps, api.Unmaps,
            peakNativeBytes = api.PeakBytes,
            requestTraceSha256 = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(requests.ToString()))),
            traceSha256 = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(trace.ToString()))) };
    }
    static object ImportedArena()
    {
        var api = new Vk(); DeviceMemory memory = api.Import(16384);
        var block = new MemoryAllocatorBlockList.Block(memory, (nint)0x70000000, 16384, false, importedHostPointer: true);
        var allocator = new MemoryAllocatorBlockList(api, default, 7, block);
        var ranges = new List<MemoryAllocation>();
        for (int i = 0; i < 16; i++)
        {
            MemoryAllocation entry = allocator.Allocate(1024, 256, true);
            Check(entry.Memory.Handle == memory.Handle && entry.Offset == (ulong)i * 1024, "imported first-fit offset");
            Check(entry.HostPointer == (nint)(0x70000000 + i * 1024), "imported pointer offset");
            ranges.Add(entry);
        }
        Check(allocator.Allocate(1, 1, true).Memory.Handle == 0, "fixed arena cannot grow");
        Check(allocator.Allocate(1, 1, false).Memory.Handle == 0, "fixed arena mapping mismatch");
        for (int i = 0; i < ranges.Count; i += 2) ranges[i].Dispose();
        Check(allocator.Allocate(1025, 1, true).Memory.Handle == 0, "fixed arena fragmentation is preserved");
        for (int i = 1; i < ranges.Count; i += 2) ranges[i].Dispose();
        Check(api.Live == 1 && api.Frees == 0, "fixed arena persists while empty");
        MemoryAllocation whole = allocator.Allocate(16384, 1024, true);
        Check(whole.Offset == 0 && whole.Memory.Handle == memory.Handle, "fixed arena coalesces");
        whole.Dispose(); allocator.Dispose();
        Check(api.Live == 0 && api.Frees == 1 && api.Maps == 0 && api.Unmaps == 0 && api.Allocations == 0,
              "imported arena freed without mapping or growth");
        return new { size = 16384, slices = 16, api.Allocations, api.Frees, api.Maps, api.Unmaps };
    }
    static object ConcurrentLifetimes(int poolSize)
    {
        var api = new Vk(); var allocator = new MemoryAllocatorBlockList(api, default, 0, poolSize, false);
        var active = new List<MemoryAllocation>(); var gate = new object(); int count = 0;
        Parallel.For(0, 8, worker =>
        {
            var local = new List<MemoryAllocation>();
            for (int round = 0; round < 160; round++)
            {
                for (int n = 0; n < 8; n++)
                {
                    MemoryAllocation entry = allocator.Allocate((ulong)(128 + (worker * 32) + n), 64, (worker & 1) != 0);
                    lock (gate)
                    {
                        foreach (var other in active) Check(!Overlap(other, entry), "concurrent live ranges do not overlap");
                        active.Add(entry);
                    }
                    local.Add(entry); Interlocked.Increment(ref count);
                }
                foreach (var entry in local)
                {
                    lock (gate)
                    {
                        int index = active.FindIndex(a => a.Memory.Handle == entry.Memory.Handle && a.Offset == entry.Offset);
                        Check(index >= 0, "concurrent resource registered"); active.RemoveAt(index);
                    }
                    entry.Dispose();
                }
                local.Clear();
            }
        });
        Check(active.Count == 0 && api.Live == 0 && api.Mapped == 0 && api.Allocations == api.Frees && api.Maps == api.Unmaps,
              "concurrent teardown releases every native resource");
        allocator.Dispose();
        // Allocation counts depend on scheduling. Report only invariant workload counts.
        return new { poolSize, workers = 8, allocations = count, nativeLeaks = api.Live, mappedLeaks = api.Mapped };
    }
    static object Failures(bool injected)
    {
        var cases = new List<object>();
        foreach (string mode in new[] { "map-result", "map-throw", "allocate-result", "block-setup", "publication" })
        {
            if (!injected && (mode == "block-setup" || mode == "publication")) continue;
            var api = new Vk(); var allocator = new MemoryAllocatorBlockList(api, default, 0, 4096, true);
            int caught = 0;
            for (int i = 0; i < 16; i++)
            {
                if (mode == "map-result") api.MapFailures = 1;
                if (mode == "map-throw") api.MapThrows = 1;
                if (mode == "allocate-result") api.AllocationFailures = 1;
                if (mode == "block-setup") AllocationProbe.FailBlock = true;
                if (mode == "publication") AllocationProbe.FailPublication = true;
                try { allocator.Allocate(128, 16, true); }
                catch (Exception error) when (error is VulkanException || error is InvalidOperationException || error is OutOfMemoryException)
                { caught++; }
            }
            Check(caught == 16, "injected failure propagated");
            allocator.Dispose();
            cases.Add(new { mode, attempts = 16, caught, nativeLeaks = api.Live, mappedLeaks = api.Mapped,
                            api.Allocations, api.Frees, api.Maps, api.Unmaps });
        }
        return cases;
    }
    static object SearchCase(string mode, int dedicatedCount)
    {
        var api = new Vk(); var allocator = new MemoryAllocatorBlockList(api, default, 0, 4096, true);
        var dedicated = new List<MemoryAllocation>();
        for (int i = 0; i < dedicatedCount; i++)
        {
            ulong size = mode == "small-dedicated" ? 2048UL : mode == "equal-dedicated" ? 4096UL : 8192UL;
            dedicated.Add(allocator.Allocate(size, 1, false));
        }
        MemoryAllocation anchor = allocator.Allocate(16, 16, false);
        for (int i = 0; i < 1000; i++) allocator.Allocate(64, 16, false).Dispose();
        const int count = 10000;
        AllocationProbe.SizeReads = 0; AllocationProbe.BlockVisits = 0;
        long beginAlloc = GC.GetAllocatedBytesForCurrentThread();
        long beginTime = Stopwatch.GetTimestamp();
        for (int i = 0; i < count; i++)
        {
            MemoryAllocation entry = allocator.Allocate(64, 16, false);
            if (entry.Memory.Handle != anchor.Memory.Handle || entry.Offset != 16)
                throw new InvalidOperationException("different first pooled candidate");
            entry.Dispose();
        }
        long ticks = Stopwatch.GetTimestamp() - beginTime;
        long allocated = GC.GetAllocatedBytesForCurrentThread() - beginAlloc;
        long sizeReads = AllocationProbe.SizeReads; long blockVisits = AllocationProbe.BlockVisits;
        anchor.Dispose(); foreach (var entry in dedicated) entry.Dispose(); allocator.Dispose();
        Check(api.Live == 0, "search benchmark cleanup");
        return new { mode, dedicatedCount, queries = count, allocatedBytes = allocated, sizeReads, blockVisits,
                     elapsedMs = (double)ticks * 1000 / Stopwatch.Frequency };
    }
    static object DedicatedChurn(int count)
    {
        var api = new Vk(); var allocator = new MemoryAllocatorBlockList(api, default, 0, 16, true);
        var entries = new MemoryAllocation[count];
        for (int i = 0; i < count; i++) entries[i] = allocator.Allocate(4096, 64, false);
        for (int i = 0; i < 1000; i++)
        {
            int index = i % count; entries[index].Dispose(); entries[index] = allocator.Allocate(4096, 64, false);
        }
        AllocationProbe.BlockVisits = 0; AllocationProbe.Comparisons = 0;
        long beginAlloc = GC.GetAllocatedBytesForCurrentThread();
        long beginTime = Stopwatch.GetTimestamp();
        const int operations = 10000;
        for (int i = 0; i < operations; i++)
        {
            int index = i % count; entries[index].Dispose(); entries[index] = allocator.Allocate(4096, 64, false);
        }
        long ticks = Stopwatch.GetTimestamp() - beginTime;
        long bytes = GC.GetAllocatedBytesForCurrentThread() - beginAlloc;
        long visits = AllocationProbe.BlockVisits, comparisons = AllocationProbe.Comparisons;
        foreach (var entry in entries) entry.Dispose(); allocator.Dispose();
        Check(api.Live == 0 && api.Frees == api.Allocations, "dedicated churn resources released once");
        return new { liveBlocks = count, operations, allocatedBytes = bytes, blockVisits = visits, comparisons,
                     elapsedMs = (double)ticks * 1000 / Stopwatch.Frequency };
    }
    static object BookkeepingAllocations()
    {
        const int count = 10000;
        object keep = null;
        // No native driver allocations occur in this measurement.
        long begin = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < count; i++) keep = new MemoryAllocatorBlockList.Block(default, 0, 4096, true);
        long blockBytes = GC.GetAllocatedBytesForCurrentThread() - begin;
        GC.KeepAlive(keep);
        var api = new Vk();
        begin = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < count; i++) keep = new MemoryAllocatorBlockList(api, default, 0, 16, true);
        long listBytes = GC.GetAllocatedBytesForCurrentThread() - begin;
        GC.KeepAlive(keep);
        return new { count, blockBytes, blockListBytes = listBytes };
    }
    static void Main(string[] args)
    {
        bool injected = args.Length > 0 && args[0] == "instrumented";
        var random = new[] { RandomLifetimes(4096), RandomLifetimes(16) };
        var imported = ImportedArena();
        var concurrent = new[] { ConcurrentLifetimes(65536), ConcurrentLifetimes(16) };
        var failures = Failures(injected);
        var searches = new[] { SearchCase("none", 0), SearchCase("large-dedicated", 2048),
            SearchCase("small-dedicated", 2048), SearchCase("equal-dedicated", 2048) };
        var churn = new[] { DedicatedChurn(1), DedicatedChurn(32), DedicatedChurn(2048) };
        var bookkeeping = BookkeepingAllocations();
        Console.WriteLine(JsonSerializer.Serialize(new { checks = Checks, random, imported, concurrent,
                                                       failures, searches, churn, bookkeeping, nativeDriverTested = false }));
    }
}
