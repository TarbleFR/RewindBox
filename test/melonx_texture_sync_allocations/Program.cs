// Fixture of test/melonx_texture_sync_allocations_test.py. Compiled with the REAL Ryujinx.Graphics.Gpu sources of one
// variant (control or candidate) and referencing that variant's real Ryujinx.Graphics.Texture, Ryujinx.Graphics.GAL,
// Ryujinx.Common (MemoryOwner pool) and Ryujinx.Cpu (software memory manager with real write tracking). Doubles: the
// host renderer (a DispatchProxy) and its textures, which hash each upload and then dispose it, as the Vulkan backend
// disposes after its staging copy. Real Texture.SynchronizeMemory -> TextureGroup.SynchronizeMemory -> SynchronizeFull /
// SynchronizePartial -> ConvertToHostCompatibleFormat -> LayoutConverter / ETC2Transcoder -> HostTexture.SetData.
// Writes one JSON line: the hashes of every uploaded buffer (in submission order) and the GPU-thread allocations.
using Ryujinx.Common;
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Shader.Translation;
using Ryujinx.Graphics.Texture;
using Ryujinx.Memory;
using Ryujinx.Memory.Range;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using CpuMemoryManager = Ryujinx.Cpu.Jit.MemoryManager;

public sealed class HostSink
{
    // Uploads held by the host before it consumes them (the render thread's lag). 0 = consumed at once.
    public int Depth;
    public bool Threaded;
    private readonly Queue<MemoryOwner<byte>> _pending = new();
    private readonly List<string> _uploads = new();
    private readonly object _lock = new();
    public int Consumed;
    // Allocations made by this double (hashing, records), removed from the measured GPU-thread bytes.
    [ThreadStatic] public static long DoubleBytes;

    public void Add(MemoryOwner<byte> data, string kind)
    {
        long start = GC.GetAllocatedBytesForCurrentThread();
        if (Threaded)
        {
            Record(data, kind);
        }
        else
        {
            _pending.Enqueue(data);
            _kinds.Enqueue(kind);
            while (_pending.Count > Depth) Record(_pending.Dequeue(), _kinds.Dequeue());
        }
        DoubleBytes += GC.GetAllocatedBytesForCurrentThread() - start;
    }

    private readonly Queue<string> _kinds = new();

    private void Record(MemoryOwner<byte> data, string kind)
    {
        string entry = kind + ":" + data.Length + ":" + Convert.ToHexString(SHA256.HashData(data.Span), 0, 12);
        // The host is done with the buffer: return it to the pool, as TextureView.SetData does.
        data.Dispose();
        lock (_lock)
        {
            _uploads.Add(entry);
            Consumed++;
        }
    }

    public void Drain()
    {
        while (_pending.Count > 0) Record(_pending.Dequeue(), _kinds.Dequeue());
    }

    public List<string> Uploads { get { lock (_lock) return _uploads.ToList(); } }
}

public class RendererProxy : DispatchProxy
{
    public static Capabilities Caps;
    public static HostSink Sink;

    protected override object Invoke(MethodInfo method, object[] args)
    {
        switch (method.Name)
        {
            case "CreateTexture": return new HostTextureDouble(Sink, (TextureCreateInfo)args[0]);
            case "GetCapabilities": return Caps;
            case "get_PreferThreading": return true;
        }

        return method.ReturnType != typeof(void) && method.ReturnType.IsValueType ? Activator.CreateInstance(method.ReturnType) : null;
    }
}

public sealed class HostTextureDouble : ITexture
{
    private readonly HostSink _sink;
    private readonly TextureCreateInfo _info;
    public HostTextureDouble(HostSink sink, TextureCreateInfo info) { _sink = sink; _info = info; }
    public int Width => _info.Width;
    public int Height => _info.Height;
    public void CopyTo(ITexture destination, int firstLayer, int firstLevel) { }
    public void CopyTo(ITexture destination, int srcLayer, int dstLayer, int srcLevel, int dstLevel) { }
    public void CopyTo(ITexture destination, Extents2D srcRegion, Extents2D dstRegion, bool linearFilter) { }
    public void CopyTo(BufferRange range, int layer, int level, int stride) { }
    public ITexture CreateView(TextureCreateInfo info, int firstLayer, int firstLevel) => new HostTextureDouble(_sink, info);
    public PinnedSpan<byte> GetData() => default;
    public PinnedSpan<byte> GetData(int layer, int level) => default;
    public void SetData(MemoryOwner<byte> data) => _sink.Add(data, _info.Format + ".full");
    public void SetData(MemoryOwner<byte> data, int layer, int level) => _sink.Add(data, _info.Format + ".slice" + layer + "." + level);
    public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region) => _sink.Add(data, _info.Format + ".region");
    public void SetStorage(BufferRange buffer) { }
    public void Release() { }
}

