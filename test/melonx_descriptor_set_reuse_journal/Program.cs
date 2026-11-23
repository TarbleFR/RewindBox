// Production DescriptorSetUpdater members (setters, SetProgram, UpdateAndBindDescriptorSets, the template update and its
// writer, the array sets, the invalidations; in the candidate also the measurement's members and journal) on scripted
// sequences and on a stream shaped like the IPA 822 Hogwarts Legacy window (85 frames, 145 191 draws, 5 476 dispatches in
// 571 runs, about 18 500 program changes, 1 241 command buffers). After every draw or dispatch the descriptors it reads
// are decoded from the bytes of the set bound at each (bind point, set index) of the command buffer, with the layout it
// was bound with, and checked against the resources the script bound; every scalar set bound must have been written in
// this submission. The decoded values and every write and bind in call order are hashed for the variants to be compared.
// Arguments: verify|time, the array policy (on|off), the candidate's sampling (one command buffer start in N measured),
// and for timing the repeats. Timing mode: the same streams with counting doubles only, the time inside
// UpdateAndBindDescriptorSets.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Check
{
    public static long Count;
    public static void That(bool value, string message)
    {
        Count++;
        if (!value) throw new InvalidOperationException(message);
    }
}

static class Program
{
    public const int CommandBuffers = 16;
    public static readonly int[] Submissions = new int[CommandBuffers];
    public static long ResourceGets, ArraySetCalls, SetsTaken, SetsAllocated;

    public static int ElementSize(ResourceType type) => type switch
    {
        ResourceType.UniformBuffer or ResourceType.StorageBuffer => Unsafe.SizeOf<DescriptorBufferInfo>(),
        ResourceType.BufferTexture or ResourceType.BufferImage => Unsafe.SizeOf<BufferView>(),
        _ => Unsafe.SizeOf<DescriptorImageInfo>(),
    };

    static BufferHandle H(ulong value) => Unsafe.As<ulong, BufferHandle>(ref value);
    static ResourceBindingSegment Seg(int binding, int count, ResourceType type, bool array = false)
        => new(binding, count, type, ResourceStages.Compute | ResourceStages.Vertex | ResourceStages.Fragment, array);

    // ---- The command buffer, as PipelineBase and CommandBufferPool hold it. ----
    static VulkanRenderer _gd;
    static DescriptorSetUpdater _u, _helper;
    static CommandBufferScoped _cbs;
    static int _cbIndex;
    static bool _pipelineBound;
    static readonly HashSet<ulong> _writtenThisSubmission = new();

    public static void CheckCommandBuffer(CommandBuffer command)
        => Check.That(command.Handle == _cbs.CommandBuffer.Handle, "a bind into the command buffer being recorded");

    public static void NoteWrite(ulong set)
        => Check.That(_writtenThisSubmission.Add(set), $"set {set} written twice in one submission");

    public static void NoteBound(ulong set)
        => Check.That(set >= 1_000_000 || _writtenThisSubmission.Contains(set), $"set {set} bound but not written in this submission");

    static void NewCommandBuffer()
    {
        // The pool's next command buffer (reused handles, one more submission each time), and the pipeline's change signal.
        _cbIndex = (_cbIndex + 1) % CommandBuffers;
        Submissions[_cbIndex]++;
        _cbs = new CommandBufferScoped { CommandBuffer = new CommandBuffer((nint)(0x1000 + _cbIndex)), CommandBufferIndex = _cbIndex };
        _gd.Api.NewCommandBuffer();
        _writtenThisSubmission.Clear();
        _u.SignalCommandBufferChange();
        _pipelineBound = false;
    }

    // ---- What the script bound: what every draw and dispatch must read. The updater's arrays are shared by compute and
    // graphics, so is this. ----
    sealed class Model
    {
        public readonly Dictionary<int, (ulong, ulong, ulong)> Uniform = new(), Storage = new();
        public readonly Dictionary<int, (ulong, ulong)> Texture = new();
        public readonly Dictionary<int, TextureBuffer> BufferTexture = new(), BufferImage = new();
        public readonly Dictionary<int, ulong> Image = new();
        public readonly Dictionary<int, TextureArray> Arrays = new();
    }

    static Model _m;
    static bool _verify;
    static IncrementalHash _hash;
    static long _observations;
    static readonly byte[] _record = new byte[64 * 1024];

    static void Uniforms(params (int binding, ulong buffer, int offset, int size)[] list)
    {
        var assignments = new BufferAssignment[list.Length];
        for (int i = 0; i < list.Length; i++)
        {
            var (binding, buffer, offset, size) = list[i];
            assignments[i] = new BufferAssignment(binding, new BufferRange(H(buffer), offset, size));
            if (_verify) _m.Uniform[binding] = (1000 + buffer, (ulong)offset, (ulong)size);
        }
        _u.SetUniformBuffers(default, assignments);
    }

    static void Storages(params (int binding, ulong buffer, int offset, int size)[] list)
    {
        var assignments = new BufferAssignment[list.Length];
        for (int i = 0; i < list.Length; i++)
        {
            var (binding, buffer, offset, size) = list[i];
            assignments[i] = new BufferAssignment(binding, new BufferRange(H(buffer), offset, size));
            if (_verify) _m.Storage[binding] = (1000 + buffer, (ulong)offset, (ulong)size);
        }
        _u.SetStorageBuffers(default, assignments);
    }

