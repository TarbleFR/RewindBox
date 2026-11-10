using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Control = Ryujinx.Graphics.Vulkan.Control.BarrierBatch;

interface IBatch : IDisposable
{
    void Memory(MemoryBarrier barrier, PipelineStageFlags source, PipelineStageFlags dest);
    void Buffer(BufferMemoryBarrier barrier, PipelineStageFlags source, PipelineStageFlags dest);
    void Image(ImageMemoryBarrier barrier, TextureStorage resource, PipelineStageFlags source, PipelineStageFlags dest);
    void Incoherent(int kind);
    void Tfb(bool enable);
    void Flush(ShaderCollection program, bool feedback, bool renderPass, RenderPassHolder holder, Action end);
}

sealed class OldBatch : IBatch
{
    readonly Control _batch;
    public OldBatch(VulkanRenderer gd) => _batch = new(gd);
    public void Memory(MemoryBarrier b, PipelineStageFlags s, PipelineStageFlags d) => _batch.QueueBarrier(b, s, d);
    public void Buffer(BufferMemoryBarrier b, PipelineStageFlags s, PipelineStageFlags d) => _batch.QueueBarrier(b, s, d);
    public void Image(ImageMemoryBarrier b, TextureStorage r, PipelineStageFlags s, PipelineStageFlags d) => _batch.QueueBarrier(b, r, s, d);
    public void Incoherent(int k) { if (k == 0) _batch.QueueTextureBarrier(); else if (k == 1) _batch.QueueMemoryBarrier(); else _batch.QueueCommandBufferBarrier(); }
    public void Tfb(bool e) => _batch.EnableTfbBarriers(e);
    public void Flush(ShaderCollection p, bool f, bool r, RenderPassHolder h, Action end) => _batch.Flush(default, p, f, r, h, end);
    public void Dispose() => _batch.Dispose();
}
sealed class NewBatch : IBatch
{
    readonly BarrierBatch _batch;
    public NewBatch(VulkanRenderer gd) => _batch = new(gd);
    public void Memory(MemoryBarrier b, PipelineStageFlags s, PipelineStageFlags d) => _batch.QueueBarrier(b, s, d);
    public void Buffer(BufferMemoryBarrier b, PipelineStageFlags s, PipelineStageFlags d) => _batch.QueueBarrier(b, s, d);
    public void Image(ImageMemoryBarrier b, TextureStorage r, PipelineStageFlags s, PipelineStageFlags d) => _batch.QueueBarrier(b, r, s, d);
    public void Incoherent(int k) { if (k == 0) _batch.QueueTextureBarrier(); else if (k == 1) _batch.QueueMemoryBarrier(); else _batch.QueueCommandBufferBarrier(); }
    public void Tfb(bool e) => _batch.EnableTfbBarriers(e);
    public void Flush(ShaderCollection p, bool f, bool r, RenderPassHolder h, Action end) => _batch.Flush(default, p, f, r, h, end);
    public void Dispose() => _batch.Dispose();
}

static class Program
{
    static int _checks, _scenarios;
    static void Check(bool condition, string message) { _checks++; if (!condition) throw new Exception(message); }
    static readonly PipelineStageFlags[] Stages = {
        PipelineStageFlags.VertexShaderBit, PipelineStageFlags.FragmentShaderBit,
        PipelineStageFlags.ComputeShaderBit, PipelineStageFlags.TransferBit,
        PipelineStageFlags.AllGraphicsBit, PipelineStageFlags.DrawIndirectBit,
        PipelineStageFlags.TransformFeedbackBitExt
    };
    static IBatch Batch(bool updated, VulkanRenderer gd) => updated ? new NewBatch(gd) : new OldBatch(gd);

    static void Queue(IBatch batch, int kind, uint id, TextureStorage resource, PipelineStageFlags source, PipelineStageFlags dest)
    {
        AccessFlags access = (id & 1) == 0 ? AccessFlags.ShaderReadBit : AccessFlags.ShaderWriteBit;
        if (kind == 0) batch.Memory(new MemoryBarrier { SType = StructureType.MemoryBarrier, SrcAccessMask = access, DstAccessMask = (AccessFlags)id }, source, dest);
        else if (kind == 1) batch.Buffer(new BufferMemoryBarrier { SType = StructureType.BufferMemoryBarrier,
            SrcAccessMask = access, DstAccessMask = (AccessFlags)id, Buffer = new Silk.NET.Vulkan.Buffer(id + 31), Offset = id * 3,
            Size = id + 5, SrcQueueFamilyIndex = 0xffffffff, DstQueueFamilyIndex = id % 8 }, source, dest);
        else batch.Image(new ImageMemoryBarrier { SType = StructureType.ImageMemoryBarrier,
            SrcAccessMask = access, DstAccessMask = (AccessFlags)id, Image = new Image(id + 79),
            OldLayout = ImageLayout.General, NewLayout = ImageLayout.TransferSrcOptimal,
            SrcQueueFamilyIndex = id % 4, DstQueueFamilyIndex = 0xffffffff,
            SubresourceRange = new ImageSubresourceRange(ImageAspectFlags.ColorBit, id % 9, id % 7 + 1, id % 17, id % 11 + 1) }, resource, source, dest);
    }

