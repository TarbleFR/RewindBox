using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Control = Ryujinx.Graphics.Vulkan.Control.BarrierBatch;

// The complete production BarrierBatch of the Core 649 preparation (control, renamed namespace) and of the candidate (plus
// adapt_artifact_counters), compiled with the production NativeArray against doubled driver boundaries (Boundaries.cs).
// Every flush of every scenario must emit the same API barriers, pass ends and forced fences in both, and the candidate's
// InPassAttachmentBarriersKept must move only on a tile-based MoltenVK without argument-buffer hazard tracking, inside a
// pass, when every queued image barrier is for an attachment and the pass is still active after the memory-barrier check of
// the same loop turn: once per such loop turn. A memory barrier queued for DrawIndirect or for compute (a stage
// SupportsRenderPassBarrier rejects) ends the pass in that turn, and the image barriers are then recorded outside it: 0.
static class Program
{
    static int _checks;
    static void Check(bool condition, string message) { _checks++; if (!condition) throw new Exception(message); }

    // An image barrier queue: resource ids (even: attachment) and the destination stage of each; an optional memory barrier
    // (source, destination; queued before or after the images); the expected count on the path (tile-based MoltenVK
    // without hazard tracking, in a pass) and whether the pass ends there before any image barrier is recorded.
    sealed record Queue(string Name, (int Id, PipelineStageFlags Dest)[] Images, (PipelineStageFlags Source, PipelineStageFlags Dest)? Memory,
        bool MemoryLast, int KeptDecisions, bool PassEndsOnPath);

    const PipelineStageFlags Fragment = PipelineStageFlags.FragmentShaderBit, Vertex = PipelineStageFlags.VertexShaderBit,
        Color = PipelineStageFlags.ColorAttachmentOutputBit;
    static readonly (int, PipelineStageFlags)[] OneAttachment = { (2, Fragment) };

    static readonly Queue[] Queues =
    {
        new("none", Array.Empty<(int, PipelineStageFlags)>(), null, false, 0, false),
        new("one attachment", OneAttachment, null, false, 1, false),
        new("attachments only, one stage", new[] { (2, Fragment), (4, Fragment) }, null, false, 1, false),
        new("attachments only, two stages", new[] { (2, Fragment), (4, Vertex) }, null, false, 2, false),
        new("20 attachments (two batches of at most 16)", Enumerable.Range(0, 20).Select(i => (2 * i, Fragment)).ToArray(), null, false, 2, false),
        new("memory barrier first, then an attachment", new[] { (2, Vertex) }, (Fragment, Fragment), false, 2, false),
        // The image-barrier decision keeps these in the pass, then the memory-barrier check of the same turn ends it.
        new("memory barrier to DrawIndirect, then an attachment", OneAttachment, (Color, PipelineStageFlags.DrawIndirectBit), false, 0, true),
        new("an attachment, then a memory barrier to DrawIndirect", OneAttachment, (Color, PipelineStageFlags.DrawIndirectBit), true, 0, true),
        new("memory barrier to compute, then an attachment", OneAttachment, (Color, PipelineStageFlags.ComputeShaderBit), false, 0, true),
        new("one non-attachment", new[] { (3, Fragment) }, null, false, 0, true),
        new("mixed", new[] { (2, Fragment), (3, Fragment) }, null, false, 0, true),
    };

    static (List<string> trace, long kept, long ended) Run(bool candidate, Queue q, bool tbdr, bool moltenVk, bool tracks, bool inPass)
    {
        VulkanRenderer gd = new() { IsTBDR = tbdr, IsMoltenVk = moltenVk, MoltenVkTracksArgumentBufferHazards = moltenVk && tracks };
        gd.Api.Capture = true;
        RenderPassHolder holder = new(gd.Api);
        Action end = () => gd.Api.Trace.Add("end");
        long kept = RenderDetail.InPassAttachmentBarriersKept, ended = RenderDetail.EndedPassImageBarriers;
        if (candidate)
        {
            using BarrierBatch batch = new(gd);
            Fill(q, batch.QueueBarrier, batch.QueueBarrier);
            batch.Flush(default, null, false, inPass, holder, end);
            batch.Flush(default, null, false, false, null, end);
        }
        else
        {
            using Control batch = new(gd);
            Fill(q, batch.QueueBarrier, batch.QueueBarrier);
            batch.Flush(default, null, false, inPass, holder, end);
            batch.Flush(default, null, false, false, null, end);
        }
        return (gd.Api.Trace, RenderDetail.InPassAttachmentBarriersKept - kept, RenderDetail.EndedPassImageBarriers - ended);
    }

