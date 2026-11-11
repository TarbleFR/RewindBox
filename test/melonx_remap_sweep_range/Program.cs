// Differential fixture of adapt_remap_sweep_range (test/melonx_remap_sweep_range_test.py builds it against the control
// engine and against the candidate engine, with test/melonx_gpu_teardown/Fakes.cs beside it).
// The production TextureManager, TextureBindingsManager, TextureBindingsArrayCache, TexturePool, TextureCache, Texture,
// TextureGroup, BufferManager and GPU MemoryManager of the engine it is built against run one seeded script on guest
// memory; only the GAL backend is a double, and it keeps the bytes of every upload, so that what a bound host texture
// would show is part of the observed state.
//
// One thread does everything (the unthreaded renderer path; the guest's Map and Unmap are called on it between two
// commits), nothing waits, and the fixture reads no clock: the script's time is its own steps (one TextureCache.Tick
// per step). The engine's own clock readings on this path (the array cache's once-a-second inventory count) decide
// nothing that is observed. The digests hold contents, ranges and set membership, never object identities (host
// texture ids are reported apart, for information).
//
// Scene: two GPU address spaces (memory managers) of one process, so one texture cache; address space 1 has a pool of 256
// ids bound through two pool arrays (lengths 256 and 255) and eight ordinary texture bindings, with textures created
// partially mapped, textures fully mapped, ids sharing one texture at one address, and textures referenced at two different
// addresses (an alias mapping of the same pages); address space 2 has a pool of 32 ids bound through one pool array, at the
// same numeric addresses as textures of address space 1.
// Script: seeded steps (Map/Unmap of unrelated ranges, events of the other address space, hole fills, partial unmaps,
// remaps to other pages, descriptor rewrites, and two scripted sequences), each followed by a commit of both channels.
// Arguments: steps, seed, steps to dump ("-" for none), scene ("gated" or "dependencies").
// Output: one JSON line with, per step, the digests of the observable state and what the event queued.
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Texture;
using Ryujinx.Memory;
using Ryujinx.Memory.Range;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;

static class Program
{
    private const BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;

    // ---- guest layout (offsets in guest memory)
    private const ulong GuestBase = 0x10000000;
    private const ulong Pool1Offset = 0x000000;
    private const ulong SamplerOffset = 0x100000;
    private const ulong CbufOffset = 0x200000;
    private const ulong ScratchOffset = 0x300000;   // 64 pages of memory no texture uses
    private const ulong Pool2Offset = 0x400000;
    private const ulong LowSize = 0x1000000;
    private const ulong OrigOffset = 0x1000000;     // textures of address space 1, first backing
    private const ulong AltOffset = 0x2000000;      // textures of address space 1, second backing (other bytes)
    private const ulong Tex2Offset = 0x3000000;     // textures of address space 2
    private const ulong GuestSize = 0x4000000;
    private const ulong Slot = 0x10000;
    private const int Slots = 256;
    private const int Slots2 = 32;

    // ---- GPU virtual addresses
    private const ulong GpuBase = 0x40000000;       // low region and textures (both address spaces, same numbers)
    private const ulong AliasBase = 0x80000000;     // address space 1: second address of some textures
    private const ulong ScratchVa = 0xC0000000;     // address space 1: a range no texture is addressed through

    private static ulong TexVa(int slot) => GpuBase + OrigOffset + (ulong)slot * Slot;
    private static ulong AliasVa(int slot) => AliasBase + (ulong)slot * Slot;

    // ---- backend double: every host texture keeps the bytes it was given, per level
    private sealed class Storage
    {
        public byte[][] Levels;
        public long Version;
        public ulong Marker;
    }

    public sealed class HostTexture : ITexture
    {
        public static int Created, Uploads;
        public static long UploadBytes;
        public readonly int Id;
        public readonly TextureCreateInfo Info;
        private readonly Storage _storage;
        private readonly int _firstLevel;
        private long _signatureVersion = -1;
        private ulong _signature;

        public HostTexture(TextureCreateInfo info)
        {
            Id = ++Created;
            Info = info;
            _storage = new Storage { Levels = new byte[Math.Max(1, info.Levels)][] };
        }

        private HostTexture(TextureCreateInfo info, Storage storage, int firstLevel)
        {
            Id = ++Created;
            Info = info;
            _storage = storage;
            _firstLevel = firstLevel;
        }

        public int Width => Info.Width;
        public int Height => Info.Height;

        private int LevelSize(int level) => Math.Max(1, Info.Width >> level) * Math.Max(1, Info.Height >> level) * Math.Max(1, Info.BytesPerPixel);

        private void Store(int level, ReadOnlySpan<byte> data)
        {
            int index = _firstLevel + level;
            if (index >= _storage.Levels.Length) Array.Resize(ref _storage.Levels, index + 1);
            _storage.Levels[index] = data.ToArray();
            _storage.Version++;
        }

        public void SetData(MemoryOwner<byte> data)
        {
            ReadOnlySpan<byte> span = data.Span;
            Uploads++; UploadBytes += span.Length;
            int total = 0;
            for (int level = 0; level < Info.Levels; level++) total += LevelSize(level);
            if (total == span.Length)
            {
                int offset = 0;
                for (int level = 0; level < Info.Levels; level++)
                {
                    Store(level, span.Slice(offset, LevelSize(level)));
                    offset += LevelSize(level);
                }
            }
            else
            {
                // Not the layout this double knows: the whole upload is one opaque level.
                Store(0, span);
                _storage.Marker = Mix(_storage.Marker, 0x5157);
            }
            data.Dispose();
        }

        public void SetData(MemoryOwner<byte> data, int layer, int level)
        {
            Uploads++; UploadBytes += data.Span.Length;
            Store(level, data.Span);
            data.Dispose();
        }

