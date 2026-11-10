using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Program
{
    static int _assertions;
    static long _digest = 17;
    static bool _sink;
    static void Check(bool condition, string name)
    {
        _assertions++;
        if (!condition) throw new Exception(name);
    }
    static void Main()
    {
        var random = new Random(852196);
        var storages = Enumerable.Range(0, 33).Select(id => new TextureStorage(id)).ToArray();
        var gd = new VulkanRenderer();
        int scenarios = 0;
        for (int length = 0; length <= 9; length++)
        {
            for (int round = 0; round < 40; round++)
            {
                var views = Enumerable.Range(0, length).Select(_ => new TextureView(storages[random.Next(storages.Length)])).ToArray();
                var fb = new FramebufferParams(views);
                var holder = new RenderPassHolder(gd, default, default, fb);
                for (int i = 0; i < storages.Length; i++)
                {
                    bool expected = false;
                    foreach (var view in views) if (view.Storage == storages[i]) { expected = true; break; }
                    bool result = holder.ContainsAttachment(storages[i]);
                    Check(result == expected, "attachment membership");
                    _digest = unchecked(_digest * 31 + (result ? i + 1 : 0));
                }
                Check(!holder.ContainsAttachment(null), "absent null storage");
                if (views.Length > 0)
                {
                    views[0].Storage = null;
                    Check(holder.ContainsAttachment(null), "null storage matches null attachment");
                }
                holder.GetFramebuffer(gd, default, fb);
                holder.GetFramebuffer(gd, default, fb);
                Check(fb.Creates == 1, "framebuffer reuse");
                fb.Width++;
                holder.GetFramebuffer(gd, default, fb);
                Check(fb.Creates == 2, "framebuffer key change");
                var pass = holder.GetRenderPass();
                holder.Dispose();
                Check(pass.Value.Disposed, "render pass disposal");
                foreach (var view in views) Check(view.Adds == 1 && view.Removes == 1, "registration lifecycle");
                scenarios++;
            }
        }
        // The first flags win for duplicate fence registration, including after
        // insertions, and removing disposed resources must not skip survivors.
        for (int round = 0; round < 100; round++)
        {
            var resources = Enumerable.Range(0, 32).Select(id => new TextureStorage(id)).ToArray();
            var holder = new RenderPassHolder(gd, default, default, new FramebufferParams([]));
            var expected = new Dictionary<TextureStorage, PipelineStageFlags>();
            for (int i = 0; i < 256; i++)
            {
                var resource = resources[random.Next(resources.Length)];
                var flags = (PipelineStageFlags)(1u << random.Next(16));
                expected.TryAdd(resource, flags);
                holder.AddForcedFence(resource, flags);
            }
            foreach (var resource in resources) resource.Disposed = random.Next(3) == 0;
            TextureStorage.DispatchOrder.Clear();
            holder.InsertForcedFences(default);
            holder.InsertForcedFences(default);
            var expectedOrder = expected.Keys.Where(resource => !resource.Disposed).Select(resource => resource.Id).ToArray();
            Check(TextureStorage.DispatchOrder.SequenceEqual(expectedOrder.Concat(expectedOrder)), "first registration order");
            foreach (var resource in resources)
            {
                int count = expected.ContainsKey(resource) && !resource.Disposed ? 2 : 0;
                Check(resource.Barriers.Count == count, "duplicate or disposed fence");
                if (count > 0) Check(resource.Barriers.All(flag => flag == expected[resource]), "first stage flags");
                _digest = unchecked(_digest * 31 + resource.Barriers.Count + resource.Id);
            }
            var removed = resources.FirstOrDefault(resource => resource.Disposed && expected.ContainsKey(resource));
            if (removed != null)
            {
                removed.Disposed = false;
                holder.AddForcedFence(removed, PipelineStageFlags.TransferBit);
                holder.InsertForcedFences(default);
                Check(removed.Barriers.Count == 1 && removed.Barriers[0] == PipelineStageFlags.TransferBit, "removed fence can rearm with new flags");
            }
            holder.Dispose();
            scenarios++;
        }
        var probeViews = Enumerable.Range(0, 9).Select(id => new TextureView(storages[id])).ToArray();
        var probe = new RenderPassHolder(gd, default, default, new FramebufferParams(probeViews));
        probe.AddForcedFence(storages[0], PipelineStageFlags.VertexShaderBit);
        var reports = new List<object>();
        reports.Add(Measure("attachment-first", () => _sink = probe.ContainsAttachment(storages[0])));
        reports.Add(Measure("attachment-last", () => _sink = probe.ContainsAttachment(storages[8])));
        reports.Add(Measure("attachment-miss", () => _sink = probe.ContainsAttachment(storages[32])));
        reports.Add(Measure("fence-duplicate", () => probe.AddForcedFence(storages[0], PipelineStageFlags.FragmentShaderBit)));
        probe.Dispose();
        Console.WriteLine(JsonSerializer.Serialize(new { scenarios, assertions = _assertions, digest = _digest, measurements = reports }));
    }
    static object Measure(string name, Action operation)
    {
        const int iterations = 100000;
        for (int i = 0; i < 10000; i++) operation();
        long bytes = GC.GetAllocatedBytesForCurrentThread();
        long start = Stopwatch.GetTimestamp();
        for (int i = 0; i < iterations; i++) operation();
        long elapsed = Stopwatch.GetTimestamp() - start;
        bytes = GC.GetAllocatedBytesForCurrentThread() - bytes;
        return new { name, iterations, allocatedBytes = bytes, nanoseconds = elapsed * 1e9 / Stopwatch.Frequency / iterations };
    }
}
