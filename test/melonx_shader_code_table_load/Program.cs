// Driver of melonx_shader_code_table_load_test.py. For each data set it replays the registration of a disk shader
// cache load through the loader's real lines (Double.cs), then asks the real tables, with the real TryFind and a guest
// memory double, for every registered code and for probes around them, dumps the complete table state by reflection,
// adds programs as play does (TryFind first, then Add with the cached arrays) and asks again. The same program is
// compiled with the control's and with the candidate's files; the gate compares the two reports.
//
// Fixture.dll <control|candidate> <repetitions> [directory of a real cache: guest.toc, guest.data, shared.toc, shared.data]
using System;
using System.Buffers.Binary;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using Ryujinx.Common;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Gpu.Shader.DiskCache;
using Ryujinx.Graphics.Gpu.Shader.HashTable;
using Ryujinx.Graphics.Shader;

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
        return _state * 0x2545F4914F6CDD1DUL;
    }

    public int Int(int bound) => (int)(Next() % (ulong)bound);
    public int Range(int low, int high) => low + Int(high - low + 1);
    public double Unit() => (Next() >> 11) * (1.0 / (1UL << 53));
    public double Normal() => Math.Sqrt(-2.0 * Math.Log(1.0 - Unit())) * Math.Cos(2.0 * Math.PI * Unit());

    public void Fill(Span<byte> data)
    {
        int index = 0;
        for (; index + 8 <= data.Length; index += 8)
        {
            BinaryPrimitives.WriteUInt64LittleEndian(data[index..], Next());
        }

        for (; index < data.Length; index++)
        {
            data[index] = (byte)Next();
        }
    }

    public void Shuffle<T>(IList<T> list)
    {
        for (int index = list.Count - 1; index > 0; index--)
        {
            int other = Int(index + 1);
            (list[index], list[other]) = (list[other], list[index]);
        }
    }
}

sealed class ProgramSpec
{
    public bool Compute;
    public int[] Stages; // code number per stage (6 for graphics, 1 for compute); -1: stage absent
}

sealed class Shape
{
    public int Graphics, Compute, Play;
    public int VertexCodes, FragmentCodes, ComputeCodes, RareCodes;
    public double RareShare;
    public int MinSize, MaxSize, SizeStep;
    public double MedianSize, Sigma;
    public int Families;
    public double Prefix, Duplicate, EqualSize;
    public double ShareNone = 0.3, ShareLong = 0.3; // codes that start like no other, and like another for half their size or more
    public int HeaderMin = 80, HeaderMax = 480;      // the others start like their family for this many bytes
    public bool Sharing, ComputePrefix;
    public string Order = "cache";
}

sealed class DataSet
{
    public const int ComputeSlot = 6;

    public string Name, Kind;
    public ulong Seed;
    public readonly List<byte[]> Codes = new();
    public readonly List<int>[] SlotCodes = Enumerable.Range(0, 7).Select(_ => new List<int>()).ToArray();
    public readonly List<ProgramSpec> Programs = new();
    public readonly List<ProgramSpec> Play = new();
    public bool ContentDigest = true;
    public int CodeBudget = int.MaxValue, ProgramBudget = int.MaxValue;

    private int AddCode(int slot, byte[] code)
    {
        Codes.Add(code);
        SlotCodes[slot].Add(Codes.Count - 1);
        return Codes.Count - 1;
    }

    private static int SampleSize(Rng rng, Shape shape)
    {
        double size = Math.Exp(Math.Log(shape.MedianSize) + shape.Sigma * rng.Normal());
        int clamped = (int)Math.Clamp(size, shape.MinSize, shape.MaxSize);
        return Math.Max(shape.MinSize, clamped - clamped % shape.SizeStep);
    }

    // A new code for a stage's pool: a truncation or an extension of an earlier code, the content of an earlier code in
    // another array, or new content of a sampled (or an earlier code's) size that starts like its family.
    // Compute codes of a load are never truncations of one another: the engine's compute Add throws on a code that an
    // earlier, longer one starts with (GetOrAdd returns the partial entry's null list), in the control and in the candidate
    // alike, and a load that throws has no state to compare. Play covers it, exception included.
    private int NewCode(Rng rng, Shape shape, int slot, byte[][] families, int forcedSize = 0)
    {
        List<int> pool = SlotCodes[slot];
        double kind = rng.Unit();

        if (pool.Count != 0 && forcedSize == 0 && kind < shape.Duplicate)
        {
            return AddCode(slot, (byte[])Codes[pool[rng.Int(pool.Count)]].Clone());
        }

        if (pool.Count != 0 && forcedSize == 0 && kind < shape.Duplicate + shape.Prefix && (slot != ComputeSlot || shape.ComputePrefix))
        {
            byte[] other = Codes[pool[rng.Int(pool.Count)]];

            if (other.Length > 1 && rng.Int(2) == 0)
            {
                return AddCode(slot, other[..rng.Range(1, other.Length - 1)]);
            }

            byte[] longer = new byte[Math.Min(shape.MaxSize + 64, other.Length + rng.Range(1, 400))];
            other.CopyTo(longer, 0);
            rng.Fill(longer.AsSpan(other.Length));
            return AddCode(slot, longer);
        }

        int size = forcedSize != 0 ? forcedSize : SampleSize(rng, shape);
        if (pool.Count != 0 && forcedSize == 0 && rng.Unit() < shape.EqualSize)
        {
            size = Codes[pool[rng.Int(pool.Count)]].Length;
        }

        byte[] code = new byte[size];
        rng.Fill(code);

        byte[] family = families[rng.Int(families.Length)];
        double share = rng.Unit();
        int shared = share < shape.ShareNone ? 0 : share < 1.0 - shape.ShareLong ? rng.Range(shape.HeaderMin, shape.HeaderMax) : (int)(size * (0.5 + 0.5 * rng.Unit()));
        shared = Math.Min(shared, Math.Min(size, family.Length));
        if (slot == ComputeSlot && !shape.ComputePrefix)
        {
            shared = Math.Max(0, Math.Min(shared, size - 12)); // its last bytes are its own: no compute code starts another
        }

        family.AsSpan(0, shared).CopyTo(code);
        return AddCode(slot, code);
    }

