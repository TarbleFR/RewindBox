"""Release GPU modified-range snapshots on every exit, without rooting buffers.

The upstream snapshots are necessary: callbacks can mutate the range graph.
Do not substitute a borrowed span. Return each private array, clear its object
references, and release the existing lock when a callback/fence raises. In
particular, a snapshot containing only current/future syncs previously escaped
without being returned, allocating again on the next readback attempt.
"""
import hashlib
from adapt_session import once


def apply(source):
    path = source / 'src/Ryujinx.Graphics.Gpu/Memory/BufferModifiedRangeList.cs'
    expected = '606809c5963a3ce1302a0f22615841476bc2c495a18176f59e40f71e265f178e'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, str(path)

    once(path, '''            Lock.EnterReadLock();
            BufferModifiedRange[] overlaps = FindOverlapsAsArray(address, size, out int length);
            Lock.ExitReadLock();

            if (length != 0)
            {
                for (int i = 0; i < length; i++)
                {
                    BufferModifiedRange overlap = overlaps[i];
                    rangeAction(overlap.Address, overlap.Size);
                }
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
                ArrayPool<BufferModifiedRange>.Shared.Return(overlaps);
            }''', '''            BufferModifiedRange[] overlaps;
            int length;
            Lock.EnterReadLock();
            try
            {
                overlaps = FindOverlapsAsArray(address, size, out length);
            }
            finally
            {
                Lock.ExitReadLock();
            }

            if (overlaps != null)
            {
                try
                {
                    for (int i = 0; i < length; i++)
                    {
                        BufferModifiedRange overlap = overlaps[i];
                        rangeAction(overlap.Address, overlap.Size);
                    }
                }
                finally
                {
                    ArrayPool<BufferModifiedRange>.Shared.Return(overlaps, clearArray: true);
                }
            }''')

    once(path, '''            Lock.EnterWriteLock();
            // We use the non-span method here because the array is partially modified by the code, which would invalidate a span.
            BufferModifiedRange[] overlaps = FindOverlapsAsArray(address, size, out int rangeCount);

            if (rangeCount == 0)
            {
                Lock.ExitWriteLock();
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
                return;
            }

            // First, determine which syncpoint to wait on.
            // This is the latest syncpoint that is not equal to the current sync.

            long highestDiff = long.MinValue;

            for (int i = 0; i < rangeCount; i++)
            {
                BufferModifiedRange overlap = overlaps![i];

                long diff = (long)(overlap.SyncNumber - currentSync);

                if (diff < 0 && diff > highestDiff)
                {
                    highestDiff = diff;
                }
            }

            if (highestDiff == long.MinValue)
            {
                Lock.ExitWriteLock();
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
                return;
            }

            // Wait for the syncpoint.
            _context.Renderer.WaitSync(currentSync + (ulong)highestDiff);

            RemoveRangesAndFlush(overlaps, rangeCount, highestDiff, currentSync, address, endAddress);
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
            ArrayPool<BufferModifiedRange>.Shared.Return(overlaps!);
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
            Lock.ExitWriteLock();''', '''            BufferModifiedRange[] overlaps = null;
            Lock.EnterWriteLock();
            try
            {
                // A private snapshot is required while the range list is modified.
                overlaps = FindOverlapsAsArray(address, size, out int rangeCount);

                if (rangeCount == 0)
                {
                    return;
                }

                // Preserve the latest syncpoint strictly before the current sync.
                long highestDiff = long.MinValue;

                for (int i = 0; i < rangeCount; i++)
                {
                    BufferModifiedRange overlap = overlaps[i];
                    long diff = (long)(overlap.SyncNumber - currentSync);

                    if (diff < 0 && diff > highestDiff)
                    {
                        highestDiff = diff;
                    }
                }

                if (highestDiff == long.MinValue)
                {
                    return;
                }

                _context.Renderer.WaitSync(currentSync + (ulong)highestDiff);
                RemoveRangesAndFlush(overlaps, rangeCount, highestDiff, currentSync, address, endAddress);
            }
            finally
            {
                try
                {
                    if (overlaps != null)
                    {
                        ArrayPool<BufferModifiedRange>.Shared.Return(overlaps, clearArray: true);
                    }
                }
                finally
                {
                    Lock.ExitWriteLock();
                }
            }''')

    once(path, '''            ranges.Lock.EnterReadLock();
            int rangesCount = ranges.Count;
            BufferModifiedRange[] inheritRanges = ArrayPool<BufferModifiedRange>.Shared.Rent(ranges.Count);
            ranges.Items.AsSpan(0, ranges.Count).CopyTo(inheritRanges);
            ranges.Lock.ExitReadLock();

            // Copy over the migration from the previous range list''', '''            BufferModifiedRange[] inheritRanges = null;
            try
            {
                int rangesCount;
                ranges.Lock.EnterReadLock();
                try
                {
                    rangesCount = ranges.Count;
                    inheritRanges = ArrayPool<BufferModifiedRange>.Shared.Rent(rangesCount);
                    ranges.Items.AsSpan(0, rangesCount).CopyTo(inheritRanges);
                }
                finally
                {
                    ranges.Lock.ExitReadLock();
                }

                InheritRangeSnapshot(ranges, inheritRanges, rangesCount, registerRangeAction);
            }
            finally
            {
                if (inheritRanges != null)
                {
                    ArrayPool<BufferModifiedRange>.Shared.Return(inheritRanges, clearArray: true);
                }
            }
        }

        private void InheritRangeSnapshot(BufferModifiedRangeList ranges, BufferModifiedRange[] inheritRanges,
            int rangesCount, Action<ulong, ulong> registerRangeAction)
        {
            // Copy over the migration from the previous range list''')
    once(path, '''            Lock.EnterWriteLock();

            for (int i = 0; i < rangesCount; i++)
            {
                BufferModifiedRange range = inheritRanges[i];
                Add(range);
            }

            Lock.ExitWriteLock();''', '''            Lock.EnterWriteLock();
            try
            {
                for (int i = 0; i < rangesCount; i++)
                {
                    BufferModifiedRange range = inheritRanges[i];
                    Add(range);
                }
            }
            finally
            {
                Lock.ExitWriteLock();
            }''')
    once(path, '''\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
            ArrayPool<BufferModifiedRange>.Shared.Return(inheritRanges);
        }''', '''        }''')
    migration = source / 'src/Ryujinx.Graphics.Gpu/Memory/BufferMigration.cs'
    assert hashlib.sha256(migration.read_bytes()).hexdigest() == \
        '7a28ddf2306df5d82cb2a0d8b21208cb4bc835e0d4a47e9c8c8760cd7cdc3584', str(migration)
    text = migration.read_text(encoding='utf-8-sig')
    enter = '                Interlocked.Increment(ref _refCount);\n'
    leave = '                Interlocked.Decrement(ref _refCount);'
    assert text.count(enter) == text.count(leave) == 1, str(migration)
    body = text[text.index(enter) + len(enter):text.index(leave)]
    guarded = ''.join('    ' + line if line.strip() else line for line in body.splitlines(keepends=True))
    once(migration, enter + body + leave,
         enter + '                try\n                {\n' + guarded +
         '                }\n                finally\n                {\n' +
         '                    Interlocked.Decrement(ref _refCount);\n                }')
    return [path, migration]
