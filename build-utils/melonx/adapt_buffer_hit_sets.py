"""The buffer cache's last-hit table holds a draw's buffers: 256 two-way sets, emptied per buffer (every title).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journal, pid 5954, four [MeloNX:hot] profiles of GPU.MainThread in
the world, 544 running samples): Buffer.OverlapsWith 34 own samples, CreateBufferAligned 14, GetOrCreateBuffer 5
(10.1 %, 9.9 % on IPA 736 before adapt_buffer_last_hit). In the Core's disassembly every one of CreateBufferAligned's
14 stack samples returns right after its call to OverlapsWith, past the inlined table: misses of the table. The table
of adapt_buffer_last_hit has 16 direct-mapped slots keyed by four bits of the page number, one buffer each, and is
emptied entirely whenever any buffer leaves the list; a draw binds up to 16 vertex streams, the index buffer, up to 18
uniform buffers per stage and storage buffers, in distinct buffers, so the slots keep evicting each other, and each
merge, eviction or trim empties the table.

Change (BufferCache.cs only):
- 256 sets of two ways (512 entries, 12 KiB), the set chosen by the page number folded with its higher bits; a hit in
  the second way moves it to the first; a remembered buffer goes to the first way and pushes the first to the second.
- A buffer leaving the list (RemoveBufferTracking, the only way out of _buffers) clears only its own entries: the
  list's buffers do not overlap and their bounds never change (Buffer.Address read-only, Size set in the constructor),
  so the other entries stay true.
- CreateBufferAligned asks the list for its leftmost overlapping buffer first (FindOverlap, one O(log n) search): when
  it contains the whole range it is the overlaps[0] the existing branch touched and remembered, without building the
  overlap span. Not FindOverlapFast: the list can hold two overlapping buffers once a merge recreates a multi-range
  buffer before the merged buffer is added (CreateBufferAligned, RecreateMultiRangeBuffers), and FindOverlapFast may
  then answer the other one (adversarial review of the lot). GetOrCreateBuffer's lookups are unchanged. In that state
  the table could keep an entry of the sub-buffer remembered before the merged buffer was added: AddBuffer drops the
  entries the new buffer overlaps (adapt_buffer_last_hit's table only lost them at the next removal of any buffer).

The same buffers are returned as before for every lookup; the answers come from the table more often. Expected on the
device: OverlapsWith, CreateBufferAligned and GetOrCreateBuffer lower in GPU.MainThread's profile. Not measured on an
iPhone. Applied after adapt_buffer_last_hit (its post-image). Rollback: drop this adapter from prepare_embedded.py and
ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'
BASELINE = {CACHE: '5eac40feb2d941ff5746ad90a9719c94746ce3eb275629226df928ebe6b3fe74'}

TABLE_OLD = '''        private const int BufferHitSlots = 16;
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
'''
TABLE_NEW = '''        // RewindBox (adapt_buffer_hit_sets): 256 sets of two ways, so that a draw's buffers stay in the table; a buffer
        // leaving the list clears only its own entries.
        private const int BufferHitSets = 256;
        private readonly BufferHit[] _bufferHits = new BufferHit[BufferHitSets * 2];

        private static int BufferHitSet(ulong address)
        {
            ulong page = address >> 12;

            return (int)((page ^ (page >> 8)) & (BufferHitSets - 1)) * 2;
        }

        private Buffer FindBufferHit(ulong address, ulong size)
        {
            ulong endAddress = address + size;

            if (endAddress <= address)
            {
                return null;
            }

            int set = BufferHitSet(address);
            ref BufferHit first = ref _bufferHits[set];

            if (first.Buffer != null && address >= first.Address && endAddress <= first.EndAddress)
            {
                return first.Buffer;
            }

            ref BufferHit second = ref _bufferHits[set + 1];

            if (second.Buffer != null && address >= second.Address && endAddress <= second.EndAddress)
            {
                BufferHit hit = second;
                second = first;
                first = hit;

                return hit.Buffer;
            }

            return null;
        }

        private void RememberBufferHit(ulong address, Buffer buffer)
        {
            int set = BufferHitSet(address);
            ref BufferHit first = ref _bufferHits[set];

            if (ReferenceEquals(first.Buffer, buffer))
            {
                return;
            }

            _bufferHits[set + 1] = first;
            first.Buffer = buffer;
            first.Address = buffer.Address;
            first.EndAddress = buffer.EndAddress;
        }
'''

CLEAR_OLD = '''            Array.Clear(_bufferHits); // RewindBox (adapt_buffer_last_hit): a buffer left the list
'''
CLEAR_NEW = '''            // RewindBox (adapt_buffer_last_hit, adapt_buffer_hit_sets): a buffer left the list; its own entries go.
            for (int i = 0; i < _bufferHits.Length; i++)
            {
                if (ReferenceEquals(_bufferHits[i].Buffer, buffer))
                {
                    _bufferHits[i] = default;
                }
            }
'''

CREATE_OLD = '''            Buffer known = FindBufferHit(address, size);

            if (known != null)
            {
                Touch(known);

                return;
            }

            ReadOnlySpan<Buffer> overlaps = _buffers.FindOverlapsAsSpan(address, size);
'''
CREATE_NEW = '''            Buffer known = FindBufferHit(address, size);

            if (known != null)
            {
                Touch(known);

                return;
            }

            // RewindBox (adapt_buffer_hit_sets): the leftmost overlapping buffer, when it contains the whole range, is the
            // overlaps[0] the branch below touches and remembers (one O(log n) search instead of the overlap span).
            Buffer single = _buffers.FindOverlap(address, size);

            if (single != null && single.FullyContains(address, size))
            {
                Touch(single);
                RememberBufferHit(address, single);

                return;
            }

            ReadOnlySpan<Buffer> overlaps = _buffers.FindOverlapsAsSpan(address, size);
'''

ADD_OLD = '''        private void AddBuffer(Buffer buffer)
        {
            _buffers.Add(buffer);
'''
ADD_NEW = '''        private void AddBuffer(Buffer buffer)
        {
            // RewindBox (adapt_buffer_hit_sets): entries of buffers the new one overlaps go (a merge can leave a recreated
            // multi-range buffer's sub-buffer in the list under the merged one; the lookups take the leftmost).
            for (int i = 0; i < _bufferHits.Length; i++)
            {
                if (_bufferHits[i].Buffer != null && _bufferHits[i].Address < buffer.EndAddress && buffer.Address < _bufferHits[i].EndAddress)
                {
                    _bufferHits[i] = default;
                }
            }

            _buffers.Add(buffer);
'''


PAIRS = ((TABLE_OLD, TABLE_NEW), (CLEAR_OLD, CLEAR_NEW), (CREATE_OLD, CREATE_NEW), (ADD_OLD, ADD_NEW))


def apply(source):
    path = source / CACHE
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, CACHE
    # The table is read and written by these methods only.
    text = path.read_text(encoding='utf-8-sig')
    assert not digests or (text.count('_bufferHits') == 4 and text.count('BufferHitSlots') == 4), CACHE
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
