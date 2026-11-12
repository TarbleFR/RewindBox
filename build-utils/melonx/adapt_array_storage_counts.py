"""A texture array keeps its set of storages up to date from small element changes (Hogwarts Legacy policy).

IPA 727, Hogwarts Legacy (Core 737, pid 56836, 12 Nov; private journals, aggregates only), in play: the "Vulkan pass and
GPU detail" windows of 97-122 frames count 25 167-36 092 texture array barrier passes taking 240-290 ms of the render
thread per 5 s, of which "sets rebuilt 806-1 125 over 61-64 million elements": every element change that replaces a
storage (a bindless pool delta of about 40 elements) empties the array's storage set, and the next barrier pass walks
every element of the array again (about 54 000 per rebuild on average, up to 524 288) to collect its distinct storages.
GPU busy 13.5-17.4 ms per frame (31-33 %): the render thread, not the GPU, is the limit at 22-28 frames per second.

Change (TextureArray.cs only; under EncodingPolicy.IncrementalArrayDescriptors, which Library.cs sets for Hogwarts
Legacy only, like the other incremental array members): the array counts how many elements name each storage of its
set. The count is built by the existing full walk (the first pass, and every pass after a change it did not follow);
afterwards an element change of at most LargeChange elements moves one count per replaced element (a storage reaching
zero leaves the set at once, as the cleared set dropped it before; a new storage joins it), and the set is no longer
emptied nor walked again. A larger change, or any change while the counts are not valid, empties the set and marks it
for a full walk as before. A barrier pass after a counted change is never skipped as "the same set" by
adapt_array_barrier_epoch: the set did change. Not changed: which storages a pass visits (the set is the distinct
non-null storages of the elements, as the walk builds it), the barrier decision (TextureStorage.QueueWriteToReadBarrier),
buffer arrays, every other title (the policy is off: every path is the delivered one). The order in which a pass visits
the storages of its set may differ from a fresh walk's (a HashSet's order follows its history); each storage's barrier
is queued independently of the others.
Expected: the 61-64 million element visits per 5 s fall to the walks that large changes still require. Not measured on
an iPhone: the next session's "sets rebuilt ... over ... elements" and texture array barrier pass times decide it.
Rollback: remove this adapter. Fail closed on drift: TextureArray.cs must be the Core 739 preparation's.
"""
import hashlib
from adapt_session import once

ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
BASELINE = {
    ARRAY: 'e62eb2f3e25cbccc3f7ce6dfd77c8c5ab29de9561ee429742506067748d19b57',
}
TAG = 'RewindBox (adapt_array_storage_counts)'

