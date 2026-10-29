using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Engine.Types;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.Graphics.Shader;
using Ryujinx.Memory.Range;

static class BindingLookupProgram
{
#if LOOKUP_ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif
    sealed class CountingComparer<T> : IEqualityComparer<T>
    {
        public long Comparisons;
        public bool Equals(T left, T right) { Comparisons++; return EqualityComparer<T>.Default.Equals(left, right); }
        public int GetHashCode(T key) => EqualityComparer<T>.Default.GetHashCode(key);
    }

    static TextureBindingInfo Binding(int handle, int length = 1, Target target = Target.Texture2D, bool sampler = false)
        => new(target, 0, 0, length, 0, handle, TextureUsageFlags.None, sampler);

    static object Key(Type type, TextureBindingInfo binding, TexturePool textures, SamplerPool samplers,
                      bool image, BufferBounds? bounds)
    {
        object[] arguments = bounds.HasValue
            ? new object[] { image, binding, textures, samplers, bounds.Value }
            : new object[] { image, binding, textures, samplers };
        return type.GetConstructors().Single().Invoke(arguments);
    }

    static object CollisionCase<T>(string kind, object[] boxed, object[] equivalent)
    {
        T[] keys = boxed.Cast<T>().ToArray();
        T[] copies = equivalent.Cast<T>().ToArray();
        CountingComparer<T> comparer = new();
        Dictionary<T, int> dictionary = new(keys.Length, comparer);
        for (int i = 0; i < keys.Length; i++)
        {
            Check.That(EqualityComparer<T>.Default.Equals(keys[i], copies[i]), "equal production keys");
            Check.That(comparer.GetHashCode(keys[i]) == comparer.GetHashCode(copies[i]), "equal keys have equal hashes");
            dictionary.Add(keys[i], i);
        }
        comparer.Comparisons = 0;
        for (int pass = 0; pass < 8; pass++)
        {
            for (int i = 0; i < keys.Length; i++)
                Check.That(dictionary.TryGetValue(copies[i], out int value) && value == i, "exact dictionary lookup");
        }
        double comparisons = comparer.Comparisons / (8.0 * keys.Length);
        int distinctHashes = keys.Select(k => comparer.GetHashCode(k)).Distinct().Count();
        // Removal and reinsertion exercise the same keys used by production eviction.
        for (int i = 0; i < keys.Length; i += 2) Check.That(dictionary.Remove(copies[i]), "exact key removal");
        for (int i = 0; i < keys.Length; i += 2) dictionary.Add(keys[i], i);
        for (int i = 0; i < keys.Length; i++) Check.That(dictionary[copies[i]] == i, "reinsertion preserves mapping");
        return new { kind, count = keys.Length, comparisonsPerHit = comparisons, distinctHashes };
    }

    static object BuildCollisionCase(string kind, int count)
    {
        bool buffer = kind == "buffer";
        Type type = typeof(TextureBindingsArrayCache).GetNestedType(buffer ? "CacheEntryFromBufferKey" : "CacheEntryFromPoolKey", BindingFlags.NonPublic);
        TexturePool textures = new(1); SamplerPool samplers = new(1);
        object[] keys = new object[count], copies = new object[count];
        for (int i = 0; i < count; i++)
        {
            TextureBindingInfo binding = Binding(buffer ? i * 2 : 0, buffer ? 1 : i + 1);
            BufferBounds? bounds = buffer ? new BufferBounds(new MultiRange(0x10000, 8192)) : null;
            keys[i] = Key(type, binding, textures, samplers, false, bounds);
            // Equal ranges reconstructed independently, rather than the same boxed key.
            BufferBounds? sameBounds = buffer ? new BufferBounds(new MultiRange(new[] { new MemoryRange(0x10000, 8192) })) : null;
            copies[i] = Key(type, binding, textures, samplers, false, sameBounds);
        }
        return typeof(BindingLookupProgram).GetMethod(nameof(CollisionCase), BindingFlags.NonPublic | BindingFlags.Static)
            .MakeGenericMethod(type).Invoke(null, new object[] { kind, keys, copies });
    }

