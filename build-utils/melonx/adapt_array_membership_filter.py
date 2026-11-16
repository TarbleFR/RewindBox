"""A texture array tests a 256-bit membership filter before it looks a signalled texture up in its set (every title).

Evidence (IPA 748-751 / Core 030cc14f, Hogwarts Legacy, private journals, [MeloNX:hot] profiles of GPU.MainThread; counts
and times only): Dictionary<__Canon, int>.FindValue, which is CacheEntry.Textures (Dictionary<Texture, int>), stays a
self hot spot after adapt_array_log_membership: 18 of 543, 14 of 357 and 12 of 206 running samples (33, 39 and 58 per
thousand; 28 of 544 in IPA 740), 0.87, 0.73 and 0.81 ms per game frame; 5, 9 and 10 of them have
CacheEntry.SynchronizeMemory as their recorded caller (0.24, 0.47 and 0.67 ms per game frame), the rest is lost to the
profiles' truncated edge lists. The InBindlessArray flag skips the textures that were never in any array, but every
logged texture that is in some array still costs Textures.ContainsKey (SynchronizeMemory, up to LogRounds = 3 times
from the same entry) or Textures.TryGetValue (ValidateTextures) in every bound array, member of that array or not.

Change (Texture.cs, TextureBindingsArrayCache.cs, on the post-image of adapt_array_log_membership):
- Texture.ArrayFilterBit: a byte fixed at construction (a process-wide counter, Fibonacci-hashed), never written again.
- CacheEntry: four ulongs, the bits of the textures put into its Textures. NoteMember sets the bit at the three
  insertions (the delta path of RecordDelta and the two whole rebuilds of UpdateFromPool and UpdateFromBuffer, next to
  the membership flag), Reset clears the filter with the set. MayContain tests a bit.
- The two walks of the change rings (SynchronizeMemory, ValidateTextures) test MayContain(texture.ArrayFilterBit) after
  InBindlessArray and before the dictionary lookup.
Exact: every key of Textures has its bit set (each insertion sets it first, Remove only takes keys out, Clear runs with
the filter's clear in Reset). A texture whose bit is clear is not in the set, so the lookup it skips would have answered
no. The set and its filter are written and read on the thread that owns the cache entry (as the dictionary already is);
the bit is an immutable field of the texture the ring entry resolved to, so no ordering with the ring's writers is
involved and the walks' acceptance protocol (writers in flight, epoch, overrun) is unchanged. A bit set by another
texture only costs the lookup made today. The adapter refuses a cache whose writes into Textures are not exactly the
three insertions (each after the membership flag), one Remove and one Clear (in Reset), with no Add, TryAdd or
CollectionsMarshal.

Departure from plan 740 lot 6b: the plan stored the filter byte in a second ring next to each weak reference, read by
Volatile.Read before the reference. Two slot arrays written one after the other can disagree when a writer is overtaken
by a full lap of the ring (1 024 appends) between its two stores, a case where the reference alone is still right; the
byte kept on the texture cannot disagree with it, and the plan's Volatile.Read of the byte has no object left (an
immutable field read through the reference the ring published). What this does not skip is the resolution of the weak
reference (Texture.TryReadLog, 4 self samples in IPA 740, not in the plan's bound).

Host proof (gate array-sync-epochs, final preparation): a small array updated while another cache's textures are
signalled leaves the control's states at every step; the same fixture with the filter answering yes gives the same
report with more lookups keyed by a texture (64 against 446 over 40 updates of that array, twice), and with the filter
answering no it fails. Fixture counts, not a device measure.

Scope: every texture and image array (CacheEntry of pool and of buffer arrays); no title policy. Bound (plan 748 rank
14, not measured): at most FindValue's share under the two walks, between 0.24-0.67 ms (recorded edge) and 0.73-0.87 ms
(self) per game frame of the GPU thread; nothing for the pool arrays, whose thousands of textures fill the filter.
Memory: 32 bytes per cache entry, one byte per texture. Expected on the device: FindValue's self samples on GPU.MainThread
lower in the [MeloNX:hot] profiles; no log line changes. Not measured on an iPhone. Rollback: drop this adapter from
prepare_embedded.py and ORDER (no other adapter edits these files after it). Fail closed on drift.
"""
import hashlib
import re
from adapt_session import once

TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
ARRAYS = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
BASELINE = {
    TEXTURE: '278c1b4ca4af3e9c76f8991129b56f5754eda2c883909024329099caa64c0201',  # adapt_array_log_membership's post-image
    ARRAYS: 'b488adf496e16f42e8a949e0b3812310b9ce3df3314c321a45c96afa941678d7',  # adapt_array_log_membership's post-image
}

BIT_OLD = '''        internal bool InBindlessArray;
'''
BIT_NEW = '''        internal bool InBindlessArray;

        // RewindBox (adapt_array_membership_filter): this texture's bit in the 256-bit membership filter of the texture
        // arrays, fixed at construction. An array whose filter lacks it does not hold the texture.
        private static int _arrayFilterSeed;
        internal readonly byte ArrayFilterBit =
            (byte)(unchecked((uint)System.Threading.Interlocked.Increment(ref _arrayFilterSeed) * 2654435761u) >> 24);
'''

