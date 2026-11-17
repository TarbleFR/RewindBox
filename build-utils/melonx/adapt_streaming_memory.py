"""Apply the foreground GC and streaming allocation fixes to the delivered 775 sources."""
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
                return new Holder(new T[minimumSize]);
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
