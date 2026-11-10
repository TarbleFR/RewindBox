"""A buffer evicted from the GPU buffer cache is recreated when it is used again, whatever the host memory budget setting.

IPA 674 (Core 673), private journals, not in the repository: Hogwarts Legacy ran with hostMemoryBudget=False (the setting
of every recent Hogwarts session) and the application aborted after about 7 minutes of play on a
NullReferenceException in BufferCache.GetBuffer, from GetBufferRangeAligned in BufferManager.CommitGraphicsBindings
(RenderThread, MacroHLE.DrawElements).

Mechanism (MeloNX source): on Apple unified memory the buffer cache always has a byte limit (from the process budget,
or from the guest memory size when host budget tracking is off: 256 MiB for Hogwarts) and AddBuffer always evicts the
least recently used buffers above it. Only the lookups that a binding uses later (GetOrCreateBuffer,
GetOrCreateSparseBuffer) and the eviction suppression during a multi-range creation were conditioned on host budget
tracking. With tracking off, a buffer evicted after a binding recorded its range is looked up, not found, and null is
dereferenced.

Change (BufferCache.cs, every title): the lookups recreate a missing or partially overlapping buffer, and eviction is
deferred during a multi-range creation, in both settings. With tracking on nothing changes; with it off the only change
is that a lookup which used to return null (or a buffer that does not contain the range) now creates the buffer.
Limits, eviction order, pressure trimming and the setting itself are unchanged.
Fail closed on drift: the file must be the Core 675 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs': '82d674927916ad74de1a8de9c46c79f418bda7efb2e8a7b566c0ecbee232a3ba',
}

MULTI_OLD = '''        private void CreateMultiRangeBuffer(MultiRange range, BufferStage stage)
        {
            if (!GraphicsConfig.EnableHostMemoryBudgetTracking)
            {
                CreateMultiRangeBufferImpl(range, stage);

                return;
            }

            _evictionSuppressDepth++;
'''
MULTI_NEW = '''        private void CreateMultiRangeBuffer(MultiRange range, BufferStage stage)
        {
            // RewindBox (adapt_evicted_buffer_recreate): AddBuffer evicts in both host budget settings, so the
            // sub-buffers created here are protected from eviction until the multi-range buffer exists in both.
            _evictionSuppressDepth++;
'''

LOOKUP_OLD = '''            Buffer buffer = size != 0
                ? _buffers.FindOverlap(address, size)
                : _buffers.FindOverlapFast(address, 1);

            if (!GraphicsConfig.EnableHostMemoryBudgetTracking)
            {
                return buffer;
            }

            // A buffer that only partially overlaps'''
LOOKUP_NEW = '''            Buffer buffer = size != 0
                ? _buffers.FindOverlap(address, size)
                : _buffers.FindOverlapFast(address, 1);

            // RewindBox (adapt_evicted_buffer_recreate): AddBuffer evicts in both host budget settings, so an evicted
            // buffer is recreated in both (with tracking off it used to be returned as null: IPA 674 Hogwarts abort).
            // A buffer that only partially overlaps'''

SPARSE_OLD = '''            Buffer buffer = _buffers.FindOverlap(address, size);

            if (!GraphicsConfig.EnableHostMemoryBudgetTracking)
            {
                return buffer;
            }

            if (buffer == null || !buffer.FullyContains(address, size))
            {
                CreateBuffer(address, size, stage, SparseBufferAlignmentSize);
'''
SPARSE_NEW = '''            Buffer buffer = _buffers.FindOverlap(address, size);

            // RewindBox (adapt_evicted_buffer_recreate): recreated after an eviction in both host budget settings.
            if (buffer == null || !buffer.FullyContains(address, size))
            {
                CreateBuffer(address, size, stage, SparseBufferAlignmentSize);
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    cache = paths['src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs']
    once(cache, MULTI_OLD, MULTI_NEW)
    once(cache, LOOKUP_OLD, LOOKUP_NEW)
    once(cache, SPARSE_OLD, SPARSE_NEW)
    return list(paths.values())
