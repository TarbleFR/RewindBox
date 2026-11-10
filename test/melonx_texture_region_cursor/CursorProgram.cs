using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.Texture;
#if ADAPTED
using Cursor = Ryujinx.Graphics.Texture.SizeInfo.RegionEnumerator;
#else
using Cursor = System.Collections.Generic.IEnumerator<Ryujinx.Graphics.Texture.Region>;
#endif

static class CursorProgram
{
    static int checks, cases;
    static readonly List<string> Results = new();
    static long Sink;
    static void Require(bool condition, string message) { checks++; if (!condition) throw new Exception(message); }
    static Cursor NewCursor(SizeInfo size)
    {
#if ADAPTED
        return size.GetRegionEnumerator();
#else
        return size.AllRegions().GetEnumerator();
#endif
    }
    static string Step(ref Cursor cursor)
    {
        try { return cursor.MoveNext() ? $"true:{cursor.Current.Offset}:{cursor.Current.Size}" : $"false:{cursor.Current.Offset}:{cursor.Current.Size}"; }
        catch (Exception ex) { return ex.GetType().Name; }
    }
    static string ReferenceStep(IEnumerator<Region> cursor)
    {
        try { return cursor.MoveNext() ? $"true:{cursor.Current.Offset}:{cursor.Current.Size}" : $"false:{cursor.Current.Offset}:{cursor.Current.Size}"; }
        catch (Exception ex) { return ex.GetType().Name; }
    }
    static void Case(string name, SizeInfo size, int disposeAfter = -1, Action<int> mutate = null)
    {
        Cursor actual = NewCursor(size);
        using var reference = size.AllRegions().GetEnumerator();
        try
        {
            Require(actual.Current.Offset == reference.Current.Offset && actual.Current.Size == reference.Current.Size, "initial Current differs");
            var log = new StringBuilder(name);
            for (int i = 0; i < 20000; i++)
            {
                if (i == disposeAfter) { actual.Dispose(); reference.Dispose(); }
                mutate?.Invoke(i);
                string expected = ReferenceStep(reference);
                string found = Step(ref actual);
                Require(found == expected, $"{name} step {i}: {found} != {expected}");
                log.Append('|').Append(found);
                if (!expected.StartsWith("true:"))
                {
                    for (int retry = 0; retry < 3; retry++)
                    {
                        expected = ReferenceStep(reference); found = Step(ref actual);
                        Require(found == expected, name + ": state after finish/failure differs");
                        log.Append('|').Append(found);
                    }
                    Results.Add(log.ToString()); cases++; return;
                }
            }
            throw new Exception("cursor did not terminate: " + name);
        }
        finally { actual.Dispose(); }
    }
    static void Cases()
    {
        var random = new Random(94017);
        for (int i = 0; i < 1000; i++)
        {
            int depth = i % 3 == 0 ? random.Next(2, 33) : 1;
            int layers = depth > 1 ? 1 : random.Next(1, 17);
            int levels = random.Next(1, 7);
            var size = SizeCalculator.GetBlockLinearTextureSize(random.Next(1, 257), random.Next(1, 129), depth,
                levels, layers, 1, 1, 1 << random.Next(0, 4), 1 << random.Next(0, 3),
                depth > 1 ? 1 << random.Next(0, 3) : 1, 1, random.Next(2) == 0 ? 0 : 65536);
            Case("layout:" + i, size);
            if (i % 11 == 0) { Case("dispose-first:" + i, size, 0); Case("dispose-mid:" + i, size, 1); }
        }
        Case("default", default);
        Case("zero-size", new SizeInfo(0));
        Case("negative-size", new SizeInfo(-1));
        foreach (bool volume in new[] { false, true })
        {
            var values = new[] { -1, 0, 16, int.MaxValue, int.MinValue };
            Case("wrapped:" + volume, new SizeInfo(values, values, values, values, 8, values.Length, 0, int.MinValue, volume));
            Case("empty:" + volume, new SizeInfo(Array.Empty<int>(), Array.Empty<int>(), Array.Empty<int>(), Array.Empty<int>(), 0, 0, 0, 0, volume));
            Case("missing-offsets:" + volume, new SizeInfo(null, null, new[] { 4 }, new[] { 4 }, 1, 1, 4, 4, volume));
            Case("missing-sizes:" + volume, new SizeInfo(new[] { 0 }, new[] { 0 }, null, null, 1, 1, 4, 4, volume));
            Case("short-sizes:" + volume, new SizeInfo(new[] { 0, 4, 8 }, new[] { 0, 4, 8 }, new[] { 4 }, new[] { 4 }, 1, 3, 12, 12, volume));
            Case("zero-levels:" + volume, new SizeInfo(new[] { 0 }, new[] { 0 }, new[] { 4 }, new[] { 4 }, 1, 0, 4, 4, volume));
            int[] offsets = { 0, 4, 8, 12 }, lengths = { 4, 4, 4, 4 };
            var mutable = new SizeInfo(offsets, offsets, lengths, lengths, 1, 4, 16, 16, volume);
            Case("array-mutation:" + volume, mutable, mutate: i =>
            {
                if (i < offsets.Length) { offsets[i] += i; lengths[i] -= i; }
            });
        }
    }
    static long AllocationProbe()
    {
        var size = SizeCalculator.GetBlockLinearTextureSize(4, 4, 1, 4, 8, 1, 1, 4, 1, 1, 1, 4096);
        long sum = 0;
        for (int i = 0; i < 2000; i++)
        {
            using var cursor = NewCursor(size);
            while (cursor.MoveNext()) sum += cursor.Current.Size;
        }
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 20000; i++)
        {
            using var cursor = NewCursor(size);
            while (cursor.MoveNext()) sum += cursor.Current.Size;
        }
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        Sink = sum; return allocated;
    }
    static void Main(string[] args)
    {
        Cases();
        Program.Main(args);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            cases, checks, digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n', Results)))),
            iterations = 20000, allocatedBytes = AllocationProbe(), oracleEnumerableUnchanged = true,
        }));
    }
}