        public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region)
        {
            Uploads++; UploadBytes += data.Span.Length;
            int index = _firstLevel + level;
            byte[] target = index < _storage.Levels.Length ? _storage.Levels[index] : null;
            int bpp = Math.Max(1, Info.BytesPerPixel);
            int width = Math.Max(1, Info.Width >> level);
            if (target != null && target.Length == LevelSize(level) && data.Span.Length == region.Width * region.Height * bpp)
            {
                for (int y = 0; y < region.Height; y++)
                {
                    data.Span.Slice(y * region.Width * bpp, region.Width * bpp).CopyTo(target.AsSpan(((region.Y + y) * width + region.X) * bpp));
                }
                _storage.Version++;
            }
            else
            {
                _storage.Marker = Mix(Mix(_storage.Marker, Fnv(data.Span)), (ulong)(level * 31 + region.X * 7 + region.Y));
                _storage.Version++;
            }
            data.Dispose();
        }

        public void CopyTo(ITexture destination, int firstLayer, int firstLevel)
        {
            var other = (HostTexture)destination;
            for (int level = 0; level < Info.Levels; level++)
            {
                int source = _firstLevel + level;
                if (source < _storage.Levels.Length && _storage.Levels[source] != null) other.Store(firstLevel + level, _storage.Levels[source]);
            }
        }

        private void Blend(ITexture destination, ulong salt)
        {
            var other = (HostTexture)destination;
            other._storage.Marker = Mix(Mix(other._storage.Marker, Signature()), salt);
            other._storage.Version++;
        }

        public void CopyTo(ITexture destination, int srcLayer, int dstLayer, int srcLevel, int dstLevel)
        {
            // One level to one level (copy dependencies): the bytes move when the two levels have the same size.
            var other = (HostTexture)destination;
            int source = _firstLevel + srcLevel;
            byte[] bytes = source < _storage.Levels.Length ? _storage.Levels[source] : null;
            if (bytes != null && bytes.Length == other.LevelSize(dstLevel)) other.Store(dstLevel, bytes); else Blend(destination, (ulong)(srcLevel * 16 + dstLevel));
        }
        public void CopyTo(ITexture destination, Extents2D srcRegion, Extents2D dstRegion, bool linearFilter) => Blend(destination, 0x77);
        public void CopyTo(BufferRange range, int layer, int level, int stride) { }
        public ITexture CreateView(TextureCreateInfo info, int firstLayer, int firstLevel) => new HostTexture(info, _storage, _firstLevel + firstLevel);
        public PinnedSpan<byte> GetData() => default;
        public PinnedSpan<byte> GetData(int layer, int level) => default;
        public void SetStorage(BufferRange buffer) { }
        public void Release() { }

        public string Describe() => string.Join(" ", Enumerable.Range(0, Info.Levels).Select(level =>
        {
            int index = _firstLevel + level;
            byte[] bytes = index < _storage.Levels.Length ? _storage.Levels[index] : null;
            return bytes == null ? "null" : (Fnv(bytes) & 0xffff).ToString("x4") + ":" + bytes.Length;
        })) + " marker=" + _storage.Marker.ToString("x") + " first=" + _firstLevel;

