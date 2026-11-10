"""Reuse private constant-buffer snapshots on bindless cache rebuilds.

The entry keeps one texture snapshot and, only for separate samplers, a second
snapshot. Replace their data in place when the exact length is unchanged;
different lengths keep the original exact-length allocation. No new retained
cache, generation shortcut, memory read suppression or validation rule is added.

Combined snapshots intentionally alias. A transition to separate samplers must
preserve the old sampler snapshot even if a later allocation fails, so it first
allocates a distinct texture snapshot. Also keep an incoming sampler span intact
if it overlaps the old texture destination before copying the texture data.
All snapshot consumers remain read-only and synchronous in this private entry.
"""
import hashlib
from adapt_session import once


RELATIVE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
BASELINE = 'b27962d8c7fcb4316ac45be63a91525f58e8215808b8a78c9dbcef6c897217d3'


def apply(source):
    path = source / RELATIVE
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)
    once(path, '''                _cachedTextureBuffer = cachedTextureBuffer.ToArray();
                _cachedSamplerBuffer = separateSamplerBuffer ? cachedSamplerBuffer.ToArray() : _cachedTextureBuffer;''',
         '''                int[] textureSnapshot = _cachedTextureBuffer;

                if (textureSnapshot == null || textureSnapshot.Length != cachedTextureBuffer.Length ||
                    (separateSamplerBuffer && ReferenceEquals(textureSnapshot, _cachedSamplerBuffer)) ||
                    cachedSamplerBuffer.Overlaps(textureSnapshot))
                {
                    textureSnapshot = cachedTextureBuffer.ToArray();
                }
                else
                {
                    cachedTextureBuffer.CopyTo(textureSnapshot);
                }

                _cachedTextureBuffer = textureSnapshot;

                if (separateSamplerBuffer)
                {
                    int[] samplerSnapshot = _cachedSamplerBuffer;

                    if (samplerSnapshot == null || samplerSnapshot.Length != cachedSamplerBuffer.Length ||
                        ReferenceEquals(samplerSnapshot, textureSnapshot) || cachedTextureBuffer.Overlaps(samplerSnapshot))
                    {
                        samplerSnapshot = cachedSamplerBuffer.ToArray();
                    }
                    else
                    {
                        cachedSamplerBuffer.CopyTo(samplerSnapshot);
                    }

                    _cachedSamplerBuffer = samplerSnapshot;
                }
                else
                {
                    _cachedSamplerBuffer = textureSnapshot;
                }''')
    return [path]
