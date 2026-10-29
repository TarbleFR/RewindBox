using System;
using System.Collections.Generic;
using Silk.NET.Vulkan;

namespace Ryujinx.Graphics.Vulkan
{
    // These doubles cover GPU objects/dispatch only; the complete production
    // RenderPassHolder, including construction, duplicate handling and disposal,
    // is compiled without extracting or rewriting any method.
    interface IRefEquatable<T> { bool Equals(ref T other); }
    sealed class HashTableSlim<TKey, TValue> where TKey : IRefEquatable<TKey>
    {
        readonly List<(TKey Key, TValue Value)> _items = new();
        public IEnumerable<TValue> Values { get { foreach (var item in _items) yield return item.Value; } }
        public bool TryGetValue(ref TKey key, out TValue result)
        {
            foreach (var item in _items)
            {
                TKey copy = item.Key;
                if (copy.Equals(ref key)) { result = item.Value; return true; }
            }
            result = default;
            return false;
        }
        public void Add(ref TKey key, TValue value) => _items.Add((key, value));
    }
    static class Constants { public const int MaxRenderTargets = 8; }
    readonly struct RenderPassCacheKey { }
    readonly struct CommandBufferScoped { }
    sealed class TextureStorage
    {
        public static readonly List<int> DispatchOrder = new();
        public bool Disposed;
        public readonly int Id;
        public readonly List<PipelineStageFlags> Barriers = new();
        public TextureStorage(int id) => Id = id;
        public void QueueWriteToReadBarrier(CommandBufferScoped cbs, AccessFlags access, PipelineStageFlags flags)
        {
            if (access != AccessFlags.ShaderReadBit) throw new Exception("wrong access");
            Barriers.Add(flags);
            DispatchOrder.Add(Id);
        }
        public static SampleCountFlags ConvertToSampleCountFlags(SampleCountFlags flags, int samples) => SampleCountFlags.Count1Bit;
    }
    sealed class TextureView
    {
        public TextureStorage Storage;
        public int Adds, Removes;
        public TextureView(TextureStorage storage) => Storage = storage;
        public void AddRenderPass(RenderPassCacheKey key, RenderPassHolder holder) => Adds++;
        public void RemoveRenderPass(RenderPassCacheKey key) => Removes++;
    }
    sealed class Auto<T> : IDisposable where T : IDisposable
    {
        public readonly T Value;
        public Auto(T value) => Value = value;
        public void Dispose() => Value.Dispose();
    }
    sealed class DisposableRenderPass : IDisposable
    {
        public bool Disposed;
        public DisposableRenderPass(FakeApi api, Device device, RenderPass renderPass) { }
        public void Dispose() => Disposed = true;
    }
    sealed class DisposableFramebuffer : IDisposable { public void Dispose() { } }
    sealed class VulkanRenderer
    {
        public readonly FakeApi Api = new();
        public readonly Caps Capabilities = new();
    }
    sealed class Caps { public SampleCountFlags SupportedSampleCounts = SampleCountFlags.Count1Bit; }
    unsafe sealed class FakeApi
    {
        public Result CreateRenderPass(Device device, in RenderPassCreateInfo info, AllocationCallbacks* alloc, out RenderPass renderPass)
        { renderPass = default; return Result.Success; }
    }
    static class ResultExtensions
    {
        public static void ThrowOnError(this Result result) { if (result != Result.Success) throw new Exception("API error"); }
    }
    static class PipelineConverter
    {
        public static SubpassDependency CreateSubpassDependency(VulkanRenderer gd) => default;
    }
    sealed class FramebufferParams
    {
        public uint Width = 1, Height = 1, Layers = 1;
        public int AttachmentsCount, ColorAttachmentsCount, MaxColorAttachmentIndex;
        public bool HasDepthStencil;
        public readonly Format[] AttachmentFormats = [];
        public readonly int[] AttachmentSamples = [], AttachmentIndices = [];
        readonly TextureView[] _views;
        public int Creates;
        public FramebufferParams(TextureView[] views) => _views = views;
        public TextureView[] GetAttachmentViews() => _views;
        public Auto<DisposableFramebuffer> Create(FakeApi api, CommandBufferScoped cbs, Auto<DisposableRenderPass> pass)
        { Creates++; return new(new()); }
    }
}
