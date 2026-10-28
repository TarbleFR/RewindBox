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
  reallocated every frame. Segments are now copied into arrays rented from
  the runtime's shared pool (ArrayPool<int>.Shared) and returned once the
  GPU thread has processed them. That pool drops, when a gen 2 collection
  runs, the arrays it has kept unused for about 10 s at high memory load
  (the load iOS reports during a large game), 60 s otherwise. Host
  harness: 28-69 times fewer bytes allocated than before. The words are
  only read during Process and every consumer copies what it keeps. A
  segment pushed by the host keeps its own array.
- MemoryOwner<T>: the pool behind texture conversions and uploads keeps one
  array per length and dropped every other array of that length when it was
  returned, so N same-sized uploads in flight left N-1 arrays to the GC, as
  large objects from 85,000 bytes. Such an array (85,000 bytes or more) now
  waits as a spare, outside the list the pool searches: that list, its
  search, skip counts and cleanup are unchanged, and when a rent takes a
  length's array, a spare of that length takes its place. Spares use at
  most 64 MiB per element type (the oldest go first), a timer releases each
  3 s after it was returned, and the cleanup that drops a length drops its
  spares. Host benchmark (x86-64, the .NET GC set as on iOS), 600 frames:
  4 uploads of 4 MiB per frame, gen 2 collections 237-245 -> 2 and GC
  pauses 235-252 ms -> 1 ms; 200 uploads of 256 KiB, 1,050-1,111 -> 10-20
  and 1.27-1.30 s -> 7-20 ms; peak working set 25-110 MiB higher.
- ThreadedRenderer: data passed to the render thread with a command (buffer
  uploads, per-draw state) goes through an 8 MiB ring; when the render thread
  is more than 8 MiB behind, every such span became a new array. The ring
  becomes 32 MiB, written in full by normal traffic, so 24 MiB more stay
  resident.

Memory kept for these: 16 MiB at most per GPU channel for the copy buffer,
64 MiB at most of pooled spares (each released 3 s after it was returned)
and 24 MiB for the ring; the word arrays are the runtime pool's. No
rendering path changes: the same bytes reach the same calls. Not measured
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

        // Prefetched command words, returned to the runtime's shared pool once the GPU thread has
        // processed them; that pool drops arrays left unused for a while when gen 2 collections run.
        private static readonly System.Buffers.ArrayPool<int> _wordPool = System.Buffers.ArrayPool<int>.Shared;
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
                // Set while this array waits as a spare: its place in the age list and in its length's list.
                public LinkedListNode<Holder>? Spare;
                public LinkedListNode<Holder>? SameLength;
                public long Returned;
                public readonly T[]? Array = array;
''')
    once(owner, '''            private const int MaxSkipCount = 50;
''', '''            private const int MaxSkipCount = 50;

            // Arrays of 85,000 bytes or more returned while their length is pooled wait as spares
            // instead of being dropped (a frame uploads several textures of one size), outside
            // _pool, which keeps one array per length as before. When a rent takes a length's
            // array, a spare of that length takes its place. Spares use at most 64 MiB; the oldest
            // go first, and a timer releases a spare 3 s after it was returned.
            private const long MinSpareBytes = 85000;
            private const long MaxSpareBytes = 64L * 1024 * 1024;
            private const int SpareIdleMilliseconds = 3000;
            private static readonly LinkedList<Holder> _spares = new();
            private static readonly Dictionary<int, LinkedList<Holder>> _sparesByLength = new();
            private static long _spareBytes;
            private static Timer? _spareTimer;
''')
    once(owner, '''                        _pool.Remove(holder);
                        return holder.Array!;
''', '''                        if (_sparesByLength.TryGetValue(holder.Array!.Length, out LinkedList<Holder>? spares))
                        {
                            Holder spare = spares.Last!.Value;
                            RemoveSpareLocked(spare);
                            _pool[index] = spare;
                        }
                        else
                        {
                            _pool.RemoveAt(index);
                        }

                        return holder.Array!;
''')
    once(owner, '''                    if (i < 0)
                    {
                        _pool.Insert(~i, holder);
                    }
''', '''                    if (i < 0)
                    {
                        _pool.Insert(~i, holder);
                    }
                    else
                    {
                        KeepSpareLocked(holder);
                    }
''')
    once(owner, '''                                _pool.Remove(h);
                                index--;
''', '''                                _pool.RemoveAt(index);
                                DropSparesLocked(h.Array!.Length);
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

            private static void KeepSpareLocked(Holder holder)
            {
                long bytes = Bytes(holder.Array!);

                if (bytes < MinSpareBytes || bytes > MaxSpareBytes)
                {
                    return;
                }

                while (_spareBytes + bytes > MaxSpareBytes)
                {
                    RemoveSpareLocked(_spares.First!.Value);
                }

                holder.Returned = Environment.TickCount64;
                holder.Spare = _spares.AddLast(holder);

                if (!_sparesByLength.TryGetValue(holder.Array!.Length, out LinkedList<Holder>? sameLength))
                {
                    _sparesByLength[holder.Array!.Length] = sameLength = new();
                }

                holder.SameLength = sameLength.AddLast(holder);
                _spareBytes += bytes;

                if (_spares.Count == 1)
                {
                    (_spareTimer ??= new Timer(ReleaseIdleSpares)).Change(SpareIdleMilliseconds, Timeout.Infinite);
                }
            }

            private static void RemoveSpareLocked(Holder holder)
            {
                LinkedList<Holder> sameLength = holder.SameLength!.List!;

                _spares.Remove(holder.Spare!);
                sameLength.Remove(holder.SameLength);
                holder.Spare = null;
                holder.SameLength = null;
                _spareBytes -= Bytes(holder.Array!);

                if (sameLength.Count == 0)
                {
                    _sparesByLength.Remove(holder.Array!.Length);
                }
            }

            private static void DropSparesLocked(int length)
            {
                while (_sparesByLength.TryGetValue(length, out LinkedList<Holder>? spares))
                {
                    RemoveSpareLocked(spares.First!.Value);
                }
            }

            private static void ReleaseIdleSpares(object? state)
            {
                lock (_lock)
                {
                    long now = Environment.TickCount64;

                    while (_spares.First is { } oldest && now - oldest.Value.Returned >= SpareIdleMilliseconds)
                    {
                        RemoveSpareLocked(oldest.Value);
                    }

                    if (_spares.First is { } next)
                    {
                        _spareTimer!.Change(Math.Max(1, next.Value.Returned + SpareIdleMilliseconds - now), Timeout.Infinite);
                    }
                }
            }
''')

    renderer = source / 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
    once(renderer, 'private const int SpanPoolBytes = 8 * 1024 * 1024;', 'private const int SpanPoolBytes = 32 * 1024 * 1024;')
    return [dma, fifo, owner, renderer]
