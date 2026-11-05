using Ryujinx.Common.Configuration;
using Ryujinx.Common.Logging;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Shader;
using Ryujinx.Memory;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;

// Executes the compiled production GpuContext, TexturePool, Texture, TextureGroup, TextureCache, AutoDeleteCache and GPU
// MemoryManager of the candidate (adapt_cold_texture_release) against guest memory holding linear RGBA8 textures. Only
// GAL is doubled: a renderer whose textures record what they are given (uploads, release); no Vulkan, Metal or GPU.
// Time is the GPU use clock (GpuContext.TextureUseEpoch, seconds) and the pass clock (milliseconds), both set here.
static class Program
{
    private const ulong GuestBase = 0x10000000;
    private const ulong GuestSize = 256UL << 20;
    private const ulong PoolOffset = 0;
    private const ulong TextureOffset = 16UL << 20;
    private const ulong TextureGpuVa = 0x20000000;
    private const ulong TextureSpace = 200UL << 20;
    private const int MaximumId = 1023;
    private const string Tag = "(adapt_cold_texture_release)";

    private static readonly List<string> Lines = [];

    private sealed class RecordingTexture : ITexture
    {
        public readonly TextureCreateInfo Info;
        public readonly List<byte[]> Uploads = [];
        public int Releases;
        public int Reads;

        public RecordingTexture(TextureCreateInfo info) => Info = info;

        public int Width => Info.Width;
        public int Height => Info.Height;

