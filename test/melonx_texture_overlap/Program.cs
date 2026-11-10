using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Texture;
using Ryujinx.Memory.Range;
using GpuTexture = Ryujinx.Graphics.Gpu.Image.Texture;

namespace Ryujinx.Graphics.Gpu.Memory
{
    sealed class PhysicalMemory { }

    static class MemoryManager
    {
        public const ulong PteUnmapped = ulong.MaxValue;
    }
}

namespace Ryujinx.Graphics.Gpu
{
    sealed class GpuContext { }
}

namespace Ryujinx.Graphics.Gpu.Image
{
    readonly record struct TextureInfo(int GobBlocksInZ);

    partial class Texture
    {
        private SizeInfo _sizeInfo;
        private GpuContext _context;
        private Memory.PhysicalMemory _physicalMemory;
        private Texture _viewStorage;
        private List<Texture> _views;
        private List<object> _poolOwners;
        public SizeInfo SizeInfo => _sizeInfo;
        public TextureInfo Info { get; private set; }
        public MultiRange Range { get; set; }

        private void SetInfo(TextureInfo info) => Info = info;

        public Texture(SizeInfo sizeInfo, MultiRange range, int gobBlocksInZ = 1)
        {
            InitializeTexture(null, null, new TextureInfo(gobBlocksInZ), sizeInfo, range);
        }

        public void Reinitialize(SizeInfo sizeInfo, MultiRange range)
            => InitializeTexture(null, null, new TextureInfo(1), sizeInfo, range);
    }
}

