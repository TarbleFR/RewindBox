using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Memory.Range;
using System;
using System.Collections.Generic;
using System.Text.Json;

static class Program
{
    static int _checks;
    static void Check(bool value, string message) { _checks++; if (!value) throw new Exception(message); }
    static void Main(string[] args)
    {
        bool fixedMode = args[0] == "fixed";
        var cpu = new FakeCpuMemory();
        for (int i = 0; i < cpu.Bytes.Length; i++) cpu.Bytes[i] = (byte)(i * 17 + 3);
        var physical = new PhysicalMemory(cpu);
        var range = new MultiRange(new[] { new MemoryRange(0, 524288), new MemoryRange(1048576, 524288) });
        byte[] expected = physical.GetSpan(range).ToArray();
        using (var region = physical.GetReadOnlyRegion(range, true))
            Check(region.Span.SequenceEqual(expected), "fragmented bytes preserved");
        Check(cpu.TrackedReads == 2, "tracking preserved for each fragment");
        using (var region = physical.GetReadOnlyRegion(new MultiRange(0, 32)))
        {
            cpu.Bytes[1] = 201;
            Check(region.Span[1] == 201, "contiguous path remains borrowed");
        }
        var holes = new MultiRange(new[] { new MemoryRange(0, 32), new MemoryRange(ulong.MaxValue, 128), new MemoryRange(2048, 32) });
        var dirty = new MultiRange(new[] { new MemoryRange(0, 96), new MemoryRange(2048, 96) });
        using (var region = physical.GetReadOnlyRegion(dirty))
            Check(region.Span.Slice(32, 128).IndexOfAnyExcept((byte)0) >= 0, "reused snapshot starts with nonzero bytes");
        using (var region = physical.GetReadOnlyRegion(holes))
            Check(region.Span.Slice(32, 128).IndexOfAnyExcept((byte)0) == -1, "unmapped holes stay zero after pool reuse");
        cpu.ShortAddress = 0;
        foreach (int count in new[] { 16, 0 })
        {
            cpu.ShortLength = count;
            using var region = physical.GetReadOnlyRegion(dirty);
            Check(region.Span.SequenceEqual(physical.GetSpan(dirty)), "handled short guest read preserves zero tail");
        }
        cpu.ShortAddress = ulong.MaxValue;

        // The production full-sync method releases its snapshot on changed, unchanged and failing uploads.
        var texture = new TestImage.Texture(physical, range);
        texture.SynchronizeFull();
        texture.SynchronizeFull();
        Check(texture.Conversions == 1, "unchanged full texture skips conversion");
        texture.FailConversion = true;
        cpu.Bytes[0]++;
        bool threw = false;
        try { texture.SynchronizeFull(); } catch (InvalidOperationException) { threw = true; }
        Check(threw && Tracking.Active.Count == 0, "failed full conversion returns the snapshot");
        texture.FailConversion = false;

        var partialRange = new MultiRange(new[] { new MemoryRange(0, 524288), new MemoryRange(1048576, 524288),
            new MemoryRange(2097152, 524288), new MemoryRange(3145728, 524288) });
        var storage = new TestImage.Storage(partialRange);
        var group = new TestImage.TextureGroup(physical, storage);
        group.Run();
        Check(storage.Uploads == 2 && Tracking.Active.Count == 0, "partial snapshots released between slices");
        storage.FailConversion = true;
        threw = false;
        try { group.Run(); } catch (InvalidOperationException) { threw = true; }
        Check(threw && Tracking.Active.Count == 0, "failed partial conversion returns its snapshot");

        cpu.FailAddress = 1048576;
        threw = false;
        try { using var region = physical.GetReadOnlyRegion(range); } catch (InvalidOperationException) { threw = true; }
        Check(threw && Tracking.Active.Count == 0, "fragment read failure returns rented storage");
        cpu.FailAddress = ulong.MaxValue;

        // Measure the actual two production upload consumers with native conversion/upload doubled out.
        storage.FailConversion = false;
        for (int i = 0; i < 5; i++) { cpu.Bytes[0]++; texture.SynchronizeFull(); group.Run(); }
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 64; i++) { cpu.Bytes[0]++; texture.SynchronizeFull(); group.Run(); }
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        Check(fixedMode ? allocated < 65536 : allocated >= 192L * 1048576,
            $"fragmented upload allocation budget: {allocated}");
        Check(Tracking.Active.Count == 0 && Tracking.Rents == Tracking.Returns, "all scoped snapshots returned exactly once");
        Console.WriteLine(JsonSerializer.Serialize(new { mode = args[0], passed = true, checks = _checks,
            fragmentedUploads = 192, allocatedBytes = allocated, rents = Tracking.Rents, returns = Tracking.Returns,
            physicalDeviceTested = false }));
    }
}

sealed class FakeCpuMemory
{
    public readonly byte[] Bytes = new byte[4 * 1024 * 1024];
    public int TrackedReads;
    public ulong FailAddress = ulong.MaxValue;
    public ulong ShortAddress = ulong.MaxValue;
    public int ShortLength;
    public ReadOnlySpan<byte> GetSpan(ulong address, int size, bool tracked = false)
    {
        if (address == FailAddress) throw new InvalidOperationException("guest read failure");
        if (tracked) TrackedReads++;
        if (address == ShortAddress) size = Math.Min(size, ShortLength);
        return Bytes.AsSpan((int)address, size);
    }
}

static class Tracking
{
    public static readonly HashSet<Ryujinx.Common.Memory.MemoryOwner<byte>> Active = new();
    public static int Rents, Returns;
    public static Ryujinx.Common.Memory.MemoryOwner<byte> Rent(int size)
    {
        var owner = Ryujinx.Common.Memory.MemoryOwner<byte>.Rent(size);
        if (!Active.Add(owner)) throw new Exception("duplicate lease");
        Rents++;
        return owner;
    }
    public static void Dispose(Ryujinx.Common.Memory.MemoryOwner<byte>? owner)
    {
        if (owner == null) return;
        if (!Active.Remove(owner)) throw new Exception("duplicate release");
        owner.Dispose(); Returns++;
    }
}
