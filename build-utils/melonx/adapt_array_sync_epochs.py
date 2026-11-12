"""A bound texture array is walked when one of its textures needs it, not at every update (next Core candidate).

IPA 729 / Core 743, Hogwarts Legacy 1x (pid 58475), "gpuWork" of the 5 s performance windows during play
(12:48:30-12:50:27): arrayDelta (TextureBindingsArrayCache.UpdateFromPoolDelta) 170-534 calls and 459-1 136 ms per
window, 0.9 ms per call at the start of play, 2.8-6.7 ms after 100 s; "bindings", which contains it, 956-1 773 ms per
window: a fifth to a third of the GPU thread. The time per call follows the number of textures the array holds, not
the number of elements that changed.

Cause read in the source: each update of a pool array walks every texture of the array three times.
CollectLoggedChanges calls ValidateTextures (one walk comparing each texture's InvalidatedSequence), then
SynchronizeMemoryAndValidate walks them to call Texture.SynchronizeMemory on each (which, for a texture that is not
dirty, only stamps LastUseEpoch, a clock in seconds) and walks them again to validate. The cache-hit path does the
same three walks. Every walk touches each Texture object of an array of several thousand.

Change:
- Texture.cs: SignalGroupDirty, the only writer of a texture's dirty flag after its creation, moves a process-wide
  DirtyEpoch after setting the flag, and the three places that move InvalidatedSequence go through one method; both
  count their writers in flight (DirtyWriters, InvalidationWriters), so a reader that finds no writer and an unmoved
  epoch knows that nothing was signalled since it last read the epoch, from any thread. SetScale's four scale mode
  assignments go through AssignScaleMode, which moves DirtyEpoch when a texture leaves Blacklisted (a view follows
  its storage's mode and a storage its view's; found by the independent review of the first version, which assumed
  a blacklisted mode stayed).
- TextureBindingsArrayCache.cs (CacheEntry): ValidateTextures returns at once when no InvalidatedSequence moved since
  its last complete walk and the set was not refilled. SynchronizeMemory returns after synchronising only the
  textures added since its last complete walk when, since that walk, no texture was signalled dirty, the use clock
  did not tick, the access is not a store and every texture was already blacklisted for scaling if that is asked;
  if one of those synchronisations signals a texture dirty, the complete walk runs in the same call. Otherwise it
  walks as before. A store access always walks (SignalModified is per call).
What each texture receives is unchanged: the same LastUseEpoch after every call (the walk runs at each tick of the
clock), a dirty texture is synchronised at the first update after its signal as before, the same SignalModified and
scale blacklist. Not changed: what an update resolves, sends to the backend, or when it rebuilds.

Expected on the device (same save and route): arrayDelta under 200 ms per 5 s window after 100 s of play (from
700-1 136) and "bindings" lower by at least the same amount; refuted, and the adapter removed, if arrayDelta stays
above 500 ms or a texture shows stale content. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
BASELINE = {
    TEXTURE: '8b17f16bcd0fbf363cd9a8c5074a52e97aabe0ec687ea5f2d5751bad2a20cde1',
    CACHE: 'c64415fc5128087b8c4371b16a9aa0d51b4367a51844961abd0a30438b1aaf04',
}

EPOCH_OLD = '''        internal static int InvalidationEpoch;
'''
EPOCH_NEW = '''        internal static int InvalidationEpoch;

        // RewindBox (adapt_array_sync_epochs): the calls of MoveInvalidatedSequence in flight, on any thread. A reader
        // that finds none and InvalidationEpoch where it read it before walking a set of textures knows that no
        // InvalidatedSequence moved since that walk read it.
        internal static int InvalidationWriters;

        // RewindBox (adapt_array_sync_epochs): DirtyEpoch moves at every SignalGroupDirty, after the flag is set;
        // DirtyWriters counts the calls in flight. A reader that finds none and DirtyEpoch where it read it before
        // walking a set of textures knows that none of them was signalled dirty since that walk read its flag.
        internal static int DirtyEpoch;
        internal static int DirtyWriters;

        /// <summary>RewindBox (adapt_array_sync_epochs): the texture use clock of this texture's context (seconds).</summary>
        internal int ContextUseEpoch => _context.TextureUseEpoch;

        private void MoveInvalidatedSequence()
        {
            System.Threading.Interlocked.Increment(ref InvalidationWriters);
            InvalidatedSequence++;
            System.Threading.Interlocked.Increment(ref InvalidationEpoch);
            System.Threading.Interlocked.Decrement(ref InvalidationWriters);
        }

        // RewindBox (adapt_array_sync_epochs): SetScale gives a view its storage's scale mode and a storage its view's,
        // so a texture can leave Blacklisted without a new storage. A bound array's walk blacklists it again: the change
        // is signalled as a dirty flag is, and the next update of every array walks.
        private static void AssignScaleMode(Texture texture, TextureScaleMode mode)
        {
            bool leavesBlacklist = texture.ScaleMode == TextureScaleMode.Blacklisted && mode != TextureScaleMode.Blacklisted;

            if (leavesBlacklist)
            {
                System.Threading.Interlocked.Increment(ref DirtyWriters);
            }

            texture.ScaleMode = mode;

            if (leavesBlacklist)
            {
                System.Threading.Interlocked.Increment(ref DirtyEpoch);
                System.Threading.Interlocked.Decrement(ref DirtyWriters);
            }
        }
'''

# The four assignments of SetScale (the constructors' and BlacklistScale's are not changed: a new texture enters an array
# through a noted addition or a refill, and BlacklistScale only enters the blacklist).
SCALE_PAIRS = (
    ('''                _viewStorage.ScaleMode = newScaleMode;
''', '''                AssignScaleMode(_viewStorage, newScaleMode); // RewindBox (adapt_array_sync_epochs)
'''),
    ('''                    view.ReplaceStorage(newView);
                    view.ScaleMode = newScaleMode;
''', '''                    view.ReplaceStorage(newView);
                    AssignScaleMode(view, newScaleMode); // RewindBox (adapt_array_sync_epochs)
'''),
    ('''                ScaleMode = newScaleMode;

                foreach (Texture view in _views)
                {
                    view.ScaleMode = newScaleMode;
                }
''', '''                AssignScaleMode(this, newScaleMode); // RewindBox (adapt_array_sync_epochs)

                foreach (Texture view in _views)
                {
                    AssignScaleMode(view, newScaleMode); // RewindBox (adapt_array_sync_epochs): same statement as above
                }
'''),
)

DIRTY_OLD = '''        public void SignalGroupDirty()
        {
            _dirty = true;
        }
'''
DIRTY_NEW = '''        public void SignalGroupDirty()
        {
            // RewindBox (adapt_array_sync_epochs): counted in flight, and the epoch moves once the flag is set.
            System.Threading.Interlocked.Increment(ref DirtyWriters);
            _dirty = true;
            System.Threading.Interlocked.Increment(ref DirtyEpoch);
            System.Threading.Interlocked.Decrement(ref DirtyWriters);
        }
'''

TAIL = '''            InvalidatedSequence++;
            System.Threading.Interlocked.Increment(ref InvalidationEpoch);
'''
CALL = '''            MoveInvalidatedSequence(); // RewindBox (adapt_array_sync_epochs)
'''
# The three places that move a texture's sequence, each with the lines that precede it there.
MOVE_CONTEXTS = ('''                _physicalMemory.TextureCache.RemoveShortCache(this);
            }

''', '''                _poolOwners.Clear();
            }

''', '''        private void DisposeTextures()
        {
''')
MOVE_PAIRS = tuple((context + TAIL, context + CALL) for context in MOVE_CONTEXTS)

FIELDS_OLD = '''            private Dictionary<Texture, int> _deltaReferences;
'''
FIELDS_NEW = '''            private Dictionary<Texture, int> _deltaReferences;

            // RewindBox (adapt_array_sync_epochs): what the last complete walk of Textures by SynchronizeMemory
            // established (Texture.DirtyEpoch read before it, the use clock it stamped, whether it blacklisted the
            // scale), the textures added since, and the same for ValidateTextures. Not current after a refill.
            private bool _syncCurrent;
            private bool _syncedBlacklisted;
            private int _syncedDirtyEpoch;
            private int _syncedUseEpoch;
            private Texture _syncSource;
            private List<Texture> _unsynced;
            private bool _validationCurrent;
            private int _validatedEpoch;

            private const int UnsyncedLimit = 256;

            // A texture entered the set after the last complete walk, with its current sequence: it is synchronised by
            // the next call, alone if nothing else asks for a walk.
            private void NoteTextureAdded(Texture texture)
            {
                if (!_syncCurrent)
                {
                    return;
                }

                if ((_unsynced ??= new List<Texture>()).Count >= UnsyncedLimit)
                {
                    _syncCurrent = false;
                    _unsynced.Clear();

                    return;
                }

                _unsynced.Add(texture);
            }

            private void ForgetWalks()
            {
                _syncCurrent = false;
                _validationCurrent = false;
                _syncSource = null;
                _unsynced?.Clear();
            }
'''

ADDED_OLD = '''                        Textures[texture] = sequence;
'''
ADDED_NEW = '''                        Textures[texture] = sequence;
                        NoteTextureAdded(texture); // RewindBox (adapt_array_sync_epochs)
'''

SYNC_OLD = '''            public void SynchronizeMemory(bool isStore, bool blacklistScale)
            {
                foreach (Texture texture in Textures.Keys)
                {
                    texture.SynchronizeMemory();

                    if (isStore)
                    {
                        texture.SignalModified();
                    }

                    if (blacklistScale && texture.ScaleMode != TextureScaleMode.Blacklisted)
                    {
                        // Scaling textures used on arrays is currently not supported.

                        texture.BlacklistScale();
                    }
                }
            }
'''
SYNC_NEW = '''            public void SynchronizeMemory(bool isStore, bool blacklistScale)
            {
                // RewindBox (adapt_array_sync_epochs): no SignalGroupDirty in flight, then the epoch, both before any
                // dirty flag is read.
                bool quiet = Volatile.Read(ref Texture.DirtyWriters) == 0;
                int dirtyEpoch = Volatile.Read(ref Texture.DirtyEpoch);

                if (!isStore && _syncCurrent && (!blacklistScale || _syncedBlacklisted) &&
                    quiet && dirtyEpoch == _syncedDirtyEpoch && _syncSource.ContextUseEpoch == _syncedUseEpoch)
                {
                    // Since the last complete walk no texture was signalled dirty and the use clock did not tick: every
                    // texture walked then would only be stamped with the same second again. Only the textures added
                    // since remain.
                    if (_unsynced == null || _unsynced.Count == 0)
                    {
                        return;
                    }

                    for (int index = 0; index < _unsynced.Count; index++)
                    {
                        Texture added = _unsynced[index];

                        if (!Textures.ContainsKey(added))
                        {
                            continue; // replaced again before this call
                        }

                        added.SynchronizeMemory();

                        if (blacklistScale && added.ScaleMode != TextureScaleMode.Blacklisted)
                        {
                            added.BlacklistScale();
                        }
                    }

                    _unsynced.Clear();

                    if (!blacklistScale)
                    {
                        _syncedBlacklisted = false;
                    }

                    if (Volatile.Read(ref Texture.DirtyWriters) == 0 && Volatile.Read(ref Texture.DirtyEpoch) == dirtyEpoch)
                    {
                        return;
                    }

                    // One of those synchronisations (or another thread) signalled a texture dirty: the complete walk.
                    dirtyEpoch = Volatile.Read(ref Texture.DirtyEpoch);
                }

                Texture source = null;
                int useEpoch = 0;

                foreach (Texture texture in Textures.Keys)
                {
                    if (source == null)
                    {
                        source = texture;
                        useEpoch = texture.ContextUseEpoch; // read before the first stamp
                    }

                    texture.SynchronizeMemory();

                    if (isStore)
                    {
                        texture.SignalModified();
                    }

                    if (blacklistScale && texture.ScaleMode != TextureScaleMode.Blacklisted)
                    {
                        // Scaling textures used on arrays is currently not supported.

                        texture.BlacklistScale();
                    }
                }

                _unsynced?.Clear();
                _syncSource = source;
                _syncCurrent = source != null;
                _syncedDirtyEpoch = dirtyEpoch;
                _syncedUseEpoch = useEpoch;
                _syncedBlacklisted = blacklistScale;
            }
'''

RESET_OLD = '''                Textures.Clear();
                DeltaReady = false;
'''
RESET_NEW = '''                Textures.Clear();
                ForgetWalks(); // RewindBox (adapt_array_sync_epochs): the set is refilled
                DeltaReady = false;
'''

VALIDATE_OLD = '''            public bool ValidateTextures()
            {
                foreach ((Texture texture, int invalidatedSequence) in Textures)
                {
                    if (texture.InvalidatedSequence != invalidatedSequence)
                    {
                        return false;
                    }
                }

                return true;
            }
'''
VALIDATE_NEW = '''            public bool ValidateTextures()
            {
                // RewindBox (adapt_array_sync_epochs): no sequence moved since the last complete walk found them all
                // current, and every texture added since was recorded with its sequence of that moment.
                bool quiet = Volatile.Read(ref Texture.InvalidationWriters) == 0;
                int epoch = Volatile.Read(ref Texture.InvalidationEpoch);

                if (quiet && _validationCurrent && epoch == _validatedEpoch)
                {
                    return true;
                }

                foreach ((Texture texture, int invalidatedSequence) in Textures)
                {
                    if (texture.InvalidatedSequence != invalidatedSequence)
                    {
                        _validationCurrent = false;

                        return false;
                    }
                }

                // The epoch was read before the walk: a sequence moved during it moves the epoch past this value.
                _validatedEpoch = epoch;
                _validationCurrent = quiet;

                return true;
            }
'''

TEXTURE_PAIRS = MOVE_PAIRS + SCALE_PAIRS + ((EPOCH_OLD, EPOCH_NEW), (DIRTY_OLD, DIRTY_NEW))
CACHE_PAIRS = ((FIELDS_OLD, FIELDS_NEW), (ADDED_OLD, ADDED_NEW), (SYNC_OLD, SYNC_NEW), (RESET_OLD, RESET_NEW),
               (VALIDATE_OLD, VALIDATE_NEW))
FILE_PAIRS = {TEXTURE: TEXTURE_PAIRS, CACHE: CACHE_PAIRS}
PAIRS = TEXTURE_PAIRS + CACHE_PAIRS


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