    public static DataSet Synthetic(string name, ulong seed, Shape shape)
    {
        DataSet set = new() { Name = name, Kind = "synthetic", Seed = seed };
        Rng rng = new(seed);
        byte[][][] families = new byte[7][][];

        for (int slot = 0; slot < 7; slot++)
        {
            families[slot] = new byte[shape.Families][];
            for (int index = 0; index < shape.Families; index++)
            {
                families[slot][index] = new byte[Math.Min(shape.MaxSize, (int)(shape.MedianSize * 6))];
                rng.Fill(families[slot][index]);
            }
        }

        int[] pools = { shape.RareCodes, shape.VertexCodes, shape.RareCodes, shape.RareCodes, shape.RareCodes, shape.FragmentCodes, shape.ComputeCodes };
        for (int slot = 0; slot < 7; slot++)
        {
            int count = shape.Sharing ? pools[slot] : slot == ComputeSlot ? shape.Compute : shape.Graphics;
            for (int index = 0; index < count; index++)
            {
                set.NewCode(rng, shape, slot, families[slot]);
            }
        }

        int[] next = new int[7];
        int Pick(int slot)
        {
            List<int> pool = set.SlotCodes[slot];
            if (!shape.Sharing)
            {
                return pool[next[slot]++ % pool.Count];
            }

            // Every code of a pool is used once; the other uses favour the first codes.
            if (next[slot] < pool.Count)
            {
                return pool[next[slot]++];
            }

            double u = rng.Unit();
            return pool[(int)(pool.Count * u * u)];
        }

        for (int index = 0; index < shape.Graphics; index++)
        {
            int[] stages = { -1, Pick(1), -1, -1, -1, Pick(5) };
            if (rng.Unit() < shape.RareShare)
            {
                stages[0] = Pick(0);
            }

            if (rng.Unit() < shape.RareShare)
            {
                stages[2] = Pick(2);
                stages[3] = Pick(3);
            }

            if (rng.Unit() < shape.RareShare)
            {
                stages[4] = Pick(4);
            }

            set.Programs.Add(new ProgramSpec { Stages = stages });
        }

        for (int index = 0; index < shape.Compute; index++)
        {
            set.Programs.Add(new ProgramSpec { Compute = true, Stages = new[] { Pick(ComputeSlot) } });
        }

        rng.Shuffle(set.Programs);
        int Largest(ProgramSpec spec) => spec.Stages.Where(code => code >= 0).Max(code => set.Codes[code].Length);
        if (shape.Order == "increasing")
        {
            List<ProgramSpec> sorted = set.Programs.OrderBy(Largest).ToList();
            set.Programs.Clear();
            set.Programs.AddRange(sorted);
        }
        else if (shape.Order == "decreasing")
        {
            List<ProgramSpec> sorted = set.Programs.OrderByDescending(Largest).ToList();
            set.Programs.Clear();
            set.Programs.AddRange(sorted);
        }

        set.AddPlay(rng, shape, families);
        return set;
    }

    // Programs made in play: stages already cached in new combinations, and new codes around the cached ones (a size
    // below every cached size, a cached size, truncations, extensions, the content of a cached code in another array).
    private void AddPlay(Rng rng, Shape shape, byte[][][] families)
    {
        Shape around = new()
        {
            MinSize = shape.MinSize, MaxSize = shape.MaxSize, SizeStep = shape.SizeStep, MedianSize = shape.MedianSize, Sigma = shape.Sigma,
            Prefix = 0.3, Duplicate = 0.1, EqualSize = 0.3, ComputePrefix = true,
        };

        int Stage(int slot)
        {
            List<int> pool = SlotCodes[slot];
            if (pool.Count == 0)
            {
                return -1;
            }

            double kind = rng.Unit();
            if (kind < 0.4)
            {
                return pool[rng.Int(pool.Count)];
            }

            int smallest = pool.Min(code => Codes[code].Length);
            if (kind < 0.5 && smallest > 1)
            {
                return NewCode(rng, around, slot, families[slot], rng.Range(1, smallest - 1));
            }

            return NewCode(rng, around, slot, families[slot]);
        }

        for (int index = 0; index < shape.Play; index++)
        {
            if (rng.Unit() < 0.2 && SlotCodes[ComputeSlot].Count != 0)
            {
                Play.Add(new ProgramSpec { Compute = true, Stages = new[] { Stage(ComputeSlot) } });
                continue;
            }

            int[] stages = { -1, Stage(1), -1, -1, -1, Stage(5) };
            if (rng.Unit() < 0.15)
            {
                stages[0] = Stage(0);
            }

            if (rng.Unit() < 0.15)
            {
                stages[4] = Stage(4);
            }

            Play.Add(new ProgramSpec { Stages = stages });
        }
    }

