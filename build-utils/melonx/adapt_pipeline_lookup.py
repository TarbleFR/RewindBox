"""Keep exact Vulkan cache equality while bounding lookup and insertion work.

HashTableSlim previously had 16 fixed buckets and copied each bucket on every
insert. Grow bucket storage geometrically and redistribute stored hashes when
the average occupancy exceeds eight. Duplicate-key first-match behavior and
the ref-key API remain intact; removals clear the now-unused reference slot.

PipelineUid's XOR hash discarded field/element order. Mix active fields with
distinct weights, then fold array elements in order. Equality remains the
authority; no serialized shader/pipeline cache format or equality rule changes.
"""
import hashlib
from adapt_session import once


UPSTREAM = {
    'HashTableSlim.cs': '22f8a03d266f8e6f8107559de967d6e3f5d56dd023635691427f697a3576ade8',
    'PipelineUid.cs': '86f9ee7b54de323f80da642276262d1c1906a385dc7b0e7089b3755b3afa9ff3',
}


def apply(source):
    directory = source / 'src/Ryujinx.Graphics.Vulkan'
    paths = [directory / name for name in UPSTREAM]
    for path in paths:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == UPSTREAM[path.name], str(path)
    table, uid = paths
    once(table, '''        private const int TotalBuckets = 16; // Must be power of 2
        private const int TotalBucketsMask = TotalBuckets - 1;''', '''        private const int InitialBuckets = 16; // Must be power of 2.
        private const int EntriesPerBucket = 8;''')
    once(table, '        private readonly Bucket[] _hashTable = new Bucket[TotalBuckets];',
         '        private Bucket[] _hashTable = new Bucket[InitialBuckets];\n'
         '        private int _count;')
    once(table, '''            Entry entry = new()
            {
                Hash = key.GetHashCode(),
                Key = key,
                Value = value,
            };

            int hashCode = key.GetHashCode();
            int bucketIndex = hashCode & TotalBucketsMask;''', '''            int hashCode = key.GetHashCode();

            if (_count / _hashTable.Length >= EntriesPerBucket)
            {
                Grow();
            }

            Entry entry = new()
            {
                Hash = hashCode,
                Key = key,
                Value = value,
            };

            int bucketIndex = hashCode & (_hashTable.Length - 1);''')
    once(table, '                    Array.Resize(ref bucket.Entries, index + 1);',
         '                    Array.Resize(ref bucket.Entries, checked(index * 2));')
    once(table, '''            bucket.Length++;
        }

        public bool Remove''', '''            bucket.Length++;
            _count++;
        }

        private void Grow()
        {
            Bucket[] next = new Bucket[checked(_hashTable.Length * 2)];
            int mask = next.Length - 1;

            // Count first, so redistribution allocates each destination once.
            // Publish only when complete; allocation failure leaves this table usable.
            foreach (Bucket bucket in _hashTable)
            {
                foreach (ref Entry entry in bucket.AsSpan())
                {
                    next[entry.Hash & mask].Length++;
                }
            }

            for (int i = 0; i < next.Length; i++)
            {
                ref Bucket bucket = ref next[i];

                if (bucket.Length != 0)
                {
                    bucket.Entries = new Entry[bucket.Length];
                    bucket.Length = 0;
                }
            }

            foreach (Bucket bucket in _hashTable)
            {
                foreach (ref Entry entry in bucket.AsSpan())
                {
                    ref Bucket destination = ref next[entry.Hash & mask];
                    destination.Entries[destination.Length++] = entry;
                }
            }

            _hashTable = next;
        }

        public bool Remove''')
    once(table, '            ref Bucket bucket = ref _hashTable[hashCode & TotalBucketsMask];',
         '            ref Bucket bucket = ref _hashTable[hashCode & (_hashTable.Length - 1)];')
    once(table, '            Span<Entry> entries = _hashTable[hashCode & TotalBucketsMask].AsSpan();',
         '            Span<Entry> entries = _hashTable[hashCode & (_hashTable.Length - 1)].AsSpan();')
    once(table, '''                    bucket.Length--;

                    return true;''', '''                    bucket.Length--;
                    bucket.Entries[bucket.Length] = default;
                    _count--;

                    return true;''')

    text = uid.read_text()
    start = text.index('        public override int GetHashCode()\n')
    suffix = '    }\n}\n'
    assert text.endswith(suffix), str(uid)
    previous = text[start:-len(suffix)]
    replacement = previous
    for field, prime in zip(['Id0', 'Id1', 'Id2', 'Id3', 'Id4', 'Id5', 'Id6', 'Id7', 'Id8',
                             'AttachmentIntegerFormatMask'], [23, 29, 31, 37, 41, 43, 47, 53, 59, 61]):
        old = field + ' * 23'
        assert replacement.count(old) == 1, old
        replacement = replacement.replace(old, field + ' * ' + str(prime))
    replacement = replacement.replace('(LogicOpsAllowed ? 23UL : 0UL)', '(LogicOpsAllowed ? 67UL : 0UL)')
    # The original field coverage is retained, but each element is folded into
    # the running hash in order instead of XORing an unordered multiset.
    import re
    for name in ['vertexAttributeDescriptionsSpan', 'vertexBindingDescriptionsSpan',
                 'colorBlendAttachmentStateSpan', 'attachmentFormatsSpan']:
        lines = re.findall(r'^                hash64 \^= .*' + name + r'\[i\].*;\n', replacement, re.M)
        assert lines, name
        weighted = []
        for line, prime in zip(lines, [23, 29, 31, 37, 41, 43, 47, 53], strict=False):
            weighted.append(line.replace('hash64 ^=', 'elementHash ^=').replace('* 23;', '* ' + str(prime) + ';'))
        old = ''.join(lines)
        assert replacement.count(old) == 1, name
        replacement = replacement.replace(old, '                ulong elementHash = 0;\n' + ''.join(weighted) +
            '                hash64 = (hash64 ^ elementHash) * 1099511628211UL;\n')
    once(uid, previous, replacement)
    return paths
