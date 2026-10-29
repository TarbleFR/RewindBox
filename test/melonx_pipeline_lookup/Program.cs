using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;

static class Program
{
    static int _checks;
    static long _sink;

    struct Key : IRefEquatable<Key>
    {
        public int Id;
        public int Hash;
        public static long HashCalls;
        public bool Equals(ref Key other) => Id == other.Id;
        public override int GetHashCode() { HashCalls++; return Hash; }
    }

    struct CountedPipeline : IRefEquatable<CountedPipeline>
    {
        public PipelineUid Value;
        public static long Comparisons;
        public bool Equals(ref CountedPipeline other)
        {
            Comparisons++;
            return Value.Equals(ref other.Value);
        }
        public override int GetHashCode() => Value.GetHashCode();
    }

    sealed class Payload { }

    static void Check(bool value, string message)
    {
        _checks++;
        if (!value) throw new Exception(message);
    }

    static Key MakeKey(int id) => new() { Id = id, Hash = id % 3 - 1 };

    static void TableSemantics()
    {
        HashTableSlim<Key, int> table = new();
        List<(int Id, int Value)> oracle = new();
        Random random = new(71823);
        for (int i = 1; i <= 6000; i++)
        {
            int id = random.Next(80), action = random.Next(3);
            Key key = MakeKey(id);
            int position = oracle.FindIndex(x => x.Id == id);
            if (action == 0)
            {
                table.Add(ref key, i);
                oracle.Add((id, i));
            }
            else if (action == 1)
            {
                Check(table.Remove(ref key) == (position >= 0), "remove result");
                if (position >= 0) oracle.RemoveAt(position);
            }
            else
            {
                bool found = table.TryGetValue(ref key, out int value);
                Check(found == (position >= 0), "lookup result");
                Check(value == (position >= 0 ? oracle[position].Value : 0), "first duplicate and default miss");
            }
            if (i % 50 == 0)
            {
                Check(table.Values.Order().SequenceEqual(oracle.Select(x => x.Value).Order()), "value enumeration after grow/remove");
                Check(table.Keys.Select(x => x.Id).Order().SequenceEqual(oracle.Select(x => x.Id).Order()), "key enumeration after grow/remove");
            }
        }
        foreach (var item in oracle)
        {
            Key key = MakeKey(item.Id);
            Check(table.Remove(ref key), "remove every duplicate");
        }
        Check(!table.Keys.Any() && !table.Values.Any(), "empty enumerators");
        Key newKey = new() { Id = 987, Hash = int.MinValue };
        table.Add(ref newKey, 55);
        Check(table.TryGetValue(ref newKey, out int result) && result == 55, "reuse after removing all entries");

        HashTableSlim<Key, Payload> nullable = new();
        nullable.Add(ref newKey, null);
        Check(nullable.TryGetValue(ref newKey, out var nullValue) && nullValue == null, "cached null is distinct from absence");
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference AddAndRemove(HashTableSlim<Key, Payload> table)
    {
        Key key = MakeKey(1);
        Payload value = new();
        WeakReference weak = new(value);
        table.Add(ref key, value);
        Check(table.Remove(ref key), "remove retained value");
        return weak;
    }

    static bool RemovedValueRetained()
    {
        HashTableSlim<Key, Payload> table = new();
        WeakReference weak = AddAndRemove(table);
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        bool retained = weak.IsAlive;
        GC.KeepAlive(table);
        return retained;
    }

    static PipelineUid Pipeline(int[] offsets)
    {
        PipelineUid key = new()
        {
            Id0 = 0x1122334455667788,
            Id1 = 0x1029384756,
            Id5 = ((ulong)offsets.Length << 38) | (1UL << 46),
            Id6 = 1UL << 8,
            LogicOpsAllowed = true
        };
        for (int i = 0; i < offsets.Length; i++)
        {
            key.VertexAttributeDescriptions[i] = new VertexInputAttributeDescription
            {
                Binding = 0, Location = (uint)i, Offset = (uint)(offsets[i] * 16),
                Format = Format.R32G32B32A32Sfloat
            };
        }
        key.VertexBindingDescriptions[0] = new VertexInputBindingDescription
        { Binding = 0, Stride = 128, InputRate = VertexInputRate.Vertex };
        key.ColorBlendAttachmentState[0] = new PipelineColorBlendAttachmentState
        { BlendEnable = true, SrcColorBlendFactor = BlendFactor.One, ColorWriteMask = ColorComponentFlags.RBit | ColorComponentFlags.GBit };
        key.AttachmentFormats[0] = Format.R8G8B8A8Unorm;
        return key;
    }

    static bool NextPermutation(int[] values)
    {
        int i = values.Length - 2;
        while (i >= 0 && values[i] >= values[i + 1]) i--;
        if (i < 0) return false;
        int j = values.Length - 1;
        while (values[j] <= values[i]) j--;
        (values[i], values[j]) = (values[j], values[i]);
        Array.Reverse(values, i + 1, values.Length - i - 1);
        return true;
    }

    static void PipelineEquality()
    {
        for (int i = 0; i < 9; i++)
            Check(Marshal.OffsetOf<PipelineUid>("Id" + i).ToInt64() == i * sizeof(ulong), "consecutive identity fields");
        PipelineUid first = Pipeline(new[] { 0, 1, 2, 3, 4, 5, 6, 7 });
        PipelineUid second = first;
        second.VertexAttributeDescriptions[31].Offset = 119;
        second.VertexBindingDescriptions[32].Stride = 991;
        second.ColorBlendAttachmentState[7].ColorWriteMask = ColorComponentFlags.BBit;
        second.AttachmentFormats[8] = Format.R32Sint;
        Check(first.Equals(ref second) && first.GetHashCode() == second.GetHashCode(), "inactive tail bytes ignored by equality and hash");
        HashTableSlim<PipelineUid, int> table = new();
        table.Add(ref first, 100);
        Check(table.TryGetValue(ref second, out int same) && same == 100, "equal inactive-tail lookup");
        List<PipelineUid> variants = new();
        for (int i = 0; i < 9; i++)
        {
            PipelineUid key = first;
            MemoryMarshal.CreateSpan(ref key.Id0, 9)[i] ^= 1;
            variants.Add(key);
        }
        second = first; second.AttachmentIntegerFormatMask = 1; variants.Add(second);
        second = first; second.LogicOpsAllowed = false; variants.Add(second);
        second = first; second.VertexAttributeDescriptions[0].Offset = 23; variants.Add(second);
        second = first; second.VertexAttributeDescriptions[0].Format = Format.R32Sfloat; variants.Add(second);
        second = first; second.VertexAttributeDescriptions[0].Binding = 2; variants.Add(second);
        second = first; second.VertexAttributeDescriptions[0].Location = 19; variants.Add(second);
        second = first; second.VertexBindingDescriptions[0].Stride = 256; variants.Add(second);
        second = first; second.VertexBindingDescriptions[0].Binding = 3; variants.Add(second);
        second = first; second.VertexBindingDescriptions[0].InputRate = VertexInputRate.Instance; variants.Add(second);
        second = first; second.ColorBlendAttachmentState[0].BlendEnable = false; variants.Add(second);
        second = first; second.ColorBlendAttachmentState[0].ColorWriteMask = ColorComponentFlags.ABit; variants.Add(second);
        second = first; second.AttachmentFormats[0] = Format.R32Uint; variants.Add(second);
        second = first; second.Id6 |= 1UL << 63; second.AttachmentFormats[1] = Format.D32Sfloat; variants.Add(second);
        second = first; second.Id5 += 1UL << 38; second.VertexAttributeDescriptions[8].Offset = 55; variants.Add(second);
        for (int i = 0; i < variants.Count; i++)
        {
            PipelineUid key = variants[i];
            Check(!first.Equals(ref key), "active pipeline state remains distinct");
            table.Add(ref key, i);
        }
        for (int i = 0; i < variants.Count; i++)
        {
            PipelineUid key = variants[i];
            Check(table.TryGetValue(ref key, out int value) && value == i, "exact state lookup");
        }
    }

    static (long bytes, int buckets, int largest) Insertions()
    {
        Key.HashCalls = 0;
        HashTableSlim<Key, int> table = new();
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 4096; i++)
        {
            Key key = new() { Id = i, Hash = i * 17 };
            table.Add(ref key, i);
        }
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        for (int i = 0; i < 4096; i++)
        {
            Key key = new() { Id = i, Hash = i * 17 };
            Check(table.TryGetValue(ref key, out int value) && value == i, "all grown entries found");
        }
        Array buckets = (Array)table.GetType().GetField("_hashTable", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(table);
        int largest = 0;
        foreach (object bucket in buckets)
            largest = Math.Max(largest, (int)bucket.GetType().GetField("Length").GetValue(bucket));
        return (allocated, buckets.Length, largest);
    }

    static double MedianLookups(HashTableSlim<PipelineUid, int> table, PipelineUid[] keys)
    {
        // Timers execute uninstrumented production classes after a substantial warmup.
        const int iterations = 8192;
        for (int i = 0; i < iterations; i++) { table.TryGetValue(ref keys[i % keys.Length], out int value); _sink += value; }
        double[] samples = new double[5];
        for (int sample = 0; sample < samples.Length; sample++)
        {
            long start = Stopwatch.GetTimestamp(), total = 0;
            for (int i = 0; i < iterations; i++) { table.TryGetValue(ref keys[i % keys.Length], out int value); total += value; }
            samples[sample] = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
            _sink += total;
        }
        Array.Sort(samples);
        return samples[samples.Length / 2];
    }

    static object[] SmallAndDistributedCaches()
    {
        List<object> result = new();
        foreach (int count in new[] { 1, 4, 16, 64, 512 })
        {
            PipelineUid[] keys = new PipelineUid[count];
            HashTableSlim<PipelineUid, int> table = new();
            for (int i = 0; i < count; i++)
            {
                keys[i] = Pipeline(new[] { 0, 1, 2, 3, 4, 5, 6, 7 });
                keys[i].Id0 = (ulong)i * 0x9e3779b97f4a7c15UL;
                table.Add(ref keys[i], i);
            }
            result.Add(new { count, iterations = 8192,
                medianWarmLookupMilliseconds = MedianLookups(table, keys) });
        }
        return result.ToArray();
    }

    static void Main(string[] args)
    {
        string mode = args[0];
        TableSemantics();
        PipelineEquality();
        bool retained = RemovedValueRetained();
        Check(retained == (mode == "control"), "removed value is not rooted by inactive capacity");
        var insertion = Insertions();
        const int count = 512;
        PipelineUid[] keys = new PipelineUid[count];
        int[] offsets = Enumerable.Range(0, 8).ToArray();
        for (int i = 0; i < count; i++)
        {
            keys[i] = Pipeline(offsets);
            NextPermutation(offsets);
        }
        HashTableSlim<PipelineUid, int> table = new();
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < count; i++) table.Add(ref keys[i], i);
        long pipelineAllocated = GC.GetAllocatedBytesForCurrentThread() - before;
        double milliseconds = MedianLookups(table, keys);
        object[] distributedCaches = SmallAndDistributedCaches();
        HashSet<int> hashes = new();
        HashTableSlim<CountedPipeline, int> counted = new();
        for (int i = 0; i < count; i++)
        {
            CountedPipeline key = new() { Value = keys[i] };
            hashes.Add(key.GetHashCode());
            counted.Add(ref key, i);
        }
        CountedPipeline.Comparisons = 0;
        for (int i = 0; i < count; i++)
        {
            CountedPipeline key = new() { Value = keys[i] };
            Check(counted.TryGetValue(ref key, out int value) && value == i, "collision lookup correctness");
        }
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            result = "passed", mode, checks = _checks, removedValueRetained = retained,
            insertionAllocatedBytes = insertion.bytes, insertionBuckets = insertion.buckets,
            insertionLargestBucket = insertion.largest, insertionAndLookupHashCalls = Key.HashCalls,
            pipelineCount = count, pipelineUidBytes = Unsafe.SizeOf<PipelineUid>(),
            pipelineInsertionAllocatedBytes = pipelineAllocated, pipelineDistinctHashes = hashes.Count,
            pipelineEqualityChecks = CountedPipeline.Comparisons, lookupIterations = 8192,
            medianWarmLookupMilliseconds = milliseconds, physicalDeviceTested = false,
            distributedCaches,
            warmupIterations = 8192, timingSamples = 5, tieredCompilation = false, sink = _sink
        }));
    }
}
