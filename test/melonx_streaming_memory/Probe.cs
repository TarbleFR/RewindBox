using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading.Model;

namespace Ryujinx.Graphics.GAL
{
    public interface ITexture { }
    public interface ISampler { }
    public interface IImageArray { void SetImages(int index, ITexture[] images); }
}

class Texture : ITexture { }
class Sampler : ISampler { }
struct FormatInfo { }

partial class CacheEntry
{
    public bool ForceRebuild, DeltaReady, DeltaAllBlacklisted;
    public int DeltaLength, DeltaAliasGeneration;
    public FormatInfo DeltaFormatInfo;
    public ITextureArray TextureArray;
    public IImageArray ImageArray;
    private Dictionary<Texture, int> _deltaReferences;

    public void Write(int i, Texture item, Texture resolved)
    {
#if CANDIDATE
        RecordPoolItem(i, item, resolved);
#else
        DeltaItems[i] = item;
#endif
        DeltaTextures[i] = resolved;
    }

    public Texture Read(int i)
    {
#if CANDIDATE
        return PoolItemAt(i);
#else
        return DeltaItems[i];
#endif
    }
}

// Captures values until Consume, including after the producer has cleared its array.
class Backend : ITextureArray, IImageArray
{
    protected ITexture[] textures;
    protected ISampler[] samplers;
    protected int offset;
    public void Dispose() { }
    public void SetTextures(int i, ITexture[] a) { offset = i; textures = ThreadedArrayPool<ITexture>.Copy(a); }
    public void SetImages(int i, ITexture[] a) => SetTextures(i, a);
    public void SetSamplers(int i, ISampler[] a) { offset = i; samplers = ThreadedArrayPool<ISampler>.Copy(a); }

    public void Consume(int i, int n, Texture t, Sampler s, bool isSampler)
    {
        if (offset != i || (isSampler ? samplers.Length : textures.Length) != n) throw new Exception("range");
        for (int k = 0; k < n; k++)
        {
            object expected = k % 3 == 0 ? null : isSampler ? s : t;
            if (!ReferenceEquals(isSampler ? (object)samplers[k] : textures[k], expected)) throw new Exception("snapshot");
        }
        if (isSampler) ThreadedArrayPool<ISampler>.Return(samplers);
        else ThreadedArrayPool<ITexture>.Return(textures);
        textures = null;
        samplers = null;
    }
}

class ThreadedBackend : Backend
#if CANDIDATE
    , IArrayRangeWriter<ITexture>, IArrayRangeWriter<ISampler>
#endif
{
#if CANDIDATE
    public void SetRange(int i, ReadOnlySpan<ITexture> a) { offset = i; textures = ThreadedArrayPool<ITexture>.Copy(a); }
    public void SetRange(int i, ReadOnlySpan<ISampler> a) { offset = i; samplers = ThreadedArrayPool<ISampler>.Copy(a); }
#endif
}

partial class Bindings
{
    private const int BindingScratchSlots = 4, MaxBindingScratchLength = 4096;
    private readonly ITexture[] _deltaRunTextures = new ITexture[4096];
    private readonly ISampler[] _deltaRunSamplers = new ISampler[4096];
    private readonly ITexture[][] _deltaTextureScratch = new ITexture[BindingScratchSlots][];
    private readonly ISampler[][] _deltaSamplerScratch = new ISampler[BindingScratchSlots][];
    private int _nextDeltaTextureScratch, _nextDeltaSamplerScratch;

    public long Run(Backend backend)
    {
        var entry = new CacheEntry { ImageArray = backend, TextureArray = backend };
        var t = new Texture();
        var s = new Sampler();
        long start = GC.GetAllocatedBytesForCurrentThread();
        for (int call = 0; call < 16384; call++)
        {
            int length = call % 64 + 1, count = length;
            bool sampler = call % 3 == 0, image = call % 3 == 1;
            for (int k = 0; k < length; k++)
            {
                _deltaRunTextures[k] = k % 3 == 0 || sampler ? null : t;
                _deltaRunSamplers[k] = k % 3 == 0 || !sampler ? null : s;
            }
            FlushDeltaRun(entry, image, sampler, call, ref count);
            if (count != 0) throw new Exception("run not drained");
            for (int k = 0; k < length; k++)
                if (_deltaRunTextures[k] != null || _deltaRunSamplers[k] != null) throw new Exception("retained");
            backend.Consume(call, length, t, s, sampler);
        }
        return GC.GetAllocatedBytesForCurrentThread() - start;
    }
}

class Probe
{
    static void Check(bool ok) { if (!ok) throw new Exception("streaming memory regression"); }

    public static void Main()
    {
        const int length = 524288;
        var entry = new CacheEntry();
        entry.PrepareDelta(length, false, default, 0, false);
        long initial = entry.DeltaBytes();
        var texture = new Texture();
        var alias = new Texture();
        for (int i = 0; i < length; i++) entry.Write(i, texture, texture);
        Check(entry.DeltaBytes() == initial);
        entry.Write(255, null, texture);
        entry.Write(256, texture, alias);
        entry.Write(length - 1, alias, null);
        Check(entry.Read(254) == texture && entry.Read(255) == null && entry.Read(256) == texture &&
              entry.Read(257) == texture && entry.Read(length - 1) == alias);
        long sparse = entry.DeltaBytes();
        Check(sparse == TextureArrayInventory.PoolEntryBytes);

        var random = new Random(775);
        foreach (int size in new[] { 257, 257, 4097, 1, 0, 8193 })
        {
            entry.PrepareDelta(size, false, default, 0, false);
            Texture[] expected = new Texture[size];
            for (int i = 0; i < size; i++) entry.Write(i, expected[i], null);
            if (size == 0) continue;
            for (int j = 0; j < 8000; j++)
            {
                int i = random.Next(size);
                Texture item = random.Next(3) == 0 ? null : texture;
                Texture resolved = random.Next(3) == 0 ? alias : item;
                entry.Write(i, item, resolved);
                expected[i] = item;
            }
            for (int i = 0; i < size; i++) Check(entry.Read(i) == expected[i]);
            Check(entry.DeltaBytes() == TextureArrayInventory.PoolEntryBytes);
        }

        var owners = new MemoryOwner<byte>[3];
        int[] sizes = { 131072, 262144, 524288 };
        for (int i = 0; i < sizes.Length; i++) owners[i] = MemoryOwner<byte>.Rent(sizes[i]);
        foreach (var o in owners) o.Dispose();
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < sizes.Length; i++) owners[i] = MemoryOwner<byte>.Rent(sizes[i]);
        long upload = GC.GetAllocatedBytesForCurrentThread() - before;
        foreach (var o in owners) o.Dispose();
        Parallel.For(0, 8, lane => {
            for (int i = 0; i < 1000; i++)
            {
                using var owner = MemoryOwner<byte>.Rent(1000 + i % 161);
                owner.Span.Fill((byte)lane);
                Thread.Yield();
                if (owner.Span.IndexOfAnyExcept((byte)lane) >= 0) throw new Exception("shared live upload");
            }
        });
#if CANDIDATE
        Check(Gap.MayCompactInGap(0) && Gap.MayCompactInGap(256UL << 20) &&
              !Gap.MayCompactInGap((256UL << 20) + 1) && !Gap.MayCompactInGap(2300299544UL));
#endif
        var direct = new Bindings().Run(new Backend());
        var threaded = new Bindings().Run(new ThreadedBackend());
        Console.WriteLine($"{initial},{sparse},{upload},{direct},{threaded}");
    }
}
