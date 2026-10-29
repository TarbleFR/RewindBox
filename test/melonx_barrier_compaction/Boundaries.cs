using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;

namespace Ryujinx.Graphics.Vulkan
{
    readonly struct CommandBufferScoped
    {
        public CommandBuffer CommandBuffer => new(0x1234);
    }
    sealed class ShaderCollection
    {
        public PipelineStageFlags IncoherentBufferWriteStages;
        public PipelineStageFlags IncoherentTextureWriteStages;
    }
    sealed class TextureStorage
    {
        public readonly int Id;
        public TextureStorage(int id) => Id = id;
    }
    sealed class RenderPassHolder
    {
        readonly FakeApi _api;
        public RenderPassHolder(FakeApi api) => _api = api;
        public void InsertForcedFences(CommandBufferScoped cbs) { if (_api.Capture) _api.Trace.Add("insert"); }
        public bool ContainsAttachment(TextureStorage resource) => resource != null && (resource.Id & 1) == 0;
        public void AddForcedFence(TextureStorage resource, PipelineStageFlags flags)
        { if (_api.Capture) _api.Trace.Add($"force:{resource?.Id}:{(uint)flags}"); }
    }
    sealed class VulkanRenderer
    {
        public readonly FakeApi Api = new();
        public object TransformFeedbackApi;
        public bool IsTBDR;
        public bool IsMoltenVk;
        public bool SupportsRenderPassBarrier(PipelineStageFlags flags) => (flags & PipelineStageFlags.ComputeShaderBit) == 0;
    }
    sealed class FakeApi
    {
        public readonly List<string> Trace = new();
        public bool Capture;
        public long Calls;
        public ulong Digest;
        public unsafe void CmdPipelineBarrier(CommandBuffer command, PipelineStageFlags source, PipelineStageFlags dest,
            uint flags, uint memoryCount, MemoryBarrier* memory, uint bufferCount, BufferMemoryBarrier* buffers,
            uint imageCount, ImageMemoryBarrier* images)
        {
            Calls++;
            Digest ^= (uint)source + ((ulong)(uint)dest << 32) + memoryCount + bufferCount + imageCount;
            if (!Capture) return;
            Trace.Add($"call:{command.Handle}:{(uint)source}:{(uint)dest}:{flags}:{memoryCount}:{bufferCount}:{imageCount}");
            for (int i = 0; i < memoryCount; i++)
                Trace.Add($"m:{(int)memory[i].SType}:{(nuint)memory[i].PNext}:{(uint)memory[i].SrcAccessMask}:{(uint)memory[i].DstAccessMask}");
            for (int i = 0; i < bufferCount; i++)
            {
                ref BufferMemoryBarrier b = ref buffers[i];
                Trace.Add($"b:{(int)b.SType}:{(nuint)b.PNext}:{(uint)b.SrcAccessMask}:{(uint)b.DstAccessMask}:{b.Buffer.Handle}:{b.Offset}:{b.Size}:{b.SrcQueueFamilyIndex}:{b.DstQueueFamilyIndex}");
            }
            for (int i = 0; i < imageCount; i++)
            {
                ref ImageMemoryBarrier b = ref images[i];
                ref ImageSubresourceRange r = ref b.SubresourceRange;
                Trace.Add($"i:{(int)b.SType}:{(nuint)b.PNext}:{(uint)b.SrcAccessMask}:{(uint)b.DstAccessMask}:{b.Image.Handle}:{(int)b.OldLayout}:{(int)b.NewLayout}:{b.SrcQueueFamilyIndex}:{b.DstQueueFamilyIndex}:{(uint)r.AspectMask}:{r.BaseArrayLayer}:{r.LayerCount}:{r.BaseMipLevel}:{r.LevelCount}");
            }
        }
    }
}
