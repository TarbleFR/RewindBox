"""The texture arrays' change rings skip, without a dictionary lookup, the textures that were never in any array (every title).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journal, pid 5954, [MeloNX:hot] profiles of GPU.MainThread in the
world): Dictionary<__Canon, NativeLibraryStatus>.FindValue, which is Dictionary<Texture, int>.FindValue
(CacheEntry.Textures), became a hot spot with adapt_array_dirty_log (up to 5.1 % of the thread's running samples). The
two walks of the rings (SynchronizeMemory, ValidateTextures) look up every texture signalled since the array's last
complete state in that array's Textures, in every bound array: arrays x signals lookups, most of them for textures that
are in no array at all (render targets, copy destinations, textures bound outside bindless arrays).

Change: a texture records, the first time it is put into any array's Textures (the three insertions in
TextureBindingsArrayCache.cs), that it has been in one (Texture.InBindlessArray, set and never cleared, GPU thread like
the insertions and the walks). The two walks test that flag before the lookup. A texture never inserted cannot be in a
Textures dictionary, so no entry the walks acted on is skipped: the same textures are synchronised, blacklisted and
compared as before.

Expected on the device: FindValue's share of GPU.MainThread lower. Not measured on an iPhone. Applied after
adapt_array_dirty_log (its post-images). Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on
drift.
"""
import hashlib
from adapt_session import once

TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
ARRAYS = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
BASELINE = {
    TEXTURE: '48cd31ddbb6f3294a41a873774d63c980e26f4e918eef4634fdc2dd781c06ce0',
    ARRAYS: '5dc66bb904fb9426ccb9bbe9a8fafc4d67e55c6ec59f15a3120d1bcfe22eef79',
}

FIELD_OLD = '''        private System.WeakReference<Texture> _logReference;
'''
FIELD_NEW = '''        private System.WeakReference<Texture> _logReference;

        // RewindBox (adapt_array_log_membership): set when the texture is first put into a texture array's Textures, never
        // cleared (GPU thread). A texture without it is in no array: the walks of the rings skip it without a lookup.
        internal bool InBindlessArray;
'''

DELTA_OLD = '''                        Textures[texture] = sequence;
'''
DELTA_NEW = '''                        texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                        Textures[texture] = sequence;
'''

FULL_OLD = '''
                            entry.Textures[texture] = texture.InvalidatedSequence;
'''
FULL_NEW = '''
                            texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                            entry.Textures[texture] = texture.InvalidatedSequence;
'''

SINGLE_OLD = '''
                        entry.Textures[texture] = texture.InvalidatedSequence;
'''
SINGLE_NEW = '''
                        texture.InBindlessArray = true; // RewindBox (adapt_array_log_membership)
                        entry.Textures[texture] = texture.InvalidatedSequence;
'''

SYNC_OLD = '''if (Texture.TryReadDirtyLog(entry, out Texture logged) && Textures.ContainsKey(logged))'''
SYNC_NEW = '''if (Texture.TryReadDirtyLog(entry, out Texture logged) && logged.InBindlessArray && Textures.ContainsKey(logged))'''

VALIDATE_OLD = '''                        if (Texture.TryReadInvalidationLog(entry, out Texture moved) &&
                            Textures.TryGetValue(moved, out int recorded) && moved.InvalidatedSequence != recorded)'''
VALIDATE_NEW = '''                        if (Texture.TryReadInvalidationLog(entry, out Texture moved) && moved.InBindlessArray &&
                            Textures.TryGetValue(moved, out int recorded) && moved.InvalidatedSequence != recorded)'''

PAIRS = ((TEXTURE, FIELD_OLD, FIELD_NEW), (ARRAYS, DELTA_OLD, DELTA_NEW), (ARRAYS, FULL_OLD, FULL_NEW),
         (ARRAYS, SINGLE_OLD, SINGLE_NEW), (ARRAYS, SYNC_OLD, SYNC_NEW), (ARRAYS, VALIDATE_OLD, VALIDATE_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    # The three insertions are the only writes into an array's Textures (besides its creation and Clear/Remove).
    text = paths[ARRAYS].read_text(encoding='utf-8-sig')
    assert not digests or (text.count('Textures[texture] = ') == 3 and 'Textures.Add(' not in text and
                           'Textures.TryAdd(' not in text), ARRAYS
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
