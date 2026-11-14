"""The buffer cache answers a range that a recently used buffer contains without searching its list (every title).

IPA 736 / Core c4a25b94, Hogwarts Legacy (private journal, pid 2349, five [MeloNX:hot] profiles in the world, 774 running
samples of GPU.MainThread): Buffer.OverlapsWith 57 of them (7.4 %), the largest single place of that thread, with
BufferCache.CreateBufferAligned 8, GetOrCreateBuffer 7 and Touch 5; the core windows count 31 700 buffer loads per
second. Read in the source: every use of a guest buffer range runs CreateBufferAligned (two binary searches of the
list for the left and right edge) and then GetOrCreateBuffer (a third), and each step of a search reads a Buffer object
(RangeListBase.BinarySearch: item.OverlapsWith, item.Address), twelve or so objects spread over the heap per search
with 4 500 buffers.

Change (BufferCache.cs only): sixteen slots, chosen by the page of the range's address, each holding a buffer and its
bounds. CreateBufferAligned and GetOrCreateBuffer first look at the slot: when its buffer contains the whole range it
is the answer the search would give (the list's buffers do not overlap), with the same Touch. A range the slot does not
contain is searched as before, and the buffer found is remembered. Every removal from the list empties the slots (the
only way a buffer leaves it: merge, eviction, cold trim). GPU thread only, as the list's modifications are.

Expected on the device: Buffer.OverlapsWith's share of GPU.MainThread's running samples under 2 %. Rendering unchanged:
the same buffer is returned for every range. Rollback: drop this adapter from prepare_embedded.py and ORDER.
Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'
BASELINE = {CACHE: '4887dc48c79ab6ae97aa4f0203b03a9459900068ca22fcea5dced071e8246f88'}

FIELDS_OLD = '''        private readonly NonOverlappingRangeList<Buffer> _buffers;
        private readonly MultiRangeList<MultiRangeBuffer> _multiRangeBuffers;
'''
FIELDS_NEW = '''        private readonly NonOverlappingRangeList<Buffer> _buffers;
        private readonly MultiRangeList<MultiRangeBuffer> _multiRangeBuffers;

        // RewindBox (adapt_buffer_last_hit): per page slot, a buffer of the list and its bounds. A range it contains is
        // answered without a search (the list's buffers do not overlap: it is the one the search would return). Emptied
        // by every removal from the list. GPU thread only.
        private struct BufferHit
        {
            public Buffer Buffer;
            public ulong Address;
            public ulong EndAddress;
        }

        private const int BufferHitSlots = 16;
        private readonly BufferHit[] _bufferHits = new BufferHit[BufferHitSlots];

        private Buffer FindBufferHit(ulong address, ulong size)
        {
            ref BufferHit hit = ref _bufferHits[(int)(address >> 12) & (BufferHitSlots - 1)];
            ulong endAddress = address + size;

            return hit.Buffer != null && address >= hit.Address && endAddress <= hit.EndAddress && endAddress > address
                ? hit.Buffer
                : null;
        }

        private void RememberBufferHit(ulong address, Buffer buffer)
        {
            ref BufferHit hit = ref _bufferHits[(int)(address >> 12) & (BufferHitSlots - 1)];
            hit.Buffer = buffer;
            hit.Address = buffer.Address;
            hit.EndAddress = buffer.EndAddress;
        }

        // The buffer a search found: remembered when it contains the whole range (a partial overlap is not an answer).
        private Buffer RememberIfContains(ulong address, ulong size, Buffer buffer)
        {
            if (buffer != null && address >= buffer.Address && address + size <= buffer.EndAddress && address + size > address)
            {
                RememberBufferHit(address, buffer);
            }

            return buffer;
        }
'''

REMOVE_OLD = '''        private void RemoveBufferTracking(Buffer buffer)
        {
            if (buffer.CacheNode != null)
'''
REMOVE_NEW = '''        private void RemoveBufferTracking(Buffer buffer)
        {
            Array.Clear(_bufferHits); // RewindBox (adapt_buffer_last_hit): a buffer left the list

            if (buffer.CacheNode != null)
'''

CREATE_OLD = '''        private void CreateBufferAligned(ulong address, ulong size, BufferStage stage)
        {
            ReadOnlySpan<Buffer> overlaps = _buffers.FindOverlapsAsSpan(address, size);
'''
CREATE_NEW = '''        private void CreateBufferAligned(ulong address, ulong size, BufferStage stage)
        {
            // RewindBox (adapt_buffer_last_hit): a buffer known to contain the whole range is the existing buffer below.
            Buffer known = FindBufferHit(address, size);

            if (known != null)
            {
                Touch(known);

                return;
            }

            ReadOnlySpan<Buffer> overlaps = _buffers.FindOverlapsAsSpan(address, size);
'''

TOUCH_OLD = '''                else
                {
                    Touch(overlaps[0]);
                }
            }
            else
            {
                // No overlap, just create a new buffer.
                AddBuffer(new(_context, _physicalMemory, address, size, stage, sparseCompatible: false, []));
'''
TOUCH_NEW = '''                else
                {
                    Touch(overlaps[0]);
                    RememberBufferHit(address, overlaps[0]); // RewindBox (adapt_buffer_last_hit)
                }
            }
            else
            {
                // No overlap, just create a new buffer.
                AddBuffer(new(_context, _physicalMemory, address, size, stage, sparseCompatible: false, []));
'''

GET_OLD = '''        private Buffer GetOrCreateBuffer(ulong address, ulong size, BufferStage stage)
        {
            Buffer buffer = size != 0
'''
GET_NEW = '''        private Buffer GetOrCreateBuffer(ulong address, ulong size, BufferStage stage)
        {
            // RewindBox (adapt_buffer_last_hit): a buffer known to contain the range is the one the search below returns.
            Buffer known = FindBufferHit(address, size != 0 ? size : 1);

            if (known != null)
            {
                return known;
            }

            Buffer buffer = size != 0
'''

TAIL_OLD = '''            return buffer;
        }

        /// <summary>
        /// Gets a buffer for a given memory range.
        /// A buffer overlapping with the specified range is assumed to already exist on the cache.
'''
TAIL_NEW = '''            return RememberIfContains(address, size != 0 ? size : 1, buffer); // RewindBox (adapt_buffer_last_hit)
        }

        /// <summary>
        /// Gets a buffer for a given memory range.
        /// A buffer overlapping with the specified range is assumed to already exist on the cache.
'''

# The members this adapter adds (the fixtures of the gates that compile the real BufferCache.cs members take them).
ADDED = FIELDS_NEW[len(FIELDS_OLD):]

PAIRS = ((FIELDS_OLD, FIELDS_NEW), (REMOVE_OLD, REMOVE_NEW), (CREATE_OLD, CREATE_NEW), (TOUCH_OLD, TOUCH_NEW), (GET_OLD, GET_NEW),
         (TAIL_OLD, TAIL_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[CACHE], old, new)
    return list(paths.values())
