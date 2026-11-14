"""A partition's private mappings are looked up in a published snapshot instead of under the tree's reader lock (every title).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journal, pid 5954, the four slow [MeloNX:hot] profiles of
GPU.MainThread, 544 running samples): TryGetVirtualContiguous -> HasAnyPrivateAllocation 31 samples (5.7 %),
HasAnyPrivateAllocation -> HasPrivateAllocation 24 (4.4 %), HasPrivateAllocation -> ReaderWriterLockSlim
TryEnterReadLockCore 9; self samples TryEnterReadLockCore 4, HasPrivateAllocation 4, FindPrivateMappingLocked 2,
PrivateMapping.CompareTo 2, GetNode 1, thread-static helpers of the lock 9 to 11. No reader-writer lock wait on any
profiled thread and no Update/MapPrivate sample: the cost is the uncontended lock (a spin-lock compare-and-swap and a
thread-static count on each enter and exit) and the tree walk behind it, about 18 to 21 of the 544 samples (3.3 to
3.9 %), roughly 0.7 to 1.0 ms of GPU-thread CPU per game frame at 15 to 21 game FPS (an upper bound for the frame
time: it reaches it only while the GPU thread is the producer's bottleneck). Every heap, MapPhysicalMemory and
MapMemory range is mapped Private, so ordinary GPU reads (GetSpan, GetRef, GetWritableRegion, TryGetContiguousSpan)
and the managed Read, Write, GetReadOnlySequence and GetHostRegions of every thread go through these lookups.

Change (AddressSpacePartition.cs, upstream file): the partition keeps `_privateSpans`, an array of (Address, Size,
PrivateAllocation) for every node of `_privateTree` in address order, built under the write lock and never written
after it is published: by the constructor, and in Update's finally before ExitWriteLock (nested try, so a failed
allocation cannot leave the write lock held). Update first withdraws it (Interlocked.Exchange to null, a full fence)
before it changes anything. HasPrivateAllocation, GetFirstPrivateAllocation and GetPrivateAllocation read it with
Volatile.Read, find the span holding `va` by binary search with PrivateMapping.CompareTo(ulong)'s comparisons, and
return what the locked walk returns for the same tree: the same node, the same Successor sequence, the same
expressions. While it is null (an Update in progress, or a copy that did not cover the whole tree) and for an address
outside the partition (no caller passes one), the unchanged locked walk below runs. Memory ordering: the array is
filled before its release store and read after an acquire load (stlr/ldar on ARM64), so a reader sees all of it; a
reader that loads a non-null array is linearized at that load, before the next Update's withdrawal. A reader racing
an Unmap no longer holds the Update off while it searches the array: the window in which the Update can unmap or free
an allocation the reader has just found grows by that search (tens of nanoseconds); readers arriving during the Update
wait on the lock as before. One array per Update, 48 bytes per node of the partition.

Scope: every title (MemoryManagerHostTracked). Expected on the device: in the [MeloNX:hot] profiles of GPU.MainThread,
HasPrivateAllocation's self samples and TryEnterReadLockCore under it near 0, HasAnyPrivateAllocation's edge down by
about 18 to 21 samples per 544. Not measured on an iPhone. Rollback: drop this adapter from prepare_embedded.py and
ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

PARTITION = 'src/Ryujinx.Cpu/Jit/HostTracked/AddressSpacePartition.cs'
BASELINE = {PARTITION: 'ca21f6c2737fb3e74dcdc35601f6471657a9f5951c572d30999121bb999b7d34'}

FIELD_OLD = '''        private PrivateMapping _lastPrivateMapping;

        private readonly ulong _hostPageSize;
'''
FIELD_NEW = '''        private PrivateMapping _lastPrivateMapping;

        // RewindBox (adapt_private_span_snapshot): every node of _privateTree in address order, copied under the write
        // lock and never written after it is published; null while an Update changes the tree (the lookups then take the
        // lock and wait for it, as before) or when the copy did not cover the whole tree.
        private readonly struct PrivateSpan
        {
            public readonly ulong Address;
            public readonly ulong Size;
            public readonly PrivateMemoryAllocation Allocation;

            public ulong EndAddress => Address + Size;

            public PrivateSpan(ulong address, ulong size, PrivateMemoryAllocation allocation)
            {
                Address = address;
                Size = size;
                Allocation = allocation;
            }
        }

        private PrivateSpan[] _privateSpans;

        // Under the write lock (or in the constructor). The elements are written before the release store that publishes
        // the array, so a reader's acquire load sees all of them.
        private void PublishPrivateSpans()
        {
            PrivateSpan[] spans = new PrivateSpan[_privateTree.Count];
            PrivateMapping map = _privateTree.GetNode(Address);
            int count = 0;

            for (; map != null && count < spans.Length; map = map.Successor)
            {
                spans[count++] = new(map.Address, map.Size, map.PrivateAllocation);
            }

            Volatile.Write(ref _privateSpans, map == null && count == spans.Length ? spans : null);
        }

        // The index of the span holding va, compared as PrivateMapping.CompareTo(ulong) compares it (the node
        // _privateTree.GetNode(va) returns), or -1 when no span holds it.
        private static int FindSpan(PrivateSpan[] spans, ulong va)
        {
            int left = 0;
            int right = spans.Length - 1;

            while (left <= right)
            {
                int middle = left + ((right - left) >> 1);
                ref readonly PrivateSpan span = ref spans[middle];

                if (va < span.Address)
                {
                    right = middle - 1;
                }
                else if (va <= span.EndAddress - 1UL)
                {
                    return middle;
                }
                else
                {
                    left = middle + 1;
                }
            }

            return -1;
        }

        private readonly ulong _hostPageSize;
'''

CONSTRUCTOR_OLD = '''            Address = address;
            Size = size;
        }
'''
CONSTRUCTOR_NEW = '''            Address = address;
            Size = size;

            PublishPrivateSpans(); // RewindBox (adapt_private_span_snapshot)
        }
'''

UPDATE_OLD = '''                Volatile.Write(ref _lastPrivateMapping, null);

                Mapping map = _mappingTree.GetNode(va);

                Update(map, va, pa, size, type);
            }
            finally
            {
                _treeLock.ExitWriteLock();
            }
'''
UPDATE_NEW = '''                Volatile.Write(ref _lastPrivateMapping, null);

                // RewindBox (adapt_private_span_snapshot): withdrawn before the tree changes, with a full fence; a lookup
                // that loads it from here on takes the lock and waits for this Update.
                Interlocked.Exchange(ref _privateSpans, null);

                Mapping map = _mappingTree.GetNode(va);

                Update(map, va, pa, size, type);
            }
            finally
            {
                // RewindBox (adapt_private_span_snapshot): republished before the lock is released, also after a throw;
                // the nested finally releases the lock if the copy cannot be allocated.
                try
                {
                    PublishPrivateSpans();
                }
                finally
                {
                    _treeLock.ExitWriteLock();
                }
            }
'''

GET_OLD = '''        public PrivateRange GetPrivateAllocation(ulong va)
        {
            _treeLock.EnterReadLock();
'''
GET_NEW = '''        public PrivateRange GetPrivateAllocation(ulong va)
        {
            // RewindBox (adapt_private_span_snapshot): the published spans without the lock; the locked walk below runs
            // while an Update changes the tree, or for an address outside the partition.
            PrivateSpan[] spans = Volatile.Read(ref _privateSpans);
            int index = spans == null ? -1 : FindSpan(spans, va);

            if (index >= 0)
            {
                ref readonly PrivateSpan span = ref spans[index];

                if (span.Allocation.IsValid)
                {
                    return new(span.Allocation.Memory, span.Allocation.Offset + (va - span.Address), span.Size - (va - span.Address));
                }

                return PrivateRange.Empty;
            }

            _treeLock.EnterReadLock();
'''

FIRST_OLD = '''        public PrivateRange GetFirstPrivateAllocation(ulong va, ulong size, out ulong nextVa)
        {
            _treeLock.EnterReadLock();
'''
FIRST_NEW = '''        public PrivateRange GetFirstPrivateAllocation(ulong va, ulong size, out ulong nextVa)
        {
            // RewindBox (adapt_private_span_snapshot): the published spans without the lock; the locked walk below runs
            // while an Update changes the tree, or for an address outside the partition.
            PrivateSpan[] spans = Volatile.Read(ref _privateSpans);
            int index = spans == null ? -1 : FindSpan(spans, va);

            if (index >= 0)
            {
                ref readonly PrivateSpan span = ref spans[index];

                nextVa = span.EndAddress;

                if (span.Allocation.IsValid)
                {
                    ulong spanOffset = va - span.Address;

                    return new(
                        span.Allocation.Memory,
                        span.Allocation.Offset + spanOffset,
                        Math.Min(span.Allocation.Size - spanOffset, size));
                }

                return PrivateRange.Empty;
            }

            _treeLock.EnterReadLock();
'''

HAS_OLD = '''        public bool HasPrivateAllocation(ulong va, ulong size, ulong startVa, ulong startSize, ref PrivateRange range)
        {
            ulong endVa = va + size;

            _treeLock.EnterReadLock();
'''
HAS_NEW = '''        public bool HasPrivateAllocation(ulong va, ulong size, ulong startVa, ulong startSize, ref PrivateRange range)
        {
            ulong endVa = va + size;

            // RewindBox (adapt_private_span_snapshot): the published spans without the lock, from the span holding va
            // along the following ones as the locked walk below follows Successor; that walk runs while an Update
            // changes the tree, or for an address outside the partition.
            PrivateSpan[] spans = Volatile.Read(ref _privateSpans);
            int index = spans == null ? -1 : FindSpan(spans, va);

            if (index >= 0)
            {
                for (; index < spans.Length && spans[index].Address < endVa; index++)
                {
                    ref readonly PrivateSpan span = ref spans[index];

                    if (span.Allocation.IsValid)
                    {
                        if (span.Address <= startVa && span.EndAddress >= startVa + startSize)
                        {
                            ulong spanOffset = startVa - span.Address;

                            range = new(
                                span.Allocation.Memory,
                                span.Allocation.Offset + spanOffset,
                                Math.Min(span.Allocation.Size - spanOffset, startSize));
                        }

                        return true;
                    }
                }

                return false;
            }

            _treeLock.EnterReadLock();
'''

PAIRS = ((FIELD_OLD, FIELD_NEW), (CONSTRUCTOR_OLD, CONSTRUCTOR_NEW), (UPDATE_OLD, UPDATE_NEW),
         (GET_OLD, GET_NEW), (FIRST_OLD, FIRST_NEW), (HAS_OLD, HAS_NEW))


def apply(source):
    path = source / PARTITION
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, PARTITION
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
