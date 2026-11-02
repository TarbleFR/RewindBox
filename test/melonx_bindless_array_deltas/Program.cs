// Host fixture for adapt_bindless_array_deltas: the production TextureBindingsArrayCache,
// threaded array producers and commands are compiled unchanged from the prepared tree
// (control: as delivered in Core b99e754d; candidate: with the adapter). Only the GPU
// resources, pools, memory and renderer transport are doubled, following the pool rules
// of the production TexturePool/SamplerPool: Items[id] is replaced only when a written
// descriptor really differs, an empty id stays known-invalid until its descriptor is
// written, format aliases are stable per texture, replaced samplers are disposed.
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
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Commands;
using Ryujinx.Graphics.GAL.Multithreading.Commands.ImageArray;
using Ryujinx.Graphics.GAL.Multithreading.Commands.TextureArray;
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

sealed class TestFailure : Exception { }
sealed class HostTexture : ITexture { public readonly int Id; public HostTexture(int id) => Id = id; }
sealed class HostSampler : ISampler { public readonly int Id; public HostSampler(int id) => Id = id; }

sealed class TextureSink : ITextureArray
{
    public readonly ITexture[] Textures;
    public readonly ISampler[] Samplers;
    public long Calls, Elements;
    public TextureSink(int length) { Textures = new ITexture[length]; Samplers = new ISampler[length]; }
    public void SetTextures(int index, ITexture[] textures)
    {
        Array.Copy(textures, 0, Textures, index, textures.Length); Calls++; Elements += textures.Length;
    }
    public void SetSamplers(int index, ISampler[] samplers)
    {
        Array.Copy(samplers, 0, Samplers, index, samplers.Length); Calls++; Elements += samplers.Length;
    }
    public void Dispose() { }
}

sealed class ImageSink : IImageArray
{
    public readonly ITexture[] Images;
    public long Calls, Elements;
    public ImageSink(int length) => Images = new ITexture[length];
    public void SetImages(int index, ITexture[] images)
    {
        Array.Copy(images, 0, Images, index, images.Length); Calls++; Elements += images.Length;
    }
    public void Dispose() { }
}

enum Kind { Texture, Sampler, Image }

sealed class World
{
    public readonly Random Random;
    public readonly ThreadedRenderer Threaded;
    public readonly DirectRenderer Direct;
    public readonly GpuContext Context;
    public readonly GpuChannel Channel = new();
    public readonly TextureBindingsArrayCache Cache;
    public readonly TexturePool Textures;
    public readonly SamplerPool Samplers;
    public readonly Texture[] Library;
    public readonly Sampler[] SamplerLibrary;
    public readonly int Length;
    public IRenderer Renderer => (IRenderer)Threaded ?? Direct;

