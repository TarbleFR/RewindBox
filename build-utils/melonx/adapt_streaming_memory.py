"""Apply the foreground GC and streaming allocation fixes to the delivered 775 sources.

POOL_830, every title (MemoryOwner<T>, the pool behind texture uploads and conversions, DMA copies and fragmented
guest reads and writes). IPA 830 private journals (counts only), Hogwarts Legacy: the large object heap (LOH) is
491-509 MiB five seconds after each of ten launches, 153-255 MiB of it free; an engine compaction in a loading gap
(pid 19616) brought it to 265 MiB with nothing free, and 15 s later it was 504 MiB again, 181 MiB free. In play the
GPU thread allocates up to 267 MiB in 5 s, and the heap stays at 451-466 MiB, about 210 MiB free, to the end. The pool
missed: a miss allocated an array of the exact length asked, so an upload of another size found nothing to reuse,
and every array, the first of a length included, left the pool 3 s after it was returned. Neither returns memory to
iOS: a freed large array is LOH free space the collector keeps committed, and the background collections the
session runs (adapt_bgc_keepalive) never compact it. Each new large array is also cleared, which touches pages iOS
may have compressed.

Change, in the pool only: a miss of 85,000 bytes or more allocates its size class (the next multiple of a quarter
of the length's power of two: at most 25 % more); the large arrays kept, primaries and spares, use at most 96 MiB
together (the oldest spares go first, then the primary returned the longest ago); a kept large array is released
30 s after it was returned instead of 3 s (a primary under 85,000 bytes, not a large object, still after 3 s). A rent
still returns an array at least as long as asked whose first `length` elements the caller owns, RentCleared still
clears them; contents, search, spares (64 MiB at most) and skip counts are otherwise unchanged. Memory kept: at most
96 MiB of large arrays per element type, instead of the 64 MiB of spares plus every primary for 3 s. Host bench
(.NET 10, x64; 6 bursts of 48 uploads of 32 texture-like sizes from 64 KiB to 8 MiB, 8 in flight, 3.5 s apart):
248.1 MiB allocated by the delivered pool, 65.3 MiB by this one, at most 65.2 MiB kept; exclusive spans under 8
threads, RentCleared and RentCopy checked. Not measured on an iPhone; the journals' LOH figures (gcEvent,
memoryInventory) and the GPU thread's allocated bytes (core-performance) show the effect.
"""
import hashlib

from adapt_session import once

MEMORY = 'src/Ryujinx.Library/EmbeddedMemory.cs'
POOL = 'src/Ryujinx.Common/Memory/MemoryOwner.cs'
BINDINGS = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
GAL = 'src/Ryujinx.Graphics.GAL/'
ARRAY_API = GAL + 'ITextureArray.cs'
SNAPSHOTS = GAL + 'Multithreading/Model/ThreadedArrayPool.cs'
TEXTURES = GAL + 'Multithreading/Resources/ThreadedTextureArray.cs'
IMAGES = GAL + 'Multithreading/Resources/ThreadedImageArray.cs'

BASELINE = {
    MEMORY: 'da02ae71a08ac754999b28864256e6a472c3800d35165c00a9aad439499b86b9',
    POOL: 'b139c5a7407a2632c3e5b2fd0bd84313be1624dbb6050241b8bcefd2f2fa72d4',
    BINDINGS: 'f61740ec7897f8149f4f3c50ef3b7a298f315b1401b67bbc247767e5baa0ed3a',
    ARRAY_API: 'bebf4ac56fcd76c09f64318900bf2cf5c08f2e1b50fdbf28db0946e393e3008b',
    SNAPSHOTS: '376a74665c8898e8fa3b018c56fd152982cdacebfd64c8220aad982622c3b888',
    TEXTURES: 'a3a116c083ce487b981d4481527be72708fc32d50b2185f072204e8057ec31e6',
    IMAGES: '15f70d0656ff7fcf3d0281a3259de39e861d18ba0d8e8b375e56d3b05394eba4',
}