    static void Fill(Queue q, Action<MemoryBarrier, PipelineStageFlags, PipelineStageFlags> memory,
        Action<ImageMemoryBarrier, TextureStorage, PipelineStageFlags, PipelineStageFlags> image)
    {
        void Memory()
        {
            memory(new MemoryBarrier { SType = StructureType.MemoryBarrier, SrcAccessMask = AccessFlags.ShaderWriteBit,
                DstAccessMask = AccessFlags.ShaderReadBit }, q.Memory.Value.Source, q.Memory.Value.Dest);
        }
        if (q.Memory != null && !q.MemoryLast)
        {
            Memory();
        }
        foreach ((int id, PipelineStageFlags dest) in q.Images)
        {
            image(new ImageMemoryBarrier { SType = StructureType.ImageMemoryBarrier, SrcAccessMask = AccessFlags.ColorAttachmentWriteBit,
                DstAccessMask = AccessFlags.ShaderReadBit, Image = new Image((ulong)id + 79), OldLayout = ImageLayout.General,
                NewLayout = ImageLayout.General, SubresourceRange = new ImageSubresourceRange(ImageAspectFlags.ColorBit, 0, 1, 0, 1) },
                new TextureStorage(id), PipelineStageFlags.ColorAttachmentOutputBit, dest);
        }
        if (q.Memory != null && q.MemoryLast)
        {
            Memory();
        }
    }

    static void Main()
    {
        int scenarios = 0;
        long keptTotal = 0, keptScenarios = 0, passEndingMemoryScenarios = 0;
        var kept = new Dictionary<string, long>();
        foreach (Queue q in Queues)
        foreach (bool tbdr in new[] { true, false })
        foreach (bool moltenVk in new[] { true, false })
        foreach (bool tracks in new[] { false, true })
        foreach (bool inPass in new[] { true, false })
        {
            if (!moltenVk && tracks) continue; // production: tracking implies MoltenVK
            var control = Run(false, q, tbdr, moltenVk, tracks, inPass);
            var candidate = Run(true, q, tbdr, moltenVk, tracks, inPass);
            string name = $"{q.Name} tbdr={tbdr} moltenVk={moltenVk} tracks={tracks} inPass={inPass}";
            Check(control.trace.SequenceEqual(candidate.trace), "API barriers, pass ends or forced fences differ: " + name);
            Check(control.ended == candidate.ended, "EndedPassImageBarriers differs: " + name);
            bool path = tbdr && moltenVk && !tracks && inPass;
            long expected = path ? q.KeptDecisions : 0;
            Check(candidate.kept == expected, $"InPassAttachmentBarriersKept {candidate.kept}, expected {expected}: {name}");
            Check(control.kept == 0, "the control has no such counter increment: " + name);
            if (path)
            {
                kept[q.Name] = candidate.kept;
                // Counted only when the image barriers are recorded inside the pass: no pass end at all. When the pass
                // ends (non-attachment, or a memory barrier the pass cannot hold), it ends before any image barrier call.
                int endAt = candidate.trace.IndexOf("end");
                int imageAt = candidate.trace.FindIndex(entry => entry.StartsWith("i:"));
                Check(imageAt >= 0 || q.Images.Length == 0, "the image barriers were recorded: " + name);
                Check(q.PassEndsOnPath ? endAt >= 0 && endAt < imageAt && candidate.kept == 0 : endAt < 0,
                    "pass end and count disagree: " + name + " " + string.Join(",", candidate.trace));
                bool memoryEnds = q.PassEndsOnPath && q.Memory != null;
                passEndingMemoryScenarios += memoryEnds ? 1 : 0;
            }
            keptTotal += candidate.kept;
            keptScenarios += candidate.kept > 0 ? 1 : 0;
            scenarios++;
        }
        Check(keptScenarios == Queues.Count(q => q.KeptDecisions > 0), "counted exactly in the attachment-only MoltenVK 1.4.2 pass scenarios");
        Check(passEndingMemoryScenarios == 3, "the memory barriers that end the pass were exercised on the path");
        Console.WriteLine(JsonSerializer.Serialize(new { result = "passed", scenarios, checks = _checks, keptTotal, keptScenarios,
            passEndingMemoryScenarios, keptOnPath = kept }));
    }
}
