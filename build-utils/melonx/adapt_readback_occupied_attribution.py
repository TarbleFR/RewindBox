"""Attribute the read-backs the Hogwarts DMA policy declines as "occupied": which branch, and what occupies the destination.

IPA 640 (Core 639, Hogwarts Legacy, 4 November 2026; private logs): the DMA summary gives 1 313 GPU read-backs of 1 969
candidates, 1 310 into buffers (an R32G32B32A32Float 1x1 copy each frame), and 655 declined as "occupied", which take
the guest path (656 slow reads, a texture flush and a render-thread wait each). The attribution lines show a second
read-back, R16G16B16A16Float 1x1 to a linear destination of stride 8 (TryReadBackGpuRegion), that succeeded only at the
start of each session. "Occupied" counts three different conditions that the summary does not separate:

- TryReadBackGpuRegion, no buffer over the destination: FindTexture found no linear texture with this stride and height,
  and FindOverlapsInRange found other textures over the destination;
- the same, with no texture but a destination that is not one contiguous physical range;
- TryReadBackIntoBuffer: a texture of the source's own group over the destination.

Which one, and what the occupying texture is (a read-back target the lookup no longer matches, a texture of the game over
that memory, its layout and stride), decides the correction, so the synchronisation is not changed before it is known.

Change, diagnostics only (no decision, copy, flush or synchronisation changes): the summary line adds
"(other textures N, fragmented N, source group N)" after "occupied N" (the sum stays as before). The first 8 distinct
occupants of the first branch are logged once each: format, target, size, layout and stride, levels, read-back target,
GPU-modified, offset of the destination in it, whether it is in the texture cache's auto-delete list, and whether it meets
FindTexture's linear match (linear, same stride, same height). The overlaps found there are released before returning, as
the buffer branch already does. Not measured on an iPhone. Fail closed on drift: DmaClass.cs must be the Core 639
preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs': '3094626fcb5b5d5e0cbd145da4dce42c27555f66b58cb9ac8bbf22ff5507dcab',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    dma = paths['src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs']
    once(dma, '''        private long _readBackCandidates;
''', '''        private long _readBackCandidates;
        // RewindBox (adapt_readback_occupied_attribution): the "occupied" declines by branch, and their first occupants.
        private long _readBackOccupiedOverlaps;
        private long _readBackOccupiedFragmented;
        private long _readBackOccupiedSource;
        private const int ReadBackOccupantSignatureLimit = 8;
        private readonly HashSet<(int, int, int, int, int, int, bool, bool, bool)> _readBackOccupantSignatures = new();
''')
    once(dma, '''                if (memoryManager.Physical.TextureCache.FindOverlapsInRange(
                        memoryManager, dstVa, size, ref _targetOverlaps, out bool contiguous) != 0 || !contiguous)
                {
                    _readBackDeclines[(int)ReadBackDecline.Occupied]++;
                    return false;
                }
''', '''                int occupants = memoryManager.Physical.TextureCache.FindOverlapsInRange(
                    memoryManager, dstVa, size, ref _targetOverlaps, out bool contiguous);

                if (occupants != 0 || !contiguous)
                {
                    _readBackDeclines[(int)ReadBackDecline.Occupied]++;

                    if (occupants == 0)
                    {
                        _readBackOccupiedFragmented++;
                    }
                    else
                    {
                        _readBackOccupiedOverlaps++;
                        ulong destination = memoryManager.Translate(dstVa);

                        for (int i = 0; i < occupants; i++)
                        {
                            NoteReadBackOccupant(_targetOverlaps[i], occupants, destination, size, dstStride, height);
                        }

                        // The overlaps are not kept.
                        Array.Clear(_targetOverlaps, 0, occupants);
                    }

                    return false;
                }
''')
    once(dma, '''            if (sourceThere)
            {
                _readBackDeclines[(int)ReadBackDecline.Occupied]++;
                return false;
            }
''', '''            if (sourceThere)
            {
                _readBackDeclines[(int)ReadBackDecline.Occupied]++;
                _readBackOccupiedSource++;
                return false;
            }
''')
    once(dma, '''occupied {_readBackDeclines[2]} target " +''',
         '''occupied {_readBackDeclines[2]} (other textures {_readBackOccupiedOverlaps}, fragmented " +
                    $"{_readBackOccupiedFragmented}, source group {_readBackOccupiedSource}) target " +''')
    once(dma, '''        private void NoteReadBackOverlap(Image.Texture texture, int overlaps, ulong address, ulong size, bool readBackTarget, bool modified)
''', '''        /// <summary>
        /// RewindBox (adapt_readback_occupied_attribution): logs once each of the first 8 distinct textures over the destination
        /// of a read-back TryReadBackGpuRegion declines as occupied, with whether FindTexture's linear match accepts it.
        /// </summary>
        private void NoteReadBackOccupant(Image.Texture texture, int occupants, ulong address, ulong size, int dstStride, int height)
        {
            int layout = (texture.Info.IsLinear ? 1 : 2) + (texture.Info.Levels > 1 ? 4 : 0) + (texture.Info.DepthOrLayers > 1 ? 8 : 0);
            bool readBackTarget = texture.Group != null && texture.Group.ReadBackTarget;
            bool modified = texture.Group != null && texture.Group.AnyHandleModified();
            bool lookupMatch = texture.Info.IsLinear && texture.Info.Stride == dstStride && texture.Info.Height == height;

            if (_readBackOccupantSignatures.Count >= ReadBackOccupantSignatureLimit ||
                !_readBackOccupantSignatures.Add(((int)texture.Info.Target, (int)texture.Info.FormatInfo.Format, layout, texture.Info.Width,
                                                  texture.Info.Height, texture.Info.Stride, readBackTarget, modified, lookupMatch)))
            {
                return;
            }

            ulong start = texture.Range.Count != 0 ? texture.Range.GetSubRange(0).Address : 0;
            string offset = start <= address ? $"+{address - start}" : $"-{start - address}";
            Logger.Warning?.Print(LogClass.Gpu, $"DMA read-back declined as occupied (Hogwarts policy) #{_readBackOccupantSignatures.Count}: " +
                $"{occupants} texture(s) over {size} bytes at stride {dstStride}; {texture.Info.FormatInfo.Format} {texture.Info.Target} " +
                $"{texture.Info.Width}x{texture.Info.Height}x{texture.Info.DepthOrLayers} levels {texture.Info.Levels} " +
                $"{(texture.Info.IsLinear ? "linear stride " + texture.Info.Stride : "block-linear gobY " + texture.Info.GobBlocksInY)} " +
                $"size {texture.Size}, destination at {offset}; read-back target {readBackTarget}, modified {modified}, " +
                $"in auto-delete cache {texture.CacheNode != null}, linear lookup match {lookupMatch}");
        }

        private void NoteReadBackOverlap(Image.Texture texture, int overlaps, ulong address, ulong size, bool readBackTarget, bool modified)
''')
    return list(paths.values())