    static void Texture(int binding, TextureView view, SamplerHolder sampler, ShaderStage stage = ShaderStage.Fragment)
    {
        _u.SetTextureAndSampler(_cbs, stage, binding, view, sampler);
        if (_verify) _m.Texture[binding] = (view?.Normal.Value.Value.Handle ?? 1, view == null ? 2 : sampler?.Current.Value.Value.Handle ?? 2);
    }

    static void BufferTexture(int binding, TextureBuffer buffer)
    {
        _u.SetTextureAndSampler(_cbs, ShaderStage.Compute, binding, buffer, null);
        if (_verify) _m.BufferTexture[binding] = buffer;
    }

    static void Image(int binding, TextureView view, ShaderStage stage = ShaderStage.Compute)
    {
        _u.SetImage(_cbs, stage, binding, view);
        if (_verify) _m.Image[binding] = view?.Identity.Value.Value.Handle ?? 1;
    }

    static void ArraySet(int setIndex, TextureArray array, ShaderStage stage)
    {
        _u.SetTextureArraySeparate(_cbs, stage, setIndex, array);
        if (_verify) _m.Arrays[setIndex] = array;
    }

    // ---- Counters and timing. ----
    static long _updateTicks, _ops, _draws, _dispatches, _programSets;

    static void Update(PipelineBindPoint pbp)
    {
        long start = Stopwatch.GetTimestamp();
        _u.UpdateAndBindDescriptorSets(_cbs, pbp);
        _updateTicks += Stopwatch.GetTimestamp() - start;
        _ops++;
        _pipelineBound = true;
        if (_verify) Observe(pbp);
    }

    static void SetProgram(ShaderCollection program)
    {
        _u.SetProgram(_cbs, program, _pipelineBound);
        _programSets++;
    }

    static unsafe void Observe(PipelineBindPoint pbp)
    {
        ShaderCollection program = _u.Current;
        int length = 0;
        void Put(ulong value)
        {
            MemoryMarshal.Write(_record.AsSpan(length), in value);
            length += 8;
        }
        Put((ulong)pbp);
        for (int set = 0; set < program.BindingSegments.Length; set++)
        {
            ResourceBindingSegment[] segments = program.BindingSegments[set];
            if (segments.Length == 0) continue;
            Check.That(_gd.Api.Bound.TryGetValue((pbp, (uint)set), out var bound), $"{program.Name}: set {set} bound in this command buffer");
            Check.That(bound.Layout == program.PipelineLayout.Handle, $"{program.Name}: set {set} bound with this program's layout");
            Put((ulong)set);
            if (set >= 4)
            {
                TextureArray array = _m.Arrays[set];
                Check.That(array.VersionOfSet.TryGetValue(bound.Set, out int version) && version == array.Version,
                    $"{program.Name}: the array set bound holds version {version}, current {array.Version}");
                Put((ulong)version);
                continue;
            }
            byte[] bytes = _gd.Api.Contents[bound.Set];
            Check.That(bytes.Length == program.Templates[set].Size, $"{program.Name}: set {set} written for this program's template");
            int offset = 0;
            foreach (ResourceBindingSegment segment in segments)
            {
                for (int i = 0; i < segment.Count; i++)
                {
                    int binding = segment.Binding + i;
                    if (segment.Type is ResourceType.UniformBuffer or ResourceType.StorageBuffer)
                    {
                        DescriptorBufferInfo info = MemoryMarshal.Read<DescriptorBufferInfo>(bytes.AsSpan(offset));
                        var expected = (segment.Type == ResourceType.UniformBuffer ? _m.Uniform : _m.Storage)
                            .GetValueOrDefault(binding, (1UL, 0UL, Vk.WholeSize));
                        Check.That((info.Buffer.Handle, info.Offset, info.Range) == expected,
                            $"{program.Name}: set {set} binding {binding} buffer {info.Buffer.Handle}+{info.Offset}/{info.Range}, expected {expected}");
                        Put(info.Buffer.Handle); Put(info.Offset); Put(info.Range);
                    }
                    else if (segment.Type is ResourceType.BufferTexture or ResourceType.BufferImage)
                    {
                        BufferView view = MemoryMarshal.Read<BufferView>(bytes.AsSpan(offset));
                        var source = segment.Type == ResourceType.BufferTexture ? _m.BufferTexture : _m.BufferImage;
                        ulong expected = source.TryGetValue(binding, out TextureBuffer buffer) ? buffer.ViewHandle : 0;
                        Check.That(view.Handle == expected, $"{program.Name}: set {set} binding {binding} buffer view {view.Handle}, expected {expected}");
                        Put(view.Handle);
                    }
                    else if (segment.Type == ResourceType.Image)
                    {
                        DescriptorImageInfo info = MemoryMarshal.Read<DescriptorImageInfo>(bytes.AsSpan(offset));
                        ulong expected = _m.Image.GetValueOrDefault(binding, 1UL);
                        Check.That(info.ImageView.Handle == expected, $"{program.Name}: set {set} binding {binding} image {info.ImageView.Handle}, expected {expected}");
                        Put(info.ImageView.Handle);
                    }
                    else
                    {
                        DescriptorImageInfo info = MemoryMarshal.Read<DescriptorImageInfo>(bytes.AsSpan(offset));
                        var expected = _m.Texture.GetValueOrDefault(binding, (1UL, 2UL));
                        Check.That((info.ImageView.Handle, info.Sampler.Handle) == expected,
                            $"{program.Name}: set {set} binding {binding} texture {info.ImageView.Handle}/{info.Sampler.Handle}, expected {expected}");
                        Put(info.ImageView.Handle); Put(info.Sampler.Handle);
                    }
                    offset += ElementSize(segment.Type);
                }
            }
        }
        _hash.AppendData(_record, 0, length);
        _observations++;
    }