def apply(source):
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name

    memory = source / MEMORY
    once(memory, '    internal static int StallCompactions =>', '''    // A presentation gap can be an active scene stalled on decompression or GC.
    // Only take the emergency path at the same process headroom used for a critical GPU trim.
    // If the OS reports zero, the existing device-pressure and fragmentation guards still apply.
    private const ulong CriticalProcessHeadroom = 256UL * 1024 * 1024;
    internal static bool MayCompactInGap(ulong processHeadroom) => processHeadroom <= CriticalProcessHeadroom;

    internal static int StallCompactions =>''')
    once(memory, '            if (!ShouldCompactInStall(ReclaimableBytes', '''            if (!MayCompactInGap(Ryujinx.Memory.HostMemoryBudget.AvailableBytes) ||
                !ShouldCompactInStall(ReclaimableBytes''')
    once(memory, '            if (presentStamp != -1 && DrainHolds(presentStamp))',
         '            if (presentStamp != -1 && (!MayCompactInGap(Ryujinx.Memory.HostMemoryBudget.AvailableBytes) || DrainHolds(presentStamp)))')

    pool = source / POOL
    once(pool, 'if (self > other * 4)', 'if (self > (long)other * 4)')
    once(pool, '''                int max = list.Count-1;
''', '''                int max = list.Count - 1;
                int fit = -1;
''')
    once(pool, '''                    if (comparison == 0)
                    {
                        return mid;
                    }
''', '''                    if (comparison == 0)
                    {
                        // Use the smallest suitable buffer. A larger one may be needed by the next upload.
                        if (list[mid].Array!.Length == size)
                        {
                            return mid;
                        }

                        fit = mid;
                    }
''')
    once(pool, '                return ~min;', '                return fit >= 0 ? fit : ~min;')
    once(pool, '''
                    return new Holder(new T[minimumSize]);
                }
''', '''                }

                // A miss owns no pool entry. Allocate outside the shared lock so returns can proceed.
                return new Holder(new T[ClassLength(minimumSize)]);
''')
    # IPA 830 (POOL_830 in the docstring): size classes, one budget for the large arrays kept, a 30 s idle release.
    once(pool, '''            // Arrays of 85,000 bytes or more returned while their length is pooled wait as spares
            // instead of being dropped (a frame uploads several textures of one size), outside
            // _pool, which keeps one array per length as before. When a rent takes a length's
            // array, a spare of that length takes its place. Spares use at most 64 MiB; the oldest
            // go first, and a timer releases a spare 3 s after it was returned.
            private const long MinSpareBytes = 85000;
            private const long MaxSpareBytes = 64L * 1024 * 1024;
            private const int SpareIdleMilliseconds = 3000;
''', '''            // Arrays of 85,000 bytes or more returned while their length is pooled wait as spares
            // instead of being dropped (a frame uploads several textures of one size), outside
            // _pool, which keeps one array per length as before. When a rent takes a length's
            // array, a spare of that length takes its place. Spares use at most 64 MiB; the oldest
            // go first.
            // RewindBox (adapt_streaming_memory, IPA 830): such an array is allocated at its size class
            // (four per power of two, at most 25 % longer than asked), so uploads of nearby sizes share
            // it; the large arrays kept, primaries and spares together, use at most 96 MiB (spares first,
            // then the primary returned the longest ago); a timer releases a kept large array 30 s after
            // it was returned (a primary under 85,000 bytes still 3 s). With 3 s, a large array released
            // between two loads became free space that the large object heap keeps, and the next load
            // allocated a new one.
            private const long MinSpareBytes = 85000;
            private const long MaxSpareBytes = 64L * 1024 * 1024;
            private const long MaxPooledBytes = 96L * 1024 * 1024;
            private const int SpareIdleMilliseconds = 30000;
            private const int SmallIdleMilliseconds = 3000;
            // The bytes of the large arrays in _pool (primaries); _spareBytes counts the spares.
            private static long _primaryBytes;
''')
    once(pool, '''            public static Holder Get(int minimumSize)
''', '''            // RewindBox (adapt_streaming_memory): the length a miss allocates. Under 85,000 bytes the length asked
            // (not a large object); from it, the next multiple of a quarter of the length's power of two.
            private static int ClassLength(int length)
            {
                if ((long)length * Unsafe.SizeOf<T>() < MinSpareBytes)
                {
                    return length;
                }

                long step = (1L << System.Numerics.BitOperations.Log2((uint)length)) >> 2;
                long rounded = ((long)length + step - 1) / step * step;

                return rounded <= Array.MaxLength ? (int)rounded : length;
            }

            private static long LargeBytes(T[] array)
            {
                long bytes = Bytes(array);

                return bytes >= MinSpareBytes ? bytes : 0;
            }

            private static long IdleMilliseconds(T[] array) => LargeBytes(array) != 0 ? SpareIdleMilliseconds : SmallIdleMilliseconds;

            // RewindBox (adapt_streaming_memory): the large arrays kept fit MaxPooledBytes. The oldest spares go first,
            // then the large primary returned the longest ago (its length leaves the pool, as a cleanup drops it).
            private static void TrimToBudgetLocked()
            {
                while (_primaryBytes + _spareBytes > MaxPooledBytes)
                {
                    if (_spares.First is { } spare)
                    {
                        RemoveSpareLocked(spare.Value);
                        continue;
                    }

                    int oldest = -1;

                    for (int index = 0; index < _pool.Count; index++)
                    {
                        Holder kept = _pool[index];

                        if (LargeBytes(kept.Array!) != 0 && (oldest < 0 || kept.Returned < _pool[oldest].Returned))
                        {
                            oldest = index;
                        }
                    }

                    if (oldest < 0)
                    {
                        return;
                    }

                    _primaryBytes -= LargeBytes(_pool[oldest].Array!);
                    _pool.RemoveAt(oldest);
                }
            }

            public static Holder Get(int minimumSize)
''')
    once(pool, '''                        else
                        {
                            _pool.RemoveAt(index);
                        }

                        return holder;
''', '''                        else
                        {
                            _pool.RemoveAt(index);
                            _primaryBytes -= LargeBytes(holder.Array!);
                        }

                        return holder;
''')
    once(pool, '''                    if (i < 0)
                    {
                        _pool.Insert(~i, holder);
                    }
                    else
                    {
                        KeepSpareLocked(holder);
                    }
''', '''                    if (i < 0)
                    {
                        _pool.Insert(~i, holder);
                        _primaryBytes += LargeBytes(holder.Array!);
                    }
                    else
                    {
                        KeepSpareLocked(holder);
                    }

                    TrimToBudgetLocked();
''')
    once(pool, '''                                _pool.RemoveAt(index);
                                DropSparesLocked(h.Array!.Length);
''', '''                                _pool.RemoveAt(index);
                                _primaryBytes -= LargeBytes(h.Array!);
                                DropSparesLocked(h.Array!.Length);
''')
    once(pool, '''                        (_arrayTimer ??= new Timer(ReleaseIdleArrays)).Change(SpareIdleMilliseconds, Timeout.Infinite);
''', '''                        (_arrayTimer ??= new Timer(ReleaseIdleArrays)).Change(SmallIdleMilliseconds, Timeout.Infinite);
''')
    once(pool, '''                    long next = SpareIdleMilliseconds;
                    int writeIndex = 0;

                    for (int index = 0; index < _pool.Count; index++)
                    {
                        Holder holder = _pool[index];
                        long remaining = holder.Returned + SpareIdleMilliseconds - now;
''', '''                    // Every 3 s at most while arrays are kept: a small primary leaves 3 s after its return.
                    long next = SmallIdleMilliseconds;
                    int writeIndex = 0;

                    for (int index = 0; index < _pool.Count; index++)
                    {
                        Holder holder = _pool[index];
                        long remaining = holder.Returned + IdleMilliseconds(holder.Array!) - now;
''')
    once(pool, '''                        if (remaining > 0)
                        {
                            _pool[writeIndex++] = holder;
                            next = Math.Min(next, remaining);
                        }
''', '''                        if (remaining > 0)
                        {
                            _pool[writeIndex++] = holder;
                            next = Math.Min(next, remaining);
                        }
                        else
                        {
                            _primaryBytes -= LargeBytes(holder.Array!);
                        }
''')

    bindings = source / BINDINGS
    once(bindings, '            public Texture[] DeltaItems;', '''            // Ordinarily the resolved texture is the pool item. Materialize only pages
            // with a differing item (format aliases or a failed resolution). An allocated
            // page stores exact references, including null, for all its elements.
            private const int ItemPageSize = 256;
            private Texture[][] _itemPages;
            private int _itemSlots;

            private Texture PoolItemAt(int index)
            {
                Texture[] page = _itemPages?[index / ItemPageSize];
                return page == null ? DeltaTextures[index] : page[index % ItemPageSize];
            }

            private void RecordPoolItem(int index, Texture item, Texture resolved)
            {
                int pageIndex = index / ItemPageSize;
                Texture[] page = _itemPages?[pageIndex];
                if (page == null)
                {
                    if (ReferenceEquals(item, resolved))
                    {
                        return;
                    }

                    if (_itemPages == null)
                    {
                        _itemPages = new Texture[1 + (DeltaTextures.Length - 1) / ItemPageSize][];
                        CountItemSlots(_itemPages.Length);
                    }

                    int start = index - index % ItemPageSize;
                    page = new Texture[Math.Min(ItemPageSize, DeltaTextures.Length - start)];
                    Array.Copy(DeltaTextures, start, page, 0, page.Length);
                    _itemPages[pageIndex] = page;
                    CountItemSlots(page.Length);
                }

                page[index % ItemPageSize] = item;
            }

            private void CountItemSlots(int count)
            {
                _itemSlots += count;
                Interlocked.Add(ref TextureArrayInventory.PoolEntryBytes, (long)count * IntPtr.Size);
            }
''')
    once(bindings, '(long)(DeltaItems?.Length ?? 0)', '(long)_itemSlots')
    once(bindings, '''                    if (DeltaItems?.Length != length)
                    {
                        DeltaItems = new Texture[length];''', '''                    if (DeltaTextures?.Length != length)
                    {
                        _itemPages = null;
                        _itemSlots = 0;''')
    once(bindings, 'if (DeltaSamplers != null && DeltaItems == null)', 'if (DeltaSamplers != null && DeltaTextures == null)')
    once(bindings, '                DeltaItems[index] = item;', '                RecordPoolItem(index, item, texture);')
    once(bindings, 'if (item != DeltaItems[index])', 'if (item != PoolItemAt(index))')

    once(source / ARRAY_API, '    public interface ITextureArray : IDisposable', '''    // The writer must consume or snapshot the span before returning to the producer.
    public interface IArrayRangeWriter<T> where T : class
    {
        void SetRange(int index, ReadOnlySpan<T> elements);
    }

    public interface ITextureArray : IDisposable''')
    snapshots = source / SNAPSHOTS
    once(snapshots, '''        public static T[] Copy(T[] source)
        {
            ArgumentNullException.ThrowIfNull(source);''', '''        public static T[] Copy(T[] source)
        {
            ArgumentNullException.ThrowIfNull(source);
            return Copy(new ReadOnlySpan<T>(source));
        }

        public static T[] Copy(ReadOnlySpan<T> source)
        {''')
    once(snapshots, 'new ReadOnlySpan<T>(source).CopyTo(snapshot);', 'source.CopyTo(snapshot);')
    for name, kind, writers in (
            (TEXTURES, 'Texture', ('Textures', 'Samplers')),
            (IMAGES, 'Image', ('Images',))):
        path = source / name
        array = f'I{kind}Array'
        types = ['ISampler' if method == 'Samplers' else 'ITexture' for method in writers]
        once(path, f' : {array}\n', f' : {array}, ' + ', '.join(f'IArrayRangeWriter<{t}>' for t in types) + '\n')
        for method, element in zip(writers, types):
            arg = method.lower()
            once(path, f'''        public unsafe void Set{method}(int index, {element}[] {arg})
        {{
            if ({arg} != null && {arg}.Length == 1)''', f'''        public void Set{method}(int index, {element}[] {arg})
        {{
            System.ArgumentNullException.ThrowIfNull({arg});
            SetRange(index, new System.ReadOnlySpan<{element}>({arg}));
        }}

        public unsafe void SetRange(int index, System.ReadOnlySpan<{element}> {arg})
        {{
            if ({arg}.Length == 1)''')

    once(bindings, '''            if (isSampler)
            {
                ISampler[] samplers = RentBindingScratch(_deltaSamplerScratch, count);''', '''            // The threaded backend already takes its own snapshot. Pass the live prefix
            // directly; direct backends retain the existing exact-length scratch path.
            if (isSampler && entry.TextureArray is IArrayRangeWriter<ISampler> samplerWriter)
            {
                try
                {
                    samplerWriter.SetRange(runStart, _deltaRunSamplers.AsSpan(0, count));
                }
                finally
                {
                    Array.Clear(_deltaRunSamplers, 0, count);
                }
                return;
            }

            IArrayRangeWriter<ITexture> textureWriter = isSampler ? null :
                isImage ? entry.ImageArray as IArrayRangeWriter<ITexture> : entry.TextureArray as IArrayRangeWriter<ITexture>;
            if (textureWriter != null)
            {
                try
                {
                    textureWriter.SetRange(runStart, _deltaRunTextures.AsSpan(0, count));
                }
                finally
                {
                    Array.Clear(_deltaRunTextures, 0, count);
                }
                return;
            }

            if (isSampler)
            {
                ISampler[] samplers = RentBindingScratch(_deltaSamplerScratch, count);''')
    return [source / name for name in (MEMORY, POOL, BINDINGS, ARRAY_API, SNAPSHOTS, TEXTURES, IMAGES)]
