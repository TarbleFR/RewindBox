using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using Ryujinx.Graphics.GAL;
using Silk.NET.Vulkan;
using VkBuffer = Silk.NET.Vulkan.Buffer;
using VkFormat = Silk.NET.Vulkan.Format;
using Format = Ryujinx.Graphics.GAL.Format;

namespace Ryujinx.Common {
    static class BitUtils {
        public static int AlignUp(int value, int align) => (value + align - 1) & -align;
        public static int DivRoundUp(int value, int divisor) => (value + divisor - 1) / divisor;
    }
}
namespace Ryujinx.Common.Logging {
    enum LogClass { Gpu }
    class Sink { public void PrintMsg(LogClass c, string message) { } }
    static class Logger { public static Sink Debug; }
}
namespace Ryujinx.Graphics.GAL { record struct BufferHandle(ulong Value); }
namespace Silk.NET.Vulkan {
    enum Result { ErrorOutOfHostMemory, ErrorOutOfDeviceMemory, ErrorDeviceLost, ErrorUnknown }
    record struct Buffer(ulong Handle);
    record struct Image(ulong Handle);
    record struct CommandBuffer(int Id);
    enum Format { Other, D32SfloatS8Uint }
    enum ImageLayout { General }
    [Flags] enum ImageAspectFlags { ColorBit = 1, DepthBit = 2, StencilBit = 4 }
    record struct ImageSubresourceLayers(ImageAspectFlags AspectMask, uint MipLevel, uint BaseArrayLayer, uint LayerCount);
    record struct Extent3D(uint Width, uint Height, uint Depth);
    record struct Offset3D(int X, int Y, int Z);
    record struct BufferImageCopy(ulong BufferOffset, uint BufferRowLength, uint BufferImageHeight,
        ImageSubresourceLayers ImageSubresource, Offset3D ImageOffset, Extent3D ImageExtent);
}
namespace Ryujinx.Graphics.Vulkan {
    class VulkanException : Exception { public Result? ResultCode; public VulkanException(Result result) { ResultCode = result; } }
    enum BufferAllocationType { HostMapped }
    class DisposableBuffer { public VkBuffer Value; }
    class DisposableImage { public Image Value; }
    class Auto<T> where T : class {
        private readonly T _value;
        public Auto(T value) { _value = value; }
        public T Get(CommandBufferScoped cbs, int offset = 0, int size = 0) => _value;
    }
    class FenceHolder {
        public bool Signaled;
        public int References;
        public void Get() { References++; }
        public void Put() { References--; if (References < 0) throw new Exception("Fence reference underflow"); }
        public bool IsSignaled() => Signaled;
        public void Wait() { if (!Signaled) throw new Exception("Upload waited for an unfinished fence"); }
    }
    readonly struct CommandBufferScoped : IDisposable {
        public readonly CommandBuffer CommandBuffer;
        private readonly CommandBufferPool _pool;
        public CommandBufferScoped(CommandBufferPool pool, int id) { _pool = pool; CommandBuffer = new(id); }
        public FenceHolder GetFence() => _pool.Fences[CommandBuffer.Id];
        public void Dispose() { }
    }
    class CommandBufferPool {
        private int _next;
        public readonly Dictionary<int, FenceHolder> Fences = new();
        public CommandBufferScoped Rent() { int id = ++_next; Fences[id] = new(); return new(this, id); }
        public CommandBufferScoped ReturnAndRent(CommandBufferScoped old) => Rent();
        public bool IsFenceOnRentedCommandBuffer(FenceHolder fence) => true;
    }
    class BufferHolder : IDisposable {
        private static ulong _next;
        public static Dictionary<ulong, BufferHolder> All = new();
        public readonly byte[] Data;
        public readonly ulong Id;
        public int DisposeCount;
        public int Size => Data.Length;
        public BufferHolder(int size) { Data = new byte[size]; Id = ++_next; All[Id] = this; }
        public Span<byte> GetDataStorage(int offset, int size) => Data.AsSpan(offset, size);
        public void SetDataUnchecked(int offset, ReadOnlySpan<byte> data) => data.CopyTo(GetDataStorage(offset, data.Length));
        public Auto<DisposableBuffer> GetBuffer() => new(new() { Value = new(Id) });
        public Auto<DisposableBuffer> GetBuffer(CommandBuffer commandBuffer, int offset = 0, int size = 0, bool write = false) => GetBuffer();
        public static void Copy(VulkanRenderer gd, CommandBufferScoped cbs, Auto<DisposableBuffer> source,
            Auto<DisposableBuffer> destination, int sourceOffset, int destOffset, int size) =>
            All[source.Get(cbs).Value.Handle].Data.AsSpan(sourceOffset, size).CopyTo(
                All[destination.Get(cbs).Value.Handle].Data.AsSpan(destOffset, size));
        public void Dispose() { DisposeCount++; if (DisposeCount != 1) throw new Exception("Native buffer disposed twice"); }
    }
    class BufferManager : IDisposable {
        public int NativeCreates;
        public readonly StagingBuffer StagingBuffer;
        private StagingBuffer _textureStagingBuffer;
        private bool _textureStagingUnavailable;
        private readonly List<BufferHolder> _buffers = new();
        public readonly List<BufferHolder> AllCreated = new();
        public bool ReturnNullForNextLarge;
        public Result? ThrowForNextLarge;
        public int LargeAllocationAttempts;
        public BufferManager(VulkanRenderer gd) { StagingBuffer = new(gd, this); }
        public BufferHolder Create(VulkanRenderer gd, int size) {
            NativeCreates++;
            if (size == 16 * 1024 * 1024) {
                LargeAllocationAttempts++;
                if (ReturnNullForNextLarge) { ReturnNullForNextLarge = false; return null; }
                if (ThrowForNextLarge is Result error) { ThrowForNextLarge = null; throw new VulkanException(error); }
            }
            var holder = new BufferHolder(size); AllCreated.Add(holder); return holder;
        }
        public BufferHandle CreateWithHandle(VulkanRenderer gd, int size, out BufferHolder holder) {
            holder = Create(gd, size); if (holder == null) return new(0); _buffers.Add(holder); return new(holder.Id);
        }
        public void Delete(BufferHandle handle) { var holder = _buffers.SingleOrDefault(b => b.Id == handle.Value); if (holder != null) { holder.Dispose(); _buffers.Remove(holder); } }
        /* TEXTURE_POOL_METHOD */
        /* MANAGER_DISPOSAL */
    }
    class Storage {
        public bool Inline;
        public bool HasCommandBufferDependency(CommandBufferScoped cbs) => Inline;
    }
    class Pipeline {
        public CommandBufferScoped CurrentCommandBuffer;
        public CommandBufferScoped Preload;
        public int EndRenderPassCalls;
        public Pipeline(CommandBufferPool pool) { CurrentCommandBuffer = pool.Rent(); Preload = pool.Rent(); }
        public CommandBufferScoped GetPreloadCommandBuffer() => Preload;
        public void EndRenderPass() { EndRenderPassCalls++; }
    }
    class Capabilities { public ulong MinResourceAlignment = 256; }
    class VulkanRenderer {
        public readonly CommandBufferPool CommandBufferPool = new();
        public readonly Pipeline PipelineInternal;
        public readonly Capabilities Capabilities = new();
        public readonly BufferManager BufferManager;
        public readonly Api Api = new();
        public VulkanRenderer() { PipelineInternal = new(CommandBufferPool); BufferManager = new(this); }
        public void FlushAllCommands() => throw new Exception("Upload flushed to obtain staging space");
    }
    class Api {
        public record Copy(VkBuffer Buffer, Image Image, BufferImageCopy Region, bool ToImage);
        public readonly List<Copy> Copies = new();
        public readonly Dictionary<Image, (TextureCreateInfo Info, bool Expanded)> Images = new();
        public void CmdCopyBufferToImage(CommandBuffer cbs, VkBuffer buffer, Image image, ImageLayout layout,
            int count, in BufferImageCopy region) => Copies.Add(new(buffer, image, region, true));
        public void CmdCopyImageToBuffer(CommandBuffer cbs, Image image, ImageLayout layout, VkBuffer buffer,
            int count, in BufferImageCopy region) => Copies.Add(new(buffer, image, region, false));
        public string Complete() {
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            foreach (Copy copy in Copies) {
                var (info, expanded) = Images[copy.Image];
                int rows = (int)(copy.Region.ImageExtent.Height + (uint)info.BlockHeight - 1) / info.BlockHeight;
                int columns = (int)copy.Region.BufferRowLength / info.BlockWidth;
                int size = columns * info.BytesPerPixel * rows * (int)copy.Region.ImageExtent.Depth * (int)copy.Region.ImageSubresource.LayerCount;
                if (expanded) size *= 2;
                hash.AppendData(BufferHolder.All[copy.Buffer.Handle].Data.AsSpan((int)copy.Region.BufferOffset, size));
            }
            Copies.Clear();
            return Convert.ToHexString(hash.GetHashAndReset());
        }
    }
    static class FormatCapabilities { public static bool IsD24S8(Format format) => format == Format.D24UnormS8Uint; }
    static class EnumConversion {
        public static ImageAspectFlags ConvertAspectFlags(this Format format) =>
            format.HasDepth ? ImageAspectFlags.DepthBit | (format.HasStencil ? ImageAspectFlags.StencilBit : 0) : ImageAspectFlags.ColorBit;
    }
    class TextureView {
        private readonly VulkanRenderer _gd;
        public readonly TextureCreateInfo Info;
        public readonly Storage Storage = new();
        public VkFormat VkFormat;
        public int FirstLayer, FirstLevel;
        private static ulong _nextImage;
        private readonly Image _image;
        public TextureView(VulkanRenderer gd, TextureCreateInfo info, bool expanded = false) {
            _gd = gd; Info = info; VkFormat = expanded ? VkFormat.D32SfloatS8Uint : VkFormat.Other;
            _image = new(++_nextImage); gd.Api.Images[_image] = (info, expanded);
        }
        public Auto<DisposableImage> GetImage() => new(new() { Value = _image });
        public void Upload(ReadOnlySpan<byte> data, int layer = 0, int level = 0, int layers = 1, int levels = 1,
            bool singleSlice = true, Rectangle<int>? region = null) => SetData(data, layer, level, layers, levels, singleSlice, region);
        /* PRODUCTION_METHODS */
    }
}