    // ---- Scripted steps: one effect each, counted. ----
    static readonly List<object> Steps = new();
    static readonly List<string> StepTrace = new();

    static (long writes, long binds, long descriptors, long taken) Counters()
        => (_gd.Api.SetWrites, _gd.Api.Binds, _gd.Api.DescriptorsWritten, SetsTaken);

    static void Step(string label, ShaderCollection program, PipelineBindPoint pbp, Action bindings)
    {
        var before = Counters();
        long hashBefore = _observations;
        if (program != null) SetProgram(program);
        bindings?.Invoke();
        Update(pbp);
        var after = Counters();
        Steps.Add(new { label, writes = after.writes - before.writes, binds = after.binds - before.binds,
                        descriptors = after.descriptors - before.descriptors, setsTaken = after.taken - before.taken });
    }

    static void Helper(ShaderCollection program, TextureView view, SamplerHolder sampler, bool mainCommandBuffer)
    {
        // A helper shader: its own updater; on the main command buffer, then the main pipeline is restored (Restore:
        // SignalCommandBufferChange); otherwise after a flush, on a command buffer of its own.
        if (!mainCommandBuffer) NewCommandBuffer();
        _helper.SignalCommandBufferChange();
        _helper.SetProgram(_cbs, program, false);
        _helper.SetUniformBuffers(default, new[] { new BufferAssignment(1, new BufferRange(H(900), 0, 16)) });
        _helper.SetTextureAndSampler(_cbs, ShaderStage.Fragment, 0, view, sampler);
        _helper.UpdateAndBindDescriptorSets(_cbs, PipelineBindPoint.Graphics);
        if (mainCommandBuffer)
        {
            _u.SignalCommandBufferChange();
            _pipelineBound = false;
        }
        else
        {
            NewCommandBuffer();
        }
    }