        public void CopyTo(ITexture destination, int firstLayer, int firstLevel) { }
        public void CopyTo(ITexture destination, int srcLayer, int dstLayer, int srcLevel, int dstLevel) { }
        public void CopyTo(ITexture destination, Extents2D srcRegion, Extents2D dstRegion, bool linearFilter) { }
        public void CopyTo(BufferRange range, int layer, int level, int stride) { }
        public ITexture CreateView(TextureCreateInfo info, int firstLayer, int firstLevel) => new RecordingTexture(info);
        public PinnedSpan<byte> GetData() { Reads++; return default; }
        public PinnedSpan<byte> GetData(int layer, int level) { Reads++; return default; }
        public void SetData(MemoryOwner<byte> data) { Uploads.Add(data.Span.ToArray()); data.Dispose(); }
        public void SetData(MemoryOwner<byte> data, int layer, int level) { Uploads.Add(data.Span.ToArray()); data.Dispose(); }
        public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region) { Uploads.Add(data.Span.ToArray()); data.Dispose(); }
        public void SetStorage(BufferRange buffer) { }
        public void Release() => Releases++;
    }

    private sealed class RecordingRenderer : IRenderer
    {
        public readonly List<RecordingTexture> Textures = [];
        private int _buffers;

        public event EventHandler<ScreenCaptureImageInfo> ScreenCaptured { add { } remove { } }
        public bool PreferThreading => false;
        public IPipeline Pipeline { get; } = Fake.Create<IPipeline>();
        public IWindow Window { get; } = Fake.Create<IWindow>();
        public uint ProgramCount => 0;
        public void BackgroundContextAction(Action action, bool alwaysBackground = false) => action();
        public BufferHandle CreateBuffer(int size, BufferAccess access = BufferAccess.Default) => Handle();
        public BufferHandle CreateBuffer(nint pointer, int size) => Handle();
        public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> storageBuffers) => Handle();
        public IImageArray CreateImageArray(int size, bool isBuffer) => Fake.Create<IImageArray>();
        public IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info) => Fake.Create<IProgram>();
        public ISampler CreateSampler(SamplerCreateInfo info) => Fake.Create<ISampler>();
        public ITexture CreateTexture(TextureCreateInfo info)
        {
            RecordingTexture texture = new(info);
            Textures.Add(texture);
            return texture;
        }
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
            return System.Runtime.CompilerServices.Unsafe.As<ulong, BufferHandle>(ref value);
        }
    }

    private sealed class Session : IDisposable
    {
        public readonly MemoryBlock Backing = new(GuestSize);
        public readonly Ryujinx.Cpu.Jit.MemoryManager Cpu;
        public readonly RecordingRenderer Renderer = new();
        public readonly GpuContext Gpu;
        public readonly MemoryManager GpuMemory;
        public readonly TexturePool Pool;
        private ulong _nextTexture;

        public Session(int maximumId = MaximumId)
        {
            Cpu = new Ryujinx.Cpu.Jit.MemoryManager(Backing, 1UL << 36);
            Cpu.Map(GuestBase, 0, GuestSize, MemoryMapFlags.None);
            Cpu.IncrementReferenceCount();
            Gpu = new GpuContext(Renderer, new DirtyHacks(Array.Empty<ulong>()));
            // The pass and the pools run on the GPU thread, as Switch.ProcessFrame does.
            Gpu.SetGpuThread();
            Gpu.RegisterProcess(1, Cpu);
            GpuMemory = Gpu.CreateMemoryManager(1, GuestSize);
            GpuMemory.Map(GuestBase + TextureOffset, TextureGpuVa, TextureSpace, PteKind.Pitch);
            GpuChannel channel = Gpu.CreateChannel();
            channel.BindMemory(GpuMemory);
            Pool = new TexturePool(Gpu, channel, GuestBase + PoolOffset, maximumId);
        }

        // A linear RGBA8 texture of width x height in guest memory, filled with a pattern, and its pool descriptor.
        public (ulong Address, int Size) AddTexture(int id, int width, int height, byte seed)
        {
            ulong offset = _nextTexture;
            int size = width * height * 4;
            _nextTexture += (ulong)((size + 0xFFFF) & ~0xFFFF);
            byte[] data = new byte[size];
            for (int i = 0; i < size; i++) data[i] = (byte)(seed * 31 + i * 7 + (i >> 9));
            Cpu.Write(GuestBase + TextureOffset + offset, data);
            ulong gpuVa = TextureGpuVa + offset;
            uint[] words =
            [
                0x24908 | (2u << 19) | (3u << 22) | (4u << 25) | (5u << 28), // A8B8G8R8 Unorm, RGBA swizzle
                (uint)gpuVa,
                (uint)(gpuVa >> 32) | (2u << 21),                             // Linear descriptor
                (uint)(width * 4) >> 5,                                       // stride, 1 level
                (uint)(width - 1) | (1u << 23),                               // Texture2D
                (uint)(height - 1),
                0,
                0,
            ];
            Cpu.Write(GuestBase + PoolOffset + (ulong)id * 32, MemoryMarshal.AsBytes(words.AsSpan()));
            return (GuestBase + TextureOffset + offset, size);
        }

        public byte[] Guest(ulong address, int size)
        {
            byte[] data = new byte[size];
            Cpu.Read(address, data);
            return data;
        }

        public void Dispose() => Backing.Dispose();
    }

    private static int Epoch(Session s, int epoch)
    {
        s.Gpu.TextureUseEpoch = epoch;
        return epoch;
    }

    private static Dictionary<string, object> Stats(GpuContext.ColdTextureStats stats) => new()
    {
        ["poolOnly"] = stats.PoolOnly,
        ["poolOnlyBytes"] = stats.PoolOnlyBytes,
        ["cold"] = stats.Cold,
        ["coldBytes"] = stats.ColdBytes,
        ["released"] = stats.Released,
        ["releasedBytes"] = stats.ReleasedBytes,
        ["gpuData"] = stats.GpuData,
        ["gpuDataBytes"] = stats.GpuDataBytes,
        ["kept"] = stats.Kept,
    };

    private static RecordingTexture Host(Texture texture) => (RecordingTexture)texture.HostTexture;

    private static int LinesNow()
    {
        lock (Lines) return Lines.Count;
    }

    private static List<string> LinesSince(int start)
    {
        lock (Lines) return Lines.Skip(start).ToList();
    }

    // (a) A cold, unmodified, pool-only texture is released when the device is short and re-created on the next fetch
    // from guest memory with the same data; a texture used by a cached binding or a bindless array (synchronised, not
    // fetched) and one fetched recently stay.
    private static Dictionary<string, object> ReleaseAndRecreate()
    {
        using Session s = new();
        (ulong address, int size) = s.AddTexture(3, 256, 256, 3);
        s.AddTexture(4, 256, 256, 4);
        s.AddTexture(5, 256, 256, 5);
        s.Gpu.AdvanceSequence();
        Epoch(s, 1000);
        Texture first = s.Pool.Get(3);
        Texture boundOnly = s.Pool.Get(4);
        Texture fetched = s.Pool.Get(5);
        byte[] firstUpload = Host(first).Uploads.Single();
        byte[] guest = s.Guest(address, size);
        Epoch(s, 1050);
        boundOnly.SynchronizeMemory(); // what TextureBindingsManager's cached path and a bindless array do per draw
        Epoch(s, 1055);
        s.Pool.Get(5);
        Epoch(s, 1061);
        GpuContext.ColdTextureStats measured = s.Gpu.MeasurePoolTextures(out _, out _);
        int sequence = first.InvalidatedSequence;
        long deltaLog = s.Pool.DeltaLogCount;
        int lines = LinesNow();
        bool ran = s.Gpu.ReleaseColdTextures(8, 1061_000, out GpuContext.ColdTextureStats pass);
        List<string> passLines = LinesSince(lines);
        bool released = s.Pool.GetCachedItem(3) == null && Host(first).Releases == 1 && first.InvalidatedSequence != sequence;
        bool othersStay = s.Pool.GetCachedItem(4) == boundOnly && s.Pool.GetCachedItem(5) == fetched &&
                          Host(boundOnly).Releases == 0 && Host(fetched).Releases == 0;
        // Next fetch, after the reload window: an ordinary re-creation, not a reload.
        Epoch(s, 1500);
        int created = s.Renderer.Textures.Count;
        Texture second = s.Pool.Get(3);
        byte[] secondUpload = second == null ? [] : Host(second).Uploads.Single();
        GpuContext.ColdTextureStats after = s.Gpu.MeasurePoolTextures(out int reloads, out int pinned);
        return new()
        {
            ["passRan"] = ran,
            ["measuredBefore"] = Stats(measured),
            ["pass"] = Stats(pass),
            ["passLines"] = passLines,
            ["released"] = released,
            ["deltaLogged"] = s.Pool.DeltaLogCount - deltaLog,
            ["boundOnlyAndFetchedStay"] = othersStay,
            ["recreated"] = second != null && !ReferenceEquals(second, first) && s.Renderer.Textures.Count == created + 1,
            ["sameInfo"] = second != null && second.Info.Width == first.Info.Width && second.Info.Height == first.Info.Height &&
                           second.Format == first.Format && second.Info.GpuAddress == first.Info.GpuAddress,
            ["firstUploadIsGuest"] = firstUpload.AsSpan().SequenceEqual(guest),
            ["secondUploadIsGuest"] = secondUpload.AsSpan().SequenceEqual(guest),
            ["uploadBytes"] = secondUpload.Length,
            ["sameOnNextFetch"] = ReferenceEquals(second, s.Pool.Get(3)),
            ["lateReloadCounted"] = reloads,
            ["pinnedAfterLateReload"] = pinned,
            ["measuredAfter"] = Stats(after),
        };
    }

    // (b) A pool-only texture whose group holds GPU-written data (a render target the auto delete cache dropped after an
    // untracked flush, which keeps the modified flags) is never released nor read back, pass after pass.
    private static Dictionary<string, object> ModifiedKept()
    {
        using Session s = new();
        s.AddTexture(6, 256, 256, 6);
        s.Gpu.AdvanceSequence();
        Epoch(s, 1000);
        Texture texture = s.Pool.Get(6);
        texture.SignalModified(); // a GPU write: the texture is lifted into the auto delete cache
        bool lifted = texture.CacheNode != null && !texture.HasOneReference();
        object cache = typeof(TextureCache).GetField("_cache", BindingFlags.NonPublic | BindingFlags.Instance)!
            .GetValue(s.Gpu.PhysicalMemoryRegistry.Values.Single().TextureCache)!;
        cache.GetType().GetMethod("Remove")!.Invoke(cache, [texture, false]);
        bool poolOnlyModified = texture.HasOneReference() && texture.CacheNode == null && texture.Group.AnyHandleModified();
        List<Dictionary<string, object>> passes = [];
        for (int pass = 0; pass < 5; pass++)
        {
            int epoch = Epoch(s, 1100 + pass * 100);
            s.Gpu.ReleaseColdTextures(5, epoch * 1000L, out GpuContext.ColdTextureStats stats);
            passes.Add(Stats(stats));
        }
        return new()
        {
            ["liftedOnGpuWrite"] = lifted,
            ["poolOnlyWithGpuData"] = poolOnlyModified,
            ["passes"] = passes,
            ["stillInPool"] = s.Pool.GetCachedItem(6) == texture,
            ["hostReleases"] = Host(texture).Releases,
            ["hostReads"] = Host(texture).Reads,
            ["stillModified"] = texture.Group.AnyHandleModified(),
        };
    }

    // (c) A texture fetched again soon after its release pins its slot: it is never released again (no loop), the
    // counters show it, and the age doubles when half the released textures came back.
    private static Dictionary<string, object> NoLoop()
    {
        using Session s = new();
        s.AddTexture(7, 256, 256, 7);
        s.Gpu.AdvanceSequence();
        Epoch(s, 1000);
        s.Pool.Get(7);
        int ageBefore = s.Gpu.ColdTextureAgeSeconds;
        Epoch(s, 1061);
        s.Gpu.ReleaseColdTextures(8, 1061_000, out GpuContext.ColdTextureStats first);
        Epoch(s, 1062);
        Texture reloaded = s.Pool.Get(7); // used again one second after its release
        GpuContext.ColdTextureStats measured = s.Gpu.MeasurePoolTextures(out int reloads, out int pinned);
        List<Dictionary<string, object>> later = [];
        int lines = LinesNow();
        for (int pass = 0; pass < 6; pass++)
        {
            int epoch = Epoch(s, 1200 + pass * 200);
            s.Gpu.ReleaseColdTextures(8, epoch * 1000L, out GpuContext.ColdTextureStats stats);
            later.Add(Stats(stats));
        }
        return new()
        {
            ["firstPass"] = Stats(first),
            ["reloads"] = reloads,
            ["pinnedSlots"] = pinned,
            ["measuredAfterReload"] = Stats(measured),
            ["laterPasses"] = later,
            ["laterLines"] = LinesSince(lines),
            ["stillInPool"] = s.Pool.GetCachedItem(7) == reloaded,
            ["hostTexturesCreatedForSlot"] = s.Renderer.Textures.Count,
            ["ageBefore"] = ageBefore,
            ["ageAfter"] = s.Gpu.ColdTextureAgeSeconds,
        };
    }

    // A texture with a format alias (the alias may be bound where only the alias is synchronised) is never released.
    private static Dictionary<string, object> AliasKept()
    {
        using Session s = new();
        s.AddTexture(11, 256, 256, 11);
        s.Gpu.AdvanceSequence();
        Epoch(s, 1000);
        s.Pool.GetForBinding(11, new FormatInfo(Format.R32Uint, 1, 1, 4, 1), out Texture alias);
        Texture texture = s.Pool.GetCachedItem(11);
        List<Dictionary<string, object>> passes = [];
        for (int pass = 0; pass < 3; pass++)
        {
            int epoch = Epoch(s, 1100 + pass * 100);
            s.Gpu.ReleaseColdTextures(8, epoch * 1000L, out GpuContext.ColdTextureStats stats);
            passes.Add(Stats(stats));
        }
        return new()
        {
            ["aliasCreated"] = alias != null && texture != null && !ReferenceEquals(alias, texture) && alias.Format == Format.R32Uint,
            ["passes"] = passes,
            ["stillInPool"] = s.Pool.GetCachedItem(11) == texture,
            ["hostReleases"] = s.Renderer.Textures.Sum(t => t.Releases),
        };
    }

    // GPU-thread cost of a measure and of a pass over a Hogwarts-sized pool (524288 slots) holding 2000 textures, all
    // used recently (nothing to release), on this host: an upper bound of the scan, not an iPhone timing.
    private static Dictionary<string, object> ScanCost()
    {
        using Session s = new(524287);
        const int count = 2000;
        for (int id = 0; id < count; id++) s.AddTexture(id * 262, 64, 64, (byte)id);
        s.Gpu.AdvanceSequence();
        Epoch(s, 1000);
        for (int id = 0; id < count; id++) s.Pool.Get(id * 262);
        double measure = double.MaxValue, pass = double.MaxValue;
        int poolOnly = 0, released = 0;
        for (int round = 0; round < 5; round++)
        {
            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            poolOnly = s.Gpu.MeasurePoolTextures(out _, out _).PoolOnly;
            measure = Math.Min(measure, System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds);
            start = System.Diagnostics.Stopwatch.GetTimestamp();
            s.Gpu.ReleaseColdTextures(8, 2_000_000L + round * 10_000, out GpuContext.ColdTextureStats stats);
            pass = Math.Min(pass, System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds);
            released += stats.Released;
        }
        return new()
        {
            ["slots"] = 524288,
            ["textures"] = count,
            ["poolOnly"] = poolOnly,
            ["released"] = released,
            ["measureMs"] = Math.Round(measure, 3),
            ["passMs"] = Math.Round(pass, 3),
        };
    }

    // (d) Nothing happens while the device is not short (or unknown), nor within 10 s of a pass.
    private static Dictionary<string, object> NotShort()
    {
        using Session s = new();
        s.AddTexture(8, 256, 256, 8);
        s.AddTexture(9, 256, 256, 9);
        s.Gpu.AdvanceSequence();
        Epoch(s, 1000);
        Texture a = s.Pool.Get(8);
        Texture b = s.Pool.Get(9);
        Epoch(s, 5000);
        int lines = LinesNow();
        Dictionary<string, object> devices = new();
        foreach (int device in new[] { -1, 11, 12, 27, 50, 100 })
        {
            devices[device.ToString()] = s.Gpu.ReleaseColdTextures(device, 5_000_000, out GpuContext.ColdTextureStats stats) || stats.Released != 0;
        }
        int linesNotShort = LinesSince(lines).Count;
        bool untouched = s.Pool.GetCachedItem(8) == a && s.Pool.GetCachedItem(9) == b && Host(a).Releases == 0 && Host(b).Releases == 0;
        // At the threshold (10 %) a pass runs and releases both cold textures; the interval then holds the next pass
        // back for 10 s.
        bool atThreshold = s.Gpu.ReleaseColdTextures(10, 6_000_000, out GpuContext.ColdTextureStats firstPass);
        s.AddTexture(10, 256, 256, 10);
        s.Gpu.AdvanceSequence();
        Epoch(s, 5000);
        s.Pool.Get(10);
        Epoch(s, 6100);
        bool within = s.Gpu.ReleaseColdTextures(5, 6_009_999, out GpuContext.ColdTextureStats withinStats);
        bool afterInterval = s.Gpu.ReleaseColdTextures(5, 6_010_000, out GpuContext.ColdTextureStats afterStats);
        return new()
        {
            ["ranOrReleasedPerDevice"] = devices,
            ["linesWhileNotShort"] = linesNotShort,
            ["untouchedWhileNotShort"] = untouched,
            ["ranAtThreshold10"] = atThreshold,
            ["releasedAtThreshold10"] = firstPass.Released,
            ["ranWithin10s"] = within,
            ["releasedWithin10s"] = withinStats.Released,
            ["ranAfter10s"] = afterInterval,
            ["releasedAfter10s"] = afterStats.Released,
        };
    }

    // (e) Per-pass bounds: at most 64 MiB and 256 textures a pass, one journal line a pass.
    private static Dictionary<string, object> Bounds(int count, int width, int height)
    {
        using Session s = new();
        for (int id = 0; id < count; id++) s.AddTexture(id, width, height, (byte)id);
        s.Gpu.AdvanceSequence();
        Epoch(s, 1000);
        for (int id = 0; id < count; id++) s.Pool.Get(id);
        List<Dictionary<string, object>> passes = [];
        int lines = LinesNow();
        for (int pass = 0; pass < 4; pass++)
        {
            int epoch = Epoch(s, 1100 + pass * 10);
            bool ran = s.Gpu.ReleaseColdTextures(9, epoch * 1000L, out GpuContext.ColdTextureStats stats);
            Dictionary<string, object> entry = Stats(stats);
            entry["ran"] = ran;
            passes.Add(entry);
        }
        int remaining = Enumerable.Range(0, count).Count(id => s.Pool.GetCachedItem(id) != null);
        return new()
        {
            ["textures"] = count,
            ["bytesEach"] = width * height * 4,
            ["passes"] = passes,
            ["lines"] = LinesSince(lines).Count,
            ["remainingInPool"] = remaining,
            ["hostReleases"] = s.Renderer.Textures.Sum(t => t.Releases),
        };
    }

    private static Dictionary<string, object> Run(Func<Dictionary<string, object>> scenario)
    {
        try { return scenario(); }
        catch (Exception error) { return new() { ["harnessException"] = error.ToString() }; }
    }

    public static void Main(string[] args)
    {
        Logger.RemoveTarget("console");
        Logger.SetEnable(LogLevel.Info, true);
        Logger.Updated += (_, entry) =>
        {
            if (entry.Message.Contains(Tag))
            {
                lock (Lines) Lines.Add(entry.Message);
            }
        };
        Dictionary<string, object> report = new()
        {
            ["releaseAndRecreate"] = Run(ReleaseAndRecreate),
            ["modifiedKept"] = Run(ModifiedKept),
            ["noLoop"] = Run(NoLoop),
            ["notShort"] = Run(NotShort),
            ["aliasKept"] = Run(AliasKept),
            ["scanCost"] = Run(ScanCost),
            ["byteBound"] = Run(() => Bounds(100, 512, 512)),
            ["countBound"] = Run(() => Bounds(300, 64, 64)),
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
