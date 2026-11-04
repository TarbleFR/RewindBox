"""Give the texture over a DMA read-back destination the data the read-back writes, instead of a write signal without data.

IPA 643 (MeloNX Core 642, Hogwarts Legacy v1.0.5, 4 November 2026; private logs and a screen recording, not in the
repository): the screen stays black at launch while frames are presented, until the MeloNX menu is opened and closed,
and black or dim single frames appear later. The DMA summary of that session gives every GPU read-back into a buffer
(973 of 973) "over textures", and the one texture there is logged once: R32G32B32A32Float Texture2D 1x1, block-linear,
512 bytes, the destination at +0, never written by the GPU (modified False). The source is a 1x1 R32G32B32A32Float
render target, copied into a 16-byte buffer each frame.

The Hogwarts policy's TryReadBackIntoBuffer (adapt_hogwarts_dma_copies, build 628) copies the source into the buffer on
the GPU and, when textures are over the destination, first calls PhysicalMemory.SignalTextureWrite (a precise guest
write signal, buffers exempt), "as a guest write of the destination would". A guest write puts the bytes in guest
memory; this copy does not: they stay in the host buffer until something reads that memory through tracking. The
texture, now dirty, reloads on its next use from guest memory without tracking (Texture.SynchronizeFull and
TextureGroup.SynchronizePartial read through GetReadOnlyRegion, tracked: false), so it gets the bytes that were there
before: zeros or an older value, and the value just read back only if a tracked guest access flushed the buffer first. A 1x1 RGBA32F value read back by the game every frame
and sampled as a 1x1 texture is the shape of an auto-exposure or luminance value; a zero or stale one darkens the whole
image. Whether this is the cause of the black launch is a hypothesis that only a device run can confirm.

Change: in TryReadBackIntoBuffer, every texture over the destination (buffer textures apart, as before) must be a
receiver: not a view, Texture2D, one level, one layer, the source's format and scale (and that format host-compatible
as is), no incompatible overlaps in its group (as the other GPU copies of this file require), the source's width and
height, its storage one range starting at the destination, and the destination's bytes at the same places in it (linear with
the destination's stride, or block-linear with one row of 16 bytes or less, which is the start of a GOB's first row).
If one is not, the read-back declines as occupied ("unreceivable" in the occupied split) and the delivered guest path
copies through guest memory, which invalidates the texture with the right bytes. Otherwise the write signal is no
longer sent, and after the buffer copy each receiver gets the source on the GPU, as the GPU texture copy of this file
already does (SynchronizeMemory, HostTexture.CopyTo, SignalModified): the texture holds the value just read back, the
buffer too, and a later guest access of that memory flushes the same bytes from either (a block-linear flush writes the
texel positions only). Not sending the signal also avoids flushing a receiver modified by the previous read-back before
each read-back (the signal is a write, which runs the flush of a GPU-modified texture). Texture pools over the
destination were already not signalled when no texture is there; that case is unchanged. The summary counts the
receivers copied ("copied into receivers N") and the unreceivable declines. Open risk (independent review, unproven):
a receiver stays GPU-modified with the last value read back; if the game later writes the destination through the
buffer on the GPU (no read-back) and the guest CPU then reads it, the texture's flush may land after the buffer's and
put the older value in guest memory. The delivered code already left such a texture stale for the GPU in that case.
Not measured on an iPhone.
Fail closed on drift: DmaClass.cs must be the Core 642 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs': '39a59d894b0c2c6385dab0bb7f3c266aa400d475b63d7b59c49c65d3dc9bd702',
}

# Bytes of the first row of a GOB that are linear in a block-linear layout (offsets 0-15 of row 0).
LINEAR_GOB_PREFIX = 16


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    dma = paths['src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs']
    once(dma, '''        private long _readBackOccupiedSource;
''', '''        private long _readBackOccupiedSource;
        // RewindBox (adapt_readback_receivers): textures over a read-back destination that receive the source on the GPU.
        private Image.Texture[] _readBackReceivers = new Image.Texture[8];
        private long _readBackReceiverCopies;
        private long _readBackOccupiedUnreceivable;
''')
    once(dma, '''            int textures = 0, readBackTargets = 0, modified = 0, bufferTextures = 0;
            bool sourceThere = false;
''', '''            int textures = 0, readBackTargets = 0, modified = 0, bufferTextures = 0;
            bool sourceThere = false;
            bool unreceivable = false;

            if (_readBackReceivers.Length < overlaps)
            {
                Array.Resize(ref _readBackReceivers, overlaps);
            }
''')
    once(dma, '''                sourceThere |= texture.Group == source.Group;
                textures++;
''', '''                sourceThere |= texture.Group == source.Group;

                if (IsReadBackReceiver(texture, source, address, width, height, size, dstStride))
                {
                    _readBackReceivers[textures] = texture;
                }
                else
                {
                    unreceivable = true;
                }

                textures++;
''')
    once(dma, '''            if (sourceThere)
            {
                _readBackDeclines[(int)ReadBackDecline.Occupied]++;
                _readBackOccupiedSource++;
                return false;
            }

            if (!contiguous)
            {
                _readBackDeclines[(int)ReadBackDecline.Buffer]++;
                return false;
            }
''', '''            if (sourceThere)
            {
                Array.Clear(_readBackReceivers, 0, textures);
                _readBackDeclines[(int)ReadBackDecline.Occupied]++;
                _readBackOccupiedSource++;
                return false;
            }

            // RewindBox (adapt_readback_receivers): a texture there that cannot receive the source keeps the guest path,
            // whose guest write gives it the right bytes; a write signal alone would reload it from stale guest memory.
            if (unreceivable)
            {
                Array.Clear(_readBackReceivers, 0, textures);
                _readBackDeclines[(int)ReadBackDecline.Occupied]++;
                _readBackOccupiedUnreceivable++;
                return false;
            }

            if (!contiguous)
            {
                Array.Clear(_readBackReceivers, 0, textures);
                _readBackDeclines[(int)ReadBackDecline.Buffer]++;
                return false;
            }
''')
    once(dma, '''            source.SynchronizeMemory();

            if (textures != 0)
            {
                // As a guest write of the destination would: buffers exempt, the copy below writes the one there.
                memoryManager.Physical.SignalTextureWrite(address, size);
            }

            if (!memoryManager.Physical.BufferCache.TryCopyTextureToBuffer(memoryManager, source.HostTexture, dstVa, size, dstStride))
            {
                _readBackDeclines[(int)ReadBackDecline.Buffer]++;
                return false;
            }
''', '''            source.SynchronizeMemory();

            if (!memoryManager.Physical.BufferCache.TryCopyTextureToBuffer(memoryManager, source.HostTexture, dstVa, size, dstStride))
            {
                Array.Clear(_readBackReceivers, 0, textures);
                _readBackDeclines[(int)ReadBackDecline.Buffer]++;
                return false;
            }

            // RewindBox (adapt_readback_receivers): the copy above leaves the bytes in the host buffer, not in guest memory,
            // so a write signal would make each texture there reload what guest memory held before. Each receives the
            // source on the GPU instead, as the GPU texture copy of this class does, and holds the value just read back.
            for (int i = 0; i < textures; i++)
            {
                Image.Texture receiver = _readBackReceivers[i];
                receiver.SynchronizeMemory();
                source.HostTexture.CopyTo(receiver.HostTexture, 0, 0);
                receiver.SignalModified();
                _readBackReceiverCopies++;
            }

            Array.Clear(_readBackReceivers, 0, textures);
''')
    once(dma, '''buffer textures {_bufferTextureOverlaps}) of {_readBackCandidates}, " +''',
         '''buffer textures {_bufferTextureOverlaps}, copied into receivers {_readBackReceiverCopies}) of {_readBackCandidates}, " +''')
    once(dma, '''source group {_readBackOccupiedSource}) target " +''',
         '''source group {_readBackOccupiedSource}, unreceivable {_readBackOccupiedUnreceivable}) target " +''')
    once(dma, '''        private void NoteReadBackOverlap(Image.Texture texture, int overlaps, ulong address, ulong size, bool readBackTarget, bool modified)
''', '''        /// <summary>
        /// RewindBox (adapt_readback_receivers): whether a texture over the destination of a read-back into a buffer holds the
        /// destination's bytes at the same places as the source's texels, so a GPU copy of the whole source gives it exactly
        /// what the read-back writes: not a view, 2D, one level and layer, the source's format (host-compatible as is), scale
        /// and size, no incompatible overlaps in its group, one range
        /// starting at the destination, linear with the destination's stride or block-linear with a single row of at most
        /// %d bytes (offsets 0 to 15 of a GOB's first row are linear).
        /// </summary>
        private bool IsReadBackReceiver(Image.Texture texture, Image.Texture source, ulong address, int width, int height,
                                        ulong size, int dstStride)
        {
            Image.TextureInfo info = texture.Info;

            if (texture.IsView || texture.HostTexture == null || info.Target != Target.Texture2D || info.Levels != 1 ||
                info.DepthOrLayers != 1 || info.FormatInfo.Format != source.Info.FormatInfo.Format ||
                Image.TextureCompatibility.ToHostCompatibleFormat(info, _context.Capabilities).Format != info.FormatInfo.Format ||
                texture.Group == null || texture.Group.HasIncompatibleOverlaps ||
                texture.ScaleFactor != source.ScaleFactor || info.Width != width || info.Height != height ||
                texture.Range.Count != 1 || texture.Range.GetSubRange(0).Address != address)
            {
                return false;
            }

            return info.IsLinear
                ? info.Stride == dstStride
                : height == 1 && size <= %d && (ulong)(width * info.FormatInfo.BytesPerPixel) == size;
        }

        private void NoteReadBackOverlap(Image.Texture texture, int overlaps, ulong address, ulong size, bool readBackTarget, bool modified)
''' % (LINEAR_GOB_PREFIX, LINEAR_GOB_PREFIX))
    return list(paths.values())