    static void Scripted()
    {
        var compute = PipelineBindPoint.Compute;
        var graphics = PipelineBindPoint.Graphics;
        var empty = Array.Empty<ResourceBindingSegment>();
        TestLayout la = new(1), lb = new(2), lc = new(3), lh = new(4), lt = new(5);
        ShaderCollection a = new("A", la, false, new[] { new[] { Seg(0, 1, ResourceType.UniformBuffer), Seg(1, 3, ResourceType.UniformBuffer) },
            new[] { Seg(0, 2, ResourceType.StorageBuffer) }, new[] { Seg(64, 3, ResourceType.TextureAndSampler) }, empty,
            new[] { Seg(0, 1, ResourceType.TextureAndSampler, array: true) } });
        ShaderCollection b = new("B", lb, false, new[] { new[] { Seg(0, 1, ResourceType.UniformBuffer), Seg(1, 2, ResourceType.UniformBuffer) },
            empty, new[] { Seg(64, 2, ResourceType.TextureAndSampler) }, empty });
        ShaderCollection c = new("C", lc, true, new[] { new[] { Seg(0, 2, ResourceType.UniformBuffer) }, new[] { Seg(0, 3, ResourceType.StorageBuffer) },
            new[] { Seg(0, 2, ResourceType.TextureAndSampler) }, new[] { Seg(0, 1, ResourceType.Image) } });
        ShaderCollection t = new("T", lt, true, new[] { empty, empty,
            new[] { Seg(0, 1, ResourceType.TextureAndSampler), Seg(32, 1, ResourceType.BufferTexture) }, empty });
        ShaderCollection h = new("H", lh, false, new[] { new[] { Seg(1, 1, ResourceType.UniformBuffer) }, empty,
            new[] { Seg(0, 1, ResourceType.TextureAndSampler) }, empty });
        TextureView v1 = new(10), v2 = new(11), v3 = new(12), v4 = new(13);
        SamplerHolder s1 = new(30), s2 = new(31);
        TextureArray bindless = new();
        TextureBuffer tb = new(40);

        void ABindings(int objectOffset)
        {
            Uniforms((0, 1, 0, 256), (1, 2, 0, 256), (2, 3, 512, 256), (3, 4, objectOffset, 256));
            Storages((0, 5, 0, 1024), (1, 5, 1024, 1024));
            Texture(64, v1, s1); Texture(65, v2, s1); Texture(66, v3, s2);
            ArraySet(4, bindless, ShaderStage.Fragment);
        }

        Step("graphics A first draw", a, graphics, () => ABindings(0));
        Step("A again, object constants moved", null, graphics, () => Uniforms((3, 4, 256, 256)));
        Step("A again, identical assignment", null, graphics, () => Uniforms((3, 4, 256, 256)));
        Step("A again, empty uniform assignment", null, graphics, () => Uniforms());
        Step("A again, bindless element changed", null, graphics, () => { bindless.Change(); _u.ForceTextureDirty(); });
        Step("A again, texture array set dirty, array unchanged", null, graphics, () => _u.ForceTextureDirty());
        _u.Rebind(_gd.BufferManager.Buffers[2], 0, 16);
        Step("A again after a buffer write over a bound uniform buffer", null, graphics, null);
        Step("compute C first dispatch", c, compute, () =>
        {
            Uniforms((0, 6, 0, 256), (1, 6, 256, 256)); Storages((0, 7, 0, 4096), (1, 7, 4096, 4096), (2, 8, 0, 512));
            Texture(0, v1, s1, ShaderStage.Compute); Texture(1, v4, s2, ShaderStage.Compute); Image(0, v2);
        });
        Step("compute C again, same bindings", c, compute, null);
        Step("compute C again, constants moved", c, compute, () => Uniforms((1, 6, 512, 256)));
        Step("graphics A after compute, bindings sent again", a, graphics, () => ABindings(256));
        Step("compute C after graphics, bindings sent again", c, compute, () =>
        {
            Uniforms((0, 6, 0, 256), (1, 6, 512, 256)); Storages((0, 7, 0, 4096), (1, 7, 4096, 4096), (2, 8, 0, 512));
            Texture(0, v1, s1, ShaderStage.Compute); Texture(1, v4, s2, ShaderStage.Compute); Image(0, v2);
        });
        Step("graphics A after compute, a texture changed", a, graphics, () => { ABindings(256); Texture(65, v4, s1); });
        Step("graphics B (another layout)", b, graphics, () =>
        {
            Uniforms((0, 1, 0, 256), (1, 2, 0, 256), (2, 4, 768, 256)); Texture(64, v1, s1); Texture(65, v2, s2);
        });
        Step("graphics A again (A B A), nothing of A changed", a, graphics, () => { ABindings(256); Texture(65, v4, s1); });
        Step("graphics B again (B A B), B's object constants moved", b, graphics, () =>
        {
            Uniforms((0, 1, 0, 256), (1, 2, 0, 256), (2, 4, 1024, 256)); Texture(64, v1, s1); Texture(65, v2, s2);
        });
        Step("graphics A again, its earlier textures back", a, graphics, () => { ABindings(256); Texture(65, v4, s1); });
        Helper(h, v1, s1, mainCommandBuffer: true);
        Step("graphics A after a helper shader on the main command buffer", a, graphics, () => { ABindings(256); Texture(65, v4, s1); });
        Helper(h, v1, s1, mainCommandBuffer: false);
        Step("graphics A on the command buffer after a helper's flush", a, graphics, () => { ABindings(256); Texture(65, v4, s1); });
        NewCommandBuffer();
        Step("graphics A on a new command buffer", a, graphics, () => { ABindings(256); Texture(65, v4, s1); });
        Step("graphics A again on it, nothing changed", a, graphics, null);
        for (int i = 0; i < CommandBuffers - 1; i++) NewCommandBuffer();
        Step("graphics A on the same command buffer handle, next submission", a, graphics, () => { ABindings(256); Texture(65, v4, s1); });
        Step("buffer texture program", t, compute, () => { Texture(0, v1, s1, ShaderStage.Compute); BufferTexture(32, tb); });
        Step("buffer texture program set again, view unchanged", t, compute, null);
        tb.ViewHandle = 41;
        Step("buffer texture program set again, view changed without a setter", t, compute, null);
    }

    // ---- The stream shaped like the IPA 822 window. ----
    // Per frame: 1 708 draws in passes of 213 draws over 8 programs, a program change on 10.9 % of the draws (30 % of them
    // back to the previous program, which keeps its material half of the time), the object's constants moved on 77 %, the
    // material on 73 % of the others, storage on 65 % of the draws of programs with storage, a bindless element changed
    // under 2.4 % of the draws of programs with an array set, 7 compute runs of about 9.6 dispatches (one program again
    // 60 % of the time; constants moved 80 %, storage 50 %, textures 40 %), the graphics bindings sent again after each
    // run, a helper shader every 1 300 draws (on the main command buffer or after a flush), a new command buffer every 121
    // operations. The control then writes 0.93 / 0.25 / 0.71 / 0.05 sets per operation (window: 0.89 / 0.26 / 0.73 / 0.05)
    // and 19 descriptors per set (window: 21). These repeat rates are the model's, not measures. "No repeat": every set
    // marked dirty holds descriptors never bound before (the candidate's worst case).
    sealed class GProgram
    {
        public ShaderCollection Program;
        public int Vertex, Fragment, Storage, VertexTextures, FragmentTextures, Images;
        public bool Array;
        public int Material;
        public int[] Materials;
    }

    sealed class CProgram
    {
        public ShaderCollection Program;
        public int Uniforms, Storages, Textures, Images;
        public int Constants, StorageOffset, TextureBase;
    }

    sealed class StreamSpec
    {
        public string Name;
        public int Frames = 85, DrawsPerFrame = 1708, RunsPerFrame = 7;
        public double DispatchesPerRun = 9.6;
        public double Switch = 0.109, Return = 0.3, KeepMaterialOnReturn = 0.5, ObjectChange = 0.77, MaterialChange = 0.73;
        public double StorageChange = 0.65, ArrayChange = 0.024, ComputeSame = 0.6, ComputeConstants = 0.8, ComputeStorage = 0.5,
            ComputeTextures = 0.4;
        public int OpsPerCommandBuffer = 121, HelperEvery = 1300;
        public bool Fresh;
    }

