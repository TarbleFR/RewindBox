// Driver of melonx_shader_cache_parallel_read_test.py. It runs the production disk shader cache load of a built
// Ryujinx.Graphics.Gpu.dll (the whole ParallelDiskCacheLoader.LoadShaders with the real DiskCacheHostStorage,
// DiskCacheGuestStorage, serializer, specialization state, shader information builder and code tables; only the
// renderer is a double that records what it is asked to create) against cache directories it writes itself, in the
// on-disk format, then alters. The same driver runs with the control's assembly and with the candidate's; the gate
// compares the two reports. The engine's internal types are reached by reflection: nothing of the engine is recompiled.
//
// Fixture.dll run <work directory> [directory of a real cache: guest.*, shared.*, vulkan_apple.*]
// Fixture.dll perf <cache directory> <loads> <settings, comma separated: control | default | number of threads>
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common;
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Logging;
using Ryujinx.Common.Logging.Targets;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Shader.Translation;

sealed class Rng
{
    private ulong _state;

    public Rng(ulong seed)
    {
        _state = seed * 0x9E3779B97F4A7C15UL + 0x1234567;
        Next();
    }

    public ulong Next()
    {
        _state ^= _state << 13;
        _state ^= _state >> 7;
        _state ^= _state << 17;
        return _state;
    }

    public int Below(int bound) => (int)(Next() % (ulong)bound);

    public int Between(int low, int high) => low + Below(high - low + 1);
}

// What one load is asked to do besides loading, and what the renderer double sees of it.
sealed class Probe
{
    public int Threads = -1;          // candidate: value given to the storage's _readAheadThreads; -1 leaves its own
    public bool CancelBefore;
    public int CancelAtCreate = -1;   // the token is cancelled inside this CreateProgram call (0-based)
    public int FailLinkAt = -1;       // this program's link check answers Failure
    public int MemoryAt = -1;         // the GPU thread is held in this CreateProgram call, then reachable memory is measured
    public int MemorySettleMilliseconds = 300;
    public bool Digest = true;

    public CancellationTokenSource Cancellation;
    public long CancelTimestamp;
    public long MemoryBytes = -1;
    public int Programs;
    public long SourceBytes;
    public readonly List<byte[]> CallDigests = new();
}

sealed class FakeProgram(int index, bool failLink) : IProgram
{
    public int Index { get; } = index;
    public bool CanBindWhileIncomplete => false;
    public ProgramLinkStatus CheckProgramLink(bool blocking) => failLink ? ProgramLinkStatus.Failure : ProgramLinkStatus.Success;
    public byte[] GetBinary() => throw new NotSupportedException();
    public void Dispose() { }
}

// The renderer boundary. A program is "created" by recording what was handed over: every stage, every byte of its
// code, and what the shader information says.
sealed class FakeRenderer(Probe probe) : IRenderer
{
    public event EventHandler<ScreenCaptureImageInfo> ScreenCaptured { add { } remove { } }
    public bool PreferThreading => false;
    public IPipeline Pipeline => null;
    public IWindow Window => null;
    public uint ProgramCount => (uint)probe.Programs;
    public void BackgroundContextAction(Action action, bool alwaysBackground = false) => action();
    public BufferHandle CreateBuffer(int size, BufferAccess access = BufferAccess.Default) => throw new NotSupportedException();
    public BufferHandle CreateBuffer(nint pointer, int size) => throw new NotSupportedException();
    public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> storageBuffers) => throw new NotSupportedException();
    public IImageArray CreateImageArray(int size, bool isBuffer) => throw new NotSupportedException();

    public IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info)
    {
        int index = probe.Programs++;

        if (probe.Digest)
        {
            using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            hash.AppendData(BitConverter.GetBytes(shaders.Length));

            foreach (ShaderSource source in shaders)
            {
                hash.AppendData(BitConverter.GetBytes((int)source.Stage));
                hash.AppendData(BitConverter.GetBytes(source.BinarySegment.Count));
                hash.AppendData(source.BinarySegment.AsSpan());
            }

            StringBuilder text = new();
            text.Append(info.FragmentOutputMap).Append('|').Append(info.FromCache).Append('|').Append(info.State.HasValue).Append('|');

            if (info.ResourceLayout.Sets != null)
            {
                foreach (ResourceDescriptorCollection set in info.ResourceLayout.Sets)
                {
                    text.Append('{');
                    foreach (ResourceDescriptor descriptor in set.Descriptors)
                    {
                        text.Append(descriptor.Binding).Append(',').Append(descriptor.Count).Append(',').Append((int)descriptor.Type).Append(',').Append((int)descriptor.Stages).Append(';');
                    }
                    text.Append('}');
                }
            }

            hash.AppendData(Encoding.UTF8.GetBytes(text.ToString()));
            probe.CallDigests.Add(hash.GetHashAndReset());
        }

        foreach (ShaderSource source in shaders)
        {
            probe.SourceBytes += source.BinarySegment.Count;
        }

        if (index == probe.CancelAtCreate)
        {
            probe.CancelTimestamp = Stopwatch.GetTimestamp();
            probe.Cancellation.Cancel();
        }

        if (index == probe.MemoryAt)
        {
            // The GPU thread stays here: whatever reads ahead of it fills its window. Then what is reachable is counted.
            Thread.Sleep(probe.MemorySettleMilliseconds);
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
            probe.MemoryBytes = GC.GetTotalMemory(true);
        }

        return new FakeProgram(index, index == probe.FailLinkAt);
    }

    public ISampler CreateSampler(SamplerCreateInfo info) => throw new NotSupportedException();
    public ITexture CreateTexture(TextureCreateInfo info) => throw new NotSupportedException();
    public ITextureArray CreateTextureArray(int size, bool isBuffer) => throw new NotSupportedException();
    public bool PrepareHostMapping(nint address, ulong size) => false;
    public void CreateSync(ulong id, bool strict) { }
    public void DeleteBuffer(BufferHandle buffer) { }
    public PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size) => throw new NotSupportedException();

    public Capabilities GetCapabilities()
    {
        object capabilities = default(Capabilities);
        void Set(string name, object value) => typeof(Capabilities).GetField(name).SetValue(capabilities, value);
        Set("Api", TargetApi.Vulkan);
        Set("VendorName", "Apple");
        Set("UniformBufferSetIndex", 0);
        Set("StorageBufferSetIndex", 1);
        Set("TextureSetIndex", 2);
        Set("ImageSetIndex", 3);
        Set("ExtraSetBaseIndex", 4);
        Set("MaximumExtraSets", 4);
        Set("MaximumUniformBuffersPerStage", 18u);
        Set("MaximumStorageBuffersPerStage", 16u);
        Set("MaximumTexturesPerStage", 32u);
        Set("MaximumImagesPerStage", 16u);
        Set("SupportsGeometryShader", true);
        Set("SupportsTransformFeedback", true);
        Set("SupportsLayerVertexTessellation", true);
        return (Capabilities)capabilities;
    }

    public ulong GetCurrentSync() => 0;
    public HardwareInfo GetHardwareInfo() => default;
    public IProgram LoadProgramBinary(byte[] programBinary, bool hasFragmentShader, ShaderInfo info) => throw new NotSupportedException();
    public void SetBufferData(BufferHandle buffer, int offset, ReadOnlySpan<byte> data) { }
    public void UpdateCounters() { }
    public void PreFrame() { }
    public ICounterEvent ReportCounter(CounterType type, EventHandler<ulong> resultHandler, float divisor, bool hostReserved) => throw new NotSupportedException();
    public void ResetCounter(CounterType type) { }
    public void WaitSync(ulong id) { }
    public void Initialize(GraphicsDebugLevel logLevel) { }
    public void SetInterruptAction(Action<Action> interruptAction) { }
    public void Screenshot() { }
    public void Dispose() { }
}

