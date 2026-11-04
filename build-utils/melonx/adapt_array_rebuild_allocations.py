"""Keep the whole-rebuild arrays of large bindless texture, sampler and image arrays instead of allocating them each time.

Finding (IPA 650 / 643 device logs, Hogwarts Legacy, private, not in the repository): at every scene transition the
managed allocation rate jumps to 600-1100 MiB per 5 s with 200-700 ms of GC pause per window. The GPU thread's
"bindings" work is the largest allocator in those windows (S1 17:42:55: 529 calls, 234,000 KiB; 37 compute
dispatches alone allocated 229 MiB, about 6 MiB each) while 1.05-2.63 million bindless elements per window are
rebuilt whole (arrFullElems).

Mechanism (measured on the real code, test/melonx_array_rebuild_allocations_test.py): a whole rebuild in
TextureBindingsArrayCache (UpdateFromPool and UpdateFromBuffer) rents an ITexture[] and, for texture and sampler arrays,
an ISampler[] of bindingInfo.ArrayLength elements from a scratch cache that keeps only lengths up to 4096. Pool-sized
bindless arrays (ArrayLength is the pool's MaximumId + 1) are longer, so both arrays are allocated anew on every
rebuild (large object heap). With the threaded renderer, ThreadedTextureArray.SetSamplers/SetTextures and
ThreadedImageArray.SetImages then copy each one into a private snapshot from ThreadedArrayPool, which also keeps only
lengths up to 4096: two more allocations of the same size. A threaded rebuild of a texture or sampler array allocates
32 bytes per element on the GPU thread (an image array 16, direct rebuilds half that), all in those four arrays; the
per-element loop allocates nothing. Large-object-heap allocations count against the gen2 budget (with
System.GC.ConserveMemory=5): 200 such rebuilds cause 26-66 gen2 collections in the host measurement. The device logs
do not give the array lengths: about 6.2 MiB per compute dispatch matches one threaded texture array of about 200000
elements or three of 65536 (both measured).

Change:
- TextureBindingsArrayCache: the whole rebuilds rent and return their arrays through RentRebuildScratch and
  ReturnRebuildScratch. Lengths up to 4096 go to the existing scratch cache exactly as before. Longer ones are taken
  from (removed while lent) and returned to two bounded slots per element type: at most two arrays and 1,048,576
  elements in all per type (8 MiB of reference slots), the most recently returned kept first; longer arrays are not
  kept. Every returned array is cleared first, as before, so a kept array never roots a texture or sampler. The delta
  runs (at most 4096 elements) keep their own cache unchanged.
- ThreadedArrayPool: eight bounded slots per element type (process-wide, under the pool's existing lock) for snapshots
  longer than 4096, within the same 1,048,576-element budget: Copy takes a kept array of the exact length if one is
  free, Return clears it and keeps it within the budget. Eight slots let a render thread lag up to eight rebuilds
  behind the GPU thread and still find a kept snapshot. Lengths up to 4096 are unchanged.
Nothing else changes: the arrays passed to every backend call have the same length and the same contents (a kept
array is all null when lent, as a new one), the calls, their order, the recorded delta state, the buffer entries'
texture and sampler ids, the texture sets and reference counts are those of the control (asserted on the real code
with doubles).

Measured effect (host, .NET 10 SDK 10.0.100, real cache/producers/commands/pool with doubles for pools, textures and
backend, ConserveMemory=5; receipt dist/melonx/array-rebuild-allocations-checks.json), bytes allocated on the GPU
thread per whole rebuild of a 65536-element array, control -> candidate: threaded texture 2,097,248 -> 0; threaded
sampler about 2,097,300-2,099,200 -> 32 (a Sampler the pool double creates for the written element); threaded image
about 1,048,600-1,049,200 -> 0; direct texture 1,048,624 -> 0; direct sampler about 1,048,700-1,050,000 -> 32; direct
image 524,312 -> 0. In the control the whole-length arrays are exactly 32, 16 or 8 bytes per element (plus array
headers) in every run; small allocations of up to about 2 KiB around them vary between runs. The candidate rows did
not vary over four runs.
Longer arrays (threaded texture): 200000 elements 6,400,096 -> 0, 524288 elements 16,777,312 -> 0, 1100000 elements
about 35.2 MB -> about 35.2 MB (over the budget: no gain, as designed). One dispatch of three threaded texture arrays:
3 x 65536 about 6,291,800 -> 0, 3 x 200000 19,200,288 -> 0. Buffer-handle rebuilds (UpdateFromBuffer) of 8000
elements: threaded texture 256,096 -> 0, direct image 64,024 -> 0.
Bursts of 200 threaded 65536-element texture rebuilds with the consumer draining every N rebuilds (one warm-up round
at the same lag first), control -> candidate: N = 1, 2, 4, 8: about 400 MiB -> 0.1 MiB allocated, about 48-66 -> 0
gen2 collections, about 40-130 -> 0 ms of GC pause; N = 16: about 400 -> 96 MiB, gen2 about 33-40 -> 7; N = 37: about
400 -> 152 MiB, gen2 about 20-27 -> 7-8 (the GC pause also falls there, by a noisy amount; the host's gen2 counts and
pauses vary between runs, the allocated MiB do not). Beyond eight snapshots in
flight per element type only the cache-scratch half (16 of 32 bytes per element) and the snapshots that fit the slots
are removed. Wall time is noisy on the host and is not claimed (per-rebuild and burst times move in both directions
between runs).
Backend contents, call stream and recorded state identical in 48 pool-path scenarios, 36 buffer-handle scenarios
(failing lookups in the middle of a rebuild included), one mixed-length cache, every measure and every burst.
The 4096-element limit on the existing caches was the cause: the device's pool-sized arrays never fit it.

Limits: textures created by the pool lookups (FindOrCreateTexture), a new entry's per-element delta state and
dictionaries, and the Vulkan backend's own work are not changed. Arrays longer than 1,048,576 elements, or arrays of
one element type whose lengths in flight together exceed that budget, are allocated as before. Up to 8 MiB per element
type stays allocated per TextureBindingsArrayCache (one per GPU channel, freed with it) and in the process-wide
threaded pool (ITexture and ISampler, not released by the Library teardown) once a large array has been rebuilt. A
render thread lagging more than eight rebuilds behind still allocates the snapshots beyond eight. The device array
lengths and render-thread lag are assumptions. Not measured on an iPhone.
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
        // RewindBox (adapt_array_rebuild_allocations): whole rebuilds of pool-sized arrays (longer than 4096 elements)
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
        // RewindBox (adapt_array_rebuild_allocations): snapshots of pool-sized arrays (longer than 4096 elements) were
        // allocated on every whole rebuild. Keep at most eight longer ones per element type (a render thread lagging up
        // to eight rebuilds behind still finds one), 1048576 elements in all (8 MiB of reference slots), cleared like the
        // others; longer ones are not kept.
        private const int LargeSlots = 8;
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
