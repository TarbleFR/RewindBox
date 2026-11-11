using Ryujinx.Common.Configuration;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Shader;
using Ryujinx.Memory;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;

// Executes the compiled production TextureManager, TextureBindingsManager, TexturePool, SamplerPool, Texture and
// BufferManager (control or candidate engine) against guest memory: compute and graphics commits alternate as a game
// alternates dispatches and draws. Only GAL is doubled: a pipeline that keeps one slot table per binding number for
// textures and one for images, shared by compute and graphics like the Vulkan backend's DescriptorSetUpdater, and records
// every call. After each commit the slots of the committing pipeline must hold the textures its handles name now
// (handle changes and pool rewrites included). Prints the sequence of slot states, the call counts and the time of
// steady commits.
static class Program
{
    private const ulong GuestBase = 0x10000000;
    private const ulong GuestSize = 64UL << 20;
    private const ulong PoolOffset = 0;               // texture pool, 32 bytes per entry
    private const ulong SamplerOffset = 1UL << 20;    // sampler pool, 32 bytes per entry
    private const ulong CbufOffset = 2UL << 20;       // compute handles at +0, graphics handles at +0x1000
    private const ulong TextureOffset = 4UL << 20;
    private const ulong GpuBase = 0x40000000;
    private const int MaximumId = 255;