sealed class LogCapture : ILogTarget
{
    public readonly List<string> Lines = new();
    public string Name => "capture";

    public void Log(object sender, LogEventArgs args)
    {
        lock (Lines)
        {
            Lines.Add(args.Level + " " + args.Message);
        }
    }

    public void Dispose() { }
}

// The engine's internal types, by reflection.
static class Engine
{
    public const BindingFlags All = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    public static readonly Assembly Gpu = typeof(GpuContext).Assembly;
    private const string Cache = "Ryujinx.Graphics.Gpu.Shader.DiskCache.";
    public static readonly Type Storage = Gpu.GetType(Cache + "DiskCacheHostStorage", true);
    public static readonly Type Loader = Gpu.GetType(Cache + "ParallelDiskCacheLoader", true);
    public static readonly Type Serializer = Gpu.GetType(Cache + "BinarySerializer", true);
    public static readonly Type GraphicsTable = Gpu.GetType("Ryujinx.Graphics.Gpu.Shader.ShaderCacheHashTable", true);
    public static readonly Type ComputeTable = Gpu.GetType("Ryujinx.Graphics.Gpu.Shader.ComputeShaderCacheHashTable", true);
    public static readonly Type Program = Gpu.GetType("Ryujinx.Graphics.Gpu.Shader.CachedShaderProgram", true);
    public static readonly Type Stage = Gpu.GetType("Ryujinx.Graphics.Gpu.Shader.CachedShaderStage", true);
    public static readonly Type Specialization = Gpu.GetType("Ryujinx.Graphics.Gpu.Shader.ShaderSpecializationState", true);
    public static readonly FieldInfo Threads = Storage.GetField("_readAheadThreads", All);
    public static readonly Type ReadAhead = Storage.GetNestedType("ProgramReadAhead", All);
    public static bool HasReadAhead => Threads != null;
    public static uint CodeGenVersion => (uint)Storage.GetProperty("CodeGenVersion", All).GetValue(null);

    public static object New(Type type, params object[] arguments) => Activator.CreateInstance(type, All, null, arguments, null);
}

// A cache directory written here, byte by byte, in the on-disk format (DiskCacheHostStorage and DiskCacheGuestStorage:
// tables of contents, Brotli records), with where each record lies.
sealed class GuestCode
{
    public byte[] Code, Cb1;
    public long TocEntry, DataOffset, CompressedOffset, CompressedLength;
}

sealed class ProgramSpec
{
    public bool Compute;
    public int[] Guest = [-1, -1, -1, -1, -1, -1];
    public byte[] HostCode;
    public ulong Seed;
    public uint? StageMask;       // written instead of the real one
    public (int Stage, int Index)? GuestIndex; // written instead of the real one
    public long SharedOffset, SharedLength, HostOffset, HostCompressed, InfoOffset, InfoLength;
}

sealed class CacheSet
{
    public string Name;
    public readonly List<GuestCode> Codes = new();
    public readonly List<ProgramSpec> Programs = new();
    public long HostBytes, HostCompressedBytes, GuestBytes;
    public int DistinctCodes => Codes.Count;
}

static class CacheWriter
{
    private static uint Magic(string text) => (uint)(text[0] | text[1] << 8 | text[2] << 16 | text[3] << 24);
    public const uint FormatVersion = (1u << 16) | 2;
    public const ulong Timestamp = 1790000000;

    // Words like those of a SPIR-V module: instructions of two to five words (an operation word, then small numbers
    // that mostly follow each other), and runs of words that repeat earlier ones. Brotli at the level the cache writes
    // with makes about a third of it and decodes it at about 300 MiB/s on the host: the ratio (3.2) and speed measured
    // for the real host cache.
    public static void FillWords(Span<byte> target, Rng rng)
    {
        uint[] operations = new uint[24];
        for (int i = 0; i < operations.Length; i++) operations[i] = (uint)(((2 + i % 4) << 16) | rng.Below(400));
        uint id = 1;
        int offset = 0;

        while (offset + 4 <= target.Length)
        {
            ulong roll = rng.Next();

            if (offset >= 256 && (int)((roll >> 32) % 100) < 42)
            {
                int run = 3 + (int)((roll >> 8) % 10);
                int from = offset - 4 * (1 + (int)((roll >> 16) % (ulong)Math.Min(offset / 4 - 16, 8192)));
                for (int word = 0; word < run && offset + 4 <= target.Length; word++, offset += 4, from += 4) target.Slice(from, 4).CopyTo(target[offset..]);
                continue;
            }

            uint operation = operations[roll % (ulong)operations.Length];
            BitConverter.TryWriteBytes(target[offset..], operation);
            offset += 4;

            for (int word = 1; word < (int)(operation >> 16) && offset + 4 <= target.Length; word++, offset += 4)
            {
                ulong operand = rng.Next();
                uint value = word == 1 ? id++ : (operand & 3) == 0 ? (uint)(operand >> 40) & 0xfff : id - 1 - (uint)((operand >> 8) % 64);
                BitConverter.TryWriteBytes(target[offset..], value);
            }
        }
    }

