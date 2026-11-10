using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using Buffer = Silk.NET.Vulkan.Buffer;

static class Check
{
    public static int Count;
    public static void That(bool value, string message)
    { Count++; if (!value) throw new InvalidOperationException(message); }
}

static class Program
{
#if DESCRIPTOR_ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif
    static BufferHandle Handle(ulong value) => Unsafe.As<ulong, BufferHandle>(ref value);
    static BufferAssignment Assignment(int slot = 0, ulong handle = 1, int offset = 16, int size = 64, bool write = false)
        => new(slot, new BufferRange(Handle(handle), offset, size, write));

    static void Assign(DescriptorSetUpdater updater, string kind, BufferAssignment[] assignments)
    {
        if (kind == "uniform" || kind == "uniformPush") updater.SetUniformBuffers(default, assignments);
        else if (kind == "storage") updater.SetStorageBuffers(default, assignments);
        else updater.SetStorageBuffers(default, 0, updater.Gd.BufferManager.Direct);
    }

    static void CheckChangingFields(string kind)
    {
        using DescriptorSetUpdater updater = new();
        ShaderCollection shader = new(kind == "uniform" ? 0 : 1, 1, extra: true);
        updater.SetProgram(default, shader, false);
        BufferAssignment[] assignments = { Assignment() };
        Assign(updater, kind, assignments); updater.Draw();
        int firstUpdates = updater.Gd.Api.DescriptorUpdates;
        Check.That(firstUpdates == 1, "first assignment publishes descriptors");
        Assign(updater, kind, assignments); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == firstUpdates + (Adapted ? 0 : 1), "identical assignment dispatch");
        int lookups = updater.Gd.BufferManager.Lookups;
        foreach (BufferAssignment changed in new[]
        {
            Assignment(offset: 32), Assignment(offset: 32, size: 128),
            Assignment(handle: 2, offset: 32, size: 128),
            Assignment(handle: 2, offset: 32, size: 128, write: true),
            Assignment(handle: 0, offset: 0, size: 0), Assignment(),
        })
        {
            int before = updater.Gd.Api.DescriptorUpdates;
            assignments[0] = changed;
            Assign(updater, kind, assignments); updater.Draw();
            Check.That(updater.Gd.Api.DescriptorUpdates == before + 1, "changed identity/offset/range/write/null must publish");
        }
        Check.That(updater.Gd.BufferManager.Lookups == lookups + 5, "non-null assignments always resolve their buffer");
        Check.That(updater.Gd.Api.LastBuffer.Handle == 11 && updater.Gd.Api.LastOffset == 16 && updater.Gd.Api.LastRange == 64,
                   "actual template bytes contain the current binding");