public record Spec(string Name, Format Format, int Width, int Height, int Layers, int Levels, bool Linear, bool MipViews);

public static class Program
{
    static (int bw, int bh, int bpp, int comp) Shape(Format format) => format switch
    {
        Format.Bc1RgbaUnorm or Format.Bc1RgbaSrgb or Format.Bc4Unorm or Format.Bc4Snorm => (4, 4, 8, 4),
        Format.Bc2Unorm or Format.Bc3Unorm or Format.Bc5Unorm or Format.Bc5Snorm or Format.Bc7Unorm or Format.Bc7Srgb
            or Format.Astc4x4Unorm => (4, 4, 16, 4),
        Format.R16G16B16A16Float => (1, 1, 8, 4),
        _ => (1, 1, 4, 4),
    };

    static Capabilities MakeCaps(bool bc)
    {
        ConstructorInfo ctor = typeof(Capabilities).GetConstructors().Single();
        ParameterInfo[] parameters = ctor.GetParameters();
        object[] args = parameters.Select(p => p.ParameterType.IsValueType ? Activator.CreateInstance(p.ParameterType) : null).ToArray();
        void Set(string name, object value) { int i = Array.FindIndex(parameters, p => p.Name == name); if (i < 0) throw new Exception(name); args[i] = value; }
        Set("api", TargetApi.Vulkan);
        Set("vendorName", "Apple");
        // An iPhone through MoltenVK: ASTC and ETC2, BC only where the Metal device reports it.
        Set("supportsAstcCompression", true);
        Set("supportsEtc2Compression", true);
        Set("supportsBc123Compression", bc);
        Set("supportsBc45Compression", bc);
        Set("supportsBc67Compression", bc);
        Set("supports3DTextureCompression", true);
        Set("supportsR4G4B4A4Format", true);
        Set("supports5BitComponentFormat", true);
        Set("supportsBgraFormat", true);
        return (Capabilities)ctor.Invoke(args);
    }

    // Guest bytes with runs of identical 8-byte words, as flat areas and padding give (BC1/BC4 reuse runs).
    static byte[] GuestData(Random random, int size)
    {
        byte[] data = new byte[size];
        random.NextBytes(data);
        for (int i = 8; i + 8 <= size; i += 8)
        {
            if (random.Next(4) == 0) data.AsSpan(i - 8, 8).CopyTo(data.AsSpan(i, 8));
        }
        return data;
    }

    sealed class World
    {
        public GpuContext Context;
        public PhysicalMemory Physical;
        public CpuMemoryManager Cpu;
        public HostSink Sink;
        public ulong NextVa = 0x10000000;
    }

    static World MakeWorld(bool bc, HostSink sink, IRenderer wrap = null)
    {
        var world = new World { Sink = sink };
        RendererProxy.Caps = MakeCaps(bc);
        RendererProxy.Sink = world.Sink;
        IRenderer renderer = wrap ?? DispatchProxy.Create<IRenderer, RendererProxy>();
        world.Context = new GpuContext(renderer, new DirtyHacks(Array.Empty<EnabledDirtyHack>()));
        world.Context.Capabilities = RendererProxy.Caps;
        var block = new MemoryBlock(512UL << 20);
        world.Cpu = new CpuMemoryManager(block, 1UL << 36);
        world.Cpu.Map(0x10000000, 0, 512UL << 20, MemoryMapFlags.Private);
        world.Physical = new PhysicalMemory(world.Context, world.Cpu);
        return world;
    }

