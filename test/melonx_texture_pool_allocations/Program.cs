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
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;

// Texture pool churn on the production GPU texture path (test/melonx_texture_pool_allocations_test.py builds it against the
// control and the candidate engine). The compiled production TextureManager, TextureBindingsManager, TexturePool,
// TextureCache, AutoDeleteCache and Texture run on guest memory (Ryujinx.Cpu MemoryManager) with a doubled renderer: host
// textures record their creation, views, uploads (with the first texel of level 0) and release; the pipeline is a no-op.
// A bindless fragment array of 512 combined samplers indexed by pool id (as Hogwarts Legacy's set 4) is committed once per
// pass; a pass of a "ticked" scenario first presents a frame (TextureCache.Tick, as Window.Present). Every texture holds a
// marker in its first texel (family, index, version); after each pass every element of the array must hold a live host
// texture of the descriptor's size and swizzle whose uploaded marker is the one guest memory holds now, read through the
// GPU address (so remaps count). Measured after warm-up, per scenario: host textures and views created, uploads and bytes,
// releases, bytes allocated and time of the production work of a pass (Tick + commit, one scope), live host texture bytes
// (peak, end) and, on an engine that has it, the short cache's retained list. Prints one JSON object.
static class Program
{
    private const ulong GuestBase = 0x10000000;
    private const ulong GuestSize = 512UL << 20;
    private const ulong PoolOffset = 0;                 // texture pool, 32 bytes per entry
    private const ulong SamplerOffset = 1UL << 20;      // sampler pool
    private const ulong CbufOffset = 2UL << 20;
    private const ulong TextureOffset = 4UL << 20;      // big textures: 256 KiB each (BigSpacing), indices 1..BigTextures-1
    private const ulong BigSpacing = 0x40000;
    private const int BigTextures = 1100;
    private const ulong SmallOffset = 280UL << 20;      // small textures: 8x8, 4 KiB each, indices 0..SmallTextures-1
    private const ulong SmallSpacing = 0x1000;
    private const int SmallTextures = 1300;
    private const ulong AltOffset = 288UL << 20;        // other guest pages a texture's GPU range is remapped to
    private const ulong GpuBase = 0x40000000;
    private const int MaximumId = 511;

    public sealed class RecordingTexture : ITexture
    {
        public static int Created, Views, Uploads, Releases, DoubleReleases;
        public static long UploadBytes, LiveBytes, PeakLiveBytes;
        public readonly TextureCreateInfo Info;
        public readonly int FirstLevel;
        public readonly RecordingTexture Parent;
        private readonly long _bytes;
        public uint Marker = 0xFFFFFFFF;
        public bool Released;

        public RecordingTexture(TextureCreateInfo info, RecordingTexture parent = null, int firstLevel = 0)
        {
            Info = info;
            Parent = parent;
            FirstLevel = firstLevel;
            if (parent == null)
            {
                Created++;
                _bytes = (long)info.GetTotalSize();
                LiveBytes += _bytes;
                PeakLiveBytes = Math.Max(PeakLiveBytes, LiveBytes);
            }
            else
            {
                Views++;
            }
        }

        public int Width => Info.Width;
        public int Height => Info.Height;
        // GPU copies between host textures (copy dependencies of overlapping textures) carry level 0's first texel.
        private void CopyMarker(ITexture destination, bool levelZero)
        {
            if (levelZero && destination is RecordingTexture target) Root(target).Marker = Root(this).Marker;
        }
        public void CopyTo(ITexture destination, int firstLayer, int firstLevel) =>
            CopyMarker(destination, FirstLevel == 0 && firstLayer == 0 && firstLevel + ((destination as RecordingTexture)?.FirstLevel ?? 0) == 0);
        public void CopyTo(ITexture destination, int srcLayer, int dstLayer, int srcLevel, int dstLevel) =>
            CopyMarker(destination, srcLayer == 0 && dstLayer == 0 && srcLevel + FirstLevel == 0 && dstLevel + ((destination as RecordingTexture)?.FirstLevel ?? 0) == 0);
        public void CopyTo(ITexture destination, Extents2D srcRegion, Extents2D dstRegion, bool linearFilter) =>
            CopyMarker(destination, FirstLevel == 0 && srcRegion.X1 == 0 && srcRegion.Y1 == 0 && dstRegion.X1 == 0 && dstRegion.Y1 == 0);
        public void CopyTo(BufferRange range, int layer, int level, int stride) { }
        public ITexture CreateView(TextureCreateInfo info, int firstLayer, int firstLevel) => new RecordingTexture(info, this, firstLevel);
        public PinnedSpan<byte> GetData() => default;
        public PinnedSpan<byte> GetData(int layer, int level) => default;