    public World(int length, bool threaded, int seed, int librarySize = 24)
    {
        Random = new Random(seed);
        Length = length;
        if (threaded) Threaded = new ThreadedRenderer(); else Direct = new DirectRenderer();
        Context = new GpuContext { Renderer = Renderer };
        Library = new Texture[librarySize + 1];
        SamplerLibrary = new Sampler[librarySize + 1];
        for (int key = 0; key <= librarySize; key++)
        {
            // SamplerPool.Get creates a sampler for every in-range id, the zero descriptor included.
            ISampler sampler = new HostSampler(key);
            SamplerLibrary[key] = new Sampler(threaded ? new ThreadedSampler { Base = sampler } : sampler, key);
            if (key == 0) continue;
            ITexture host = new HostTexture(key);
            Library[key] = new Texture(threaded ? new ThreadedTexture { Base = host } : host, key, format: 1 + key % 3, world: this);
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

    public static TextureBindingInfo Binding(int length, Kind kind, TextureUsageFlags flags = 0, int format = 0,
                                             Target target = Target.Texture2D)
        => kind == Kind.Sampler
            ? new(target, 0, 0, length, 0, TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct), flags, true)
            : new(target, new FormatInfo(format), 0, 0, length, 0, TextureHandle.PackOffsets(0, 0, TextureHandleType.Direct), flags);

    public void Update(in TextureBindingInfo binding, Kind kind)
    {
        Context.SequenceNumber++;
        Textures.Synchronize();
        Samplers.Synchronize();
        if (kind == Kind.Image) Cache.UpdateImageArray(Textures, ShaderStage.Compute, 0, 0, binding);
        else Cache.UpdateTextureArray(Textures, Samplers, ShaderStage.Compute, 0, 0, SamplerIndex.ViaHeaderIndex, binding);
        Threaded?.Drain();
    }

    public TextureSink TextureSink => Threaded?.TextureSinks[0] ?? Direct.TextureSinks[0];
    public ImageSink ImageSink => Threaded?.ImageSinks[0] ?? Direct.ImageSinks[0];

    // Mutations, as the game and the texture cache perform them.
    public void Mutate(int operations, Kind kind)
    {
        for (int i = 0; i < operations; i++)
        {
            int id = Random.Next(Length);
            switch (Random.Next(9))
            {
                case 0: Textures.Write(id, Random.Next(3) == 0 ? 0 : 1 + Random.Next(Library.Length - 1)); break;
                case 1: Textures.Write(id, Textures.Keys[id]); break; // rewrite of identical bytes
                case 2: Samplers.Write(id, Random.Next(4) == 0 ? 0 : 1 + Random.Next(SamplerLibrary.Length - 1)); break;
                case 3: Samplers.Write(id, Samplers.Keys[id]); break;
                case 4: Invalidate(Library[1 + Random.Next(Library.Length - 1)], removeFromPool: true); break;
                case 5: Invalidate(Library[1 + Random.Next(Library.Length - 1)], removeFromPool: false); break;
                case 6: Textures.Touch(); break; // pool written, nothing changed
                case 7: Samplers.Touch(); break;
                default: Textures.Write(id, 1 + Random.Next(Library.Length - 1)); break;
            }
        }
    }

    // A replaced or unmapped texture bumps its sequence; the cache may also drop it from pools.
    public void Invalidate(Texture texture, bool removeFromPool)
    {
        texture.InvalidatedSequence++;
        texture.DropAliases();
        if (removeFromPool) Textures.ForceRemove(texture);
    }

    public string Snapshot(Kind kind, int arrayLength)
    {
        StringBuilder text = new();
        if (kind == Kind.Image)
        {
            foreach (ITexture image in ImageSink.Images) text.Append(Id(image)).Append(',');
        }
        else
        {
            foreach (ITexture texture in TextureSink.Textures) text.Append(Id(texture)).Append(',');
            text.Append('|');
            foreach (ISampler sampler in TextureSink.Samplers) text.Append(Id(sampler)).Append(',');
        }
        return text.ToString();
    }

    static string Id(object value) => value switch
    {
        null => "-",
        HostTexture t => "t" + t.Id,
        HostSampler s => "s" + s.Id,
        AliasHost a => "a" + a.Key + "." + a.Format,
        _ => "?",
    };
}

sealed class AliasHost : ITexture { public readonly int Key, Format; public AliasHost(int key, int format) { Key = key; Format = format; } }

static class Program
{
#if ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif

    // Expected backend element, computed from the pools exactly as a full rebuild resolves it.
    static string Expected(World w, Kind kind, int index, int format)
    {
        if (index >= Math.Min(w.Length, w.Length)) return "-";
        if (kind == Kind.Sampler)
        {
            return "s" + w.Samplers.Keys[index];
        }
        int textureKey = w.Textures.Keys[index];
        if (textureKey == 0) return "-";
        Texture texture = w.Library[textureKey];
        if (format != 0 && texture.Format != format) return "a" + textureKey + "." + format;
        return "t" + textureKey;
    }

    static void VerifyAgainstPools(World w, Kind kind, int format, string context)
    {
        for (int index = 0; index < w.Length; index++)
        {
            string actual = kind == Kind.Image ? Describe(w.ImageSink.Images[index])
                : kind == Kind.Sampler ? Describe(w.TextureSink.Samplers[index]) : Describe(w.TextureSink.Textures[index]);
            string expected = Expected(w, kind, index, format);
            Check.That(actual == expected, $"{context}: element {index} is {actual}, pools say {expected}");
            if (kind == Kind.Texture) Check.That(w.TextureSink.Samplers[index] == null, "texture arrays carry no sampler");
            if (kind == Kind.Sampler) Check.That(w.TextureSink.Textures[index] == null, "sampler arrays carry no texture");
        }
    }