FILTER_OLD = '''            private const int UnsyncedLimit = 256;
'''
FILTER_NEW = '''            private const int UnsyncedLimit = 256;

            // RewindBox (adapt_array_membership_filter): the ArrayFilterBit of every texture put into Textures (set before
            // each insertion, cleared with the set in Reset): a texture whose bit is clear is not in the set.
            private ulong _filter0, _filter1, _filter2, _filter3;

            public void NoteMember(Texture texture)
            {
                int bit = texture.ArrayFilterBit;
                ulong mask = 1UL << (bit & 63);

                switch (bit >> 6)
                {
                    case 0: _filter0 |= mask; break;
                    case 1: _filter1 |= mask; break;
                    case 2: _filter2 |= mask; break;
                    default: _filter3 |= mask; break;
                }
            }

            private bool MayContain(byte bit)
            {
                ulong word = (bit >> 6) switch { 0 => _filter0, 1 => _filter1, 2 => _filter2, _ => _filter3 };

                return ((word >> (bit & 63)) & 1) != 0;
            }
'''

DELTA_OLD = '''                        texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                        Textures[texture] = sequence;
'''
DELTA_NEW = '''                        texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                        NoteMember(texture); // RewindBox (adapt_array_membership_filter)
                        Textures[texture] = sequence;
'''

FULL_OLD = '''
                            texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                            entry.Textures[texture] = texture.InvalidatedSequence;
'''
FULL_NEW = '''
                            texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                            entry.NoteMember(texture); // RewindBox (adapt_array_membership_filter)
                            entry.Textures[texture] = texture.InvalidatedSequence;
'''

SINGLE_OLD = '''
                        texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                        entry.Textures[texture] = texture.InvalidatedSequence;
'''
SINGLE_NEW = '''
                        texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                        entry.NoteMember(texture); // RewindBox (adapt_array_membership_filter)
                        entry.Textures[texture] = texture.InvalidatedSequence;
'''

RESET_OLD = '''                Textures.Clear();
                ForgetWalks(); // RewindBox (adapt_array_sync_epochs): the set is refilled
'''
RESET_NEW = '''                Textures.Clear();
                _filter0 = _filter1 = _filter2 = _filter3 = 0; // RewindBox (adapt_array_membership_filter): with the set
                ForgetWalks(); // RewindBox (adapt_array_sync_epochs): the set is refilled
'''

SYNC_OLD = '''if (Texture.TryReadDirtyLog(entry, out Texture logged) && logged.InBindlessArray && Textures.ContainsKey(logged))'''
SYNC_NEW = '''if (Texture.TryReadDirtyLog(entry, out Texture logged) && logged.InBindlessArray &&
                                MayContain(logged.ArrayFilterBit) && Textures.ContainsKey(logged)) // RewindBox (adapt_array_membership_filter)'''

VALIDATE_OLD = '''                        if (Texture.TryReadInvalidationLog(entry, out Texture moved) && moved.InBindlessArray &&
                            Textures.TryGetValue(moved, out int recorded) && moved.InvalidatedSequence != recorded)'''
VALIDATE_NEW = '''                        if (Texture.TryReadInvalidationLog(entry, out Texture moved) && moved.InBindlessArray &&
                            MayContain(moved.ArrayFilterBit) && // RewindBox (adapt_array_membership_filter)
                            Textures.TryGetValue(moved, out int recorded) && moved.InvalidatedSequence != recorded)'''

PAIRS = ((TEXTURE, BIT_OLD, BIT_NEW), (ARRAYS, FILTER_OLD, FILTER_NEW), (ARRAYS, DELTA_OLD, DELTA_NEW),
         (ARRAYS, FULL_OLD, FULL_NEW), (ARRAYS, SINGLE_OLD, SINGLE_NEW), (ARRAYS, RESET_OLD, RESET_NEW),
         (ARRAYS, SYNC_OLD, SYNC_NEW), (ARRAYS, VALIDATE_OLD, VALIDATE_NEW))

# Every write into a CacheEntry's Textures (a private readonly field of a private nested class: only this file).
WRITES = re.compile(r'\bTextures(?:\.(?:Add|TryAdd|Remove|Clear)\(|\[[^\]]+\]\s*=(?!=))')
EXPECTED_WRITES = ['Textures.Clear(', 'Textures.Remove(', 'Textures[texture] =', 'Textures[texture] =', 'Textures[texture] =']
MEMBERSHIP_FLAG = 'texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)\n'


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    # Refused unless Textures is written exactly at the three insertions (each right after the membership flag), one
    # Remove and one Clear: a fourth insertion without NoteMember would let the filter skip a member.
    text = paths[ARRAYS].read_text(encoding='utf-8-sig')
    assert not digests or (sorted(w.replace(' ', '') for w in WRITES.findall(text)) ==
                           sorted(w.replace(' ', '') for w in EXPECTED_WRITES) and
                           len(re.findall(re.escape(MEMBERSHIP_FLAG) + r'\s*(?:entry\.)?Textures\[texture\] = ', text)) == 3 and
                           'CollectionsMarshal' not in text and len(re.findall(r'\bTextures = ', text)) == 1), ARRAYS
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