static class Program
{
    private static int _checks;
    private static ulong _resultDigest = 14695981039346656037UL;
    private static readonly Dictionary<string, int> _covered = new();
    private static volatile bool _sink;

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new Exception(message);
        }
    }

    private static SizeInfo PaddedArray(int layers, int levels = 4)
    {
        return SizeCalculator.GetBlockLinearTextureSize(
            4, 4, 1, levels, layers, 1, 1, 4, 1, 1, 1, 4096);
    }

    private static GpuTexture Contiguous(SizeInfo size, ulong address, int gobZ = 1)
    {
        return new GpuTexture(size, new MultiRange(address, (ulong)size.TotalSize), gobZ);
    }

    // Oracle deliberately materializes the actual production layout/mapping
    // result, then considers every pair. It has no ordering assumption.
    private static bool Oracle(GpuTexture left, GpuTexture right, TextureViewCompatibility compatibility)
    {
        if (compatibility == TextureViewCompatibility.LayoutIncompatible &&
            left.Info.GobBlocksInZ > 1 && left.Info.GobBlocksInZ == right.Info.GobBlocksInZ)
        {
            return false;
        }

        if (left.SizeInfo.AllOffsets.Length == 1 && right.SizeInfo.AllOffsets.Length == 1)
        {
            return left.Range.OverlapsWith(right.Range);
        }

        MultiRange[] leftRegions = left.SizeInfo.AllRegions()
            .Select(region => left.Range.Slice((ulong)region.Offset, (ulong)region.Size)).ToArray();
        MultiRange[] rightRegions = right.SizeInfo.AllRegions()
            .Select(region => right.Range.Slice((ulong)region.Offset, (ulong)region.Size)).ToArray();

        return leftRegions.Any(leftRegion => rightRegions.Any(leftRegion.OverlapsWith));
    }

    private static void Check(GpuTexture left, GpuTexture right, string category,
        TextureViewCompatibility compatibility = TextureViewCompatibility.Incompatible, bool? expected = null)
    {
        bool oracle = Oracle(left, right, compatibility);
        if (expected.HasValue)
        {
            Require(oracle == expected.Value, "Invalid fixture: " + category);
        }

        bool actual = left.DataOverlaps(right, compatibility);
        bool reversed = right.DataOverlaps(left, compatibility);
        Require(actual == oracle && reversed == oracle, "Overlap mismatch: " + category);
        _checks += 2;
        _resultDigest = unchecked((_resultDigest ^ (actual ? 1UL : 0UL)) * 1099511628211UL);
        _covered.TryGetValue(category, out int count);
        _covered[category] = count + 1;
    }

    private static MultiRange Fragmented(SizeInfo size, ulong address, int kind, Random random)
    {
        int count = random.Next(2, 7);
        ulong totalSize = (ulong)size.TotalSize;
        ulong baseSize = totalSize / (ulong)count;
        MemoryRange[] ranges = new MemoryRange[count];

        for (int i = 0; i < count; i++)
        {
            ulong length = i == count - 1 ? totalSize - baseSize * (ulong)i : baseSize;
            ulong start = kind switch
            {
                1 => address + (ulong)i * (baseSize + 512),
                2 => address + (ulong)(count - i - 1) * (baseSize + 512),
                3 => i % 2 == 0 ? ulong.MaxValue : address + (ulong)i * baseSize,
                4 => address,
                _ => throw new ArgumentException(nameof(kind)),
            };
            ranges[i] = new MemoryRange(start, length);
        }

        return new MultiRange(ranges);
    }

    private static void CheckInvalidSlice(GpuTexture left, GpuTexture right, string category = "short-mapping-slice-exception")
    {
        for (int i = 0; i < 2; i++)
        {
            bool threw = false;
            try
            {
                left.DataOverlaps(right, TextureViewCompatibility.Incompatible);
            }
            catch (ArgumentOutOfRangeException)
            {
                threw = true;
            }

            Require(threw, "A short mapping must retain the original Slice exception");
            _checks++;
            _resultDigest = unchecked((_resultDigest ^ 2UL) * 1099511628211UL);
            (left, right) = (right, left);
        }

        _covered[category] = 1;
    }

    private static SizeInfo RandomSize(Random random, out int gobZ)
    {
        int depth = random.Next(5) == 0 ? random.Next(2, 17) : 1;
        int levels = random.Next(1, 7);
        int layers = depth > 1 ? 1 : random.Next(1, 17);
        int width = random.Next(1, 129);
        int height = random.Next(1, 65);
        gobZ = depth > 1 ? 1 << random.Next(0, 3) : 1;
        return SizeCalculator.GetBlockLinearTextureSize(width, height, depth, levels, layers,
            1, 1, 1 << random.Next(0, 4), 1 << random.Next(0, 3), gobZ, 1,
            random.Next(2) == 0 ? 0 : 65536);
    }

    private static void Correctness()
    {
        SizeInfo padded = PaddedArray(64);
        GpuTexture first = Contiguous(padded, 0x100000);
        GpuTexture shifted = Contiguous(padded, 0x100800);
        Require(padded.AllRegions().Count() == 256, "Expected 256 real regions");
        Require(first.Range.OverlapsWith(shifted.Range), "Allocations overlap despite disjoint data");
        Check(first, shifted, "padded-disjoint-data", expected: false);
        Check(first, first, "first-region-match", expected: true);
        Check(first, Contiguous(padded, 0x100000 + 63 * 4096), "last-layer-match", expected: true);
        Check(first, Contiguous(padded, 0x100000 + 63 * 4096 + 2048), "touching-last-end", expected: false);
        Check(first, Contiguous(padded, 0x100000 + 63 * 4096 + 2047), "one-byte-overlap", expected: true);
        Check(first, Contiguous(padded, 0x1000000), "separate-allocations", expected: false);

        SizeInfo linear = SizeCalculator.GetLinearTextureSize(64, 7, 1);
        Check(Contiguous(linear, 0x100000), first, "linear-vs-array", expected: true);
        Check(Contiguous(linear, 0x100800), first, "linear-in-padding", expected: false);
        Check(Contiguous(linear, 0x100000), Contiguous(linear, 0x1001C0), "single-touching", expected: false);
        Check(Contiguous(new SizeInfo(0), 0x100001), first, "zero-sized-existing-semantics", expected: true);
        Check(Contiguous(padded, ulong.MaxValue - (ulong)padded.TotalSize),
            Contiguous(padded, ulong.MaxValue - (ulong)padded.TotalSize - 2048), "high-valid-address");
        Check(Contiguous(padded, ulong.MaxValue - 2048), first, "overflowing-address-fallback");
        Check(Contiguous(padded, ulong.MaxValue), Contiguous(padded, 2047), "unmapped-fallback");

        // Slice's ulong subtraction permits an offset beyond a short mapping.
        // That can wrap later layer addresses despite a non-wrapping mapping,
        // so the ordered path must check TotalSize <= mapping.Size first.
        GpuTexture shortHigh = new(padded, new MultiRange(ulong.MaxValue - 4095, 2048));
        Check(shortHigh, Contiguous(new SizeInfo(512), 0), "short-mapping-wrapped-region", expected: true);
        GpuTexture shortNormal = new(padded, new MultiRange(0x100000, 2048));
        Check(shortNormal, Contiguous(new SizeInfo(512), 0x100000), "short-mapping-first-match", expected: true);
        CheckInvalidSlice(new GpuTexture(padded, new MultiRange(0x100000, 511)), first);

        // Five 1 GiB layers wrap the int total back to +1 GiB while intermediate
        // AllRegions offsets are negative. Preserve the original Slice failure.
        SizeInfo overflow = SizeCalculator.GetBlockLinearTextureSize(
            16384, 4096, 1, 1, 5, 1, 1, 16, 1, 1, 1);
        Require(overflow.TotalSize == 1 << 30 && overflow.AllOffsets[2] < 0, "Actual SizeCalculator overflow fixture");
        GpuTexture reused = Contiguous(padded, 0x100000);
        Check(reused, shifted, "layout-validation-initial", expected: false);
        FieldInfo orderField = typeof(GpuTexture).GetField("_dataRegionOrder", BindingFlags.NonPublic | BindingFlags.Instance);
        if (orderField != null) Require((byte)orderField.GetValue(reused) == 1, "Valid layout proof is memoized");

        // Later malformed slices must not matter when the original traversal
        // already returns true on the first pair. No validation scan is needed.
        GpuTexture invalidFirstMatch = Contiguous(overflow, 0x100000);
        GpuTexture firstSlice = Contiguous(new SizeInfo(512), 0x100000);
        Require(invalidFirstMatch.DataOverlaps(firstSlice, TextureViewCompatibility.Incompatible), "Malformed layout first pair still matches");
        Require(firstSlice.DataOverlaps(invalidFirstMatch, TextureViewCompatibility.Incompatible), "Malformed layout first pair matches symmetrically");
        if (orderField != null) Require((byte)orderField.GetValue(invalidFirstMatch) == 0, "Immediate match skips layout validation");
        _checks += 2;
        _resultDigest = unchecked((_resultDigest ^ 1UL) * 1099511628211UL);
        _covered["invalid-layout-first-pair-match"] = 1;

        reused.Range = shortHigh.Range;
        Check(reused, Contiguous(new SizeInfo(512), 0), "validated-layout-remapped-short", expected: true);
        reused.Reinitialize(overflow, new MultiRange(0x100000000, (ulong)overflow.TotalSize));
        if (orderField != null) Require((byte)orderField.GetValue(reused) == 0, "Production initialization resets layout proof");
        CheckInvalidSlice(reused, Contiguous(new SizeInfo(512), 0), "overflow-layout-original-exception");
        if (orderField != null) Require((byte)orderField.GetValue(reused) == 2, "Invalid layout uses the original path");
        reused.Reinitialize(padded, first.Range);
        if (orderField != null) Require((byte)orderField.GetValue(reused) == 0, "Reinitialization resets a negative proof");
        Check(reused, shifted, "layout-validation-reinitialized", expected: false);
        if (orderField != null) Require((byte)orderField.GetValue(reused) == 1, "Replacement layout is checked afresh");

        for (int depth = 1; depth <= 17; depth += 2)
        {
            for (int gobZ = 1; gobZ <= 8; gobZ *= 2)
            {
                for (int levels = 1; levels <= 6; levels++)
                {
                    SizeInfo size = SizeCalculator.GetBlockLinearTextureSize(
                        17, 29, depth, levels, 1, 1, 1, 4, 4, gobZ, 1);
                    GpuTexture volume = Contiguous(size, 0x100000, gobZ);
                    Check(volume, Contiguous(size, 0x100000, gobZ), "3d-identical",
                        TextureViewCompatibility.Full, true);
                    Check(volume, Contiguous(size, 0x100000, gobZ), "3d-layout-exception",
                        TextureViewCompatibility.LayoutIncompatible, gobZ == 1);
                    Check(volume, Contiguous(size, 0x100000 + (ulong)size.TotalSize - 1, gobZ),
                        "3d-last-byte");
                    Check(volume, Contiguous(size, 0x100000 + (ulong)size.TotalSize, gobZ),
                        "3d-touching");
                }
            }
        }

        Random random = new(0x29A0B);
        string[] mappingKinds = { "contiguous", "fragmented", "reversed", "holes", "alias" };
        for (int i = 0; i < 2500; i++)
        {
            SizeInfo leftSize = RandomSize(random, out int leftZ);
            SizeInfo rightSize = i % 3 == 0 ? leftSize : RandomSize(random, out _);
            int leftKind = i % 5;
            int rightKind = (i / 5) % 5;
            ulong leftAddress = (ulong)random.Next(0, 64) * 512;
            ulong rightAddress = (ulong)random.Next(0, 128) * 512;
            MultiRange leftRange = leftKind == 0 ? new MultiRange(leftAddress, (ulong)leftSize.TotalSize)
                : Fragmented(leftSize, leftAddress, leftKind, random);
            MultiRange rightRange = rightKind == 0 ? new MultiRange(rightAddress, (ulong)rightSize.TotalSize)
                : Fragmented(rightSize, rightAddress, rightKind, random);
            GpuTexture left = new(leftSize, leftRange, leftZ);
            GpuTexture right = new(rightSize, rightRange, i % 3 == 0 ? leftZ : 1);
            Check(left, right, mappingKinds[leftKind] + "-" + mappingKinds[rightKind]);
            Check(left, right, "random-layout-compatibility", TextureViewCompatibility.LayoutIncompatible);

            // Reuse the same object after remapping, including a switch between
            // contiguous and fragmented physical ranges. No stale range result.
            if (i % 25 == 0)
            {
                left.Range = new MultiRange(rightAddress, (ulong)leftSize.TotalSize);
                Check(left, right, "remapped-contiguous");
                left.Range = Fragmented(leftSize, rightAddress, 2, random);
                Check(left, right, "remapped-fragmented");
            }
        }
    }

    private static object Benchmark(string name, GpuTexture left, GpuTexture right)
    {
        const TextureViewCompatibility compatibility = TextureViewCompatibility.Incompatible;
        bool expected = Oracle(left, right, compatibility);
        for (int i = 0; i < 32; i++)
        {
            _sink = left.DataOverlaps(right, compatibility);
        }

        long calibrationStart = Stopwatch.GetTimestamp();
        for (int i = 0; i < 16; i++)
        {
            _sink = left.DataOverlaps(right, compatibility);
        }
        double calibrationSeconds = (Stopwatch.GetTimestamp() - calibrationStart) / (double)Stopwatch.Frequency;
        int iterations = (int)Math.Clamp(Math.Ceiling(16 * 0.05 / Math.Max(calibrationSeconds, 0.000001)), 64, 100000);
        double[] wallNs = new double[5];
        double[] cpuNs = new double[5];
        double[] bytes = new double[5];
        using Process process = Process.GetCurrentProcess();

        for (int batch = 0; batch < wallNs.Length; batch++)
        {
            TimeSpan cpuBefore = process.TotalProcessorTime;
            long allocatedBefore = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            for (int i = 0; i < iterations; i++)
            {
                _sink = left.DataOverlaps(right, compatibility);
            }
            long end = Stopwatch.GetTimestamp();
            long allocatedAfter = GC.GetAllocatedBytesForCurrentThread();
            TimeSpan cpuAfter = process.TotalProcessorTime;
            wallNs[batch] = (end - start) * 1e9 / Stopwatch.Frequency / iterations;
            cpuNs[batch] = (cpuAfter - cpuBefore).TotalMilliseconds * 1e6 / iterations;
            bytes[batch] = (allocatedAfter - allocatedBefore) / (double)iterations;
            Require(_sink == expected, "Benchmark result changed: " + name);
        }

        Array.Sort(wallNs);
        Array.Sort(cpuNs);
        Array.Sort(bytes);
        return new
        {
            name,
            result = expected,
            regionsPerTexture = left.SizeInfo.AllRegions().Count(),
            iterationsPerBatch = iterations,
            batches = wallNs.Length,
            medianNanosecondsPerCall = wallNs[2],
            medianProcessCpuNanosecondsPerCall = cpuNs[2],
            bytesPerCall = bytes[2],
        };
    }

    private static object FirstComparisons(string name, SizeInfo size, ulong otherAddress, int pairs)
    {
        bool expected = Oracle(Contiguous(size, 0x100000), Contiguous(size, otherAddress),
            TextureViewCompatibility.Incompatible);
        double[] wallNs = new double[5];
        double[] bytes = new double[5];

        for (int batch = 0; batch < wallNs.Length; batch++)
        {
            // Construct before the timer. Each pair is used exactly once, so
            // layout validation is cold while the JIT and utilities are warm.
            GpuTexture[] left = new GpuTexture[pairs];
            GpuTexture[] right = new GpuTexture[pairs];
            for (int i = 0; i < pairs; i++)
            {
                left[i] = Contiguous(size, 0x100000);
                right[i] = Contiguous(size, otherAddress);
            }

            long before = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            for (int i = 0; i < pairs; i++)
            {
                _sink = left[i].DataOverlaps(right[i], TextureViewCompatibility.Incompatible);
            }
            long end = Stopwatch.GetTimestamp();
            long after = GC.GetAllocatedBytesForCurrentThread();
            Require(_sink == expected, "First-comparison benchmark result changed");
            wallNs[batch] = (end - start) * 1e9 / Stopwatch.Frequency / pairs;
            bytes[batch] = (after - before) / (double)pairs;
        }

        Array.Sort(wallNs);
        Array.Sort(bytes);
        return new
        {
            name,
            result = expected,
            regionsPerTexture = size.AllRegions().Count(),
            freshPairsPerBatch = pairs,
            batches = wallNs.Length,
            medianNanosecondsPerFirstComparison = wallNs[2],
            bytesPerFirstComparison = bytes[2],
            constructionIncluded = false,
        };
    }

    public static void Main(string[] arguments)
    {
        Correctness();
        SizeInfo small = PaddedArray(8);
        SizeInfo large = PaddedArray(64);
        GpuTexture first = Contiguous(large, 0x100000);
        Random random = new(17);
        GpuTexture fragmented = new(large, Fragmented(large, 0x100000, 2, random));
        object[] benchmarks =
        {
            Benchmark("padded-32-regions", Contiguous(small, 0x100000), Contiguous(small, 0x100800)),
            Benchmark("padded-256-regions", first, Contiguous(large, 0x100800)),
            Benchmark("last-layer-match", first, Contiguous(large, 0x100000 + 63 * 4096)),
            Benchmark("first-region-match", first, first),
            Benchmark("fragmented-first-match", fragmented, fragmented),
            Benchmark("single-subresource", Contiguous(new SizeInfo(512), 0), Contiguous(new SizeInfo(512), 1)),
        };
        object[] firstComparisons =
        {
            FirstComparisons("first-match-256-regions", large, 0x100000, 4096),
            FirstComparisons("padded-256-regions", large, 0x100800, 64),
        };
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            mode = arguments[0],
            checks = _checks,
            resultDigest = _resultDigest.ToString("x16"),
            covered = _covered,
            benchmarks,
            firstComparisons,
        }));
    }
}