    private static Stream Decompressed(Stream stream)
    {
        return stream.ReadByte() switch
        {
            0 => stream,
            1 => new DeflateStream(stream, CompressionMode.Decompress, true),
            2 => new BrotliStream(stream, CompressionMode.Decompress, true),
            _ => throw new InvalidDataException("compression"),
        };
    }

    // A real cache, read as DiskCacheHostStorage.LoadShaders and DiskCacheGuestStorage.LoadShader read it: programs in
    // the order of shared.toc, one array per guest code index. Untrusted data: every offset and index is checked.
    public static DataSet Real(string directory, ulong seed, Shape playShape)
    {
        DataSet set = new() { Name = "real cache", Kind = "real", Seed = seed };
        byte[] guestToc = File.ReadAllBytes(Path.Combine(directory, "guest.toc"));
        byte[] sharedToc = File.ReadAllBytes(Path.Combine(directory, "shared.toc"));
        using FileStream guestData = File.OpenRead(Path.Combine(directory, "guest.data"));
        using FileStream sharedData = File.OpenRead(Path.Combine(directory, "shared.data"));
        int guestCount = (guestToc.Length - 32) / 16;
        int programCount = (sharedToc.Length - 32) / 8;
        byte[][] guest = new byte[Math.Max(0, guestCount)][];
        Dictionary<(int, int), int> numbers = new();
        byte[] word = new byte[4];

        if (guestCount <= 0 || programCount <= 0 || guestCount > 1 << 20 || programCount > 1 << 20)
        {
            throw new InvalidDataException("table of contents");
        }

        for (int index = 0; index < programCount; index++)
        {
            ulong offset = BinaryPrimitives.ReadUInt64LittleEndian(sharedToc.AsSpan(32 + index * 8));
            if (offset >= (ulong)sharedData.Length)
            {
                throw new InvalidDataException("shared offset");
            }

            sharedData.Seek((long)offset, SeekOrigin.Begin);
            Stream entry = Decompressed(sharedData);
            entry.ReadExactly(word);
            uint mask = BinaryPrimitives.ReadUInt32LittleEndian(word);
            if ((mask & ~0x3fu) != 0)
            {
                throw new InvalidDataException("stage mask");
            }

            bool compute = mask == 0;
            int[] stages = Enumerable.Repeat(-1, compute ? 1 : 6).ToArray();
            for (int stage = 0; stage < 6; stage++)
            {
                if (((compute ? 1u : mask) & (1u << stage)) == 0)
                {
                    continue;
                }

                entry.ReadExactly(word);
                int guestIndex = BinaryPrimitives.ReadInt32LittleEndian(word);
                if ((uint)guestIndex >= (uint)guestCount)
                {
                    throw new InvalidDataException("guest index");
                }

                if (guest[guestIndex] == null)
                {
                    uint codeOffset = BinaryPrimitives.ReadUInt32LittleEndian(guestToc.AsSpan(32 + guestIndex * 16));
                    uint codeSize = BinaryPrimitives.ReadUInt32LittleEndian(guestToc.AsSpan(36 + guestIndex * 16));
                    uint cb1Size = BinaryPrimitives.ReadUInt32LittleEndian(guestToc.AsSpan(40 + guestIndex * 16));
                    if (codeSize == 0 || codeSize > 1 << 24 || (ulong)codeOffset + cb1Size >= (ulong)guestData.Length)
                    {
                        throw new InvalidDataException("guest entry");
                    }

                    guest[guestIndex] = new byte[codeSize];
                    guestData.Seek(codeOffset + cb1Size, SeekOrigin.Begin);
                    Stream code = Decompressed(guestData);
                    code.ReadExactly(guest[guestIndex]);
                    if (code != guestData)
                    {
                        code.Dispose();
                    }
                }

                // One array per guest index, as the loader's memory cache; a code used by two stage kinds is listed in both.
                int slot = compute ? ComputeSlot : stage;
                if (!numbers.TryGetValue((slot, guestIndex), out int number))
                {
                    set.Codes.Add(guest[guestIndex]);
                    number = set.Codes.Count - 1;
                    set.SlotCodes[slot].Add(number);
                    numbers.Add((slot, guestIndex), number);
                }

                stages[stage] = number;
            }

            if (entry != sharedData)
            {
                entry.Dispose();
            }

            set.Programs.Add(new ProgramSpec { Compute = compute, Stages = stages });
        }

        Rng rng = new(seed);
        byte[][][] families = new byte[7][][];
        for (int slot = 0; slot < 7; slot++)
        {
            families[slot] = new[] { new byte[4096] };
            rng.Fill(families[slot][0]);
        }

        playShape.MinSize = 8;
        playShape.MaxSize = set.Codes.Max(code => code.Length);
        playShape.MedianSize = 4096;
        set.AddPlay(rng, playShape, families);
        return set;
    }
}

