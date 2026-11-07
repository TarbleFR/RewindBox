"""Hogwarts Legacy: a read-back over an occupied destination with no buffer goes into a buffer on the GPU (Core 689).

IPA 688 on the device (Hogwarts Legacy, PID 29464, 7 November 2026, Core 687, per-game "Async shaders" on; private
journals): the GPU thread is 60-95 % busy in every 5.1 s window of the drops, and its largest single item is the
texture flush action of the DMA engine (gpuWork.texFlushAction 0.4-2.3 s per window, about one per frame, 5-15 ms each,
which the render thread's read fence waits mirror: 48.5 s over 9 647 frames). The DMA summary gives the cause: 4 391
read-backs declined as "occupied" (other textures 4 391, fragmented 0, source group 0) and 4 390 slow guest-path reads.
TryReadBackGpuRegion declines when no buffer of the cache covers the linear destination, no linear texture of its stride
is there, and FindOverlapsInRange finds other textures. The occupants it logged in this session are the game's 1x1
R32G32B32A32Float block-linear texture at the destination (a read-back receiver of TryReadBackIntoBuffer) and two
R32Float TextureBuffer textures (views of buffer memory, which TryReadBackIntoBuffer leaves alone). Without async
shaders the same flush was cheap (the GPU had finished; IPA 688, PID 28747): the guest now waits for the host GPU.

Change (Hogwarts policy only, as the read-back itself): when such a destination is one contiguous physical range with
textures over it, the read-back takes TryReadBackIntoBuffer, the path of build 626 for a destination a buffer holds
(validated on the device since: 4 213 copies into receivers in this session). BufferCache.TryCopyTextureToBuffer creates
the buffer over the range, the level is copied on the GPU, the range is marked GPU-modified, each receiver texture gets
the source on the GPU, and the forced host sync follows; a guest read of that memory later flushes the buffer. That path
keeps its own declines (partial copy, a texture of the source's group, an occupant that cannot receive the source,
non-contiguous, no buffer): each keeps the guest path as before. A fragmented destination with no texture is still
declined. Counted in the DMA summary ("rerouted into buffers N, copied N"); the decline counters keep their meaning.
Not measured on an iPhone. Fail closed on drift: DmaClass.cs must be the Core 687 preparation's.
"""
import hashlib
from adapt_session import once

DMA = 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'
BASELINE = {
    DMA: '5876158a34125cdd1b09528d4b96296fb4a6e457f61296ef6f85e6668037edf5',
}

FIELDS_OLD = '''        private long _readBackOccupiedOverlaps;
'''
FIELDS_NEW = '''        private long _readBackOccupiedOverlaps;
        // RewindBox (adapt_occupied_readback_buffers): occupied destinations sent into a buffer, and how many were copied.
        private long _readBackOccupiedRerouted;
        private long _readBackOccupiedReroutedCopies;
        private bool _readBackOccupiedRerouteNoted;
'''

SUMMARY_OLD = '''unreceivable {_readBackOccupiedUnreceivable}) target " +'''
SUMMARY_NEW = '''unreceivable {_readBackOccupiedUnreceivable}; rerouted into buffers {_readBackOccupiedRerouted}, copied {_readBackOccupiedReroutedCopies}) target " +'''

DECLINE_OLD = '''                int occupants = memoryManager.Physical.TextureCache.FindOverlapsInRange(
                    memoryManager, dstVa, size, ref _targetOverlaps, out bool contiguous);

                if (occupants != 0 || !contiguous)
                {
'''
DECLINE_NEW = '''                int occupants = memoryManager.Physical.TextureCache.FindOverlapsInRange(
                    memoryManager, dstVa, size, ref _targetOverlaps, out bool contiguous);

                // RewindBox (adapt_occupied_readback_buffers): textures over one contiguous destination with no buffer: the
                // read-back goes into a buffer created there (TryReadBackIntoBuffer feeds the receivers, leaves buffer
                // textures alone and declines what it cannot keep coherent), not through guest memory.
                if (occupants != 0 && contiguous)
                {
                    // The overlaps are not kept; TryReadBackIntoBuffer looks them up again.
                    Array.Clear(_targetOverlaps, 0, occupants);
                    _readBackOccupiedRerouted++;

                    if (!TryReadBackIntoBuffer(memoryManager, source, format, sourceX, sourceY, width, height, dstVa, size, dstStride))
                    {
                        return false;
                    }

                    _readBackOccupiedReroutedCopies++;

                    if (!_readBackOccupiedRerouteNoted)
                    {
                        _readBackOccupiedRerouteNoted = true;
                        Logger.Warning?.Print(LogClass.Gpu, $"DMA read-back over an occupied destination into a buffer (Hogwarts policy): " +
                            $"{format.Format} {width}x{height} to stride {dstStride}, {occupants} texture(s) there");
                    }

                    return true;
                }

                if (occupants != 0 || !contiguous)
                {
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    dma = paths[DMA]
    once(dma, FIELDS_OLD, FIELDS_NEW)
    once(dma, SUMMARY_OLD, SUMMARY_NEW)
    once(dma, DECLINE_OLD, DECLINE_NEW)
    return list(paths.values())
