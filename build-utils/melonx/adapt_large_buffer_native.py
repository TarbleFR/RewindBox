"""MemoryOwner's large buffers (85 000 bytes or more, elements without references) are native memory instead of large
object heap arrays (every title).

Evidence (private journals of IPA 822, Hogwarts Legacy, 96 s of play; counts and durations only):
- The first-frame compaction (adapt_safe_point_compaction) left the large object heap (LOH) at 265 MiB with 0 MiB free;
  it was at 502 MiB 15 s later and 452 MiB with 115 to 250 MiB free after every later background collection. In the
  gcEvent lines the LOH bytes allocated between two background collections (occupied before the second less occupied
  after the first) were 221 MiB over the world load (04:30:27-32), then 26, 164, 97 and 19 MiB in the four intervals of
  play that follow (15-16 s each).
- Over the same intervals the GPU thread's texture synchronisation (core-performance gpuWork texSync: bytes allocated by
  the thread inside the scope) allocated 152, 17, 166, 70 and 21 MB, and its pooled guest reads (pooledReadBytes) were
  133, 21, 159, 81 and 19 MB: in play the texture data path is the LOH's churn (the world load adds about 80 MB of other
  large objects: that window's bindings allocate 213 MB).
- That path's buffers are all MemoryOwner<byte> rents: the guest copy of a non-contiguous texture range
  (PhysicalMemory.GetReadOnlyRegion), the linear layout (LayoutConverter), the decoders and transcoders, handed to
  ITexture.SetData and disposed by the render thread once copied into a staging buffer. The pool keeps one array per
  length plus 64 MiB of same-length spares and lets an array go 3 s after its return; a miss allocates the exact length.
  Each such array is a LOH object: every miss and every array let go is a hole in that heap, committed (and compressed
  by iOS) until a compaction, and every reuse of a hole touches its pages again.

Change (src/Ryujinx.Common/Memory/MemoryOwner.cs only): a pool miss of 85 000 bytes or more, for an element type without
references, allocates its elements with NativeMemory.AllocZeroed (zeroed, as a new array is) in a NativeBuffer, a
MemoryManager<T> that the holder keeps for its life; Span and Memory read it, Pin returns its address. Everything else
of the pool is unchanged: which buffer a rent takes (the same lengths, the smallest suitable, 4x at most), the spares and
their 64 MiB, the 3 s idle release, the skip-count purge, RentCleared and RentCopy, ownership and disposal. A buffer is
freed no earlier than 3 s after its last return: at once when the pool lets it go after its 3 s idle time, after a 3 s
quarantine when the pool lets it go sooner (over the spares' bound, a purge) or its owner was never disposed (its
finalizer quarantines it), so a span taken before its owner was disposed keeps valid memory for 3 s (a managed array
would have stayed alive under it). Arrays under 85 000 bytes stay managed. LargeBufferStatistics counts the native bytes
live, quarantined, at their peak, allocated and freed, and publishes a description through AppContext
("RewindBox.LargeBuffers") that adapt_device_pressure_compaction's lines carry.

Host (test/melonx_large_buffer_native_test.py: CoreCLR with the segments GC library, the Core's GC settings, a
texture-upload-shaped workload of 928 uploads, 719 MiB, a background gen2 every 2 s): the render thread copies the same
data bit for bit; large object heap allocations 452 -> 67 MB (what is left is the workload's own staging ring and its
long-lived large objects), its peak 207-211 -> 65 MB, the peak of committed plus native 301-305 -> 240 MiB, gen2
collections 23 -> 16; after a quiet period and a blocking gen2, 50 MiB of holes -> 0.2 MiB and committed 210 -> 159 MiB
with no native byte left (in one run of three that blocking gen2 compacted the control's LOH itself: ConserveMemory 5
past 50 % of fragmentation, which no play-time background collection does); the same
385 MiB of misses as native allocations (63), every one freed. The contract (span, memory, pin, hit and miss data,
clears, element types, idle release, quarantine, a leaked owner, 8 threads, the spares' bound) passes with CoreCLR and
with a NativeAOT build (regions GC there).

Bounds: the pool's retention rules are the ones above (no new one); the quarantine holds what the pool let go in the
last 3 s. Not changed: the data any rent returns (a miss is zeroed, a hit holds what its last user left, as before), the
GC configuration, any caller.
Expected on the device (Hogwarts Legacy, same route): gcEvent background lines with the LOH occupied before minus the
previous occupied after under 30 MiB per 15 s in play (IPA 822: 19 to 164), lohAfterBytes and lohFreeAfterBytes of the
memoryInventory lines under 350 and 120 MiB once the world is loaded (452 and 217 MiB); in the "memory pressureCompactions"
line at the session's end (adapt_device_pressure_compaction) "native large buffers live N MiB (peak P MiB ...)" with P
under 160 and "leaked" 0 or a few. Refuted if the LOH keeps growing the same way, or if any crash names NativeBuffer.
Not measured on an iPhone. Rollback: drop this adapter from prepare_embedded.py and ORDER (the pressure line then reads
"native large buffers none"). Fail closed on drift: the file must be the Core 827 preparation's.
"""
import hashlib
from adapt_session import once

