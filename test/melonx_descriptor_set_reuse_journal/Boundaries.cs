// Boundaries of the production DescriptorSetUpdater members compiled by melonx_descriptor_set_reuse_journal_test.py.
// Production files: the DescriptorSetUpdater members (and, in the candidate, the adapter's members and journal),
// DescriptorSetTemplateUpdater with its writer, NativeArray, BitMapStruct, ResourceBindingSegment, Constants and the GAL
// and common types they use. Here: the Vulkan calls (a command buffer's bound sets per (bind point, set index) with the
// layout they were bound with, Vulkan's rule that a bind with another layout disturbs them, the bytes each set was last
// written with, and a hash of every write and bind in call order), the layout's per-command-buffer set lists (each set handed out once per submission, the lists
// reused at the next submission of that command buffer, as PipelineLayoutCacheEntry), the programs and the resources.
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

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Printer
    {
        public static readonly List<string> Lines = new();
        public void Print(LogClass logClass, string text) => Lines.Add(text);
    }
    static class Logger
    {
        public static Printer Warning = new();
    }
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
        // Resources referenced by the command buffer (a set collection's own reference is not counted: the candidate takes
        // fewer sets).
        public T Get(CommandBufferScoped cbs) { if (typeof(T) != typeof(DescriptorSetCollection)) Program.ResourceGets++; return Value; }
        public T Get(CommandBufferScoped cbs, int offset, int size, bool write) { Program.ResourceGets++; return Value; }
        public T GetMirrorable(CommandBufferScoped cbs, ref int offset, int size, out bool mirrored) { Program.ResourceGets++; mirrored = false; return Value; }
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
    // The command buffer being recorded: what a draw or dispatch reads is the set bound at (bind point, set index) with
    // the layout it was bound with; a bind with another layout disturbs every set bound at that bind point (the fixture's
    // layouts are all incompatible). Verify: the bytes each set was last written with are kept. Timing: counts only.
    sealed class TestApi
    {
        public bool Verify = true;
        // Every write (set, template, bytes) and bind (bind point, layout, index, set), in call order.
        public readonly System.Security.Cryptography.IncrementalHash Calls = System.Security.Cryptography.IncrementalHash.CreateHash(System.Security.Cryptography.HashAlgorithmName.SHA256);
        readonly byte[] _call = new byte[40];
        void Record(ulong a, ulong b, ulong c, ulong d)
        {
            System.Runtime.InteropServices.MemoryMarshal.Write(_call.AsSpan(0), in a);
            System.Runtime.InteropServices.MemoryMarshal.Write(_call.AsSpan(8), in b);
            System.Runtime.InteropServices.MemoryMarshal.Write(_call.AsSpan(16), in c);
            System.Runtime.InteropServices.MemoryMarshal.Write(_call.AsSpan(24), in d);
            Calls.AppendData(_call, 0, 32);
        }
        public readonly Dictionary<ulong, byte[]> Contents = new();
        public readonly Dictionary<(PipelineBindPoint, uint), (ulong Set, ulong Layout)> Bound = new();
        public long SetWrites, Binds, DescriptorsWritten;
        public readonly long[] WritesBySet = new long[4];
        public unsafe void UpdateDescriptorSetWithTemplate(Device device, DescriptorSet set, DescriptorUpdateTemplate template, void* data)
        {
            DescriptorSetTemplate known = DescriptorSetTemplate.All[template.Handle];
            if (Verify)
            {
                if (!Contents.TryGetValue(set.Handle, out byte[] bytes) || bytes.Length != known.Size)
                {
                    Contents[set.Handle] = bytes = new byte[known.Size];
                }
                new ReadOnlySpan<byte>(data, known.Size).CopyTo(bytes);
                Program.NoteWrite(set.Handle);
                Record(1, set.Handle, template.Handle, (ulong)known.Size);
                Calls.AppendData(bytes);
            }
            SetWrites++;
            WritesBySet[known.SetIndex]++;
            DescriptorsWritten += known.Descriptors;
        }
        public void CmdBindDescriptorSets(CommandBuffer command, PipelineBindPoint bindPoint, PipelineLayout layout,
            uint firstSet, uint count, ReadOnlySpan<DescriptorSet> sets, uint dynamicCount, ReadOnlySpan<uint> offsets)
        {
            Binds++;
            if (!Verify) return;
            Program.CheckCommandBuffer(command);
            Record(2, (ulong)bindPoint, layout.Handle, ((ulong)firstSet << 32) | count);
            Record(3, sets[0].Handle, (ulong)command.Handle, 0);
            List<(PipelineBindPoint, uint)> disturbed = null;
            foreach (var pair in Bound)
            {
                if (pair.Key.Item1 == bindPoint && pair.Value.Layout != layout.Handle) (disturbed ??= new()).Add(pair.Key);
            }
            if (disturbed != null) foreach (var key in disturbed) Bound.Remove(key);
            Bound[(bindPoint, firstSet)] = (sets[0].Handle, layout.Handle);
            Program.NoteBound(sets[0].Handle);
        }
        public void NewCommandBuffer() => Bound.Clear();
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
    // PipelineLayoutCacheEntry's set lists: per command buffer index and set index, a cursor reset when the command
    // buffer index or its submission changes; a set is handed out once per submission and reused at the next one.
    sealed class TestLayout
    {
        public readonly int Id;
        public readonly PipelineLayout PipelineLayout;
        readonly List<Auto<DescriptorSetCollection>>[,] _lists = new List<Auto<DescriptorSetCollection>>[Program.CommandBuffers, 8];
        readonly int[] _cursor = new int[8];
        int _lastIndex = -1, _lastSubmission = -1, _current;
        public TestLayout(int id) { Id = id; PipelineLayout = new PipelineLayout(0x7000 + (ulong)id); }
        public void UpdateCommandBufferIndex(int index)
        {
            int submission = Program.Submissions[index];
            if (index != _lastIndex || submission != _lastSubmission)
            {
                _lastIndex = index;
                _lastSubmission = submission;
                Array.Clear(_cursor);
            }
            _current = index;
        }
        public Auto<DescriptorSetCollection> GetNew(int set, out bool isNew)
        {
            List<Auto<DescriptorSetCollection>> list = _lists[_current, set] ??= new();
            int index = _cursor[set]++;
            Program.SetsTaken++;
            if (index == list.Count)
            {
                list.Add(new(new DescriptorSetCollection()));
                Program.SetsAllocated++;
                isNew = true;
                return list[index];
            }
            isNew = false;
            return list[index];
        }
    }
    sealed class ShaderCollection
    {
        public bool UsePushDescriptors, UpdateTexturesWithoutTemplate;
        public bool HasMinimalLayout = true;
        public bool IsCompute;
        public readonly string Name;
        public readonly TestLayout Layout;
        public PipelineLayout PipelineLayout => Layout.PipelineLayout;
        public readonly ResourceBindingSegment[][] BindingSegments;
        public readonly ResourceBindingSegment[][] ClearSegments;
        public readonly DescriptorSetTemplate[] Templates;
        public readonly DescriptorSetUpdater.DirtyFlags BufferViewDirtyFlags;
        public ShaderCollection(string name, TestLayout layout, bool compute, ResourceBindingSegment[][] segments)
        {
            Name = name;
            Layout = layout;
            IsCompute = compute;
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
            BufferViewDirtyFlags = DescriptorSetUpdater.BufferViewSets(segments);
        }
        public bool HasSameLayout(ShaderCollection other) => other != null && other.Layout == Layout;
        public void UpdateDescriptorCacheCommandBufferIndex(int index) => Layout.UpdateCommandBufferIndex(index);
        public Auto<DescriptorSetCollection> GetNewDescriptorSetCollection(int set, out bool isNew) => Layout.GetNew(set, out isNew);
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
    // A bindless texture array in its own set: a set per content version, returned again while unchanged (as
    // TextureArray's current set), with the version each set holds.
    sealed class TextureArray : ITextureArray
    {
        static ulong _next = 1_000_000;
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
                _sets = new[] { new DescriptorSet(_next++) };
                VersionOfSet[_sets[0].Handle] = Version;
            }
            return _sets;
        }
    }
    sealed class ImageArray : IImageArray
    {
        public void IncrementBindCount() { }
        public void DecrementBindCount() { }
        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stages) { }
        public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView texture) => throw new InvalidOperationException();
        public ReadOnlySpan<BufferView> GetBufferViews(CommandBufferScoped cbs) => throw new InvalidOperationException();
        public DescriptorSet[] GetDescriptorSets(Device device, CommandBufferScoped cbs, DescriptorSetTemplateUpdater updater,
            ShaderCollection shader, int set, TextureView texture) => throw new InvalidOperationException();
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
        public static bool IncrementalArrayDescriptors { get; set; }
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
        private readonly VulkanRenderer _gd;
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
        public List<TextureView> FeedbackLoopHazards { get; private set; }
        public VulkanRenderer Gd => _gd;
        public ShaderCollection Current => _program;
        // The main pipeline's updater gets the hazard list (Initialize(isMainPipeline)); a helper pipeline's does not.
        public DescriptorSetUpdater(VulkanRenderer gd, bool mainPipeline)
        {
            _gd = gd;
            FeedbackLoopHazards = mainPipeline ? new() : null;
        }
        private void UpdateAndBind(CommandBufferScoped cbs, int setIndex, PipelineBindPoint pbp) => throw new InvalidOperationException("unexpected descriptor fallback");
        private void UpdateAndBindTexturesWithoutTemplate(CommandBufferScoped cbs, ShaderCollection shader, PipelineBindPoint point) => throw new InvalidOperationException("unexpected texture fallback");
    }
}