        private void Upload(MemoryOwner<byte> data, bool levelZero)
        {
            Uploads++;
            UploadBytes += data.Length;
            if (levelZero && data.Length >= 4)
            {
                Root(this).Marker = MemoryMarshal.Read<uint>(data.Span);
            }
            data.Dispose();
        }

        public void SetData(MemoryOwner<byte> data) => Upload(data, true);
        public void SetData(MemoryOwner<byte> data, int layer, int level) => Upload(data, layer == 0 && level + FirstLevel == 0);
        public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region) =>
            Upload(data, layer == 0 && level + FirstLevel == 0 && region.X == 0 && region.Y == 0);
        public void SetStorage(BufferRange buffer) { }

        public void Release()
        {
            if (Released)
            {
                DoubleReleases++;
                return;
            }
            Released = true;
            if (Parent == null)
            {
                Releases++;
                LiveBytes -= _bytes;
            }
        }
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
        public void Dispose() { }
    }

    private sealed class RecordingRenderer : IRenderer
    {
        private int _buffers;
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
        public ISampler CreateSampler(SamplerCreateInfo info) => new RecordingSampler();
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

    private static RecordingTexture Root(RecordingTexture t) => t.Parent == null ? t : Root(t.Parent);

    // Texture identity: (family, index) -> GPU address, size, levels. Big k: own 256 KiB, unique size, two levels. Small s:
    // 8x8, one level, own 4 KiB page.
    private static ulong BigVa(int k) => GpuBase + TextureOffset + (ulong)k * BigSpacing;
    private static int BigWidth(int k) => 64 + 8 * (k % 64);
    private static int BigHeight(int k) => 64 + k / 64;
    private static ulong SmallVa(int s) => GpuBase + SmallOffset + (ulong)s * SmallSpacing;

    private static Ryujinx.Cpu.Jit.MemoryManager _cpu;
    private static MemoryManager _gpuMemory;
    private static readonly int[] BigVersion = new int[BigTextures];
    private static readonly int[] SmallVersion = new int[SmallTextures];

    private static uint MarkerOf(int family, int index, int version) => (uint)(family << 30) | (uint)(index << 12) | (uint)(version & 0xFFF);

    private static void WriteMarker(ulong guestAddress, uint marker)
    {
        Span<byte> bytes = stackalloc byte[4];
        MemoryMarshal.Write(bytes, in marker);
        _cpu.Write(guestAddress, bytes);
    }

    // What a pool entry names: GPU address, size, levels and swizzle.
    private struct EntryState
    {
        public ulong Va;
        public int Width, Height, Levels;
        public bool Red, Snorm;
    }

    private static readonly EntryState[] Entries = new EntryState[MaximumId + 1];

    private static void Entry(int id, ulong va, int width, int height, int levels, bool red = false, bool snorm = false)
    {
        Span<uint> words = stackalloc uint[8];
        // A8B8G8R8 Unorm (or Snorm: component types 1), RGBA or RRRA
        words[0] = (snorm ? 0x12488u : 0x24908u) | (2u << 19) | ((red ? 2u : 3u) << 22) | ((red ? 2u : 4u) << 25) | (5u << 28);
        words[1] = (uint)va;
        words[2] = (uint)(va >> 32) | (2u << 21);                       // linear
        words[3] = ((uint)(width * 4) >> 5) | ((uint)(levels - 1) << 28); // stride, levels
        words[4] = (uint)(width - 1) | (1u << 23);                      // Texture2D
        words[5] = (uint)(height - 1);
        words[6] = 0;
        words[7] = (uint)(levels - 1) << 4;                             // base level 0, max level
        _cpu.Write(GuestBase + PoolOffset + (ulong)id * 32, MemoryMarshal.AsBytes(words));
        Entries[id] = new EntryState { Va = va, Width = width, Height = height, Levels = levels, Red = red, Snorm = snorm };
    }

    // Pitch (linear) textures have one level on the hardware (a two-level linear texture overlapped by one of another height
    // makes TextureGroup.GenerateHandles throw in the control engine too).
    private static void Big(int id, int k, bool red = false, int heightDelta = 0, bool snorm = false)
    {
        // Guest size of a one-level pitch texture: stride (width * 4, a multiple of 32) * height; it must stay within the
        // texture's own 256 KiB (no overlap with the next one).
        if ((ulong)(BigWidth(k) * 4 * (BigHeight(k) + heightDelta)) > BigSpacing) throw new InvalidOperationException($"texture {k} overlaps the next one");
        Entry(id, BigVa(k), BigWidth(k), BigHeight(k) + heightDelta, 1, red, snorm);
    }
    private static void Small(int id, int s) => Entry(id, SmallVa(s), 8, 8, 1);

    private static CachedShaderBindings Bindings(int stages, int stage, TextureBindingInfo[] textures)
    {
        var bindings = (CachedShaderBindings)RuntimeHelpers.GetUninitializedObject(typeof(CachedShaderBindings));
        var t = Enumerable.Range(0, stages).Select(_ => Array.Empty<TextureBindingInfo>()).ToArray();
        var i = Enumerable.Range(0, stages).Select(_ => Array.Empty<TextureBindingInfo>()).ToArray();
        t[stage] = textures;
        void Set(string name, object value) =>
            typeof(CachedShaderBindings).GetField($"<{name}>k__BackingField", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(bindings, value);
        Set(nameof(CachedShaderBindings.TextureBindings), t);
        Set(nameof(CachedShaderBindings.ImageBindings), i);
        Set(nameof(CachedShaderBindings.TextureCounts), new int[stages]);
        Set(nameof(CachedShaderBindings.MaxTextureBinding), textures.Max(b => b.Binding));
        Set(nameof(CachedShaderBindings.MaxImageBinding), 0);
        return bindings;
    }

    // A specialization state with no recorded texture state: every MatchesTexture/MatchesImage returns true.
    private static ShaderSpecializationState Spec(int stages)
    {
        var spec = (ShaderSpecializationState)RuntimeHelpers.GetUninitializedObject(typeof(ShaderSpecializationState));
        foreach (string name in new[] { "_textureByBinding", "_imageByBinding" })
        {
            FieldInfo field = typeof(ShaderSpecializationState).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!;
            Type inner = field.FieldType.GetElementType()!;
            Array outer = Array.CreateInstance(inner, stages);
            for (int i = 0; i < stages; i++) outer.SetValue(Array.CreateInstance(inner.GetElementType()!, 8), i);
            field.SetValue(spec, outer);
        }
        return spec;
    }

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
        MemoryManager gpuMemory = _gpuMemory = gpu.CreateMemoryManager(1, GuestSize);
        gpuMemory.Map(GuestBase, GpuBase, GuestSize, PteKind.Pitch);
        GpuChannel channel = gpu.CreateChannel();
        channel.BindMemory(gpuMemory);
        TextureManager textures = channel.TextureManager;
        TextureCache cache = gpuMemory.Physical.TextureCache;
        GraphicsConfig.EnableHostMemoryBudgetTracking = true;

        PropertyInfo reuseProperty = typeof(TextureCache).GetProperty("ShortCacheReuse");
        bool candidate = reuseProperty != null;
        Func<string, long> reuseField = name =>
        {
            if (reuseProperty == null) return 0;
            object stats = reuseProperty.GetValue(cache);
            object value = stats.GetType().GetField(name).GetValue(stats);
            return Convert.ToInt64(value);
        };

        for (int k = 1; k < BigTextures; k++) WriteMarker(GuestBase + TextureOffset + (ulong)k * BigSpacing, MarkerOf(1, k, 0));
        for (int s = 0; s < SmallTextures; s++) WriteMarker(GuestBase + SmallOffset + (ulong)s * SmallSpacing, MarkerOf(2, s, 0));
        for (int i = 0; i < 64; i++) WriteMarker(GuestBase + AltOffset + (ulong)i * BigSpacing, MarkerOf(3, i, 0));

        for (int id = 1; id <= MaximumId; id++) Big(id, id);

        int direct = TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct);
        var arrayBinding = new TextureBindingInfo(Target.Texture2D, 4, 0, MaximumId + 1, 0, direct, TextureUsageFlags.None, false);
        textures.SetGraphicsTexturePool(GpuBase + PoolOffset, MaximumId);
        textures.SetGraphicsSamplerPool(GpuBase + SamplerOffset, MaximumId, Ryujinx.Graphics.Gpu.Engine.Types.SamplerIndex.Independently);
        textures.SetGraphicsTextureBufferIndex(0);
        textures.SetGraphicsBindings(Bindings(5, 4, new[] { arrayBinding }));
        channel.BufferManager.SetGraphicsUniformBuffer(4, 0, GpuBase + CbufOffset + 0x1000, 0x100);
        var spec = Spec(6);
        var errors = new List<string>();
        var observation = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);

        // Production pool items (the Gpu Texture of an entry), for the layout check and the render target lift.
        FieldInfo bindingsField = typeof(TextureManager).GetField("_gpBindingsManager", BindingFlags.Instance | BindingFlags.NonPublic)!;
        FieldInfo poolField = bindingsField.FieldType.GetField("_texturePool", BindingFlags.Instance | BindingFlags.NonPublic)!;
        Texture PoolTexture(int id)
        {
            object pool = poolField.GetValue(bindingsField.GetValue(textures));
            FieldInfo items = pool.GetType().BaseType!.GetField("Items", BindingFlags.Instance | BindingFlags.NonPublic)!;
            return ((Texture[])items.GetValue(pool))[id];
        }

        void Check(string step, int first, int count)
        {
            RecordingTextureArray array = Arrays[^1];
            Span<byte> record = stackalloc byte[16];
            for (int id = first; id < first + count; id++)
            {
                EntryState e = Entries[id];
                var t = array.Textures[id] as RecordingTexture;
                uint expected = gpuMemory.Read<uint>(e.Va);
                string problem = null;
                if (t == null) problem = "no texture";
                else if (t.Released || Root(t).Released) problem = "a released host texture";
                else if (Root(t).Width != e.Width || Root(t).Height != e.Height) problem = $"size {Root(t).Width}x{Root(t).Height}, descriptor {e.Width}x{e.Height}";
                else if (Root(t).Marker != expected) problem = $"data {Root(t).Marker:x8}, guest memory {expected:x8}";
                else if (t.Info.SwizzleG != (e.Red ? SwizzleComponent.Red : SwizzleComponent.Green)) problem = $"swizzle {t.Info.SwizzleG}";
                else if (t.Info.Format != (e.Snorm ? Format.R8G8B8A8Snorm : Format.R8G8B8A8Unorm)) problem = $"format {t.Info.Format}";
                if (problem != null && errors.Count < 12) errors.Add($"{step}: element {id}: {problem}");
                MemoryMarshal.Write(record, in id);
                uint marker = t == null ? 0 : Root(t).Marker;
                MemoryMarshal.Write(record[4..], in marker);
                int size = t == null ? 0 : Root(t).Width * 1000 + Root(t).Height;
                MemoryMarshal.Write(record[8..], in size);
                int swizzle = t == null ? -1 : (int)t.Info.SwizzleG | ((int)t.Info.Format << 8);
                MemoryMarshal.Write(record[12..], in swizzle);
                observation.AppendData(record);
            }
        }

        void Pass(bool tick)
        {
            if (tick) cache.Tick();
            gpu.AdvanceSequence();
            textures.CommitGraphicsBindings(spec, out _);
        }

        // Guest layout (the real size of each texture, from the production textures, against its spacing; no overlap).
        Pass(false);
        Check("first", 1, MaximumId);
        var layout = new List<(ulong Start, ulong End)>();
        for (int id = 1; id <= MaximumId; id++)
        {
            Texture texture = PoolTexture(id);
            if (texture == null || texture.Size > BigSpacing) errors.Add($"layout: entry {id} size {texture?.Size} above the {BigSpacing} B spacing");
            if (texture != null) layout.Add((texture.Info.GpuAddress, texture.Info.GpuAddress + texture.Size));
        }
        layout.Sort();
        for (int i = 1; i < layout.Count; i++) if (layout[i].Start < layout[i - 1].End) errors.Add($"layout: overlap at {layout[i].Start:x}");
        ulong largestBig = (ulong)layout.Max(r => (long)(r.End - r.Start));

        // JIT warm-up of the churn path on entries 64..127 (textures 64..127 and 1000..1063), then the entries are restored
        // and 70 presents let anything retained from it expire. Same inputs for both engines.
        for (int p = 0; p < 240; p++)
        {
            for (int i = 0; i < 64; i++) Big(64 + i, (p % 4) == 0 ? 64 + i : 1000 + i);
            Pass(true);
        }
        Thread.Sleep(600);
        for (int i = 0; i < 64; i++) Big(64 + i, 64 + i);
        for (int p = 0; p < 70; p++) Pass(true);
        Check("warm-up", 1, MaximumId);

        var results = new Dictionary<string, object>();
        string[] reuseNames = { "Reused", "ReleasedByAge", "RefusedByBound", "ReleasedAll", "ReleasedInvalid", "DestroyedOnExpiry" };

        void Measure(string name, int passes, bool tick, int first, int count, Action<int> change, int warmup = 8)
        {
            for (int p = 0; p < warmup; p++) { change(p); Pass(tick); Check(name + " warm-up", first, count); }
            observation.AppendData(Encoding.UTF8.GetBytes(name));
            int created = RecordingTexture.Created, views = RecordingTexture.Views, uploads = RecordingTexture.Uploads;
            int releases = RecordingTexture.Releases;
            long uploadBytes = RecordingTexture.UploadBytes;
            RecordingTexture.PeakLiveBytes = RecordingTexture.LiveBytes;
            long startLive = RecordingTexture.LiveBytes;
            var reuseStart = reuseNames.ToDictionary(n => n, reuseField);
            long maxRetained = 0, maxRetainedBytes = 0;
            long bytes = 0;
            var watch = new Stopwatch();
            var scenario = Stopwatch.StartNew();
            for (int p = warmup; p < warmup + passes; p++)
            {
                change(p);
                long before = GC.GetAllocatedBytesForCurrentThread();
                watch.Start();
                Pass(tick);
                watch.Stop();
                bytes += GC.GetAllocatedBytesForCurrentThread() - before;
                Check(name, first, count);
                maxRetained = Math.Max(maxRetained, reuseField("Retained"));
                maxRetainedBytes = Math.Max(maxRetainedBytes, reuseField("RetainedBytes"));
            }
            scenario.Stop();
            var result = new Dictionary<string, object>
            {
                ["passes"] = passes,
                ["changedElements"] = count,
                ["texturesCreated"] = RecordingTexture.Created - created,
                ["viewsCreated"] = RecordingTexture.Views - views,
                ["uploads"] = RecordingTexture.Uploads - uploads,
                ["uploadBytes"] = RecordingTexture.UploadBytes - uploadBytes,
                ["hostTexturesReleased"] = RecordingTexture.Releases - releases,
                ["bytesPerPass"] = bytes / passes,
                ["msPerPass"] = Math.Round(watch.Elapsed.TotalMilliseconds / passes, 4),
                ["scenarioMs"] = Math.Round(scenario.Elapsed.TotalMilliseconds, 2),
                ["liveHostBytesStart"] = startLive,
                ["liveHostBytesPeak"] = RecordingTexture.PeakLiveBytes,
                ["liveHostBytesEnd"] = RecordingTexture.LiveBytes,
            };
            if (candidate)
            {
                foreach (string n in reuseNames) result[n] = reuseField(n) - reuseStart[n];
                result["maxRetained"] = maxRetained;
                result["maxRetainedBytes"] = maxRetainedBytes;
                result["retainedEnd"] = reuseField("Retained");
                result["retainedBytesEnd"] = reuseField("RetainedBytes");
            }
            results[name] = result;
        }

        Measure("unchanged", 100, false, 1, MaximumId, _ => { });
        // No present between: 64 entries alternate their own texture and texture id+511 (the short cache's two ticks).
        Measure("swapNoPresent", 200, false, 1, 64, p => { for (int i = 0; i < 64; i++) Big(1 + i, (p & 1) == 0 ? 1 + i + MaximumId : 1 + i); });
        // The cycle: 64 entries name their own texture for one presented frame, texture id+511 for three.
        Measure("returnAfterExpiry", 120, true, 130, 64, p => { for (int i = 0; i < 64; i++) Big(130 + i, (p % 4) == 0 ? 130 + i : 130 + i + MaximumId); });
        // Back after one present (within the two ticks).
        Measure("returnBeforeExpiry", 120, true, 200, 64, p => { for (int i = 0; i < 64; i++) Big(200 + i, (p % 2) == 0 ? 200 + i : 200 + i + MaximumId); });
        // Back after 70 presents (beyond the 60-present age): recreated by both engines.
        Measure("returnAfterAge", 216, true, 270, 16, p => { for (int i = 0; i < 16; i++) Big(270 + i, (p % 72) == 0 ? 270 + i : 270 + i + MaximumId); }, warmup: 72);
        // CPU writes to the textures while they are away (two presents after leaving): the return must upload the new data.
        Measure("cpuModifiedWhileAway", 120, true, 300, 64, p =>
        {
            for (int i = 0; i < 64; i++)
            {
                int k = 300 + i;
                if ((p % 4) == 3) WriteMarker(GuestBase + TextureOffset + (ulong)k * BigSpacing, MarkerOf(1, k, ++BigVersion[k]));
                Big(300 + i, (p % 4) == 0 ? k : k + MaximumId);
            }
        });
        // Descriptor changes on return, each after three presents away: the same memory with another swizzle (RRRA), another
        // format (Snorm), a smaller height, then as before.
        Measure("descriptorChange", 192, true, 400, 64, p =>
        {
            int phase = p % 16;
            for (int i = 0; i < 64; i++)
            {
                int k = 400 + i;
                if (phase == 0) Big(400 + i, k);
                else if (phase == 4) Big(400 + i, k, red: true);
                else if (phase == 8) Big(400 + i, k, snorm: true);
                else if (phase == 12) Big(400 + i, k, heightDelta: -4);
                else Big(400 + i, k + 211);    // away: textures 611..674
            }
        }, warmup: 16);
        // Unmap while away: two presents after leaving, the texture's GPU range is unmapped and mapped to other guest pages
        // (alternately back); the return must show the pages mapped now.
        bool[] remapped = new bool[16];
        Measure("unmapWhileAway", 80, true, 470, 16, p =>
        {
            for (int i = 0; i < 16; i++)
            {
                int k = 470 + i;
                if ((p % 4) == 3)
                {
                    gpuMemory.Unmap(BigVa(k), BigSpacing);
                    remapped[i] = !remapped[i];
                    gpuMemory.Map(remapped[i] ? GuestBase + AltOffset + (ulong)i * BigSpacing : GuestBase + TextureOffset + (ulong)k * BigSpacing, BigVa(k), BigSpacing, PteKind.Pitch);
                }
                Big(470 + i, (p % 4) == 0 ? k : k + 560 - 470);  // away: textures 560..575
            }
        });
        // Referenced elsewhere: entries 490 and 491 name texture 1080; 490 leaves for three presents (491 still holds it),
        // then both leave for three; texture 1081 (entries 492, 493) is also lifted into the auto delete cache each pass (as
        // a render target is), so it never reaches the short cache.
        Measure("referencedElsewhere", 120, true, 490, 4, p =>
        {
            // Phase 0: both name 1080; 1-3: 490 away, 491 holds it; 4: both; 5-7: both away (to the short cache at 5).
            int phase = p % 8;
            Big(490, phase == 0 || phase == 4 ? 1080 : 1090);
            Big(491, phase <= 4 ? 1080 : 1091);
            Texture lifted = PoolTexture(492);
            if (lifted != null && lifted.Info.GpuAddress == BigVa(1081)) cache.Lift(lifted);
            Big(492, (p % 4) == 0 ? 1081 : 1092);
            Big(493, (p % 4) == 0 ? 1081 : 1093);
        });
        // Count bound: 64 entries name small textures in turn (1 300 of them, back after about 20 presents): more than 1 024
        // are away at once. Then 896 of them (back after 14 presents): within the bound.
        int smallCursor = 0;
        Measure("saturationEntries", 200, true, 300, 64, p => { for (int i = 0; i < 64; i++) Small(300 + i, smallCursor++ % SmallTextures); });
        smallCursor = 0;
        Measure("withinEntryBound", 200, true, 300, 64, p => { for (int i = 0; i < 64; i++) Small(300 + i, smallCursor++ % 896); }, warmup: 20);
        // Byte bound: 32 entries name big textures 600..1099, 24 rows taller (at most 238 KiB each), in turn (back after
        // about 16 presents: more than 32 MiB away).
        for (int i = 32; i < 64; i++) Big(300 + i, 300 + i);
        int bigCursor = 0;
        Measure("saturationBytes", 200, true, 300, 32, p => { for (int i = 0; i < 32; i++) Big(300 + i, 600 + bigCursor++ % 500, heightDelta: 24); }, warmup: 20);
        for (int id = 300; id < 332; id++)
        {
            Texture texture = PoolTexture(id);
            if (texture == null || texture.Size > BigSpacing) errors.Add($"layout: entry {id} size {texture?.Size} above the {BigSpacing} B spacing");
        }
        // Memory pressure: the cycle again, with the device-short trim of the IPA 694 lines (Warning, freeOnly) as
        // GpuContext.TrimCaches calls it, every 12th pass just before the textures come back.
        long trimmed = 0, liveBeforeTrim = 0, liveAfterTrim = 0;
        int trims = 0;
        Measure("pressure", 120, true, 130, 64, p =>
        {
            if (p % 12 == 0)
            {
                liveBeforeTrim += RecordingTexture.LiveBytes;
                trimmed += (long)cache.Trim(MemoryPressureLevel.Warning, freeOnly: true);
                liveAfterTrim += RecordingTexture.LiveBytes;
                trims++;
            }
            for (int i = 0; i < 64; i++) Big(130 + i, (p % 4) == 0 ? 130 + i : 130 + i + MaximumId);
        });
        ((Dictionary<string, object>)results["pressure"])["trims"] = trims;
        ((Dictionary<string, object>)results["pressure"])["trimReturnedBytes"] = trimmed;
        ((Dictionary<string, object>)results["pressure"])["liveHostBytesReleasedByTrims"] = liveBeforeTrim - liveAfterTrim;

        // Close: the production teardown of the texture cache (PhysicalMemory.Dispose queues Destroy, which the render thread
        // runs with the deferred actions: TextureCache.Dispose).
        long liveBeforeClose = RecordingTexture.LiveBytes;
        long retainedBeforeClose = reuseField("Retained");
        int releasesBeforeClose = RecordingTexture.Releases;
        gpuMemory.Physical.Dispose();
        gpu.RunDeferredActions();
        var close = new Dictionary<string, object>
        {
            ["liveHostBytesBefore"] = liveBeforeClose,
            ["liveHostBytesAfter"] = RecordingTexture.LiveBytes,
            ["hostTexturesReleased"] = RecordingTexture.Releases - releasesBeforeClose,
            ["retainedBefore"] = retainedBeforeClose,
            ["retainedAfter"] = reuseField("Retained"),
        };
        if (RecordingTexture.LiveBytes != 0) errors.Add($"close: {RecordingTexture.LiveBytes} B of host textures not released");
        if (RecordingTexture.Releases != RecordingTexture.Created) errors.Add($"close: {RecordingTexture.Created} created, {RecordingTexture.Releases} released");
        if (RecordingTexture.DoubleReleases != 0) errors.Add($"{RecordingTexture.DoubleReleases} host textures released twice");

        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["engine"] = candidate ? "candidate" : "control",
            ["tieredCompilation"] = Environment.GetEnvironmentVariable("DOTNET_TieredCompilation") ?? "default",
            ["errors"] = errors,
            ["observation"] = Convert.ToHexString(observation.GetHashAndReset()).ToLowerInvariant(),
            ["largestBigTextureBytes"] = largestBig,
            ["results"] = results,
            ["close"] = close,
            ["totals"] = new Dictionary<string, object>
            {
                ["texturesCreated"] = RecordingTexture.Created,
                ["viewsCreated"] = RecordingTexture.Views,
                ["uploads"] = RecordingTexture.Uploads,
                ["uploadBytes"] = RecordingTexture.UploadBytes,
            },
        }));
        return 0;
    }
}