    public sealed class RecordingTexture : ITexture
    {
        public readonly TextureCreateInfo Info;
        public RecordingTexture(TextureCreateInfo info) => Info = info;
        public int Width => Info.Width;
        public int Height => Info.Height;
        public void CopyTo(ITexture destination, int firstLayer, int firstLevel) { }
        public void CopyTo(ITexture destination, int srcLayer, int dstLayer, int srcLevel, int dstLevel) { }
        public void CopyTo(ITexture destination, Extents2D srcRegion, Extents2D dstRegion, bool linearFilter) { }
        public void CopyTo(BufferRange range, int layer, int level, int stride) { }
        public ITexture CreateView(TextureCreateInfo info, int firstLayer, int firstLevel) => new RecordingTexture(info);
        public PinnedSpan<byte> GetData() => default;
        public PinnedSpan<byte> GetData(int layer, int level) => default;
        public void SetData(MemoryOwner<byte> data) => data.Dispose();
        public void SetData(MemoryOwner<byte> data, int layer, int level) => data.Dispose();
        public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region) => data.Dispose();
        public void SetStorage(BufferRange buffer) { }
        public void Release() { }
    }

    public sealed class RecordingSampler : ISampler
    {
        public readonly int Index;
        public RecordingSampler(int index) => Index = index;
        public void Dispose() { }
    }

    // The backend's slot tables: one per binding number, shared by compute and graphics.
    public static readonly Dictionary<int, (object Texture, object Sampler)> TextureSlots = new();
    public static readonly Dictionary<int, object> ImageSlots = new();
    public static int TextureCalls, ImageCalls;

    public class RecordingPipeline : DispatchProxy
    {
        protected override object Invoke(MethodInfo method, object[] args)
        {
            if (method.Name == nameof(IPipeline.SetTextureAndSampler))
            {
                TextureCalls++;
                TextureSlots[(int)args[1]] = (args[2], args[3]);
            }
            else if (method.Name == nameof(IPipeline.SetImage) && args.Length == 3 && args[0] is ShaderStage)
            {
                ImageCalls++;
                ImageSlots[(int)args[1]] = args[2];
            }
            Type result = method.ReturnType;
            return result != typeof(void) && result.IsValueType ? Activator.CreateInstance(result) : null;
        }
    }

    private sealed class RecordingRenderer : IRenderer
    {
        private int _buffers, _samplers;
        public event EventHandler<ScreenCaptureImageInfo> ScreenCaptured { add { } remove { } }
        public bool PreferThreading => false;
        public IPipeline Pipeline { get; } = DispatchProxy.Create<IPipeline, RecordingPipeline>();
        public IWindow Window { get; } = Fake.Create<IWindow>();
        public uint ProgramCount => 0;
        public void BackgroundContextAction(Action action, bool alwaysBackground = false) => action();
        public BufferHandle CreateBuffer(int size, BufferAccess access = BufferAccess.Default) => Handle();
        public BufferHandle CreateBuffer(nint pointer, int size) => Handle();
        public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> storageBuffers) => Handle();
        public IImageArray CreateImageArray(int size, bool isBuffer) => Fake.Create<IImageArray>();
        public IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info) => Fake.Create<IProgram>();
        public ISampler CreateSampler(SamplerCreateInfo info) => new RecordingSampler(++_samplers);
        public ITexture CreateTexture(TextureCreateInfo info) => new RecordingTexture(info);
        public ITextureArray CreateTextureArray(int size, bool isBuffer) => Fake.Create<ITextureArray>();
        public bool PrepareHostMapping(nint address, ulong size) => false;
        public void CreateSync(ulong id, bool strict) { }
        public void DeleteBuffer(BufferHandle buffer) { }
        public PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size) => default;
        public Capabilities GetCapabilities() => default;
        public ulong GetCurrentSync() => 0;
        public HardwareInfo GetHardwareInfo() => new("", "", "");
        public IProgram LoadProgramBinary(byte[] programBinary, bool hasFragmentShader, ShaderInfo info) => Fake.Create<IProgram>();
        public void SetBufferData(BufferHandle buffer, int offset, ReadOnlySpan<byte> data) { }
        public void UpdateCounters() { }
        public void PreFrame() { }
        public ICounterEvent ReportCounter(CounterType type, EventHandler<ulong> resultHandler, float divisor, bool hostReserved) => Fake.Create<ICounterEvent>();
        public void ResetCounter(CounterType type) { }
        public void WaitSync(ulong id) { }
        public void Initialize(GraphicsDebugLevel logLevel) { }
        public void SetInterruptAction(Action<Action> interruptAction) { }
        public void Screenshot() { }
        public void Dispose() { }
        private BufferHandle Handle()
        {
            ulong value = (ulong)++_buffers;
            return Unsafe.As<ulong, BufferHandle>(ref value);
        }
    }

    private static Ryujinx.Cpu.Jit.MemoryManager _cpu;
    private static ulong _nextTexture;
    private static readonly Dictionary<int, int> WidthOf = new(); // texture id -> width (unique per texture)

    private static void Texture(int id, int width)
    {
        ulong offset = _nextTexture;
        int size = width * 8 * 4;
        _nextTexture += (ulong)((size + 0xFFFF) & ~0xFFFF);
        _cpu.Write(GuestBase + TextureOffset + offset, new byte[size]);
        ulong gpuVa = GpuBase + TextureOffset + offset;
        uint[] words =
        [
            0x24908 | (2u << 19) | (3u << 22) | (4u << 25) | (5u << 28), // A8B8G8R8 Unorm, RGBA swizzle
            (uint)gpuVa,
            (uint)(gpuVa >> 32) | (2u << 21),                             // linear
            (uint)(width * 4) >> 5,
            (uint)(width - 1) | (1u << 23),                               // Texture2D
            7,                                                            // height 8
            0,
            0,
        ];
        _cpu.Write(GuestBase + PoolOffset + (ulong)id * 32, MemoryMarshal.AsBytes(words.AsSpan()));
        WidthOf[id] = width;
    }

    private static void Handle(ulong cbuf, int word, int textureId, int samplerId)
    {
        _cpu.Write(GuestBase + CbufOffset + cbuf + (ulong)word * 4, BitConverter.GetBytes(textureId | (samplerId << 20)));
    }

    private static CachedShaderBindings Bindings(int stages, int stage, TextureBindingInfo[] textures, TextureBindingInfo[] images)
    {
        var bindings = (CachedShaderBindings)RuntimeHelpers.GetUninitializedObject(typeof(CachedShaderBindings));
        var t = Enumerable.Range(0, stages).Select(_ => Array.Empty<TextureBindingInfo>()).ToArray();
        var i = Enumerable.Range(0, stages).Select(_ => Array.Empty<TextureBindingInfo>()).ToArray();
        t[stage] = textures;
        i[stage] = images;
        void Set(string name, object value) =>
            typeof(CachedShaderBindings).GetField($"<{name}>k__BackingField", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(bindings, value);
        Set(nameof(CachedShaderBindings.TextureBindings), t);
        Set(nameof(CachedShaderBindings.ImageBindings), i);
        Set(nameof(CachedShaderBindings.TextureCounts), new int[stages]);
        Set(nameof(CachedShaderBindings.MaxTextureBinding), textures.Length == 0 ? 0 : textures.Max(b => b.Binding));
        Set(nameof(CachedShaderBindings.MaxImageBinding), images.Length == 0 ? 0 : images.Max(b => b.Binding));
        return bindings;
    }

    // A specialization state with no recorded texture state: every MatchesTexture/MatchesImage returns true.
    private static ShaderSpecializationState Spec(int stages)
    {
        var spec = (ShaderSpecializationState)RuntimeHelpers.GetUninitializedObject(typeof(ShaderSpecializationState));
        foreach (string name in new[] { "_textureByBinding", "_imageByBinding" })
        {
            FieldInfo field = typeof(ShaderSpecializationState).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!;
            Type inner = field.FieldType.GetElementType()!;            // Box<TextureSpecializationState>[]
            Array outer = Array.CreateInstance(inner, stages);
            for (int i = 0; i < stages; i++) outer.SetValue(Array.CreateInstance(inner.GetElementType()!, 8), i);
            field.SetValue(spec, outer);
        }
        return spec;
    }

    private static int Width(object texture) => texture is RecordingTexture t ? t.Width : 0;
    private static int SamplerId(object sampler) => sampler is RecordingSampler s ? s.Index : 0;

    public static int Main()
    {
        var backing = new MemoryBlock(GuestSize);
        _cpu = new Ryujinx.Cpu.Jit.MemoryManager(backing, 1UL << 36);
        _cpu.Map(GuestBase, 0, GuestSize, MemoryMapFlags.None);
        _cpu.IncrementReferenceCount();
        var renderer = new RecordingRenderer();
        var gpu = new GpuContext(renderer, new DirtyHacks(Array.Empty<ulong>()));
        gpu.SetGpuThread();
        gpu.RegisterProcess(1, _cpu);
        MemoryManager gpuMemory = gpu.CreateMemoryManager(1, GuestSize);
        gpuMemory.Map(GuestBase, GpuBase, GuestSize, PteKind.Pitch);
        GpuChannel channel = gpu.CreateChannel();
        channel.BindMemory(gpuMemory);
        TextureManager textures = channel.TextureManager;
        BufferManager buffers = channel.BufferManager;

        for (int id = 1; id <= 8; id++) Texture(id, 8 * id);
        // Sampler pool: zeroed descriptors are valid samplers (ids 0..2 used).

        var rgba8 = new FormatInfo(Format.R8G8B8A8Unorm, 1, 1, 4, 4);
        // Compute: textures at bindings 0 and 1 (handle words 0 and 1), an image at binding 0 (word 2).
        // Graphics (fragment): textures at bindings 0, 1 and 2 (words 0, 1, 2): bindings 0 and 1 share the compute slots.
        var computeTextures = new[]
        {
            new TextureBindingInfo(Target.Texture2D, 2, 0, 1, -1, 0, TextureUsageFlags.None, false),
            new TextureBindingInfo(Target.Texture2D, 2, 1, 1, -1, 1, TextureUsageFlags.None, false),
        };
        var computeImages = new[] { new TextureBindingInfo(Target.Texture2D, rgba8, 3, 0, 1, -1, 2, TextureUsageFlags.None) };
        var graphicsTextures = new[]
        {
            new TextureBindingInfo(Target.Texture2D, 2, 0, 1, -1, 0, TextureUsageFlags.None, false),
            new TextureBindingInfo(Target.Texture2D, 2, 1, 1, -1, 1, TextureUsageFlags.None, false),
            new TextureBindingInfo(Target.Texture2D, 2, 2, 1, -1, 2, TextureUsageFlags.None, false),
        };
        var graphicsImages = new[] { new TextureBindingInfo(Target.Texture2D, rgba8, 3, 0, 1, -1, 3, TextureUsageFlags.None) };

        textures.SetComputeTexturePool(GpuBase + PoolOffset, MaximumId);
        textures.SetComputeSamplerPool(GpuBase + SamplerOffset, MaximumId, Ryujinx.Graphics.Gpu.Engine.Types.SamplerIndex.Independently);
        textures.SetGraphicsTexturePool(GpuBase + PoolOffset, MaximumId);
        textures.SetGraphicsSamplerPool(GpuBase + SamplerOffset, MaximumId, Ryujinx.Graphics.Gpu.Engine.Types.SamplerIndex.Independently);
        textures.SetComputeTextureBufferIndex(0);
        textures.SetGraphicsTextureBufferIndex(0);
        textures.SetComputeBindings(Bindings(1, 0, computeTextures, computeImages));
        textures.SetGraphicsBindings(Bindings(5, 4, graphicsTextures, graphicsImages));
        buffers.SetComputeUniformBuffer(0, GpuBase + CbufOffset, 0x100);
        buffers.SetGraphicsUniformBuffer(4, 0, GpuBase + CbufOffset + 0x1000, 0x100);

        int[] compute = [1, 2, 3]; int[] computeSamplers = [0, 1, 0];
        int[] graphics = [4, 5, 6, 7]; int[] graphicsSamplers = [1, 0, 2, 0];
        void WriteHandles()
        {
            for (int w = 0; w < 3; w++) Handle(0, w, compute[w], computeSamplers[w]);
            for (int w = 0; w < 4; w++) Handle(0x1000, w, graphics[w], graphicsSamplers[w]);
        }
        WriteHandles();

        var specCompute = Spec(1);
        var specGraphics = Spec(6); // indexed by ShaderStage value (Fragment = 5)
        var sequence = new List<string>();
        var errors = new List<string>();

        // Each draw and dispatch advances the GPU sequence, as ComputeClass and ThreedClass do (pools re-check their memory once per sequence).
        void Dispatch(string step)
        {
            gpu.AdvanceSequence();
            textures.CommitComputeBindings(specCompute);
            string state = $"{step} compute t0={Width(TextureSlots.GetValueOrDefault(0).Texture)}/{SamplerId(TextureSlots.GetValueOrDefault(0).Sampler)} " +
                           $"t1={Width(TextureSlots.GetValueOrDefault(1).Texture)} i0={Width(ImageSlots.GetValueOrDefault(0))}";
            sequence.Add(state);
            if (Width(TextureSlots.GetValueOrDefault(0).Texture) != WidthOf[compute[0]] ||
                Width(TextureSlots.GetValueOrDefault(1).Texture) != WidthOf[compute[1]] ||
                Width(ImageSlots.GetValueOrDefault(0)) != WidthOf[compute[2]])
                errors.Add("wrong compute slots: " + state);
        }

        void Draw(string step)
        {
            gpu.AdvanceSequence();
            textures.CommitGraphicsBindings(specGraphics, out _);
            string state = $"{step} graphics t0={Width(TextureSlots.GetValueOrDefault(0).Texture)}/{SamplerId(TextureSlots.GetValueOrDefault(0).Sampler)} " +
                           $"t1={Width(TextureSlots.GetValueOrDefault(1).Texture)} t2={Width(TextureSlots.GetValueOrDefault(2).Texture)} " +
                           $"i0={Width(ImageSlots.GetValueOrDefault(0))}";
            sequence.Add(state);
            if (Width(TextureSlots.GetValueOrDefault(0).Texture) != WidthOf[graphics[0]] ||
                Width(TextureSlots.GetValueOrDefault(1).Texture) != WidthOf[graphics[1]] ||
                Width(TextureSlots.GetValueOrDefault(2).Texture) != WidthOf[graphics[2]] ||
                Width(ImageSlots.GetValueOrDefault(0)) != WidthOf[graphics[3]])
                errors.Add("wrong graphics slots: " + state);
        }

        int callsBefore = TextureCalls + ImageCalls;
        for (int i = 0; i < 4; i++) { Dispatch("steady" + i); Draw("steady" + i); }
        Draw("drawAgain");                                        // two draws in a row: nothing to re-send
        int steadyCalls = TextureCalls + ImageCalls - callsBefore;
        graphics[0] = 2; WriteHandles();                          // a graphics handle changes to the compute's texture
        Dispatch("handle"); Draw("handle");
        compute[1] = 6; WriteHandles();                           // a compute handle changes
        Dispatch("computeHandle"); Draw("computeHandle");
        Texture(5, 72);                                           // the pool entry of a bound texture is rewritten
        Dispatch("pool"); Draw("pool");
        graphics[3] = 8; WriteHandles();                          // the graphics image handle changes
        Draw("imageNoDispatch"); Dispatch("image"); Draw("image");
        for (int i = 0; i < 3; i++) { Dispatch("after" + i); Draw("after" + i); }

        // Steady commits, timed (host CPU, Release build, run by the gate without tiered compilation so that every
        // round executes the same optimized code): seven rounds of 50 000 compute/graphics pairs, each just after a
        // reference round of 50 000 pairs of graphics commits with no compute between them (the path the adapter
        // leaves as it is, in the same classes). The measure is the median of round / reference: the two probes are
        // separate processes and a shared runner does not give both the same speed (Core CI run 43009346249: the
        // control's fastest of five rounds 48 ms, the candidate's 140 ms, against 204 and 122 ms for one round each in
        // run 42958274015), so each round is compared to the same engine's unchanged work done by the same process at
        // the same moment. The fastest round is still reported. The backend calls are those of the first round.
        for (int i = 0; i < 2000; i++) { gpu.AdvanceSequence(); textures.CommitComputeBindings(specCompute); gpu.AdvanceSequence(); textures.CommitGraphicsBindings(specGraphics, out _); }
        for (int i = 0; i < 2000; i++) { gpu.AdvanceSequence(); textures.CommitGraphicsBindings(specGraphics, out _); gpu.AdvanceSequence(); textures.CommitGraphicsBindings(specGraphics, out _); }
        var roundsMs = new double[7];
        var referenceMs = new double[roundsMs.Length];
        int timedCalls = 0;
        for (int round = 0; round < roundsMs.Length; round++)
        {
            var watch = Stopwatch.StartNew();
            for (int i = 0; i < 50000; i++) { gpu.AdvanceSequence(); textures.CommitGraphicsBindings(specGraphics, out _); gpu.AdvanceSequence(); textures.CommitGraphicsBindings(specGraphics, out _); }
            referenceMs[round] = watch.Elapsed.TotalMilliseconds;
            int timedCallsBefore = TextureCalls + ImageCalls;
            watch.Restart();
            for (int i = 0; i < 50000; i++) { gpu.AdvanceSequence(); textures.CommitComputeBindings(specCompute); gpu.AdvanceSequence(); textures.CommitGraphicsBindings(specGraphics, out _); }
            roundsMs[round] = watch.Elapsed.TotalMilliseconds;
            if (round == 0) { timedCalls = TextureCalls + ImageCalls - timedCallsBefore; }
        }
        double ms = roundsMs.Min();
        double[] relative = roundsMs.Select((value, index) => value / referenceMs[index]).OrderBy(value => value).ToArray();

        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["sequence"] = sequence,
            ["errors"] = errors,
            ["steadyCalls"] = steadyCalls,
            ["timedPairs"] = 50000,
            ["timedMs"] = ms,
            ["timedRoundsMs"] = roundsMs,
            ["referenceRoundsMs"] = referenceMs,
            ["timedRelative"] = relative[relative.Length / 2],
            ["tieredCompilation"] = Environment.GetEnvironmentVariable("DOTNET_TieredCompilation") ?? "",
            ["timedBackendCalls"] = timedCalls,
        }));
        return 0;
    }
}
