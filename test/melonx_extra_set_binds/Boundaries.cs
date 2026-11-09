// Boundaries of the production DescriptorSetUpdater members compiled by melonx_extra_set_binds_test.py (adapted from the
// Core 705 fixture test/melonx_same_program_descriptors). The members, DescriptorSetTemplateUpdater (and its writer),
// BitMapStruct, ResourceBindingSegment and the GAL and common types they use are production files. Here: the Vulkan
// calls, which keep the bytes each descriptor set was written with and the set bound at each (bind point, set index)
// with Vulkan's disturbance rule (a bind with an incompatible layout, here another layout handle, unbinds the lower
// sets bound with another layout and every higher set), and the resources (views, samplers, buffers, buffer textures,
// texture, buffer texture and image arrays with their own set per version) with plain handles.
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;
using Buffer = Silk.NET.Vulkan.Buffer;

namespace Ryujinx.Graphics.GAL
{
    interface ITexture { }
    interface ISampler { }
    interface ITextureArray { }
    interface IImageArray { }
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
        public Auto(T value) => Value = value;
        public T Get(CommandBufferScoped cbs) => Value;
        public T Get(CommandBufferScoped cbs, int offset, int size, bool write) => Value;
        public T GetMirrorable(CommandBufferScoped cbs, ref int offset, int size, out bool mirrored) { mirrored = false; return Value; }
    }
    sealed class BufferHolder
    {
        public readonly Auto<DisposableBuffer> Buffer = new(new DisposableBuffer(1));
        public Auto<DisposableBuffer> GetBuffer() => Buffer;
    }
    sealed class BufferManager
    {
        public readonly Dictionary<ulong, Auto<DisposableBuffer>> Buffers = new();
        public Auto<DisposableBuffer> GetBuffer(CommandBuffer command, BufferHandle handle, bool write, bool isSSBO = false)
        {
            ulong key = Unsafe.As<BufferHandle, ulong>(ref handle);
            if (!Buffers.TryGetValue(key, out var buffer))
            {
                Buffers[key] = buffer = new(new DisposableBuffer(1000 + key));
            }
            return buffer;
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
        public readonly Dictionary<ulong, byte[]> Contents = new();
        public readonly Dictionary<(PipelineBindPoint, uint), ulong> Bound = new();
        public readonly Dictionary<(PipelineBindPoint, uint), ulong> BoundLayout = new();
        public int SetWrites, Binds;
        public long DescriptorsWritten;
        public readonly int[] WritesBySet = new int[4];
        public unsafe void UpdateDescriptorSetWithTemplate(Device device, DescriptorSet set, DescriptorUpdateTemplate template, void* data)
        {
            DescriptorSetTemplate known = DescriptorSetTemplate.All[template.Handle];
            Contents[set.Handle] = new ReadOnlySpan<byte>(data, known.Size).ToArray();
            SetWrites++;
            WritesBySet[known.SetIndex]++;
            DescriptorsWritten += known.Descriptors;
        }
        public void CmdBindDescriptorSets(CommandBuffer command, PipelineBindPoint bindPoint, PipelineLayout layout,
            uint firstSet, uint count, DescriptorSet[] sets, uint dynamicCount, ReadOnlySpan<uint> offsets)
        {
            Binds++;
            // Vulkan pipeline layout compatibility, with "compatible" read as "the same layout handle" (stricter).
            bool disturbHigher = BoundLayout.TryGetValue((bindPoint, firstSet), out ulong previous) && previous != layout.Handle;
            foreach (var key in new List<(PipelineBindPoint, uint)>(BoundLayout.Keys))
            {
                if (key.Item1 == bindPoint && key.Item2 < firstSet && BoundLayout[key] != layout.Handle)
                {
                    Bound.Remove(key); BoundLayout.Remove(key); disturbHigher = true;
                }
            }
            if (disturbHigher)
            {
                foreach (var key in new List<(PipelineBindPoint, uint)>(BoundLayout.Keys))
                {
                    if (key.Item1 == bindPoint && key.Item2 > firstSet) { Bound.Remove(key); BoundLayout.Remove(key); Disturbed++; }
                }
            }
            Bound[(bindPoint, firstSet)] = sets[0].Handle;
            BoundLayout[(bindPoint, firstSet)] = layout.Handle;
        }
        public int Disturbed;
    }
    sealed class TestPushApi
    {
        public unsafe void CmdPushDescriptorSetWithTemplate(CommandBuffer command, DescriptorUpdateTemplate template,
            PipelineLayout layout, uint set, void* data) => throw new InvalidOperationException("no push descriptors here");
    }
    sealed class DescriptorSetTemplate
    {
        public static readonly Dictionary<ulong, DescriptorSetTemplate> All = new();
        static ulong _next = 1;
        public readonly int Size, SetIndex, Descriptors;
        public readonly DescriptorUpdateTemplate Template;
        public DescriptorSetTemplate(int setIndex, int size, int descriptors)
        {
            SetIndex = setIndex; Size = size; Descriptors = descriptors;
            Template = new DescriptorUpdateTemplate(_next++);
            All[Template.Handle] = this;
        }
    }
    sealed class DescriptorSetCollection
    {
        static ulong _next = 1;
        readonly DescriptorSet[] _sets = { new(_next++) };
        public DescriptorSet[] GetSets() => _sets;
        public void InitializeBuffers(int set, int binding, int count, DescriptorType type, Buffer buffer) { }
    }
    sealed class ShaderCollection
    {
        public bool UsePushDescriptors, UpdateTexturesWithoutTemplate;
        public bool HasMinimalLayout = true;
        public int LayoutId, Allocations;
        public PipelineLayout PipelineLayout;
        public readonly ResourceBindingSegment[][] BindingSegments;
        public readonly ResourceBindingSegment[][] ClearSegments;
        public readonly DescriptorSetTemplate[] Templates;
        public ShaderCollection(int layoutId, ResourceBindingSegment[][] segments)
        {
            LayoutId = layoutId;
            PipelineLayout = new PipelineLayout((ulong)layoutId);
            BindingSegments = segments;
            ClearSegments = new ResourceBindingSegment[segments.Length][];
            Templates = new DescriptorSetTemplate[segments.Length];
            for (int set = 0; set < segments.Length; set++)
            {
                ClearSegments[set] = Array.Empty<ResourceBindingSegment>();
                int size = 0, descriptors = 0;
                foreach (ResourceBindingSegment segment in segments[set])
                {
                    size += segment.Count * Program.ElementSize(segment.Type);
                    descriptors += segment.Count;
                }
                Templates[set] = set < 4 ? new DescriptorSetTemplate(set, size, descriptors) : null;
            }
        }
        public bool HasSameLayout(ShaderCollection other) => other != null && other.LayoutId == LayoutId;
        public void UpdateDescriptorCacheCommandBufferIndex(int index) { }
        public Auto<DescriptorSetCollection> GetNewDescriptorSetCollection(int set, out bool isNew)
        { Allocations++; Program.Allocations++; isNew = true; return new(new DescriptorSetCollection()); }
        public DescriptorSetTemplate GetPushDescriptorTemplate(long bindings) => throw new InvalidOperationException();
    }
    sealed class TextureView : ITexture
    {
        public readonly Auto<DisposableImageView> Normal, Identity;
        public TextureView(ulong handle)
        {
            Normal = new(new DisposableImageView { Value = new ImageView(handle) });
            Identity = new(new DisposableImageView { Value = new ImageView(handle + 100000) });
        }
        public Auto<DisposableImageView> GetImageView() => Normal;
        public Auto<DisposableImageView> GetIdentityImageView() => Identity;
        public void ClearUsage(List<TextureView> hazards) { }
        public void PrepareForUsage(CommandBufferScoped cbs, PipelineStageFlags stages, List<TextureView> hazards) { }
        public void Dispose() { }
    }
    sealed class SamplerHolder : ISampler
    {
        public readonly Auto<DisposableSampler> Current;
        public SamplerHolder(ulong handle) => Current = new(new DisposableSampler { Value = new Silk.NET.Vulkan.Sampler(handle) });
        public Auto<DisposableSampler> GetSampler() => Current;
        public void Dispose() { }
    }
    // A buffer texture whose view can change without a setter call (SetStorage, its buffer's release).
    sealed class TextureBuffer : ITexture
    {
        public ulong ViewHandle;
        public TextureBuffer(ulong view) => ViewHandle = view;
        public BufferView GetBufferView(CommandBufferScoped cbs, bool write) => new(ViewHandle);
    }
    // Which array and which version each array set holds (texture, buffer texture and image arrays).
    static class ArraySets
    {
        public static ulong Next = 1_000_000;
        public static readonly Dictionary<ulong, (object Array, int Version)> Held = new();
    }
    // A bindless texture array in its own set: a new set per content version (TextureArray's own sets), with the
    // version each set holds.
    sealed class TextureArray : ITextureArray
    {
        public int Version, BindCount;
        public readonly Dictionary<ulong, int> VersionOfSet = new();
        DescriptorSet[] _sets;
        public void Change() { Version++; _sets = null; }
        public void IncrementBindCount() => BindCount++;
        public void DecrementBindCount() => BindCount--;
        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stages) { }
        public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView texture, SamplerHolder sampler)
            => throw new InvalidOperationException("no array in the main texture set here");
        public ReadOnlySpan<BufferView> GetBufferViews(CommandBufferScoped cbs) => throw new InvalidOperationException();
        public DescriptorSet[] GetDescriptorSets(Device device, CommandBufferScoped cbs, DescriptorSetTemplateUpdater updater,
            ShaderCollection shader, int set, TextureView texture, SamplerHolder sampler)
        {
            Program.ArraySetCalls++;
            if (_sets == null)
            {
                _sets = new[] { new DescriptorSet(ArraySets.Next++) };
                VersionOfSet[_sets[0].Handle] = Version;
                ArraySets.Held[_sets[0].Handle] = (this, Version);
            }
            return _sets;
        }
    }
    // A bindless image array in its own set, as the texture array.
    sealed class ImageArray : IImageArray
    {
        public int Version, BindCount;
        DescriptorSet[] _sets;
        public void Change() { Version++; _sets = null; }
        public void IncrementBindCount() => BindCount++;
        public void DecrementBindCount() => BindCount--;
        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stages) { }
        public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView texture) => throw new InvalidOperationException();
        public ReadOnlySpan<BufferView> GetBufferViews(CommandBufferScoped cbs) => throw new InvalidOperationException();
        public DescriptorSet[] GetDescriptorSets(Device device, CommandBufferScoped cbs, DescriptorSetTemplateUpdater updater,
            ShaderCollection shader, int set, TextureView texture)
        {
            Program.ArraySetCalls++;
            if (_sets == null)
            {
                _sets = new[] { new DescriptorSet(ArraySets.Next++) };
                ArraySets.Held[_sets[0].Handle] = (this, Version);
            }
            return _sets;
        }
    }
    static class TestConversions
    {
        public static DescriptorType Convert(this ResourceType type) => DescriptorType.UniformBuffer;
        public static PipelineStageFlags ConvertToPipelineStageFlags(this ShaderStage stage) => (PipelineStageFlags)(1UL << (int)stage);
    }
    static class PipelineBase
    {
        public const int UniformSetIndex = 0, StorageSetIndex = 1, TextureSetIndex = 2, ImageSetIndex = 3, DescriptorSetLayouts = 4;
    }
    public static class EncodingPolicy
    {
        public static bool BindingSizedDescriptorScratch { get; set; } = true;
    }
    static class RenderDetail
    {
        public static readonly long[] TemplateFallbacks = new long[4];
        public static readonly long[] DescriptorSetWrites = new long[4];
        public static long DescriptorsWritten, ProgramSets, SameProgramSets;
    }

    partial class DescriptorSetUpdater
    {
        private const int ArrayGrowthSize = 16;
        private const ulong StorageBufferMaxMirrorable = 0x2000;
        private readonly record struct ArrayRef<T>(ShaderStage Stage, T Array);
        private readonly VulkanRenderer _gd = new();
        private readonly Device _device;
        private ShaderCollection _program;
        private readonly BufferRef[] _uniformBufferRefs = new BufferRef[Constants.MaxUniformBufferBindings];
        private readonly BufferRef[] _storageBufferRefs = new BufferRef[Constants.MaxStorageBufferBindings];
        private readonly TextureRef[] _textureRefs = new TextureRef[Constants.MaxTextureBindings * 2];
        private readonly ImageRef[] _imageRefs = new ImageRef[Constants.MaxImageBindings * 2];
        private readonly TextureBuffer[] _bufferTextureRefs = new TextureBuffer[Constants.MaxTextureBindings * 2];
        private readonly TextureBuffer[] _bufferImageRefs = new TextureBuffer[Constants.MaxImageBindings * 2];
        private ArrayRef<TextureArray>[] _textureArrayRefs = new ArrayRef<TextureArray>[1];
        private ArrayRef<ImageArray>[] _imageArrayRefs = new ArrayRef<ImageArray>[1];
        private ArrayRef<TextureArray>[] _textureArrayExtraRefs = new ArrayRef<TextureArray>[1];
        private ArrayRef<ImageArray>[] _imageArrayExtraRefs = new ArrayRef<ImageArray>[1];
        private readonly DescriptorBufferInfo[] _uniformBuffers = new DescriptorBufferInfo[Constants.MaxUniformBufferBindings];
        private readonly DescriptorBufferInfo[] _storageBuffers = new DescriptorBufferInfo[Constants.MaxStorageBufferBindings];
        private readonly DescriptorImageInfo[] _textures = new DescriptorImageInfo[Constants.MaxTextureBindings * 2];
        private readonly DescriptorImageInfo[] _images = new DescriptorImageInfo[Constants.MaxImageBindings * 2];
        private readonly BufferView[] _bufferTextures = new BufferView[Constants.MaxTextureBindings * 2];
        private readonly BufferView[] _bufferImages = new BufferView[Constants.MaxImageBindings * 2];
        private readonly DescriptorSetTemplateUpdater _templateUpdater = new();
        private BitMapStruct<Ryujinx.Common.Memory.Array2<long>> _uniformSet, _storageSet, _uniformMirrored, _storageMirrored;
        private readonly int[] _uniformSetPd = new int[Constants.MaxUniformBufferBindings];
        private int _pdSequence = 1;
        private bool _updateDescriptorCacheCbIndex;
        private DirtyFlags _dirty;
        private readonly BufferHolder _dummyBuffer = new();
        private readonly TextureView _dummyTexture = new(1);
        private readonly SamplerHolder _dummySampler = new(2);
        public List<TextureView> FeedbackLoopHazards { get; private set; } = new();
        public VulkanRenderer Gd => _gd;
        public ShaderCollection Current => _program;
        private void UpdateAndBind(CommandBufferScoped cbs, int setIndex, PipelineBindPoint pbp) => throw new InvalidOperationException("unexpected descriptor fallback");
        private void UpdateAndBindTexturesWithoutTemplate(CommandBufferScoped cbs, ShaderCollection shader, PipelineBindPoint point) => throw new InvalidOperationException("unexpected texture fallback");
    }
}
