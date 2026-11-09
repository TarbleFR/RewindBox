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

// (adapted from test/melonx_compute_switch_bindings/Program.cs) Executes the compiled production TextureManager, TextureBindingsManager, TexturePool, SamplerPool, Texture and
// BufferManager (control or candidate engine) against guest memory: compute and graphics commits alternate as a game
// alternates dispatches and draws. Only GAL is doubled: a pipeline that keeps one slot table per binding number for
// textures and one for images, shared by compute and graphics like the Vulkan backend's DescriptorSetUpdater, and records
// every call. After each commit the slots of the committing pipeline must hold the textures its handles name now
// (handle changes and pool rewrites included). Prints the sequence of slot states, the call counts and the time of
// steady commits.
static class Program
{
    private const ulong GuestBase = 0x10000000;
    private const ulong GuestSize = 512UL << 20;
    private const ulong PoolOffset = 0;               // texture pool, 32 bytes per entry
    private const ulong SamplerOffset = 1UL << 20;    // sampler pool, 32 bytes per entry
    private const ulong CbufOffset = 2UL << 20;       // compute handles at +0, graphics handles at +0x1000
    private const ulong TextureOffset = 4UL << 20;
    private const ulong GpuBase = 0x40000000;
    private const int MaximumId = 511;

    public sealed class RecordingTexture : ITexture
    {
        public static int Created, Views, Uploads;
        public readonly TextureCreateInfo Info;
        public readonly int FirstLevel;
        public readonly RecordingTexture Parent;
        public RecordingTexture(TextureCreateInfo info, RecordingTexture parent = null, int firstLevel = 0)
        { Info = info; Parent = parent; FirstLevel = firstLevel; if (parent == null) Created++; else Views++; }
        public int Width => Info.Width;
        public int Height => Info.Height;
        public void CopyTo(ITexture destination, int firstLayer, int firstLevel) { }
        public void CopyTo(ITexture destination, int srcLayer, int dstLayer, int srcLevel, int dstLevel) { }
        public void CopyTo(ITexture destination, Extents2D srcRegion, Extents2D dstRegion, bool linearFilter) { }
        public void CopyTo(BufferRange range, int layer, int level, int stride) { }
        public ITexture CreateView(TextureCreateInfo info, int firstLayer, int firstLevel) => new RecordingTexture(info, this, firstLevel);
        public PinnedSpan<byte> GetData() => default;
        public PinnedSpan<byte> GetData(int layer, int level) => default;
        public void SetData(MemoryOwner<byte> data) { Uploads++; data.Dispose(); }
        public void SetData(MemoryOwner<byte> data, int layer, int level) => data.Dispose();
        public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region) => data.Dispose();
        public void SetStorage(BufferRange buffer) { }
        public void Release() { }
    }

    public sealed class RecordingTextureArray : ITextureArray
    {
        public readonly ITexture[] Textures;
        public int Writes, ElementsWritten;
        public RecordingTextureArray(int size) => Textures = new ITexture[size];
        public void SetSamplers(int index, ISampler[] samplers) { }
        public void SetTextures(int index, ITexture[] textures) { Writes++; ElementsWritten += textures.Length; textures.AsSpan().CopyTo(Textures.AsSpan(index)); }
        public void Dispose() { }
    }

    public static readonly List<RecordingTextureArray> Arrays = new();

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
        public IPipeline Pipeline { get; } = new NoopPipeline();
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
        public ITextureArray CreateTextureArray(int size, bool isBuffer) => NewArray(size);
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

    private static RecordingTextureArray NewArray(int size)
    {
        var array = new RecordingTextureArray(size);
        Arrays.Add(array);
        return array;
    }

    private static Ryujinx.Cpu.Jit.MemoryManager _cpu;
    private static ulong Trimmed;
    private const int Textures = 1600;
    private const int Changed = 64;
    // Pool entry -> (texture index, base level): what the array element must hold.
    private static readonly int[] EntryTexture = new int[MaximumId + 1];
    private static readonly int[] EntryBase = new int[MaximumId + 1];

    // Texture k (1..Textures): its own 256 KiB of guest memory, a unique size (Width(k) x Height(k)), two levels.
    private static ulong TextureVa(int k) => GpuBase + TextureOffset + (ulong)k * 0x40000;
    private static int TexWidth(int k) => 64 + 8 * (k % 64);
    private static int TexHeight(int k) => 64 + k / 64;

    private static readonly int[] EntrySwizzle = new int[MaximumId + 1];

    private static void Entry(int id, int k, int baseLevel = 0, bool red = false)
    {
        int width = TexWidth(k);
        uint[] words =
        [
            0x24908 | (2u << 19) | ((red ? 2u : 3u) << 22) | ((red ? 2u : 4u) << 25) | (5u << 28), // A8B8G8R8 Unorm, RGBA or RRRA
            (uint)TextureVa(k),
            (uint)(TextureVa(k) >> 32) | (2u << 21),                     // linear
            ((uint)(width * 4) >> 5) | (1u << 28),                         // stride, two levels
            (uint)(width - 1) | (1u << 23),                                // Texture2D
            (uint)(TexHeight(k) - 1),                                      // height
            0,
            (uint)baseLevel | (1u << 4),                                   // base level, max level 1
        ];
        _cpu.Write(GuestBase + PoolOffset + (ulong)id * 32, MemoryMarshal.AsBytes(words.AsSpan()));
        EntryTexture[id] = k;
        EntryBase[id] = baseLevel;
        EntrySwizzle[id] = red ? 1 : 0;
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

    private static RecordingTexture Root(RecordingTexture t) => t.Parent == null ? t : Root(t.Parent);

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

        for (int id = 1; id <= MaximumId; id++) Entry(id, id);

        // A fragment array of combined samplers indexed by pool id (direct handle), as Hogwarts Legacy's set 4 array.
        int direct = Ryujinx.Graphics.Shader.TextureHandle.PackOffsets(0, 0, Ryujinx.Graphics.Shader.TextureHandleType.Direct);
        var arrayBinding = new TextureBindingInfo(Target.Texture2D, 4, 0, MaximumId + 1, 0, direct, TextureUsageFlags.None, false);
        textures.SetGraphicsTexturePool(GpuBase + PoolOffset, MaximumId);
        textures.SetGraphicsSamplerPool(GpuBase + SamplerOffset, MaximumId, Ryujinx.Graphics.Gpu.Engine.Types.SamplerIndex.Independently);
        textures.SetGraphicsTextureBufferIndex(0);
        textures.SetGraphicsBindings(Bindings(5, 4, new[] { arrayBinding }, Array.Empty<TextureBindingInfo>()));
        buffers.SetGraphicsUniformBuffer(4, 0, GpuBase + CbufOffset + 0x1000, 0x100);
        var spec = Spec(6);
        var errors = new List<string>();

        void Draw(string step)
        {
            gpu.AdvanceSequence();
            textures.CommitGraphicsBindings(spec, out _);
            RecordingTextureArray array = Arrays[^1];
            for (int id = 1; id <= MaximumId; id++)
            {
                var t = array.Textures[id] as RecordingTexture;
                int width = t == null ? 0 : Root(t).Width * 1000 + Root(t).Height;
                int level = t == null ? -1 : t.Parent == null ? 0 : t.FirstLevel;
                int expected = TexWidth(EntryTexture[id]) * 1000 + TexHeight(EntryTexture[id]);
                if (width != expected || level != EntryBase[id])
                {
                    if (errors.Count < 8) errors.Add($"{step}: element {id} holds width {width} level {level}, pool names {expected} level {EntryBase[id]}");
                }
            }
        }

        var results = new Dictionary<string, object>();
        int pass = 0;

        void Measure(string name, int passes, Action<int> change, int changedPerPass)
        {
            // Warm-up passes of the same kind, then measured passes.
            for (int i = 0; i < 8; i++) { change(pass++); Draw(name + " warm-up"); }
            int created = RecordingTexture.Created, views = RecordingTexture.Views, uploads = RecordingTexture.Uploads;
            int writes = Arrays[^1].Writes, elements = Arrays[^1].ElementsWritten;
            long bytes = 0;
            var watch = new Stopwatch();
            for (int i = 0; i < passes; i++)
            {
                change(pass++);
                long before = GC.GetAllocatedBytesForCurrentThread();
                watch.Start();
                gpu.AdvanceSequence();
                textures.CommitGraphicsBindings(spec, out _);
                watch.Stop();
                bytes += GC.GetAllocatedBytesForCurrentThread() - before;
                Draw(name + " check");
            }
            results[name] = new Dictionary<string, object>
            {
                ["passes"] = passes,
                ["changedPerPass"] = changedPerPass,
                ["bytesPerPass"] = bytes / passes,
                ["bytesPerChangedElement"] = changedPerPass == 0 ? 0 : bytes / passes / changedPerPass,
                ["texturesCreated"] = RecordingTexture.Created - created,
                ["viewsCreated"] = RecordingTexture.Views - views,
                ["arrayWrites"] = Arrays[^1].Writes - writes,
                ["elementsSent"] = Arrays[^1].ElementsWritten - elements,
                ["msPerPass"] = Math.Round(watch.Elapsed.TotalMilliseconds / passes, 4),
                ["uploads"] = RecordingTexture.Uploads - uploads,
            };
        }

        Draw("first");
        Measure("unchanged", 200, _ => { }, 0);
        Measure("identicalRewrite", 200, p => { for (int i = 0; i < Changed; i++) { int id = 1 + (p * 7 + i) % MaximumId; Entry(id, EntryTexture[id], EntryBase[id]); } }, Changed);
        // Swap: 64 entries alternate between their own texture and texture id+511 (both seen after the warm-up).
        Measure("swapKnown", 200, p => { for (int i = 0; i < Changed; i++) { int id = 1 + i; Entry(id, (p & 1) == 0 ? id + MaximumId : id); } }, Changed);
        // Swizzle: 64 entries alternate RGBA and RRRA views of their own texture (same memory, another view).
        Measure("swizzleFlip", 200, p => { for (int i = 0; i < Changed; i++) { int id = 400 + i; Entry(id, id, 0, (p & 1) == 1); } }, Changed);
        // Swap with presents between passes: 64 entries name texture id+511 for three presented frames (Window.Present
        // ticks the texture cache once per frame), then their own texture again.
        Measure("swapAfterFrames", 120, p =>
        {
            gpuMemory.Physical.TextureCache.Tick();
            for (int i = 0; i < Changed; i++) { int id = 130 + i; Entry(id, (p % 4) == 0 ? id : id + MaximumId); }
        }, Changed);
        // CPU writes: 64 bound textures have their guest memory rewritten before each pass (TextureSync path).
        byte[] texel = new byte[0x40000];
        Measure("cpuModified", 200, p => { for (int i = 0; i < Changed; i++) { int k = 300 + i; texel[0] = (byte)p; _cpu.Write(GuestBase + TextureOffset + (ulong)k * 0x40000, texel.AsSpan(0, TexWidth(k) * TexHeight(k) * 4)); } }, Changed);
        // Swap with a host Warning trim (device short, freeOnly as in the IPA 694 lines) before every fourth pass: the
        // swapped-out textures are unreferenced when the trim runs; the next swap names them again.
        GraphicsConfig.EnableHostMemoryBudgetTracking = true;
        Measure("swapKnownWithTrim", 200, p =>
        {
            if (p % 4 == 0) Trimmed += gpuMemory.Physical.TextureCache.Trim(Ryujinx.Memory.MemoryPressureLevel.Warning, freeOnly: true);
            for (int i = 0; i < Changed; i++) { int id = 1 + i; Entry(id, (p & 1) == 0 ? id + MaximumId : id); }
        }, Changed);
        // New textures: 64 entries name textures never seen before (bounded: 16 passes).
        int fresh = 2 * MaximumId + 1;
        Measure("newTextures", 8, p => { for (int i = 0; i < Changed && fresh < Textures; i++) { int id = 200 + i; Entry(id, fresh++); } }, Changed);

        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["errors"] = errors,
            ["results"] = results,
            ["arrays"] = Arrays.Count,
            ["trimmedBytes"] = Trimmed,
            ["cacheBytes"] = gpuMemory.Physical.TextureCache.CachedBytes,
            ["cacheLimit"] = gpuMemory.Physical.TextureCache.CacheLimit,
        }));
        return 0;
    }
}
