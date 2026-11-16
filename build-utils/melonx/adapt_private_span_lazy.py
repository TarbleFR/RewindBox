"""A partition's private-span snapshot is rebuilt by the first lookup after an Update instead of by every Update (every
title).

Evidence (IPA 748-751 / Core 030cc14f, Hogwarts Legacy, private journals; counts and times only): adapt_private_span_snapshot
removed the reader lock from the GPU thread (TryGetVirtualContiguous 31 -> 11, 12 and 6 samples, TryEnterReadLockCore
4 -> 0), but its Update republishes a new array of _privateTree.Count spans in its finally at every Map and Unmap. In the
loading profile of Hogwarts session pid 12613 (3.9 FPS), Map -> PublishPrivateSpans weighs 36 of the 427 running samples
(8.4 %), 22 of the 130 of the guest's async loading thread (17 %, 9 of them self). In play, 10 samples in the slow 748
profiles (6 on the guest's main thread, 4 on its render thread) and 4 in the slow 749 profiles. A burst of
MapPhysicalMemory thus pays one O(n) copy and allocation per call, while one copy before the next lookup is enough.

Change (AddressSpacePartition.cs, on the post-image of adapt_private_span_snapshot):
- Update still withdraws `_privateSpans` (Interlocked.Exchange to null, a full fence) under the write lock before it
  changes either tree, and no longer republishes it: its finally only releases the write lock again (upstream's finally).
- FindPrivateMappingLocked, whose only callers are the locked paths of GetPrivateAllocation, GetFirstPrivateAllocation
  and HasPrivateAllocation (each holds the read lock around it), first rebuilds the array when it finds it null and
  publishes it with Interlocked.CompareExchange(ref _privateSpans, spans, null), still under the read lock; the lookup's
  own result is still the unchanged locked walk that follows. The constructor's publication is unchanged.
Exact: the tree is written only under the write lock (Update -> MapPrivate/UnmapPrivate, TryCoalesce) and in the
constructor; a reader that holds the read lock excludes every Update, so the array it builds is the tree as the walk sees
it, and a non-null array always equals the current tree: an Update withdraws it before any change, and nothing publishes
while the write lock is held. Readers that build at the same time build the same array and only the first is published
(the others are dropped). A lookup that finds the array null takes the lock, as before; one that loads a non-null array is
linearized at that load, as with adapt_private_span_snapshot. The lock-free lookups, FindSpan and the array layout are
unchanged; an address outside the partition (no caller passes one) still takes the walk without a rebuild.
Cost moved, not added: at most one copy per Update that a lookup follows (as before), none for Updates with no lookup
between them; that copy is now made by the first reader after the Update, under the read lock (an Update arriving then
waits for it, as a reader waited for the copy in Update before), and readers arriving together may each make it once.

Scope: every title (MemoryManagerHostTracked). Expected on the device: in the [MeloNX:hot] profiles, the
Map -> PublishPrivateSpans edge gone from loading bursts; PublishPrivateSpans, when sampled, under the lookups
(FindPrivateMappingLocked); the lock-free lookups as with adapt_private_span_snapshot. Bound (plan 748, rank 16): at most
8.4 % of the loading profile's running samples (17 % of the guest's loading thread), at most 10 and 4 samples in play. Not
measured on an iPhone. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

PARTITION = 'src/Ryujinx.Cpu/Jit/HostTracked/AddressSpacePartition.cs'
BASELINE = {PARTITION: '7270ef549443d50b2506bd909136fcef944fad4a02e18694a9d81ce23b694221'}

FIELD_OLD = '''        // RewindBox (adapt_private_span_snapshot): every node of _privateTree in address order, copied under the write
        // lock and never written after it is published; null while an Update changes the tree (the lookups then take the
        // lock and wait for it, as before) or when the copy did not cover the whole tree.
'''
FIELD_NEW = '''        // RewindBox (adapt_private_span_snapshot): every node of _privateTree in address order, never written after it is
        // published; null while an Update changes the tree (the lookups then take the lock and wait for it, as before)
        // or when the copy did not cover the whole tree. adapt_private_span_lazy: also null after an Update until the
        // first lookup that takes the read lock rebuilds it (FindPrivateMappingLocked).
'''

PUBLISH_OLD = '''        // Under the write lock (or in the constructor). The elements are written before the release store that publishes
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
'''
PUBLISH_NEW = '''        // RewindBox (adapt_private_span_lazy): in the constructor, or under the read lock by the first lookup after an
        // Update (FindPrivateMappingLocked): no Update runs meanwhile, and an Update withdraws the array before it changes
        // the tree. The elements are written before the compare-and-swap that publishes the array (a full fence), so a
        // reader's acquire load sees all of them; of readers building at the same time (the same array), the first
        // publishes. Nothing is published when the copy did not cover the whole tree.
        private void PublishPrivateSpans()
        {
            PrivateSpan[] spans = new PrivateSpan[_privateTree.Count];
            PrivateMapping map = _privateTree.GetNode(Address);
            int count = 0;

            for (; map != null && count < spans.Length; map = map.Successor)
            {
                spans[count++] = new(map.Address, map.Size, map.PrivateAllocation);
            }

            if (map == null && count == spans.Length)
            {
                Interlocked.CompareExchange(ref _privateSpans, spans, null);
            }
        }
'''

UPDATE_OLD = '''            finally
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
UPDATE_NEW = '''            finally
            {
                // RewindBox (adapt_private_span_lazy): left withdrawn, also after a throw; the first lookup after this
                // Update rebuilds it under the read lock (FindPrivateMappingLocked), so Updates with no lookup between
                // them copy nothing.
                _treeLock.ExitWriteLock();
            }
'''

FIND_OLD = '''        private PrivateMapping FindPrivateMappingLocked(ulong va)
        {
            PrivateMapping map = Volatile.Read(ref _lastPrivateMapping);
'''
FIND_NEW = '''        private PrivateMapping FindPrivateMappingLocked(ulong va)
        {
            // RewindBox (adapt_private_span_lazy): its only callers, the locked paths of GetPrivateAllocation,
            // GetFirstPrivateAllocation and HasPrivateAllocation, hold the read lock, so no Update runs: the first of them
            // after an Update republishes the spans for the lookups without the lock. Its own result is the walk below.
            if (Volatile.Read(ref _privateSpans) == null)
            {
                PublishPrivateSpans();
            }

            PrivateMapping map = Volatile.Read(ref _lastPrivateMapping);
'''

PAIRS = ((FIELD_OLD, FIELD_NEW), (PUBLISH_OLD, PUBLISH_NEW), (UPDATE_OLD, UPDATE_NEW), (FIND_OLD, FIND_NEW))


def apply(source):
    path = source / PARTITION
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, PARTITION
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