    public static CacheSet Build(string name, int programs, int hostMinimum, int hostMaximum, int guestMinimum, int guestMaximum,
        ulong seed, int[] hugePrograms = null, int hugeSize = 0)
    {
        CacheSet set = new() { Name = name };
        Rng rng = new(seed);
        Dictionary<string, int> shared = new();

        int Code(string key)
        {
            if (key != null && shared.TryGetValue(key, out int known))
            {
                return known;
            }

            // Random content, a multiple of eight bytes as guest code is: no code is the start of another.
            byte[] code = new byte[rng.Between(guestMinimum / 8, guestMaximum / 8) * 8];
            for (int i = 0; i < code.Length; i++) code[i] = (byte)rng.Next();
            byte[] cb1 = new byte[new[] { 0, 16, 64 }[rng.Below(3)]];
            for (int i = 0; i < cb1.Length; i++) cb1[i] = (byte)rng.Next();
            set.Codes.Add(new GuestCode { Code = code, Cb1 = cb1 });
            set.GuestBytes += code.Length;
            if (key != null) shared[key] = set.Codes.Count - 1;
            return set.Codes.Count - 1;
        }

        int lastFragment = -1;

        for (int i = 0; i < programs; i++)
        {
            ProgramSpec program = new() { Compute = i % 7 == 3, Seed = rng.Next() };
            List<int> sources = new();

            if (program.Compute)
            {
                program.Guest[0] = Code("compute" + i / 14);
                sources.Add(0);
            }
            else
            {
                if (i % 11 == 5) program.Guest[0] = Code("vertexA" + i / 22);
                program.Guest[1] = Code("vertex" + i / 3);
                if (i % 17 == 9) { program.Guest[2] = Code(null); program.Guest[3] = Code(null); }
                if (i % 13 == 7) program.Guest[4] = Code("geometry" + i / 26);
                program.Guest[5] = i % 9 == 8 && lastFragment >= 0 ? lastFragment : Code(null);
                lastFragment = program.Guest[5];
                for (int stage = 1; stage < 6; stage++) if (program.Guest[stage] >= 0) sources.Add(stage);
            }

            // The host code as ShaderBinarySerializer packs it: a count, then stage, length and SPIR-V of each stage.
            int size = hugePrograms != null && Array.IndexOf(hugePrograms, i) >= 0 ? hugeSize : rng.Between(hostMinimum, hostMaximum);
            int each = Math.Max(size / sources.Count / 4 * 4, 4);
            using MemoryStream host = new();
            host.Write(BitConverter.GetBytes(sources.Count));
            byte[] words = new byte[each];

            foreach (int stage in sources)
            {
                host.Write(BitConverter.GetBytes(stage));
                host.Write(BitConverter.GetBytes(each));
                FillWords(words, rng);
                host.Write(words);
            }

            program.HostCode = host.ToArray();
            set.HostBytes += program.HostCode.Length;
            set.Programs.Add(program);
        }

        return set;
    }

    private static void Compressed(Stream stream, ReadOnlySpan<byte> data)
    {
        stream.WriteByte(2); // CompressionAlgorithm.Brotli
        using BrotliStream brotli = new(stream, CompressionLevel.Fastest, true);
        brotli.Write(data);
    }

    private static byte[] Specialization(ProgramSpec program)
    {
        Rng rng = new(program.Seed);
        using MemoryStream stream = new();
        using BinaryWriter writer = new(stream);
        writer.Write(rng.Below(4) == 0 ? 2 : 0);               // queried state: primitive topology, or nothing
        writer.Write(program.Compute);
        writer.Write(Magic(program.Compute ? "COMS" : "GFXS"));
        writer.Write(8);                                         // the first eight bytes of the state; the rest stays zero
        if (program.Compute)
        {
            writer.Write(rng.Between(1, 16));
            writer.Write(rng.Between(1, 16));
        }
        else
        {
            writer.Write(rng.Below(2));
            writer.Write(rng.Below(6));
        }
        byte use = (byte)(program.Compute ? rng.Below(2) : rng.Below(32));
        writer.Write(use);
        for (int bit = 0; bit < 5; bit++) if ((use >> bit & 1) != 0) writer.Write((uint)rng.Next());
        bool pipeline = !program.Compute && rng.Below(3) == 0;
        writer.Write(pipeline);
        if (pipeline)
        {
            writer.Write(Magic("PGPS"));
            writer.Write(0);
        }
        int textures = rng.Below(3);
        writer.Write((ushort)textures);
        for (int texture = 0; texture < textures; texture++)
        {
            writer.Write(Magic("TEXK"));
            writer.Write(8);
            writer.Write(texture);
            writer.Write(rng.Below(4096));
            writer.Write(Magic("TEXS"));
            writer.Write(0);
        }
        writer.Flush();
        return stream.ToArray();
    }

    private static byte[] Information(ProgramSpec program)
    {
        Rng rng = new(program.Seed ^ 0x5555);
        using MemoryStream stream = new();
        using BinaryWriter writer = new(stream);
        int stages = program.Compute ? 1 : 6;

        for (int stage = 0; stage < stages; stage++)
        {
            if (program.Guest[stage] < 0 || (stage == 0 && stages != 1))
            {
                continue;
            }

            int constantBuffers = rng.Below(3), storageBuffers = rng.Below(2);
            writer.Write(Magic("SHDI"));
            writer.Write(9);
            writer.Write((ushort)constantBuffers);
            writer.Write((ushort)storageBuffers);
            writer.Write((ushort)0);
            writer.Write((ushort)0);
            writer.Write((byte)(program.Compute ? ShaderStage.Compute : (ShaderStage)stage));

            for (int buffer = 0; buffer < constantBuffers + storageBuffers; buffer++)
            {
                writer.Write(Magic("BUFD"));
                writer.Write(8);
                writer.Write(buffer < constantBuffers ? 0 : 1);
                writer.Write(1 + buffer);
            }
        }

        writer.Flush();
        return stream.ToArray();
    }