    static (Texture Texture, ulong Va, int Size) Create(World world, Spec spec, bool withData)
    {
        var (bw, bh, bpp, comp) = Shape(spec.Format);
        var formatInfo = new FormatInfo(spec.Format, (byte)bw, (byte)bh, (byte)bpp, (byte)comp);
        int blocksHigh = BitUtils.DivRoundUp(spec.Height, bh);
        int gobY = (int)Math.Min(16u, BitOperations.RoundUpToPowerOf2((uint)Math.Max(1, blocksHigh / 8)));
        int stride = BitUtils.AlignUp(BitUtils.DivRoundUp(spec.Width, bw) * bpp, 32);
        Target target = spec.Layers > 1 ? Target.Texture2DArray : Target.Texture2D;
        SizeInfo sizeInfo = spec.Linear
            ? SizeCalculator.GetLinearTextureSize(stride, spec.Height, bh)
            : SizeCalculator.GetBlockLinearTextureSize(spec.Width, spec.Height, 1, spec.Levels, spec.Layers, bw, bh, bpp, gobY, 1, 1);
        var info = new TextureInfo(world.NextVa, spec.Width, spec.Height, spec.Layers, spec.Levels, 1, 1, spec.Linear ? stride : 0,
            spec.Linear, gobY, 1, 1, target, formatInfo);
        int size = sizeInfo.TotalSize;
        ulong va = world.NextVa;
        world.NextVa += (ulong)BitUtils.AlignUp(size, 0x10000);
        var texture = new Texture(world.Context, world.Physical, info, sizeInfo, new MultiRange(va, (ulong)size), TextureScaleMode.Blacklisted);
        texture.InitializeGroup(spec.MipViews, spec.MipViews, new List<TextureIncompatibleOverlap>());
        texture.InitializeData(false, withData);
        return (texture, va, size);
    }

    // One measured synchronization: GPU-thread bytes allocated by the real code (the double's own bytes removed).
    static long Sync(Texture texture)
    {
        long doubles = HostSink.DoubleBytes;
        long start = GC.GetAllocatedBytesForCurrentThread();
        texture.SynchronizeMemory();
        return GC.GetAllocatedBytesForCurrentThread() - start - (HostSink.DoubleBytes - doubles);
    }