OWNER = 'src/Ryujinx.Common/Memory/MemoryOwner.cs'
# The Core 827 preparation (after adapt_streaming_memory; no later adapter edits this file).
SPACES = ' ' * 16  # a whitespace-only line of the file
BASELINE = {OWNER: 'f94421c357ea252fd61e39c0e08969916eaaeb2327f4b1f60acd57300820d0ee'}

HOLDER_OLD = '''            public class Holder(T[]? array = null) : IComparable<Holder>, IComparable<int>
            {
                public int SkipCount;
                // Set while this array waits as a spare: its place in the age list and in its length's list.
                public LinkedListNode<Holder>? Spare;
                public LinkedListNode<Holder>? SameLength;
                public long Returned;
                public readonly T[]? Array = array;

                public int CompareTo(Holder? other)
                {
                    return Array!.Length.CompareTo(other!.Array!.Length);
                }
''' + SPACES + '''
                public int CompareTo(int other)
                {
                    int self = Array!.Length;
'''
HOLDER_NEW = '''            public class Holder : IComparable<Holder>, IComparable<int>
            {
                public int SkipCount;
                // Set while this array waits as a spare: its place in the age list and in its length's list.
                public LinkedListNode<Holder>? Spare;
                public LinkedListNode<Holder>? SameLength;
                public long Returned;
                public readonly T[]? Array;
                // RewindBox (adapt_large_buffer_native): a large buffer of elements without references is native memory
                // (Native, Array null); Length is the element count of either.
                public readonly NativeBuffer? Native;
                public readonly int Length;

                public Holder(T[] array)
                {
                    Array = array;
                    Length = array.Length;
                }

                public Holder(NativeBuffer native)
                {
                    Native = native;
                    Length = native.Length;
                }

                public int CompareTo(Holder? other)
                {
                    return Length.CompareTo(other!.Length);
                }
''' + SPACES + '''
                public int CompareTo(int other)
                {
                    int self = Length;
'''