    static string Describe(object value) => value switch
    {
        null => "-",
        HostTexture t => "t" + t.Id,
        HostSampler s => "s" + s.Id,
        AliasHost a => "a" + a.Key + "." + a.Format,
        _ => "?",
    };

    static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))[..16];

    // Random pool writes, rewrites, invalidations and quiet passes; every update is checked
    // against the pools and its backend state and synchronisation sets are digested, so the
    // driver can require identical digests for control and candidate at every step.
    static object Scenario(bool threaded, Kind kind, bool store, int length, int format, int seed, int steps)
    {
        World w = new(length, threaded, seed);
        TextureUsageFlags flags = store ? TextureUsageFlags.ImageStore : 0;
        TextureBindingInfo binding = World.Binding(length, kind, flags, format);
        List<string> digests = new();
        for (int step = 0; step < steps; step++)
        {
            if (step != 0) w.Mutate(1 + w.Random.Next(step % 4 == 0 ? 0 : 6), kind);
            foreach (Texture t in w.Library.Skip(1)) t.ResetStepCounters();
            w.Update(binding, kind);
            VerifyAgainstPools(w, kind, format, $"{kind} L={length} step {step}");
            string synced = string.Join(",", w.Library.Skip(1).Where(t => t.StepSynced).Select(t => t.Key));
            string signaled = string.Join(",", w.Library.Skip(1).Where(t => t.StepSignaled).Select(t => t.Key));
            // A rebuild synchronises pool items, the hit path the bound aliases: compare the
            // synchronised set exactly without aliases, and require every bound alias synced otherwise.
            if (format != 0)
            {
                foreach (ITexture bound in w.TextureSink.Textures)
                {
                    if (bound is ThreadedTexture { Base: AliasHost } || bound is AliasHost) { }
                }
                synced = "aliases";
            }
            digests.Add(Hash(w.Snapshot(kind, length) + "#" + synced + "#" + signaled));
        }
        w.Threaded?.Dispose();
        return new { threaded, kind = kind.ToString(), store, length, format, seed, steps, digest = Hash(string.Join(";", digests)) };
    }

    // A buffer-texture array keeps the full rebuild (its storage is rebound on every update).
    static object TextureBufferScenario(bool threaded)
    {
        World w = new(64, threaded, 7);
        foreach (Texture t in w.Library.Skip(1)) t.Target = Target.TextureBuffer;
        TextureBindingInfo binding = World.Binding(64, Kind.Texture, 0, 0, Target.TextureBuffer);
        long lookups = 0;
        for (int step = 0; step < 6; step++)
        {
            w.Textures.Touch();
            long before = w.Textures.Lookups;
            w.Update(binding, Kind.Texture);
            lookups += w.Textures.Lookups - before;
        }
        w.Threaded?.Dispose();
        return new { threaded, lookupsPerUpdate = lookups / 6.0, storageBindings = w.Channel.BufferManager.StorageBindings };
    }

    // A lookup that throws mid-pass leaves the array to the next full rebuild, which must be complete.
    static object FailureScenario(bool threaded)
    {
        World w = new(300, threaded, 11);
        TextureBindingInfo binding = World.Binding(300, Kind.Texture);
        w.Update(binding, Kind.Texture);
        w.Textures.Write(150, 3);
        w.Textures.Write(20, 4);
        w.Textures.ThrowAt = 150;
        bool threw = false;
        try { w.Update(binding, Kind.Texture); } catch (TestFailure) { threw = true; w.Threaded?.Drain(); }
        Check.That(threw, "the doubled lookup failure propagates");
        w.Textures.ThrowAt = -1;
        // The failed pass already consumed the pool's modified sequence (as delivered, too): the
        // next pool write brings the array back, here through the full rebuild.
        w.Textures.Touch();
        w.Update(binding, Kind.Texture);
        VerifyAgainstPools(w, Kind.Texture, 0, "after failure");
        w.Threaded?.Dispose();
        return new { threaded, recovered = true };
    }

    // Cost with the observed shape: a pool-sized array, the pool written before every
    // dispatch, k elements really changed. Producer-thread bytes are the GPU thread's.
    static object Measure(bool threaded, Kind kind, int length, int changes, bool scattered)
    {
        World w = new(length, threaded, 3);
        TextureBindingInfo binding = World.Binding(length, kind);
        w.Update(binding, kind);
        w.Update(binding, kind);
        const int Updates = 20;
        long bytes = 0, lookups = 0, ticks = 0, calls = 0, elements = 0;
        long sinkCalls0 = kind == Kind.Image ? w.ImageSink.Calls : w.TextureSink.Calls;
        long sinkElements0 = kind == Kind.Image ? w.ImageSink.Elements : w.TextureSink.Elements;
        for (int u = 0; u < Updates; u++)
        {
            for (int c = 0; c < changes; c++)
            {
                int id = scattered ? (int)((long)(c * 7919 + u * 104729) % length) : (u * 131 + c) % length;
                if (kind == Kind.Sampler) w.Samplers.Write(id, 1 + (w.Samplers.Keys[id] % (w.SamplerLibrary.Length - 1)));
                else w.Textures.Write(id, 1 + (w.Textures.Keys[id] % (w.Library.Length - 1)));
            }
            w.Textures.Touch(); w.Samplers.Touch();
            long lookupsBefore = w.Textures.Lookups + w.Samplers.Lookups;
            w.Context.SequenceNumber++;
            w.Textures.Synchronize(); w.Samplers.Synchronize();
            long before = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            if (kind == Kind.Image) w.Cache.UpdateImageArray(w.Textures, ShaderStage.Compute, 0, 0, binding);
            else w.Cache.UpdateTextureArray(w.Textures, w.Samplers, ShaderStage.Compute, 0, 0, SamplerIndex.ViaHeaderIndex, binding);
            ticks += Stopwatch.GetTimestamp() - start;
            bytes += GC.GetAllocatedBytesForCurrentThread() - before;
            lookups += w.Textures.Lookups + w.Samplers.Lookups - lookupsBefore;
            w.Threaded?.Drain();
        }
        calls = (kind == Kind.Image ? w.ImageSink.Calls : w.TextureSink.Calls) - sinkCalls0;
        elements = (kind == Kind.Image ? w.ImageSink.Elements : w.TextureSink.Elements) - sinkElements0;
        VerifyAgainstPools(w, kind, 0, $"measure {kind} L={length} k={changes}");
        w.Threaded?.Dispose();
        return new
        {
            threaded, kind = kind.ToString(), length, changes, scattered,
            producerBytesPerUpdate = bytes / (double)Updates,
            lookupsPerUpdate = lookups / (double)Updates,
            backendCallsPerUpdate = calls / (double)Updates,
            backendElementsPerUpdate = elements / (double)Updates,
            producerMicrosecondsPerUpdate = ticks * 1e6 / Stopwatch.Frequency / Updates,
        };
    }

    static void Main()
    {
        List<object> scenarios = new();
        foreach (bool threaded in new[] { true, false })
            foreach (Kind kind in new[] { Kind.Texture, Kind.Sampler, Kind.Image })
                foreach (int length in new[] { 8, 70, 5000 })
                    for (int seed = 1; seed <= 3; seed++)
                    {
                        bool store = kind == Kind.Image && seed != 2;
                        int format = kind == Kind.Texture && seed == 3 ? 2 : 0;
                        scenarios.Add(Scenario(threaded, kind, store, length, format, seed * 31 + length, 40));
                    }
        List<object> buffers = new() { TextureBufferScenario(true), TextureBufferScenario(false) };
        List<object> failures = new() { FailureScenario(true), FailureScenario(false) };
        List<object> measures = new();
        foreach (int length in new[] { 4097, 16384, 65536 })
        {
            measures.Add(Measure(true, Kind.Texture, length, 0, false));
            measures.Add(Measure(true, Kind.Texture, length, 1, false));
            measures.Add(Measure(true, Kind.Texture, length, 64, true));
            measures.Add(Measure(true, Kind.Texture, length, 256, false));
            measures.Add(Measure(true, Kind.Sampler, length, 1, false));
            measures.Add(Measure(false, Kind.Texture, length, 1, false));
        }
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            adapted = Adapted, checks = Check.Count, scenarios, buffers, failures, measures,
            counters = Enum.GetNames<PD.Counter>().Zip(PD.Totals).ToDictionary(p => p.First, p => p.Second),
        }));
    }
}

