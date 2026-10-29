using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using Ryujinx.Memory.Range;

static class Program
{
    static int Cases, Checks;
    static readonly MemoryStream Bytes = new();
    static readonly BinaryWriter Writer = new(Bytes);
    static long Sink;
    static void Check(bool value, string message) { Checks++; if (!value) throw new Exception(message); }

    static void Record(MultiRange range)
    {
        Writer.Write(range.Count); Writer.Write(range.IsUnmapped);
        for (int i = 0; i < range.Count; i++)
        {
            MemoryRange item = range.GetSubRange(i);
            Writer.Write(item.Address); Writer.Write(item.Size);
        }
    }

    static void Query(MemoryRange[] ranges, ulong offset, ulong size, bool oracle)
    {
        Cases++;
        var input = new MultiRange(ranges);
        Writer.Write(offset); Writer.Write(size);
        try
        {
            MultiRange result = input.Slice(offset, size);
            Writer.Write((byte)1); Record(result);
            Check(result.Equals(result), "A slice remains equal to itself");
            if (oracle)
            {
                // Independent bounded interval-intersection oracle for valid,
                // positive-sized inputs. Holes preserve their sentinel address.
                var expected = new List<MemoryRange>();
                ulong position = 0, end = offset + size;
                foreach (MemoryRange source in ranges)
                {
                    ulong begin = Math.Max(position, offset);
                    ulong finish = Math.Min(position + source.Size, end);
                    if (begin < finish)
                    {
                        ulong address = source.Address == ulong.MaxValue ? ulong.MaxValue : source.Address + begin - position;
                        expected.Add(new MemoryRange(address, finish - begin));
                    }
                    position += source.Size;
                }
                Check(result.Count == expected.Count, "The number of intersected physical ranges matches the independent oracle");
                for (int i = 0; i < expected.Count; i++) Check(result.GetSubRange(i) == expected[i], "Physical bytes and unmapped holes match the independent oracle");
            }
        }
        catch (ArgumentOutOfRangeException error)
        {
            Check(!oracle, "Every valid positive-sized interval must be accepted");
            Writer.Write((byte)2); Writer.Write(error.GetType().FullName); Writer.Write(error.ParamName ?? "");
        }
    }

    static void Edges()
    {
        ulong[] special = { 0, 1, 15, 16, 4095, 4096, 4097, (1UL << 63) - 1, 1UL << 63, (1UL << 63) + 1, ulong.MaxValue - 1, ulong.MaxValue };
        MemoryRange[][] mappings = {
            Array.Empty<MemoryRange>(), new[] { new MemoryRange(0x1000, 0) },
            new[] { new MemoryRange(ulong.MaxValue, 4096) },
            new[] { new MemoryRange(0x1000, 4096) },
            new[] { new MemoryRange(0x1000, 4096), new MemoryRange(ulong.MaxValue, 4096), new MemoryRange(0x8000, 4096) },
            new[] { new MemoryRange(ulong.MaxValue - 16, 32), new MemoryRange(3, 0), new MemoryRange(0x4000, 100) },
            new[] { new MemoryRange(0, ulong.MaxValue), new MemoryRange(ulong.MaxValue, 1), new MemoryRange(2, 32) },
            new[] { new MemoryRange(0x8000, 0), new MemoryRange(0x1000, 0), new MemoryRange(0x4000, 0) },
            new[] { new MemoryRange(5, 1UL << 63), new MemoryRange(9, (1UL << 63) + 2), new MemoryRange(13, 16) },
        };
        foreach (MemoryRange[] ranges in mappings)
            foreach (ulong offset in special)
                foreach (ulong size in special) Query(ranges, offset, size, false);
        var random = new Random(673914);
        for (int iteration = 0; iteration < 12000; iteration++)
        {
            int count = random.Next(0, 65);
            var ranges = new MemoryRange[count];
            for (int i = 0; i < count; i++)
                ranges[i] = new MemoryRange(special[random.Next(special.Length)], special[random.Next(special.Length)]);
            Query(ranges, special[random.Next(special.Length)], special[random.Next(special.Length)], false);
        }
    }