NATIVE_OLD = '''            // ReSharper disable once StaticMemberInGenericType
            private static int _maxCacheCount = 50;
'''
NATIVE_NEW = '''            // RewindBox (adapt_large_buffer_native) begin
            // A buffer of 85 000 bytes or more would be a large object heap array: each miss and each array let go after
            // its idle time left a hole in that heap, committed until a compaction (IPA 822, Hogwarts Legacy: the texture
            // data path, 20 to 232 MiB of large objects between two background collections). Such a buffer of elements
            // without references is native memory, zeroed as a new array is. A buffer the pool lets go waits
            // QuarantineMilliseconds before it is freed, so no span taken from it before its owner was disposed outlives
            // its memory.
            public const long NativeMinimumBytes = 85000;
            public const int QuarantineMilliseconds = 3000;
            private static readonly bool _nativeEligible = !RuntimeHelpers.IsReferenceOrContainsReferences<T>();
            private static readonly List<(nint Pointer, long Bytes, long Released)> _quarantine = new();

            public sealed unsafe class NativeBuffer : MemoryManager<T>
            {
                private nint _pointer;
                public readonly int Length;

                public NativeBuffer(int length)
                {
                    Length = length;
                    _pointer = (nint)NativeMemory.AllocZeroed((nuint)length, (nuint)Unsafe.SizeOf<T>());
                    LargeBufferStatistics.Allocated(Bytes);
                }

                public long Bytes => (long)Length * Unsafe.SizeOf<T>();

                public override Span<T> GetSpan()
                {
                    nint pointer = Volatile.Read(ref _pointer);

                    if (pointer == 0)
                    {
                        ThrowObjectDisposedException();
                    }

                    return new Span<T>((void*)pointer, Length);
                }

                public override MemoryHandle Pin(int elementIndex = 0)
                {
                    ArgumentOutOfRangeException.ThrowIfGreaterThan((uint)elementIndex, (uint)Length, nameof(elementIndex));

                    nint pointer = Volatile.Read(ref _pointer);

                    if (pointer == 0)
                    {
                        ThrowObjectDisposedException();
                    }

                    return new MemoryHandle((byte*)pointer + (nint)elementIndex * Unsafe.SizeOf<T>());
                }

                public override void Unpin()
                {
                }

                // The pool owns the memory: only Detach (the quarantine) and the finalizer give it up.
                protected override void Dispose(bool disposing)
                {
                }

                public bool Detach(out nint pointer, out long bytes)
                {
                    pointer = Interlocked.Exchange(ref _pointer, 0);
                    bytes = Bytes;

                    if (pointer == 0)
                    {
                        return false;
                    }

                    GC.SuppressFinalize(this);

                    return true;
                }

                // An owner never disposed: its buffer is quarantined like any other the pool lets go, never freed here, so a
                // span still in use when its owner became unreachable keeps valid memory for QuarantineMilliseconds (CA2015).
#pragma warning disable CA2015
                ~NativeBuffer()
                {
                    nint pointer = Interlocked.Exchange(ref _pointer, 0);

                    if (pointer != 0)
                    {
                        LargeBufferStatistics.Leaked();

                        lock (_lock)
                        {
                            QuarantineLocked(pointer, Bytes, Environment.TickCount64);
                        }
                    }
                }
#pragma warning restore CA2015
            }

            private static Holder NewHolder(int length)
            {
                if (_nativeEligible && (long)length * Unsafe.SizeOf<T>() >= NativeMinimumBytes)
                {
                    return new Holder(new NativeBuffer(length));
                }

                return new Holder(new T[length]);
            }

            // A holder the pool lets go (idle, over the spares' bound, purged). Its native memory is freed
            // QuarantineMilliseconds after its last return at the earliest: at once for an idle one, later otherwise.
            private static void ReleaseLocked(Holder holder)
            {
                if (holder.Native != null && holder.Native.Detach(out nint pointer, out long bytes))
                {
                    if (Environment.TickCount64 - holder.Returned >= QuarantineMilliseconds)
                    {
                        FreeNative(pointer, bytes);
                    }
                    else
                    {
                        QuarantineLocked(pointer, bytes, holder.Returned);
                    }
                }
            }

            private static unsafe void FreeNative(nint pointer, long bytes)
            {
                NativeMemory.Free((void*)pointer);
                LargeBufferStatistics.Freed(bytes);
            }

            private static void QuarantineLocked(nint pointer, long bytes, long released)
            {
                _quarantine.Add((pointer, bytes, released));
                LargeBufferStatistics.Quarantined(bytes);

                if (!_arrayTrimScheduled)
                {
                    _arrayTrimScheduled = true;
                    (_arrayTimer ??= new Timer(ReleaseIdleArrays)).Change(QuarantineMilliseconds, Timeout.Infinite);
                }
            }

            // Frees what waited QuarantineMilliseconds; returns the time until the next one may be freed (or the full wait).
            private static long FreeQuarantinedLocked(long now)
            {
                long next = QuarantineMilliseconds;
                int writeIndex = 0;

                for (int index = 0; index < _quarantine.Count; index++)
                {
                    (nint pointer, long bytes, long released) = _quarantine[index];
                    long remaining = released + QuarantineMilliseconds - now;

                    if (remaining <= 0)
                    {
                        LargeBufferStatistics.Unquarantined(bytes);
                        FreeNative(pointer, bytes);
                    }
                    else
                    {
                        _quarantine[writeIndex++] = _quarantine[index];
                        next = Math.Min(next, remaining);
                    }
                }

                _quarantine.RemoveRange(writeIndex, _quarantine.Count - writeIndex);

                return next;
            }
            // RewindBox (adapt_large_buffer_native) end

            // ReSharper disable once StaticMemberInGenericType
            private static int _maxCacheCount = 50;
'''

