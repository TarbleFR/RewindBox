// Host fixture for adapt_array_rebuild_allocations. The production TextureBindingsArrayCache, the threaded array
// producers (ThreadedTextureArray, ThreadedImageArray), their commands and ThreadedArrayPool are compiled unchanged
// from the prepared tree (control) or from that tree with the adapter (candidate). Only the GPU resources, the pools,
// memory and the renderer transport are doubled, following the production rules the cache relies on (the same doubles
// as the adapt_bindless_array_deltas fixture: pool items replaced only by a different descriptor, format aliases,
// storage replacement by scaling and blacklisting, removal and alias-list destruction).
//
// What it runs:
// - scenarios: random pool writes, rewrites, removals, remaps, scaling, alias-list destruction and quiet passes, on
//   texture, sampler and image arrays, threaded and direct, at lengths below and above the 4096-element scratch limit;
//   after every update the backend contents, the backend call stream, the store/synchronisation sets and the cache's
//   recorded state (per-element delta state, texture set, reference counts) are digested;
// - buffer-handle scenarios: the same, for arrays whose handles are read from a constant buffer (UpdateFromBuffer,
//   combined and separate sampler handles, lengths 300 to 8000), with buffer-word rewrites and failing lookups;
// - one cache with arrays of several large lengths (one over the retention budget) rebuilt in turn;
// - the measurement: whole rebuilds of 65536-element arrays (pool of 65536, 4096 distinct textures) of every kind,
//   threaded and direct, then threaded texture arrays of 200000, 524288 and 1100000 elements (the last one over the
//   retention budget), dispatches rebuilding three arrays of one element type, and buffer-handle rebuilds of 8000
//   elements, with GC.GetAllocatedBytesForCurrentThread read at the boundaries the doubles see (first and last pool
//   lookup, each threaded command reservation or direct backend call, the pipeline binding, the return);
// - bursts of 200 threaded rebuilds with the render-thread consumer lagging behind by 1, 2, 4, 8, 16 and 37 rebuilds
//   (the queue is drained only every N rebuilds), with the GC collection counts and pause time.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Commands;
using Ryujinx.Graphics.GAL.Multithreading.Commands.ImageArray;
using Ryujinx.Graphics.GAL.Multithreading.Commands.TextureArray;
using Ryujinx.Graphics.GAL.Multithreading.Model;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Engine.Types;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Shader;
using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;

static class Check
{
    public static int Count;
    public static void That(bool value, string message)
    {
        Count++;
        if (!value) throw new InvalidOperationException(message);
    }
}

// Allocation probe: marks are stored in preallocated arrays, so probing allocates nothing.
static class Probe
{
    public static bool Enabled;
    public static readonly string[] Names = new string[64];
    public static readonly long[] Bytes = new long[64];
    public static int Count;
    static bool _inLoop;
    static long _lastLookup;
    public static long Lookups;

    public static void Begin()
    {
        Count = 0; _inLoop = false; Lookups = 0; Enabled = true;
        Add("start", GC.GetAllocatedBytesForCurrentThread());
    }

    public static void End()
    {
        Mark("end");
        Enabled = false;
    }

    static void Add(string name, long bytes)
    {
        if (Count < Names.Length) { Names[Count] = name; Bytes[Count] = bytes; Count++; }
    }

    public static void Lookup()
    {
        if (!Enabled) return;
        long bytes = GC.GetAllocatedBytesForCurrentThread();
        Lookups++;
        if (!_inLoop) { Add("first pool lookup", bytes); _inLoop = true; }
        _lastLookup = bytes;
    }

    public static void Mark(string name)
    {
        if (!Enabled) return;
        long bytes = GC.GetAllocatedBytesForCurrentThread();
        if (_inLoop) { Add("last pool lookup", _lastLookup); _inLoop = false; }
        Add(name, bytes);
    }
}

sealed class TestFailure : Exception { }
sealed class HostTexture : ITexture { public readonly int Id; public readonly string Name; public HostTexture(int id, string name) { Id = id; Name = name; } }
sealed class HostSampler : ISampler { public readonly int Id; public HostSampler(int id) => Id = id; }

// The backend call stream is hashed without allocating (direct backends run on the measured thread).
static class CallStream
{
    public static ulong Hash = 14695981039346656037UL;
    public static long Calls, Elements;
    public static void Add(long value) { Hash = (Hash ^ (ulong)value) * 1099511628211UL; }
    public static long Id(object value) => value switch
    {
        null => 0,
        HostTexture t => t.Id,
        HostSampler s => -1 - s.Id,
        ThreadedTexture w => Id(w.Base),
        ThreadedSampler w => Id(w.Base),
        _ => long.MinValue,
    };
    public static void Record<T>(int method, int sink, int index, T[] values) where T : class
    {
        Calls++;
        Elements += values.Length;
        Add(method); Add(sink); Add(index); Add(values.Length);
        foreach (T value in values) Add(Id(value));
    }
}

sealed class TextureSink : ITextureArray
{
    public readonly int Number;
    public readonly ITexture[] Textures;
    public readonly ISampler[] Samplers;
    public long Calls, Elements;
    public TextureSink(int number, int length) { Number = number; Textures = new ITexture[length]; Samplers = new ISampler[length]; }
    public void SetTextures(int index, ITexture[] textures)
    {
        Probe.Mark("backend SetTextures");
        CallStream.Record(1, Number, index, textures);
        Array.Copy(textures, 0, Textures, index, textures.Length); Calls++; Elements += textures.Length;
    }
    public void SetSamplers(int index, ISampler[] samplers)
    {
        Probe.Mark("backend SetSamplers");
        CallStream.Record(2, Number, index, samplers);
        Array.Copy(samplers, 0, Samplers, index, samplers.Length); Calls++; Elements += samplers.Length;
    }
    public void Dispose() { }
}

sealed class ImageSink : IImageArray
{
    public readonly int Number;
    public readonly ITexture[] Images;
    public long Calls, Elements;
    public ImageSink(int number, int length) { Number = number; Images = new ITexture[length]; }
    public void SetImages(int index, ITexture[] images)
    {
        Probe.Mark("backend SetImages");
        CallStream.Record(3, Number, index, images);
        Array.Copy(images, 0, Images, index, images.Length); Calls++; Elements += images.Length;
    }
    public void Dispose() { }
}

enum Kind { Texture, Sampler, Image }

sealed class World
{
    public readonly Random Random;
    public readonly bool ThreadedMode;
    public readonly ThreadedRenderer Threaded;
    public readonly DirectRenderer Direct;
    public readonly GpuContext Context;
    public readonly GpuChannel Channel = new();
    public readonly TextureBindingsArrayCache Cache;
    public readonly TexturePool Textures;
    public readonly SamplerPool Samplers;
    public readonly Dictionary<int, Texture> Library = new();
    public readonly List<Texture> All = new();
    public readonly Sampler[] SamplerLibrary;
    public readonly HashSet<HostTexture> Released = new();
    public readonly int Length, LibrarySize;
    public int Violations, NextHost = 1;
    public IRenderer Renderer => (IRenderer)Threaded ?? Direct;