    static void Valid()
    {
        var random = new Random(773015);
        for (int iteration = 0; iteration < 12000; iteration++)
        {
            int count = random.Next(2, 129);
            var ranges = new MemoryRange[count];
            ulong total = 0;
            for (int i = 0; i < count; i++)
            {
                ulong size = (ulong)random.Next(1, 8193);
                ranges[i] = new MemoryRange(i % 7 == 3 ? ulong.MaxValue : (ulong)random.Next(1, 0x1000000), size);
                total += size;
            }
            ulong offset = (ulong)random.NextInt64((long)total);
            ulong length = 1 + (ulong)random.NextInt64((long)(total - offset));
            Query(ranges, offset, length, true);
        }
    }

    static void MutationIsolation()
    {
        foreach (int count in new[] { 2, 4, 17, 512 })
        {
            var ranges = Enumerable.Range(0, count).Select(i => new MemoryRange((ulong)i * 0x2000, 0x1000)).ToArray();
            var original = new MultiRange(ranges);
            MultiRange full = original.Slice(0, original.GetSize());
            MultiRange narrow = original.Slice(1, 12);
            MemoryRange savedFirst = full.GetSubRange(0), savedNarrow = narrow.GetSubRange(0);
            ranges[0] = new MemoryRange(0xcafe, 3);
            Check(full.GetSubRange(0) == savedFirst && narrow.GetSubRange(0) == savedNarrow,
                "A slice never aliases its caller's mutable array, including whole-range slices");
            Cases++;
            Record(full); Record(narrow);
        }
    }

    static object Measure(string name, MultiRange input, ulong offset, ulong size, int iterations)
    {
        void Run(int count)
        {
            for (int i = 0; i < count; i++)
            {
                MultiRange slice = input.Slice(offset, size);
                Sink += slice.Count;
                if (slice.Count != 0) Sink += (long)slice.GetSubRange(0).Address;
            }
        }
        Run(2000);
        double[] timings = new double[5];
        long totalBytes = 0;
        for (int repeat = 0; repeat < timings.Length; repeat++)
        {
            long before = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            Run(iterations);
            timings[repeat] = Stopwatch.GetElapsedTime(start).TotalNanoseconds / iterations;
            totalBytes += GC.GetAllocatedBytesForCurrentThread() - before;
        }
        Array.Sort(timings);
        return new { name, iterations, repeats = timings.Length, allocatedBytes = totalBytes,
            bytesPerSlice = (double)totalBytes / (iterations * timings.Length), medianNanoseconds = timings[2] };
    }

    static void Main()
    {
        Edges(); Valid(); MutationIsolation();
        Writer.Flush();
        string semanticDigest = Convert.ToHexString(SHA256.HashData(Bytes.ToArray()));
        var fragmented = new MultiRange(Enumerable.Range(0, 512).Select(i => new MemoryRange((ulong)i * 0x2000, 0x1000)).ToArray());
        object[] benchmark = {
            Measure("single-input", new MultiRange(0x1000, 0x1000), 16, 32, 100000),
            Measure("fragmented-single-first", fragmented, 16, 32, 100000),
            Measure("fragmented-single-middle", fragmented, 256UL * 0x1000 + 16, 32, 20000),
            Measure("fragmented-single-last", fragmented, 511UL * 0x1000 + 16, 32, 20000),
            Measure("fragmented-two", fragmented, 4080, 32, 50000),
            Measure("fragmented-whole", fragmented, 0, 512UL * 0x1000, 2000),
            Measure("empty-input", new MultiRange(Array.Empty<MemoryRange>()), 0, 0, 100000),
        };
        Console.WriteLine(JsonSerializer.Serialize(new { cases = Cases, checks = Checks, semanticDigest,
            semanticBytes = Bytes.Length, benchmark, sink = Sink, physicalDeviceTested = false }));
    }
}
