"""A bound texture array synchronises and validates the textures that were signalled, not all of them (every title).

IPA 736 / Core c4a25b94, Hogwarts Legacy (private journals, pid 2349). The GPU thread dispatches 36.7 ms per game frame
in the world (frame_report with the stderr journal, seconds 50-250); its five [MeloNX:hot] profiles there (774 running
samples) put 17.2 % under TextureBindingsArrayCache.UpdateFromPool, of which the walks of every texture of the array:
CacheEntry.SynchronizeMemory 5.2 % and ValidateTextures 3.7 %, with 6.5 % of all samples in the dictionary enumerators
those walks run; the core windows count arrayDelta at 117 ms per second (median; 85 calls of 1.4 ms).
adapt_array_sync_epochs (Core 745) skips a walk only while no texture of the whole process was signalled dirty (or had
its storage replaced) since the last one: in a world that streams textures some texture is signalled at nearly every
update, so the arrays of several thousand textures are still walked (its own expectation, arrayDelta under 200 ms per
5 s window, is not met: 585 ms).

Change (Texture.cs, TextureBindingsArrayCache.cs):
- Texture.cs: the three writers of that protocol (SignalGroupDirty, AssignScaleMode when a texture leaves the scale
  blacklist, MoveInvalidatedSequence) also append the texture to a ring of 1 024 entries, after setting the flag (or
  the sequence) and before moving the epoch, still counted in flight. The rings hold weak references (one per texture,
  made at its first signal): nothing of a closed session is kept alive by them.
- CacheEntry.SynchronizeMemory: when the dirty epoch moved since its last complete state and the ring was not
  overrun, it synchronises (and blacklists, if asked) the textures added since and the logged textures that are in the
  array instead of walking them all; the state is taken as complete only if, after that, no writer is in flight and
  the epoch is where it was read before the ring (else it reads again, three times at most, then walks as before).
- CacheEntry.ValidateTextures: likewise, it compares the recorded sequence of the logged textures that are in the
  array; a mismatch is the same answer as before.
What each texture receives is unchanged: a texture signalled dirty is synchronised at the first update after its
signal, a texture that was not signalled would only have been stamped with the same second again (the use clock still
forces a complete walk at each tick), store accesses still walk. Not changed: what an update resolves or sends.

Why the log is complete: a writer sets its flag, then takes its ring index, then writes the slot, then moves the
epoch, all while counted in flight. A reader reads the in-flight count, the epoch, then the ring count, scans, and
accepts only if no writer is in flight and the epoch is unchanged: every writer whose epoch move it saw had written
its slot before the scan, and any other writer makes the acceptance fail. A complete walk records the ring count it
read before walking: what was signalled before is set before the walk starts, what is signalled later is logged later.

Expected on the device (same save and route): CacheEntry.SynchronizeMemory, ValidateTextures and the dictionary
enumerators under 2 % of GPU.MainThread's running samples together (15 % in IPA 736), arrayDelta under 300 ms per 5 s
window. Refuted and removed if a texture shows stale content or arrayDelta stays above 500 ms.
Rollback: drop this adapter from prepare_embedded.py and ORDER. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
BASELINE = {
    TEXTURE: 'c06dd5dcebd9faaa401d3f0d2d3bac189ebb6cbdf1f53da8b612ce507d7f2560',
    CACHE: 'bdbf01cb95b922f08fb26903ff92e99d71e67c9e1a71f0ed4463892488f07f5c',
}

LOG_OLD = '''        internal static int DirtyEpoch;
        internal static int DirtyWriters;
'''
LOG_NEW = LOG_OLD + '''
        // RewindBox (adapt_array_dirty_log): the textures the writers of the two protocols above signalled, in order: a
        // writer appends after setting its flag (or sequence) and before moving its epoch, still counted in flight. A
        // bound array that finds an epoch moved reads the entries appended since its last complete state. Weak
        // references (one per texture, made at its first signal): the rings keep nothing of a closed session alive.
        internal const int ChangeLogSize = 1024;
        internal static long DirtyLogCount;
        internal static long InvalidationLogCount;
        private static readonly System.WeakReference<Texture>[] _dirtyLog = new System.WeakReference<Texture>[ChangeLogSize];
        private static readonly System.WeakReference<Texture>[] _invalidationLog = new System.WeakReference<Texture>[ChangeLogSize];
        private System.WeakReference<Texture> _logReference;

        private static void LogChange(System.WeakReference<Texture>[] log, ref long count, Texture texture)
        {
            System.WeakReference<Texture> reference = texture._logReference ??= new System.WeakReference<Texture>(texture);
            long index = System.Threading.Interlocked.Increment(ref count) - 1;

            System.Threading.Volatile.Write(ref log[index & (ChangeLogSize - 1)], reference);
        }

        private static bool TryReadLog(System.WeakReference<Texture>[] log, long index, out Texture texture)
        {
            System.WeakReference<Texture> reference = System.Threading.Volatile.Read(ref log[index & (ChangeLogSize - 1)]);

            texture = null;

            return reference != null && reference.TryGetTarget(out texture);
        }

        internal static bool TryReadDirtyLog(long index, out Texture texture) => TryReadLog(_dirtyLog, index, out texture);

        internal static bool TryReadInvalidationLog(long index, out Texture texture) => TryReadLog(_invalidationLog, index, out texture);
'''

MOVE_OLD = '''            InvalidatedSequence++;
            System.Threading.Interlocked.Increment(ref InvalidationEpoch);
'''
MOVE_NEW = '''            InvalidatedSequence++;
            LogChange(_invalidationLog, ref InvalidationLogCount, this); // RewindBox (adapt_array_dirty_log)
            System.Threading.Interlocked.Increment(ref InvalidationEpoch);
'''

SCALE_OLD = '''            texture.ScaleMode = mode;

            if (leavesBlacklist)
            {
                System.Threading.Interlocked.Increment(ref DirtyEpoch);
'''
SCALE_NEW = '''            texture.ScaleMode = mode;

            if (leavesBlacklist)
            {
                LogChange(_dirtyLog, ref DirtyLogCount, texture); // RewindBox (adapt_array_dirty_log)
                System.Threading.Interlocked.Increment(ref DirtyEpoch);
'''

SIGNAL_OLD = '''            _dirty = true;
            System.Threading.Interlocked.Increment(ref DirtyEpoch);
'''
SIGNAL_NEW = '''            _dirty = true;
            LogChange(_dirtyLog, ref DirtyLogCount, this); // RewindBox (adapt_array_dirty_log)
            System.Threading.Interlocked.Increment(ref DirtyEpoch);
'''

FIELDS_OLD = '''            private bool _validationCurrent;
            private int _validatedEpoch;
'''
FIELDS_NEW = FIELDS_OLD + '''            // RewindBox (adapt_array_dirty_log): the ring counts those two states were read with.
            private long _syncedDirtyLog;
            private long _validatedLog;
            private const int LogRounds = 3;
'''

HEAD_OLD = '''                bool quiet = Volatile.Read(ref Texture.DirtyWriters) == 0;
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
'''
HEAD_NEW = '''                bool quiet = Volatile.Read(ref Texture.DirtyWriters) == 0;
                int dirtyEpoch = Volatile.Read(ref Texture.DirtyEpoch);
                long dirtyLog = Volatile.Read(ref Texture.DirtyLogCount); // RewindBox (adapt_array_dirty_log): after the epoch

                // RewindBox (adapt_array_dirty_log): the epoch may have moved, if the ring still holds every entry
                // appended since the last complete state.
                if (!isStore && _syncCurrent && (!blacklistScale || _syncedBlacklisted) &&
                    quiet && _syncSource.ContextUseEpoch == _syncedUseEpoch &&
                    (dirtyEpoch == _syncedDirtyEpoch || dirtyLog - _syncedDirtyLog <= Texture.ChangeLogSize))
                {
                    // Since the last complete state the use clock did not tick: every texture walked then would only be
                    // stamped with the same second again, unless it was signalled dirty since (those are in the ring).
                    // Only they and the textures added since remain.
                    bool signalled = dirtyEpoch != _syncedDirtyEpoch;

                    if (!signalled && (_unsynced == null || _unsynced.Count == 0))
                    {
                        return;
                    }

                    if (_unsynced != null && _unsynced.Count != 0)
                    {
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
                    }

                    for (int round = 0; round < LogRounds; round++)
                    {
                        // The textures signalled since the last complete state, from the same entry at every round.
                        for (long entry = _syncedDirtyLog; entry < dirtyLog; entry++)
                        {
                            if (Texture.TryReadDirtyLog(entry, out Texture logged) && Textures.ContainsKey(logged))
                            {
                                logged.SynchronizeMemory();

                                if (blacklistScale && logged.ScaleMode != TextureScaleMode.Blacklisted)
                                {
                                    logged.BlacklistScale();
                                }
                                else if (!blacklistScale)
                                {
                                    _syncedBlacklisted = false; // it may have left the blacklist
                                }
                            }
                        }

                        if (Volatile.Read(ref Texture.DirtyWriters) != 0)
                        {
                            break; // a writer in flight: its entry may not be written yet
                        }

                        if (Volatile.Read(ref Texture.DirtyEpoch) == dirtyEpoch)
                        {
                            // Complete: every signal up to this epoch was among the entries read.
                            _syncedDirtyEpoch = dirtyEpoch;
                            _syncedDirtyLog = dirtyLog;

                            return;
                        }

                        // One of those synchronisations (or another thread) signalled a texture dirty: read again.
                        dirtyEpoch = Volatile.Read(ref Texture.DirtyEpoch);
                        dirtyLog = Volatile.Read(ref Texture.DirtyLogCount);

                        if (dirtyLog - _syncedDirtyLog > Texture.ChangeLogSize)
                        {
                            break; // the ring was overrun
                        }
                    }

                    // A writer in flight, an overrun ring or too many rounds: the complete walk.
                    dirtyEpoch = Volatile.Read(ref Texture.DirtyEpoch);
                    dirtyLog = Volatile.Read(ref Texture.DirtyLogCount);
                }
'''

TAIL_OLD = '''                _syncedDirtyEpoch = dirtyEpoch;
                _syncedUseEpoch = useEpoch;
'''
TAIL_NEW = '''                _syncedDirtyEpoch = dirtyEpoch;
                _syncedDirtyLog = dirtyLog; // RewindBox (adapt_array_dirty_log): read before the walk
                _syncedUseEpoch = useEpoch;
'''

VALIDATE_OLD = '''                bool quiet = Volatile.Read(ref Texture.InvalidationWriters) == 0;
                int epoch = Volatile.Read(ref Texture.InvalidationEpoch);

                if (quiet && _validationCurrent && epoch == _validatedEpoch)
                {
                    return true;
                }
'''
VALIDATE_NEW = '''                bool quiet = Volatile.Read(ref Texture.InvalidationWriters) == 0;
                int epoch = Volatile.Read(ref Texture.InvalidationEpoch);
                long log = Volatile.Read(ref Texture.InvalidationLogCount); // RewindBox (adapt_array_dirty_log): after the epoch

                if (quiet && _validationCurrent && epoch == _validatedEpoch)
                {
                    return true;
                }

                // RewindBox (adapt_array_dirty_log): sequences moved since the last complete state: those textures are
                // in the ring; the ones of this array are compared with what was recorded, the others were not touched.
                if (quiet && _validationCurrent && log - _validatedLog <= Texture.ChangeLogSize)
                {
                    for (long entry = _validatedLog; entry < log; entry++)
                    {
                        if (Texture.TryReadInvalidationLog(entry, out Texture moved) &&
                            Textures.TryGetValue(moved, out int recorded) && moved.InvalidatedSequence != recorded)
                        {
                            _validationCurrent = false;

                            return false;
                        }
                    }

                    if (Volatile.Read(ref Texture.InvalidationWriters) == 0 && Volatile.Read(ref Texture.InvalidationEpoch) == epoch)
                    {
                        _validatedEpoch = epoch;
                        _validatedLog = log;

                        return true;
                    }

                    // A sequence moved meanwhile: the complete walk, with what is read now.
                    quiet = Volatile.Read(ref Texture.InvalidationWriters) == 0;
                    epoch = Volatile.Read(ref Texture.InvalidationEpoch);
                    log = Volatile.Read(ref Texture.InvalidationLogCount);
                }
'''

VTAIL_OLD = '''                _validatedEpoch = epoch;
                _validationCurrent = quiet;
'''
VTAIL_NEW = '''                _validatedEpoch = epoch;
                _validatedLog = log; // RewindBox (adapt_array_dirty_log): read before the walk
                _validationCurrent = quiet;
'''

FILE_PAIRS = {
    TEXTURE: ((LOG_OLD, LOG_NEW), (MOVE_OLD, MOVE_NEW), (SCALE_OLD, SCALE_NEW), (SIGNAL_OLD, SIGNAL_NEW)),
    CACHE: ((FIELDS_OLD, FIELDS_NEW), (HEAD_OLD, HEAD_NEW), (TAIL_OLD, TAIL_NEW),
            (VALIDATE_OLD, VALIDATE_NEW), (VTAIL_OLD, VTAIL_NEW)),
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