    public World(int length, bool threaded, int seed, int librarySize = 24)
    {
        Random = new Random(seed);
        Length = length;
        LibrarySize = librarySize;
        ThreadedMode = threaded;
        if (threaded) Threaded = new ThreadedRenderer(); else Direct = new DirectRenderer();
        Context = new GpuContext { Renderer = Renderer };
        SamplerLibrary = new Sampler[librarySize + 1];
        for (int key = 0; key <= librarySize; key++)
        {
            ISampler sampler = new HostSampler(key);
            SamplerLibrary[key] = new Sampler(threaded ? new ThreadedSampler { Base = sampler } : sampler, key);
            if (key != 0) Library[key] = NewTexture(key, 1 + key % 3);
        }
        Textures = new TexturePool(this, length);
        Samplers = new SamplerPool(this, length);
        for (int id = 0; id < length; id++)
        {
            Textures.Keys[id] = id % 5 == 0 ? 0 : 1 + id % librarySize;
            Samplers.Keys[id] = id % 7 == 0 ? 0 : 1 + id % librarySize;
        }
        Cache = new TextureBindingsArrayCache(Context, Channel);
    }

    public ITexture NewHost(string name)
    {
        ITexture host = new HostTexture(NextHost++, name);
        return ThreadedMode ? new ThreadedTexture { Base = host } : host;
    }

    public Texture NewTexture(int key, int format, Texture parent = null)
    {
        Texture texture = new(this, NewHost(parent == null ? "t" + key : "a" + key + "." + format), key, format, parent);
        All.Add(texture);
        return texture;
    }

    public static HostTexture Raw(object host) => host switch { ThreadedTexture t => (HostTexture)t.Base, HostTexture h => h, _ => null };

    public void Release(ITexture host) => Released.Add(Raw(host));

    public static TextureBindingInfo Binding(int length, Kind kind, TextureUsageFlags flags = 0, int format = 0, Target target = Target.Texture2D)
        => kind == Kind.Sampler
            ? new(target, 0, 0, length, 0, TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct), flags, true)
            : new(target, new FormatInfo(format), 0, 0, length, 0, TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct), flags);

    // A handle array read from constant buffer 0 (handles at words 0, 2, 4, ...). Combined: the sampler id is in the
    // high bits of each handle (SamplerIndex.Independently). Separate: one sampler handle at word 100 of buffer 1.
    public static TextureBindingInfo BufferBinding(int length, Kind kind, bool separate, Target target = Target.Texture2D)
    {
        int handle = separate ? TextureHandle.PackOffsets(0, 100, TextureHandleType.SeparateSamplerHandle)
                              : TextureHandle.PackOffsets(0, 0, TextureHandleType.CombinedSampler);
        int slots = separate ? TextureHandle.PackSlots(0, 1) : 0;
        return kind == Kind.Sampler
            ? new(target, 0, 0, length, slots, handle, 0, true)
            : new(target, new FormatInfo(0), 0, 0, length, slots, handle, 0);
    }

    public int[] Buffer(int slot) => Channel.MemoryManager.Physical.Buffers[slot];

    public int RandomHandle() => Random.Next(Length) | (Random.Next(Math.Min(Length, 4096)) << 20);

    public void FillHandles(int length, bool separate)
    {
        int[] words = Buffer(0);
        for (int i = 0; i < length; i++) words[2 * i] = Random.Next(9) == 0 ? 0 : RandomHandle();
        if (separate) Buffer(1)[100] = (1 + Random.Next(Math.Min(Length, 4096) - 1)) << 20;
    }

    public void UpdateBuffer(in TextureBindingInfo binding, Kind kind, bool drain = true)
    {
        Context.SequenceNumber++;
        if (kind == Kind.Image) Cache.UpdateImageArray(Textures, ShaderStage.Compute, 0, 0, binding);
        else Cache.UpdateTextureArray(Textures, Samplers, ShaderStage.Compute, 0, 0, SamplerIndex.Independently, binding);
        if (drain) Threaded?.Drain();
    }

    public void UpdateOnly(in TextureBindingInfo binding, Kind kind)
    {
        Context.SequenceNumber++;
        if (kind == Kind.Image) Cache.UpdateImageArray(Textures, ShaderStage.Compute, 0, 0, binding);
        else Cache.UpdateTextureArray(Textures, Samplers, ShaderStage.Compute, 0, 0, SamplerIndex.ViaHeaderIndex, binding);
    }

    public void Update(in TextureBindingInfo binding, Kind kind)
    {
        UpdateOnly(binding, kind);
        Threaded?.Drain();
    }

    // A delta pass that fails on the lookup of a written element: the next update of the entry is a whole rebuild
    // (the entry is marked ForceRebuild), as after any failed update in production.
    public void ForceRebuild(in TextureBindingInfo binding, Kind kind, int id, bool drain = true)
    {
        if (kind == Kind.Sampler) { Samplers.Write(id, 1 + (Samplers.Keys[id] % LibrarySize)); Samplers.ThrowAt = id; }
        else { Textures.Write(id, 1 + (Textures.Keys[id] % LibrarySize)); Textures.ThrowAt = id; }
        bool threw = false;
        try { if (drain) Update(binding, kind); else UpdateOnly(binding, kind); }
        catch (TestFailure) { threw = true; if (drain) Threaded?.Drain(); }
        Textures.ThrowAt = Samplers.ThrowAt = -1;
        Check.That(threw, "the forcing delta pass reached the failing lookup");
        Textures.Touch(); Samplers.Touch();
    }

    public TextureSink TextureSink(int i = 0) => Threaded?.TextureSinks[i] ?? Direct.TextureSinks[i];
    public ImageSink ImageSink(int i = 0) => Threaded?.ImageSinks[i] ?? Direct.ImageSinks[i];

    public void Remove(Texture texture)
    {
        if (texture.Disposed) return;
        Textures.ForceRemove(texture);
        texture.Dispose();
        if (Library.TryGetValue(texture.Key, out Texture current) && current == texture)
            Library[texture.Key] = NewTexture(texture.Key, texture.Format);
    }

    public Texture RandomLibraryTexture() => Library[1 + Random.Next(LibrarySize)];

    public void Mutate(int operations)
    {
        for (int i = 0; i < operations; i++)
        {
            int id = Random.Next(Length);
            switch (Random.Next(12))
            {
                case 0: Textures.Write(id, Random.Next(3) == 0 ? 0 : 1 + Random.Next(LibrarySize)); break;
                case 1: Textures.Write(id, Textures.Keys[id]); break;
                case 2: Samplers.Write(id, Random.Next(4) == 0 ? 0 : 1 + Random.Next(LibrarySize)); break;
                case 3: Samplers.Write(id, Samplers.Keys[id]); break;
                case 4: Remove(RandomLibraryTexture()); break;
                case 5: RandomLibraryTexture().Invalidate(); break;
                case 6: Textures.Touch(); break;
                case 7: Samplers.Touch(); break;
                case 8: RandomLibraryTexture().ScaleUp(); break;
                case 9: Textures.RemoveAliasList(RandomLibraryTexture(), Random.Next(2) == 0); break;
                case 10: Textures.DisposeOrphanAliases(); break;
                default: Textures.Write(id, 1 + Random.Next(LibrarySize)); break;
            }
        }
    }

    public static string Describe(object value) => value switch
    {
        null => "-",
        HostTexture t => t.Name,
        HostSampler s => "s" + s.Id,
        ThreadedTexture w => Describe(w.Base),
        ThreadedSampler w => Describe(w.Base),
        Texture t => t.Name + "#" + t.Key + "." + t.Format,
        Sampler s => "S" + s.Key + (s.IsDisposed ? "x" : ""),
        _ => "?",
    };

    public string Contents()
    {
        StringBuilder text = new();
        foreach (TextureSink sink in Threaded?.TextureSinks ?? Direct.TextureSinks)
        {
            foreach (ITexture texture in sink.Textures) text.Append(Describe(texture)).Append(',');
            text.Append('|');
            foreach (ISampler sampler in sink.Samplers) text.Append(Describe(sampler)).Append(',');
            text.Append('\n');
        }
        foreach (ImageSink sink in Threaded?.ImageSinks ?? Direct.ImageSinks)
        {
            foreach (ITexture image in sink.Images) text.Append(Describe(image)).Append(',');
            text.Append('\n');
        }
        return text.ToString();
    }

    // The cache's recorded state, read by reflection: every entry's per-element delta state, its texture set (with
    // recorded sequences, in enumeration order), its reference counts and its flags.
    public string CacheState()
    {
        StringBuilder text = new();
        const BindingFlags Any = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        object pool = typeof(TextureBindingsArrayCache).GetField("_cacheFromPool", Any).GetValue(Cache);
        foreach (object pair in (IEnumerable)pool)
        {
            object entry = pair.GetType().GetProperty("Value").GetValue(pair);
            Type type = entry.GetType();
            foreach (string name in new[] { "DeltaLength", "DeltaReady", "DeltaAliasGeneration", "DeltaAllBlacklisted", "DeltaLogPosition", "ForceRebuild" })
                text.Append(name).Append('=').Append(type.GetField(name, Any).GetValue(entry)).Append(';');
            text.Append("fmt=").Append(((FormatInfo)type.GetField("DeltaFormatInfo", Any).GetValue(entry)).Format).Append(';');
            foreach (string name in new[] { "DeltaItems", "DeltaTextures", "DeltaSequences", "DeltaHosts", "DeltaSamplers", "DeltaHostSamplers" })
            {
                text.Append(name).Append('[');
                if (type.GetField(name, Any).GetValue(entry) is Array values)
                    foreach (object value in values) text.Append(value is int n ? n.ToString() : Describe(value)).Append(',');
                else text.Append("null");
                text.Append(']');
            }
            text.Append("Textures{");
            foreach (KeyValuePair<Texture, int> item in (Dictionary<Texture, int>)type.GetField("Textures", Any).GetValue(entry))
                text.Append(Describe(item.Key)).Append(':').Append(item.Value).Append(',');
            text.Append("}refs{");
            if (type.GetField("_deltaReferences", Any).GetValue(entry) is Dictionary<Texture, int> references)
                foreach (KeyValuePair<Texture, int> item in references) text.Append(Describe(item.Key)).Append(':').Append(item.Value).Append(',');
            text.Append("}\n");
        }
        object buffer = typeof(TextureBindingsArrayCache).GetField("_cacheFromBuffer", Any).GetValue(Cache);
        foreach (object pair in (IEnumerable)buffer)
        {
            object entry = pair.GetType().GetProperty("Value").GetValue(pair);
            Type type = entry.GetType();
            text.Append("buffer{");
            foreach (KeyValuePair<int, (Texture, TextureDescriptor)> item in (Dictionary<int, (Texture, TextureDescriptor)>)type.GetField("TextureIds", Any).GetValue(entry))
                text.Append(item.Key).Append(':').Append(Describe(item.Value.Item1)).Append(':').Append(item.Value.Item2.Value).Append(',');
            text.Append("}samplers{");
            foreach (KeyValuePair<int, (Sampler, SamplerDescriptor)> item in (Dictionary<int, (Sampler, SamplerDescriptor)>)type.GetField("SamplerIds", Any).GetValue(entry))
                text.Append(item.Key).Append(':').Append(Describe(item.Value.Item1)).Append(':').Append(item.Value.Item2.Value).Append(',');
            text.Append("}Textures{");
            foreach (KeyValuePair<Texture, int> item in (Dictionary<Texture, int>)type.GetField("Textures", Any).GetValue(entry))
                text.Append(Describe(item.Key)).Append(':').Append(item.Value).Append(',');
            text.Append("}\n");
        }
        return text.ToString();
    }
}

