"""A large texture array's slot that would be written whole is copied from the array's latest slot instead (Hogwarts Legacy).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journal, pid 5954, "Vulkan pass and GPU detail" windows): the pool
texture arrays of 524 288 elements (adapt_bindless_pool_arrays; backend texture arrays over 4096 elements 3) are written
whole whenever the slot a draw gets is new, or older than the array's change log floor, or more than a quarter behind:
64 whole writes of 524 288 elements in the session, 11 to 17 ms each (21.3 ms per million elements by regression of
the windows' write time), a frame hitch each time, mostly in streaming and right after a resume. TextureArray keeps up to
eight slots (descriptor sets) per array and writes only the changed ranges into a slot that is recent enough.

Change (TextureArray.cs, GetOwnDescriptorSets): for an array of more than 4096 elements whose slot would be written
whole, the most recent other slot of the same binding and type that was written (Sequence >= 0) is copied into it with
one vkCopyDescriptorSet of the whole binding, when the changes since that slot are in the log and a quarter of the
array or less; then only those changes are written, as for a recent slot. The copy is its own vkUpdateDescriptorSets
call before the writes (within one call the writes are applied before the copies). Its content is the array's values at
the source's Sequence, the invariant the range path already relies on; the source may be bound by a pending command
buffer (it is only read). In the embedded MoltenVK (MVKDescriptorSet.mm, copyDescriptorSetBinding, Metal 3 argument
buffers) the copy is a memcpy of the CPU and GPU descriptor buffers, where a write encodes every element. Smaller
arrays, and slots with no usable source, are written as before.

Scope: EncodingPolicy.IncrementalArrayDescriptors (Hogwarts Legacy). Expected on the device: "texture arrays: whole
writes" down by most of their elements and "write time" lower in the pass windows; fewer frame hitches in streaming.
Not measured on an iPhone. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
BASELINE = {ARRAY: '54d8a585078eb2bc98008d497dcf0f82d8f2bf85fe17f8e6cf39fffb73892b51'}

GATHER_OLD = '''            int elements = GatherChanges(slot.Sequence);

            if (elements < 0 || elements > _textures.Length / 4)
            {
                _runs.Clear();
'''
GATHER_NEW = '''            int elements = GatherChanges(slot.Sequence);

            // RewindBox (adapt_pool_slot_copy): a large array's slot that would be written whole is copied from the latest
            // other slot of the binding (a pending one may be read), then only the changes since that slot are written.
            if ((elements < 0 || elements > _textures.Length / 4) && _textures.Length > LargeChange)
            {
                ArraySlot source = null;

                foreach (ArraySlot other in _slots)
                {
                    if (!ReferenceEquals(other, slot) && other.Sequence >= 0 && other.Binding == binding && other.Type == type &&
                        (source == null || other.Sequence > source.Sequence))
                    {
                        source = other;
                    }
                }

                int sourceElements = source == null ? -1 : GatherChanges(source.Sequence);

                if (sourceElements >= 0 && sourceElements <= _textures.Length / 4)
                {
                    CopySlot(device, source, slot);
                    elements = sourceElements; // _runs holds the changes since the source's sequence
                }
            }

            if (elements < 0 || elements > _textures.Length / 4)
            {
                _runs.Clear();
'''

COPY_OLD = '''        private unsafe void WriteRuns(Device device, ArraySlot slot)
'''
COPY_NEW = '''        // RewindBox (adapt_pool_slot_copy): the whole binding of one slot into another (same binding, type and count),
        // in its own call before WriteRuns: within one vkUpdateDescriptorSets the writes are applied before the copies.
        private unsafe void CopySlot(Device device, ArraySlot source, ArraySlot destination)
        {
            CopyDescriptorSet copy = new()
            {
                SType = StructureType.CopyDescriptorSet,
                SrcSet = source.Sets[0],
                SrcBinding = (uint)source.Binding,
                SrcArrayElement = 0,
                DstSet = destination.Sets[0],
                DstBinding = (uint)destination.Binding,
                DstArrayElement = 0,
                DescriptorCount = (uint)_textures.Length,
            };

            _gd.Api.UpdateDescriptorSets(device, 0, (WriteDescriptorSet*)null, 1, &copy);
        }

        private unsafe void WriteRuns(Device device, ArraySlot slot)
'''

PAIRS = ((GATHER_OLD, GATHER_NEW), (COPY_OLD, COPY_NEW))


def apply(source):
    path = source / ARRAY
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, ARRAY
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
