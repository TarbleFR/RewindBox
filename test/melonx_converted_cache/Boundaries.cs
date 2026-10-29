using System;
using System.Collections.Generic;

namespace Ryujinx.Graphics.Vulkan
{
    // GPU payload/dirty callbacks are doubled; CacheByRange and all its keys and
    // Dependency are compiled in full from the actual source file.
    sealed class Auto<T> { }
    readonly struct DisposableBuffer { }
    sealed class IndexBufferPattern { }
    sealed class PipelineBoundary
    {
        public readonly List<string> Dirty = new();
        public void DirtyIndexBuffer(Auto<DisposableBuffer> value) => Dirty.Add(value == null ? "index:null" : "index:buffer");
        public void DirtyVertexBuffer(Auto<DisposableBuffer> value) => Dirty.Add(value == null ? "vertex:null" : "vertex:buffer");
    }
    sealed class VulkanRenderer { public readonly PipelineBoundary PipelineInternal = new(); }
    sealed class BufferHolder
    {
        public CacheByRange<Payload> Cache;
        public int Removals;
        public void RemoveCachedConvertedBuffer(int offset, int size, ICacheKey key)
        {
            Removals++;
            Cache.Remove(offset, size, key);
        }
    }
}