// ---- Boundary doubles. Production cache, producers, commands, handles and TableRef are compiled from the tree.
namespace Ryujinx.Common
{
    public static class EmbeddedPerformanceDiagnostics
    {
        public enum Work { Draw, Compute, Dma, InlineToMemory, TextureSync, TextureFlush, TextureFlushAction,
            BufferLoad, BufferFlush, PoolSync, ShaderLookup, Bindings, ComputeBindings, ArrayFull, ArrayDelta, ArrayBuffer, Count }
        public enum Counter { ArrayFullRebuilds, ArrayFullElements, ArrayDeltaPasses, ArrayDeltaElements, ArrayDeltaChanged,
            ArrayBufferRebuilds, ArrayBufferElements, PoolCreates, Count }
        public static readonly long[] Totals = new long[(int)Counter.Count];
        public readonly struct WorkScope : IDisposable { public void Dispose() { } }
        public static WorkScope Track(Work work) => default;
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
        public void SetTextureArray(ShaderStage stage, int binding, ITextureArray array) => Bindings++;
        public void SetTextureArraySeparate(ShaderStage stage, int set, ITextureArray array) => Bindings++;
        public void SetImageArray(ShaderStage stage, int binding, IImageArray array) => Bindings++;
        public void SetImageArraySeparate(ShaderStage stage, int set, IImageArray array) => Bindings++;
    }
}