sealed class Digest
{
    private readonly IncrementalHash _hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    private readonly byte[] _buffer = new byte[1 << 16];
    private int _used;

    public void Add(long value)
    {
        if (_used + 8 > _buffer.Length)
        {
            _hash.AppendData(_buffer, 0, _used);
            _used = 0;
        }

        BinaryPrimitives.WriteInt64LittleEndian(_buffer.AsSpan(_used), value);
        _used += 8;
    }

    public string Finish()
    {
        _hash.AppendData(_buffer, 0, _used);
        _used = 0;
        return Convert.ToHexString(_hash.GetHashAndReset()).ToLowerInvariant();
    }
}

// The complete state of the real tables, read by reflection: every size table, every entry (stored hash, partial or
// full, item, and optionally a hash of the content itself), the bucket count, the identifier counters, the programs.
// Bucket order and the array a partial entry borrows its bytes from are left out: no lookup can tell them.
static class State
{
    private const BindingFlags Any = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    private static readonly Dictionary<(Type, string), FieldInfo> Fields = new();

    public static object Get(object owner, string name)
    {
        Type type = owner.GetType();
        if (!Fields.TryGetValue((type, name), out FieldInfo field))
        {
            field = type.GetField(name, Any) ?? throw new MissingFieldException(type.Name, name);
            Fields.Add((type, name), field);
        }

        return field.GetValue(owner);
    }

    private static long Content(byte[] data, int size)
    {
        ulong hash = 0x9E3779B97F4A7C15UL ^ (ulong)size;
        ReadOnlySpan<byte> span = data.AsSpan(0, size);
        int index = 0;
        for (; index + 8 <= size; index += 8)
        {
            hash = (hash ^ BinaryPrimitives.ReadUInt64LittleEndian(span[index..])) * 0xff51afd7ed558ccdUL;
            hash ^= hash >> 29;
        }

        for (; index < size; index++)
        {
            hash = (hash ^ span[index]) * 0x100000001b3UL;
        }

        return (long)(hash ^ (hash >> 32));
    }

    public static void Table(object table, Func<object, long> item, bool content, Digest digest, Dictionary<string, long> totals)
    {
        FieldInfo reserved = table.GetType().GetField("_reservedSizes", Any);
        if (reserved != null && reserved.GetValue(table) != null)
        {
            throw new InvalidOperationException("a batch left its reservation open");
        }

        IList sizes = (IList)Get(table, "_sizeTable");
        digest.Add(sizes.Count);
        totals["sizeTables"] = totals.GetValueOrDefault("sizeTables") + sizes.Count;
        List<(long, long, long, long)> rows = new();

        foreach (object sizeEntry in sizes)
        {
            int size = (int)sizeEntry.GetType().GetProperty("Size").GetValue(sizeEntry);
            object partition = Get(sizeEntry, "_table");
            Array buckets = (Array)Get(partition, "_buckets");
            int count = (int)Get(partition, "_count");
            rows.Clear();

            void Row(object entry)
            {
                byte[] data = (byte[])Get(entry, "Data");
                int ownSize = (int)Get(entry, "OwnSize");
                if (ownSize != 0 ? ownSize != size || data.Length <= size : data.Length != size)
                {
                    throw new InvalidOperationException("entry size");
                }

                rows.Add(((uint)Get(entry, "Hash"), ownSize != 0 ? 1 : 0, ownSize != 0 ? 0 : item(Get(entry, "Item")), content ? Content(data, size) : 0));
                totals[ownSize != 0 ? "partialEntries" : "fullEntries"] = totals.GetValueOrDefault(ownSize != 0 ? "partialEntries" : "fullEntries") + 1;
            }

            foreach (object bucket in buckets)
            {
                object inline = Get(bucket, "InlineEntry");
                if (Get(inline, "Data") == null)
                {
                    if (Get(bucket, "MoreEntries") != null)
                    {
                        throw new InvalidOperationException("bucket");
                    }

                    continue;
                }

                Row(inline);
                if (Get(bucket, "MoreEntries") is IEnumerable more)
                {
                    foreach (object entry in more)
                    {
                        Row(entry);
                    }
                }
            }

            if (rows.Count != count || (count == 0 ? buckets.Length > 1 : buckets.Length != 1 << System.Numerics.BitOperations.Log2((uint)count)))
            {
                throw new InvalidOperationException("table count");
            }

            rows.Sort();
            digest.Add(size);
            digest.Add(count);
            digest.Add(buckets.Length);
            foreach ((long hash, long partial, long value, long bytes) in rows)
            {
                digest.Add(hash);
                digest.Add(partial);
                digest.Add(value);
                digest.Add(bytes);
            }
        }
    }

    public static long List(object list)
    {
        if (list == null)
        {
            return -1;
        }

        long value = 17;
        foreach (CachedShaderProgram program in (ShaderSpecializationList)list)
        {
            value = value * 1000003 + program.Index + 1;
        }

        return value;
    }

