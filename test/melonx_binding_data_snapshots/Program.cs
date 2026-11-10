using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Shader;

static class SnapshotCloneProbe
{
    public static int TextureCopies, SamplerCopies;
    public static bool FailTexture, FailSampler;
    public static int[] Texture(ReadOnlySpan<int> source)
    {
        TextureCopies++;
        if (FailTexture) throw new OutOfMemoryException("texture clone boundary");
        return source.ToArray();
    }
    public static int[] Sampler(ReadOnlySpan<int> source)
    {
        SamplerCopies++;
        if (FailSampler) throw new OutOfMemoryException("sampler clone boundary");
        return source.ToArray();
    }
}

static class BindingSnapshotProgram
{
    delegate void UpdateData(ReadOnlySpan<int> texture, ReadOnlySpan<int> sampler, bool separate);
    delegate bool MatchesData(ReadOnlySpan<int> texture, ReadOnlySpan<int> sampler, bool separate, int offset);
    sealed class EntryAccess : IDisposable
    {
        public readonly Fixture Fixture = new(8, threaded: false);
        public readonly object Entry;
        public readonly UpdateData Update;
        public readonly MatchesData Matches;
        readonly FieldInfo textureField, samplerField;
        public EntryAccess()
        {
            Fixture.Update(Fixture.Binding(4, buffer: true));
            var dictionary = (IDictionary)typeof(TextureBindingsArrayCache).GetField("_cacheFromBuffer", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(Fixture.Cache);
            Entry = dictionary.Values.Cast<object>().Single();
            var type = Entry.GetType();
            Update = type.GetMethod("UpdateData").CreateDelegate<UpdateData>(Entry);
            Matches = type.GetMethod("MatchesBufferData").CreateDelegate<MatchesData>(Entry);
            textureField = type.GetField("_cachedTextureBuffer", BindingFlags.Instance | BindingFlags.NonPublic);
            samplerField = type.GetField("_cachedSamplerBuffer", BindingFlags.Instance | BindingFlags.NonPublic);
            Reset();
        }
        public int[] Texture => (int[])textureField.GetValue(Entry);
        public int[] Sampler => (int[])samplerField.GetValue(Entry);
        public void Reset() { textureField.SetValue(Entry, null); samplerField.SetValue(Entry, null); }
        public void Dispose() => Fixture.Dispose();
    }
    static int checks, scenarios;
    static ulong digest = 14695981039346656037;
    static void Assert(bool value, string message)
    {
        checks++;
        if (!value) throw new Exception(message);
    }
    static void Record(ulong value) => digest = unchecked((digest ^ value) * 1099511628211);
    static void RecordArray(int[] values)
    {
        Record((ulong)values.Length);
        foreach (int value in values) Record(unchecked((uint)value));
    }
    static int[] Values(int length, int seed) => Enumerable.Range(0, length).Select(i => unchecked(seed * 134775813 + i * 1103515245)).ToArray();
    static void Verify(EntryAccess entry, ReadOnlySpan<int> texture, ReadOnlySpan<int> sampler, bool separate, string message)
    {
        Assert(entry.Texture.AsSpan().SequenceEqual(texture), message + " texture snapshot");
        Assert(entry.Sampler.AsSpan().SequenceEqual(separate ? sampler : texture), message + " sampler snapshot");
        Assert(separate || ReferenceEquals(entry.Texture, entry.Sampler), message + " combined alias");
        Assert(!separate || entry.Texture.Length == 0 || entry.Sampler.Length == 0 || !ReferenceEquals(entry.Texture, entry.Sampler), message + " separate storage");
        RecordArray(entry.Texture); RecordArray(entry.Sampler);
    }
    static bool OracleMatch(int[] oldTexture, int[] oldSampler, ReadOnlySpan<int> texture, ReadOnlySpan<int> sampler, bool separate, int offset)
    {
        if (oldTexture != null && texture.Length > oldTexture.Length) texture = texture[..oldTexture.Length];
        if (!oldTexture.AsSpan().SequenceEqual(texture)) return false;
        if (!separate) return true;
        if (oldSampler == null || oldSampler.Length <= offset || sampler.Length <= offset) return false;
        return oldSampler[offset] == sampler[offset];
    }
    static void Transitions()
    {
        using EntryAccess entry = new();
        int[] lengths = { 0, 1, 2, 7, 8, 31, 128, 1024 };
        int seed = 1;
        foreach (bool initialSeparate in new[] { false, true })
        foreach (bool nextSeparate in new[] { false, true })
        foreach (int firstLength in lengths)
        foreach (int secondLength in lengths)
        {
            scenarios++;
            entry.Reset();
            int[] firstT = Values(firstLength, seed++), firstS = Values(firstLength / 2, seed++);
            entry.Update(firstT, firstS, initialSeparate);
            Verify(entry, firstT, firstS, initialSeparate, "initial");
            int[] nextT = Values(secondLength, seed++), nextS = Values(firstLength, seed++);
            entry.Update(nextT, nextS, nextSeparate);
            Verify(entry, nextT, nextS, nextSeparate, "transition");
            int[] expectedT = nextT.ToArray(), expectedS = nextSeparate ? nextS.ToArray() : expectedT;
            if (nextT.Length != 0) nextT[^1] ^= 0x35353535;
            if (nextS.Length != 0) nextS[^1] ^= 0x12121212;
            Verify(entry, expectedT, expectedS, nextSeparate, "caller mutation isolated");
            foreach (int offset in new[] { 0, 1, Math.Max(0, expectedS.Length - 1), expectedS.Length, expectedS.Length + 1 })
            {
                bool expected = OracleMatch(expectedT, expectedS, nextT, nextS, nextSeparate, offset);
                bool actual = entry.Matches(nextT, nextS, nextSeparate, offset);
                Assert(actual == expected, "matches after input mutation");
                Record(actual ? 1UL : 0UL);
            }
            var grown = expectedT.Concat(new[] { 789, 456 }).ToArray();
            Assert(entry.Matches(grown, expectedS, nextSeparate, 0) == OracleMatch(expectedT, expectedS, grown, expectedS, nextSeparate, 0), "longer source truncation unchanged");
        }
    }
    static void Aliases()
    {
        using EntryAccess entry = new();
        foreach (bool initialSeparate in new[] { false, true })
        foreach (bool nextSeparate in new[] { false, true })
        foreach (int mode in Enumerable.Range(0, 8))
        {
            scenarios++;
            entry.Reset(); entry.Update(Values(16, 100), Values(16, 200), initialSeparate);
            int[] oldT = entry.Texture, oldS = entry.Sampler;
            int[] externalT = Values(16, 300), externalS = Values(16, 400);
            ReadOnlySpan<int> texture = mode switch { 0 => oldT, 1 => oldS, 2 => oldS.AsSpan(2, 10), 3 => oldT.AsSpan(1, 12), 4 => oldT, 5 => externalT, 6 => oldS, _ => externalT };
            ReadOnlySpan<int> sampler = mode switch { 0 => oldS, 1 => oldT, 2 => oldT.AsSpan(3, 9), 3 => oldS.AsSpan(4, 8), 4 => externalS, 5 => oldT, 6 => externalS, _ => externalS };
            int[] expectedT = texture.ToArray(), expectedS = sampler.ToArray();
            entry.Update(texture, sampler, nextSeparate);
            Verify(entry, expectedT, expectedS, nextSeparate, "aliased inputs");
            Assert(texture.SequenceEqual(expectedT), $"readonly texture source preserved ({initialSeparate},{nextSeparate},{mode})");
            Assert(sampler.SequenceEqual(expectedS), $"readonly sampler source preserved ({initialSeparate},{nextSeparate},{mode})");
        }
    }
    static void AllocationFailures()
    {
        using EntryAccess entry = new();
        foreach (bool initialSeparate in new[] { false, true })
        foreach (bool failTexture in new[] { false, true })
        {
            scenarios++;
            entry.Reset(); entry.Update(Values(16, 1), Values(16, 2), initialSeparate);
            int[] oldT = entry.Texture, oldS = entry.Sampler;
            int[] oldTexture = oldT.ToArray(), oldSampler = oldS.ToArray();
            int[] texture = Values(failTexture ? 17 : 16, 3), sampler = Values(19, 4);
            SnapshotCloneProbe.FailTexture = failTexture;
            SnapshotCloneProbe.FailSampler = !failTexture;
            bool failed = false;
            try { entry.Update(texture, sampler, separate: true); }
            catch (OutOfMemoryException) { failed = true; }
            finally { SnapshotCloneProbe.FailTexture = SnapshotCloneProbe.FailSampler = false; }
            Assert(failed, "real clone boundary failed");
            Assert(entry.Texture.AsSpan().SequenceEqual(failTexture ? oldTexture : texture), "texture state after clone failure");
            Assert(entry.Sampler.AsSpan().SequenceEqual(oldSampler), "sampler state after clone failure");
            Assert(ReferenceEquals(entry.Sampler, oldS), "old sampler owner after failed clone");
            if (failTexture) Assert(ReferenceEquals(entry.Texture, oldT), "old texture owner after first failed clone");
            RecordArray(entry.Texture); RecordArray(entry.Sampler);
        }
    }
    static object EndToEnd()
    {
        int bindingCalls = 0, textureCalls = 0, samplerCalls = 0;
        foreach (bool separate in new[] { false, true })
        {
            using Fixture f = new(8, threaded: false);
            int slots = separate ? TextureHandle.PackSlots(0, 1) : 0;
            int handle = TextureHandle.PackOffsets(0, 0, separate ? TextureHandleType.SeparateSamplerId : TextureHandleType.CombinedSampler);
            TextureBindingInfo binding = new(Target.Texture2D, 0, 0, 4, slots, handle, TextureUsageFlags.None, false);
            int[] words = f.Channel.MemoryManager.Physical.Buffers[0];
            int[] samplerWords = f.Channel.MemoryManager.Physical.Buffers[1];
            for (int i = 0; i < 4; i++) words[i * 2] = i + 1;
            for (int i = 0; i < 500; i++)
            {
                scenarios++;
                words[0] = (i & 1) + 1;
                samplerWords[0] = (i & 1) + 1;
                if (i % 13 == 0) f.First.InvalidatedSequence++;
                f.Update(binding);
                TextureSink sink = f.TextureSink();
                Assert(ReferenceEquals(sink.Textures[0], f.Textures.Items[words[0]]?.Host), "actual rebuild binding content");
                for (int j = 0; j < 4; j++) Record(ReferenceEquals(sink.Textures[j], f.FirstHost) ? 1UL : ReferenceEquals(sink.Textures[j], f.SecondHost) ? 2UL : 0UL);
                if (i % 17 == 0)
                {
                    // Unchanged data still follows the normal validation/fast-hit path.
                    f.Update(binding);
                    Assert(ReferenceEquals(sink.Textures[0], f.Textures.Items[words[0]]?.Host), "actual unchanged binding");
                }
            }
            bindingCalls += f.Context.Renderer.Pipeline.Bindings;
            textureCalls += f.TextureSink().TextureCalls; samplerCalls += f.TextureSink().SamplerCalls;
            f.Cache.RemoveAllWithPool(f.Textures);
            // The existing pool-removal API only handles direct-pool entries;
            // buffer-backed entries retain their original timestamp eviction.
            Assert(f.TextureSink().Disposals == 0, "original buffer-entry removal scope preserved");
            int minimumAge = (int)typeof(TextureBindingsArrayCache).GetField("MinDeltaForRemoval", BindingFlags.Static | BindingFlags.NonPublic).GetRawConstantValue();
            TextureBindingInfo other = new(Target.Texture2D, 0, 0, 4, slots,
                TextureHandle.PackOffsets(16, 0, separate ? TextureHandleType.SeparateSamplerId : TextureHandleType.CombinedSampler), TextureUsageFlags.None, false);
            for (int i = 0; i <= minimumAge; i++) f.Update(other);
            Assert(f.TextureSink().Disposals == 1, "entry disposal after snapshots reused");
        }
        return new { bindingCalls, textureCalls, samplerCalls };
    }
    static object Measure(int length, bool separate)
    {
        using EntryAccess entry = new();
        int[] texture = Values(length, 55), sampler = Values(length, 77);
        for (int i = 0; i < 100; i++) { texture[0] = i; entry.Update(texture, sampler, separate); }
        const int iterations = 200;
        int beforeTextureCopies = SnapshotCloneProbe.TextureCopies, beforeSamplerCopies = SnapshotCloneProbe.SamplerCopies;
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < iterations; i++) { texture[0] = i; entry.Update(texture, sampler, separate); }
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        Assert(entry.Texture.AsSpan().SequenceEqual(texture), "warm snapshot values");
        Assert(entry.Sampler.AsSpan().SequenceEqual(separate ? sampler : texture), "warm sampler values");
        return new { length, separate, iterations, allocatedBytes = allocated,
            textureCopies = SnapshotCloneProbe.TextureCopies - beforeTextureCopies,
            samplerCopies = SnapshotCloneProbe.SamplerCopies - beforeSamplerCopies };
    }
    static void Main()
    {
        Transitions(); Aliases(); AllocationFailures(); var behavior = EndToEnd();
        var allocations = new List<object>();
        foreach (int length in new[] { 16, 1024, 32768 })
        foreach (bool separate in new[] { false, true }) allocations.Add(Measure(length, separate));
        Console.WriteLine(JsonSerializer.Serialize(new { checks, scenarios, semanticDigest = digest.ToString("x16"), behavior, allocations }));
    }
}
