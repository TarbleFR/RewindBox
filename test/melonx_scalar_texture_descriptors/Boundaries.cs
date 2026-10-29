using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;
using Buffer = Silk.NET.Vulkan.Buffer;

namespace Ryujinx.Graphics.GAL
{
    interface ITexture { }
    interface ISampler { }
}

namespace Ryujinx.Graphics.Vulkan
{
    struct CommandBufferScoped { public CommandBuffer CommandBuffer; public int CommandBufferIndex; }
    readonly struct DisposableBuffer
    {
        public readonly Buffer Value;
        public DisposableBuffer(ulong handle) => Value = new Buffer { Handle = handle };
    }
    struct DisposableImageView { public ImageView Value; }
    struct DisposableSampler { public Silk.NET.Vulkan.Sampler Value; }
    sealed class Auto<T>
    {
        public readonly T Value;
        public bool Mirrored;
        public int Gets, MirrorableGets, WriteGets;
        public Auto(T value) => Value = value;
        public T Get(CommandBufferScoped cbs) { Gets++; return Value; }
        public T Get(CommandBufferScoped cbs, int offset, int size, bool write) { Gets++; if (write) WriteGets++; return Value; }
        public T GetMirrorable(CommandBufferScoped cbs, ref int offset, int size, out bool mirrored)
        { MirrorableGets++; mirrored = Mirrored; return Value; }
    }
    sealed class BufferHolder { public Auto<DisposableBuffer> GetBuffer() => null; }
    sealed class BufferManager
    {
        public readonly Auto<DisposableBuffer>[] Direct = { new(new DisposableBuffer(11)), new(new DisposableBuffer(22)) };
        public int Lookups, Writes, StorageLookups;
        public Action OnGet;
        public Auto<DisposableBuffer> GetBuffer(CommandBuffer command, BufferHandle handle, bool write, bool isSSBO = false)
        {
            Lookups++; if (write) Writes++; if (isSSBO) StorageLookups++;
            if (OnGet != null) { Action action = OnGet; OnGet = null; action(); }
            return Direct[(int)handle - 1];
        }
    }
    sealed class VulkanRenderer
    {
        public readonly BufferManager BufferManager = new();
        public readonly TestApi Api = new();
        public readonly TestPushApi PushDescriptorApi = new();
    }
    sealed class TestApi
    {
        public int DescriptorUpdates, Binds;
        public Buffer LastBuffer;
        public ulong LastOffset, LastRange, LastImage, LastSampler, LastBufferView;
        public readonly ulong[] LastImages = new ulong[128], LastSamplers = new ulong[128];
        public unsafe void UpdateDescriptorSetWithTemplate(Device device, DescriptorSet set, DescriptorUpdateTemplate template, void* data)
        {
            DescriptorUpdates++;
            int kind = (int)template.Handle - 1;
            if (kind >= 10)
            {
                LastBufferView = Unsafe.AsRef<BufferView>(data).Handle;
            }
            else if (kind >= 2)
            {
                ref DescriptorImageInfo info = ref Unsafe.AsRef<DescriptorImageInfo>(data);
                LastImage = info.ImageView.Handle; LastSampler = info.Sampler.Handle;
                for (int i = 0; i < 8; i++)
                {
                    var current = Unsafe.Add(ref info, i);
                    LastImages[i] = current.ImageView.Handle;
                    LastSamplers[i] = current.Sampler.Handle;
                }
            }
            else
            {
                ref DescriptorBufferInfo info = ref Unsafe.AsRef<DescriptorBufferInfo>(data);
                LastBuffer = info.Buffer; LastOffset = info.Offset; LastRange = info.Range;
            }
        }
        public void CmdBindDescriptorSets(CommandBuffer command, PipelineBindPoint bindPoint, PipelineLayout layout,
            uint firstSet, uint count, DescriptorSet[] sets, uint dynamicCount, ReadOnlySpan<uint> offsets) => Binds++;
    }
    sealed class TestPushApi
    {
        public int Pushes;
        public unsafe void CmdPushDescriptorSetWithTemplate(CommandBuffer command, DescriptorUpdateTemplate template,
            PipelineLayout layout, uint set, void* data) => Pushes++;
    }
    sealed class DescriptorSetTemplate
    {
        public int Size = 128 * Unsafe.SizeOf<DescriptorBufferInfo>();
        public DescriptorUpdateTemplate Template;
    }
    sealed class DescriptorSetCollection
    {
        readonly DescriptorSet[] _sets = { new() };
        public DescriptorSet[] GetSets() => _sets;
        public void InitializeBuffers(int set, int binding, int count, DescriptorType type, Buffer buffer) { }
    }
    sealed class ShaderCollection
    {
        public bool UsePushDescriptors, UpdateTexturesWithoutTemplate;
        public bool HasMinimalLayout = true;
        public int LayoutId = 1, NewSets, CommandUpdates;
        public PipelineLayout PipelineLayout;
        public readonly ResourceBindingSegment[][] BindingSegments = new ResourceBindingSegment[5][];
        public readonly ResourceBindingSegment[][] ClearSegments = new ResourceBindingSegment[5][];
        public readonly DescriptorSetTemplate[] Templates = new DescriptorSetTemplate[5];
        readonly Auto<DescriptorSetCollection> _sets = new(new DescriptorSetCollection());
        public ShaderCollection(int set, int count = 1, bool buffer = false)
        {
            for (int i = 0; i < 5; i++)
            {
                BindingSegments[i] = Array.Empty<ResourceBindingSegment>();
                ClearSegments[i] = Array.Empty<ResourceBindingSegment>();
                Templates[i] = new() { Template = new DescriptorUpdateTemplate((ulong)(i + 1 + (buffer ? 10 : 0))) };
            }
            ResourceType type = set switch { 0 => ResourceType.UniformBuffer, 1 => ResourceType.StorageBuffer,
                2 => buffer ? ResourceType.BufferTexture : ResourceType.TextureAndSampler,
                _ => buffer ? ResourceType.BufferImage : ResourceType.Image };
            BindingSegments[set] = new[] { new ResourceBindingSegment(0, count, type, ResourceStages.Fragment, false) };
        }
        public bool HasSameLayout(ShaderCollection other) => other != null && other.LayoutId == LayoutId;
        public void UpdateDescriptorCacheCommandBufferIndex(int index) => CommandUpdates++;
        public Auto<DescriptorSetCollection> GetNewDescriptorSetCollection(int set, out bool isNew)
        { NewSets++; isNew = false; return _sets; }
        public DescriptorSetTemplate GetPushDescriptorTemplate(long bindings) => Templates[0];
    }
    static class ResourceTrace
    {
        public static ulong Digest = 14695981039346656037;
        public static bool Enabled = true;
        public static void Record(ulong code, ulong value = 0)
        {
            if (!Enabled) return;
            Digest = unchecked((Digest ^ code) * 1099511628211);
            Digest = unchecked((Digest ^ value) * 1099511628211);
        }
    }
    sealed class TextureStorage
    {
        public int Barriers;
        public Action OnBarrier;
        public void QueueWriteToReadBarrier(CommandBufferScoped cbs, AccessFlags access, PipelineStageFlags stage)
        {
            Barriers++; ResourceTrace.Record(6, (ulong)stage); OnBarrier?.Invoke();
        }
    }
    sealed class TextureView : ITexture
    {
        public readonly TextureStorage Storage = new();
        public Auto<DisposableImageView> Normal, Identity;
        public int NormalGets, IdentityGets, Clears, Prepares;
        public Action OnPrepare, OnNormalGet, OnIdentityGet;
        public TextureView(ulong handle = 700)
        {
            Normal = new(new DisposableImageView { Value = new ImageView(handle) });
            Identity = new(new DisposableImageView { Value = new ImageView(handle + 10000) });
        }
        public Auto<DisposableImageView> GetImageView()
        { NormalGets++; ResourceTrace.Record(1, Normal.Value.Value.Handle); OnNormalGet?.Invoke(); return Normal; }
        public Auto<DisposableImageView> GetIdentityImageView()
        { IdentityGets++; ResourceTrace.Record(2, Identity.Value.Value.Handle); OnIdentityGet?.Invoke(); return Identity; }
        public void ClearUsage(List<TextureView> hazards)
        { Clears++; ResourceTrace.Record(3); }
        public void PrepareForUsage(CommandBufferScoped cbs, PipelineStageFlags stages, List<TextureView> hazards)
        { Prepares++; ResourceTrace.Record(4, (ulong)stages); OnPrepare?.Invoke(); }
    }
    sealed class SamplerHolder : ISampler
    {
        public Auto<DisposableSampler> Current;
        public int Gets;
        public Action OnGet;
        public SamplerHolder(ulong handle = 900)
        { Current = new(new DisposableSampler { Value = new Silk.NET.Vulkan.Sampler(handle) }); }
        public Auto<DisposableSampler> GetSampler()
        { Gets++; ResourceTrace.Record(5, Current.Value.Value.Handle); OnGet?.Invoke(); return Current; }
    }
    sealed class TextureBuffer : ITexture
    {
        public ulong Handle = 555;
        public int Gets;
        public BufferView GetBufferView(CommandBufferScoped cbs, bool write)
        { Gets++; return new BufferView(Handle); }
    }
    sealed class UnknownTexture : ITexture { }
    sealed class UnknownSampler : ISampler { }
    sealed class TextureArray
    {
        readonly DescriptorSet[] _sets = { new() };
        public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView texture, SamplerHolder sampler) => ReadOnlySpan<DescriptorImageInfo>.Empty;
        public ReadOnlySpan<BufferView> GetBufferViews(CommandBufferScoped cbs) => ReadOnlySpan<BufferView>.Empty;
        public DescriptorSet[] GetDescriptorSets(Device device, CommandBufferScoped cbs, DescriptorSetTemplateUpdater updater,
            ShaderCollection shader, int set, TextureView texture, SamplerHolder sampler) => _sets;
    }
    sealed class ImageArray
    {
        readonly DescriptorSet[] _sets = { new() };
        public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView texture) => ReadOnlySpan<DescriptorImageInfo>.Empty;
        public ReadOnlySpan<BufferView> GetBufferViews(CommandBufferScoped cbs) => ReadOnlySpan<BufferView>.Empty;
        public DescriptorSet[] GetDescriptorSets(Device device, CommandBufferScoped cbs, DescriptorSetTemplateUpdater updater,
            ShaderCollection shader, int set, TextureView texture) => _sets;
    }
    static class TestConversions
    {
        public static DescriptorType Convert(this ResourceType type) => DescriptorType.UniformBuffer;
        public static PipelineStageFlags ConvertToPipelineStageFlags(this ShaderStage stage)
            => (PipelineStageFlags)(1UL << (int)stage);
    }
    static class PipelineBase
    {
        public const int UniformSetIndex = 0, StorageSetIndex = 1, TextureSetIndex = 2, ImageSetIndex = 3, DescriptorSetLayouts = 4;
    }

    partial class DescriptorSetUpdater : IDisposable
    {
        private const ulong StorageBufferMaxMirrorable = 0x2000;
        private readonly record struct ArrayRef<T>(ShaderStage Stage, T Array);
        private readonly VulkanRenderer _gd = new();
        private readonly Device _device;
        private ShaderCollection _program;
        private readonly BufferRef[] _uniformBufferRefs = new BufferRef[128], _storageBufferRefs = new BufferRef[128];
        private readonly TextureRef[] _textureRefs = new TextureRef[128];
        private readonly ImageRef[] _imageRefs = new ImageRef[128];
        private readonly TextureBuffer[] _bufferTextureRefs = new TextureBuffer[128], _bufferImageRefs = new TextureBuffer[128];
        private ArrayRef<TextureArray>[] _textureArrayRefs = new ArrayRef<TextureArray>[128];
        private ArrayRef<ImageArray>[] _imageArrayRefs = new ArrayRef<ImageArray>[128];
        private ArrayRef<TextureArray>[] _textureArrayExtraRefs = { new(ShaderStage.Fragment, new TextureArray()) };
        private ArrayRef<ImageArray>[] _imageArrayExtraRefs = { new(ShaderStage.Fragment, new ImageArray()) };
        private readonly DescriptorBufferInfo[] _uniformBuffers = new DescriptorBufferInfo[128], _storageBuffers = new DescriptorBufferInfo[128];
        private readonly DescriptorImageInfo[] _textures = new DescriptorImageInfo[128], _images = new DescriptorImageInfo[128];
        private readonly BufferView[] _bufferTextures = new BufferView[128], _bufferImages = new BufferView[128];
        private readonly DescriptorSetTemplateUpdater _templateUpdater = new();
        private BitMapStruct<Array2<long>> _uniformSet, _storageSet, _uniformMirrored, _storageMirrored;
        private readonly int[] _uniformSetPd = new int[128];
        private int _pdSequence = 1;
        private bool _updateDescriptorCacheCbIndex;
        private DirtyFlags _dirty;
        private readonly BufferHolder _dummyBuffer;
        private readonly TextureView _dummyTexture = new();
        private readonly SamplerHolder _dummySampler = new();
        public List<TextureView> FeedbackLoopHazards { get; private set; } = new();
        public VulkanRenderer Gd => _gd;
        public Auto<DisposableImageView> ImageViewAt(int index) => _imageRefs[index].ImageView;
        public object TextureViewAt(int index) => _textureRefs[index].View;
        public int DirtyBits => (int)_dirty;
        public void Draw(CommandBufferScoped cbs = default) => UpdateAndBindDescriptorSets(cbs, PipelineBindPoint.Graphics);
        public void Dispose() => _templateUpdater.Dispose();
        // The legacy exceptional Vulkan fallback and individual texture fallback
        // are outside this buffer-path test. Unexpected use fails the test.
        private void UpdateAndBind(CommandBufferScoped cbs, int set, PipelineBindPoint point) => throw new InvalidOperationException("unexpected descriptor fallback");
        private void UpdateAndBindTexturesWithoutTemplate(CommandBufferScoped cbs, ShaderCollection shader, PipelineBindPoint point) => throw new InvalidOperationException("unexpected texture fallback");
    }
}