    public static void Write(string directory, CacheSet set, uint codeGenVersion)
    {
        Directory.CreateDirectory(directory);

        using (FileStream toc = File.Create(Path.Combine(directory, "guest.toc")))
        using (FileStream data = File.Create(Path.Combine(directory, "guest.data")))
        using (BinaryWriter writer = new(toc))
        {
            writer.Write(Magic("TOCG"));
            writer.Write((1u << 16) | 1);
            writer.Write(0u);
            writer.Write((uint)set.Codes.Count);
            writer.Write(0ul);
            writer.Write(0ul);

            foreach (GuestCode code in set.Codes)
            {
                writer.Flush();
                code.TocEntry = toc.Position;
                code.DataOffset = data.Position;
                data.Write(code.Cb1);
                code.CompressedOffset = data.Position;
                Compressed(data, code.Code);
                code.CompressedLength = data.Position - code.CompressedOffset;
                writer.Write((uint)code.DataOffset);
                writer.Write((uint)code.Code.Length);
                writer.Write((uint)code.Cb1.Length);
                // DiskCacheGuestStorage.CalcHash: its rebuild finds a code again by this hash.
                writer.Write((uint)Hash128.ComputeHash(code.Cb1).Low * 23 ^ (uint)Hash128.ComputeHash(code.Code).Low);
            }
        }

        using FileStream sharedToc = File.Create(Path.Combine(directory, "shared.toc"));
        using FileStream sharedData = File.Create(Path.Combine(directory, "shared.data"));
        using FileStream hostToc = File.Create(Path.Combine(directory, "vulkan_apple.toc"));
        using FileStream hostData = File.Create(Path.Combine(directory, "vulkan_apple.data"));
        using BinaryWriter sharedWriter = new(sharedToc);
        using BinaryWriter hostWriter = new(hostToc);

        foreach ((BinaryWriter writer, string magic, uint version) in new[] { (sharedWriter, "TOCS", codeGenVersion), (hostWriter, "TOCH", 0u) })
        {
            writer.Write(Magic(magic));
            writer.Write(FormatVersion);
            writer.Write(version);
            writer.Write(0u);
            writer.Write(Timestamp);
            writer.Write(0ul);
        }

        set.HostCompressedBytes = 0;

        foreach (ProgramSpec program in set.Programs)
        {
            using MemoryStream entry = new();
            using (BinaryWriter writer = new(entry, Encoding.UTF8, true))
            {
                uint mask = 0;
                if (!program.Compute) for (int stage = 0; stage < 6; stage++) if (program.Guest[stage] >= 0) mask |= 1u << stage;
                writer.Write(program.StageMask ?? mask);
                int stages = program.Compute ? 1 : 6;
                for (int stage = 0; stage < stages; stage++)
                {
                    if (program.Guest[stage] >= 0)
                    {
                        writer.Write(program.GuestIndex is { } other && other.Stage == stage ? other.Index : program.Guest[stage]);
                    }
                }
                writer.Write(Specialization(program));
            }

            program.SharedOffset = sharedData.Position;
            sharedWriter.Write((ulong)sharedData.Position);
            Compressed(sharedData, entry.ToArray());
            program.SharedLength = sharedData.Position - program.SharedOffset;

            program.HostOffset = hostData.Position;
            Compressed(hostData, program.HostCode);
            program.HostCompressed = hostData.Position - program.HostOffset;
            program.InfoOffset = hostData.Position;
            Compressed(hostData, Information(program));
            program.InfoLength = hostData.Position - program.InfoOffset;
            hostWriter.Write((ulong)program.HostOffset);
            hostWriter.Write((uint)program.HostCode.Length);
            hostWriter.Write((uint)program.HostCompressed);
            set.HostCompressedBytes += program.HostCompressed;
        }
    }
}

static class Files
{
    public static void Copy(string from, string to)
    {
        Directory.CreateDirectory(to);
        foreach (string file in Directory.GetFiles(from)) File.Copy(file, Path.Combine(to, Path.GetFileName(file)), true);
    }

    public static void Append(string path, int count)
    {
        using FileStream stream = new(path, FileMode.Append);
        stream.Write(new byte[count]);
    }

    public static void Truncate(string path, long length)
    {
        using FileStream stream = new(path, FileMode.Open);
        stream.SetLength(length);
    }

    public static void Alter(string path, long offset, int count)
    {
        using FileStream stream = new(path, FileMode.Open);
        byte[] bytes = new byte[count];
        stream.Seek(offset, SeekOrigin.Begin);
        stream.ReadExactly(bytes);
        for (int i = 0; i < count; i++) bytes[i] ^= 0xA5;
        stream.Seek(offset, SeekOrigin.Begin);
        stream.Write(bytes);
    }

    public static void Put(string path, long offset, byte[] bytes)
    {
        using FileStream stream = new(path, FileMode.Open);
        stream.Seek(offset, SeekOrigin.Begin);
        stream.Write(bytes);
    }

    // Each file's size and SHA-256. The tables of contents carry the second they were created at (bytes 16 to 23):
    // left out, as a rebuild writes the current time there.
    public static SortedDictionary<string, string> Digest(string directory)
    {
        SortedDictionary<string, string> digests = new();
        if (!Directory.Exists(directory)) return digests;

        foreach (string file in Directory.GetFiles(directory))
        {
            byte[] bytes = File.ReadAllBytes(file);
            string name = Path.GetFileName(file);
            if ((name == "shared.toc" || name == "vulkan_apple.toc") && bytes.Length >= 24) Array.Clear(bytes, 16, 8);
            digests[name] = bytes.Length + ":" + Convert.ToHexString(SHA256.HashData(bytes))[..24];
        }

        return digests;
    }
}

static class Program
{
    private static readonly LogCapture Log = new();
    private static readonly List<(Thread Thread, uint Class)> RaisedThreads = new();
    private static string _journal;
    private static long _journalOffset;

    private static string Hex(byte[] bytes) => Convert.ToHexString(bytes)[..24];

    private static string Ordered(IEnumerable<string> items)
    {
        using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (string item in items) hash.AppendData(Encoding.UTF8.GetBytes(item + "\n"));
        return Hex(hash.GetHashAndReset());
    }

    private static string Sorted(IEnumerable<string> items) => Ordered(items.OrderBy(item => item, StringComparer.Ordinal));