SEARCH_OLD = '''                        if (list[mid].Array!.Length == size)
'''
SEARCH_NEW = '''                        if (list[mid].Length == size)
'''

GET_OLD = '''                        if (_sparesByLength.TryGetValue(holder.Array!.Length, out LinkedList<Holder>? spares))
                        {
                            Holder spare = spares.Last!.Value;
'''
GET_NEW = '''                        if (_sparesByLength.TryGetValue(holder.Length, out LinkedList<Holder>? spares))
                        {
                            Holder spare = spares.Last!.Value;
'''

MISS_OLD = '''                // A miss owns no pool entry. Allocate outside the shared lock so returns can proceed.
                return new Holder(new T[minimumSize]);
'''
MISS_NEW = '''                // A miss owns no pool entry. Allocate outside the shared lock so returns can proceed.
                // RewindBox (adapt_large_buffer_native): a large one in native memory.
                return NewHolder(minimumSize);
'''

PURGE_OLD = '''                                _pool.RemoveAt(index);
                                DropSparesLocked(h.Array!.Length);
                                index--;
'''
PURGE_NEW = '''                                _pool.RemoveAt(index);
                                DropSparesLocked(h.Length);
                                ReleaseLocked(h); // RewindBox (adapt_large_buffer_native)
                                index--;
'''

BYTES_OLD = '''            private static long Bytes(T[] array) => (long)array.Length * Unsafe.SizeOf<T>();

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
'''
BYTES_NEW = '''            private static long Bytes(Holder holder) => (long)holder.Length * Unsafe.SizeOf<T>();

            private static void KeepSpareLocked(Holder holder)
            {
                long bytes = Bytes(holder);

                if (bytes < MinSpareBytes || bytes > MaxSpareBytes)
                {
                    ReleaseLocked(holder); // RewindBox (adapt_large_buffer_native): not kept
                    return;
                }

                while (_spareBytes + bytes > MaxSpareBytes)
                {
                    Holder oldest = _spares.First!.Value;
                    RemoveSpareLocked(oldest);
                    ReleaseLocked(oldest); // RewindBox (adapt_large_buffer_native)
                }
'''

KEEP_OLD = '''                if (!_sparesByLength.TryGetValue(holder.Array!.Length, out LinkedList<Holder>? sameLength))
                {
                    sameLength = _spareLists.TryPop(out LinkedList<Holder>? reusable) ? reusable : new();
                    _sparesByLength[holder.Array!.Length] = sameLength;
                }
'''
KEEP_NEW = '''                if (!_sparesByLength.TryGetValue(holder.Length, out LinkedList<Holder>? sameLength))
                {
                    sameLength = _spareLists.TryPop(out LinkedList<Holder>? reusable) ? reusable : new();
                    _sparesByLength[holder.Length] = sameLength;
                }
'''

REMOVE_OLD = '''                _spareBytes -= Bytes(holder.Array!);

                if (sameLength.Count == 0)
                {
                    _sparesByLength.Remove(holder.Array!.Length);
'''
REMOVE_NEW = '''                _spareBytes -= Bytes(holder);

                if (sameLength.Count == 0)
                {
                    _sparesByLength.Remove(holder.Length);
'''

DROP_OLD = '''                while (_sparesByLength.TryGetValue(length, out LinkedList<Holder>? spares))
                {
                    RemoveSpareLocked(spares.First!.Value);
                }
'''
DROP_NEW = '''                while (_sparesByLength.TryGetValue(length, out LinkedList<Holder>? spares))
                {
                    Holder spare = spares.First!.Value;
                    RemoveSpareLocked(spare);
                    ReleaseLocked(spare); // RewindBox (adapt_large_buffer_native)
                }
'''

