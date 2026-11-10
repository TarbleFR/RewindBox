// Production DescriptorSetUpdater members (setters, SetProgram, UpdateAndBindDescriptorSets, the template update, extra
// sets, invalidations) on scripted sequences (adapted from the Core 705 fixture for adapt_extra_set_binds: texture,
// buffer texture and image arrays in extra sets, programs of another layout, Vulkan's disturbance rule). After every draw or dispatch the descriptors the draw would read are
// decoded from the bytes of the set bound at each (bind point, set index) of the current command buffer and checked
// against the resources the script bound (a model kept here); the decoded sequence is printed for the variants to be
// compared. Counts: template writes per set, descriptors written, sets allocated, binds, texture array set lookups.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Check
{
    public static int Count;
    public static void That(bool value, string message)
    {
        Count++;
        if (!value) throw new InvalidOperationException(message);
    }
}

static class Program
{
    public static int Allocations, ArraySetCalls;

    public static int ElementSize(ResourceType type) => type switch
    {
        ResourceType.UniformBuffer or ResourceType.StorageBuffer => Unsafe.SizeOf<DescriptorBufferInfo>(),
        ResourceType.BufferTexture or ResourceType.BufferImage => Unsafe.SizeOf<BufferView>(),
        _ => Unsafe.SizeOf<DescriptorImageInfo>(),
    };

    static BufferHandle H(ulong value) => Unsafe.As<ulong, BufferHandle>(ref value);
    static ResourceBindingSegment Seg(int binding, int count, ResourceType type, bool array = false)
        => new(binding, count, type, ResourceStages.Compute | ResourceStages.Vertex | ResourceStages.Fragment, array);

    // The resources the script bound, per binding: what every draw must read.
    sealed class Model
    {
        public readonly Dictionary<int, (ulong, ulong, ulong)> Uniform = new(), Storage = new();
        public readonly Dictionary<int, (ulong, ulong)> Texture = new();
        public readonly Dictionary<int, TextureBuffer> BufferTexture = new(), BufferImage = new();
        public readonly Dictionary<int, ulong> Image = new();
        public TextureArray Array, BufferArray;
        public ImageArray Images;
        public object Extra; // the array last set at set index 4 (SetTextureArraySeparate/SetImageArraySeparate)
    }

    static int VersionOf(object array) => array is TextureArray t ? t.Version : ((ImageArray)array).Version;

    static void ExtraTextures(TextureArray array)
    {
        _u.SetTextureArraySeparate(_cbs, ShaderStage.Compute, 4, array);
        _m.Extra = array;
    }

    static void ExtraImages(ImageArray array)
    {
        _u.SetImageArraySeparate(_cbs, ShaderStage.Compute, 4, array);
        _m.Extra = array;
    }

    static readonly List<string> Trace = new();
    static CommandBufferScoped _cbs;
    static DescriptorSetUpdater _u;
    static Model _m;

    static void Uniform(int binding, ulong buffer, int offset, int size)
    {
        _u.SetUniformBuffers(default, new[] { new BufferAssignment(binding, new BufferRange(H(buffer), offset, size)) });
        _m.Uniform[binding] = (1000 + buffer, (ulong)offset, (ulong)size);
    }

    static void Storage(int binding, ulong buffer, int offset, int size)
    {
        _u.SetStorageBuffers(default, new[] { new BufferAssignment(binding, new BufferRange(H(buffer), offset, size)) });
        _m.Storage[binding] = (1000 + buffer, (ulong)offset, (ulong)size);
    }

    static void Texture(int binding, TextureView view, SamplerHolder sampler, ShaderStage stage = ShaderStage.Compute)
    {
        _u.SetTextureAndSampler(_cbs, stage, binding, view, sampler);
        _m.Texture[binding] = (view?.Normal.Value.Value.Handle ?? 1, view == null ? 2 : sampler?.Current.Value.Value.Handle ?? 2);
    }

    static void BufferTexture(int binding, TextureBuffer buffer)
    {
        _u.SetTextureAndSampler(_cbs, ShaderStage.Compute, binding, buffer, null);
        _m.BufferTexture[binding] = buffer;
    }

    static void Image(int binding, TextureView view)
    {
        _u.SetImage(_cbs, ShaderStage.Compute, binding, view);
        _m.Image[binding] = view?.Identity.Value.Value.Handle ?? 1;
    }

    static void BufferImage(int binding, TextureBuffer buffer)
    {
        _u.SetImage(_cbs, ShaderStage.Compute, binding, buffer);
        _m.BufferImage[binding] = buffer;
    }

