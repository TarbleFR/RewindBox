"""Keep the whole-rebuild arrays of large bindless texture, sampler and image arrays instead of allocating them each time.

Finding (IPA 650 / 643 device logs, Hogwarts Legacy, private, not in the repository): at every scene transition the
managed allocation rate jumps to 600-1100 MiB per 5 s with 200-700 ms of GC pause per window. The GPU thread's
"bindings" work is the largest allocator in those windows (S1 17:42:55: 529 calls, 234,000 KiB; 37 compute
dispatches alone allocated 229 MiB, about 6 MiB each) while 1.05-2.63 million bindless elements per window are
rebuilt whole (arrFullElems).

Mechanism (measured on the real code, test/melonx_array_rebuild_allocations_test.py): a whole rebuild in
TextureBindingsArrayCache (UpdateFromPool and UpdateFromBuffer) rents an ITexture[] and, for texture and sampler arrays,
an ISampler[] of bindingInfo.ArrayLength elements from a scratch cache that keeps only lengths up to 4096. Pool-sized
bindless arrays are 65536 to 524288 elements long, so both arrays are allocated anew on every rebuild (large object
heap). With the threaded renderer, ThreadedTextureArray.SetSamplers/SetTextures and ThreadedImageArray.SetImages then
copy each one into a private snapshot from ThreadedArrayPool, which also keeps only lengths up to 4096: two more
allocations of the same size. A threaded rebuild of a 65536-element texture or sampler array allocates 2,097,248 bytes
on the GPU thread (32 bytes per element; an image array 16), all in those four arrays; the per-element loop allocates
nothing. Large-object-heap allocations count against the gen2 budget (with System.GC.ConserveMemory=5): 200 such
rebuilds cause 65 gen2 collections in the host measurement.

Change:
- TextureBindingsArrayCache: the whole rebuilds rent and return their arrays through RentRebuildScratch and
  ReturnRebuildScratch. Lengths up to 4096 go to the existing scratch cache exactly as before. Longer ones are taken
  from (removed while lent) and returned to two bounded slots per element type: at most two arrays and 1,048,576
  elements in all per type (8 MiB of reference slots), the most recently returned kept first; longer arrays are not
  kept. Every returned array is cleared first, as before, so a kept array never roots a texture or sampler. The delta
  runs (at most 4096 elements) keep their own cache unchanged.
- ThreadedArrayPool: the same two bounded slots per element type (process-wide, under the pool's existing lock) for
  snapshots longer than 4096: Copy takes a kept array of the exact length if one is free, Return clears it and keeps it
  within the budget. Lengths up to 4096 are unchanged.
Nothing else changes: the arrays passed to every backend call have the same length and the same contents (a kept
array is all null when lent, as a new one), the calls, their order, the recorded delta state, the texture sets and
reference counts are those of the control (asserted on the real code with doubles).

Measured effect (host, .NET 10 SDK 10.0.100, real cache/producers/commands/pool with doubles for pools, textures and
backend, ConserveMemory=5; receipt dist/melonx/array-rebuild-allocations-checks.json), per whole rebuild of a
65536-element array on the GPU thread: threaded texture 2,097,854 -> 0 bytes, threaded sampler 2,098,562 -> 32 (a
sampler the pool double creates), threaded image 1,048,624 -> 0, direct texture 1,048,624 -> 0, direct image 524,900
-> 0 (byte counts stable across runs). 200 threaded texture rebuilds in a row: 400.1 MiB -> 0.1 MiB allocated, 63-66 ->
0 gen2 collections, 57-132 -> 0 ms of GC pause (three runs; wall time, noisy on the host, falls by 15-45 %).
Backend contents, call stream and recorded state identical in 48 scenarios, one mixed-length cache and the measures.
The 4096-element limit on the existing caches was the cause: the device's pool-sized arrays never fit it.

Limits: textures created by the pool lookups (FindOrCreateTexture), a new entry's per-element delta state and
dictionaries, and the Vulkan backend's own work are not changed. Up to 8 MiB per element type stays allocated per
TextureBindingsArrayCache (one per GPU channel) and in the threaded pool once a large array has been rebuilt; a
threaded snapshot still in flight when the next rebuild starts is allocated as before. Not measured on an iPhone.
Fail closed on drift: each file must be the base preparation's.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
POOL = 'src/Ryujinx.Graphics.GAL/Multithreading/Model/ThreadedArrayPool.cs'
BASELINE = {
    CACHE: '5faea5ff3fb5a684f22de6ede6a4635978df4c1f167a9049c133882d954c5860',
    POOL: '1e73a4faefb413eac267e6718c18c98313ceac4f0493dd41ad680692695df467',
}

RENT = ('                samplers = isImage ? null : RentBindingScratch(_samplerBindingScratch, bindingInfo.ArrayLength);\n'
        '                textures = RentBindingScratch(_textureBindingScratch, bindingInfo.ArrayLength);\n')
RENT_NEW = ('                // RewindBox (adapt_array_rebuild_allocations): pool-sized arrays come from the bounded large slots.\n'
            '                samplers = isImage ? null : RentRebuildScratch(_samplerBindingScratch, _largeSamplerBindingScratch, bindingInfo.ArrayLength);\n'
            '                textures = RentRebuildScratch(_textureBindingScratch, _largeTextureBindingScratch, bindingInfo.ArrayLength);\n')
RETURN = ('                ReturnBindingScratch(_textureBindingScratch, textures, ref _nextTextureBindingScratch);\n'
          '                ReturnBindingScratch(_samplerBindingScratch, samplers, ref _nextSamplerBindingScratch);\n'
          '            }\n        }\n\n')
RETURN_NEW = ('                ReturnRebuildScratch(_textureBindingScratch, _largeTextureBindingScratch, textures, ref _nextTextureBindingScratch);\n'
              '                ReturnRebuildScratch(_samplerBindingScratch, _largeSamplerBindingScratch, samplers, ref _nextSamplerBindingScratch);\n'
              '            }\n        }\n\n')
# The two whole rebuilds (UpdateFromPool, then UpdateFromBuffer), told apart by the line that follows each.
POOL_LOOP = '\n                for (int index = 0; index < length; index++)\n'
BUFFER_LOOP = '\n                for (int index = 0; index < bindingInfo.ArrayLength; index++)\n'
POOL_NEXT = '        // One contiguous run of elements to send'
BUFFER_NEXT = '        /// <summary>\n        /// Updates a texture array binding on the host.\n'
REBUILD_EDITS = (
    (RENT + POOL_LOOP, RENT_NEW + POOL_LOOP),
    (RENT + BUFFER_LOOP, RENT_NEW + BUFFER_LOOP),
    (RETURN + POOL_NEXT, RETURN_NEW + POOL_NEXT),
    (RETURN + BUFFER_NEXT, RETURN_NEW + BUFFER_NEXT),
)
SCRATCH_END = '''                cache[next] = scratch;
                next = (next + 1) % cache.Length;
            }
        }
'''

CACHE_MEMBERS = '''
        // RewindBox (adapt_array_rebuild_allocations): whole rebuilds of pool-sized arrays (65536 to 524288 elements)
        // allocated both arrays on every rebuild. Keep at most two longer arrays per element type, 1048576 elements in
        // all (8 MiB of reference slots), cleared like the others; longer arrays are not kept.
        private const int LargeBindingScratchSlots = 2;
        private const int LargeBindingScratchBudget = 1 << 20;
        private readonly ITexture[][] _largeTextureBindingScratch = new ITexture[LargeBindingScratchSlots][];
        private readonly ISampler[][] _largeSamplerBindingScratch = new ISampler[LargeBindingScratchSlots][];

        private static T[] RentRebuildScratch<T>(T[][] cache, T[][] largeCache, int length)
        {
            if (length <= MaxBindingScratchLength)
            {
                return RentBindingScratch(cache, length);
            }

            for (int i = 0; i < largeCache.Length; i++)
            {
                T[] scratch = largeCache[i];

                if (scratch != null && scratch.Length == length)
                {
                    // Do not lend an array twice, including during a nested update.
                    largeCache[i] = null;
                    return scratch;
                }
            }

            return new T[length];
        }

        private static void ReturnRebuildScratch<T>(T[][] cache, T[][] largeCache, T[] scratch, ref int next)
        {
            if (scratch == null || scratch.Length <= MaxBindingScratchLength)
            {
                ReturnBindingScratch(cache, scratch, ref next);
                return;
            }

            Array.Clear(scratch);

            if (scratch.Length > LargeBindingScratchBudget)
            {
                return;
            }

            KeepLargeScratch(largeCache, scratch);
        }

        // The returned array is kept first; the oldest are dropped until the budget holds.
        private static void KeepLargeScratch<T>(T[][] largeCache, T[] scratch)
        {
            for (int i = largeCache.Length - 1; i > 0; i--)
            {
                largeCache[i] = largeCache[i - 1];
            }

            largeCache[0] = scratch;

            int sum = 0;

            for (int i = 0; i < largeCache.Length; i++)
            {
                if (largeCache[i] != null && (sum += largeCache[i].Length) > LargeBindingScratchBudget)
                {
                    sum -= largeCache[i].Length;
                    largeCache[i] = null;
                }
            }
        }
'''

POOL_MEMBERS = '''
        // RewindBox (adapt_array_rebuild_allocations): snapshots of pool-sized arrays (65536 to 524288 elements) were
        // allocated on every whole rebuild. Keep at most two longer ones per element type, 1048576 elements in all
        // (8 MiB of reference slots), cleared like the others; longer ones are not kept.
        private const int LargeSlots = 2;
        private const int LargeBudget = 1 << 20;
        private static readonly T[][] LargeCache = new T[LargeSlots][];

        // Under the lock. The returned array is kept first; the oldest are dropped until the budget holds.
        private static void KeepLarge(T[] snapshot)
        {
            for (int i = LargeCache.Length - 1; i > 0; i--)
            {
                LargeCache[i] = LargeCache[i - 1];
            }

            LargeCache[0] = snapshot;

            int sum = 0;

            for (int i = 0; i < LargeCache.Length; i++)
            {
                if (LargeCache[i] != null && (sum += LargeCache[i].Length) > LargeBudget)
                {
                    sum -= LargeCache[i].Length;
                    LargeCache[i] = null;
                }
            }
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    cache = paths[CACHE]
    for old, new in REBUILD_EDITS:
        once(cache, old, new)
    once(cache, SCRATCH_END, SCRATCH_END + CACHE_MEMBERS)

    pool = paths[POOL]
    once(pool, '''        private static int _nextEviction;
''', '''        private static int _nextEviction;
''' + POOL_MEMBERS)
    once(pool, '''                lock (Cache)
                {
                    for (int i = 0; i < Cache.Length; i++)
                    {
                        if (Cache[i]?.Length == length)
                        {
                            snapshot = Cache[i];
                            Cache[i] = null;
                            break;
                        }
                    }
                }
            }
''', '''                lock (Cache)
                {
                    for (int i = 0; i < Cache.Length; i++)
                    {
                        if (Cache[i]?.Length == length)
                        {
                            snapshot = Cache[i];
                            Cache[i] = null;
                            break;
                        }
                    }
                }
            }
            else if (length > MaximumLength && length <= LargeBudget)
            {
                // RewindBox (adapt_array_rebuild_allocations): a kept array is all null, as a new one.
                lock (Cache)
                {
                    for (int i = 0; i < LargeCache.Length; i++)
                    {
                        if (LargeCache[i]?.Length == length)
                        {
                            snapshot = LargeCache[i];
                            LargeCache[i] = null;
                            break;
                        }
                    }
                }
            }
''')
    once(pool, '''            if (snapshot.Length <= 1 || snapshot.Length > MaximumLength)
            {
                return;
            }

            // Clear before publication: cached arrays never root backend resources.
            Array.Clear(snapshot);

            lock (Cache)
            {
''', '''            // RewindBox (adapt_array_rebuild_allocations): longer snapshots go to the bounded large slots.
            if (snapshot.Length <= 1 || snapshot.Length > LargeBudget)
            {
                return;
            }

            // Clear before publication: cached arrays never root backend resources.
            Array.Clear(snapshot);

            lock (Cache)
            {
                if (snapshot.Length > MaximumLength)
                {
                    KeepLarge(snapshot);
                    return;
                }

''')
    return list(paths.values())
