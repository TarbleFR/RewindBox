"""Stop the GPU emulation thread allocating a new array for each copy it makes.

Hogwarts Legacy, builds 564-572 app.log (27 October 2026): of 666 gameplay
seconds at 3-18 FPS with the GPU thread busy 95 % of the time or more, 632
(95 %) had the .NET background GC thread at 30 % of a core or more; of 182
seconds at 27 FPS or more, 6 (3 %). Onsets happen inside one scene (30 to
5 FPS as the background GC goes from 0 to 50 % of a core). While a background
GC runs, the .NET GC makes allocating threads wait: a 2 ms sleep every 140
allocation-context refills, and a large-object allocation (85,000 bytes or
more) yields or waits for the whole background GC once the large-object heap
has grown by 10 % or 100 % during it (gc.cpp, .NET 10). Ephemeral
collections run on the thread that allocates. The GPU thread's CPU time per
frame triples in those seconds (52-58 ms against 15-18 ms). The logs hold no
allocation counts, so how much each site below contributes is not known; each
one allocates on every use, on the GPU thread or for it, in every game:

- DmaClass: a partial texture copy by the copy engine (a sub-rectangle or a
  mip level written into a larger texture, which is how streamed textures
  arrive) read the whole destination range into a new array, patched the
  copied texels in it and wrote it back: one destination-sized array (a
  large object from 85 KB) per copy. The range is now read into a buffer
  the engine keeps (copies run one at a time on the GPU thread, and nothing
  between the read and the write-back runs another copy), patched and
  written back exactly as before. Copies above 16 MiB keep their own array.
- GPFifoDevice: every command segment the guest submits was copied into a
  new int[] by the thread that submits it, so the whole command stream was
  reallocated every frame. Segments of up to 1 MiB are now copied into
  arrays rented from a pool shared by the channels (up to 32 arrays per
  power-of-two size, so at most 64 MiB stay pooled) and returned once the
  GPU thread has processed them; larger segments keep their own array. The
  words are only read during Process and every consumer copies what it
  keeps. A segment pushed by the host keeps its own array.
- MemoryOwner<T>: the pool behind texture conversions and uploads kept one
  array per length and dropped every other array of that length when it was
  returned, so N same-sized uploads in flight left N-1 arrays to the GC. It
  now keeps all of them, up to 64 MiB per element type (the oldest entries
  make room), which also bounds a pool that had no bound (one array per
  distinct length, never trimmed).
- ThreadedRenderer: data passed to the render thread with a command (buffer
  uploads, per-draw state) goes through an 8 MiB ring; when the render thread
  is more than 8 MiB behind, every such span became a new array. The ring
  becomes 32 MiB.

No rendering path changes: the same bytes reach the same calls. Not measured
on an iPhone; no FPS gain is claimed. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    gpu = source / 'src/Ryujinx.Graphics.Gpu/Engine'
    dma = gpu / 'Dma/DmaClass.cs'
    once(dma, '''        private readonly DeviceState<DmaClassState> _state;
''', '''        private readonly DeviceState<DmaClassState> _state;

        // The destination bytes of a partial copy, reused by every copy of this engine.
        private const int MaxDestinationScratch = 16 * 1024 * 1024;
        private byte[] _destinationScratch;
''')
    once(dma, '''        /// <summary>
        /// Reads data from the class registers.
        /// </summary>''', '''        /// <summary>
        /// A buffer of <paramref name="size"/> bytes for the destination range of a partial copy.
        /// Copies run one at a time on the GPU thread, so the buffer is reused; a copy above
        /// 16 MiB gets its own array.
        /// </summary>
        private Span<byte> DestinationScratch(int size)
        {
            if (size > MaxDestinationScratch)
            {
                return new byte[size];
            }

            if (_destinationScratch == null || _destinationScratch.Length < size)
            {
                uint capacity = System.Numerics.BitOperations.RoundUpToPowerOf2((uint)Math.Max(size, 4096));

                _destinationScratch = new byte[Math.Min(capacity, (uint)MaxDestinationScratch)];
            }

            return _destinationScratch.AsSpan(0, size);
        }

        /// <summary>
        /// Reads data from the class registers.
        /// </summary>''')
    once(dma, '''                // OPT: This allocates a (potentially) huge temporary array and then copies an existing
                // region of memory into it, data that might get overwritten entirely anyways. Ideally this should
                // all be rewritten to use pooled arrays, but that gets complicated with packed data and strides
                Span<byte> dstSpan = memoryManager.GetSpan(dstGpuVa + (ulong)dstBaseOffset, dstSize).ToArray();
''', '''                // The destination range is read into this engine's buffer, patched there and
                // written back whole, as before; only the array per copy is gone.
                Span<byte> dstSpan = DestinationScratch(dstSize);
                memoryManager.GetSpan(dstGpuVa + (ulong)dstBaseOffset, dstSize).CopyTo(dstSpan);
''')

    fifo = gpu / 'GPFifo/GPFifoDevice.cs'
    once(fifo, '''            public int[] Words;
''', '''            public int[] Words;

            /// <summary>
            /// True when <see cref="Words"/> was rented from the prefetch pool; it can be longer than the entry.
            /// </summary>
            public bool PooledWords;
''')
    once(fifo, '''                Words = GetWords(memoryManager, true).ToArray();
''', '''                ReadOnlySpan<int> words = GetWords(memoryManager, true);

                Words = _wordPool.Rent(words.Length);
                PooledWords = true;
                words.CopyTo(Words);
''')
    once(fifo, '''                return Words ?? GetWords(memoryManager, flush);
''', '''                return Words != null ? new ReadOnlySpan<int>(Words, 0, (int)EntryCount) : GetWords(memoryManager, flush);
''')
    once(fifo, '''        private readonly ConcurrentQueue<CommandBuffer> _commandBufferQueue;
''', '''        private readonly ConcurrentQueue<CommandBuffer> _commandBufferQueue;

        // Prefetched command words, returned once the GPU thread has processed them. Shared by every
        // channel; each power-of-two size up to 1 MiB keeps up to 32 arrays (64 MiB at most).
        private static readonly System.Buffers.ArrayPool<int> _wordPool = System.Buffers.ArrayPool<int>.Create(1 << 18, 32);
''')
    once(fifo, '''                entry.Processor.Process(entry.EntryAddress, words);
''', '''                entry.Processor.Process(entry.EntryAddress, words);

                if (entry.PooledWords)
                {
                    _wordPool.Return(entry.Words);
                }
''')

    owner = source / 'src/Ryujinx.Common/Memory/MemoryOwner.cs'
    once(owner, '''                public int SkipCount;
                public readonly T[]? Array = array;
''', '''                public int SkipCount;
                public long Stamp;
                public readonly T[]? Array = array;
''')
    once(owner, '''            private const int MaxSkipCount = 50;
''', '''            private const int MaxSkipCount = 50;

            // Arrays kept for reuse, several of one length included, up to this many bytes; the
            // oldest entries make room.
            private const long MaxPooledBytes = 64L * 1024 * 1024;
            private static long _pooledBytes;
            private static long _stamp;
''')
    once(owner, '''                        _pool.Remove(holder);
                        return holder.Array!;
''', '''                        RemoveLocked(index);
                        return holder.Array!;
''')
    once(owner, '''            public static void Return(T[] array)
            {

                lock (_lock)
                {
                    Holder holder = new(array);
                    int i = _pool.BinarySearch(holder);
                    if (i < 0)
                    {
                        _pool.Insert(~i, holder);
                    }
''', '''            public static void Return(T[] array)
            {
                long bytes = Bytes(array);

                if (bytes > MaxPooledBytes)
                {
                    return;
                }

                lock (_lock)
                {
                    // Keep every returned array: a frame uploads many textures of one size, and
                    // keeping only one array per length left the others to the GC.
                    while (_pool.Count > 0 && _pooledBytes + bytes > MaxPooledBytes)
                    {
                        RemoveLocked(OldestLocked());
                    }

                    Holder holder = new(array) { Stamp = ++_stamp };
                    int i = _pool.BinarySearch(holder);
                    _pool.Insert(i >= 0 ? i : ~i, holder);
                    _pooledBytes += bytes;
''')
    once(owner, '''                                _pool.Remove(h);
                                index--;
''', '''                                RemoveLocked(index);
                                index--;
''')
    once(owner, '''                        _maxCacheCount = _pool.Count * 2;
                    }
                }
            }
''', '''                        _maxCacheCount = _pool.Count * 2;
                    }
                }
            }

            private static long Bytes(T[] array) => (long)array.Length * Unsafe.SizeOf<T>();

            private static int OldestLocked()
            {
                int oldest = 0;

                for (int index = 1; index < _pool.Count; index++)
                {
                    if (_pool[index].Stamp < _pool[oldest].Stamp)
                    {
                        oldest = index;
                    }
                }

                return oldest;
            }

            private static void RemoveLocked(int index)
            {
                _pooledBytes -= Bytes(_pool[index].Array!);
                _pool.RemoveAt(index);
            }
''')

    renderer = source / 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
    once(renderer, 'private const int SpanPoolBytes = 8 * 1024 * 1024;', 'private const int SpanPoolBytes = 32 * 1024 * 1024;')
    return [dma, fifo, owner, renderer]
