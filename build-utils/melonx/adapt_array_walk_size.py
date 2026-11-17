"""GPU thread (every title): a bindless array entry walks its own textures when the change ring to read is longer.

IPA 764 / Core a80b212f, Hogwarts Legacy in the castle courtyard (private journals, pid 28682, profile #2 at 14.6 FPS;
docs/melonx-ipa764-journals-2026-11-17.md): the GPU thread runs 157 of 300 samples (about 36 ms per frame).
TextureBindingsManager.CommitTextureBindings holds 34 of them, the bindless arrays 23 (UpdateFromBuffer 13, UpdateFromPool
10), and under them CacheEntry.SynchronizeMemory at least 11 (5 on the path of a constant buffer whose handles did not
change), MayContain 4 of its own: the two walks of the global change rings call it, nothing else.

Read in the source (TextureBindingsArrayCache.cs, adapt_array_dirty_log and adapt_array_membership_filter): an array of
handles in a constant buffer covers the whole buffer, but its set (Textures) holds only the handles resolved, often a
few textures, and the key includes the buffer's bounds, so there are many such entries (about 0.56 separate array binds
per draw), each used rarely. At each use, SynchronizeMemory and ValidateTextures read the global ring from the entry's
last complete state, up to Texture.ChangeLogSize entries (and SynchronizeMemory up to LogRounds times): for each entry a
weak reference resolved, InBindlessArray, MayContain, the set's lookup. Their complete walk, the code they fall back to
when the ring was overrun, a writer was in flight or the rounds ran out, visits the set once: for a texture with nothing
to synchronise, Texture.SynchronizeMemory is one store and two tests.

Change (TextureBindingsArrayCache.cs only): the ring is read only while the entries to read are not more than the set's
textures (SynchronizeMemory's condition and its rounds, ValidateTextures' condition); otherwise the complete walk runs.
The return when nothing moved stays immediate.

Exact: the complete walk is the code the entry already runs whenever the ring is not read, and it synchronises (or
compares) every texture of the set, which covers every texture the ring names; on the ring's preconditions the use clock
has not ticked, so the use stamps it writes are the values already there. Same textures, samplers, arrays sent and
uploads; the writers' protocol (DirtyWriters, epochs, rings) is unchanged; Textures.Count belongs to the GPU thread. An
entry never visits more than before: a set larger than the ring to read keeps the ring.

Expected on the device: UpdateFromBuffer's SynchronizeMemory site and MayContain under the journal's threshold
(computed 5 to 7 of the GPU thread's 157 samples, about 1.1 to 1.6 ms per frame; not measured). No gain for the pool
arrays, whose sets are larger. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

ARRAYS = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
# The preparation of Core a80b212f (IPA 764): TextureBindingsArrayCache.cs after adapt_array_membership_filter.
BASELINE = {ARRAYS: 'eb4307153bc50466f662e2275f03399dd3bb67c24372e5af1c9daf791f840aa9'}

SYNC_OLD = '''                if (!isStore && _syncCurrent && (!blacklistScale || _syncedBlacklisted) &&
                    quiet && _syncSource.ContextUseEpoch == _syncedUseEpoch &&
                    (dirtyEpoch == _syncedDirtyEpoch || dirtyLog - _syncedDirtyLog <= Texture.ChangeLogSize))
'''
SYNC_NEW = '''                // RewindBox (adapt_array_walk_size): and only while the entries to read are not more than the set's textures
                // (more: the complete walk below visits fewer).
                if (!isStore && _syncCurrent && (!blacklistScale || _syncedBlacklisted) &&
                    quiet && _syncSource.ContextUseEpoch == _syncedUseEpoch &&
                    (dirtyEpoch == _syncedDirtyEpoch ||
                     (dirtyLog - _syncedDirtyLog <= Texture.ChangeLogSize && dirtyLog - _syncedDirtyLog <= Textures.Count)))
'''

ROUND_OLD = '''                        if (dirtyLog - _syncedDirtyLog > Texture.ChangeLogSize)
                        {
                            break; // the ring was overrun
                        }
'''
ROUND_NEW = '''                        if (dirtyLog - _syncedDirtyLog > Texture.ChangeLogSize ||
                            dirtyLog - _syncedDirtyLog > Textures.Count) // RewindBox (adapt_array_walk_size)
                        {
                            break; // the ring was overrun, or is now longer than the set
                        }
'''

VALIDATE_OLD = '''                if (quiet && _validationCurrent && log - _validatedLog <= Texture.ChangeLogSize)
'''
VALIDATE_NEW = '''                // RewindBox (adapt_array_walk_size): and only while the entries to read are not more than the set's textures.
                if (quiet && _validationCurrent && log - _validatedLog <= Texture.ChangeLogSize &&
                    log - _validatedLog <= Textures.Count)
'''

PAIRS = [
    (ARRAYS, SYNC_OLD, SYNC_NEW),
    (ARRAYS, ROUND_OLD, ROUND_NEW),
    (ARRAYS, VALIDATE_OLD, VALIDATE_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
