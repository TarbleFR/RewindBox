"""Distribute bindless-cache keys by the fields that already define equality.

Buffer-backed bindings previously hashed only their constant-buffer range.
Every handle offset, target, array length and pool using that buffer therefore
shared a Dictionary collision chain, even on the unchanged-bindings fast path.
Pool-backed bindings similarly ignored the image/texture distinction, target
and array length. Include those existing key fields so an exact lookup does
not linearly scan all the other bindings using the same backing buffer/pool.

Only the two hash functions change. Key equality, entry lifetime, LRU policy,
texture validation, synchronization, resource ownership and binding calls stay
identical. No cached host state or memory invalidation is bypassed.
"""
from adapt_session import once


def apply(source):
    cache = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
    once(cache,
         '                return HashCode.Combine(_texturePool, _samplerPool, IsSampler);',
         '''                return HashCode.Combine(_texturePool, _samplerPool, IsImage, IsSampler, Target, ArrayLength);''')
    once(cache,
         '                return _textureBufferBounds.Range.GetHashCode();',
         '''                return HashCode.Combine(_textureBufferBounds, _texturePool, _samplerPool, IsImage, Target, HandleIndex, ArrayLength);''')
    return [cache]
