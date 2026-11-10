using System;
using System.Collections.Generic;
using Ryujinx.Graphics.GAL;
using Silk.NET.Vulkan;

namespace Ryujinx.Common.Memory {
    struct PinnedSpan<T> { }
    class MemoryOwner<T> : IDisposable {
        public Span<T> Span => System.Span<T>.Empty;
        public void Dispose() { }
    }
}
namespace Ryujinx.Graphics.GAL {
    interface ITexture { }
    record struct BufferHandle(int Value);
    record struct BufferRange(BufferHandle Handle, int Offset, int Size);
    struct TextureCreateInfo { public int Width, Height; public int Format; }
    struct Extents2D { }
    struct Rectangle<T> { }
}
namespace Silk.NET.Vulkan {
    enum Format { Test }
    record struct BufferView(int Id);
}
namespace Ryujinx.Graphics.Vulkan {
    static class FormatTable { public static Format GetFormat(int value) => Format.Test; }
    struct CommandBufferScoped { }
    class DisposableBufferView { public BufferView Value; }
    class Auto<T> : IDisposable where T : class {
        public T Value;
        public bool Disposed;
        public Auto(T value) { Value = value; }
        public T Get(CommandBufferScoped cbs, int offset, int size, bool write) {
            if (Disposed) throw new Exception("Disposed view reused");
            return Value;
        }
        public void Dispose() { Disposed = true; }
    }
    class BufferHolder { }
    class BufferManager {
        private readonly Dictionary<BufferHandle, BufferHolder> _buffers = new();
        public int BufferCount;
        public int ViewCreates;
        public void Create(BufferHandle handle) { _buffers[handle] = new(); BufferCount++; }
        public void Delete(BufferHandle handle) { _buffers.Remove(handle); }
        public BufferHolder GetBufferIdentity(BufferHandle handle) =>
            _buffers.TryGetValue(handle, out var holder) ? holder : null;
        public Auto<DisposableBufferView> CreateView(BufferHandle handle, Format format, int offset, int size, Action invalidateView) {
            if (!_buffers.ContainsKey(handle)) return null;
            ViewCreates++;
            return new(new DisposableBufferView { Value = new BufferView(ViewCreates) });
        }
    }
    class VulkanRenderer {
        public BufferManager BufferManager = new();
        public HashSet<ITexture> Textures = new();
        public Ryujinx.Common.Memory.PinnedSpan<byte> GetBufferData(BufferHandle handle, int offset, int size) => new();
        public void SetBufferData(BufferHandle handle, int offset, ReadOnlySpan<byte> bytes) { }
    }
}
