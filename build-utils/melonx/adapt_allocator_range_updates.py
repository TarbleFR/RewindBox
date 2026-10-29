"""Update block suballocation splits and coalescence without redundant shifts.

For an ordinary nonwrapping free interval, the optional prefix and tail stay
at its existing sorted position. Replace the surviving interval in place and
insert at most one extra interval. The old remove/two-insert path shifts the
same suffix up to three times. Keep it for zero sizes, wrapped intervals and
duplicate/overlapping following offsets so its unusual behavior is preserved.
The lock, first-fit choice, alignment arithmetic and free/coalescing path stay
semantically unchanged. Coalescence replaces its surviving neighbor in place
and removes only the second joined neighbor, preserving the original list even
for unusual zero/wrapped ranges. No native-memory budget or sync policy changes.
"""
import hashlib
from adapt_session import once


RELATIVE = 'src/Ryujinx.Graphics.Vulkan/MemoryAllocatorBlockList.cs'
BASELINE = 'bb57d6943937c038bdcc7866a6da14ae5ceb6771d836e63403da519c6fc255ae'


def apply(source):
    path = source / RELATIVE
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)
    once(path, '''                        if (sizeDelta < range.Size && usableSize >= size)
                        {
                            _freeRanges.RemoveAt(i);''', '''                        if (sizeDelta < range.Size && usableSize >= size)
                        {
                            if (sizeDelta == 0 && usableSize == size)
                            {
                                _freeRanges.RemoveAt(i);
                                return alignedOffset;
                            }

                            ulong rangeEnd = range.Offset + range.Size;
                            if (size != 0 && rangeEnd >= range.Offset &&
                                (i == 0 || _freeRanges[i - 1].Offset < range.Offset) &&
                                (i + 1 == _freeRanges.Count || _freeRanges[i + 1].Offset >= rangeEnd))
                            {
                                ulong tailSize = usableSize - size;
                                if (sizeDelta != 0)
                                {
                                    _freeRanges[i] = new Range(range.Offset, sizeDelta);
                                    if (tailSize != 0)
                                    {
                                        _freeRanges.Insert(i + 1, new Range(alignedOffset + size, tailSize));
                                    }
                                }
                                else if (tailSize != 0)
                                {
                                    _freeRanges[i] = new Range(alignedOffset + size, tailSize);
                                }
                                else
                                {
                                    _freeRanges.RemoveAt(i);
                                }

                                return alignedOffset;
                            }

                            // Preserve the historical ordering for unusual zero,
                            // wrapped or duplicate-offset range configurations.
                            _freeRanges.RemoveAt(i);''')
    once(path, '''                if (index < _freeRanges.Count && _freeRanges[index].Offset == endOffset)
                {
                    endOffset = _freeRanges[index].Offset + _freeRanges[index].Size;
                    _freeRanges.RemoveAt(index);
                }

                if (index > 0 && _freeRanges[index - 1].Offset + _freeRanges[index - 1].Size == offset)
                {
                    offset = _freeRanges[index - 1].Offset;
                    _freeRanges.RemoveAt(--index);
                }

                range = new Range(offset, endOffset - offset);

                _freeRanges.Insert(index, range);''', '''                bool mergeNext = index < _freeRanges.Count && _freeRanges[index].Offset == endOffset;
                bool mergePrevious = index > 0 && _freeRanges[index - 1].Offset + _freeRanges[index - 1].Size == offset;

                if (mergeNext)
                {
                    endOffset = _freeRanges[index].Offset + _freeRanges[index].Size;
                }

                if (mergePrevious)
                {
                    offset = _freeRanges[index - 1].Offset;
                    if (mergeNext)
                    {
                        _freeRanges.RemoveAt(index);
                    }

                    _freeRanges[index - 1] = new Range(offset, endOffset - offset);
                }
                else if (mergeNext)
                {
                    _freeRanges[index] = new Range(offset, endOffset - offset);
                }
                else
                {
                    _freeRanges.Insert(index, range);
                }''')
    return [path]