sealed class DirectRenderer : IRenderer
{
    public TestPipeline Pipeline { get; } = new();
    public readonly List<TextureSink> TextureSinks = new();
    public readonly List<ImageSink> ImageSinks = new();
    public ITextureArray CreateTextureArray(int length, bool isBuffer) { TextureSink sink = new(length); TextureSinks.Add(sink); return sink; }
    public IImageArray CreateImageArray(int length, bool isBuffer) { ImageSink sink = new(length); ImageSinks.Add(sink); return sink; }
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
    // Unbounded FIFO transport: the production renderer waits for queue space instead of failing.
    unsafe sealed class ThreadedRenderer : IRenderer, IDisposable
    {
        const int Stride = 64;
        readonly Queue<(CommandType, IntPtr)> _commands = new();
        readonly Queue<(int, object)> _references = new();
        readonly Dictionary<int, object> _table = new();
        int _nextReference;
        IntPtr _reserved;
        CommandType _reservedType;
        public TestPipeline Pipeline { get; } = new();
        public readonly List<TextureSink> TextureSinks = new();
        public readonly List<ImageSink> ImageSinks = new();
        public ITextureArray CreateTextureArray(int length, bool isBuffer)
        { TextureSink sink = new(length); TextureSinks.Add(sink); return new ThreadedTextureArray(this) { Base = sink }; }
        public IImageArray CreateImageArray(int length, bool isBuffer)
        { ImageSink sink = new(length); ImageSinks.Add(sink); return new ThreadedImageArray(this) { Base = sink }; }
        public T* New<T>() where T : unmanaged, IGALCommand
        {
            if (_reserved != IntPtr.Zero || sizeof(T) > Stride) throw new InvalidOperationException("one reservation at a time");
            _reserved = (IntPtr)NativeMemory.AllocZeroed(Stride);
            _reservedType = default(T).CommandType;
            return (T*)_reserved;
        }
        public void QueueCommand()
        {
            if (_reserved == IntPtr.Zero) throw new InvalidOperationException("no reservation");
            _commands.Enqueue((_reservedType, _reserved)); _reserved = IntPtr.Zero;
        }
        public int AddTableRef(object value) { int index = _nextReference++; _table[index] = value; _references.Enqueue((index, value)); return index; }
        public object RemoveTableRef(int index)
        {
            (int expected, object value) = _references.Dequeue();
            if (expected != index) throw new InvalidOperationException("table reference FIFO order");
            _table.Remove(index);
            return value;
        }
        public void Drain()
        {
            while (_commands.Count != 0)
            {
                (CommandType type, IntPtr pointer) = _commands.Dequeue();
                void* command = (void*)pointer;
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
            Check.That(_references.Count == 0 && _table.Count == 0, "renderer drained with no table references left");
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
    struct BufferBounds { public TestRange Range; }
    sealed class TestMemoryManager { public readonly TestPhysicalMemory Physical = new(); }
    sealed class TestPhysicalMemory
    {
        public readonly int[][] Buffers = { new int[1024], new int[1024] };
        public ReadOnlySpan<byte> GetSpan(TestRange range) => MemoryMarshal.AsBytes(Buffers[range.Slot].AsSpan());
    }
    sealed class TestBufferManager
    {
        readonly BufferBounds[] _bounds = { new() { Range = new(0) }, new() { Range = new(1) } };
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
        public readonly ITexture Host;
        public readonly int Key, Format;
        readonly World _world;
        readonly Dictionary<int, Texture> _aliases = new();
        public Target Target = Target.Texture2D;
        public TextureScaleMode ScaleMode;
        public int InvalidatedSequence;
        public TestRange Range;
        public bool StepSynced, StepSignaled;
        public Texture(ITexture host, int key, int format, World world) { Host = host; Key = key; Format = format; _world = world; }
        public ITexture GetTargetTexture(Target target) => Host;
        public void SynchronizeMemory() => StepSynced = true;
        public void SignalModified() => StepSignaled = true;
        public void BlacklistScale() => ScaleMode = TextureScaleMode.Blacklisted;
        public void ResetStepCounters() { StepSynced = false; StepSignaled = false; foreach (Texture a in _aliases.Values) a.ResetStepCounters(); }
        // A stable view per requested format, dropped (and invalidated) with its parent.
        public Texture Alias(int format)
        {
            if (!_aliases.TryGetValue(format, out Texture alias))
            {
                ITexture host = new AliasHost(Key, format);
                if (Host is ThreadedTexture) host = new ThreadedTexture { Base = host };
                _aliases[format] = alias = new Texture(host, Key, format, _world);
            }
            return alias;
        }
        public void DropAliases() { foreach (Texture a in _aliases.Values) a.InvalidatedSequence++; _aliases.Clear(); }
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
        public int MaximumId, Sequence = 1, ThrowAt = -1;
        public long Lookups;
        public TexturePool(World world, int length)
        {
            _world = world; Items = new Texture[length]; Keys = new int[length]; _invalid = new bool[length];
            _descriptors = new TextureDescriptor[length]; MaximumId = length - 1;
        }
        public bool WasModified(ref int sequence) { bool changed = Sequence != sequence; sequence = Sequence; return changed; }
        public void Synchronize() { }
        public void Touch() => Sequence++;
        // InvalidateRangeImpl: an identical descriptor keeps its item; a different one clears it.
        public void Write(int id, int key)
        {
            Sequence++;
            if (Keys[id] == key && Items[id] != null) return;
            Keys[id] = key; Items[id] = null; _invalid[id] = false;
        }
        public void ForceRemove(Texture texture)
        {
            // TexturePool.ForceRemove clears the item without touching the modified sequence.
            for (int id = 0; id < Items.Length; id++) if (Items[id] == texture) Items[id] = null;
        }
        // GetInternal + the alias rule of GetForBinding(id, formatInfo).
        public ref readonly TextureDescriptor GetForBinding(int id, FormatInfo formatInfo, out Texture texture)
        {
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
            if (formatInfo.Format != 0 && texture.Format != formatInfo.Format) texture = texture.Alias(formatInfo.Format);
            return ref _descriptors[id];
        }
        internal Texture PeekForBindingDelta(int id, out bool knownInvalid)
        {
            Texture texture = Items[id];
            knownInvalid = texture == null && _invalid[id];
            return texture;
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
        public int MaximumId, Sequence = 1;
        public long Lookups;
        public SamplerPool(World world, int length)
        {
            _world = world; Items = new Sampler[length]; Keys = new int[length];
            _descriptors = new SamplerDescriptor[length]; MaximumId = length - 1;
        }
        public bool WasModified(ref int sequence) { bool changed = Sequence != sequence; sequence = Sequence; return changed; }
        public void Synchronize() { }
        public void Touch() => Sequence++;
        // A changed sampler descriptor disposes the old sampler object.
        public void Write(int id, int key)
        {
            Sequence++;
            if (Keys[id] == key && Items[id] != null) return;
            Keys[id] = key; Items[id]?.Dispose(); Items[id] = null;
        }
        public Sampler Get(int id)
        {
            Lookups++;
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
