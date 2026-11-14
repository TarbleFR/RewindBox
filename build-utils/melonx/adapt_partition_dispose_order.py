"""The partitioned address space publishes its empty list before it disposes its partitions (every title, session end).

adapt_partition_snapshot (IPA 736, second lot) made readers of AddressSpacePartitioned use a published array of the
partitions without the lock. Unmap publishes the new list before it disposes the partition it removes, but Dispose(bool)
disposed every partition first and published the empty list after: during a session's teardown or a change of game, a
guest or GPU thread still reading the previous snapshot could be handed a disposed partition for the length of the loop
(the window existed before the snapshot, since Dispose takes no lock, but the snapshot made it reachable without one).

Change (AddressSpacePartitioned.cs, Dispose(bool)): the list is emptied and published first, then the partitions taken
out of it are disposed, then the allocator, as Unmap orders it. No change while a session runs.

Not measured on an iPhone. Applied after adapt_partition_snapshot (its post-image). Rollback: drop this adapter from
prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

SPACE = 'src/Ryujinx.Cpu/Jit/HostTracked/AddressSpacePartitioned.cs'
BASELINE = {SPACE: 'b131af7c78d6e294205bc24c950d614537159d94ca15994d1893d2d9ae808af6'}

DISPOSE_OLD = '''            if (disposing)
            {
                foreach (AddressSpacePartition partition in _partitions)
                {
                    partition.Dispose();
                }

                _partitions.Clear();
                _lastPartitionIndex = -1;
                PublishPartitions(); // RewindBox (adapt_partition_snapshot)
                _asAllocator.Dispose();
            }
'''
DISPOSE_NEW = '''            if (disposing)
            {
                // RewindBox (adapt_partition_dispose_order): the empty list is published before the partitions taken out
                // of it are disposed, as Unmap orders it, so a reader of the snapshot is not handed a disposed partition.
                AddressSpacePartition[] partitions = _partitions.ToArray();

                _partitions.Clear();
                _lastPartitionIndex = -1;
                PublishPartitions(); // RewindBox (adapt_partition_snapshot)

                foreach (AddressSpacePartition partition in partitions)
                {
                    partition.Dispose();
                }

                _asAllocator.Dispose();
            }
'''


def apply(source):
    path = source / SPACE
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, SPACE
    once(path, DISPOSE_OLD, DISPOSE_NEW)
    return [path]