    static List<string> Trace(bool updated, int seed, int count, int mode)
    {
        Random random = new(seed);
        VulkanRenderer gd = new() { IsTBDR = (mode & 1) != 0, IsMoltenVk = (mode & 2) != 0,
            TransformFeedbackApi = (mode & 4) != 0 ? new object() : null };
        gd.Api.Capture = true;
        using IBatch batch = Batch(updated, gd);
        TextureStorage[] resources = Enumerable.Range(0, 64).Select(x => new TextureStorage(x)).ToArray();
        RenderPassHolder holder = new(gd.Api);
        ShaderCollection shader = new() { IncoherentBufferWriteStages = Stages[seed % Stages.Length],
            IncoherentTextureWriteStages = Stages[(seed + 1) % Stages.Length] };
        Action end = () => gd.Api.Trace.Add("end");
        for (int frame = 0; frame < 3; frame++)
        {
            for (uint i = 0; i < count; i++)
                Queue(batch, random.Next(3), i + (uint)frame * 65536, resources[random.Next(resources.Length)],
                    Stages[random.Next(Stages.Length)], Stages[random.Next(Stages.Length)]);
            if (mode >= 8) { batch.Tfb((frame & 1) == 0); batch.Incoherent(frame); }
            batch.Flush(mode >= 8 ? shader : null, (mode & 4) != 0, (mode & 8) != 0, holder, end);
            batch.Flush(null, false, false, null, end); // Completely drained, no extra API call.
        }
        return gd.Api.Trace;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference EnqueueResource(IBatch batch)
    {
        TextureStorage resource = new(9271);
        Queue(batch, 2, 1, resource, Stages[0], Stages[1]);
        return new WeakReference(resource);
    }

    static void Retention(bool updated)
    {
        VulkanRenderer gd = new();
        using IBatch batch = Batch(updated, gd);
        WeakReference reference = EnqueueResource(batch);
        batch.Flush(null, false, false, null, static () => throw new Exception("unexpected pass end"));
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        Check(!reference.IsAlive, "drained image list retains texture storage");
        GC.KeepAlive(batch);
    }

    static (double Nanoseconds, long AllocatedBytes, long Calls) Timed(bool updated, int count, int pattern, int iterations)
    {
        VulkanRenderer gd = new();
        using IBatch batch = Batch(updated, gd);
        Action end = static () => throw new Exception("unexpected pass end");
        void Fill()
        {
            for (uint i = 0; i < count; i++)
            {
                int stage = pattern == 0 ? 0 : pattern == 1 ? (int)(i & 1) : (int)(i % 7);
                Queue(batch, 0, i, null, Stages[stage], Stages[(stage + 1) % Stages.Length]);
            }
        }
        for (int i = 0; i < 4; i++) { Fill(); batch.Flush(null, false, false, null, end); }
        long ticks = 0, bytes = 0;
        long calls = gd.Api.Calls;
        for (int i = 0; i < iterations; i++)
        {
            Fill();
            long allocated = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            batch.Flush(null, false, false, null, end);
            ticks += Stopwatch.GetTimestamp() - start;
            bytes += GC.GetAllocatedBytesForCurrentThread() - allocated;
        }
        return ((double)ticks * 1e9 / Stopwatch.Frequency / iterations, bytes, gd.Api.Calls - calls);
    }

    static void Main()
    {
        int[] counts = { 0, 1, 15, 16, 17, 31, 32, 33, 63, 64, 127, 257, 1024 };
        foreach (int count in counts)
        for (int mode = 0; mode < 16; mode++)
        for (int seed = 1; seed <= 3; seed++)
        {
            List<string> control = Trace(false, seed, count, mode);
            List<string> candidate = Trace(true, seed, count, mode);
            Check(control.SequenceEqual(candidate), $"native barrier trace differs count={count} mode={mode} seed={seed}");
            _scenarios++;
        }
        Retention(false); Retention(true);
        List<object> timings = new();
        foreach (int count in new[] { 1, 16, 128, 1024, 4096 })
        for (int pattern = 0; pattern < 3; pattern++)
        {
            int iterations = Math.Max(8, Math.Min(10000, 200000 / count));
            List<double> oldTimes = new(), newTimes = new();
            for (int round = 0; round < 5; round++)
            {
                var updated = round % 2 == 0 ? default : Timed(true, count, pattern, iterations);
                var old = Timed(false, count, pattern, iterations);
                if (round % 2 == 0) updated = Timed(true, count, pattern, iterations);
                Check(old.AllocatedBytes == 0 && updated.AllocatedBytes == 0, "steady-state flush allocates");
                Check(old.Calls == updated.Calls, "native API call count differs");
                oldTimes.Add(old.Nanoseconds); newTimes.Add(updated.Nanoseconds);
            }
            oldTimes.Sort(); newTimes.Sort();
            timings.Add(new { count, pattern = pattern == 0 ? "same" : pattern == 1 ? "alternating" : "seven-stage-cycle",
                iterations, controlMedianNs = oldTimes[2], candidateMedianNs = newTimes[2],
                controlRoundsNs = oldTimes, candidateRoundsNs = newTimes,
                controlAllocatedBytes = 0, candidateAllocatedBytes = 0 });
        }
        Console.WriteLine(JsonSerializer.Serialize(new { result = "passed", scenarios = _scenarios, checks = _checks,
            completeProductionBarrierBatchAndNativeArray = true, realSilkTypes = true, vulkanCallsDoubled = true,
            timings, limitation = "host CPU micro-measurements; no iPhone FPS or physical GPU measurement" }));
    }
}