static class Program
{
#if ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif

    static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))[..16];

    static long Total(PD.Counter counter) => PD.Totals[(int)counter];

    static string Step(World w, in TextureBindingInfo binding, Kind kind, bool buffer = false)
    {
        foreach (Texture t in w.All) t.ResetStep();
        if (buffer) w.UpdateBuffer(binding, kind); else w.Update(binding, kind);
        Check.That(w.Violations == 0, "a call reached a disposed texture");
        string synced = string.Join(",", w.All.Where(t => t.StepSynced).Select(t => t.SignalName).OrderBy(n => n, StringComparer.Ordinal));
        string signaled = string.Join(",", w.All.Where(t => t.StepSignaled).Select(t => t.SignalName).OrderBy(n => n, StringComparer.Ordinal));
        return Hash(w.Contents() + "#" + synced + "#" + signaled + "#" + w.CacheState() + "#" + CallStream.Hash + "/" + CallStream.Calls);
    }

    static object Scenario(bool threaded, Kind kind, bool store, bool resScale, int length, int format, int seed, int steps)
    {
        World w = new(length, threaded, seed);
        CallStream.Hash = 14695981039346656037UL; CallStream.Calls = 0;
        TextureUsageFlags flags = (store ? TextureUsageFlags.ImageStore : 0) | (resScale ? TextureUsageFlags.ResScaleUnsupported : 0);
        TextureBindingInfo binding = World.Binding(length, kind, flags, format);
        List<string> digests = new();
        long full0 = Total(PD.Counter.ArrayFullElements);
        for (int step = 0; step < steps; step++)
        {
            if (step != 0) w.Mutate(1 + w.Random.Next(step % 4 == 0 ? 0 : 6));
            if (step % 7 == 3) w.ForceRebuild(binding, kind, w.Random.Next(length));
            digests.Add(Step(w, binding, kind));
        }
        w.Threaded?.Dispose();
        return new { threaded, kind = kind.ToString(), store, resScale, length, format, seed, steps,
                     fullElements = Total(PD.Counter.ArrayFullElements) - full0, digest = Hash(string.Join(";", digests)) };
    }

    // One cache, arrays of several lengths over the 4096-element scratch limit (one over the retention budget) on a
    // 5000-element pool: each binding has its own entry and its own backend array; every update is a whole rebuild.
    static object MixedLengths(bool threaded)
    {
        World w = new(5000, threaded, 29);
        CallStream.Hash = 14695981039346656037UL; CallStream.Calls = 0;
        (int Length, Kind Kind)[] arrays = { (5000, Kind.Texture), (6000, Kind.Texture), (70000, Kind.Sampler), (5000, Kind.Image),
                                             (600000, Kind.Texture), (2_000_000, Kind.Image), (70000, Kind.Texture), (4096, Kind.Texture) };
        int[] order = { 0, 1, 2, 3, 4, 5, 6, 7, 4, 4, 2, 6, 6, 5, 0, 1, 7, 3, 4, 6, 2, 5, 1, 0 };
        List<string> digests = new();
        HashSet<int> created = new();
        foreach (int index in order)
        {
            w.Mutate(2);
            w.Textures.Touch(); w.Samplers.Touch();
            (int length, Kind kind) = arrays[index];
            TextureBindingInfo binding = World.Binding(length, kind, 0, 0, index == 6 ? Target.Texture2DArray : Target.Texture2D);
            // Once an entry exists, its next update is forced to a whole rebuild.
            if (!created.Add(index)) w.ForceRebuild(binding, kind, 17);
            long full0 = Total(PD.Counter.ArrayFullElements);
            digests.Add(Step(w, binding, kind));
            Check.That(Total(PD.Counter.ArrayFullElements) - full0 == Math.Min(5000, length), "every mixed-length update rebuilds");
        }
        object retention = Retention(w.Cache);
        w.Threaded?.Dispose();
        return new { threaded, updates = order.Length, digest = Hash(string.Join(";", digests)), retention };
    }

    // Handle arrays read from a constant buffer (UpdateFromBuffer): buffer words rewritten, pool mutations, a lookup
    // that fails half-way through a rebuild (the arrays are returned by the finally block), quiet passes.
    static object BufferScenario(bool threaded, Kind kind, bool separate, int length, int seed, int steps)
    {
        World w = new(8192, threaded, seed);
        CallStream.Hash = 14695981039346656037UL; CallStream.Calls = 0;
        TextureBindingInfo binding = World.BufferBinding(length, kind, separate);
        w.FillHandles(length, separate);
        List<string> digests = new();
        long buffer0 = Total(PD.Counter.ArrayBufferElements);
        int failures = 0;
        for (int step = 0; step < steps; step++)
        {
            if (step != 0)
            {
                w.Mutate(w.Random.Next(4));
                for (int i = w.Random.Next(step % 3 == 0 ? 0 : 5); i > 0; i--) w.Buffer(0)[2 * w.Random.Next(length)] = w.RandomHandle();
                if (separate && step % 5 == 2) w.Buffer(1)[100] = (1 + w.Random.Next(4095)) << 20;
            }
            if (step % 6 == 4)
            {
                // A failing lookup during a rebuild: the next pass rebuilds again from the rewritten word.
                int index = w.Random.Next(length);
                int word = w.RandomHandle();
                w.Buffer(0)[2 * index] = word;
                w.Textures.ThrowAt = word & 0xfffff;
                bool threw = false;
                try { w.UpdateBuffer(binding, kind); } catch (TestFailure) { threw = true; w.Threaded?.Drain(); }
                w.Textures.ThrowAt = -1;
                Check.That(threw, "the failing buffer rebuild reached the failing lookup");
                failures++;
                w.Buffer(0)[2 * index] = w.RandomHandle();
            }
            digests.Add(Step(w, binding, kind, buffer: true));
        }
        w.Threaded?.Dispose();
        long elements = Total(PD.Counter.ArrayBufferElements) - buffer0;
        Check.That(elements >= (long)length * (steps / 2), "buffer scenarios rebuild");
        return new { threaded, kind = kind.ToString(), separate, length, seed, steps, failures, bufferElements = elements,
                     digest = Hash(string.Join(";", digests)) };
    }

    // What the cache and the threaded pools retain between updates (the candidate's bounded large slots).
    static object Retention(TextureBindingsArrayCache cache)
    {
        const BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        List<object> slots = new();
        void Inspect(string owner, string field, object value)
        {
            if (value is not Array[] arrays) return;
            long elements = 0, live = 0; int retained = 0;
            foreach (Array array in arrays)
            {
                if (array == null) continue;
                retained++; elements += array.Length;
                foreach (object item in array) if (item != null) live++;
            }
            slots.Add(new { owner, field, slots = arrays.Length, retained, elements, live });
        }
        foreach (FieldInfo field in typeof(TextureBindingsArrayCache).GetFields(Any))
            if (field.FieldType.IsArray && field.FieldType.GetElementType().IsArray) Inspect("cache", field.Name, field.GetValue(cache));
        foreach (Type type in new[] { typeof(ThreadedArrayPool<ITexture>), typeof(ThreadedArrayPool<ISampler>) })
            foreach (FieldInfo field in type.GetFields(Any))
                if (field.FieldType.IsArray && field.FieldType.GetElementType().IsArray) Inspect(type.GetGenericArguments()[0].Name, field.Name, field.GetValue(null));
        return slots;
    }

    // Whole rebuilds of existing entries: "arrays" arrays of one element type rebuilt in one dispatch (distinct targets,
    // so distinct entries), then the threaded queue drained, as when the render thread keeps up with the dispatch.
    // Pool path: pool-sized arrays, 4096 distinct textures, each entry forced to a whole rebuild beforehand. Buffer path
    // (UpdateFromBuffer): one handle word rewritten before each dispatch, which makes the next pass a whole rebuild.
    static readonly Target[] DispatchTargets = { Target.Texture2D, Target.Texture2DArray, Target.Cubemap };

    static object Measure(bool threaded, Kind kind, int length, int arrays = 1, bool buffer = false)
    {
        World w = new(buffer ? 8192 : length, threaded, 3, librarySize: 4096);
        CallStream.Hash = 14695981039346656037UL; CallStream.Calls = 0;
        TextureBindingInfo[] bindings = new TextureBindingInfo[arrays];
        for (int a = 0; a < arrays; a++)
            bindings[a] = buffer ? World.BufferBinding(length, kind, false, DispatchTargets[a]) : World.Binding(length, kind, 0, 0, DispatchTargets[a]);
        if (buffer) w.FillHandles(length, false);
        for (int a = 0; a < arrays; a++)
        {
            if (buffer) w.UpdateBuffer(bindings[a], kind); else w.Update(bindings[a], kind);
        }
        const int Warmup = 3, Updates = 12;
        PD.Counter counter = buffer ? PD.Counter.ArrayBufferElements : PD.Counter.ArrayFullElements;
        Dictionary<string, long> segments = new();
        List<string> order = new();
        long bytes = 0, consumer = 0, ticks = 0, lookups = 0;
        int[] toggle = { w.RandomHandle(), w.RandomHandle() };
        for (int u = 0; u < Warmup + Updates; u++)
        {
            if (buffer) w.Buffer(0)[2 * ((u * 7919) % length)] = toggle[u & 1];
            else for (int a = 0; a < arrays; a++) w.ForceRebuild(bindings[a], kind, (u * 7919 + a * 104729) % length);
            long full0 = Total(counter);
            w.Context.SequenceNumber++;
            Probe.Begin();
            long start = Stopwatch.GetTimestamp();
            for (int a = 0; a < arrays; a++)
            {
                if (kind == Kind.Image) w.Cache.UpdateImageArray(w.Textures, ShaderStage.Compute, 0, 0, bindings[a]);
                else w.Cache.UpdateTextureArray(w.Textures, w.Samplers, ShaderStage.Compute, 0, 0,
                                                buffer ? SamplerIndex.Independently : SamplerIndex.ViaHeaderIndex, bindings[a]);
            }
            long elapsed = Stopwatch.GetTimestamp() - start;
            Probe.End();
            long drain0 = GC.GetAllocatedBytesForCurrentThread();
            w.Threaded?.Drain();
            long drained = GC.GetAllocatedBytesForCurrentThread() - drain0;
            Check.That(Total(counter) - full0 == (long)length * arrays, "every measured update is a whole rebuild");
            if (u < Warmup) continue;
            ticks += elapsed; consumer += drained; lookups += Probe.Lookups;
            bytes += Probe.Bytes[Probe.Count - 1] - Probe.Bytes[0];
            for (int i = 1; i < Probe.Count; i++)
            {
                string name = Probe.Names[i - 1] + " -> " + Probe.Names[i];
                if (!segments.ContainsKey(name)) { segments[name] = 0; order.Add(name); }
                segments[name] += Probe.Bytes[i] - Probe.Bytes[i - 1];
            }
        }
        // The backend contents, the recorded state and the backend call stream of every measured rebuild.
        string digest = Hash(w.Contents() + "#" + w.CacheState() + "#" + CallStream.Hash + "/" + CallStream.Calls);
        object retention = Retention(w.Cache);
        w.Threaded?.Dispose();
        return new
        {
            threaded, kind = kind.ToString(), length, arrays, path = buffer ? "buffer" : "pool",
            bytesPerRebuild = bytes / Updates,
            bytesPerElement = Math.Round(bytes / (double)Updates / length / arrays, 2),
            consumerBytesPerRebuild = consumer / Updates,
            lookupsPerRebuild = lookups / Updates,
            microsecondsPerRebuild = Math.Round(ticks * 1e6 / Stopwatch.Frequency / Updates, 1),
            segments = order.Select(name => new { segment = name, bytesPerRebuild = segments[name] / Updates }).ToList(),
            digest, retention,
        };
    }

    // A burst of whole rebuilds (threaded texture arrays of 65536), as in a scene transition: GC count and pause. The
    // render-thread double consumes the queue only every "drainEvery" rebuilds, so up to that many snapshots per element
    // type are in flight at once (the device's render thread runs asynchronously and can lag behind a burst).
    static object Burst(int rebuilds, int drainEvery)
    {
        World w = new(65536, true, 5, librarySize: 4096);
        CallStream.Hash = 14695981039346656037UL; CallStream.Calls = 0;
        TextureBindingInfo binding = World.Binding(65536, Kind.Texture);
        w.Update(binding, Kind.Texture);
        // One warm-up round at the same lag: the kept slots fill once (the first lagging round allocates), as they do
        // on the device after the first burst; the measured burst is the steady state.
        for (int i = 0; i < drainEvery; i++)
        {
            w.ForceRebuild(binding, Kind.Texture, (i * 7919) % 65536, drain: false);
            w.UpdateOnly(binding, Kind.Texture);
        }
        w.Threaded.Drain();
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        int g0 = GC.CollectionCount(0), g1 = GC.CollectionCount(1), g2 = GC.CollectionCount(2);
        TimeSpan pause0 = GC.GetTotalPauseDuration();
        long allocated0 = GC.GetTotalAllocatedBytes(true);
        long start = Stopwatch.GetTimestamp();
        long full0 = Total(PD.Counter.ArrayFullElements);
        for (int i = 0; i < rebuilds; i++)
        {
            w.ForceRebuild(binding, Kind.Texture, (i * 104729) % 65536, drain: false);
            w.UpdateOnly(binding, Kind.Texture);
            if ((i + 1) % drainEvery == 0) w.Threaded.Drain();
        }
        w.Threaded.Drain();
        double seconds = (Stopwatch.GetTimestamp() - start) / (double)Stopwatch.Frequency;
        Check.That(Total(PD.Counter.ArrayFullElements) - full0 == (long)rebuilds * 65536, "every burst update rebuilds");
        double allocatedMiB = Math.Round((GC.GetTotalAllocatedBytes(true) - allocated0) / 1048576.0, 1);
        int gen0 = GC.CollectionCount(0) - g0, gen1 = GC.CollectionCount(1) - g1, gen2 = GC.CollectionCount(2) - g2;
        double pauseMs = Math.Round((GC.GetTotalPauseDuration() - pause0).TotalMilliseconds, 1);
        // Read after the counters: the digest itself allocates.
        string digest = Hash(w.Contents() + "#" + w.CacheState() + "#" + CallStream.Hash + "/" + CallStream.Calls);
        object result = new
        {
            rebuilds, drainEvery, digest, allocatedMiB, gen0, gen1, gen2, pauseMs,
            wallMs = Math.Round(seconds * 1000, 1),
        };
        w.Threaded?.Dispose();
        return result;
    }

    static void Main()
    {
        List<object> scenarios = new();
        foreach (bool threaded in new[] { true, false })
            foreach (Kind kind in new[] { Kind.Texture, Kind.Sampler, Kind.Image })
                foreach (int length in new[] { 70, 4096, 5000, 65536 })
                    for (int seed = 1; seed <= 2; seed++)
                    {
                        bool store = kind == Kind.Image && seed == 1;
                        bool resScale = kind != Kind.Sampler && seed == 2;
                        int format = kind != Kind.Sampler && seed == 2 ? 2 : 0;
                        scenarios.Add(Scenario(threaded, kind, store, resScale, length, format, seed * 31 + length, length > 5000 ? 10 : 30));
                    }
        List<object> bufferScenarios = new();
        foreach (bool threaded in new[] { true, false })
            foreach (Kind kind in new[] { Kind.Texture, Kind.Sampler, Kind.Image })
                foreach (int length in new[] { 300, 5000, 8000 })
                    foreach (bool separate in new[] { false, true })
                        bufferScenarios.Add(BufferScenario(threaded, kind, separate, length, 7 * length + (separate ? 1 : 0), 14));
        List<object> mixed = new() { MixedLengths(true), MixedLengths(false) };
        List<object> measures = new();
        foreach (bool threaded in new[] { true, false })
            foreach (Kind kind in new[] { Kind.Texture, Kind.Sampler, Kind.Image })
                measures.Add(Measure(threaded, kind, 65536));
        // Array lengths are an assumption (the device logs give elements per window, not per array): pool-sized arrays of
        // about 200000 (6.2 MiB per compute dispatch as one threaded texture array), 524288 and one over the budget.
        foreach (int length in new[] { 200000, 524288, 1100000 })
            measures.Add(Measure(true, Kind.Texture, length));
        // A dispatch rebuilding three arrays of one element type (three 65536 arrays also make about 6 MiB).
        measures.Add(Measure(true, Kind.Texture, 65536, arrays: 3));
        measures.Add(Measure(true, Kind.Texture, 200000, arrays: 3));
        // Handle arrays read from a constant buffer (UpdateFromBuffer).
        measures.Add(Measure(true, Kind.Texture, 8000, buffer: true));
        measures.Add(Measure(false, Kind.Image, 8000, buffer: true));
        List<object> bursts = new();
        foreach (int drainEvery in new[] { 1, 2, 4, 8, 16, 37 }) bursts.Add(Burst(200, drainEvery));
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            adapted = Adapted, checks = Check.Count, scenarios, bufferScenarios, mixed, measures, bursts,
            gcSettings = new { conserveMemory = AppContext.GetData("System.GC.ConserveMemory")?.ToString(), server = System.Runtime.GCSettings.IsServerGC },
        }));
    }
}