IDLE_OLD = '''                    long now = Environment.TickCount64;
                    long next = SpareIdleMilliseconds;
                    int writeIndex = 0;

                    for (int index = 0; index < _pool.Count; index++)
                    {
                        Holder holder = _pool[index];
                        long remaining = holder.Returned + SpareIdleMilliseconds - now;

                        if (remaining <= 0 && _sparesByLength.TryGetValue(holder.Array!.Length, out LinkedList<Holder>? spares))
                        {
                            // Keep a more recently returned spare as this length's primary array.
                            Holder newest = spares.Last!.Value;
                            RemoveSpareLocked(newest);
                            holder = newest;
                            remaining = newest.Returned + SpareIdleMilliseconds - now;
                        }

                        if (remaining > 0)
                        {
                            _pool[writeIndex++] = holder;
                            next = Math.Min(next, remaining);
                        }
                    }
'''
IDLE_NEW = '''                    long now = Environment.TickCount64;
                    // RewindBox (adapt_large_buffer_native): what waited its quarantine is freed first.
                    long next = Math.Min(SpareIdleMilliseconds, FreeQuarantinedLocked(now));
                    int writeIndex = 0;

                    for (int index = 0; index < _pool.Count; index++)
                    {
                        Holder holder = _pool[index];
                        long remaining = holder.Returned + SpareIdleMilliseconds - now;

                        if (remaining <= 0 && _sparesByLength.TryGetValue(holder.Length, out LinkedList<Holder>? spares))
                        {
                            // Keep a more recently returned spare as this length's primary array.
                            Holder newest = spares.Last!.Value;
                            RemoveSpareLocked(newest);
                            ReleaseLocked(holder); // RewindBox (adapt_large_buffer_native): the idle primary is let go
                            holder = newest;
                            remaining = newest.Returned + SpareIdleMilliseconds - now;
                        }

                        if (remaining > 0)
                        {
                            _pool[writeIndex++] = holder;
                            next = Math.Min(next, remaining);
                        }
                        else
                        {
                            ReleaseLocked(holder); // RewindBox (adapt_large_buffer_native)
                        }
                    }
'''

RESCHEDULE_OLD = '''                    _arrayTrimScheduled = _pool.Count != 0;
'''
RESCHEDULE_NEW = '''                    _arrayTrimScheduled = _pool.Count != 0 || _quarantine.Count != 0; // RewindBox (adapt_large_buffer_native)
'''

SPARES_OLD = '''                    while (_spares.First is { } oldest && now - oldest.Value.Returned >= SpareIdleMilliseconds)
                    {
                        RemoveSpareLocked(oldest.Value);
                    }
'''
SPARES_NEW = '''                    while (_spares.First is { } oldest && now - oldest.Value.Returned >= SpareIdleMilliseconds)
                    {
                        Holder spare = oldest.Value;
                        RemoveSpareLocked(spare);
                        ReleaseLocked(spare); // RewindBox (adapt_large_buffer_native)
                    }
'''

CLEARED_OLD = '''            result._holder!.Array.AsSpan(0, length).Clear();
'''
CLEARED_NEW = '''            result.Span.Clear(); // RewindBox (adapt_large_buffer_native): the array's or the native buffer's first length elements
'''

COPY_OLD = '''            buffer.CopyTo(result._holder!.Array);
'''
COPY_NEW = '''            buffer.CopyTo(result.Span); // RewindBox (adapt_large_buffer_native)
'''

MEMORY_OLD = '''                T[]? array = _holder?.Array;

                if (array is null)
                {
                    ThrowObjectDisposedException();
                }

                return new(array, 0, _length);
'''
MEMORY_NEW = '''                ArrayPooling.Holder? holder = _holder;

                if (holder is null)
                {
                    ThrowObjectDisposedException();
                }

                // RewindBox (adapt_large_buffer_native): a native buffer's Memory keeps its manager reachable.
                if (holder.Array is null)
                {
                    return holder.Native!.Memory[.._length];
                }

                return new(holder.Array, 0, _length);
'''

SPAN_OLD = '''                T[]? array = _holder?.Array;

                if (array is null)
                {
                    ThrowObjectDisposedException();
                }

                ref T firstElementRef = ref MemoryMarshal.GetArrayDataReference(array);
'''
SPAN_NEW = '''                ArrayPooling.Holder? holder = _holder;

                if (holder is null)
                {
                    ThrowObjectDisposedException();
                }

                T[]? array = holder.Array;

                // RewindBox (adapt_large_buffer_native): a native buffer's first _length elements.
                if (array is null)
                {
                    return holder.Native!.GetSpan()[.._length];
                }

                ref T firstElementRef = ref MemoryMarshal.GetArrayDataReference(array);
'''

