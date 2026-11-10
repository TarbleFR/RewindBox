using System;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;

static class Program
{
    static int Checks, Cases, MissedInvalidations;
    static void Check(bool condition, string message)
    {
        Checks++;
        if (!condition) throw new InvalidOperationException(message);
    }
    static BufferHandle Handle(ulong value) => Unsafe.As<ulong, BufferHandle>(ref value);
    static void Case(string cause, int indexSize, bool drawCount, int offset)
    {
        var gd = new VulkanRenderer(); var manager = new BufferManager();
        var indices = new BufferHolder(); var indirect = new BufferHolder(); var count = new BufferHolder();
        manager.AddSource(Handle(1), indices); manager.AddSource(Handle(2), indirect); manager.AddSource(Handle(3), count);
        var indexRange = new BufferRange(Handle(1), offset, 48 * indexSize);
        var indirectRange = new BufferRange(Handle(2), offset + 256, 80);
        var countRange = new BufferRange(Handle(3), offset + 1024, 4);
        var pattern = new IndexBufferPattern();
        var first = manager.GetBufferTopologyConversionIndirect(gd, default, indexRange, indirectRange, countRange,
            pattern, indexSize, drawCount, 4, 20);
        Check(first.Item1 != null && first.Item2 != null && manager.Created.Count == 2 && gd.HelperShader.Conversions == 1,
              "first real caller creates both conversions");
        for (int i = 0; i < 8; i++)
        {
            var cached = manager.GetBufferTopologyConversionIndirect(gd, default, indexRange, indirectRange, countRange,
                pattern, indexSize, drawCount, 4, 20);
            Check(ReferenceEquals(cached.Item1, first.Item1) && ReferenceEquals(cached.Item2, first.Item2) &&
                  manager.Created.Count == 2 && gd.HelperShader.Conversions == 1, "cached caller identity stable");
        }
        gd.PipelineInternal.TestBind(first.Item1);
        if (cause == "index") indices.Invalidate(indexRange.Offset, indexRange.Size);
        else if (cause == "indirect") indirect.Invalidate(indirectRange.Offset, indirectRange.Size);
        else count.Invalidate(countRange.Offset, countRange.Size);
        if (!gd.PipelineInternal.NeedsRebind) MissedInvalidations++;
        Check(manager.Created[0].Disposals == 1, "invalidated index conversion released once");
        var next = manager.GetBufferTopologyConversionIndirect(gd, default, indexRange, indirectRange, countRange,
            pattern, indexSize, drawCount, 4, 20);
        Check(next.Item1 != first.Item1 && gd.HelperShader.Conversions == 2, "invalidated conversion recreated");
        Check(cause == "index" ? ReferenceEquals(next.Item2, first.Item2) : next.Item2 != first.Item2,
              "dependency invalidation preserves or replaces indirect buffer appropriately");
        indices.Dispose(); indirect.Dispose(); count.Dispose();
        foreach (var holder in manager.Created) Check(holder.Disposals == 1, "every converted payload released exactly once");
        Cases++;
    }
    static void KeyEquality()
    {
        var gd = new VulkanRenderer(); var pattern = new IndexBufferPattern(); var holder = new BufferHolder();
        var a = new TopologyConversionIndirectCacheKey(gd, pattern, 2, holder, 4, 8);
        var b = new TopologyConversionIndirectCacheKey(gd, pattern, 2, holder, 4, 8);
        a.SetBuffer(new Auto<DisposableBuffer>()); b.SetBuffer(new Auto<DisposableBuffer>());
        Check(a.KeyEqual(b) && b.KeyEqual(a), "buffer assignment does not change structural equality");
        Check(!a.KeyEqual(new TopologyConversionIndirectCacheKey(gd, pattern, 4, holder, 4, 8)), "index size participates");
        Check(!a.KeyEqual(new TopologyConversionIndirectCacheKey(gd, new IndexBufferPattern(), 2, holder, 4, 8)), "pattern identity participates");
        Check(!a.KeyEqual(new TopologyConversionIndirectCacheKey(gd, pattern, 2, new BufferHolder(), 4, 8)), "indirect holder participates");
        Check(!a.KeyEqual(new TopologyConversionIndirectCacheKey(gd, pattern, 2, holder, 5, 8)), "offset participates");
        Check(!a.KeyEqual(new TopologyConversionIndirectCacheKey(gd, pattern, 2, holder, 4, 9)), "size participates");
        Check(!a.KeyEqual(new DrawCountCacheKey()), "other key type not equal");
    }
    static void Main()
    {
        foreach (int indexSize in new[] { 1, 2, 4 })
            foreach (bool count in new[] { false, true })
                foreach (int offset in new[] { 0, 1, 64, 4096, 65536 })
                    foreach (string cause in count ? new[] { "index", "indirect", "count" } : new[] { "index", "indirect" })
                        Case(cause, indexSize, count, offset);
        KeyEquality();
        Console.WriteLine(JsonSerializer.Serialize(new { checks = Checks, lifecycleCases = Cases,
            missedBoundIndexInvalidations = MissedInvalidations, shaderHelperDoubled = true, nativeDriverTested = false }));
    }
}