// ---- Boundary doubles. Production cache, producers, commands, pool of snapshots, handles and TableRef are compiled.
namespace Ryujinx.Common
{
    public static class EmbeddedPerformanceDiagnostics
    {
        public enum Work { Draw, Compute, Dma, InlineToMemory, TextureSync, TextureFlush, TextureFlushAction,
            BufferLoad, BufferFlush, PoolSync, ShaderLookup, Bindings, ArrayDelta, Count }
        public enum Counter { ArrayFullElements, ArrayDeltaElements, ArrayDeltaChanged, ArrayBufferElements, Count }
        public static readonly long[] Totals = new long[(int)Counter.Count];
        public static readonly long[] Calls = new long[(int)Work.Count];
        public readonly struct WorkScope : IDisposable { public void Dispose() { } }
        public static WorkScope Track(Work work) { Calls[(int)work]++; return default; }
        public static void Count(Counter counter, long amount = 1) => Totals[(int)counter] += amount;
    }
}

namespace Ryujinx.Graphics.GAL
{
    public interface ITexture { }
    public interface ISampler { }
    public interface IRenderer
    {
        TestPipeline Pipeline { get; }
        ITextureArray CreateTextureArray(int length, bool isBuffer);
        IImageArray CreateImageArray(int length, bool isBuffer);
    }
    public sealed class TestPipeline
    {
        public int Bindings;
        public void SetTextureArray(ShaderStage stage, int binding, ITextureArray array) { Probe.Mark("pipeline binding"); Bindings++; }
        public void SetTextureArraySeparate(ShaderStage stage, int set, ITextureArray array) { Probe.Mark("pipeline binding"); Bindings++; }
        public void SetImageArray(ShaderStage stage, int binding, IImageArray array) { Probe.Mark("pipeline binding"); Bindings++; }
        public void SetImageArraySeparate(ShaderStage stage, int set, IImageArray array) { Probe.Mark("pipeline binding"); Bindings++; }
    }
}

