"""Texture descriptors whose address lies outside the GPU address space.

Hogwarts Legacy, 27 October 2026 (Build 562 app.log): texture pool entries
filled with 0x5A5A5A5A (format 0x25A5A, sRGB, GPU VA 0x5A5A5A5A5A5A) were
looked up again after every write to the pool, more than 13,000 times a
second. Each lookup logged "Invalid texture format 0x25A5A" before
FindOrCreateTexture returned null, because MemoryManager.Translate and
TranslateFirstMapped reject such an address outright. Every log reached the
RewindBox journal (a synchronous app.log write) and the console target on the
GPU thread: the game stood at 0 FPS for 15 s with the GPU thread at 99 % and
Logger.MessageThread at 80 %, and later fell to 1-9 FPS with the .NET GC at
30-60 %.

Reject that address first, with the same outcome: the ID is marked invalid
until the pool changes, as FindOrCreateTexture's null already does. Mapped or
merely unmapped addresses keep the upstream path. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    gpu = source / 'src/Ryujinx.Graphics.Gpu'
    pool = gpu / 'Image/TexturePool.cs'
    memory = gpu / 'Memory/MemoryManager.cs'
    once(memory, '        private static bool ValidateAddress(ulong va)',
         '        internal static bool ValidateAddress(ulong va)')
    once(pool, '''                    TextureInfo info = GetInfo(descriptor, out int layerSize);
                    texture = PhysicalMemory.TextureCache.FindOrCreateTexture(_channel.MemoryManager, TextureSearchFlags.ForSampler, info, layerSize);

                    // If this happens, then the texture address is invalid, we can't add it to the cache.
                    if (texture == null)''', '''                    // Outside the GPU address space FindOrCreateTexture always returns
                    // null; skip sizing and logging a descriptor that is not one.
                    if (!MemoryManager.ValidateAddress(descriptor.UnpackAddress()))
                    {
                        _invalidMap.Set(id);
                        return ref descriptor;
                    }

                    TextureInfo info = GetInfo(descriptor, out int layerSize);
                    texture = PhysicalMemory.TextureCache.FindOrCreateTexture(_channel.MemoryManager, TextureSearchFlags.ForSampler, info, layerSize);

                    // If this happens, then the texture address is invalid, we can't add it to the cache.
                    if (texture == null)''')
    return [pool, memory]