FIELDS_OLD = '''        private HashSet<TextureStorage> _storages;
        private bool _storagesDirty = true;
'''
FIELDS_NEW = '''        private HashSet<TextureStorage> _storages;
        private bool _storagesDirty = true;

        // RewindBox (adapt_array_storage_counts): under the incremental policy, how many elements name each storage of
        // _storages (valid once a full walk has counted them, until a change they do not follow); a counted change that
        // altered the set makes the next barrier pass run.
        private Dictionary<TextureStorage, int> _storageCounts;
        private bool _storageCountsValid;
        private bool _storageSetChanged;
'''
COUNTED_OLD = '''            bool counted = _incremental && !_referencesInvalid && textures.Length <= LargeChange;
'''
COUNTED_NEW = '''            bool counted = _incremental && !_referencesInvalid && textures.Length <= LargeChange;
            // RewindBox (adapt_array_storage_counts): a small change moves the storage counts instead of emptying the set.
            bool countedStorages = _incremental && _storageCountsValid && _storages != null && !_storagesDirty &&
                textures.Length <= LargeChange;
'''
VIEW_OLD = '''                    TextureView previous = _views[index + i];
                    storageChanged |= !ReferenceEquals(previous?.Storage, view.Storage);
'''
VIEW_NEW = '''                    TextureView previous = _views[index + i];
                    storageChanged |= !ReferenceEquals(previous?.Storage, view.Storage);

                    if (countedStorages && !ReferenceEquals(previous?.Storage, view.Storage))
                    {
                        MoveStorage(previous?.Storage, view.Storage); // RewindBox (adapt_array_storage_counts)
                    }
'''
NULL_OLD = '''                    TextureView previous = _views[index + i];
                    storageChanged |= previous?.Storage != null;
'''
NULL_NEW = '''                    TextureView previous = _views[index + i];
                    storageChanged |= previous?.Storage != null;

                    if (countedStorages && previous?.Storage != null)
                    {
                        MoveStorage(previous.Storage, null); // RewindBox (adapt_array_storage_counts)
                    }
'''
DIRTY_CALL_OLD = '''            SetDirty(storageChanged);
        }
'''
DIRTY_CALL_NEW = '''            // RewindBox (adapt_array_storage_counts): a counted change has kept the set up to date; any other empties it.
            _storageSetChanged |= storageChanged && countedStorages;
            SetDirty(storageChanged && !countedStorages);
        }
'''
CLEAR_OLD = '''                _storages?.Clear();
                _storagesDirty = true;
'''
CLEAR_NEW = '''                _storages?.Clear();
                _storagesDirty = true;
                _storageCountsValid = false; // RewindBox (adapt_array_storage_counts)
'''
MOVE_OLD = '''        private void SetDirty(bool storageChanged)
        {
'''
MOVE_NEW = '''        // RewindBox (adapt_array_storage_counts): one element moved from `previous` to `current` (either may be null).
        private void MoveStorage(TextureStorage previous, TextureStorage current)
        {
            if (previous != null && _storageCounts.TryGetValue(previous, out int count))
            {
                if (count <= 1)
                {
                    _storageCounts.Remove(previous);
                    _storages.Remove(previous);
                }
                else
                {
                    _storageCounts[previous] = count - 1;
                }
            }

            if (current != null)
            {
                ref int slot = ref CollectionsMarshal.GetValueRefOrAddDefault(_storageCounts, current, out bool exists);
                slot++;

                if (!exists)
                {
                    _storages.Add(current);
                }
            }
        }

        private void SetDirty(bool storageChanged)
        {
'''
SAME_OLD = '''            bool sameSet = _storages != null && !_storagesDirty;
'''
SAME_NEW = '''            bool sameSet = _storages != null && !_storagesDirty && !_storageSetChanged; // RewindBox (adapt_array_storage_counts)
'''
WALK_OLD = '''            if (_storagesDirty)
            {
                for (int index = 0; index < _views.Length; index++)
                {
                    // RewindBox (adapt_bindless_retention): the storage of the element's view.
                    TextureStorage storage = _views[index]?.Storage;

                    if (storage != null)
                    {
                        storages.Add(storage);
                    }
                }

                _storagesDirty = false;
'''
WALK_NEW = '''            if (_storagesDirty)
            {
                // RewindBox (adapt_array_storage_counts): the walk also counts the elements of each storage.
                if (_incremental)
                {
                    (_storageCounts ??= new Dictionary<TextureStorage, int>()).Clear();
                }

                for (int index = 0; index < _views.Length; index++)
                {
                    // RewindBox (adapt_bindless_retention): the storage of the element's view.
                    TextureStorage storage = _views[index]?.Storage;

                    if (storage != null)
                    {
                        storages.Add(storage);

                        if (_incremental)
                        {
                            CollectionsMarshal.GetValueRefOrAddDefault(_storageCounts, storage, out _)++;
                        }
                    }
                }

                _storageCountsValid = _incremental;
                _storagesDirty = false;
'''
EPOCH_OLD = '''            _barrierEpoch = epoch;
'''
EPOCH_NEW = '''            _barrierEpoch = epoch;
            _storageSetChanged = false; // RewindBox (adapt_array_storage_counts)
'''
PAIRS = [(ARRAY, FIELDS_OLD, FIELDS_NEW), (ARRAY, COUNTED_OLD, COUNTED_NEW), (ARRAY, VIEW_OLD, VIEW_NEW), (ARRAY, NULL_OLD, NULL_NEW),
         (ARRAY, DIRTY_CALL_OLD, DIRTY_CALL_NEW), (ARRAY, CLEAR_OLD, CLEAR_NEW), (ARRAY, MOVE_OLD, MOVE_NEW), (ARRAY, SAME_OLD, SAME_NEW),
         (ARRAY, WALK_OLD, WALK_NEW), (ARRAY, EPOCH_OLD, EPOCH_NEW)]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