sealed class DirectRenderer : IRenderer
{
    public TestPipeline Pipeline { get; } = new();
    public readonly List<TextureSink> TextureSinks = new();
    public readonly List<ImageSink> ImageSinks = new();
    public ITextureArray CreateTextureArray(int length, bool isBuffer) { TextureSink sink = new(TextureSinks.Count, length); TextureSinks.Add(sink); return sink; }
    public IImageArray CreateImageArray(int length, bool isBuffer) { ImageSink sink = new(100 + ImageSinks.Count, length); ImageSinks.Add(sink); return sink; }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Commands
{
    enum CommandType { TextureArraySetTextures, TextureArraySetSamplers, ImageArraySetImages, TextureArrayDispose, ImageArrayDispose }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Resources
{
    class ThreadedTexture : ITexture { public ITexture Base; }
    class ThreadedSampler : ISampler { public ISampler Base; }
}

namespace Ryujinx.Graphics.GAL.Multithreading
{
    // FIFO transport with preallocated storage (the production renderer has a fixed command ring and reference table),
    // so the transport double allocates nothing on the measured thread once warm.
    unsafe sealed class ThreadedRenderer : IRenderer, IDisposable
    {
        const int Stride = 64;
        const int Capacity = 1 << 17;
        readonly CommandType[] _types = new CommandType[Capacity];
        readonly IntPtr[] _commands = new IntPtr[Capacity];
        readonly object[] _table = new object[Capacity];
        readonly int[] _tableOrder = new int[Capacity];
        int _commandHead, _commandCount, _tableHead, _tableCount, _nextReference;
        IntPtr _reserved;
        CommandType _reservedType;
        public TestPipeline Pipeline { get; } = new();
        public readonly List<TextureSink> TextureSinks = new();
        public readonly List<ImageSink> ImageSinks = new();
        public ITextureArray CreateTextureArray(int length, bool isBuffer)
        { TextureSink sink = new(TextureSinks.Count, length); TextureSinks.Add(sink); return new ThreadedTextureArray(this) { Base = sink }; }
        public IImageArray CreateImageArray(int length, bool isBuffer)
        { ImageSink sink = new(100 + ImageSinks.Count, length); ImageSinks.Add(sink); return new ThreadedImageArray(this) { Base = sink }; }
        public T* New<T>() where T : unmanaged, IGALCommand
        {
            if (_reserved != IntPtr.Zero || sizeof(T) > Stride) throw new InvalidOperationException("one reservation at a time");
            _reservedType = default(T).CommandType;
            Probe.Mark(_reservedType switch
            {
                CommandType.TextureArraySetTextures => "threaded SetTextures command",
                CommandType.TextureArraySetSamplers => "threaded SetSamplers command",
                CommandType.ImageArraySetImages => "threaded SetImages command",
                _ => "threaded other command",
            });
            _reserved = (IntPtr)NativeMemory.AllocZeroed(Stride);
            return (T*)_reserved;
        }
        public void QueueCommand()
        {
            if (_reserved == IntPtr.Zero) throw new InvalidOperationException("no reservation");
            if (_commandCount == Capacity) throw new InvalidOperationException("command ring full");
            int slot = (_commandHead + _commandCount++) % Capacity;
            _types[slot] = _reservedType; _commands[slot] = _reserved; _reserved = IntPtr.Zero;
        }
        public int AddTableRef(object value)
        {
            if (_tableCount == Capacity) throw new InvalidOperationException("reference table full");
            int index = _nextReference++;
            int slot = (_tableHead + _tableCount++) % Capacity;
            _table[slot] = value; _tableOrder[slot] = index;
            return index;
        }
        public object RemoveTableRef(int index)
        {
            if (_tableCount == 0 || _tableOrder[_tableHead] != index) throw new InvalidOperationException("table reference FIFO order");
            object value = _table[_tableHead];
            _table[_tableHead] = null;
            _tableHead = (_tableHead + 1) % Capacity; _tableCount--;
            return value;
        }
        public void Drain()
        {
            while (_commandCount != 0)
            {
                CommandType type = _types[_commandHead];
                void* command = (void*)_commands[_commandHead];
                _commands[_commandHead] = IntPtr.Zero;
                _commandHead = (_commandHead + 1) % Capacity; _commandCount--;
                try
                {
                    switch (type)
                    {
                        case CommandType.TextureArraySetTextures: TextureArraySetTexturesCommand.Run(ref Unsafe.AsRef<TextureArraySetTexturesCommand>(command), this, this); break;
                        case CommandType.TextureArraySetSamplers: TextureArraySetSamplersCommand.Run(ref Unsafe.AsRef<TextureArraySetSamplersCommand>(command), this, this); break;
                        case CommandType.ImageArraySetImages: ImageArraySetImagesCommand.Run(ref Unsafe.AsRef<ImageArraySetImagesCommand>(command), this, this); break;
                        case CommandType.TextureArrayDispose: TextureArrayDisposeCommand.Run(ref Unsafe.AsRef<TextureArrayDisposeCommand>(command), this, this); break;
                        case CommandType.ImageArrayDispose: ImageArrayDisposeCommand.Run(ref Unsafe.AsRef<ImageArrayDisposeCommand>(command), this, this); break;
                        default: throw new InvalidOperationException("unknown command");
                    }
                }
                finally { NativeMemory.Free(command); }
            }
        }
        public void Dispose()
        {
            Drain();
            Check.That(_tableCount == 0, "renderer drained with no table references left");
        }
    }
}

namespace Ryujinx.Graphics.Gpu
{
    sealed class GpuContext
    {
        public IRenderer Renderer;
        public readonly TestCapabilities Capabilities = new();
        public int SequenceNumber;
    }
    sealed class TestCapabilities { public int ExtraSetBaseIndex = 8, MaximumExtraSets = 8; }
    sealed class GpuChannel
    {
        public readonly TestBufferManager BufferManager = new();
        public readonly TestMemoryManager MemoryManager = new();
    }
    static class Constants { public const int TextureHandleSizeInBytes = 8; }
}

namespace Ryujinx.Graphics.Gpu.Memory
{
    readonly record struct TestRange(int Slot);
    // Equatable, as the production BufferBounds: the buffer-entry key compares and hashes it without boxing.
    readonly struct BufferBounds : IEquatable<BufferBounds>
    {
        public BufferBounds(TestRange range) => Range = range;
        public TestRange Range { get; }
        public bool Equals(BufferBounds other) => Range == other.Range;
        public override bool Equals(object obj) => obj is BufferBounds other && Equals(other);
        public override int GetHashCode() => Range.GetHashCode();
    }
    sealed class TestMemoryManager { public readonly TestPhysicalMemory Physical = new(); }
    sealed class TestPhysicalMemory
    {
        // 16384 words: a handle array of up to 8191 elements fits in one buffer.
        public readonly int[][] Buffers = { new int[16384], new int[16384] };
        public ReadOnlySpan<byte> GetSpan(TestRange range) => MemoryMarshal.AsBytes(Buffers[range.Slot].AsSpan());
    }
    sealed class TestBufferManager
    {
        readonly BufferBounds[] _bounds = { new(new TestRange(0)), new(new TestRange(1)) };
        public int StorageBindings;
        public ref BufferBounds GetUniformBufferBounds(bool compute, int stage, int index) => ref _bounds[index];
        public void SetBufferTextureStorage(ShaderStage stage, ITextureArray array, ITexture texture, TestRange range, TextureBindingInfo binding, int index) => StorageBindings++;
        public void SetBufferTextureStorage(ShaderStage stage, IImageArray array, ITexture texture, TestRange range, TextureBindingInfo binding, int index) => StorageBindings++;
    }
}

namespace Ryujinx.Graphics.Gpu.Image
{
    interface IPool<T> { }
    readonly struct FormatInfo
    {
        public readonly int Format;
        public FormatInfo(int format) => Format = format;
        public static FormatInfo Invalid => default;
    }
    readonly record struct TextureDescriptor(int Value);
    readonly record struct SamplerDescriptor(int Value);
    enum TextureScaleMode { Eligible, Blacklisted }

    sealed class Texture
    {
        readonly World _world;
        public ITexture Host;
        public readonly int Key, Format;
        public readonly Texture Parent;
        public readonly List<Texture> Views = new();
        public Target Target = Target.Texture2D;
        public TextureScaleMode ScaleMode;
        public int InvalidatedSequence;
        public TestRange Range;
        public bool Scaled, Disposed, StepSynced, StepSignaled, PendingUpload;
        // Core 745 (adapt_array_sync_epochs): the final cache walks an array's textures only when one was signalled
        // dirty, invalidated or added: the double carries Texture._dirty (a new texture is dirty) and the members the
        // final cache reads. StepSynced records a synchronisation that had something to do.
        public bool Dirty = true;
        internal static int DirtyEpoch, DirtyWriters, InvalidationWriters;
        // IPA 736, second lot (adapt_array_dirty_log): the rings the final cache reads when an epoch moved; the double
        // keeps the textures themselves. A writer appends after its flag (or sequence) and before its epoch.
        internal const int ChangeLogSize = 1024;
        internal static long DirtyLogCount, InvalidationLogCount;
        static readonly Texture[] DirtyRing = new Texture[ChangeLogSize], InvalidationRing = new Texture[ChangeLogSize];
        internal static void LogDirty(Texture texture) { long i = System.Threading.Interlocked.Increment(ref DirtyLogCount) - 1; DirtyRing[i & (ChangeLogSize - 1)] = texture; }
        internal static void LogInvalidation(Texture texture) { long i = System.Threading.Interlocked.Increment(ref InvalidationLogCount) - 1; InvalidationRing[i & (ChangeLogSize - 1)] = texture; }
        internal static bool TryReadDirtyLog(long index, out Texture texture) { texture = DirtyRing[index & (ChangeLogSize - 1)]; return texture != null; }
        internal static bool TryReadInvalidationLog(long index, out Texture texture) { texture = InvalidationRing[index & (ChangeLogSize - 1)]; return texture != null; }
        internal int ContextUseEpoch => 0; // no use clock in this fixture
        public void SignalGroupDirty()
        {
            System.Threading.Interlocked.Increment(ref DirtyWriters);
            Dirty = true;
            LogDirty(this);
            System.Threading.Interlocked.Increment(ref DirtyEpoch);
            System.Threading.Interlocked.Decrement(ref DirtyWriters);
        }
        public string Name => World.Describe(Host);
        public string SignalName => Parent == null ? "t" + Key : "a" + Key + "." + Format;
        public Texture(World world, ITexture host, int key, int format, Texture parent)
        {
            _world = world; Host = host; Key = key; Format = format; Parent = parent;
            if (parent != null) { parent.Views.Add(this); ScaleMode = parent.ScaleMode; }
        }
        void Use() { if (Disposed) _world.Violations++; }
        internal static int InvalidationEpoch;
        public void Invalidate() { InvalidatedSequence++; LogInvalidation(this); System.Threading.Interlocked.Increment(ref InvalidationEpoch); }
        public ITexture GetTargetTexture(Target target) { Use(); return Host; }
        public void SynchronizeMemory()
        {
            Use();
            if (Target == Target.TextureBuffer || !Dirty) return;
            Dirty = false;
            StepSynced = true;
            if (PendingUpload)
            {
                PendingUpload = false;
                if (Scaled) BlacklistScale();
            }
        }
        public void SignalModified() { Use(); StepSignaled = true; }
        void ReplaceStorage()
        {
            _world.Release(Host);
            Host = _world.NewHost(Name + "'");
            Invalidate();
            foreach (Texture view in Views) view.ReplaceStorage();
        }
        public void ScaleUp()
        {
            if (Disposed || Parent != null || ScaleMode != TextureScaleMode.Eligible || Scaled) return;
            Scaled = true;
            ReplaceStorage();
        }
        public void BlacklistScale()
        {
            Use();
            ScaleMode = TextureScaleMode.Blacklisted;
            if (Parent != null)
            {
                if (!Parent.Disposed) Parent.BlacklistScale();
                return;
            }
            foreach (Texture view in Views) view.ScaleMode = TextureScaleMode.Blacklisted;
            if (Scaled)
            {
                Scaled = false;
                ReplaceStorage();
            }
        }
        public void Dispose()
        {
            if (Disposed) return;
            Disposed = true;
            _world.Release(Host);
            Invalidate();
            Parent?.Views.Remove(this);
        }
        public void ResetStep() { StepSynced = false; StepSignaled = false; }
    }

    sealed class Sampler
    {
        public readonly ISampler Host;
        public readonly int Key;
        public bool IsDisposed { get; private set; }
        public Sampler(ISampler host, int key) { Host = host; Key = key; }
        public ISampler GetHostSampler(Texture texture) => Host;
        public void Dispose() => IsDisposed = true;
    }

    class TexturePool : IPool<Texture>
    {
        readonly World _world;
        public readonly Texture[] Items;
        public readonly int[] Keys;
        readonly bool[] _invalid;
        readonly TextureDescriptor[] _descriptors;
        readonly Dictionary<Texture, Dictionary<int, Texture>> _aliasLists = new();
        readonly List<Texture> _orphans = new();
        int _aliasGeneration;
        public int MaximumId, Sequence = 1, ThrowAt = -1;
        public long Lookups, Peeks;
        public TexturePool(World world, int length)
        {
            _world = world; Items = new Texture[length]; Keys = new int[length]; _invalid = new bool[length];
            _descriptors = new TextureDescriptor[length]; MaximumId = length - 1;
        }
        public bool WasModified(ref int sequence) { bool changed = Sequence != sequence; sequence = Sequence; return changed; }
        public void Touch() => Sequence++;
        public void Write(int id, int key)
        {
            Sequence++;
            if (Keys[id] == key && Items[id] != null) return;
            if (Items[id] != null) RemoveAliasList(Items[id], disposeNow: false);
            if (Items[id] != null || _invalid[id]) LogDeltaChange(id);
            Keys[id] = key; Items[id] = null; _invalid[id] = false;
        }
        public void ForceRemove(Texture texture)
        {
            for (int id = 0; id < Items.Length; id++)
            {
                if (Items[id] != texture) continue;
                Items[id] = null;
                LogDeltaChange(id);
            }
            RemoveAliasList(texture, disposeNow: false);
        }
        public void RemoveAliasList(Texture texture, bool disposeNow)
        {
            if (!_aliasLists.Remove(texture, out Dictionary<int, Texture> list)) return;
            _aliasGeneration++;
            foreach (Texture alias in list.Values)
            {
                if (disposeNow) alias.Dispose(); else _orphans.Add(alias);
            }
        }
        public void DisposeOrphanAliases()
        {
            foreach (Texture alias in _orphans) alias.Dispose();
            _orphans.Clear();
        }
        public ref readonly TextureDescriptor GetForBinding(int id, FormatInfo formatInfo, out Texture texture)
        {
            Probe.Lookup();
            Lookups++;
            if (id == ThrowAt) throw new TestFailure();
            texture = Items[id];
            if (texture == null)
            {
                if (_invalid[id]) return ref _descriptors[id];
                if (Keys[id] == 0) { _invalid[id] = true; return ref _descriptors[id]; }
                texture = _world.Library[Keys[id]];
                Items[id] = texture;
            }
            texture.SynchronizeMemory();
            if (formatInfo.Format != 0 && texture.Format != formatInfo.Format)
            {
                if (!_aliasLists.TryGetValue(texture, out Dictionary<int, Texture> list)) _aliasLists[texture] = list = new();
                if (!list.TryGetValue(formatInfo.Format, out Texture alias))
                {
                    list[formatInfo.Format] = alias = _world.NewTexture(texture.Key, formatInfo.Format, texture);
                }
                texture = alias;
            }
            return ref _descriptors[id];
        }
        internal Texture PeekForBindingDelta(int id, out bool knownInvalid)
        {
            Peeks++;
            Texture texture = Items[id];
            knownInvalid = texture == null && _invalid[id];
            return texture;
        }
        internal int AliasGeneration => _aliasGeneration;
        internal const int DeltaLogCapacity = 4096;
        readonly int[] _deltaLog = new int[DeltaLogCapacity];
        long _deltaLogCount;
        internal long DeltaLogCount => _deltaLogCount;
        void LogDeltaChange(int id) { _deltaLog[(int)(_deltaLogCount % DeltaLogCapacity)] = id; _deltaLogCount++; }
        internal bool CopyDeltaLog(long since, long until, int[] destination, out int count)
        {
            count = 0;
            if (since > until || until > _deltaLogCount || _deltaLogCount - since > DeltaLogCapacity) return false;
            for (long position = since; position < until; position++) destination[count++] = _deltaLog[(int)(position % DeltaLogCapacity)];
            return true;
        }
        public Texture GetCachedItem(int id) => id >= 0 && id < Items.Length ? Items[id] : null;
        public bool IsValidId(int id) => id >= 0 && id <= MaximumId;
        public ref readonly TextureDescriptor GetDescriptorRef(int id) => ref _descriptors[id];
    }

    class SamplerPool : IPool<Sampler>
    {
        readonly World _world;
        public readonly Sampler[] Items;
        public readonly int[] Keys;
        readonly SamplerDescriptor[] _descriptors;
        public int MaximumId, Sequence = 1, ThrowAt = -1;
        public long Lookups;
        public SamplerPool(World world, int length)
        {
            _world = world; Items = new Sampler[length]; Keys = new int[length];
            _descriptors = new SamplerDescriptor[length]; MaximumId = length - 1;
        }
        public bool WasModified(ref int sequence) { bool changed = Sequence != sequence; sequence = Sequence; return changed; }
        public void Touch() => Sequence++;
        public void Write(int id, int key)
        {
            Sequence++;
            if (Keys[id] == key && Items[id] != null) return;
            Keys[id] = key; Items[id]?.Dispose(); Items[id] = null;
        }
        public Sampler Get(int id)
        {
            Probe.Lookup();
            Lookups++;
            if (id == ThrowAt) throw new TestFailure();
            if (Items[id] == null)
            {
                Sampler template = _world.SamplerLibrary[Keys[id]];
                Items[id] = new Sampler(template.Host, template.Key);
            }
            return Items[id];
        }
        public Sampler GetCachedItem(int id) => id >= 0 && id < Items.Length ? Items[id] : null;
        public bool IsValidId(int id) => id >= 0 && id <= MaximumId;
        public ref readonly SamplerDescriptor GetDescriptorRef(int id) => ref _descriptors[id];
    }
}