    public static string Of(ShaderCacheHashTable graphics, ComputeShaderCacheHashTable compute, bool content, Dictionary<string, long> totals)
    {
        Digest digest = new();
        foreach (string name in new[] { "_vertexACache", "_vertexBCache", "_tessControlCache", "_tessEvaluationCache", "_geometryCache", "_fragmentCache" })
        {
            object idCache = Get(graphics, name);
            int nextId = (int)Get(idCache, "_id");
            digest.Add(nextId);
            totals["identifiers"] = totals.GetValueOrDefault("identifiers") + nextId;
            Table(Get(idCache, "_cache"), id => (int)id, content, digest, totals);
        }

        IDictionary programs = (IDictionary)Get(graphics, "_shaderPrograms");
        digest.Add(programs.Count);
        totals["idTables"] = programs.Count;
        foreach (DictionaryEntry pair in programs)
        {
            foreach (string name in new[] { "VertexAId", "VertexBId", "TessControlId", "TessEvaluationId", "GeometryId", "FragmentId" })
            {
                digest.Add((int)Get(pair.Key, name));
            }

            digest.Add(List(pair.Value));
        }

        foreach (CachedShaderProgram program in graphics.GetPrograms())
        {
            digest.Add(program.Index);
        }

        Table(Get(compute, "_cache"), List, content, digest, totals);
        foreach (CachedShaderProgram program in compute.GetPrograms())
        {
            digest.Add(program.Index);
        }

        return digest.Finish();
    }
}

sealed class Session
{
    private static readonly ShaderProgramInfo[] Infos =
    {
        null, new(ShaderStage.Vertex), new(ShaderStage.TessellationControl), new(ShaderStage.TessellationEvaluation),
        new(ShaderStage.Geometry), new(ShaderStage.Fragment),
    };

    private static readonly ShaderProgramInfo ComputeInfo = new(ShaderStage.Compute);
    private const int Base = 4096;

    public readonly DataSet Set;
    public ShaderCacheHashTable Graphics;
    public ComputeShaderCacheHashTable Compute;
    public long Probes, Hits, CodesReturned, ShadowedCompute;

    private readonly GpuChannel _channel = new();
    private readonly Dictionary<byte[], int> _numbers = new(ReferenceEqualityComparer.Instance);
    private readonly byte[] _scratch;

    public Session(DataSet set)
    {
        Set = set;
        for (int number = 0; number < set.Codes.Count; number++)
        {
            _numbers[set.Codes[number]] = number;
        }

        int largest = set.Codes.Max(code => code.Length);
        _channel.MemoryManager.Memory = new byte[Base + 6 * (largest + 4096) + 65536];
        _scratch = new byte[largest + 8192];
    }

    public CachedShaderProgram Program(ProgramSpec spec, int index, byte[][] arrays = null)
    {
        CachedShaderStage[] shaders = new CachedShaderStage[spec.Stages.Length];
        for (int stage = 0; stage < shaders.Length; stage++)
        {
            if (spec.Stages[stage] >= 0)
            {
                byte[] code = arrays?[stage] ?? Set.Codes[spec.Stages[stage]];
                shaders[stage] = new CachedShaderStage(spec.Compute ? ComputeInfo : Infos[stage], code, Array.Empty<byte>());
            }
        }

        return new CachedShaderProgram(index, shaders);
    }

    // The load: every program through the loader's registration, in order, then the end of the load.
    public (double, long) Load()
    {
        List<CachedShaderProgram> programs = Set.Programs.Select((spec, index) => Program(spec, index)).ToList();
        Graphics = new ShaderCacheHashTable();
        Compute = new ComputeShaderCacheHashTable();
        ParallelDiskCacheLoader loader = new(Graphics, Compute);
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        TableCounters.Reset();
        long allocated = GC.GetAllocatedBytesForCurrentThread();
        long start = Stopwatch.GetTimestamp();

        for (int index = 0; index < programs.Count; index++)
        {
            loader.ProcessCompiledProgram(programs[index], Set.Programs[index].Compute);
        }

        loader.EndLoad();
        double milliseconds = (Stopwatch.GetTimestamp() - start) * 1000.0 / Stopwatch.Frequency;
        return (milliseconds, GC.GetAllocatedBytesForCurrentThread() - allocated);
    }

    // Guest memory holding the given bytes for each stage, mapped up to the end of the last one; one lookup with the
    // real TryFind. The answer (found, program, the list reached, the cached array of each stage) goes to the digest.
    private readonly ulong[] _address = new ulong[6];
    private int _end;

    private void Begin()
    {
        _end = Base;
        Array.Clear(_address);
    }

    private void Place(int stage, ReadOnlySpan<byte> bytes)
    {
        _address[stage] = (ulong)_end;
        bytes.CopyTo(_channel.MemoryManager.Memory.AsSpan(_end));
        _end += bytes.Length;
    }

    private int Number(byte[] code)
    {
        if (code == null)
        {
            return -1;
        }

        CodesReturned++;
        return _numbers[code];
    }