        // An unchanged tail must not erase an earlier change in the same batch.
        shader = new(kind == "uniform" ? 0 : 1, 2, extra: true);
        updater.SetProgram(default, shader, false);
        assignments = new[] { Assignment(), Assignment(slot: 1, handle: 2) };
        Assign(updater, kind, assignments); updater.Draw();
        assignments[0] = Assignment(offset: 48);
        int beforeBatch = updater.Gd.Api.DescriptorUpdates;
        Assign(updater, kind, assignments); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == beforeBatch + 1 && updater.Gd.Api.LastOffset == 48,
                   "changed prefix survives an unchanged suffix");
    }

    static void CheckInvalidations(string kind)
    {
        using DescriptorSetUpdater updater = new();
        ShaderCollection shader = new(kind == "uniform" ? 0 : 1, 1, extra: true);
        updater.SetProgram(default, shader, false);
        BufferAssignment[] assignments = { Assignment() };
        Auto<DisposableBuffer> buffer = updater.Gd.BufferManager.Direct[0];
        buffer.Mirrored = true;
        Assign(updater, kind, assignments); updater.Draw();
        int before = updater.Gd.Api.DescriptorUpdates;
        int gets = buffer.MirrorableGets;
        updater.Rebind(buffer, 20, 8);
        Assign(updater, kind, assignments); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before + 1 && buffer.MirrorableGets == gets + 1,
                   "overlapping mirror invalidation still acquires and republishes");

        before = updater.Gd.Api.DescriptorUpdates;
        updater.Rebind(buffer, 4096, 8);
        updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before, "non-overlapping write does not invalidate");

        // GetBuffer can invalidate a mirror while an otherwise identical setter executes.
        updater.Gd.BufferManager.OnGet = () => updater.Rebind(buffer, 16, 64);
        Assign(updater, kind, assignments); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before + 1, "buffer-resolution side effect retains dirty state");

        before = updater.Gd.Api.DescriptorUpdates;
        updater.SignalCommandBufferChange();
        Assign(updater, kind, assignments); updater.Draw(new CommandBufferScoped { CommandBufferIndex = 2 });
        Check.That(updater.Gd.Api.DescriptorUpdates == before + 1, "new command buffer still republishes");

        before = updater.Gd.Api.DescriptorUpdates;
        ShaderCollection replacement = new(kind == "uniform" ? 0 : 1, 1, extra: true) { LayoutId = 2 };
        updater.SetProgram(default, replacement, false);
        Assign(updater, kind, assignments); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before + 1 && replacement.NewSets == 1,
                   "new program/layout still acquires its descriptor set");

        before = updater.Gd.Api.DescriptorUpdates;
        Auto<DisposableBuffer> swapped = new(new DisposableBuffer(31));
        updater.SwapBuffer(buffer, swapped);
        updater.Gd.BufferManager.Direct[0] = swapped;
        // PipelineBase.SwapBuffer calls this immediately after the updater's SwapBuffer.
        updater.SignalCommandBufferChange();
        Assign(updater, kind, assignments); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before + 1 && updater.Gd.Api.LastBuffer.Handle == 31,
                   "swapped buffer and command invalidation retain ownership/update");

        before = updater.Gd.Api.Binds;
        updater.ForceImageDirty();
        Assign(updater, kind, assignments); updater.Draw();
        Check.That(updater.Gd.Api.Binds > before, "unchanged setter never clears another category's dirty state");
        before = updater.Gd.Api.DescriptorUpdates;
        Assign(updater, kind, Array.Empty<BufferAssignment>()); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before + 1, "empty setter preserves its prior explicit refresh behavior");
    }

    static void CheckDirectStorageAndPushDescriptors()
    {
        using DescriptorSetUpdater updater = new();
        ShaderCollection shader = new(1, 2, extra: true);
        updater.SetProgram(default, shader, false);
        updater.SetStorageBuffers(default, 0, updater.Gd.BufferManager.Direct);
        updater.Draw();
        int before = updater.Gd.Api.DescriptorUpdates;
        updater.SetStorageBuffers(default, 0, updater.Gd.BufferManager.Direct); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before + (Adapted ? 0 : 1), "direct storage unchanged overload");
        updater.Gd.BufferManager.Direct[1] = new Auto<DisposableBuffer>(new DisposableBuffer(99));
        before = updater.Gd.Api.DescriptorUpdates;
        updater.SetStorageBuffers(default, 0, updater.Gd.BufferManager.Direct); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before + 1, "direct storage changed identity");
        before = updater.Gd.Api.DescriptorUpdates;
        updater.SetStorageBuffers(default, 1, ReadOnlySpan<Auto<DisposableBuffer>>.Empty); updater.Draw();
        Check.That(updater.Gd.Api.DescriptorUpdates == before + 1, "direct empty storage refresh preserved");

        shader = new(0, 1, extra: false) { UsePushDescriptors = true };
        updater.SetProgram(default, shader, false);
        BufferAssignment[] binding = { Assignment() };
        updater.SetUniformBuffers(default, binding); updater.Draw();
        int pushes = updater.Gd.PushDescriptorApi.Pushes;
        updater.SetUniformBuffers(default, binding); updater.Draw();
        Check.That(updater.Gd.PushDescriptorApi.Pushes == pushes, "unchanged push descriptor remains valid");
        updater.Rebind(updater.Gd.BufferManager.Direct[0], 16, 64);
        updater.SetUniformBuffers(default, binding); updater.Draw();
        Check.That(updater.Gd.PushDescriptorApi.Pushes == pushes + 1, "rebind updates push descriptor");
        updater.SignalCommandBufferChange();
        updater.SetUniformBuffers(default, binding); updater.Draw();
        Check.That(updater.Gd.PushDescriptorApi.Pushes == pushes + 2, "new command buffer resets push descriptor sequence");
    }

    static object Measure(string kind)
    {
        using DescriptorSetUpdater updater = new();
        int set = kind == "uniform" || kind == "uniformPush" ? 0 : 1;
        ShaderCollection shader = new(set, 2, extra: true) { UsePushDescriptors = kind == "uniformPush" };
        updater.SetProgram(default, shader, false);
        BufferAssignment[] assignments = { Assignment(), Assignment(slot: 1, handle: 2) };
        for (int i = 0; i < 20000; i++) { Assign(updater, kind, assignments); updater.Draw(); }
        const int samples = 5, perSample = 50000, iterations = samples * perSample;
        int updates = updater.Gd.Api.DescriptorUpdates, binds = updater.Gd.Api.Binds;
        int gets = updater.Gd.BufferManager.Lookups;
        double[] timings = new double[samples];
        long bytes = 0;
        for (int sample = 0; sample < samples; sample++)
        {
            long allocated = GC.GetAllocatedBytesForCurrentThread();
            long begin = Stopwatch.GetTimestamp();
            for (int i = 0; i < perSample; i++) { Assign(updater, kind, assignments); updater.Draw(); }
            long elapsed = Stopwatch.GetTimestamp() - begin;
            bytes += GC.GetAllocatedBytesForCurrentThread() - allocated;
            timings[sample] = elapsed * 1_000_000_000.0 / Stopwatch.Frequency / perSample;
        }
        Array.Sort(timings);
        return new { kind, iterations, warmup = 20000, samples,
                     descriptorUpdates = updater.Gd.Api.DescriptorUpdates - updates,
                     descriptorBinds = updater.Gd.Api.Binds - binds,
                     bufferLookups = updater.Gd.BufferManager.Lookups - gets,
                     medianNanosecondsPerAssignmentAndDraw = timings[samples / 2],
                     bytesPerIteration = bytes / (double)iterations };
    }

    static void Main()
    {
        CheckChangingFields("uniform"); CheckChangingFields("storage");
        CheckInvalidations("uniform"); CheckInvalidations("storage");
        CheckDirectStorageAndPushDescriptors();
        object[] measurements = new[] { "uniform", "storage", "directStorage", "uniformPush" }.Select(Measure).ToArray();
        Console.WriteLine(JsonSerializer.Serialize(new { adapted = Adapted, checks = Check.Count, measurements,
            productionMethodsVerbatim = true, nativeVulkanCallsDoubled = true,
            tieredCompilation = Environment.GetEnvironmentVariable("DOTNET_TieredCompilation") }));
    }
}

