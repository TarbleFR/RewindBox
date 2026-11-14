"""Guest memory accesses find their address space partition without the partitions' lock (every title; host-tracked memory).

IPA 736 / Core c4a25b94, Hogwarts Legacy (private journal, pid 2349, five [MeloNX:hot] profiles in the world, 774 running
samples of GPU.MainThread): MemoryManagerHostTracked.TryGetVirtualContiguous 49 samples (6.3 %), under it
AddressSpacePartitioned.HasAnyPrivateAllocation 39 (5.0 %), FindPartition 27 (3.5 %), Monitor.Enter 32 and
Lock.TryEnterSlow 31 (4.0 %: the contended path, which spins and yields). Read in the source: every read of guest
memory by the GPU thread (GetSpan) calls FindPartition, which takes lock (_partitions) to search the list of 32 MiB
partitions. The same object is the lock Map, Unmap and Reprotect hold while they change host mappings and protections,
and the lock the partitions' allocations take in their fault handler: the lookup waits behind each of them.

Change (AddressSpacePartitioned.cs only): the list's partitions are also kept in an array, published under the lock
after every change of the list (insertions in EnsurePartitionsLocked, the removal of an emptied partition in Unmap,
Dispose) and read by FindPartition without the lock. A partition's bounds never change (AddressSpacePartition.Address
and Size are set once), and what a caller then asks of the partition is protected by the partition's own lock, as
before. As before too, a partition returned by the lookup can be emptied and removed by another thread before the
caller uses it: the lock was released when the lookup returned. FindPartitionWithIndex (Reprotect) and the callers that
already hold the lock are unchanged.

Expected on the device: Lock.TryEnterSlow under TryGetVirtualContiguous gone from GPU.MainThread's profile (4.0 % of
its running samples) and FindPartition's share lower; the same bytes read. Refuted and removed if a guest memory access
faults in the partition lookup. Rollback: drop this adapter from prepare_embedded.py and ORDER.
Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

SPACE = 'src/Ryujinx.Cpu/Jit/HostTracked/AddressSpacePartitioned.cs'
BASELINE = {SPACE: '8c0d31eeda4ccd28d1249aac90dc11b2ceaf44362c2272d383a7db7a16a7b841'}

FIELD_OLD = '''        // Accessed under _partitions. List mutations invalidate the cached index.
        private int _lastPartitionIndex = -1;
'''
FIELD_NEW = FIELD_OLD + '''
        // RewindBox (adapt_partition_snapshot): the list's partitions in order, published under _partitions after every
        // change of the list and read without the lock (a partition's bounds never change); the index of the last one
        // a lookup returned, a hint checked against the array it is used with.
        private AddressSpacePartition[] _snapshot = [];
        private int _snapshotHint;

        private void PublishPartitions()
        {
            System.Threading.Volatile.Write(ref _snapshot, _partitions.ToArray());
        }
'''

REMOVE_OLD = '''                        _lastPartitionIndex = -1;
                        _partitions.Remove(partition);
                        partition.Dispose();
'''
REMOVE_NEW = '''                        _lastPartitionIndex = -1;
                        _partitions.Remove(partition);
                        PublishPartitions(); // RewindBox (adapt_partition_snapshot): before the partition is disposed
                        partition.Dispose();
'''

ENSURE_OLD = '''            if (va < endVa)
            {
                _partitions.Add(CreateAsPartition(va, endVa - va));
            }

            ValidatePartitionList();
'''
ENSURE_NEW = '''            if (va < endVa)
            {
                _partitions.Add(CreateAsPartition(va, endVa - va));
            }

            // RewindBox (adapt_partition_snapshot): this method only inserts.
            if (_partitions.Count != _snapshot.Length)
            {
                PublishPartitions();
            }

            ValidatePartitionList();
'''

FIND_OLD = '''        private AddressSpacePartition FindPartition(ulong va)
        {
            lock (_partitions)
            {
                int index = FindPartitionIndexLocked(va);
                if (index >= 0)
                {
                    return _partitions[index];
                }
            }

            return null;
        }
'''
FIND_NEW = '''        private AddressSpacePartition FindPartition(ulong va)
        {
            // RewindBox (adapt_partition_snapshot): the published array, without the lock that Map, Unmap, Reprotect and
            // the partitions' fault handlers hold while they work.
            AddressSpacePartition[] partitions = System.Threading.Volatile.Read(ref _snapshot);
            int hint = _snapshotHint;

            if ((uint)hint < (uint)partitions.Length)
            {
                AddressSpacePartition last = partitions[hint];

                if (va >= last.Address && va < last.EndAddress)
                {
                    return last;
                }
            }

            int left = 0;
            int right = partitions.Length - 1;

            while (left <= right)
            {
                int middle = left + ((right - left) >> 1);
                AddressSpacePartition partition = partitions[middle];

                if (partition.Address <= va && partition.EndAddress > va)
                {
                    _snapshotHint = middle;

                    return partition;
                }

                if (partition.Address >= va)
                {
                    right = middle - 1;
                }
                else
                {
                    left = middle + 1;
                }
            }

            return null;
        }
'''

DISPOSE_OLD = '''                _partitions.Clear();
                _lastPartitionIndex = -1;
                _asAllocator.Dispose();
'''
DISPOSE_NEW = '''                _partitions.Clear();
                _lastPartitionIndex = -1;
                PublishPartitions(); // RewindBox (adapt_partition_snapshot)
                _asAllocator.Dispose();
'''

PAIRS = ((FIELD_OLD, FIELD_NEW), (REMOVE_OLD, REMOVE_NEW), (ENSURE_OLD, ENSURE_NEW), (FIND_OLD, FIND_NEW), (DISPOSE_OLD, DISPOSE_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[SPACE], old, new)
    return list(paths.values())