    static void RunStream(StreamSpec spec, int seed)
    {
        var random = new Random(seed);
        var graphics = PipelineBindPoint.Graphics;
        var computePoint = PipelineBindPoint.Compute;
        var empty = Array.Empty<ResourceBindingSegment>();
        int layoutId = 100;
        var views = Enumerable.Range(0, 4096).Select(i => new TextureView(10_000 + (ulong)i)).ToArray();
        var samplers = Enumerable.Range(0, 24).Select(i => new SamplerHolder(500 + (ulong)i)).ToArray();
        var arrays = Enumerable.Range(0, 3).Select(_ => new TextureArray()).ToArray();
        long unique = 0;
        int objectOffset = 0, storageOffset = 0, viewOffset = 0, opsInBuffer = 0;

        int NewOffset() => (int)(++unique * 256 % (1L << 30));
        TextureView FreshView() => new(5_000_000 + (ulong)(++unique));

        var programs = new List<GProgram>();
        for (int p = 0; p < 140; p++)
        {
            GProgram g;
            if (p % 10 == 9)
            {
                // A few programs share a layout and bindings with another: the same-layout path keeps their sets.
                GProgram previous = programs[p - 1];
                g = new GProgram { Vertex = previous.Vertex, Fragment = previous.Fragment, Storage = previous.Storage, Images = previous.Images,
                    VertexTextures = previous.VertexTextures, FragmentTextures = previous.FragmentTextures, Array = previous.Array };
                g.Program = new ShaderCollection("G" + p, previous.Program.Layout, false, previous.Program.BindingSegments);
            }
            else
            {
                g = new GProgram
                {
                    Vertex = 3 + random.Next(13), Fragment = 3 + random.Next(15), Storage = random.Next(10) < 4 ? 1 + random.Next(6) : 0,
                    VertexTextures = random.Next(4), FragmentTextures = 6 + random.Next(39), Images = random.Next(25) == 0 ? 1 : 0,
                    Array = random.Next(4) == 0,
                };
                var uniform = new[] { Seg(0, 1, ResourceType.UniformBuffer), Seg(1, g.Vertex, ResourceType.UniformBuffer),
                    Seg(19, g.Fragment, ResourceType.UniformBuffer) };
                var textures = new List<ResourceBindingSegment>();
                if (g.VertexTextures > 0) textures.Add(Seg(0, g.VertexTextures, ResourceType.TextureAndSampler));
                textures.Add(Seg(64, g.FragmentTextures, ResourceType.TextureAndSampler));
                var sets = new List<ResourceBindingSegment[]> { uniform, g.Storage > 0 ? new[] { Seg(0, g.Storage, ResourceType.StorageBuffer) } : empty,
                    textures.ToArray(), g.Images > 0 ? new[] { Seg(0, 1, ResourceType.Image) } : empty };
                if (g.Array) sets.Add(new[] { Seg(0, 1, ResourceType.TextureAndSampler, array: true) });
                g.Program = new ShaderCollection("G" + p, new TestLayout(layoutId++), false, sets.ToArray());
            }
            g.Materials = Enumerable.Range(0, 4 + random.Next(24)).Select(_ => random.Next(1 << 20)).ToArray();
            g.Material = g.Materials[0];
            programs.Add(g);
        }

        var computes = new List<CProgram>();
        for (int p = 0; p < 24; p++)
        {
            var c = new CProgram { Uniforms = 1 + random.Next(4), Storages = 1 + random.Next(8), Textures = random.Next(13), Images = random.Next(5) };
            var sets = new[] { new[] { Seg(0, c.Uniforms, ResourceType.UniformBuffer) }, new[] { Seg(0, c.Storages, ResourceType.StorageBuffer) },
                c.Textures > 0 ? new[] { Seg(0, c.Textures, ResourceType.TextureAndSampler) } : empty,
                c.Images > 0 ? new[] { Seg(0, c.Images, ResourceType.Image) } : empty };
            c.Program = new ShaderCollection("C" + p, new TestLayout(layoutId++), true, sets);
            computes.Add(c);
        }
        ShaderCollection helper = new("H", new TestLayout(layoutId++), false, new[] { new[] { Seg(1, 1, ResourceType.UniformBuffer) }, empty,
            new[] { Seg(0, 1, ResourceType.TextureAndSampler) }, empty });

        // Uniform bindings: 0 the support buffer, 1 the object's constants, 2.. the view's, 19 the material's, 20.. the view's.
        void SendUniforms(GProgram g, bool all, bool objectMoved)
        {
            var list = new List<(int, ulong, int, int)>();
            if (objectMoved) objectOffset = spec.Fresh ? NewOffset() : (objectOffset + 256) % (1 << 24);
            list.Add((1, 2, objectOffset, 256));
            if (all)
            {
                list.Add((0, 1, 0, 256));
                for (int i = 2; i <= g.Vertex; i++) list.Add((i, 3, viewOffset + i * 256, 256));
                list.Add((19, 4, spec.Fresh ? NewOffset() : g.Material % 4096 * 256, 256));
                for (int i = 1; i < g.Fragment; i++) list.Add((19 + i, 3, viewOffset + (8 + i) * 256, 256));
            }
            Uniforms(list.ToArray());
        }

        void SendTextures(GProgram g)
        {
            for (int i = 0; i < g.VertexTextures; i++)
                Texture(i, spec.Fresh ? FreshView() : views[(g.Material + i) & 4095], samplers[i], ShaderStage.Vertex);
            for (int i = 0; i < g.FragmentTextures; i++)
                Texture(64 + i, spec.Fresh ? FreshView() : views[(g.Material * 7 + i * 131) & 4095], samplers[(g.Material + i) % samplers.Length]);
            if (g.Images > 0) Image(0, spec.Fresh ? FreshView() : views[g.Material & 4095], ShaderStage.Fragment);
            if (g.Array) ArraySet(4, arrays[g.Material % arrays.Length], ShaderStage.Fragment);
        }

        void SendStorage(GProgram g, bool moved)
        {
            if (g.Storage == 0) return;
            if (moved) storageOffset = spec.Fresh ? NewOffset() : (storageOffset + 4096) % (1 << 22);
            var list = new (int, ulong, int, int)[g.Storage];
            for (int i = 0; i < g.Storage; i++) list[i] = (i, 20 + (ulong)i, i == 0 ? storageOffset : (g.Material % 64) * 4096, 4096);
            Storages(list);
        }

        void SendAll(GProgram g)
        {
            SendUniforms(g, all: true, objectMoved: spec.Fresh);
            SendTextures(g);
            SendStorage(g, moved: spec.Fresh);
        }

        void MaybeNewCommandBuffer()
        {
            if (++opsInBuffer >= spec.OpsPerCommandBuffer)
            {
                opsInBuffer = 0;
                NewCommandBuffer();
            }
        }

        GProgram current = null, previousProgram = null;

        void ComputeRun()
        {
            int dispatches = Math.Max(1, (int)Math.Round(spec.DispatchesPerRun + (random.NextDouble() - 0.5) * 6));
            var run = Enumerable.Range(0, 3).Select(_ => computes[random.Next(computes.Count)]).ToArray();
            CProgram c = run[0];
            for (int d = 0; d < dispatches; d++)
            {
                MaybeNewCommandBuffer();
                if (d > 0 && random.NextDouble() >= spec.ComputeSame) c = run[random.Next(run.Length)];
                SetProgram(c.Program);
                // ComputeClass sends the dispatch's bindings each time; the updater compares them with what it holds.
                if (spec.Fresh || random.NextDouble() < spec.ComputeConstants) c.Constants = spec.Fresh ? NewOffset() : (c.Constants + 256) % (1 << 24);
                if (spec.Fresh || random.NextDouble() < spec.ComputeStorage) c.StorageOffset = spec.Fresh ? NewOffset() : (c.StorageOffset + 8192) % (1 << 22);
                if (spec.Fresh || random.NextDouble() < spec.ComputeTextures) c.TextureBase = random.Next(4096);
                var u = new (int, ulong, int, int)[c.Uniforms];
                for (int i = 0; i < c.Uniforms; i++) u[i] = (i, 60 + (ulong)i, i == 0 ? c.Constants : 0, 256);
                Uniforms(u);
                var s = new (int, ulong, int, int)[c.Storages];
                for (int i = 0; i < c.Storages; i++) s[i] = (i, 70 + (ulong)i, i == 0 ? c.StorageOffset : 0, 8192);
                Storages(s);
                for (int i = 0; i < c.Textures; i++)
                    Texture(i, spec.Fresh ? FreshView() : views[(c.TextureBase + i) & 4095], samplers[i % samplers.Length], ShaderStage.Compute);
                for (int i = 0; i < c.Images; i++) Image(i, spec.Fresh ? FreshView() : views[(c.TextureBase + 100 + i) & 4095]);
                Update(computePoint);
                _dispatches++;
            }
            // Back to graphics: the 3D engine sets its program again and every binding is sent again (BufferManager.Rebind).
            if (current != null)
            {
                SetProgram(current.Program);
                SendAll(current);
            }
        }

        for (int frame = 0; frame < spec.Frames; frame++)
        {
            int runsLeft = spec.RunsPerFrame;
            GProgram[] subset = null;
            for (int draw = 0; draw < spec.DrawsPerFrame; draw++)
            {
                if (draw % 213 == 0)
                {
                    subset = Enumerable.Range(0, 8).Select(_ => programs[random.Next(programs.Count)]).ToArray();
                    viewOffset = (viewOffset + 8192) % (1 << 20);
                    if (current != null) SendUniforms(current, all: true, objectMoved: true);
                }
                MaybeNewCommandBuffer();
                if (runsLeft > 0 && random.Next(spec.DrawsPerFrame / spec.RunsPerFrame) == 0)
                {
                    runsLeft--;
                    ComputeRun();
                }
                if (spec.HelperEvery > 0 && random.Next(spec.HelperEvery) == 0)
                {
                    Helper(helper, views[random.Next(4096)], samplers[0], mainCommandBuffer: random.Next(2) == 0);
                    if (current != null) { SetProgram(current.Program); SendAll(current); }
                }

                if (current == null || random.NextDouble() < spec.Switch)
                {
                    GProgram next = previousProgram != null && !spec.Fresh && random.NextDouble() < spec.Return
                        ? previousProgram : subset[random.Next(subset.Length)];
                    if (next != current) previousProgram = current;
                    current = next;
                    if (spec.Fresh || random.NextDouble() >= spec.KeepMaterialOnReturn) current.Material = current.Materials[random.Next(current.Materials.Length)];
                    SetProgram(current.Program);
                    SendAll(current);
                    if (!spec.Fresh && random.NextDouble() < spec.ObjectChange) SendUniforms(current, all: false, objectMoved: true);
                }
                else
                {
                    bool objectMoved = spec.Fresh || random.NextDouble() < spec.ObjectChange;
                    if (spec.Fresh || random.NextDouble() < spec.MaterialChange)
                    {
                        current.Material = current.Materials[random.Next(current.Materials.Length)];
                        SendTextures(current);
                        SendUniforms(current, all: true, objectMoved);
                    }
                    else if (objectMoved)
                    {
                        SendUniforms(current, all: false, objectMoved: true);
                    }
                    if (spec.Fresh || random.NextDouble() < spec.StorageChange) SendStorage(current, moved: true);
                }
                if (current.Array && !spec.Fresh && random.NextDouble() < spec.ArrayChange)
                {
                    // A bindless element changed while bound (TextureArray.SetTextures): ResourceArray.SetDirty.
                    arrays[current.Material % arrays.Length].Change();
                    _u.ForceTextureDirty();
                }
                Update(graphics);
                _draws++;
            }
            while (runsLeft-- > 0) ComputeRun();
        }
    }