    static void DistinctFields<T>(object[] boxed)
    {
        T[] keys = boxed.Cast<T>().ToArray();
        HashSet<T> set = new();
        foreach (T key in keys) Check.That(set.Add(key), "existing equality keeps each field variant distinct");
        foreach (T key in keys) Check.That(set.Contains(key), "field variant remains retrievable");
    }

    static void EqualityVariants()
    {
        foreach (bool buffer in new[] { false, true })
        {
            Type type = typeof(TextureBindingsArrayCache).GetNestedType(buffer ? "CacheEntryFromBufferKey" : "CacheEntryFromPoolKey", BindingFlags.NonPublic);
            TexturePool texture = new(1), otherTexture = new(1);
            SamplerPool sampler = new(1), otherSampler = new(1);
            BufferBounds? bounds = buffer ? new BufferBounds(new MultiRange(0x10000, 8192)) : null;
            List<object> keys = new()
            {
                Key(type, Binding(0), texture, sampler, false, bounds),
                Key(type, Binding(0), texture, sampler, true, bounds),
                Key(type, Binding(0, target: Target.Cubemap), texture, sampler, false, bounds),
                Key(type, Binding(0, length: 2), texture, sampler, false, bounds),
                Key(type, Binding(0), otherTexture, sampler, false, bounds),
                Key(type, Binding(0), texture, otherSampler, false, bounds),
            };
            if (buffer)
            {
                keys.Add(Key(type, Binding(2), texture, sampler, false, bounds));
                keys.Add(Key(type, Binding(0), texture, sampler, false, new BufferBounds(bounds.Value.Range, BufferUsageFlags.Write)));
                keys.Add(Key(type, Binding(0), texture, sampler, false, new BufferBounds(new MultiRange(0x10001, 8192))));
                keys.Add(Key(type, Binding(0), texture, sampler, false, new BufferBounds(new MultiRange(0x10000, 8191))));
                keys.Add(Key(type, Binding(0), texture, sampler, false, new BufferBounds(new MultiRange(new[]
                    { new MemoryRange(0x10000, 4096), new MemoryRange(0x20000, 4096) }))));
            }
            else keys.Add(Key(type, Binding(0, sampler: true), texture, sampler, false, null));
            typeof(BindingLookupProgram).GetMethod(nameof(DistinctFields), BindingFlags.NonPublic | BindingFlags.Static)
                .MakeGenericMethod(type).Invoke(null, new object[] { keys.ToArray() });
        }
    }