    private bool Ask(bool compute, Digest digest, out CachedShaderProgram program, out CachedGraphicsGuestCode guestCode)
    {
        _channel.MemoryManager.Mapped = _end;
        ShaderSpecializationList.Last = null;
        guestCode = default;
        bool found;

        if (compute)
        {
            found = Compute.TryFind(_channel, default, default, _address[0], out program, out guestCode.VertexBCode);
            digest.Add(Number(guestCode.VertexBCode));
        }
        else
        {
            GpuChannelPoolState poolState = default;
            GpuChannelGraphicsState graphicsState = default;
            ShaderAddresses addresses = new()
            {
                VertexA = _address[0], VertexB = _address[1], TessControl = _address[2],
                TessEvaluation = _address[3], Geometry = _address[4], Fragment = _address[5],
            };

            found = Graphics.TryFind(_channel, ref poolState, ref graphicsState, addresses, out program, out guestCode);
            digest.Add(Number(guestCode.VertexACode));
            digest.Add(Number(guestCode.VertexBCode));
            digest.Add(Number(guestCode.TessControlCode));
            digest.Add(Number(guestCode.TessEvaluationCode));
            digest.Add(Number(guestCode.GeometryCode));
            digest.Add(Number(guestCode.FragmentCode));
        }

        Probes++;
        Hits += found ? 1 : 0;
        digest.Add(found ? 1 : 0);
        digest.Add(program?.Index ?? -1);
        digest.Add(State.List(ShaderSpecializationList.Last));
        return found;
    }

    private void One(int slot, ReadOnlySpan<byte> bytes, Digest digest)
    {
        Begin();
        Place(slot == DataSet.ComputeSlot ? 0 : slot, bytes);
        Ask(slot == DataSet.ComputeSlot, digest, out _, out _);
    }

    private Span<byte> WithTail(byte[] code, int length, int tail, Rng rng)
    {
        Span<byte> bytes = _scratch.AsSpan(0, length + tail);
        code.AsSpan(0, length).CopyTo(bytes);
        rng.Fill(bytes[length..]);
        return bytes;
    }

    private void Programs(IReadOnlyList<ProgramSpec> specs, int budget, Rng rng, Digest digest)
    {
        int stride = Math.Max(1, specs.Count / Math.Max(1, budget));
        for (int index = 0; index < specs.Count; index += stride)
        {
            ProgramSpec spec = specs[index];
            for (int pass = 0; pass < 2; pass++)
            {
                // The program's codes as the guest holds them, each followed by other bytes; then with one code altered.
                int altered = pass == 0 ? -1 : spec.Stages.Length == 1 ? 0 : rng.Int(2) == 0 ? 1 : 5;
                Begin();
                for (int stage = 0; stage < spec.Stages.Length; stage++)
                {
                    if (spec.Stages[stage] < 0)
                    {
                        continue;
                    }

                    byte[] code = Set.Codes[spec.Stages[stage]];
                    Span<byte> bytes = WithTail(code, code.Length, 24, rng);
                    if (stage == altered)
                    {
                        bytes[rng.Int(code.Length)] ^= (byte)(1 << rng.Int(8));
                    }

                    Place(stage, bytes);
                }

                Ask(spec.Compute, digest, out _, out _);
            }
        }
    }

    public void Ask(Rng rng, Digest digest, int codeBudget, int programBudget, bool play)
    {
        int largest = Set.Codes.Max(code => code.Length);

        for (int slot = 0; slot < 7; slot++)
        {
            List<int> pool = Set.SlotCodes[slot];
            int stride = Math.Max(1, pool.Count / Math.Max(1, codeBudget));

            for (int index = 0; index < pool.Count; index += stride)
            {
                byte[] code = Set.Codes[pool[index]];
                One(slot, WithTail(code, code.Length, 40, rng), digest);                        // the code, then other bytes
                One(slot, code, digest);                                                       // the code, memory ends with it
                One(slot, code.AsSpan(0, code.Length - rng.Range(1, Math.Min(code.Length, 64))), digest); // cut short
                Span<byte> altered = WithTail(code, code.Length, 40, rng);
                altered[rng.Int(code.Length)] ^= (byte)(1 << rng.Int(8));
                One(slot, altered, digest);                                                    // one bit changed
                byte[] other = Set.Codes[pool[rng.Int(pool.Count)]];
                if (other.Length < code.Length)
                {
                    One(slot, WithTail(code, other.Length, 40, rng), digest);                  // its first bytes, up to a registered size
                    One(slot, code.AsSpan(0, other.Length), digest);
                }

                int elsewhere = (slot + 1 + rng.Int(6)) % 7;
                One(elsewhere, WithTail(code, code.Length, 40, rng), digest);                  // in another stage's table
            }

            if (pool.Count == 0)
            {
                continue;
            }

            byte[] longest = Set.Codes[pool.MaxBy(number => Set.Codes[number].Length)];
            One(slot, WithTail(longest, longest.Length, 3000, rng), digest);                   // longer than any registered code
            for (int index = 0; index < 40; index++)
            {
                int size = index % 4 == 0 ? largest + rng.Range(1, 3000) : index % 4 == 1 ? Set.Codes[pool[rng.Int(pool.Count)]].Length : rng.Range(1, largest);
                Span<byte> random = _scratch.AsSpan(0, size);
                rng.Fill(random);
                One(slot, random, digest);                                                     // other content, any size
            }
        }

        Programs(Set.Programs, programBudget, rng, digest);
        if (play)
        {
            Programs(Set.Play, programBudget, rng, digest);
        }
    }