namespace Silk.NET.Vulkan
{
    public struct CommandBuffer { }
    public struct Device { }
    public struct PipelineLayout { }
    public enum PipelineBindPoint { Graphics, Compute }
    public enum DescriptorType { UniformBuffer, StorageBuffer }
    public struct Buffer { public ulong Handle; }
    public struct BufferView { public ulong Handle; }
    public struct ImageView { public ulong Handle; }
    public struct Sampler { public ulong Handle; }
    public struct DescriptorSet { public int Id; }
    public struct DescriptorUpdateTemplate { }
    public struct DescriptorBufferInfo { public Buffer Buffer; public ulong Offset, Range; }
    public struct DescriptorImageInfo { public ImageView ImageView; public Sampler Sampler; }
    public static class Vk { public const ulong WholeSize = ulong.MaxValue; }
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
        public ulong LastOffset, LastRange;
        public unsafe void UpdateDescriptorSetWithTemplate(Device device, DescriptorSet set, DescriptorUpdateTemplate template, void* data)
        {
            DescriptorUpdates++;
            ref DescriptorBufferInfo info = ref Unsafe.AsRef<DescriptorBufferInfo>(data);
            LastBuffer = info.Buffer; LastOffset = info.Offset; LastRange = info.Range;
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
        public ShaderCollection(int bufferSet, int count, bool extra)
        {
            for (int i = 0; i < 5; i++) { BindingSegments[i] = Array.Empty<ResourceBindingSegment>(); ClearSegments[i] = Array.Empty<ResourceBindingSegment>(); Templates[i] = new(); }
            BindingSegments[bufferSet] = new[] { new ResourceBindingSegment(0, count, bufferSet == 0 ? ResourceType.UniformBuffer : ResourceType.StorageBuffer, ResourceStages.Vertex, false) };
            if (extra) BindingSegments[4] = new[] { new ResourceBindingSegment(0, 1, ResourceType.TextureAndSampler, ResourceStages.Fragment, true) };
        }
        public bool HasSameLayout(ShaderCollection other) => other != null && other.LayoutId == LayoutId;
        public void UpdateDescriptorCacheCommandBufferIndex(int index) => CommandUpdates++;
        public Auto<DescriptorSetCollection> GetNewDescriptorSetCollection(int set, out bool isNew)
        { NewSets++; isNew = false; return _sets; }
        public DescriptorSetTemplate GetPushDescriptorTemplate(long bindings) => Templates[0];
    }
    sealed class TextureView
    {
        readonly Auto<DisposableImageView> _view = new(new DisposableImageView());
        public Auto<DisposableImageView> GetImageView() => _view;
    }
    sealed class SamplerHolder
    {
        readonly Auto<DisposableSampler> _sampler = new(new DisposableSampler());
        public Auto<DisposableSampler> GetSampler() => _sampler;
    }
    sealed class TextureBuffer { public BufferView GetBufferView(CommandBufferScoped cbs, bool write) => default; }
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
    static class TestConversions { public static DescriptorType Convert(this ResourceType type) => DescriptorType.UniformBuffer; }
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
        private readonly ArrayRef<TextureArray>[] _textureArrayRefs = new ArrayRef<TextureArray>[128];
        private readonly ArrayRef<ImageArray>[] _imageArrayRefs = new ArrayRef<ImageArray>[128];
        private readonly ArrayRef<TextureArray>[] _textureArrayExtraRefs = { new(ShaderStage.Fragment, new TextureArray()) };
        private readonly ArrayRef<ImageArray>[] _imageArrayExtraRefs = { new(ShaderStage.Fragment, new ImageArray()) };
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
        public VulkanRenderer Gd => _gd;
        public void Draw(CommandBufferScoped cbs = default) => UpdateAndBindDescriptorSets(cbs, PipelineBindPoint.Graphics);
        public void Dispose() => _templateUpdater.Dispose();
        // The legacy exceptional Vulkan fallback and individual texture fallback
        // are outside this buffer-path test. Unexpected use fails the test.
        private void UpdateAndBind(CommandBufferScoped cbs, int set, PipelineBindPoint point) => throw new InvalidOperationException("unexpected descriptor fallback");
        private void UpdateAndBindTexturesWithoutTemplate(CommandBufferScoped cbs, ShaderCollection shader, PipelineBindPoint point) => throw new InvalidOperationException("unexpected texture fallback");
    }
}