    static object Snapshot(string name)
    {
        var journal = new Dictionary<string, object>();
#if CANDIDATE
        // The journal's lines of the run (one each 5 s of updates) and the rest of its counters, as one more line.
        string rest = DescriptorReuseJournal.TakeText(5 * Stopwatch.Frequency);
        var lines = new List<string>(Ryujinx.Common.Logging.Printer.Lines) { rest };
        System.Text.RegularExpressions.Match Find(string line, string pattern)
        {
            var match = System.Text.RegularExpressions.Regex.Match(line, pattern);
            Check.That(match.Success, "journal field " + pattern + ": " + line);
            return match;
        }
        long[] Sum(string field)
        {
            var total = new long[4];
            foreach (string line in lines)
            {
                var match = Find(line, field + @" (\d+)/(\d+)/(\d+)/(\d+)");
                for (int i = 0; i < 4; i++) total[i] += long.Parse(match.Groups[i + 1].Value);
            }
            return total;
        }
        long[] Pair(string field)
        {
            var total = new long[2];
            foreach (string line in lines)
            {
                var match = Find(line, field + @" (\d+) of (\d+)");
                for (int i = 0; i < 2; i++) total[i] += long.Parse(match.Groups[i + 1].Value);
            }
            return total;
        }
        double[] Part(string pattern, int groups)
        {
            var total = new double[groups];
            foreach (string line in lines)
            {
                var match = Find(line, pattern);
                for (int i = 0; i < groups; i++) total[i] += double.Parse(match.Groups[i + 1].Value, System.Globalization.CultureInfo.InvariantCulture);
            }
            return total;
        }
        foreach (string line in lines) Find(line, @"^Vulkan descriptor set reuse measured \(not applied\) over [\d.]+ ms in ");
        journal["lines"] = lines;
        journal["starts"] = Pair("ms in")[1];
        journal["sampledStarts"] = Pair("ms in")[0];
        journal["written"] = Sum("sets written");
        journal["wouldKeep"] = Sum("would be kept bound");
        journal["wouldBindAgain"] = Sum("would be bound again without a write");
        var descriptors = Pair("descriptors that would not be written");
        journal["descriptorsSpared"] = descriptors[0];
        journal["descriptorsWritten"] = descriptors[1];
        var arrays = Pair("array sets that would be kept bound");
        journal["arraySetsWouldKeep"] = arrays[0];
        journal["arraySetBinds"] = arrays[1];
        journal["draw"] = Part(@"draw updates timed (\d+) \(sets 0-3 ([\d.]+) ms, array sets ([\d.]+) ms\)", 3);
        journal["compute"] = Part(@"compute updates timed (\d+) \(sets 0-3 ([\d.]+) ms: resolving ([\d.]+) ms, writing and binding ([\d.]+) ms; array sets ([\d.]+) ms\)", 5);
#endif
        return new
        {
            name,
            ops = _ops, draws = _draws, dispatches = _dispatches, programSets = _programSets,
            setWrites = _gd.Api.SetWrites, writesBySet = _gd.Api.WritesBySet.ToArray(), descriptorsWritten = _gd.Api.DescriptorsWritten,
            binds = _gd.Api.Binds, setsTaken = SetsTaken, setsAllocated = SetsAllocated, arraySetLookups = ArraySetCalls,
            resourceGets = ResourceGets, observations = _observations,
            descriptorHash = _verify ? Convert.ToHexString(_hash.GetHashAndReset()).ToLowerInvariant() : null,
            callHash = _verify ? Convert.ToHexString(_gd.Api.Calls.GetHashAndReset()).ToLowerInvariant() : null,
            updateMs = Math.Round(_updateTicks * 1000.0 / Stopwatch.Frequency, 2),
            renderDetail = new { writes = RenderDetail.DescriptorSetWrites.ToArray(), RenderDetail.DescriptorsWritten, RenderDetail.ProgramSets, RenderDetail.SameProgramSets },
            journal,
        };
    }