    // Public fields and properties of a value, in declaration order: what the engine made of the bytes it read.
    private static void Describe(StringBuilder text, object value, int depth = 0)
    {
        if (value == null)
        {
            text.Append("null");
        }
        else if (value is string || value.GetType().IsPrimitive || value.GetType().IsEnum)
        {
            text.Append(Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture));
        }
        else if (value is IEnumerable sequence)
        {
            text.Append('[');
            foreach (object item in sequence) { Describe(text, item, depth + 1); text.Append(','); }
            text.Append(']');
        }
        else if (depth < 4)
        {
            text.Append('{');
            foreach (FieldInfo field in value.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public))
            {
                text.Append(field.Name).Append('=');
                Describe(text, field.GetValue(value), depth + 1);
                text.Append(';');
            }
            foreach (PropertyInfo property in value.GetType().GetProperties(BindingFlags.Instance | BindingFlags.Public))
            {
                if (property.GetIndexParameters().Length != 0) continue;
                text.Append(property.Name).Append('=');
                Describe(text, property.GetValue(value), depth + 1);
                text.Append(';');
            }
            text.Append('}');
        }
    }

    // The programs a table holds, in its order: which created program, each stage's guest code and constant buffer
    // data (bytes, and which array: stages sharing a code share the array), its information, and the specialization
    // state written back by the engine's own serializer.
    private static List<string> Table(object table, Dictionary<byte[], int> arrays)
    {
        List<string> lines = new();
        MethodInfo write = Engine.Specialization.GetMethod("Write", Engine.All);

        foreach (object program in (IEnumerable)table.GetType().GetMethod("GetPrograms", Engine.All).Invoke(table, null))
        {
            StringBuilder text = new();
            text.Append(((FakeProgram)Engine.Program.GetProperty("HostProgram").GetValue(program)).Index).Append('|');

            foreach (object stage in (Array)Engine.Program.GetProperty("Shaders").GetValue(program))
            {
                if (stage == null)
                {
                    text.Append("-|");
                    continue;
                }

                byte[] code = (byte[])Engine.Stage.GetProperty("Code").GetValue(stage);
                byte[] cb1 = (byte[])Engine.Stage.GetProperty("Cb1Data").GetValue(stage);
                if (!arrays.TryGetValue(code, out int id)) arrays.Add(code, id = arrays.Count);
                text.Append('#').Append(id).Append(':').Append(Hex(SHA256.HashData(code))).Append(':').Append(Hex(SHA256.HashData(cb1))).Append(':');
                Describe(text, Engine.Stage.GetProperty("Info").GetValue(stage));
                text.Append('|');
            }

            using MemoryStream stream = new();
            object[] serializer = [Engine.New(Engine.Serializer, stream)];
            write.Invoke(Engine.Program.GetProperty("SpecializationState").GetValue(program), serializer);
            text.Append(Hex(SHA256.HashData(stream.ToArray())));
            lines.Add(text.ToString());
        }

        return lines;
    }

    private static List<string> JournalLines()
    {
        List<string> lines = new();
        using FileStream stream = new(_journal, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        stream.Seek(_journalOffset, SeekOrigin.Begin);
        using StreamReader reader = new(stream);
        string line;

        while ((line = reader.ReadLine()) != null)
        {
            int brace = line.IndexOf('{');
            if (brace < 0) continue;
            using JsonDocument record = JsonDocument.Parse(line[brace..]);
            if (record.RootElement.GetProperty("stage").GetString() == "shaderCache")
            {
                lines.Add(record.RootElement.GetProperty("status").GetString() + " " + record.RootElement.GetProperty("diagnostic").GetString());
            }
        }

        _journalOffset = stream.Length;
        return lines;
    }

    private static Dictionary<string, object> Load(string directory, Probe probe)
    {
        FakeRenderer renderer = new(probe);
        GpuContext context = new(renderer, null);
        context.SetGpuThread();
        object graphics = Engine.New(Engine.GraphicsTable);
        object compute = Engine.New(Engine.ComputeTable);
        object storage = Engine.New(Engine.Storage, directory);

        if (probe.Threads >= 0)
        {
            Engine.Threads.SetValue(storage, probe.Threads);
        }

        probe.Cancellation = new CancellationTokenSource();
        if (probe.CancelBefore) probe.Cancellation.Cancel();

        List<string> callbacks = new();
        Action<ShaderCacheState, int, int> callback = (state, current, total) =>
        {
            lock (callbacks) callbacks.Add(state + " " + current + " " + total);
        };

        object loader = Engine.New(Engine.Loader, context, graphics, compute, storage, callback, probe.Cancellation.Token);

        lock (Log.Lines) Log.Lines.Clear();
        lock (RaisedThreads) RaisedThreads.Clear();
        JournalLines();
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        long memoryBefore = GC.GetTotalMemory(true);
        long allocatedBefore = GC.GetTotalAllocatedBytes(true);
        string exception = null;
        long start = Stopwatch.GetTimestamp();

        try
        {
            Engine.Loader.GetMethod("LoadShaders", Engine.All).Invoke(loader, null);
        }
        catch (TargetInvocationException error)
        {
            exception = error.InnerException.GetType().FullName + ": " + error.InnerException.Message;
        }

        long end = Stopwatch.GetTimestamp();
        (Thread Thread, uint Class)[] raised;
        lock (RaisedThreads) raised = RaisedThreads.ToArray();
        int alive = raised.Count(thread => thread.Thread.IsAlive); // at the very return of LoadShaders
        long allocated = GC.GetTotalAllocatedBytes(true) - allocatedBefore;

        Dictionary<byte[], int> arrays = new(ReferenceEqualityComparer.Instance);
        List<string> graphicsPrograms = Table(graphics, arrays);
        List<string> computePrograms = Table(compute, arrays);
        List<string> log;
        lock (Log.Lines) log = Log.Lines.Select(line => line.Replace(directory, "<cache>")).ToList();
        List<string> calls = probe.CallDigests.Select(Convert.ToHexString).ToList();
        List<string> journal = JournalLines();
        string read = journal.FirstOrDefault(line => line.StartsWith("read "));

        return new Dictionary<string, object>
        {
            ["exception"] = exception,
            ["programsCreated"] = probe.Programs,
            ["sourceBytes"] = probe.SourceBytes,
            ["createOrdered"] = Ordered(calls),
            ["createSorted"] = Sorted(calls),
            ["callbacks"] = callbacks.Count,
            ["callbacksOrdered"] = Ordered(callbacks),
            ["callbackKinds"] = string.Join(",", callbacks.GroupBy(line => line.Split(' ')[0]).OrderBy(group => group.Key).Select(group => group.Key + "=" + group.Count())),
            ["lastCallback"] = callbacks.LastOrDefault(),
            ["logOrdered"] = Ordered(log),
            ["logSorted"] = Sorted(log),
            ["log"] = log.Take(12).ToList(),
            ["logLines"] = log.Count,
            ["errorCount"] = (int)Engine.Loader.GetProperty("ErrorCount", Engine.All).GetValue(loader),
            ["graphicsPrograms"] = graphicsPrograms.Count,
            ["computePrograms"] = computePrograms.Count,
            ["tables"] = Ordered(graphicsPrograms.Concat(computePrograms)),
            ["distinctCodeArrays"] = arrays.Count,
            ["files"] = Files.Digest(directory),
            ["milliseconds"] = Math.Round(Stopwatch.GetElapsedTime(start, end).TotalMilliseconds, 1),
            ["allocatedBytes"] = allocated,
            ["raisedThreads"] = raised.Length,
            ["raisedThreadNames"] = string.Join(",", raised.Select(thread => thread.Thread.Name).OrderBy(name => name, StringComparer.Ordinal)),
            ["raisedClasses"] = string.Join(",", raised.Select(thread => thread.Class).Distinct()),
            ["raisedThreadsAliveAtReturn"] = alive,
            ["journalRead"] = read,
            ["journalReadLines"] = journal.Count(line => line.StartsWith("read ")),
            ["journalCodeTableLines"] = journal.Count(line => line.StartsWith("codeTable ")),
            ["memoryAtProbe"] = probe.MemoryBytes < 0 ? -1 : probe.MemoryBytes - memoryBefore,
            ["returnAfterCancelMilliseconds"] = probe.CancelTimestamp == 0 ? -1 : Math.Round(Stopwatch.GetElapsedTime(probe.CancelTimestamp, end).TotalMilliseconds, 1),
        };
    }

    // What a load must give again when it is repeated (and what the gate compares between control and candidate).
    private static string Signature(Dictionary<string, object> result, bool unordered)
    {
        string[] keys = ["exception", "programsCreated", "sourceBytes", "createOrdered", "callbacks", "callbackKinds", "lastCallback", "logSorted", "logLines",
            "graphicsPrograms", "computePrograms", "tables", "distinctCodeArrays", "raisedThreads", "raisedThreadsAliveAtReturn"];
        string[] ordered = ["callbacksOrdered", "logOrdered", "errorCount"];
        return string.Join("|", (unordered ? keys : keys.Concat(ordered)).Select(key => Convert.ToString(result[key]))) + "|" +
            string.Join(",", ((SortedDictionary<string, string>)result["files"]).Select(pair => pair.Key + "=" + pair.Value));
    }

    private static void Setup(string work)
    {
        Directory.CreateDirectory(work);
        _journal = Path.Combine(work, "MeloNX-core.log");
        File.WriteAllBytes(_journal, []);
        EmbeddedLaunchDiagnostics.ConfigureJournal(_journal);
        Logger.RemoveTarget("console");
        Logger.AddTarget(Log);

        // The launch preflight sets the scrub before the cache loads; the code generation of the cache follows it.
        Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub.Enabled = true;

        // Ryujinx.Common.HostThreadClass asks the scheduler class only on Apple platforms; its two hooks exist for
        // fixtures. Here they record which thread asked, for which class.
        Type threadClass = typeof(HostThreadClass);
        threadClass.GetField("ApplePlatform", Engine.All).SetValue(null, (Func<bool>)(() => true));
        threadClass.GetField("SetClass", Engine.All).SetValue(null, (Func<uint, int, int>)((qualityClass, relative) =>
        {
            lock (RaisedThreads) RaisedThreads.Add((Thread.CurrentThread, qualityClass));
            return 0;
        }));
    }

    private static string[] Settings() => Engine.HasReadAhead ? ["default", "0", "1", "2", "3"] : ["control"];

    private static int Threads(string setting) => setting is "control" or "default" ? -1 : int.Parse(setting);

    private sealed class Scenario
    {
        public string Name, Set;
        public bool InPlace;                       // a load that must leave the files as they are runs on the set itself
        public bool Unordered;                     // guest translations: their order is not the load's
        public Action<string> Alter;
        public Action<Probe> Configure;
        public string Keep;                        // the first setting's directory is kept under this name (a rebuilt cache)
        public int Repeat = 1;                     // loads per setting; each must give what the first gave
    }

    private static void Run(string work, string real)
    {
        Setup(work);
        uint codeGen = Engine.CodeGenVersion;
        Dictionary<string, object> report = new();
        Dictionary<string, string> sets = new();
        Dictionary<string, object> setFacts = new();

        CacheSet Make(string name, CacheSet set, Action<CacheSet> defect = null)
        {
            defect?.Invoke(set);
            string directory = Path.Combine(work, "sets", name);
            CacheWriter.Write(directory, set, codeGen);
            sets[name] = directory;
            setFacts[name] = new Dictionary<string, object>
            {
                ["programs"] = set.Programs.Count,
                ["guestCodes"] = set.DistinctCodes,
                ["guestBytes"] = set.GuestBytes,
                ["hostBytes"] = set.HostBytes,
                ["hostCompressedBytes"] = set.HostCompressedBytes,
                ["largestHostCode"] = set.Programs.Count == 0 ? 0 : set.Programs.Max(program => program.HostCode.Length),
                ["files"] = Files.Digest(directory),
            };
            return set;
        }

        // The data sets. Sizes of the small ones exercise the paths; the launch-shaped one has the host code sizes of
        // the real host cache measured (1,877 programs, median 125 KB, at most 674 KB, Brotli to about a third).
        CacheSet Hand() => CacheWriter.Build("hand", 120, 2_000, 40_000, 64, 4_096, 11, [30, 31, 90], 2_300_000);
        CacheSet Tiny() => CacheWriter.Build("tiny", 40, 1_000, 8_000, 8, 40, 12);
        const int At = 70, TinyAt = 20;
        CacheSet hand = Make("hand", Hand());
        Make("hand-bad-mask", Hand(), set => set.Programs[At].StageMask = 0x40 | 0x22);
        Make("hand-guest-past-table", Hand(), set => set.Programs[At].GuestIndex = (5, set.Codes.Count + 5));
        Make("hand-guest-negative", Hand(), set => set.Programs[At].GuestIndex = (5, -1));
        CacheSet tiny = Make("tiny", Tiny());
        Make("tiny-malformed-host", Tiny(), set => set.Programs[TinyAt].HostCode = [99, 0, 0, 0, 1, 2, 3, 4]);
        Make("none", CacheWriter.Build("none", 0, 1, 1, 8, 8, 13));
        Make("few15", CacheWriter.Build("few15", 15, 2_000, 40_000, 64, 4_096, 14));
        Make("few16", CacheWriter.Build("few16", 16, 2_000, 40_000, 64, 4_096, 15));
        Make("window", CacheWriter.Build("window", 64, 1 << 20, 1 << 20, 64, 1_024, 16));
        Make("above-limit", CacheWriter.Build("above-limit", 24, 2_200_000, 2_200_000, 64, 1_024, 18));
        Make("launch", CacheWriter.Build("launch", 1000, 30_000, 230_000, 512, 16_384, 17, [100, 500, 900], 674_000));
        Directory.CreateDirectory(Path.Combine(work, "sets", "absent"));
        sets["absent"] = Path.Combine(work, "sets", "absent");

        ProgramSpec program = hand.Programs[At];
        GuestCode fragment = hand.Codes[program.Guest[5]];
        string Shared(string directory, string file) => Path.Combine(directory, file);

        List<Scenario> scenarios =
        [
            new() { Name = "hand-written cache", Set = "hand", InPlace = true, Repeat = 3 },
            new() { Name = "truncated table of contents, rebuilt", Set = "hand", Alter = d => Files.Append(Shared(d, "shared.toc"), 3), Keep = "hand-rebuilt", Repeat = 3 },
            new() { Name = "cache rebuilt by the engine", Set = "hand-rebuilt", InPlace = true, Repeat = 3 },
            new() { Name = "launch-shaped cache", Set = "launch", InPlace = true },
            new() { Name = "launch-shaped cache, truncated table of contents, rebuilt", Set = "launch", Alter = d => Files.Append(Shared(d, "shared.toc"), 5), Keep = "launch-rebuilt" },
            new() { Name = "launch-shaped cache rebuilt by the engine", Set = "launch-rebuilt", InPlace = true },
            new() { Name = "no cache file", Set = "absent", InPlace = true, Repeat = 3 },
            new() { Name = "no program", Set = "none", InPlace = true, Repeat = 3 },
            new() { Name = "15 programs", Set = "few15", InPlace = true, Repeat = 3 },
            new() { Name = "16 programs", Set = "few16", InPlace = true, Repeat = 3 },
            new() { Name = "shared entry past the data file at program 70", Set = "hand", Alter = d => Files.Put(Shared(d, "shared.toc"), 32 + 8 * At, BitConverter.GetBytes(0x7fff_ffff_ffffUL)), Repeat = 3 },
            new() { Name = "shared data truncated inside program 70", Set = "hand", Alter = d => Files.Truncate(Shared(d, "shared.data"), program.SharedOffset + program.SharedLength / 2), Repeat = 3 },
            new() { Name = "shared data altered inside program 70", Set = "hand", Alter = d => Files.Alter(Shared(d, "shared.data"), program.SharedOffset + program.SharedLength / 2, 4), Repeat = 3 },
            new() { Name = "shared data altered at the start of program 70", Set = "hand", Alter = d => Files.Alter(Shared(d, "shared.data"), program.SharedOffset + 1, 3), Repeat = 3 },
            new() { Name = "unknown compression of program 70", Set = "hand", Alter = d => Files.Put(Shared(d, "shared.data"), program.SharedOffset, [9]), Repeat = 3 },
            new() { Name = "invalid stage mask at program 70", Set = "hand-bad-mask", Repeat = 3 },
            new() { Name = "guest index past the guest table at program 70", Set = "hand-guest-past-table", Repeat = 40 },
            new() { Name = "negative guest index at program 70", Set = "hand-guest-negative", Repeat = 3 },
            new() { Name = "guest table truncated before the code of program 70", Set = "hand", Alter = d => Files.Truncate(Shared(d, "guest.toc"), fragment.TocEntry), Repeat = 3 },
            new() { Name = "guest code past the guest data at program 70", Set = "hand", Alter = d => Files.Put(Shared(d, "guest.toc"), fragment.TocEntry, BitConverter.GetBytes(0xffff_fff0u)), Repeat = 3 },
            new() { Name = "guest data altered in the code of program 70", Set = "hand", Alter = d => Files.Alter(Shared(d, "guest.data"), fragment.CompressedOffset + fragment.CompressedLength / 2, 4), Repeat = 3 },
            new() { Name = "guest data altered at the start of the code of program 70", Set = "hand", Alter = d => Files.Alter(Shared(d, "guest.data"), fragment.CompressedOffset + 1, 3), Repeat = 3 },
            new() { Name = "host entry past the host data at program 70", Set = "hand", Alter = d => Files.Put(Shared(d, "vulkan_apple.toc"), 32 + 16 * At, BitConverter.GetBytes(0x7fff_ffff_ffffUL)), Repeat = 3 },
            new() { Name = "host data altered inside program 70", Set = "hand", Alter = d => Files.Alter(Shared(d, "vulkan_apple.data"), program.HostOffset + program.HostCompressed / 2, 4), Repeat = 3 },
            new() { Name = "host data truncated inside program 70", Set = "hand", Alter = d => Files.Truncate(Shared(d, "vulkan_apple.data"), program.HostOffset + program.HostCompressed / 2), Repeat = 3 },
            new() { Name = "host information altered at program 70", Set = "hand", Alter = d => Files.Alter(Shared(d, "vulkan_apple.data"), program.InfoOffset + 1, 3), Repeat = 3 },
            new() { Name = "host table header truncated", Set = "hand", Alter = d => Files.Truncate(Shared(d, "vulkan_apple.toc"), 10), Repeat = 40 },
            new() { Name = "host data file empty", Set = "hand", Alter = d => Files.Truncate(Shared(d, "vulkan_apple.data"), 0), Repeat = 3 },
            new() { Name = "wrong magic in the shared table", Set = "hand", Alter = d => Files.Put(Shared(d, "shared.toc"), 0, [1, 2, 3, 4]), Repeat = 3 },
            new() { Name = "another format version", Set = "hand", Alter = d => Files.Put(Shared(d, "shared.toc"), 4, BitConverter.GetBytes(CacheWriter.FormatVersion + 1)), Repeat = 3 },
            new() { Name = "host table ends at program 25", Set = "tiny", Unordered = true, Alter = d => Files.Truncate(Shared(d, "vulkan_apple.toc"), 32 + 16 * 25), Repeat = 3 },
            new() { Name = "no host file", Set = "tiny", Unordered = true, Alter = d => { File.Delete(Shared(d, "vulkan_apple.toc")); File.Delete(Shared(d, "vulkan_apple.data")); }, Repeat = 3 },
            new() { Name = "host files older than the shared cache", Set = "tiny", Unordered = true, Alter = d => Files.Put(Shared(d, "vulkan_apple.toc"), 16, BitConverter.GetBytes(CacheWriter.Timestamp - 1)), Repeat = 40 },
            new() { Name = "another code generation", Set = "tiny", Unordered = true, Alter = d => Files.Put(Shared(d, "shared.toc"), 8, BitConverter.GetBytes(codeGen + 1)), Repeat = 3 },
            new() { Name = "malformed host code at program 20", Set = "tiny-malformed-host", Unordered = true, Repeat = 3 },
            new() { Name = "host program 20 fails to link", Set = "tiny", Unordered = true, Configure = probe => probe.FailLinkAt = TinyAt, Repeat = 3 },
            new() { Name = "cancelled before the load", Set = "hand", InPlace = true, Configure = probe => probe.CancelBefore = true, Repeat = 3 },
            new() { Name = "cancelled at program 50", Set = "hand", InPlace = true, Configure = probe => probe.CancelAtCreate = 50, Repeat = 3 },
            new() { Name = "launch-shaped cache cancelled at program 300", Set = "launch-rebuilt", InPlace = true, Configure = probe => probe.CancelAtCreate = 300 },
            new() { Name = "64 programs of 1 MiB, GPU thread held at program 24", Set = "window", InPlace = true, Configure = probe => probe.MemoryAt = 24 },
            new() { Name = "24 programs above the limit, GPU thread held at program 10", Set = "above-limit", InPlace = true, Configure = probe => probe.MemoryAt = 10 },
        ];

        if (real != null)
        {
            sets["real"] = real;
            scenarios.Add(new() { Name = "real cache", Set = "real", InPlace = true });
            scenarios.Add(new() { Name = "real cache cancelled at program 500", Set = "real", InPlace = true, Configure = probe => probe.CancelAtCreate = 500 });
            scenarios.Add(new() { Name = "real cache, truncated table of contents, rebuilt", Set = "real", Alter = d => Files.Append(Shared(d, "shared.toc"), 3) });
        }

        List<object> results = new();

        foreach (Scenario scenario in scenarios)
        {
            Dictionary<string, object> perSetting = new();

            foreach (string setting in Settings())
            {
                string source = sets[scenario.Set];
                string directory = source;
                SortedDictionary<string, string> before = Files.Digest(source);

                if (!scenario.InPlace)
                {
                    directory = Path.Combine(work, "run");
                    if (Directory.Exists(directory)) Directory.Delete(directory, true);
                    Files.Copy(source, directory);
                    scenario.Alter?.Invoke(directory);
                }

                Probe probe = new() { Threads = Threads(setting) };
                scenario.Configure?.Invoke(probe);
                Dictionary<string, object> result = Load(directory, probe);
                result["filesUnchanged"] = scenario.InPlace
                    ? before.SequenceEqual(Files.Digest(source))
                    : (object)null;
                perSetting[setting] = result;

                // The threads meet differently at each load: the same load again, from the same files, must give the same.
                int same = 1;

                for (int repeat = 1; repeat < scenario.Repeat; repeat++)
                {
                    if (!scenario.InPlace)
                    {
                        Directory.Delete(directory, true);
                        Files.Copy(source, directory);
                        scenario.Alter?.Invoke(directory);
                    }

                    Probe again = new() { Threads = Threads(setting) };
                    scenario.Configure?.Invoke(again);
                    if (Signature(Load(directory, again), scenario.Unordered) == Signature(result, scenario.Unordered)) same++;
                }

                result["loads"] = scenario.Repeat;
                result["loadsWithTheSameResult"] = same;

                if (!scenario.InPlace)
                {
                    if (scenario.Keep != null && !sets.ContainsKey(scenario.Keep))
                    {
                        string kept = Path.Combine(work, "sets", scenario.Keep);
                        Directory.Move(directory, kept);
                        sets[scenario.Keep] = kept;
                    }
                    else
                    {
                        Directory.Delete(directory, true);
                    }
                }
            }

            results.Add(new Dictionary<string, object>
            {
                ["name"] = scenario.Name,
                ["set"] = scenario.Set,
                ["unordered"] = scenario.Unordered,
                ["inPlace"] = scenario.InPlace,
                ["settings"] = perSetting,
            });
        }

        report["hasReadAhead"] = Engine.HasReadAhead;
        report["processors"] = Environment.ProcessorCount;
        report["codeGenVersion"] = codeGen;
        report["sets"] = setFacts;
        report["setDirectories"] = sets;
        report["scenarios"] = results;

        if (Engine.HasReadAhead)
        {
            MethodInfo count = Engine.Storage.GetMethod("ReadAheadThreadCount", Engine.All);
            report["threadsForProcessors"] = new[] { 1, 2, 3, 4, 6, 8, 12, 16, 64 }.ToDictionary(processors => processors.ToString(), processors => (int)count.Invoke(null, [processors]));
            report["window"] = (int)Engine.ReadAhead.GetField("Window", Engine.All).GetValue(null);
            report["maximumHostCodeSize"] = (uint)Engine.ReadAhead.GetField("MaximumHostCodeSize", Engine.All).GetValue(null);
            report["defaultThreads"] = (int)Engine.Threads.GetValue(Engine.New(Engine.Storage, sets["absent"]));
        }

        Console.WriteLine(JsonSerializer.Serialize(report));
    }

    private static void Perf(string directory, int loads, string[] settings)
    {
        string work = Path.Combine(Path.GetTempPath(), "melonx-shader-cache-perf-" + Environment.ProcessId);
        Setup(work);
        Dictionary<string, object> report = new();

        foreach (string setting in settings)
        {
            List<double> times = new();
            Dictionary<string, object> best = null;

            for (int load = 0; load < loads + 1; load++)
            {
                Dictionary<string, object> result = Load(directory, new Probe { Threads = Threads(setting), Digest = false });
                if (result["exception"] != null) throw new Exception((string)result["exception"]);
                if (load == 0) continue; // the first load of a process compiles the engine's methods
                times.Add((double)result["milliseconds"]);
                if (best == null || (double)result["milliseconds"] < (double)best["milliseconds"]) best = result;
            }

            times.Sort();
            report[setting] = new Dictionary<string, object>
            {
                ["best"] = times[0],
                ["median"] = times[times.Count / 2],
                ["programsCreated"] = best["programsCreated"],
                ["sourceBytes"] = best["sourceBytes"],
                ["allocatedBytes"] = best["allocatedBytes"],
                ["journalRead"] = best["journalRead"],
            };
        }

        Directory.Delete(work, true);
        Console.WriteLine(JsonSerializer.Serialize(report));
    }

    public static int Main(string[] arguments)
    {
        try
        {
            if (arguments[0] == "run")
            {
                Run(Path.GetFullPath(arguments[1]), arguments.Length > 2 ? Path.GetFullPath(arguments[2]) : null);
            }
            else
            {
                Perf(Path.GetFullPath(arguments[1]), int.Parse(arguments[2]), arguments[3].Split(','));
            }

            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            return 1;
        }
    }
}
