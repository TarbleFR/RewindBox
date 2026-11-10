using System;
using System.Collections.Generic;
using Ryujinx.Graphics.GAL;

namespace Ryujinx.Graphics.Vulkan
{
    sealed class Auto<T> { }
    readonly struct DisposableBuffer { }
    readonly struct CommandBufferScoped { }
    sealed class IndexBufferPattern
    {
        public int GetConvertedCount(int indexCount) => indexCount * 2;
    }
    struct IndexBufferState
    {
        Auto<DisposableBuffer> _buffer;
        public void TestBind(Auto<DisposableBuffer> value) => _buffer = value;
        /* PRODUCTION_BOUND_EQUALS */
    }
    sealed class PipelineBoundary
    {
        IndexBufferState _indexBuffer;
        bool _needsIndexBufferRebind;
        public int PassEnds;
        public bool NeedsRebind => _needsIndexBufferRebind;
        public void TestBind(Auto<DisposableBuffer> value) { _indexBuffer.TestBind(value); _needsIndexBufferRebind = false; }
        public void EndRenderPass() => PassEnds++;
        public void DirtyVertexBuffer(Auto<DisposableBuffer> value) { }
        /* PRODUCTION_DIRTY_INDEX */
    }
    sealed class HelperBoundary
    {
        public int Conversions;
        public void ConvertIndexBufferIndirect(VulkanRenderer gd, CommandBufferScoped cbs,
            BufferHolder indirect, BufferHolder convertedIndirect, BufferRange drawCount,
            BufferHolder indices, BufferHolder convertedIndices, IndexBufferPattern pattern,
            int indexSize, int indexOffset, int indexLength, int indirectOffset,
            bool hasDrawCount, int maxDrawCount, int stride) => Conversions++;
    }
    sealed class VulkanRenderer
    {
        public readonly PipelineBoundary PipelineInternal = new();
        public readonly HelperBoundary HelperShader = new();
    }
    sealed class BufferHolder : IDisposable
    {
        CacheByRange<BufferHolder> _cachedConvertedBuffers;
        readonly Auto<DisposableBuffer> _buffer = new();
        public int Disposals;
        public Auto<DisposableBuffer> GetBuffer() => _buffer;
        public void Invalidate(int offset, int size) => _cachedConvertedBuffers.ClearRange(offset, size);
        public void Dispose() { Disposals++; _cachedConvertedBuffers.Dispose(); }
        /* PRODUCTION_CACHE_WRAPPERS */
    }
    sealed class BufferManager
    {
        readonly Dictionary<BufferHandle, BufferHolder> _sources = new();
        public readonly List<BufferHolder> Created = new();
        public void AddSource(BufferHandle handle, BufferHolder value) => _sources.Add(handle, value);
        public bool TryGetBuffer(BufferHandle handle, out BufferHolder holder) => _sources.TryGetValue(handle, out holder);
        public BufferHolder Create(VulkanRenderer gd, int size)
        {
            var holder = new BufferHolder(); Created.Add(holder); return holder;
        }
        /* PRODUCTION_INDIRECT_CONVERSION */
    }
}
