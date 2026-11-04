using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Control = Ryujinx.Graphics.Vulkan.Control.BarrierBatch;

// Core 642: the delivered BarrierBatch (stable compaction, build 87) as control, the final prepared BarrierBatch (plus
// adapt_moltenvk_barrier_ordering) as candidate, both complete production classes with the production NativeArray.
//
// tracks = true (MoltenVK 1.4.0 or earlier, or not MoltenVK): every emitted API barrier, pass end and forced fence of the
// candidate equals the control's, in all 624 compaction scenarios: the build 87 proof still holds where 642 is inactive.
//
// tracks = false (MoltenVK 1.4.1 or later): the only intended difference is the in-pass image barrier branch on a
// tile-based GPU. When an image barrier queued inside the pass is for a non-attachment, the candidate ends the pass as the
// delivered class does for other tile-based GPUs (IsMoltenVk false); otherwise it keeps the delivered MoltenVK path.
// BarrierBatch reads IsMoltenVk nowhere else, so the reference is the control class flushed with IsMoltenVk set, for that
// flush, to whether the candidate keeps the MoltenVK path. Which flushes end the pass is predicted independently from
// the queued image barriers (non-attachment: odd resource id, RenderPassHolder.ContainsAttachment) and must equal the
// candidate's own RenderDetail.EndedPassImageBarriers count.

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
    public bool EndsPass(bool anyIsNonAttachment) => _batch.EndsPassForInPassImageBarriers(anyIsNonAttachment);
}

static class Program
{
    static int _checks, _scenarios, _endingFlushes, _keptFlushes;
    static void Check(bool condition, string message) { _checks++; if (!condition) throw new Exception(message); }
    static readonly PipelineStageFlags[] Stages = {
        PipelineStageFlags.VertexShaderBit, PipelineStageFlags.FragmentShaderBit,
        PipelineStageFlags.ComputeShaderBit, PipelineStageFlags.TransferBit,
        PipelineStageFlags.AllGraphicsBit, PipelineStageFlags.DrawIndirectBit,
        PipelineStageFlags.TransformFeedbackBitExt
    };

    // Returns whether an image barrier was queued for a non-attachment (odd id: RenderPassHolder.ContainsAttachment).
    static bool Queue(IBatch batch, int kind, uint id, TextureStorage resource, PipelineStageFlags source, PipelineStageFlags dest)
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
        return kind == 2 && (resource.Id & 1) != 0;
    }

    // Candidate (updated): checks its pass endings against the prediction. Control: flushed with the reference's IsMoltenVk.
    static List<string> Trace(bool updated, int seed, int count, int mode, bool tracks, List<bool> endings)
    {
        Random random = new(seed);
        bool moltenVk = (mode & 2) != 0, tbdr = (mode & 1) != 0, renderPass = (mode & 8) != 0;
        VulkanRenderer gd = new() { IsTBDR = tbdr, IsMoltenVk = moltenVk,
            MoltenVkTracksArgumentBufferHazards = moltenVk && tracks,
            TransformFeedbackApi = (mode & 4) != 0 ? new object() : null };
        gd.Api.Capture = true;
        using IBatch batch = updated ? new NewBatch(gd) : new OldBatch(gd);
        TextureStorage[] resources = Enumerable.Range(0, 64).Select(x => new TextureStorage(x)).ToArray();
        RenderPassHolder holder = new(gd.Api);
        ShaderCollection shader = new() { IncoherentBufferWriteStages = Stages[seed % Stages.Length],
            IncoherentTextureWriteStages = Stages[(seed + 1) % Stages.Length] };
        Action end = () => gd.Api.Trace.Add("end");
        for (int frame = 0; frame < 3; frame++)
        {
            bool nonAttachment = false;
            for (uint i = 0; i < count; i++)
                nonAttachment |= Queue(batch, random.Next(3), i + (uint)frame * 65536, resources[random.Next(resources.Length)],
                    Stages[random.Next(Stages.Length)], Stages[random.Next(Stages.Length)]);
            if (mode >= 8) { batch.Tfb((frame & 1) == 0); batch.Incoherent(frame); }
            bool ends = tbdr && renderPass && nonAttachment && moltenVk && !tracks;
            if (updated)
            {
                long before = RenderDetail.EndedPassImageBarriers;
                batch.Flush(mode >= 8 ? shader : null, (mode & 4) != 0, renderPass, holder, end);
                Check(RenderDetail.EndedPassImageBarriers - before == (ends ? 1 : 0),
                      $"candidate pass ending differs from the prediction count={count} mode={mode} seed={seed} frame={frame}");
                Check(((NewBatch)batch).EndsPass(nonAttachment) == (nonAttachment && moltenVk && !tracks), "EndsPassForInPassImageBarriers rule");
                endings.Add(ends);
            }
            else
            {
                gd.IsMoltenVk = moltenVk && !ends;
                batch.Flush(mode >= 8 ? shader : null, (mode & 4) != 0, renderPass, holder, end);
                gd.IsMoltenVk = moltenVk;
            }
            batch.Flush(null, false, false, null, end); // Completely drained, no extra API call.
        }
        return gd.Api.Trace;
    }

    static void Main()
    {
        int[] counts = { 0, 1, 15, 16, 17, 31, 32, 33, 63, 64, 127, 257, 1024 };
        foreach (bool tracks in new[] { true, false })
        foreach (int count in counts)
        for (int mode = 0; mode < 16; mode++)
        for (int seed = 1; seed <= 3; seed++)
        {
            List<bool> endings = new();
            List<string> candidate = Trace(true, seed, count, mode, tracks, endings);
            List<string> control = Trace(false, seed, count, mode, tracks, new List<bool>());
            Check(control.SequenceEqual(candidate), $"native barrier trace differs tracks={tracks} count={count} mode={mode} seed={seed}");
            if (!tracks && (mode & 2) != 0 && (mode & 1) != 0 && (mode & 8) != 0)
            {
                _endingFlushes += endings.Count(x => x);
                _keptFlushes += endings.Count(x => !x);
            }
            _scenarios++;
        }
        // The new branch is exercised (some flushes end the pass, some keep the MoltenVK path).
        Check(_endingFlushes > 0 && _keptFlushes > 0, "the MoltenVK 1.4.2 in-pass branch was not exercised both ways");
        Console.WriteLine(JsonSerializer.Serialize(new { result = "passed", scenarios = _scenarios, checks = _checks,
            endingFlushes = _endingFlushes, keptMoltenVkFlushes = _keptFlushes,
            completeProductionBarrierBatchAndNativeArray = true, realSilkTypes = true, vulkanCallsDoubled = true,
            limitation = "host traces of the doubled Vulkan API; no Metal, MoltenVK, iPhone or FPS measurement" }));
    }
}