    static int CacheCount(TextureBindingsArrayCache cache, string name)
        => ((IDictionary)typeof(TextureBindingsArrayCache).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance).GetValue(cache)).Count;

    static void Update(Fixture fixture, in TextureBindingInfo binding, bool image = false)
    {
        if (image) fixture.Cache.UpdateImageArray(fixture.Textures, ShaderStage.Fragment, 0, 0, binding);
        else fixture.Cache.UpdateTextureArray(fixture.Textures, fixture.Samplers, ShaderStage.Fragment,
                                              0, 0, SamplerIndex.Independently, binding);
    }

    static object Behavior()
    {
        using Fixture f = new(4, threaded: false);
        TextureBindingInfo first = Binding(0), second = Binding(2);
        f.Channel.MemoryManager.Physical.Buffers[0][0] = 1;
        f.Channel.MemoryManager.Physical.Buffers[0][2] = 2;
        Update(f, first); Update(f, second);
        Check.That(ReferenceEquals(f.TextureSink(0).Textures[0], f.SecondHost), "first handle binding");
        Check.That(ReferenceEquals(f.TextureSink(1).Textures[0], f.FirstHost), "second handle binding");
        for (int i = 0; i < 32; i++) { Update(f, first); Update(f, second); }
        Check.That(f.Direct.TextureSinks.Count == 2, "cache hits reuse exact entries");
        f.Channel.MemoryManager.Physical.Buffers[0][0] = 2;
        f.Context.SequenceNumber++;
        Update(f, first);
        Check.That(ReferenceEquals(f.TextureSink(0).Textures[0], f.FirstHost), "changed buffer data still invalidates");
        f.Textures.Items[2] = f.Second; f.Textures.Sequence++; f.Context.SequenceNumber++;
        Update(f, second);
        Check.That(ReferenceEquals(f.TextureSink(1).Textures[0], f.SecondHost), "changed pool item still invalidates");
        f.Second.InvalidatedSequence++; f.Context.SequenceNumber++;
        Update(f, second);
        Check.That(f.TextureSink(1).TextureCalls >= 3, "invalidated texture still refreshes");
        Update(f, first, image: true);
        Check.That(f.Direct.ImageSinks.Count == 1, "image key remains independent");
        for (int i = 0; i < 20010; i++) Update(f, first);
        int bufferEntries = CacheCount(f.Cache, "_cacheFromBuffer");
        Check.That(bufferEntries == 1, "LRU eviction still runs with the same threshold");
        Check.That(f.TextureSink(1).Disposals == 1 && f.ImageSink().Disposals == 1, "evicted arrays disposed once");

        TextureBindingInfo pool = f.Binding(4), sampler = f.Binding(4, sampler: true);
        Update(f, pool); Update(f, sampler); Update(f, pool, image: true);
        Check.That(CacheCount(f.Cache, "_cacheFromPool") == 3, "pool texture/sampler/image entries independent");
        f.Cache.RemoveAllWithPool(f.Textures);
        int poolEntries = CacheCount(f.Cache, "_cacheFromPool");
        Check.That(poolEntries == 0, "pool removal finds and removes all exact keys");
        return new { bufferEntriesAfterEviction = bufferEntries, poolEntriesAfterRemoval = poolEntries,
                     textureSinks = f.Direct.TextureSinks.Count, imageSinks = f.Direct.ImageSinks.Count,
                     textureDisposals = f.Direct.TextureSinks.Sum(s => s.Disposals),
                     imageDisposals = f.Direct.ImageSinks.Sum(s => s.Disposals),
                     bindingCalls = f.Context.Renderer.Pipeline.Bindings };
    }

    static object MeasureCacheHits(int count)
    {
        using Fixture f = new(1, threaded: false);
        f.Textures.Items[0] = null;
        TextureBindingInfo[] bindings = Enumerable.Range(0, count).Select(i => Binding(i * 2)).ToArray();
        foreach (TextureBindingInfo binding in bindings) Update(f, binding);
        const int warmup = 20000, iterations = 50000, samples = 5;
        for (int i = 0; i < warmup; i++) Update(f, bindings[i % count]);
        double[] timings = new double[samples];
        long bytes = 0;
        for (int sample = 0; sample < samples; sample++)
        {
            long allocated = GC.GetAllocatedBytesForCurrentThread();
            long begin = Stopwatch.GetTimestamp();
            for (int i = 0; i < iterations; i++) Update(f, bindings[i % count]);
            long elapsed = Stopwatch.GetTimestamp() - begin;
            bytes += GC.GetAllocatedBytesForCurrentThread() - allocated;
            timings[sample] = elapsed * 1_000_000_000.0 / Stopwatch.Frequency / iterations;
        }
        Check.That(f.Direct.TextureSinks.Count == count, "warmed path created no replacement entries");
        Array.Sort(timings);
        return new { count, warmup, iterations, samples, medianNanosecondsPerHit = timings[samples / 2],
                     bytesPerHit = bytes / (double)(iterations * samples) };
    }

    static void Main()
    {
        EqualityVariants();
        List<object> collisionCases = new();
        foreach (string kind in new[] { "buffer", "pool" })
            foreach (int count in new[] { 1, 32, 128, 512 }) collisionCases.Add(BuildCollisionCase(kind, count));
        object behavior = Behavior();
        object[] warmedCacheHits = new[] { 1, 32, 128, 512 }.Select(MeasureCacheHits).ToArray();
        Console.WriteLine(JsonSerializer.Serialize(new { adapted = Adapted, checks = Check.Count, collisionCases,
            behavior, warmedCacheHits, tieredCompilation = Environment.GetEnvironmentVariable("DOTNET_TieredCompilation"),
            physicalDeviceTested = false }));
    }
}
