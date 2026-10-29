"""Find the first containing virtual buffer without collecting every overlap.

The old GPU binding lookup built an array, appended all interval hits, removed
duplicates quadratically, then used just the first containing buffer. A struct
predicate now visits intervals in the exact existing tree/subrange order and
stops at that buffer. At most eight pure Contains checks are attempted; a ninth
candidate resumes the exact old collect/deduplicate path, bounding extra work
on fragmented misses. It adds no cache or shared query state. The generic API
documents physical visits (not value-equality deduplication); only the reviewed
identity-equality MultiRangeBuffer caller uses it. All physical synchronization,
dirty notification, mapping and sparse-buffer decisions remain in place.
"""
import hashlib
from adapt_session import once


BASELINE = {
    'src/Ryujinx.Common/Collections/IntervalTree.cs': 'ce0acc84e8f7fccfab31e72525e47155038b1d0e051e0eb1f343de6ed4e47c67',
    'src/Ryujinx.Memory/Range/MultiRangeList.cs': 'b8fd139c5abfef3cb8184abe4d76fdafece608788c1dc5d2e578ffe2e4a265ec',
    'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs': 'b164837dc4320cab56ef58ea9c0cd1a70a35a95a43f25d7a408c7200c063e06f',
    'src/Ryujinx.Graphics.Gpu/Memory/MultiRangeBuffer.cs': 'ebb48b7a07c3b370590ab982e43024d1bd124972d5635cf39ce50033370370a8',
}