    static void Reset(bool verify)
    {
        _gd = new VulkanRenderer();
        _gd.Api.Verify = verify;
        _verify = verify;
        _u = new DescriptorSetUpdater(_gd, mainPipeline: true);
        _helper = new DescriptorSetUpdater(_gd, mainPipeline: false);
        _m = new Model();
        _hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        _observations = _updateTicks = _ops = _draws = _dispatches = _programSets = 0;
        ResourceGets = ArraySetCalls = SetsTaken = SetsAllocated = 0;
        Array.Clear(Submissions);
        _cbIndex = 0;
        _cbs = new CommandBufferScoped { CommandBuffer = new CommandBuffer((nint)0x1000), CommandBufferIndex = 0 };
        _writtenThisSubmission.Clear();
        _pipelineBound = false;
        Array.Clear(RenderDetail.DescriptorSetWrites);
        RenderDetail.DescriptorsWritten = RenderDetail.ProgramSets = RenderDetail.SameProgramSets = 0;
#if CANDIDATE
        DescriptorReuseJournal.TakeText(1);
#endif
        Ryujinx.Common.Logging.Printer.Lines.Clear();
    }

    // The thread's CPU time (Linux clock_gettime CLOCK_THREAD_CPUTIME_ID): a whole stream's, less sensitive than wall time to
    // other processes on the machine.
    [StructLayout(LayoutKind.Sequential)]
    struct Timespec { public long Seconds, Nanoseconds; }
    [DllImport("libc", EntryPoint = "clock_gettime")]
    static extern int ClockGetTime(int clock, out Timespec time);
    static double ThreadCpuMs() => ClockGetTime(3, out Timespec t) == 0 ? t.Seconds * 1000.0 + t.Nanoseconds / 1e6 : double.NaN;