    // Play, as ShaderCache: a lookup, and when no program answers, the program is made from the cached code arrays the
    // lookup returned (new arrays for the others) and added with the real Add.
    public void PlayAll(Rng rng, Digest digest, out int added)
    {
        added = 0;
        for (int index = 0; index < Set.Play.Count; index++)
        {
            ProgramSpec spec = Set.Play[index];
            Begin();
            for (int stage = 0; stage < spec.Stages.Length; stage++)
            {
                if (spec.Stages[stage] >= 0)
                {
                    byte[] code = Set.Codes[spec.Stages[stage]];
                    Place(stage, WithTail(code, code.Length, 24, rng));
                }
            }

            if (!Ask(spec.Compute, digest, out _, out CachedGraphicsGuestCode cached))
            {
                byte[][] arrays = spec.Compute
                    ? new[] { cached.VertexBCode }
                    : new[] { cached.VertexACode, cached.VertexBCode, cached.TessControlCode, cached.TessEvaluationCode, cached.GeometryCode, cached.FragmentCode };
                CachedShaderProgram program = Program(spec, Set.Programs.Count + index, arrays);
                if (spec.Compute)
                {
                    try
                    {
                        Compute.Add(program);
                    }
                    catch (NullReferenceException)
                    {
                        // The engine's own fault for a compute code that a registered, longer code starts with.
                        ShadowedCompute++;
                        digest.Add(-77);
                    }
                }
                else
                {
                    Graphics.Add(program);
                }

                added++;
            }

            if (index % 16 == 15)
            {
                Ask(rng, digest, 12, 12, play: false);
            }
        }
    }
}

static class Fixture
{
    private static readonly Dictionary<string, object> Report = new();

    private static Dictionary<string, object> Run(DataSet set, int repetitions)
    {
        Session session = new(set);
        List<double> times = new();
        long allocated = 0;
        EmbeddedLaunchDiagnostics.Records.Clear();

        for (int repetition = 0; repetition < repetitions; repetition++)
        {
            (double milliseconds, allocated) = session.Load();
            times.Add(Math.Round(milliseconds, 2));
        }

        // The code arrays the load registers (a pool's code no program uses is only probed).
        List<byte[]> used = set.Programs.SelectMany(spec => spec.Stages).Where(code => code >= 0).Distinct().Select(code => set.Codes[code]).ToList();
        Dictionary<string, object> report = new()
        {
            ["name"] = set.Name, ["kind"] = set.Kind, ["programs"] = set.Programs.Count,
            ["computePrograms"] = set.Programs.Count(spec => spec.Compute),
            ["stageCodes"] = set.Programs.Sum(spec => spec.Stages.Count(code => code >= 0)),
            ["codes"] = used.Count, ["codeBytes"] = used.Sum(code => (long)code.Length),
            ["hashedOnce"] = used.Sum(code => (long)(code.Length & ~7)),
            ["distinctSizes"] = used.Select(code => code.Length).Distinct().Count(),
            ["loadMs"] = times, ["loadMsBest"] = times.Min(), ["allocatedBytes"] = allocated,
            ["lookups"] = TableCounters.Lookups, ["hashedBytes"] = TableCounters.HashedBytes, ["comparedBytes"] = TableCounters.ComparedBytes,
            ["entriesAdded"] = TableCounters.Entries, ["rebuilds"] = TableCounters.Rebuilds, ["movedEntries"] = TableCounters.MovedEntries,
            ["journal"] = EmbeddedLaunchDiagnostics.Records.ToList(),
        };

        Dictionary<string, long> totals = new();
        report["state"] = State.Of(session.Graphics, session.Compute, set.ContentDigest, totals);
        foreach (KeyValuePair<string, long> total in totals)
        {
            report[total.Key] = total.Value;
        }

        Digest answers = new();
        session.Ask(new Rng(set.Seed + 1), answers, set.CodeBudget, set.ProgramBudget, play: false);
        report["answers"] = answers.Finish();
        report["probes"] = session.Probes;
        report["hits"] = session.Hits;
        report["codesReturned"] = session.CodesReturned;

        Digest play = new();
        session.PlayAll(new Rng(set.Seed + 2), play, out int added);
        session.Ask(new Rng(set.Seed + 3), play, set.CodeBudget, set.ProgramBudget, play: true);
        report["playAnswers"] = play.Finish();
        report["playPrograms"] = set.Play.Count;
        report["playAdded"] = added;
        report["playShadowedCompute"] = session.ShadowedCompute;
        report["playProbes"] = session.Probes;
        report["playHits"] = session.Hits;
        report["playState"] = State.Of(session.Graphics, session.Compute, set.ContentDigest, totals = new());
        report["playFullEntries"] = totals["fullEntries"];
        report["playSizeTables"] = totals["sizeTables"];
        return report;
    }