THROW_OLD = '''        [DoesNotReturn]
        private static void ThrowObjectDisposedException()
        {
            throw new ObjectDisposedException(nameof(MemoryOwner<T>), "The buffer has already been disposed.");
        }
    }
}
'''
THROW_NEW = '''        [DoesNotReturn]
        private static void ThrowObjectDisposedException()
        {
            throw new ObjectDisposedException(nameof(MemoryOwner<T>), "The buffer has already been disposed.");
        }
    }

    // RewindBox (adapt_large_buffer_native): the native memory of MemoryOwner's large buffers (every element type), for
    // the journal. Live: allocated and not yet freed (in use, pooled, or quarantined); quarantined: let go by the pool and
    // waiting to be freed; leaked: buffers whose owner was never disposed (quarantined by their finalizer).
    public static class LargeBufferStatistics
    {
        private static long _liveBytes;
        private static long _peakBytes;
        private static long _quarantinedBytes;
        private static long _allocations;
        private static long _allocatedBytes;
        private static long _frees;
        private static long _leaked;

        // Published for the engine's journal (adapt_device_pressure_compaction reads it without a reference to this class).
        static LargeBufferStatistics()
        {
            AppContext.SetData("RewindBox.LargeBuffers", (Func<string>)Describe);
        }

        public static string Describe() =>
            $"native large buffers live {LiveBytes >> 20} MiB (peak {PeakBytes >> 20} MiB, quarantined {QuarantinedBytes >> 20} MiB), " +
            $"allocated {Allocations} ({AllocatedBytes >> 20} MiB), freed {Frees}, leaked {LeakedBuffers}";

        public static long LiveBytes => Interlocked.Read(ref _liveBytes);
        public static long PeakBytes => Interlocked.Read(ref _peakBytes);
        public static long QuarantinedBytes => Interlocked.Read(ref _quarantinedBytes);
        public static long Allocations => Interlocked.Read(ref _allocations);
        public static long AllocatedBytes => Interlocked.Read(ref _allocatedBytes);
        public static long Frees => Interlocked.Read(ref _frees);
        public static long LeakedBuffers => Interlocked.Read(ref _leaked);

        internal static void Allocated(long bytes)
        {
            Interlocked.Increment(ref _allocations);
            Interlocked.Add(ref _allocatedBytes, bytes);
            long live = Interlocked.Add(ref _liveBytes, bytes);
            long peak;

            while (live > (peak = Interlocked.Read(ref _peakBytes)) && Interlocked.CompareExchange(ref _peakBytes, live, peak) != peak)
            {
            }
        }

        internal static void Quarantined(long bytes) => Interlocked.Add(ref _quarantinedBytes, bytes);

        internal static void Unquarantined(long bytes) => Interlocked.Add(ref _quarantinedBytes, -bytes);

        internal static void Freed(long bytes)
        {
            Interlocked.Increment(ref _frees);
            Interlocked.Add(ref _liveBytes, -bytes);
        }

        internal static void Leaked() => Interlocked.Increment(ref _leaked);
    }
}
'''

PAIRS = (
    (HOLDER_OLD, HOLDER_NEW),
    (NATIVE_OLD, NATIVE_NEW),
    (SEARCH_OLD, SEARCH_NEW),
    (GET_OLD, GET_NEW),
    (MISS_OLD, MISS_NEW),
    (PURGE_OLD, PURGE_NEW),
    (BYTES_OLD, BYTES_NEW),
    (KEEP_OLD, KEEP_NEW),
    (REMOVE_OLD, REMOVE_NEW),
    (DROP_OLD, DROP_NEW),
    (IDLE_OLD, IDLE_NEW),
    (RESCHEDULE_OLD, RESCHEDULE_NEW),
    (SPARES_OLD, SPARES_NEW),
    (CLEARED_OLD, CLEARED_NEW),
    (COPY_OLD, COPY_NEW),
    (MEMORY_OLD, MEMORY_NEW),
    (SPAN_OLD, SPAN_NEW),
    (THROW_OLD, THROW_NEW),
)


def apply(source):
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter or a gate records the pairs
    for name, expected in digests:
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(source / OWNER, old, new)
    return [source / OWNER]