    static void NewCommandBuffer()
    {
        // A new command buffer holds no binding; the pipeline signals the change (PipelineBase.SignalCommandBufferChange).
        _cbs = new CommandBufferScoped { CommandBufferIndex = _cbs.CommandBufferIndex + 1 };
        _u.Gd.Api.Bound.Clear();
        _u.SignalCommandBufferChange();
    }

    static (int writes, int binds, int allocations, long descriptors, int arrays) Counters()
        => (_u.Gd.Api.SetWrites, _u.Gd.Api.Binds, Allocations, _u.Gd.Api.DescriptorsWritten, ArraySetCalls);

    static readonly List<object> Steps = new();

    static void Run(string label, ShaderCollection program, PipelineBindPoint pbp, Action bindings)
    {
        var before = Counters();
        _u.SetProgram(_cbs, program, true);
        bindings?.Invoke();
        _u.UpdateAndBindDescriptorSets(_cbs, pbp);
        Observe(label, pbp);
        var after = Counters();
        Steps.Add(new
        {
            label,
            writes = after.writes - before.writes,
            binds = after.binds - before.binds,
            allocations = after.allocations - before.allocations,
            descriptors = after.descriptors - before.descriptors,
            arraySetLookups = after.arrays - before.arrays,
        });
    }

    static unsafe void Observe(string label, PipelineBindPoint pbp)
    {
        ShaderCollection program = _u.Current;
        var text = new StringBuilder(label).Append(':');
        for (int set = 0; set < 4; set++)
        {
            ResourceBindingSegment[] segments = program.BindingSegments[set];
            if (segments.Length == 0) continue;
            Check.That(_u.Gd.Api.Bound.TryGetValue((pbp, (uint)set), out ulong handle), $"{label}: set {set} bound in this command buffer");
            byte[] bytes = _u.Gd.Api.Contents[handle];
            Check.That(bytes.Length == program.Templates[set].Size, $"{label}: set {set} written for this program's template");
            int offset = 0;
            foreach (ResourceBindingSegment segment in segments)
            {
                for (int i = 0; i < segment.Count; i++)
                {
                    int binding = segment.Binding + i;
                    string value;
                    if (segment.Type is ResourceType.UniformBuffer or ResourceType.StorageBuffer)
                    {
                        DescriptorBufferInfo info = MemoryMarshal.Read<DescriptorBufferInfo>(bytes.AsSpan(offset));
                        var expected = (segment.Type == ResourceType.UniformBuffer ? _m.Uniform : _m.Storage)
                            .GetValueOrDefault(binding, (1UL, 0UL, Vk.WholeSize));
                        Check.That((info.Buffer.Handle, info.Offset, info.Range) == expected,
                            $"{label}: set {set} binding {binding} buffer {info.Buffer.Handle}+{info.Offset}/{info.Range}, expected {expected}");
                        value = $"{info.Buffer.Handle}+{info.Offset}/{info.Range}";
                    }
                    else if (segment.Type is ResourceType.BufferTexture or ResourceType.BufferImage)
                    {
                        BufferView view = MemoryMarshal.Read<BufferView>(bytes.AsSpan(offset));
                        var source = segment.Type == ResourceType.BufferTexture ? _m.BufferTexture : _m.BufferImage;
                        ulong expected = source.TryGetValue(binding, out TextureBuffer buffer) ? buffer.ViewHandle : 0;
                        Check.That(view.Handle == expected, $"{label}: set {set} binding {binding} buffer view {view.Handle}, expected {expected} (current view)");
                        value = $"bv{view.Handle}";
                    }
                    else if (segment.Type == ResourceType.Image)
                    {
                        DescriptorImageInfo info = MemoryMarshal.Read<DescriptorImageInfo>(bytes.AsSpan(offset));
                        ulong expected = _m.Image.GetValueOrDefault(binding, 1UL);
                        Check.That(info.ImageView.Handle == expected, $"{label}: set {set} binding {binding} image {info.ImageView.Handle}, expected {expected}");
                        value = $"i{info.ImageView.Handle}";
                    }
                    else
                    {
                        DescriptorImageInfo info = MemoryMarshal.Read<DescriptorImageInfo>(bytes.AsSpan(offset));
                        var expected = _m.Texture.GetValueOrDefault(binding, (1UL, 2UL));
                        Check.That((info.ImageView.Handle, info.Sampler.Handle) == expected,
                            $"{label}: set {set} binding {binding} texture {info.ImageView.Handle}/{info.Sampler.Handle}, expected {expected}");
                        value = $"t{info.ImageView.Handle}/s{info.Sampler.Handle}";
                    }
                    text.Append(' ').Append(set).Append('.').Append(binding).Append('=').Append(value);
                    offset += ElementSize(segment.Type);
                }
            }
        }
        if (program.BindingSegments.Length > 4 && program.BindingSegments[4].Length != 0)
        {
            Check.That(_u.Gd.Api.Bound.TryGetValue((pbp, 4u), out ulong handle), $"{label}: array set bound");
            Check.That(_u.Gd.Api.BoundLayout[(pbp, 4u)] == program.PipelineLayout.Handle, $"{label}: array set bound with this program's layout");
            (object array, int version) = ArraySets.Held[handle];
            Check.That(ReferenceEquals(array, _m.Extra), $"{label}: the array set bound is the array set at index 4");
            Check.That(version == VersionOf(array), $"{label}: the array set bound holds version {version}, current {VersionOf(array)}");
            text.Append(" 4=").Append(array is ImageArray ? "image" : ReferenceEquals(array, _m.BufferArray) ? "buffer" : "texture").Append('v').Append(version);
        }
        Trace.Add(text.ToString());
    }

