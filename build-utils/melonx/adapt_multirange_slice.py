"""Slice physical regions without temporary lists or oversized backing arrays.

Single-fragment results stay inline. Multi-fragment results count only the
suffix that contains the first match, then fill a private exact-sized array.
Both passes preserve the original unsigned arithmetic and signed termination
checks, including holes and wrapped edge inputs. Existing producers publish
fresh arrays and never mutate them afterwards; slices never alias an input.
Concurrent mutation by an external caller is not a snapshot guarantee. Normal
array bounds and a final count check prevent an underfilled result escaping.
"""
import hashlib
from adapt_session import once


REPLACEMENT = '''        public MultiRange Slice(ulong offset, ulong size)
        {
            if (HasSingleRange)
            {
                ArgumentOutOfRangeException.ThrowIfGreaterThan(size, _singleRange.Size - offset);

                return new MultiRange(_singleRange.Address + offset, size);
            }

            for (int index = 0; index < _ranges.Length; index++)
            {
                MemoryRange range = _ranges[index];

                if ((long)offset <= 0)
                {
                    // Use the original signed termination test even for wrapped
                    // inputs, and keep the unmapped address sentinel unchanged.
                    if ((long)(size - range.Size) <= 0 || index == _ranges.Length - 1)
                    {
                        return new MultiRange(range.Address, Math.Min(size, range.Size));
                    }

                    return SliceMultiple(_ranges, index, offset, size);
                }
                else if (offset < range.Size)
                {
                    ulong sliceSize = Math.Min(size, range.Size - offset);

                    if ((long)(size - sliceSize) <= 0 || index == _ranges.Length - 1)
                    {
                        ulong address = range.Address == InvalidAddress ? InvalidAddress : range.Address + offset;
                        return new MultiRange(address, sliceSize);
                    }

                    return SliceMultiple(_ranges, index, offset, size);
                }

                if ((long)size <= 0)
                {
                    break;
                }

                offset -= range.Size;
            }

            return new MultiRange(Array.Empty<MemoryRange>());
        }

        // Count only the suffix found above, then fill one private exact-sized
        // result array. Published physical-range arrays are not mutated by their
        // producers; concurrent caller mutation is not a snapshot contract.
        private static MultiRange SliceMultiple(MemoryRange[] source, int start, ulong offset, ulong size)
        {
            ulong skip = offset;
            ulong remaining = size;
            int count = 0;
            for (int index = start; index < source.Length; index++)
            {
                MemoryRange range = source[index];
                if ((long)skip <= 0)
                {
                    count++;
                    remaining -= range.Size;
                }
                else if (skip < range.Size)
                {
                    count++;
                    remaining -= Math.Min(remaining, range.Size - skip);
                }
                if ((long)remaining <= 0) break;
                skip -= range.Size;
            }
            if (count == 1)
            {
                // Wrapped edge inputs can leave only the first match after a
                // longer search. They still need no temporary result array.
                MemoryRange first = source[start];
                if ((long)offset <= 0)
                {
                    return new MultiRange(first.Address, Math.Min(size, first.Size));
                }

                ulong address = first.Address == InvalidAddress ? InvalidAddress : first.Address + offset;
                return new MultiRange(address, Math.Min(size, first.Size - offset));
            }

            MemoryRange[] result = new MemoryRange[count];
            int output = 0;
            for (int index = start; index < source.Length; index++)
            {
                MemoryRange range = source[index];
                if ((long)offset <= 0)
                {
                    result[output++] = new MemoryRange(range.Address, Math.Min(size, range.Size));
                    size -= range.Size;
                }
                else if (offset < range.Size)
                {
                    ulong sliceSize = Math.Min(size, range.Size - offset);
                    result[output++] = new MemoryRange(range.Address == InvalidAddress ? InvalidAddress : range.Address + offset, sliceSize);
                    size -= sliceSize;
                }
                if ((long)size <= 0) break;
                offset -= range.Size;
            }
            if (output != count)
            {
                throw new InvalidOperationException("Physical ranges changed while slicing.");
            }

            return new MultiRange(result);
        }

'''


def apply(source):
    path = source / 'src/Ryujinx.Memory/Range/MultiRange.cs'
    text = path.read_text(encoding='utf-8-sig')
    start = text.index('        public MultiRange Slice(ulong offset, ulong size)')
    end = text.index('        /// <summary>\n        /// Gets the physical region', start)
    before = text[start:end]
    assert hashlib.sha256(before.encode()).hexdigest() == 'c49794aa2acfa9f55a239ff0731f413cf36fdf463ddeb07f5ed7970cfdc50deb', 'Unknown MultiRange.Slice body'
    once(path, before, REPLACEMENT)
    return [path]