    static string Digest(IEnumerable<string> uploads) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("|", uploads))), 0, 16);

    static readonly Spec[] Cases =
    {
        new("rgba8-256-mips", Format.R8G8B8A8Unorm, 256, 256, 1, 9, false, false),
        new("rgba8-64", Format.R8G8B8A8Unorm, 64, 64, 1, 1, false, false),
        new("rgba8-linear-320x180", Format.R8G8B8A8Unorm, 320, 180, 1, 1, true, false),
        new("rgba16f-128", Format.R16G16B16A16Float, 128, 128, 1, 1, false, false),
        new("astc4x4-256-mips", Format.Astc4x4Unorm, 256, 256, 1, 9, false, false),
        new("bc1-512-mips", Format.Bc1RgbaUnorm, 512, 512, 1, 10, false, false),
        new("bc1-100x60-mips", Format.Bc1RgbaSrgb, 100, 60, 1, 7, false, false),
        new("bc2-128-mips", Format.Bc2Unorm, 128, 128, 1, 8, false, false),
        new("bc3-128-mipviews", Format.Bc3Unorm, 128, 128, 1, 8, false, true),
        new("bc4u-256-mips", Format.Bc4Unorm, 256, 256, 1, 9, false, false),
        new("bc4s-64", Format.Bc4Snorm, 64, 64, 1, 7, false, false),
        new("bc5u-256-mips", Format.Bc5Unorm, 256, 256, 1, 9, false, false),
        new("bc5s-128", Format.Bc5Snorm, 128, 128, 1, 1, false, false),
        new("bc7-256-mips", Format.Bc7Unorm, 256, 256, 1, 9, false, false),
        new("bc7-array3-128-mipviews", Format.Bc7Srgb, 128, 128, 3, 8, false, true),
        new("bc7-1024-mips", Format.Bc7Unorm, 1024, 1024, 1, 11, false, false),
    };

    // Per format: 7 guest rewrites, each synchronized (full, or partial for textures with mip/layer views when only the
    // start of the texture is rewritten), the host consuming each upload at once: the steady per-call cost once the
    // pool holds the sizes (the first synchronization is not counted).
    static object RunCases(bool bc)
    {
        World world = MakeWorld(bc, new HostSink { Depth = 0 });
        var random = new Random(11);
        var results = new List<object>();
        foreach (Spec spec in Cases)
        {
            var (texture, va, size) = Create(world, spec, false);
            long bytes = 0;
            int calls = 0;
            for (int round = 0; round < 7; round++)
            {
                byte[] data = GuestData(random, size);
                if (spec.MipViews && round % 2 == 1)
                {
                    world.Cpu.Write(va, data.AsSpan(0, Math.Min(size, 4096)));
                }
                else
                {
                    world.Cpu.Write(va, data);
                }

                long allocated = Sync(texture);
                if (round > 0) { bytes += allocated; calls++; }
            }
            world.Sink.Drain();
            results.Add(new { name = spec.Name, bytesPerSync = bytes / calls });
        }
        world.Sink.Drain();
        List<string> uploads = world.Sink.Uploads;
        return new { bc, uploads = uploads.Count, digest = Digest(uploads), perCase = results,
                     partialUploads = uploads.Count(u => u.Contains(".slice")) };
    }

    static List<Spec> SceneSpecs()
    {
        var specs = new List<Spec>();
        void Add(Format format, int size, int count)
        {
            for (int i = 0; i < count; i++)
                specs.Add(new Spec(format + "-" + size, format, size, size, 1, BitOperations.Log2((uint)size) + 1, false, false));
        }
        Add(Format.Bc1RgbaUnorm, 1024, 2); Add(Format.Bc1RgbaUnorm, 512, 8); Add(Format.Bc1RgbaUnorm, 256, 16);
        Add(Format.Bc1RgbaUnorm, 128, 16); Add(Format.Bc1RgbaUnorm, 64, 12);
        Add(Format.Bc7Unorm, 512, 4); Add(Format.Bc7Unorm, 256, 10); Add(Format.Bc7Unorm, 128, 12); Add(Format.Bc7Unorm, 64, 8);
        Add(Format.Bc5Unorm, 512, 4); Add(Format.Bc5Unorm, 256, 8); Add(Format.Bc5Unorm, 128, 8);
        Add(Format.Bc3Unorm, 256, 6); Add(Format.Bc4Unorm, 256, 6);
        Add(Format.R8G8B8A8Unorm, 256, 4); Add(Format.R8G8B8A8Unorm, 128, 8); Add(Format.R8G8B8A8Unorm, 64, 12);
        Add(Format.R8G8B8A8Unorm, 32, 12);
        var random = new Random(7);
        return specs.OrderBy(_ => random.Next()).ToList();
    }

    // A scene transition: every texture of the scene is created and loaded once (first round: the pool is cold, as
    // after more than 3 s of steady play; second round: the same loads again with the pool as the first left it).
    static object RunScene(bool bc, int depth)
    {
        World world = MakeWorld(bc, new HostSink { Depth = depth });
        List<Spec> specs = SceneSpecs();
        var random = new Random(5);
        var rounds = new List<object>();
        for (int round = 0; round < 2; round++)
        {
            world.NextVa = 0x10000000;
            long bytes = 0, guest = 0;
            int gen0 = GC.CollectionCount(0), gen2 = GC.CollectionCount(2);
            long process = GC.GetTotalAllocatedBytes(true);
            var watch = System.Diagnostics.Stopwatch.StartNew();
            foreach (Spec spec in specs)
            {
                var (texture, va, size) = Create(world, spec, false);
                world.Cpu.Write(va, GuestData(random, size));
                bytes += Sync(texture);
                guest += size;
            }
            world.Sink.Drain();
            rounds.Add(new
            {
                round, calls = specs.Count, gpuThreadBytes = bytes, bytesPerSync = bytes / specs.Count, guestBytes = guest,
                processBytes = GC.GetTotalAllocatedBytes(true) - process, gen0 = GC.CollectionCount(0) - gen0,
                gen2 = GC.CollectionCount(2) - gen2, ms = watch.ElapsedMilliseconds,
            });
        }
        List<string> uploads = world.Sink.Uploads;
        return new { bc, depth, uploads = uploads.Count, digest = Digest(uploads), rounds };
    }

    // The same scene through the REAL ThreadedRenderer: the GPU thread synchronizes, the render thread runs the queued
    // TextureSetData commands on the host double (which hashes then disposes). Ownership: every buffer must reach the
    // host intact after the GPU thread moved on; the hashes must equal the direct run's.
    static object RunThreaded(bool bc)
    {
        RendererProxy.Caps = MakeCaps(bc);
        var sink = new HostSink { Threaded = true };
        RendererProxy.Sink = sink;
        var threaded = new ThreadedRenderer(DispatchProxy.Create<IRenderer, RendererProxy>());
        long bytes = 0;
        int calls = 0;
        Exception failure = null;
        threaded.RunLoop(() =>
        {
            try
            {
                World world = MakeWorld(bc, sink, threaded);
                var random = new Random(5);
                List<Spec> specs = SceneSpecs();
                foreach (Spec spec in specs)
                {
                    var (texture, va, size) = Create(world, spec, false);
                    world.Cpu.Write(va, GuestData(random, size));
                    bytes += Sync(texture);
                    calls++;
                }
                while (Volatile.Read(ref sink.Consumed) < calls) Thread.Sleep(1);
            }
            catch (Exception exception)
            {
                failure = exception;
            }
            finally
            {
                new Thread(threaded.Dispose).Start();
            }
        });
        if (failure != null) throw failure;
        List<string> uploads = sink.Uploads;
        return new { bc, calls, uploads = uploads.Count, digest = Digest(uploads), bytesPerSync = bytes / Math.Max(1, calls) };
    }

    // The transcoders themselves: the renting entry points (both variants) and, for the candidate, the in-place ones,
    // on the same inputs (odd sizes, mip chains, layers, runs).
    static object RunTranscoders()
    {
        var random = new Random(3);
        var results = new List<object>();
        var shapes = new (int w, int h, int d, int levels, int layers)[] { (4, 4, 1, 1, 1), (100, 60, 1, 7, 1), (256, 256, 1, 9, 1), (128, 128, 1, 8, 3), (1024, 512, 1, 3, 1), (16, 16, 4, 2, 1) };
        foreach (var (w, h, d, levels, layers) in shapes)
        {
            int blocks8 = 0;
            for (int l = 0, lw = w, lh = h, ld = d; l < levels; l++, lw = Math.Max(1, lw >> 1), lh = Math.Max(1, lh >> 1), ld = Math.Max(1, ld >> 1))
                blocks8 += ((lw + 3) / 4) * ((lh + 3) / 4) * ld * layers;
            byte[] bc8 = GuestData(random, blocks8 * 8 + 3);
            byte[] bc16 = GuestData(random, blocks8 * 16 + 5);
            foreach (string kind in new[] { "bc1", "bc4u", "bc4s", "bc5u", "bc5s", "bc2", "bc3", "bc7" })
            {
                byte[] input = kind is "bc1" or "bc4u" or "bc4s" ? bc8 : bc16;
                using MemoryOwner<byte> rented = kind switch
                {
                    "bc1" => ETC2Transcoder.TranscodeBC1ToEtc2Pta(input),
                    "bc4u" => ETC2Transcoder.TranscodeBC4ToEacR11(input, false),
                    "bc4s" => ETC2Transcoder.TranscodeBC4ToEacR11(input, true),
                    "bc5u" => ETC2Transcoder.TranscodeBC5ToEacRG11(input, false),
                    "bc5s" => ETC2Transcoder.TranscodeBC5ToEacRG11(input, true),
                    "bc2" => ETC2Transcoder.TranscodeBC2ToEtc2Rgba(input, w, h, d, levels, layers),
                    "bc3" => ETC2Transcoder.TranscodeBC3ToEtc2Rgba(input, w, h, d, levels, layers),
                    _ => ETC2Transcoder.TranscodeBC7ToEtc2Rgba(input, w, h, d, levels, layers),
                };
                string digest = Convert.ToHexString(SHA256.HashData(rented.Span), 0, 16);
                bool? inPlaceEqual = null;
#if CANDIDATE
                byte[] copy = (byte[])input.Clone();
                switch (kind)
                {
                    case "bc1": ETC2Transcoder.TranscodeBC1ToEtc2PtaInPlace(copy); break;
                    case "bc4u": ETC2Transcoder.TranscodeBC4ToEacR11InPlace(copy, false); break;
                    case "bc4s": ETC2Transcoder.TranscodeBC4ToEacR11InPlace(copy, true); break;
                    case "bc5u": ETC2Transcoder.TranscodeBC5ToEacRG11InPlace(copy, false); break;
                    case "bc5s": ETC2Transcoder.TranscodeBC5ToEacRG11InPlace(copy, true); break;
                    case "bc2": ETC2Transcoder.TranscodeBC2ToEtc2RgbaInPlace(copy, w, h, d, levels, layers); break;
                    case "bc3": ETC2Transcoder.TranscodeBC3ToEtc2RgbaInPlace(copy, w, h, d, levels, layers); break;
                    default: ETC2Transcoder.TranscodeBC7ToEtc2RgbaInPlace(copy, w, h, d, levels, layers); break;
                }
                inPlaceEqual = copy.AsSpan().SequenceEqual(rented.Span);
#endif
                results.Add(new { shape = $"{w}x{h}x{d} L{levels} A{layers}", kind, digest, inPlaceEqual });
            }
        }
        return results;
    }

    // The REAL MemoryOwner<byte> pool under a texture-like load: rents of mixed sizes (4 KiB to 1.4 MiB, several of
    // each in flight, as uploads waiting for the render thread), each stamped while held and checked when returned, so
    // an array handed to two holders at once, or a wrong length, fails. Reports the bytes the pool allocated and its
    // spare budget (read from the private field) after every return.
    static object RunPool()
    {
        var random = new Random(9);
        int[] sizes = { 2736, 5472, 10944, 21856, 43704, 87384, 174776, 349520, 699064, 1398136, 4096, 16384, 65536, 262144, 21848, 87380 };
        Type pooling = typeof(MemoryOwner<byte>).GetNestedType("ArrayPooling", BindingFlags.NonPublic).MakeGenericType(typeof(byte));
        FieldInfo spareBytes = pooling.GetField("_spareBytes", BindingFlags.NonPublic | BindingFlags.Static);
        var held = new List<(MemoryOwner<byte> Owner, byte Stamp, int Length)>();
        long maxSpare = 0, allocated = 0;
        int errors = 0;
        for (int phase = 0; phase < 2; phase++)
        {
            long start = GC.GetAllocatedBytesForCurrentThread();
            for (int i = 0; i < 6000; i++)
            {
                if (held.Count < 48 && (held.Count < 8 || random.Next(2) == 0))
                {
                    int length = sizes[random.Next(sizes.Length)] + random.Next(3) * 16;
                    var owner = MemoryOwner<byte>.Rent(length);
                    byte stamp = (byte)random.Next(1, 256);
                    if (owner.Length != length || owner.Span.Length != length) errors++;
                    owner.Span.Fill(stamp);
                    held.Add((owner, stamp, length));
                }
                else
                {
                    int index = random.Next(held.Count);
                    var (owner, stamp, length) = held[index];
                    held.RemoveAt(index);
                    if (owner.Span.IndexOfAnyExcept(stamp) >= 0) errors++;
                    owner.Dispose();
                    maxSpare = Math.Max(maxSpare, (long)spareBytes.GetValue(null));
                }
            }
            if (phase == 1) allocated = GC.GetAllocatedBytesForCurrentThread() - start;
        }
        foreach (var (owner, stamp, _) in held)
        {
            if (owner.Span.IndexOfAnyExcept(stamp) >= 0) errors++;
            owner.Dispose();
        }
        return new { errors, warmPhaseBytes = allocated, maxSpareBytes = maxSpare };
    }

    public static void Main(string[] args)
    {
        object result = args[0] switch
        {
            "cases" => RunCases(args[1] == "bc"),
            "scene" => RunScene(args[1] == "bc", int.Parse(args[2])),
            "threaded" => RunThreaded(args[1] == "bc"),
            "transcoders" => RunTranscoders(),
            "pool" => RunPool(),
            _ => throw new ArgumentException(args[0]),
        };
        Console.WriteLine(JsonSerializer.Serialize(result));
    }
}