    static void Main()
    {
        _u = new DescriptorSetUpdater();
        _m = new Model { Array = new TextureArray(), BufferArray = new TextureArray(), Images = new ImageArray() };
        _cbs = new CommandBufferScoped { CommandBufferIndex = 0 };
        var compute = PipelineBindPoint.Compute;
        var graphics = PipelineBindPoint.Graphics;
        var empty = Array.Empty<ResourceBindingSegment>();

        ShaderCollection g1 = new(1, new[] { new[] { Seg(1, 3, ResourceType.UniformBuffer) }, new[] { Seg(16, 2, ResourceType.StorageBuffer) },
            new[] { Seg(64, 3, ResourceType.TextureAndSampler) }, empty });
        ShaderCollection g2 = new(1, new[] { new[] { Seg(1, 2, ResourceType.UniformBuffer) }, empty,
            new[] { Seg(64, 2, ResourceType.TextureAndSampler) }, empty });
        ShaderCollection c1 = new(2, new[] { new[] { Seg(0, 2, ResourceType.UniformBuffer) }, new[] { Seg(0, 3, ResourceType.StorageBuffer) },
            new[] { Seg(0, 4, ResourceType.TextureAndSampler) }, new[] { Seg(0, 2, ResourceType.Image) },
            new[] { Seg(0, 1, ResourceType.TextureAndSampler, array: true) } });
        ShaderCollection c2 = new(2, new[] { new[] { Seg(0, 1, ResourceType.UniformBuffer) }, empty,
            new[] { Seg(0, 2, ResourceType.TextureAndSampler) }, empty });
        ShaderCollection cb = new(3, new[] { empty, empty,
            new[] { Seg(0, 1, ResourceType.TextureAndSampler), Seg(32, 1, ResourceType.BufferTexture) },
            new[] { Seg(16, 1, ResourceType.BufferImage) } });

        TextureView a = new(10), b = new(11), c = new(12), d = new(13), aOtherFormat = new(20);
        SamplerHolder s1 = new(30), s2 = new(31);
        TextureBuffer tb = new(40), ib = new(50);

        Run("graphics first draw", g1, graphics, () =>
        {
            Uniform(1, 1, 0, 256); Uniform(2, 2, 256, 256); Uniform(3, 1, 512, 64); Storage(16, 3, 0, 4096); Storage(17, 3, 4096, 4096);
            Texture(64, a, s1, ShaderStage.Fragment); Texture(65, b, s1, ShaderStage.Fragment); Texture(66, c, s2, ShaderStage.Fragment);
        });
        Run("compute first dispatch", c1, compute, () =>
        {
            Uniform(0, 4, 0, 256); Uniform(1, 4, 256, 256); Storage(0, 5, 0, 1024); Storage(1, 5, 1024, 1024); Storage(2, 6, 0, 512);
            Texture(0, a, s1); Texture(1, b, s1); Texture(2, c, s2); Texture(3, d, s2); Image(0, a); Image(1, b);
            ExtraTextures(_m.Array);
        });
        Run("same compute program, nothing changed", c1, compute, null);
        Run("same compute program, uniform offset", c1, compute, () => Uniform(1, 4, 512, 256));
        Run("same compute program, identical assignment", c1, compute, () => Uniform(1, 4, 512, 256));
        Run("same compute program, texture changed", c1, compute, () => Texture(1, c, s1));
        Run("same compute program, sampler changed", c1, compute, () => Texture(1, c, s2));
        Run("same compute program, slot reused with another texture", c1, compute, () => Texture(2, a, s2));
        Run("same compute program, storage range", c1, compute, () => Storage(2, 6, 0, 256));
        Run("same compute program, storage offset", c1, compute, () => Storage(2, 6, 256, 256));
        Run("same compute program, texture of another format", c1, compute, () => Texture(0, aOtherFormat, s1));
        Run("same compute program, image changed", c1, compute, () => Image(1, c));
        Run("same compute program, texture unbound", c1, compute, () => Texture(3, null, null));
        Run("same compute program, texture array element changed", c1, compute, () => { _m.Array.Change(); _u.ForceTextureDirty(); });
        Run("same compute program, uniform only after the array change", c1, compute, () => Uniform(0, 4, 768, 256));
        Run("same compute program, storage only", c1, compute, () => Storage(0, 5, 2048, 1024));
        _u.Rebind(_u.Gd.BufferManager.Buffers[4], 0, 16);
        Run("same compute program after an overlapping buffer invalidation", c1, compute, null);
        _u.Rebind(_u.Gd.BufferManager.Buffers[4], 100000, 16);
        Run("same compute program after a disjoint buffer write", c1, compute, null);
        Run("other compute program, same layout", c2, compute, null);
        Run("first compute program again", c1, compute, null);
        Run("graphics again after compute", g1, graphics, () => Texture(64, a, s1, ShaderStage.Fragment));
        Run("same graphics program, nothing changed", g1, graphics, null);
        Run("other graphics program, same layout", g2, graphics, null);
        Run("same graphics program (second), uniform", g2, graphics, () => Uniform(2, 2, 768, 256));
        NewCommandBuffer();
        Run("new command buffer, same program", g2, graphics, null);
        Run("new command buffer, same program again", g2, graphics, null);
        Auto<DisposableBuffer> from = _u.Gd.BufferManager.Buffers[2], to = new(new DisposableBuffer(5000));
        _u.SwapBuffer(from, to);
        foreach (int key in new List<int>(_m.Uniform.Keys))
            if (_m.Uniform[key].Item1 == 1002) _m.Uniform[key] = (5000, _m.Uniform[key].Item2, _m.Uniform[key].Item3);
        // PipelineBase.SwapBuffer signals the command buffer change after the descriptor swap.
        _u.SignalCommandBufferChange();
        Run("same program after a buffer replacement", g2, graphics, null);
        Run("buffer texture program", cb, compute, () => { Texture(0, a, s1); BufferTexture(32, tb); BufferImage(16, ib); });
        tb.ViewHandle = 41;
        ib.ViewHandle = 51;
        Run("same buffer texture program, views changed without a setter", cb, compute, null);
        Run("same buffer texture program, nothing changed", cb, compute, null);
        Run("back to the array program", c1, compute, null);
        Run("array program again", c1, compute, null);
        Run("array program, uniform only", c1, compute, () => Uniform(1, 4, 1024, 256));

        // RewindBox (adapt_extra_set_binds): a program of another layout with its own array set, then back; a buffer
        // texture array and an image array in the extra set; their element changes; uniform-only updates of each.
        ShaderCollection c3 = new(9, new[] { new[] { Seg(0, 1, ResourceType.UniformBuffer) }, empty, empty, empty,
            new[] { Seg(0, 1, ResourceType.TextureAndSampler, array: true) } });
        ShaderCollection cbuf = new(10, new[] { new[] { Seg(0, 1, ResourceType.UniformBuffer) }, empty, empty, empty,
            new[] { Seg(0, 1, ResourceType.BufferTexture, array: true) } });
        ShaderCollection cimg = new(11, new[] { new[] { Seg(0, 1, ResourceType.UniformBuffer) }, empty, empty, empty,
            new[] { Seg(0, 1, ResourceType.Image, array: true) } });
        Run("program of another layout with an array set", c3, compute, () => Uniform(0, 7, 0, 256));
        Run("another layout, uniform only", c3, compute, () => Uniform(0, 7, 256, 256));
        Run("array program after another layout", c1, compute, null);
        Run("array program after another layout, uniform only", c1, compute, () => Uniform(1, 4, 1280, 256));
        Run("buffer texture array program", cbuf, compute, () => { Uniform(0, 8, 0, 256); ExtraTextures(_m.BufferArray); });
        Run("buffer texture array program, uniform only", cbuf, compute, () => Uniform(0, 8, 256, 256));
        Run("buffer texture array element changed", cbuf, compute, () => { _m.BufferArray.Change(); _u.ForceTextureDirty(); });
        Run("image array program", cimg, compute, () => { Uniform(0, 9, 0, 256); ExtraImages(_m.Images); });
        Run("image array program, uniform only", cimg, compute, () => Uniform(0, 9, 256, 256));
        Run("image array element changed", cimg, compute, () => { _m.Images.Change(); _u.ForceImageDirty(); });
        Run("image array program, uniform only after the change", cimg, compute, () => Uniform(0, 9, 512, 256));
        Run("image array program, a plain texture flag", cimg, compute, () => _u.ForceTextureDirty());
        NewCommandBuffer();
        Run("image array program, new command buffer", cimg, compute, null);
        Run("image array program, new command buffer, uniform only", cimg, compute, () => Uniform(0, 9, 768, 256));
        Run("back to the texture array program", c1, compute, () => ExtraTextures(_m.Array));
        Run("texture array program, uniform only", c1, compute, () => Uniform(1, 4, 1536, 256));

        // Repeated dispatches of one program, as ComputeClass.Dispatch sets it before each: a new uniform offset each
        // time (constants per dispatch), then nothing changed.
        long start = Stopwatch.GetTimestamp();
        var before = Counters();
        for (int i = 0; i < 2000; i++)
        {
            _u.SetProgram(_cbs, c1, true);
            Uniform(1, 4, 256 * (i % 64), 256);
            _u.UpdateAndBindDescriptorSets(_cbs, compute);
            if (i % 97 == 0) Observe("loop uniform " + i, compute);
        }
        var afterUniform = Counters();
        double uniformMs = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
        start = Stopwatch.GetTimestamp();
        for (int i = 0; i < 2000; i++)
        {
            _u.SetProgram(_cbs, c1, true);
            _u.UpdateAndBindDescriptorSets(_cbs, compute);
            if (i % 97 == 0) Observe("loop unchanged " + i, compute);
        }
        var afterUnchanged = Counters();
        double unchangedMs = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
        start = Stopwatch.GetTimestamp();
        for (int i = 0; i < 2000; i++)
        {
            _u.SetProgram(_cbs, c1, true);
            Storage(2, 6, 64 * (i % 32), 256);
            _u.UpdateAndBindDescriptorSets(_cbs, compute);
            if (i % 97 == 0) Observe("loop storage " + i, compute);
        }
        var afterStorage = Counters();
        double storageMs = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
        start = Stopwatch.GetTimestamp();
        for (int i = 0; i < 2000; i++)
        {
            _u.SetProgram(_cbs, c1, true);
            if (i % 8 == 0) { _m.Array.Change(); _u.ForceTextureDirty(); }
            Uniform(1, 4, 256 * (i % 64), 256);
            _u.UpdateAndBindDescriptorSets(_cbs, compute);
            if (i % 97 == 0 || i % 8 == 0) Observe("loop array every 8 " + i, compute);
        }
        var afterMixed = Counters();
        double mixedMs = Stopwatch.GetElapsedTime(start).TotalMilliseconds;

        object Loop((int writes, int binds, int allocations, long descriptors, int arrays) x, (int writes, int binds, int allocations, long descriptors, int arrays) y, double ms)
            => new { writes = y.writes - x.writes, binds = y.binds - x.binds, allocations = y.allocations - x.allocations,
                     descriptors = y.descriptors - x.descriptors, arraySetLookups = y.arrays - x.arrays, ms = Math.Round(ms, 2) };

        var trace = string.Join("\n", Trace);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            checks = Check.Count,
            traceSha256 = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(trace))).ToLowerInvariant(),
            observations = Trace.Count,
            steps = Steps,
            loops = new { uniformEachDispatch = Loop(before, afterUniform, uniformMs), unchanged = Loop(afterUniform, afterUnchanged, unchangedMs),
                          storageEachDispatch = Loop(afterUnchanged, afterStorage, storageMs),
                          arrayChangeEvery8 = Loop(afterStorage, afterMixed, mixedMs) },
            disturbed = _u.Gd.Api.Disturbed,
            writesBySet = _u.Gd.Api.WritesBySet,
            renderDetail = new { RenderDetail.DescriptorSetWrites, RenderDetail.DescriptorsWritten, RenderDetail.ProgramSets, RenderDetail.SameProgramSets },
        }));
        Console.WriteLine("TRACE\n" + trace);
    }
}