def apply(source):
    for relative, expected in BASELINE.items():
        assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == expected, relative
    tree = source / 'src/Ryujinx.Common/Collections/IntervalTree.cs'
    ranges = source / 'src/Ryujinx.Memory/Range/MultiRangeList.cs'
    cache = source / 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'
    once(tree, '''namespace Ryujinx.Common.Collections
{
''', '''namespace Ryujinx.Common.Collections
{
    /// <summary>
    /// A non-allocating overlap predicate. It must not mutate the queried tree.
    /// </summary>
    public interface IIntervalTreePredicate<TValue>
    {
        bool Match(TValue value);
    }

''')
    once(tree, '''        /// <summary>
        /// Adds a new interval into the tree whose start is <paramref name="start"/>, end is <paramref name="end"/> and value is <paramref name="value"/>.
''', '''        /// <summary>
        /// Finds the first overlapping value accepted by a stack-owned predicate.
        /// Visits the same left/node/right order as Get, without an output array.
        /// Each physical interval is visited; equal values are not deduplicated.
        /// The predicate must not mutate this tree.
        /// </summary>
        public bool TryFindOverlap<TPredicate>(TKey start, TKey end, ref TPredicate predicate, out TValue value)
            where TPredicate : struct, IIntervalTreePredicate<TValue>
        {
            ArgumentNullException.ThrowIfNull(start);
            ArgumentNullException.ThrowIfNull(end);

            return TryFindOverlap(Root, start, end, ref predicate, out value);
        }

        /// <summary>
        /// Adds a new interval into the tree whose start is <paramref name="start"/>, end is <paramref name="end"/> and value is <paramref name="value"/>.
''')
    once(tree, '''        /// <summary>
        /// Inserts a new node into the tree with a given <paramref name="start"/>, <paramref name="end"/> and <paramref name="value"/>.
''', '''        private static bool TryFindOverlap<TPredicate>(IntervalTreeNode<TKey, TValue> node,
            TKey start, TKey end, ref TPredicate predicate, out TValue value)
            where TPredicate : struct, IIntervalTreePredicate<TValue>
        {
            if (node == null || start.CompareTo(node.Max) >= 0)
            {
                value = default;
                return false;
            }

            if (TryFindOverlap(node.Left, start, end, ref predicate, out value))
            {
                return true;
            }

            if (end.CompareTo(node.Start) > 0)
            {
                if (start.CompareTo(node.End) < 0)
                {
                    foreach (RangeNode<TKey, TValue> overlap in node.Values)
                    {
                        if (start.CompareTo(overlap.End) < 0 && predicate.Match(overlap.Value))
                        {
                            value = overlap.Value;
                            return true;
                        }
                    }
                }

                return TryFindOverlap(node.Right, start, end, ref predicate, out value);
            }

            value = default;
            return false;
        }

        /// <summary>
        /// Inserts a new node into the tree with a given <paramref name="start"/>, <paramref name="end"/> and <paramref name="value"/>.
''')
    once(ranges, '''        /// <summary>
        /// Gets all items on the list starting at the specified memory address.
''', '''        /// <summary>
        /// Finds the first accepted physical overlap in query-subrange/tree order.
        /// Unlike FindOverlaps this does not deduplicate equal values. A pure
        /// predicate may therefore see one item more than once before a match.
        /// No output array or persistent query state is needed.
        /// </summary>
        public bool TryFindOverlap<TPredicate>(MultiRange range, ref TPredicate predicate, out T value)
            where TPredicate : struct, IIntervalTreePredicate<T>
        {
            for (int i = 0; i < range.Count; i++)
            {
                MemoryRange subrange = range.GetSubRange(i);

                if (MemoryRange.IsInvalid(ref subrange))
                {
                    continue;
                }

                if (_items.TryFindOverlap(subrange.Address, subrange.EndAddress, ref predicate, out value))
                {
                    return true;
                }
            }

            value = default;
            return false;
        }

        /// <summary>
        /// Gets all items on the list starting at the specified memory address.
''')
    once(cache, '''            MultiRangeBuffer[] overlaps = new MultiRangeBuffer[10];

            int overlapCount = _multiRangeBuffers.FindOverlaps(range, ref overlaps);

            MultiRangeBuffer buffer = null;

            for (int i = 0; i < overlapCount; i++)
            {
                if (overlaps[i].Range.Contains(range))
                {
                    buffer = overlaps[i];
                    break;
                }
            }
''', '''            BufferContainsRange predicate = new(range);
            _multiRangeBuffers.TryFindOverlap(range, ref predicate, out MultiRangeBuffer buffer);

            if (predicate.Exhausted)
            {
                // Keep the original deduplication path for complex misses.
                // Rechecking at most eight pure predicates is bounded, unlike
                // repeatedly testing a highly fragmented alias at every hit.
                MultiRangeBuffer[] overlaps = new MultiRangeBuffer[10];
                int overlapCount = _multiRangeBuffers.FindOverlaps(range, ref overlaps);
                buffer = null;

                for (int i = 0; i < overlapCount; i++)
                {
                    if (overlaps[i].Range.Contains(range))
                    {
                        buffer = overlaps[i];
                        break;
                    }
                }
            }
''')
    once(cache, '''        /// <summary>
        /// Gets a physical buffer from the cache, recreating it if it was evicted after
''', '''        private struct BufferContainsRange : IIntervalTreePredicate<MultiRangeBuffer>
        {
            private readonly MultiRange _range;
            private MultiRangeBuffer _lastBuffer;
            private int _remainingChecks;

            public bool Exhausted { get; private set; }

            public BufferContainsRange(MultiRange range)
            {
                _range = range;
                _lastBuffer = null;
                _remainingChecks = 8;
                Exhausted = false;
            }

            public bool Match(MultiRangeBuffer buffer)
            {
                if (ReferenceEquals(buffer, _lastBuffer))
                {
                    return false;
                }

                if (_remainingChecks == 0)
                {
                    // Stop traversal. This value is never used as a match:
                    // the owner checks Exhausted before using the result.
                    Exhausted = true;
                    return true;
                }

                _lastBuffer = buffer;
                _remainingChecks--;
                return buffer.Range.Contains(_range);
            }
        }

        /// <summary>
        /// Gets a physical buffer from the cache, recreating it if it was evicted after
''')
    # BufferCache already imports the range namespace, but the predicate's
    # contract belongs to Common and is not transitively imported in C#.
    once(cache, 'using Ryujinx.Common.Logging;', 'using Ryujinx.Common.Collections;\nusing Ryujinx.Common.Logging;')
    return [tree, ranges, cache]
