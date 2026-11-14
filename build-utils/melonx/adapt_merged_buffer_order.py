"""A merged buffer joins the buffer list before the multi-range buffers over its range are recreated (every title).

Evidence: code review, not a device counter. The adversarial review of the IPA 740 lot (docs/evidence/melonx-heat/
handoff.md, "IPA 740 lot: adversarial review") found the order while checking adapt_buffer_hit_sets. The IPA 740 journals
(Core da2525a1, pid 5954) have no line about merges, multi-range buffers or overlapping buffers (0 lines), so the device
frequency is unknown. It lies between none and every merge of a 64 KiB-aligned range that a multi-range buffer overlaps.

Defect (BufferCache.cs, already in the pristine MeloNX source; no adapter introduced it). The merge paths of the
three-argument (page) and four-argument (alignment) CreateBufferAligned remove the overlapping buffers (RemoveBuffers),
then pass to AddBuffer what the five-argument CreateBufferAligned returns. That overload builds the merged buffer,
copies the old buffers into it, and calls RecreateMultiRangeBuffers(address, size) before returning. So when the merged
range is 64 KiB-aligned and a multi-range buffer overlaps it, the recreation runs while the merged buffer is not in the
list yet. CreateMultiRangeBuffer -> CreateBuffer(sub-range, 64 KiB) -> the four-argument CreateBufferAligned finds no
buffer there and creates a fresh one from guest memory. The merged buffer is then inserted over it. Until one of the
two leaves:
- the list holds two overlapping buffers;
- the multi-range buffer depends on the fresh one, which lacks the GPU-written ranges the merged buffer inherited;
- FindOverlap, FindOverlapFast and the hit table can answer either buffer.
Upstream Ryujinx's CreateBufferAligned (not in this tree) adds the new buffer to the list before it copies the overlaps
and before RecreateMultiRangeBuffers.

Change (BufferCache.cs only): the five-argument CreateBufferAligned now calls AddBuffer(merged) right before
RecreateMultiRangeBuffers, and returns nothing. Its only two callers, the two merge paths, no longer add the buffer.
- Nothing between RemoveBuffers and that AddBuffer reads or changes the list (CopyTo, InheritModifiedRanges,
  DecrementReferenceCount, SynchronizeMemory, NotifyBuffersModified, which only sets the channels' rebind flags). So
  every AddBuffer now inserts a buffer that no buffer of the list overlaps.
- When RecreateMultiRangeBuffers does nothing (the range is unaligned, or no multi-range buffer overlaps it), the
  effects are the old ones in the same order. Whether it acts depends only on the range and _multiRangeBuffers, and
  AddBuffer touches neither.
- Otherwise the recreated multi-range buffers' sub-ranges find the merged buffer and touch it. If it does not contain a
  sub-range or is not sparse-compatible, it is merged into a larger 64 KiB-aligned buffer, as in Ryujinx. No duplicate
  is created.
- AddBuffer's EnforceCapacity(merged) runs before the recreation instead of after it, and finds the same evictable
  buffers less the duplicate: the merged buffer is the protected one, and the old multi-range buffers still hold the
  physical buffers outside the merged range that the recreated ones take again (CanEvict is false while a virtual or
  cache dependency exists). The eviction deferred to the end of each CreateMultiRangeBuffer finds the merged buffer
  held by a recreated multi-range buffer.
- In the LRU list the merged buffer now comes before the buffers the recreation touches, instead of after them; their
  use stamps are the same second.
- Hit table (adapt_buffer_hit_sets): entries are added only for buffers of the list and are removed with them. With no
  overlap left in the list, AddBuffer's clearing loop finds nothing more to clear. It is kept.

Expected on the device: nothing the journals count. A merged range under a multi-range (storage, transform feedback or
indirect) buffer is read from the merged buffer, not from a guest-memory duplicate; the buffer cache holds the
duplicate's bytes less. Not measured on an iPhone. Applied after adapt_buffer_hit_sets (its post-image).
Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'
BASELINE = {CACHE: '8482c246d21cfe39834a40766eb97f24e3a6796aecb97a4222ef49f7069c55c7'}

SIGNATURE_OLD = '''        private Buffer CreateBufferAligned(ulong address, ulong size, BufferStage stage, bool sparseCompatible, Buffer[] overlaps)
'''
SIGNATURE_NEW = '''        private void CreateBufferAligned(ulong address, ulong size, BufferStage stage, bool sparseCompatible, Buffer[] overlaps)
'''

TAIL_OLD = ('            NotifyBuffersModified?.Invoke();\n'
            '\n'
            '            RecreateMultiRangeBuffers(address, size);\n'
            '            \n'  # this blank line holds twelve spaces in the source
            '            return newBuffer;\n'
            '        }\n')
TAIL_NEW = '''            NotifyBuffersModified?.Invoke();

            // RewindBox (adapt_merged_buffer_order): the merged buffer joins the list before the multi-range buffers over
            // its range are recreated, as in Ryujinx; their sub-ranges then find it instead of a fresh copy from guest memory.
            AddBuffer(newBuffer);

            RecreateMultiRangeBuffers(address, size);
        }
'''

PAGE_MERGE_OLD = '''                    AddBuffer(CreateBufferAligned(address, newSize, stage, anySparseCompatible, overlapsArray));
'''
PAGE_MERGE_NEW = '''                    CreateBufferAligned(address, newSize, stage, anySparseCompatible, overlapsArray); // RewindBox (adapt_merged_buffer_order)
'''

ALIGNED_MERGE_OLD = '''                    AddBuffer(CreateBufferAligned(address, newSize, stage, sparseAligned, overlapsArray));
'''
ALIGNED_MERGE_NEW = '''                    CreateBufferAligned(address, newSize, stage, sparseAligned, overlapsArray); // RewindBox (adapt_merged_buffer_order)
'''

PAIRS = ((PAGE_MERGE_OLD, PAGE_MERGE_NEW), (ALIGNED_MERGE_OLD, ALIGNED_MERGE_NEW), (SIGNATURE_OLD, SIGNATURE_NEW),
         (TAIL_OLD, TAIL_NEW))


def apply(source):
    path = source / CACHE
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, CACHE
    # The merge overload is called by these two merge paths only, each adding what it returns.
    text = path.read_text(encoding='utf-8-sig')
    assert not digests or (text.count('CreateBufferAligned(') == 7 and text.count('AddBuffer(CreateBufferAligned(') == 2), CACHE
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