    // The reservation by itself, on the real PartitionedHashTable (candidate only: the control has no such method). A
    // table that already holds data, sizes reserved around it, the batch stopped half way: after the release the state
    // must be the one the same adds give without any reservation.
    private static Dictionary<string, object> Reservation()
    {
        MethodInfo reserve = typeof(PartitionedHashTable<int>).GetMethod("ReserveSizes");
        MethodInfo release = typeof(PartitionedHashTable<int>).GetMethod("ReleaseReservedSizes");
        Dictionary<string, object> report = new() { ["present"] = reserve != null && release != null };
        if (reserve == null || release == null)
        {
            return report;
        }

        Rng rng = new(77);
        List<byte[]> codes = new();
        byte[] family = new byte[3000];
        rng.Fill(family);
        for (int index = 0; index < 400; index++)
        {
            byte[] code = new byte[rng.Range(1, 3000)];
            rng.Fill(code);
            family.AsSpan(0, rng.Int(3) == 0 ? 0 : rng.Int(code.Length + 1)).CopyTo(code);
            byte[] earlier = index == 0 ? code : codes[rng.Int(codes.Count)];
            codes.Add(index % 9 == 8 ? earlier[..rng.Range(1, earlier.Length)] : code);
        }

        string Digest(PartitionedHashTable<int> table)
        {
            Digest digest = new();
            State.Table(table, id => (int)id, true, digest, new Dictionary<string, long>());
            return digest.Finish();
        }

        int cases = 0, equal = 0, released = 0, expectedReleased = 0;
        foreach ((int before, int added) in new[] { (0, 400), (0, 250), (150, 400), (150, 300), (399, 400), (200, 200) })
        {
            PartitionedHashTable<int> plain = new(), batched = new();
            for (int index = 0; index < before; index++)
            {
                plain.Add(codes[index], index + 1);
                batched.Add(codes[index], index + 1);
            }

            List<int> sizes = codes.Skip(before).Select(code => code.Length).ToList();
            HashSet<int> used = codes.Take(added).Select(code => code.Length).ToHashSet();
            expectedReleased += sizes.Distinct().Count(size => !used.Contains(size));
            rng.Shuffle(sizes);
            reserve.Invoke(batched, new object[] { sizes });
            for (int index = before; index < added; index++)
            {
                plain.Add(codes[index], index + 1);
                batched.Add(codes[index], index + 1);
            }

            released += (int)release.Invoke(batched, null);
            cases++;
            equal += Digest(plain) == Digest(batched) ? 1 : 0;
        }

        report["cases"] = cases;
        report["equal"] = equal;
        report["released"] = released;
        report["expectedReleased"] = expectedReleased;
        return report;
    }

    private static int Main(string[] arguments)
    {
        string variant = arguments[0];
        int repetitions = int.Parse(arguments[1]);
        List<Dictionary<string, object>> sets = new();
        ulong seed = 1000;

        // Adversarial: codes that are truncations and extensions of others, equal sizes, the same content in two arrays,
        // sizes that are not multiples of eight, every stage kind; three registration orders, with and without sharing.
        foreach (bool sharing in new[] { true, false })
        {
            foreach (string order in new[] { "increasing", "decreasing", "random" })
            {
                sets.Add(Run(DataSet.Synthetic($"adversarial, {order} sizes, {(sharing ? "heavy sharing" : "no sharing")}", ++seed, new Shape
                {
                    Graphics = 760, Compute = 140, Play = 160, VertexCodes = 90, FragmentCodes = 170, ComputeCodes = 45, RareCodes = 14, RareShare = 0.12,
                    MinSize = 4, MaxSize = 6000, SizeStep = 4, MedianSize = 500, Sigma = 1.0, Families = 10,
                    Prefix = 0.18, Duplicate = 0.06, EqualSize = 0.2, Sharing = sharing, Order = order,
                }), repetitions));
            }
        }

        // The shape of the real cache measured on the host: 1,961 programs, 2,347 codes of 104 to 81,296 bytes in multiples
        // of eight, none the start of another, most sharing under 400 first bytes with another and a few a fifth of their size.
        sets.Add(Run(DataSet.Synthetic("synthetic, shape of the measured cache", 2001, new Shape
        {
            Graphics = 1468, Compute = 493, Play = 120, VertexCodes = 703, FragmentCodes = 1151, ComputeCodes = 493, RareCodes = 0, RareShare = 0,
            MinSize = 104, MaxSize = 81296, SizeStep = 8, MedianSize = 4000, Sigma = 1.1, Families = 40,
            Prefix = 0, Duplicate = 0, EqualSize = 0, Sharing = true, ShareNone = 0.05, ShareLong = 0.06, HeaderMin = 16, HeaderMax = 400,
        }), repetitions));

        // The size of a Super Smash Bros. Ultimate load (12,600 programs); the code pool and its sharing are a guess.
        DataSet launch = DataSet.Synthetic("synthetic, 12,600 programs", 3001, new Shape
        {
            Graphics = 12000, Compute = 600, Play = 80, VertexCodes = 2600, FragmentCodes = 5200, ComputeCodes = 300, RareCodes = 12, RareShare = 0.004,
            MinSize = 200, MaxSize = 204800, SizeStep = 8, MedianSize = 4000, Sigma = 1.1, Families = 60,
            Prefix = 0, Duplicate = 0, EqualSize = 0, Sharing = true, ShareNone = 0.05, ShareLong = 0.06, HeaderMin = 16, HeaderMax = 400,
        });
        launch.ContentDigest = false;
        launch.CodeBudget = 600;
        launch.ProgramBudget = 1500;
        sets.Add(Run(launch, 1));

        if (arguments.Length > 2)
        {
            sets.Add(Run(DataSet.Real(arguments[2], 4001, new Shape { Play = 120, SizeStep = 8, Sigma = 1.0 }), repetitions));
        }

        Report["variant"] = variant;
        Report["sets"] = sets;
        Report["reservation"] = Reservation();
        Console.WriteLine(JsonSerializer.Serialize(Report));
        return 0;
    }
}
