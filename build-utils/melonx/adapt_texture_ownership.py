"""Balance pool references and schedule obsolete render textures for expiry.

Pool.Dispose calls TexturePool.Delete once per occupied descriptor slot, even
when several slots refer to one texture. The wildcard overload must therefore
release exactly one owner from the specified pool, not erase every pool's
owners and decrement only once. Explicit-ID removal remains idempotent.

The automatic short-cache overload is for textures that do not already have a
short-cache entry. Its inverted guard left obsolete render targets resident
and replaced existing entries without releasing their references. Keep the
existing two-tick grace period and all view, binding and GPU lifetime rules.
"""
from adapt_session import once


def apply(source):
    texture = source / 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
    cache = source / 'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs'

    once(texture, '''                    if (_poolOwners[i].Pool == pool && _poolOwners[i].ID == id || id == -1)
                    {
                        _poolOwners.RemoveAt(i--);
                        references++;
                    }
''', '''                    if (_poolOwners[i].Pool == pool && (id == -1 || _poolOwners[i].ID == id))
                    {
                        // Pool.Dispose releases one occupied descriptor slot per call.
                        // Keep other slots, and other pools, paired with their references.
                        _poolOwners.RemoveAt(i);
                        references++;
                        break;
                    }
''')

    once(cache, '''        public void AddShortCache(Texture texture)
        {
            if (texture.ShortCacheEntry != null)
''', '''        public void AddShortCache(Texture texture)
        {
            if (texture.ShortCacheEntry == null)
''')

    return [texture, cache]