        // What the texture would show: its shape and the bytes of its levels, however they were uploaded.
        public ulong Signature()
        {
            if (_signatureVersion != _storage.Version)
            {
                ulong hash = 0xcbf29ce484222325;
                hash = Mix(hash, (ulong)Info.Width); hash = Mix(hash, (ulong)Info.Height); hash = Mix(hash, (ulong)Info.Levels);
                hash = Mix(hash, (ulong)Info.Format); hash = Mix(hash, (ulong)Info.Target); hash = Mix(hash, _storage.Marker);
                for (int level = 0; level < Info.Levels; level++)
                {
                    int index = _firstLevel + level;
                    byte[] bytes = index < _storage.Levels.Length ? _storage.Levels[index] : null;
                    hash = Mix(hash, bytes == null ? 0x4e554c4cUL : Fnv(bytes));
                }
                _signature = hash == 0 ? 1 : hash;
                _signatureVersion = _storage.Version;
            }
            return _signature;
        }
    }

    private static ulong Mix(ulong hash, ulong value) => (hash ^ value) * 0x100000001b3UL + (value << 17 | value >> 47);

    private static ulong Fnv(ReadOnlySpan<byte> data)
    {
        ulong hash = 0xcbf29ce484222325;
        ReadOnlySpan<ulong> words = MemoryMarshal.Cast<byte, ulong>(data);
        foreach (ulong word in words) hash = (hash ^ word) * 0x100000001b3UL;
        for (int i = words.Length * 8; i < data.Length; i++) hash = (hash ^ data[i]) * 0x100000001b3UL;
        return hash;
    }

    public sealed class HostSampler : ISampler { public void Dispose() { } }

    public sealed class HostTextureArray : ITextureArray
    {
        public static long Calls, Elements;
        public readonly ITexture[] Textures;
        public HostTextureArray(int size) { Textures = new ITexture[size]; }
        public void SetSamplers(int index, ISampler[] samplers) { }
        public void SetTextures(int index, ITexture[] textures) { Calls++; Elements += textures.Length; Array.Copy(textures, 0, Textures, index, textures.Length); }
        public void Dispose() { }
    }

    public static readonly Dictionary<int, ITexture> BoundSlots = new();
    public static long SlotCalls, ArrayBinds;

    public class RecordingPipeline : DispatchProxy
    {
        protected override object Invoke(MethodInfo method, object[] args)
        {
            if (method.Name == nameof(IPipeline.SetTextureAndSampler))
            {
                SlotCalls++;
                BoundSlots[(int)args[1]] = (ITexture)args[2];
            }
            else if (method.Name == nameof(IPipeline.SetTextureArray) || method.Name == nameof(IPipeline.SetTextureArraySeparate))
            {
                ArrayBinds++;
            }
            Type result = method.ReturnType;
            return result != typeof(void) && result.IsValueType ? Activator.CreateInstance(result) : null;
        }
    }

    private sealed class HostRenderer : IRenderer
    {
        private int _buffers;
        public readonly List<HostTextureArray> Arrays = new();
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
        public ISampler CreateSampler(SamplerCreateInfo info) => new HostSampler();
        public ITexture CreateTexture(TextureCreateInfo info) => new HostTexture(info);
        public ITextureArray CreateTextureArray(int size, bool isBuffer) { var array = new HostTextureArray(size); Arrays.Add(array); return array; }
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

    // ---- guest side
    private static Ryujinx.Cpu.Jit.MemoryManager _cpu;
    private const int TexWidth = 64, TexHeight = 64, TexLevels = 7;
    private static int _texSize, _texPages;

    private static uint[] Descriptor(ulong gpuVa)
    {
        return
        [
            0x24908u | (2u << 19) | (3u << 22) | (4u << 25) | (5u << 28),  // A8B8G8R8 Unorm, RGBA swizzle
            (uint)gpuVa,
            (uint)(gpuVa >> 32) | (3u << 21),                              // block linear
            (4u << 3) | ((uint)(TexLevels - 1) << 28),
            (uint)(TexWidth - 1) | (1u << 23),                             // Texture2D
            (uint)(TexHeight - 1),
            0,
            (uint)(TexLevels - 1) << 4,
        ];
    }

    private static void WriteDescriptor(ulong poolOffset, int id, uint[] words)
    {
        _cpu.Write(GuestBase + poolOffset + (ulong)id * 32, MemoryMarshal.AsBytes((words ?? new uint[8]).AsSpan()));
    }

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

    private static ShaderSpecializationState Spec(int stages)
    {
        var spec = (ShaderSpecializationState)RuntimeHelpers.GetUninitializedObject(typeof(ShaderSpecializationState));
        foreach (string name in new[] { "_textureByBinding", "_imageByBinding" })
        {
            FieldInfo field = typeof(ShaderSpecializationState).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!;
            Type inner = field.FieldType.GetElementType()!;
            Array outer = Array.CreateInstance(inner, stages);
            for (int i = 0; i < stages; i++) outer.SetValue(Array.CreateInstance(inner.GetElementType()!, 16), i);
            field.SetValue(spec, outer);
        }
        return spec;
    }

    // ---- engine state read by reflection (identical members in control and candidate)
    private static readonly FieldInfo PartialSetField = typeof(TextureCache).GetField("_partiallyMappedTextures", Any)!;
    private static readonly FieldInfo OwnersField = typeof(Texture).GetField("_poolOwners", Any)!;
    private static readonly FieldInfo QueueField = typeof(TexturePool).GetField("_dereferenceQueue", Any)!;
    private static readonly FieldInfo PoolChannelField = typeof(TexturePool).GetField("_channel", Any)!;
    private static readonly Type OwnerType = typeof(Texture).GetNestedType("TexturePoolOwner", Any)!;
    private static readonly Type RequestType = typeof(TexturePool).GetNestedType("DereferenceRequest", Any)!;

    private readonly record struct Owner(TexturePool Pool, int Id, ulong GpuAddress);

    private static List<Owner> Owners(Texture texture)
    {
        var list = new List<Owner>();
        var owners = (IEnumerable)OwnersField.GetValue(texture)!;
        lock (owners)
        {
            foreach (object owner in owners)
            {
                list.Add(new Owner((TexturePool)OwnerType.GetField("Pool")!.GetValue(owner), (int)OwnerType.GetField("ID")!.GetValue(owner)!,
                                   (ulong)OwnerType.GetField("GpuAddress")!.GetValue(owner)!));
            }
        }
        return list;
    }

    private static List<(int Id, bool Remap, Texture Texture)> Queue(TexturePool pool)
    {
        var list = new List<(int, bool, Texture)>();
        foreach (object request in (IEnumerable)QueueField.GetValue(pool)!)
        {
            list.Add(((int)RequestType.GetField("ID")!.GetValue(request)!, (bool)RequestType.GetField("IsRemapped")!.GetValue(request)!,
                      (Texture)RequestType.GetField("Texture")!.GetValue(request)));
        }
        return list;
    }

    private static string RangeText(MultiRange range)
    {
        var text = new StringBuilder();
        for (int i = 0; i < range.Count; i++)
        {
            MemoryRange sub = range.GetSubRange(i);
            text.Append(sub.Address == MemoryManager.PteUnmapped ? "u" : (sub.Address - GuestBase).ToString("x")).Append('+').Append(sub.Size.ToString("x")).Append(',');
        }
        return text.ToString();
    }

    private static bool PhysicallyOverlaps(MultiRange a, MultiRange b)
    {
        for (int i = 0; i < a.Count; i++)
        {
            MemoryRange x = a.GetSubRange(i);
            if (x.Address == MemoryManager.PteUnmapped || x.Size == 0) continue;
            for (int j = 0; j < b.Count; j++)
            {
                MemoryRange y = b.GetSubRange(j);
                if (y.Address == MemoryManager.PteUnmapped || y.Size == 0) continue;
                if (x.Address < y.Address + y.Size && y.Address < x.Address + x.Size) return true;
            }
        }
        return false;
    }

    private static string Hash(StringBuilder text)
    {
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text.ToString())), 0, 8);
    }

    // The collector's existing array counters (arrDeltaElems, arrDeltaChanged, arrFullElems: PD.Count in the delta pass), read
    // without the native diagnostics session: an epoch is installed by reflection. Reported, and compared as totals only.
    private static object _epoch;
    private static long CounterValue(string name)
    {
        if (_epoch == null || !Enum.TryParse(typeof(PD.Counter), name, out object value)) return -1;
        var counters = (long[][])_epoch.GetType().GetField("Counters", Any)!.GetValue(_epoch)!;
        return counters.Sum(slot => slot[(int)value]);
    }

    public static int Main(string[] args)
    {
        int steps = args.Length > 0 ? int.Parse(args[0]) : 440;
        int seed = args.Length > 1 ? int.Parse(args[1]) : 20261111;
        // For a failure's diagnosis: the steps (comma separated) whose state is written in full to stdout (lines STEP, E, P).
        var dumpSteps = new HashSet<int>(args.Length > 2 && args[2] != "-" ? args[2].Split(',').Select(int.Parse) : Array.Empty<int>());
        // "dependencies": the textures referenced at two addresses are created fully mapped and take part in the random
        // partial unmaps, hole fills and descriptor changes. Their two addresses then stop mapping the same pages, the
        // engine creates a second texture with a copy dependency, and such textures cannot be restored in place: the
        // control destroys and recreates them at every unrelated event, the candidate keeps them. The digests must still
        // be equal; the queue requirements are stated for the "gated" scene.
        bool dependencyScene = args.Length > 3 && args[3] == "dependencies";

        Type epochType = typeof(PD).GetNestedType("Epoch", Any);
        if (epochType != null)
        {
            _epoch = Activator.CreateInstance(epochType, Any, null, new object[] { 1L }, null);
            typeof(PD).GetField("_current", Any)!.SetValue(null, _epoch);
        }

        _texSize = SizeCalculator.GetBlockLinearTextureSize(TexWidth, TexHeight, 1, TexLevels, 1, 1, 1, 4, 16, 1, 1).TotalSize;
        _texPages = (_texSize + 0xFFF) / 0x1000;
        if (_texPages < 4 || (ulong)_texPages * 0x1000 > Slot) throw new InvalidOperationException("texture size " + _texSize);

        var backing = new MemoryBlock(GuestSize);
        _cpu = new Ryujinx.Cpu.Jit.MemoryManager(backing, 1UL << 36);
        _cpu.Map(GuestBase, 0, GuestSize, MemoryMapFlags.None);
        _cpu.IncrementReferenceCount();

        // Distinct bytes in every texture slot of the three texture regions.
        var filler = new byte[Slot];
        for (int region = 0; region < 3; region++)
        {
            ulong offset = region == 0 ? OrigOffset : region == 1 ? AltOffset : Tex2Offset;
            int count = region == 2 ? Slots2 : Slots;
            for (int slot = 0; slot < count; slot++)
            {
                new Random(1000 * (region + 1) + slot).NextBytes(filler);
                _cpu.Write(GuestBase + offset + (ulong)slot * Slot, filler);
            }
        }

        var renderer = new HostRenderer();
        var gpu = new GpuContext(renderer, new DirtyHacks(Array.Empty<ulong>()));
        gpu.SetGpuThread();
        gpu.RegisterProcess(1, _cpu);
        MemoryManager mm1 = gpu.CreateMemoryManager(1, GuestSize);
        MemoryManager mm2 = gpu.CreateMemoryManager(1, GuestSize);
        var managers = new[] { mm1, mm2 };
        if (!ReferenceEquals(mm1.Physical, mm2.Physical)) throw new InvalidOperationException("the two address spaces must share one texture cache");
        TextureCache textureCache = mm1.Physical.TextureCache;

        // ---- mappings
        mm1.Map(GuestBase, GpuBase, LowSize, PteKind.Pitch);
        mm1.Map(GuestBase + OrigOffset, GpuBase + OrigOffset, (ulong)Slots * Slot, PteKind.Pitch);
        mm2.Map(GuestBase, GpuBase, LowSize, PteKind.Pitch);
        mm2.Map(GuestBase + Tex2Offset, GpuBase + OrigOffset, (ulong)Slots2 * Slot, PteKind.Pitch);

        // ---- model of the guest mappings
        var holes1 = Enumerable.Range(0, Slots).Select(_ => new SortedSet<int>()).ToArray();     // unmapped pages at the main address
        var holes2 = Enumerable.Range(0, Slots2).Select(_ => new SortedSet<int>()).ToArray();
        var alternate = new bool[Slots];
        int HolePage(int slot) => 1 + slot % (_texPages - 2);
        ulong Backing(int slot) => GuestBase + (alternate[slot] ? AltOffset : OrigOffset) + (ulong)slot * Slot;

        int[] aliasSlots = Enumerable.Range(20, 9).ToArray();                    // 20..28: also reachable at AliasVa
        int[] alSlots = { 25, 26, 27, 28 };                                      // scripted alias sequences
        int[] scSlots = { 60, 61, 62, 63 };                                      // scripted short cache sequences
        var reserved = new HashSet<int>(alSlots.Concat(scSlots));
        if (!dependencyScene) reserved.UnionWith(aliasSlots);
        foreach (int slot in aliasSlots) mm1.Map(GuestBase + OrigOffset + (ulong)slot * Slot, AliasVa(slot), Slot, PteKind.Pitch);

        // Textures created partially mapped: a hole in their range before the first commit.
        // In the gated scene the textures with two addresses have the same hole at both, and no random step changes it.
        var twoAddressHoles = dependencyScene ? alSlots : aliasSlots;
        var partialAtStart = Enumerable.Range(1, 9).Concat(Enumerable.Range(30, 30)).Concat(scSlots).Concat(twoAddressHoles).ToArray();
        foreach (int slot in partialAtStart)
        {
            mm1.Unmap(TexVa(slot) + (ulong)HolePage(slot) * 0x1000, 0x1000);
            holes1[slot].Add(HolePage(slot));
        }
        foreach (int slot in twoAddressHoles) mm1.Unmap(AliasVa(slot) + (ulong)HolePage(slot) * 0x1000, 0x1000);
        for (int slot = 8; slot < 16; slot++)
        {
            mm2.Unmap(TexVa(slot) + (ulong)HolePage(slot) * 0x1000, 0x1000);
            holes2[slot].Add(HolePage(slot));
        }

        // ---- pool 1: which descriptor every id holds (slot, through the alias address or not), -1 = empty
        var idSlot = new int[Slots];
        var idAlias = new bool[Slots];
        for (int id = 0; id < Slots; id++) idSlot[id] = id;
        idSlot[0] = -1; idSlot[219] = -1;
        for (int k = 0; k < 10; k++) idSlot[200 + k] = 10 + k;                                   // ids sharing one texture at one address
        for (int k = 0; k < 9; k++) { idSlot[210 + k] = 20 + k; idAlias[210 + k] = true; }       // the same texture at another address
        void WriteId(int id) => WriteDescriptor(Pool1Offset, id, idSlot[id] < 0 ? null : Descriptor(idAlias[id] ? AliasVa(idSlot[id]) : TexVa(idSlot[id])));
        for (int id = 0; id < Slots; id++) WriteId(id);
        for (int id = 0; id < Slots2; id++) WriteDescriptor(Pool2Offset, id, Descriptor(TexVa(id)));

        // ---- channels and bindings
        GpuChannel channel1 = gpu.CreateChannel();
        channel1.BindMemory(mm1);
        GpuChannel channel2 = gpu.CreateChannel();
        channel2.BindMemory(mm2);
        TextureManager textures1 = channel1.TextureManager, textures2 = channel2.TextureManager;
        int direct = TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct);
        int[] slotIds = { 5, 12, 22, 212, 35, 60, 25, 150 };                     // ordinary bindings: handle words 0..7
        var bindings1 = new List<TextureBindingInfo>
        {
            new(Target.Texture2D, 2, 0, Slots, 0, direct, TextureUsageFlags.None, false),
            new(Target.Texture2D, 2, 1, Slots - 1, 0, direct, TextureUsageFlags.None, false),
        };
        for (int word = 0; word < slotIds.Length; word++)
        {
            bindings1.Add(new TextureBindingInfo(Target.Texture2D, 2, 2 + word, 1, -1, word, TextureUsageFlags.None, false));
            _cpu.Write(GuestBase + CbufOffset + (ulong)word * 4, BitConverter.GetBytes(slotIds[word]));
        }
        textures1.SetGraphicsTexturePool(GpuBase + Pool1Offset, Slots - 1);
        textures1.SetGraphicsSamplerPool(GpuBase + SamplerOffset, 63, Ryujinx.Graphics.Gpu.Engine.Types.SamplerIndex.Independently);
        textures1.SetGraphicsTextureBufferIndex(0);
        textures1.SetGraphicsBindings(Bindings(5, 4, bindings1.ToArray()));
        channel1.BufferManager.SetGraphicsUniformBuffer(4, 0, GpuBase + CbufOffset, 0x100);
        textures2.SetGraphicsTexturePool(GpuBase + Pool2Offset, Slots2 - 1);
        textures2.SetGraphicsSamplerPool(GpuBase + SamplerOffset, 63, Ryujinx.Graphics.Gpu.Engine.Types.SamplerIndex.Independently);
        textures2.SetGraphicsTextureBufferIndex(0);
        textures2.SetGraphicsBindings(Bindings(5, 4, new[] { new TextureBindingInfo(Target.Texture2D, 2, 0, Slots2, 0, direct, TextureUsageFlags.None, false) }));
        var spec = Spec(6);

        void Commit()
        {
            gpu.AdvanceSequence();
            textures1.CommitGraphicsBindings(spec, out _);
            gpu.AdvanceSequence();
            textures2.CommitGraphicsBindings(spec, out _);
        }

        Commit();
        textureCache.Tick();
        Commit();
        textureCache.Tick();
        TexturePool pool1 = textures1.GetTexturePool(GpuBase + Pool1Offset, Slots - 1);
        TexturePool pool2 = textures2.GetTexturePool(GpuBase + Pool2Offset, Slots2 - 1);
        var pools = new[] { pool1, pool2 };
        var poolSizes = new[] { Slots, Slots2 };
        MemoryManager PoolManager(TexturePool pool) => ((GpuChannel)PoolChannelField.GetValue(pool)!).MemoryManager;
        var partialSet = (HashSet<Texture>)PartialSetField.GetValue(textureCache)!;

        var scene = new Dictionary<string, object>
        {
            ["textureBytes"] = _texSize,
            ["texturePages"] = _texPages,
            ["pool1Items"] = Enumerable.Range(0, Slots).Count(id => pool1.GetCachedItem(id) != null),
            ["pool2Items"] = Enumerable.Range(0, Slots2).Count(id => pool2.GetCachedItem(id) != null),
            ["partiallyMappedSetAtStart"] = partialSet.Count,
            ["idsSharingOneAddress"] = Enumerable.Range(200, 10).Count(id => ReferenceEquals(pool1.GetCachedItem(id), pool1.GetCachedItem(id - 190))),
            ["texturesWithTwoAddresses"] = Enumerable.Range(210, 9).Count(id => ReferenceEquals(pool1.GetCachedItem(id), pool1.GetCachedItem(id - 190)) &&
                                                                            Owners(pool1.GetCachedItem(id)).Select(o => o.GpuAddress).Distinct().Count() == 2),
            ["addressSpaces"] = 2,
            ["arrays"] = renderer.Arrays.Select(a => a.Textures.Length).ToArray(),
            ["ordinaryBindings"] = slotIds.Length,
            ["dependencyScene"] = dependencyScene,
        };

        // ---- the script
        var random = new Random(seed);
        var output = new List<Dictionary<string, object>>();
        var plan = new Dictionary<int, string>();
        for (int k = 0; k < 4; k++)
        {
            plan[30 + 80 * k] = "scAway:" + k; plan[31 + 80 * k] = "scFillBack:" + k;
            plan[50 + 80 * k] = "alAway:" + k; plan[51 + 80 * k] = "alUnrelated:" + k; plan[52 + 80 * k] = "alFill:" + k; plan[53 + 80 * k] = "alBack:" + k;
            plan[54 + 80 * k] = "alClean:" + k;
        }
        string[] kinds = { "unrelatedMap", "unrelatedMap", "unrelatedMap", "unrelatedMap", "unrelatedUnmap", "unrelatedUnmap", "unrelatedUnmap",
                           "otherMmMap", "otherMmUnmap", "holeFill", "holeFill", "holeFill", "partialUnmap", "partialUnmap", "partialUnmap",
                           "remap", "remap", "rewrite", "rewrite", "rewrite", "mm2HoleFill", "mm2PartialUnmap" };

        for (int step = 0; step < steps; step++)
        {
            string kind = plan.TryGetValue(step, out string planned) ? planned.Split(':')[0] : kinds[random.Next(kinds.Length)];
            int index = planned != null ? int.Parse(planned.Split(':')[1]) : 0;

            // The event of this step, if any (one Map or Unmap), decided before anything is changed.
            int manager = 0; bool isMap = false; ulong va = 0, size = 0, pa = 0;
            Action afterEvent = null;   // descriptor writes that follow the event
            bool hasEvent = false;
            void Event(int m, bool map, ulong address, ulong length, ulong physical = 0)
            {
                manager = m; isMap = map; va = address; size = length; pa = physical; hasEvent = true;
            }
            switch (kind)
            {
                case "unrelatedMap":
                case "alUnrelated":
                {
                    int pages = 1 + random.Next(4), page = random.Next(64 - pages);
                    Event(0, true, ScratchVa + (ulong)page * 0x1000, (ulong)pages * 0x1000, GuestBase + ScratchOffset + (ulong)random.Next(64 - pages) * 0x1000);
                    break;
                }
                case "unrelatedUnmap":
                {
                    int pages = 1 + random.Next(4), page = random.Next(64 - pages);
                    Event(0, false, ScratchVa + (ulong)page * 0x1000, (ulong)pages * 0x1000);
                    break;
                }
                case "otherMmMap":
                case "otherMmUnmap":
                {
                    // Address space 2, at the numeric address of a texture of address space 1 (nothing of space 2 is there).
                    // Preferably the address of a partially mapped one (a member of the set, referenced by pool 1 only).
                    int[] partial = Enumerable.Range(64, 136).Where(s => holes1[s].Count > 0).ToArray();
                    int slot = partial.Length > 0 ? partial[random.Next(partial.Length)] : 64 + random.Next(136), page = random.Next(_texPages);
                    Event(1, kind == "otherMmMap", TexVa(slot) + (ulong)page * 0x1000, 0x1000, GuestBase + ScratchOffset + (ulong)random.Next(64) * 0x1000);
                    break;
                }
                case "holeFill":
                {
                    int[] candidates = Enumerable.Range(1, 199).Where(s => !reserved.Contains(s) && holes1[s].Count > 0).ToArray();
                    if (candidates.Length == 0) { kind = "rewriteSame"; break; }
                    int slot = candidates[random.Next(candidates.Length)], page = holes1[slot].ElementAt(random.Next(holes1[slot].Count));
                    holes1[slot].Remove(page);
                    Event(0, true, TexVa(slot) + (ulong)page * 0x1000, 0x1000, Backing(slot) + (ulong)page * 0x1000);
                    break;
                }
                case "partialUnmap":
                {
                    int slot;
                    do { slot = 1 + random.Next(199); } while (reserved.Contains(slot) || holes1[slot].Count >= _texPages - 2);
                    int page;
                    do { page = 1 + random.Next(_texPages - 1); } while (holes1[slot].Contains(page));
                    holes1[slot].Add(page);
                    Event(0, false, TexVa(slot) + (ulong)page * 0x1000, 0x1000);
                    break;
                }
                case "remap":
                {
                    int slot = 64 + random.Next(136);
                    alternate[slot] = !alternate[slot];
                    holes1[slot].Clear();
                    Event(0, true, TexVa(slot), Slot, Backing(slot));
                    break;
                }
                case "rewrite":
                {
                    int id = 100 + random.Next(100);
                    int choice = random.Next(4);
                    idSlot[id] = choice == 0 ? id : choice == 1 ? -1 : choice == 2 ? 100 + random.Next(100) : 220 + random.Next(36);
                    idAlias[id] = false;
                    afterEvent = () => WriteId(id);
                    break;
                }
                case "mm2HoleFill":
                {
                    int[] candidates = Enumerable.Range(0, Slots2).Where(s => holes2[s].Count > 0).ToArray();
                    if (candidates.Length == 0) { kind = "rewriteSame"; break; }
                    int slot = candidates[random.Next(candidates.Length)], page = holes2[slot].ElementAt(random.Next(holes2[slot].Count));
                    holes2[slot].Remove(page);
                    Event(1, true, TexVa(slot) + (ulong)page * 0x1000, 0x1000, GuestBase + Tex2Offset + (ulong)slot * Slot + (ulong)page * 0x1000);
                    break;
                }
                case "mm2PartialUnmap":
                {
                    int slot;
                    do { slot = random.Next(Slots2); } while (holes2[slot].Count >= _texPages - 2);
                    int page;
                    do { page = 1 + random.Next(_texPages - 1); } while (holes2[slot].Contains(page));
                    holes2[slot].Add(page);
                    Event(1, false, TexVa(slot) + (ulong)page * 0x1000, 0x1000);
                    break;
                }
                case "scAway":
                {
                    // The only id of a partially mapped texture is given another descriptor: the texture goes to the short cache.
                    int id = scSlots[index];
                    idSlot[id] = 220 + index;
                    afterEvent = () => WriteId(id);
                    break;
                }
                case "scFillBack":
                {
                    // Its hole is filled while no pool references it, then the id names it again in the same step.
                    int slot = scSlots[index], page = HolePage(slot);
                    holes1[slot].Remove(page);
                    Event(0, true, TexVa(slot) + (ulong)page * 0x1000, 0x1000, Backing(slot) + (ulong)page * 0x1000);
                    idSlot[slot] = slot;
                    afterEvent = () => WriteId(slot);
                    break;
                }
                case "alAway":
                {
                    // A texture created partially mapped keeps only its reference at the alias address.
                    int id = alSlots[index];
                    idSlot[id] = 230 + index;
                    afterEvent = () => WriteId(id);
                    break;
                }
                case "alFill":
                {
                    // The hole is filled at the main address only (the alias address keeps its hole).
                    int slot = alSlots[index], page = HolePage(slot);
                    holes1[slot].Remove(page);
                    Event(0, true, TexVa(slot) + (ulong)page * 0x1000, 0x1000, Backing(slot) + (ulong)page * 0x1000);
                    break;
                }
                case "alBack":
                {
                    // The id names the main address again: the texture kept at the alias address has another range now.
                    int id = alSlots[index];
                    idSlot[id] = id;
                    afterEvent = () => WriteId(id);
                    break;
                }
                case "alClean":
                {
                    // Both ids are emptied: the two textures (now linked by a copy dependency) leave the pool before any event.
                    int id = alSlots[index], aliasId = 215 + index;
                    idSlot[id] = -1; idSlot[aliasId] = -1;
                    afterEvent = () => { WriteId(id); WriteId(aliasId); };
                    break;
                }
            }
            if (kind == "rewriteSame")
            {
                int id = 100 + random.Next(100);
                afterEvent = () => WriteId(id);
            }

            var record = new Dictionary<string, object> { ["i"] = step, ["k"] = kind };
            var queuedBefore = new Dictionary<(int, int), Texture>();
            if (hasEvent)
            {
                // ---- what the event should queue, from the state before it
                MemoryManager eventManager = managers[manager];
                MultiRange physical = eventManager.GetPhysicalRegions(va, size);
                ulong start = va & ~0xFFFUL, end = (va + size + 0xFFF) & ~0xFFFUL;
                var considered = new HashSet<Texture>(partialSet);
                var overlapped = new HashSet<Texture>();
                for (int p = 0; p < 2; p++)
                {
                    for (int id = 0; id < poolSizes[p]; id++)
                    {
                        Texture texture = pools[p].GetCachedItem(id);
                        if (texture != null && PhysicallyOverlaps(texture.Range, physical)) overlapped.Add(texture);
                    }
                }
                foreach (Texture texture in partialSet)
                {
                    if (PhysicallyOverlaps(texture.Range, physical)) overlapped.Add(texture);
                }
                considered.UnionWith(overlapped);
                int membersWithOwners = 0, sweepOwners = 0, ownerless = 0, neverSwept = 0, touched = 0;
                var expected = new SortedSet<string>();
                foreach (Texture texture in considered)
                {
                    List<Owner> owners = Owners(texture);
                    sweepOwners += owners.Count;
                    if (owners.Count > 0) membersWithOwners++; else ownerless++;
                    bool touch = overlapped.Contains(texture) || !texture.ChangedMapping || owners.Count == 0 ||
                                 owners.Any(o => ReferenceEquals(PoolManager(o.Pool), eventManager) && o.GpuAddress < end && o.GpuAddress + texture.Size > start);
                    if (!texture.ChangedMapping && !overlapped.Contains(texture)) neverSwept++;
                    if (touch)
                    {
                        touched++;
                        foreach (Owner owner in owners) expected.Add(Array.IndexOf(pools, owner.Pool) + ":" + owner.Id);
                    }
                    foreach (Owner owner in owners) queuedBefore[(Array.IndexOf(pools, owner.Pool), owner.Id)] = texture;
                }
                record["ev"] = $"{manager}:{(isMap ? "map" : "unmap")}:{va:x}+{size:x}";
                record["set"] = partialSet.Count;
                record["overlapped"] = overlapped.Count;
                record["membersWithOwners"] = membersWithOwners;
                record["ownerless"] = ownerless;
                record["neverSwept"] = neverSwept;
                record["sweepOwners"] = sweepOwners;
                record["considered"] = considered.Count;
                record["touched"] = touched;
                record["expected"] = expected.ToArray();
                record["pending"] = Queue(pool1).Count + Queue(pool2).Count;

                var itemsBefore = new[] { Enumerable.Range(0, Slots).Select(id => pool1.GetCachedItem(id)).ToArray(),
                                          Enumerable.Range(0, Slots2).Select(id => pool2.GetCachedItem(id)).ToArray() };
                if (isMap) eventManager.Map(pa, va, size, PteKind.Pitch); else eventManager.Unmap(va, size);
                record["setAfter"] = partialSet.Count;

                // The pool references the event took away (QueueUpdateMapping and ForceRemove both empty the pool item; a
                // removal request does not carry its id), and the requests it left in the dereference queues.
                var queued = new SortedSet<string>();
                int remaps = 0, removes = 0;
                for (int p = 0; p < 2; p++)
                {
                    for (int id = 0; id < poolSizes[p]; id++)
                    {
                        if (itemsBefore[p][id] != null && pools[p].GetCachedItem(id) == null) queued.Add(p + ":" + id);
                    }
                    foreach ((int _, bool remap, Texture _) in Queue(pools[p]))
                    {
                        if (remap) remaps++; else removes++;
                    }
                }
                record["queued"] = queued.ToArray();
                record["remapRequests"] = remaps;
                record["removeRequests"] = removes;
            }
            afterEvent?.Invoke();

            long setTexturesCalls = HostTextureArray.Calls, setTexturesElements = HostTextureArray.Elements, slotCalls = SlotCalls, arrayBinds = ArrayBinds;
            int created = HostTexture.Created, uploads = HostTexture.Uploads;
            long visited = CounterValue("ArrayDeltaElements"), changed = CounterValue("ArrayDeltaChanged"), full = CounterValue("ArrayFullElements");
            Commit();
            record["setTexturesCalls"] = HostTextureArray.Calls - setTexturesCalls;
            record["setTexturesElements"] = HostTextureArray.Elements - setTexturesElements;
            record["slotCalls"] = SlotCalls - slotCalls;
            record["arrayBinds"] = ArrayBinds - arrayBinds;
            record["hostTexturesCreated"] = HostTexture.Created - created;
            record["uploads"] = HostTexture.Uploads - uploads;
            record["deltaVisited"] = CounterValue("ArrayDeltaElements") - visited;
            record["deltaChanged"] = CounterValue("ArrayDeltaChanged") - changed;
            record["fullRebuildElements"] = CounterValue("ArrayFullElements") - full;
            record["restored"] = queuedBefore.Count(q => record.ContainsKey("queued") && ((string[])record["queued"]).Contains(q.Key.Item1 + ":" + q.Key.Item2) &&
                                                         ReferenceEquals(pools[q.Key.Item1].GetCachedItem(q.Key.Item2), q.Value));
            record["leftInQueues"] = Queue(pool1).Count + Queue(pool2).Count;

            // ---- the observable state after the commit
            var elements = new StringBuilder();
            var identities = new StringBuilder();
            foreach (HostTextureArray array in renderer.Arrays)
            {
                foreach (ITexture texture in array.Textures)
                {
                    elements.Append(texture == null ? 0UL : ((HostTexture)texture).Signature()).Append(',');
                    identities.Append(texture == null ? 0 : ((HostTexture)texture).Id).Append(',');
                }
                elements.Append('|');
            }
            var slots = new StringBuilder();
            for (int binding = 2; binding < 2 + slotIds.Length; binding++)
            {
                BoundSlots.TryGetValue(binding, out ITexture texture);
                slots.Append(texture == null ? 0UL : ((HostTexture)texture).Signature()).Append(',');
                identities.Append(texture == null ? 0 : ((HostTexture)texture).Id).Append(',');
            }
            var ranges = new StringBuilder();
            var membership = new StringBuilder();
            var flags = new StringBuilder();
            for (int p = 0; p < 2; p++)
            {
                for (int id = 0; id < poolSizes[p]; id++)
                {
                    Texture texture = pools[p].GetCachedItem(id);
                    ranges.Append(texture == null ? "-" : RangeText(texture.Range)).Append(';');
                    membership.Append(texture == null ? '-' : partialSet.Contains(texture) ? '1' : '0');
                    flags.Append(texture == null ? '-' : texture.ChangedMapping ? '1' : '0');
                }
            }
            membership.Append('#').Append(partialSet.Count);
            record["d"] = new[] { Hash(elements), Hash(slots), Hash(ranges), Hash(membership) };
            record["identities"] = Hash(identities);
            record["changedMappingFlags"] = Hash(flags);
            output.Add(record);
            if (dumpSteps.Contains(step))
            {
                Console.Out.WriteLine($"STEP {step} {kind} {(record.TryGetValue("ev", out object ev) ? ev : "")}");
                for (int a = 0; a < renderer.Arrays.Count; a++)
                {
                    for (int e = 0; e < renderer.Arrays[a].Textures.Length; e++)
                    {
                        var host = (HostTexture)renderer.Arrays[a].Textures[e];
                        Console.Out.WriteLine($"E a{a} [{e}] {(host == null ? "null" : host.Signature().ToString("x") + " host#" + host.Id + " " + host.Describe())}");
                    }
                }
                for (int p = 0; p < 2; p++)
                {
                    for (int id = 0; id < poolSizes[p]; id++)
                    {
                        Texture texture = pools[p].GetCachedItem(id);
                        Console.Out.WriteLine($"P p{p} [{id}] {(texture == null ? "-" : RangeText(texture.Range) + " set=" + partialSet.Contains(texture) + " cm=" + texture.ChangedMapping + " seq=" + texture.InvalidatedSequence + " view=" + texture.IsView + " host#" + ((HostTexture)texture.HostTexture).Id + " sig=" + ((HostTexture)texture.HostTexture).Signature().ToString("x") + " owners=" + string.Join("/", Owners(texture).Select(o => Array.IndexOf(pools, o.Pool) + ":" + o.Id + "@" + o.GpuAddress.ToString("x"))))}");
                    }
                }
            }

            textureCache.Tick();   // one presented frame per step
        }

        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["scene"] = scene,
            ["seed"] = seed,
            ["steps"] = output,
            ["hostTexturesCreated"] = HostTexture.Created,
            ["uploads"] = HostTexture.Uploads,
            ["uploadBytes"] = HostTexture.UploadBytes,
        }));
        return 0;
    }
}
