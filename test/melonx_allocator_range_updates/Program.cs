using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Program
{
    static int checks;
    static ulong digest = 14695981039346656037;
    static void Check(bool value, string name)
    {
        System.Threading.Interlocked.Increment(ref checks);
        if (!value) throw new Exception(name);
    }
    static void Record(ulong value) => digest = unchecked((digest ^ value) * 1099511628211);
    static List<(ulong Offset, ulong Size)> Ranges(MemoryAllocatorBlockList.Block block)
    {
        var result = new List<(ulong, ulong)>();
        var list = (IEnumerable)typeof(MemoryAllocatorBlockList.Block).GetField("_freeRanges", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(block);
        foreach (object range in list)
        {
            Type type = range.GetType();
            result.Add(((ulong)type.GetProperty("Offset").GetValue(range), (ulong)type.GetProperty("Size").GetValue(range)));
        }
        return result;
    }
    static void RecordRanges(MemoryAllocatorBlockList.Block block)
    {
        var ranges = Ranges(block); Record((ulong)ranges.Count);
        foreach (var range in ranges) { Record(range.Offset); Record(range.Size); }
    }
    sealed class Model
    {
        public List<(ulong Offset, ulong Size)> Free = new();
        public Model(ulong size) => Free.Add((0, size));
        public ulong Allocate(ulong size, ulong alignment)
        {
            for (int i = 0; i < Free.Count; i++)
            {
                var old = Free[i];
                // The valid-case oracle uses wide division rather than production's mask.
                UInt128 alignedWide = ((UInt128)old.Offset + alignment - 1) / alignment * alignment;
                if (alignedWide > ulong.MaxValue) continue;
                ulong aligned = (ulong)alignedWide;
                if (aligned < old.Offset || aligned - old.Offset >= old.Size || size > old.Size - (aligned - old.Offset)) continue;
                Free.RemoveAt(i);
                int index = i;
                if (aligned > old.Offset) Free.Insert(index++, (old.Offset, aligned - old.Offset));
                ulong tail = old.Size - (aligned - old.Offset) - size;
                if (tail != 0) Free.Insert(index, (aligned + size, tail));
                return aligned;
            }
            return ulong.MaxValue;
        }
        public void Release(ulong offset, ulong size)
        {
            Free.Add((offset, size));
            Free.Sort((a, b) => a.Offset.CompareTo(b.Offset));
            for (int i = 1; i < Free.Count;)
            {
                var a = Free[i - 1]; var b = Free[i];
                if (a.Offset + a.Size == b.Offset) { Free[i - 1] = (a.Offset, a.Size + b.Size); Free.RemoveAt(i); }
                else i++;
            }
        }
    }
    static void ValidCases()
    {
        foreach (ulong total in new ulong[] { 1, 2, 7, 64, 4096 })
        foreach (ulong prefix in new ulong[] { 0, 1, 3, 7, 15, 31 })
        foreach (ulong size in new ulong[] { 0, 1, 2, 3, 7, 16, 31, 64, 4096 })
        foreach (ulong alignment in new ulong[] { 1, 2, 4, 8, 16, 64 })
        {
            var block = new MemoryAllocatorBlockList.Block(default, 0, total, false);
            var model = new Model(total);
            if (prefix != 0) Check(block.Allocate(prefix, 1) == model.Allocate(prefix, 1), "prefix oracle");
            ulong result = block.Allocate(size, alignment); ulong expected = model.Allocate(size, alignment);
            Check(result == expected, "wide first-fit oracle");
            Check(Ranges(block).SequenceEqual(model.Free), "exact split list oracle");
            Record(total); Record(prefix); Record(size); Record(alignment); Record(result); RecordRanges(block);
        }
        for (int seed = 0; seed < 16; seed++)
        {
            var block = new MemoryAllocatorBlockList.Block(default, 0, 65536, false);
            var model = new Model(65536); var random = new Random(730019 + seed);
            var active = new List<(ulong Offset, ulong Size)>();
            for (int step = 0; step < 4000; step++)
            {
                if (active.Count > 0 && (active.Count >= 96 || random.Next(100) < 45))
                {
                    int index = random.Next(active.Count); var entry = active[index]; active.RemoveAt(index);
                    block.Free(entry.Offset, entry.Size); model.Release(entry.Offset, entry.Size);
                }
                else
                {
                    ulong size = (ulong)random.Next(1, 2000), alignment = 1UL << random.Next(0, 11);
                    ulong actual = block.Allocate(size, alignment), expected = model.Allocate(size, alignment);
                    Check(actual == expected, "random first-fit"); Record(actual); Record(size); Record(alignment);
                    if (actual != ulong.MaxValue) active.Add((actual, size));
                }
                Check(Ranges(block).SequenceEqual(model.Free), "random complete ranges");
                if (step % 128 == 0) RecordRanges(block);
            }
            foreach (var entry in active) { block.Free(entry.Offset, entry.Size); model.Release(entry.Offset, entry.Size); }
            Check(block.IsTotallyFree() && Ranges(block).SequenceEqual(model.Free), "random full coalescence");
        }
    }
    static void UnusualCases()
    {
        // These histories deliberately include zero/duplicate/overlapping or wrapped
        // entries. Compare their full historical results across both executables.
        foreach (int history in Enumerable.Range(0, 7))
        foreach (ulong size in new ulong[] { 0, 1, 2, 7, 8, 16, ulong.MaxValue })
        foreach (ulong alignment in new ulong[] { 0, 1, 2, 3, 4, 8, 16, 1UL << 63, ulong.MaxValue })
        {
            var block = new MemoryAllocatorBlockList.Block(default, 0, 16, false);
            if (history >= 4) block.Allocate(16, 1);
            switch (history)
            {
                case 1: block.Free(0, 0); break;
                case 2: block.Free(0, 8); break;
                case 3: block.Free(4, 20); break;
                case 4: block.Free(ulong.MaxValue - 7, 16); break;
                case 5: block.Free(ulong.MaxValue - 15, 15); block.Free(ulong.MaxValue - 8, 0); break;
                case 6: block.Free(32, 16); block.Free(32, 0); block.Free(32, 8); break;
            }
            Record((ulong)history); Record(size); Record(alignment);
            ulong result = block.Allocate(size, alignment); Record(result); RecordRanges(block);
            if (result != ulong.MaxValue)
            {
                block.Free(result, size); RecordRanges(block);
            }
            // Exercise coalescing itself with zero, wrapped and duplicate starts.
            block.Free(alignment, size); RecordRanges(block);
            Check(true, "unusual differential history completed");
        }
    }
    static void NativeLifetimes()
    {
        var api = new Vk { StorePayloads = true };
        var allocator = new MemoryAllocatorBlockList(api, default, 0, 65536, false);
        var random = new Random(441122); var live = new List<(MemoryAllocation Allocation, int Id)>();
        int id = 0;
        for (int step = 0; step < 2500; step++)
        {
            if (live.Count > 0 && (live.Count > 64 || random.Next(100) < 45))
            {
                int index = random.Next(live.Count); var entry = live[index]; live.RemoveAt(index);
                Check(api.CheckPattern(entry.Allocation.Memory, entry.Allocation.Offset, entry.Allocation.Size, entry.Id), "native bytes survive");
                entry.Allocation.Dispose();
            }
            else
            {
                ulong size = (ulong)random.Next(1, 2000), alignment = 1UL << random.Next(0, 9);
                var allocation = allocator.Allocate(size, alignment, random.Next(2) == 0);
                foreach (var entry in live)
                    Check(allocation.Memory.Handle != entry.Allocation.Memory.Handle || allocation.Offset >= entry.Allocation.Offset + entry.Allocation.Size ||
                        entry.Allocation.Offset >= allocation.Offset + allocation.Size, "native live ranges disjoint");
                api.StorePattern(allocation.Memory, allocation.Offset, allocation.Size, ++id); live.Add((allocation, id));
                Record(allocation.Memory.Handle); Record(allocation.Offset); Record(allocation.Size);
            }
        }
        foreach (var entry in live) { Check(api.CheckPattern(entry.Allocation.Memory, entry.Allocation.Offset, entry.Allocation.Size, entry.Id), "final bytes"); entry.Allocation.Dispose(); }
        allocator.Dispose(); Check(api.Live == 0 && api.Mapped == 0 && api.Allocations == api.Frees && api.Maps == api.Unmaps, "native lifecycle");
    }
    static void Concurrent()
    {
        var block = new MemoryAllocatorBlockList.Block(default, 0, 1024 * 1024, false);
        var active = new List<(ulong Offset, ulong Size)>(); object gate = new();
        Parallel.For(0, 8, worker =>
        {
            for (int i = 0; i < 1000; i++)
            {
                ulong size = (ulong)(1 + (worker * 7 + i) % 64); ulong offset = block.Allocate(size, 16);
                Check(offset != ulong.MaxValue, "concurrent capacity");
                lock (gate)
                {
                    foreach (var entry in active) Check(offset >= entry.Offset + entry.Size || entry.Offset >= offset + size, "concurrent disjoint");
                    active.Add((offset, size));
                }
                lock (gate) { Check(active.Remove((offset, size)), "active registration"); block.Free(offset, size); }
            }
        });
        Check(active.Count == 0 && block.IsTotallyFree(), "concurrent full release");
    }
    static MemoryAllocatorBlockList.Block Shape(int holes)
    {
        var block = new MemoryAllocatorBlockList.Block(default, 0, (ulong)(129 + holes * 128), false);
        block.Allocate(1, 1); ulong target = block.Allocate(127, 1); block.Allocate(1, 1);
        var offsets = new List<ulong>();
        for (int i = 0; i < holes; i++) { offsets.Add(block.Allocate(64, 1)); block.Allocate(64, 1); }
        block.Free(target, 127); foreach (ulong offset in offsets) block.Free(offset, 64);
        return block;
    }
    static object[] Benchmarks()
    {
        var rows = new List<object>();
        foreach (int holes in new[] { 0, 1, 32, 256, 4096 })
        foreach (string shape in new[] { "tail", "prefix-tail", "prefix", "full" })
        {
            ulong size = shape == "prefix" ? 112UL : shape == "full" ? 127UL : 32UL;
            ulong alignment = shape.StartsWith("prefix") ? 16UL : 1UL;
            var block = Shape(holes); ulong expected = alignment == 1 ? 1UL : 16UL;
            int iterations = holes >= 4096 ? 1000 : holes >= 256 ? 10000 : 30000;
            for (int i = 0; i < 1000; i++) { ulong offset = block.Allocate(size, alignment); block.Free(offset, size); }
#if RANGE_PROBE
            RangeBookkeepingProbe.Reset();
#endif
            long allocated = GC.GetAllocatedBytesForCurrentThread(), started = Stopwatch.GetTimestamp();
            for (int i = 0; i < iterations; i++)
            {
                ulong offset = block.Allocate(size, alignment);
                if (offset != expected) throw new Exception("benchmark first fit");
                block.Free(offset, size);
            }
            long elapsed = Stopwatch.GetTimestamp() - started; long bytes = GC.GetAllocatedBytesForCurrentThread() - allocated;
#if RANGE_PROBE
            long shifts = RangeBookkeepingProbe.ShiftedElements, replacements = RangeBookkeepingProbe.Replacements,
                removals = RangeBookkeepingProbe.Removals, inserts = RangeBookkeepingProbe.Inserts, searches = RangeBookkeepingProbe.Searches;
#else
            long shifts = -1, replacements = -1, removals = -1, inserts = -1, searches = -1;
#endif
            Check(bytes == 0, "warm range churn allocations");
            rows.Add(new { holes, shape, iterations, allocatedBytes = bytes, shiftedElements = shifts, replacements,
                removals, inserts, searches, nsPerOperation = elapsed * (1e9 / Stopwatch.Frequency) / iterations });
        }
        return rows.ToArray();
    }
    static void Main()
    {
        ValidCases(); UnusualCases(); NativeLifetimes();
        ulong semanticDigest = digest;
        Concurrent(); var benchmarks = Benchmarks();
        Console.WriteLine(JsonSerializer.Serialize(new { checks, semanticDigest, concurrentOperations = 8000,
            validRandomOperations = 64000, exhaustiveCases = 1620, unusualCases = 441, benchmarks }));
    }
}