    static void Main(string[] args)
    {
        string mode = args[0];
        EncodingPolicy.IncrementalArrayDescriptors = args[1] == "on";
        int sample = int.Parse(args[2]);
#if CANDIDATE
        DescriptorSetUpdater.ReuseSampleEvery = sample;
#endif
        var results = new List<object>();
        var logShaped = new StreamSpec { Name = "log-shaped" };
        var noRepeat = new StreamSpec { Name = "no-repeat", Fresh = true, HelperEvery = 0 };
        if (mode == "verify")
        {
            Reset(verify: true);
            Scripted();
            results.Add(Snapshot("scripted"));
            Reset(verify: true);
            RunStream(logShaped, 822);
            results.Add(Snapshot("log-shaped"));
            Reset(verify: true);
            RunStream(noRepeat, 823);
            results.Add(Snapshot("no-repeat"));
            Console.WriteLine(JsonSerializer.Serialize(new { mode, policy = args[1], sample, checks = Check.Count, steps = Steps, results }));
        }
#if CANDIDATE
        else if (mode == "time-samples")
        {
            // In one process, alternated: the stream with no command buffer measured (0), one in eight (8) and every one (1);
            // the time inside UpdateAndBindDescriptorSets, the least of the repeats.
            int repeats = int.Parse(args[3]);
            var least = new Dictionary<string, double>();
            foreach (var spec in new[] { logShaped, noRepeat })
            {
                for (int r = 0; r < repeats; r++)
                {
                    foreach (int every in new[] { 0, 8, 1 })
                    {
                        DescriptorSetUpdater.ReuseSampleEvery = every;
                        Reset(verify: false);
                        GC.Collect();
                        RunStream(spec, spec == logShaped ? 822 : 823);
                        string key = spec.Name + "/" + every;
                        double ms = _updateTicks * 1000.0 / Stopwatch.Frequency;
                        least[key] = least.TryGetValue(key, out double previous) ? Math.Min(previous, ms) : ms;
                    }
                }
            }
            Console.WriteLine(JsonSerializer.Serialize(new { mode, least = least.ToDictionary(x => x.Key, x => Math.Round(x.Value, 2)) }));
        }
#endif
        else
        {
            int repeats = int.Parse(args[3]);
            var timings = new Dictionary<string, List<double>>();
            var cpuTimings = new Dictionary<string, List<double>>();
            object last = null;
            foreach (var spec in new[] { logShaped, noRepeat })
            {
                timings[spec.Name] = new List<double>();
                for (int r = 0; r < repeats; r++)
                {
                    Reset(verify: false);
                    GC.Collect();
                    double cpuStart = ThreadCpuMs();
                    RunStream(spec, spec == logShaped ? 822 : 823);
                    double cpu = ThreadCpuMs() - cpuStart;
                    timings[spec.Name].Add(Math.Round(_updateTicks * 1000.0 / Stopwatch.Frequency, 2));
                    (cpuTimings.TryGetValue(spec.Name, out var list) ? list : cpuTimings[spec.Name] = new List<double>()).Add(Math.Round(cpu, 2));
                    last = Snapshot(spec.Name);
                    results.Add(last);
                }
            }
            Console.WriteLine(JsonSerializer.Serialize(new { mode, policy = args[1], sample, timings, cpuTimings, results }));
        }
    }
}
