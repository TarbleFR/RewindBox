"""A buffer's pending mirror data is kept in pages, not in a managed copy of the whole buffer (Core 723 candidate, RAM).

IPA 718, Hogwarts Legacy (pid 44597): the large object heap stays at about 507 MiB in play with about 250 MiB of holes
(gcEvent and memoryInventory lines: `loh [507, 213-249, 507, 250-267]`), about 266 MiB still live after the first-frame
compaction (adapt_safe_point_compaction), and it fragments again within 20 s of that compaction. On a tile-based GPU
(`VulkanRenderer.IsTBDR`, every Apple GPU) every host-mapped buffer uses mirrors: an update of a range the GPU may still
be reading is kept as pending data and each binding of it reads a staging copy (mirror) instead. That pending data was a
`new byte[Size]`: a managed copy of the WHOLE buffer, allocated at the buffer's first such update (vertex, index and
uniform buffers updated while in flight) and kept until the buffer is disposed, whatever the few bytes pending; a large
buffer's copy is a large-object-heap array, and every buffer the cache recreates (merges, growth) allocates a new one.

Change (BufferHolder.cs only, Vulkan backend, every title):
- the pending bytes live in 16 KiB pages rented from the shared array pool (small-object heap), one per page the pending
  ranges touch; a page is returned as soon as no pending range overlaps it (after a direct write, an upload or the
  buffer's disposal), so the memory follows the bytes actually pending, not the buffer's size;
- the mirror fill reads the same bytes in the same order as BufferMirrorRangeList.FillData (the base data, then each
  pending range over it), from the pages;
- an upload of pending data gathers every range's bytes before its first SetData (which releases the pages no pending
  range covers any more; two ranges can share a page), then returns the gathered array;
- journal (stage bufferMirrors, at most 16 lines): when the sum of the sizes of the buffers holding pending data (what
  the full copies held) or the pages' bytes reach a new 64 MiB step: both figures and the buffer count.
Unchanged: when a mirror is used, its staging copy, the range list, rebinds, flushes, every buffer type's path. Not
measured on an iPhone. Fail closed on drift: the file must be the Core 721 preparation's.

State (10 Nov): NOT WIRED. Differential check of the extracted PendingPages against the delivered full copy and the real
BufferMirrorRangeList (test/melonx_mirror_pending_pages/Program.cs, 400 random buffers + a 32 MiB buffer, 126 000
operations, 41 147 byte comparisons): no difference, pages exactly those the pending ranges overlap, all returned.
Limit found: a pending range is written to the buffer only when it is rewritten or forced out, so a ring of per-frame
data becomes pending almost everywhere and the pages then hold about as much as the copy (stress: 23 of 32 MiB). The
part that makes the gain general, still to write with its own gate: settle the pending ranges no command buffer uses any
more (the direct path's own condition: not rented, or the range not in use) by writing them to the mapped buffer and
dropping them, bounded per call; that also removes the mirror copies of those ranges at their next binding.
"""
import hashlib
from adapt_session import once

HOLDER = 'src/Ryujinx.Graphics.Vulkan/BufferHolder.cs'
BASELINE = {
    HOLDER: '4de2cceb304550b192f2c37d89d84aea109012aadefddf2fe1527a5e942a778d',
}
TAG = 'RewindBox (adapt_mirror_pending_pages)'

FIELD_OLD = '''        private byte[] _pendingData;
'''
FIELD_NEW = '''        // RewindBox (adapt_mirror_pending_pages): the pending bytes in pages (PendingPages), not a copy of the whole buffer.
        private PendingPages _pendingData;
'''

FILL_OLD = '''            Span<byte> baseData = new((void*)(_map + offset), size);
            Span<byte> modData = _pendingData.AsSpan(offset, size);

            StagingBufferReserved? newMirror = _gd.BufferManager.StagingBuffer.TryReserveData(cbs, size);

            if (newMirror != null)
            {
                StagingBufferReserved mirror = newMirror.Value;
                _pendingDataRanges.FillData(baseData, modData, offset, new Span<byte>((void*)(mirror.Buffer._map + mirror.Offset), size));
'''
FILL_NEW = '''            Span<byte> baseData = new((void*)(_map + offset), size);

            StagingBufferReserved? newMirror = _gd.BufferManager.StagingBuffer.TryReserveData(cbs, size);

            if (newMirror != null)
            {
                StagingBufferReserved mirror = newMirror.Value;
                // RewindBox (adapt_mirror_pending_pages): BufferMirrorRangeList.FillData's fill, the pending bytes read from pages.
                _pendingData.Fill(_pendingDataRanges, baseData, offset, new Span<byte>((void*)(mirror.Buffer._map + mirror.Offset), size));
'''

UPLOAD_OLD = '''            if (ranges != null)
            {
                _pendingDataRanges.Remove(offset, size);

                foreach (BufferMirrorRangeList.Range range in ranges)
                {
                    int rangeOffset = Math.Max(offset, range.Offset);
                    int rangeSize = Math.Min(offset + size, range.End) - rangeOffset;

                    if (_gd.PipelineInternal.CurrentCommandBuffer.CommandBuffer.Handle == cbs.CommandBuffer.Handle)
                    {
                        SetData(rangeOffset, _pendingData.AsSpan(rangeOffset, rangeSize), cbs, _gd.PipelineInternal.EndRenderPassDelegate, false);
                    }
                    else
                    {
                        SetData(rangeOffset, _pendingData.AsSpan(rangeOffset, rangeSize), cbs, null, false);
                    }
                }
            }
'''
UPLOAD_NEW = '''            if (ranges != null)
            {
                _pendingDataRanges.Remove(offset, size);

                // RewindBox (adapt_mirror_pending_pages): every range's bytes are gathered before the first upload, which
                // releases the pages no pending range overlaps any more (two of these ranges can share a page).
                byte[] gathered = _pendingData.Gather(ranges, offset, size);
                int position = 0;

                try
                {
                    foreach (BufferMirrorRangeList.Range range in ranges)
                    {
                        int rangeOffset = Math.Max(offset, range.Offset);
                        int rangeSize = Math.Min(offset + size, range.End) - rangeOffset;
                        ReadOnlySpan<byte> rangeData = gathered.AsSpan(position, rangeSize);
                        position += rangeSize;

                        if (_gd.PipelineInternal.CurrentCommandBuffer.CommandBuffer.Handle == cbs.CommandBuffer.Handle)
                        {
                            SetData(rangeOffset, rangeData, cbs, _gd.PipelineInternal.EndRenderPassDelegate, false);
                        }
                        else
                        {
                            SetData(rangeOffset, rangeData, cbs, null, false);
                        }
                    }
                }
                finally
                {
                    System.Buffers.ArrayPool<byte>.Shared.Return(gathered);
                    _pendingData.Release(_pendingDataRanges, offset, size);
                }
            }
'''

DIRECT_OLD = '''                    if (_pendingData != null)
                    {
                        bool removed = _pendingDataRanges.Remove(offset, dataSize);
'''
DIRECT_NEW = '''                    if (_pendingData != null)
                    {
                        bool removed = _pendingDataRanges.Remove(offset, dataSize);
                        _pendingData.Release(_pendingDataRanges, offset, dataSize); // RewindBox (adapt_mirror_pending_pages)
'''

WRITE_OLD = '''                if (_pendingData == null)
                {
                    _pendingData = new byte[Size];
                    _mirrors = new Dictionary<ulong, StagingBufferReserved>();
                }

                data[..dataSize].CopyTo(_pendingData.AsSpan(offset, dataSize));
'''
WRITE_NEW = '''                if (_pendingData == null)
                {
                    _pendingData = new PendingPages(Size); // RewindBox (adapt_mirror_pending_pages)
                    _mirrors = new Dictionary<ulong, StagingBufferReserved>();
                }

                _pendingData.Write(offset, data[..dataSize]);
'''

FALLTHROUGH_OLD = '''            if (_pendingData != null)
            {
                _pendingDataRanges.Remove(offset, dataSize);
            }

            if (cbs != null &&
'''
FALLTHROUGH_NEW = '''            if (_pendingData != null)
            {
                _pendingDataRanges.Remove(offset, dataSize);
                _pendingData.Release(_pendingDataRanges, offset, dataSize); // RewindBox (adapt_mirror_pending_pages)
            }

            if (cbs != null &&
'''

DISPOSE_OLD = '''            _flushLock.EnterWriteLock();

            ClearFlushFence();

            _flushLock.ExitWriteLock();
        }
    }
}
'''
DISPOSE_NEW = '''            _flushLock.EnterWriteLock();

            ClearFlushFence();

            _flushLock.ExitWriteLock();

            _pendingData?.ReleaseAll(); // RewindBox (adapt_mirror_pending_pages)
        }

        // RewindBox (adapt_mirror_pending_pages): the bytes of the pending ranges (_pendingDataRanges) in 16 KiB pages rented
        // from the shared pool, instead of a managed copy of the whole buffer kept for its lifetime. Only bytes inside a
        // pending range are ever read (the mirror fill and the uploads read the ranges only); Write precedes the range's Add,
        // and a page is returned only once no pending range overlaps it, so every pending byte has its page. Render thread
        // only, as the rest of the mirror state.
        internal sealed class PendingPages
        {
            internal const int PageShift = 14;
            internal const int PageSize = 1 << PageShift;
            private const long ReportStep = 64L << 20;
            private const int MaxReports = 16;

            private static long _fullBytes;
            private static long _pageBytes;
            private static int _buffers;
            private static long _nextFullReport = ReportStep;
            private static long _nextPageReport = ReportStep;
            private static int _reports;
            private static int _missingPages;

            private readonly int _size;
            private readonly Dictionary<int, byte[]> _pages = new();
            private bool _released;

            public PendingPages(int size)
            {
                _size = size;
                Interlocked.Increment(ref _buffers);
                Interlocked.Add(ref _fullBytes, size);
                Report();
            }

            internal static long FullBytes => Interlocked.Read(ref _fullBytes);
            internal static long PageBytes => Interlocked.Read(ref _pageBytes);
            internal static int MissingPages => Volatile.Read(ref _missingPages);
            internal int PageCount => _pages.Count;

            public void Write(int offset, ReadOnlySpan<byte> data)
            {
                bool added = false;

                while (!data.IsEmpty)
                {
                    int index = offset >> PageShift;
                    int inPage = offset & (PageSize - 1);
                    int count = Math.Min(PageSize - inPage, data.Length);

                    if (!_pages.TryGetValue(index, out byte[] page))
                    {
                        page = System.Buffers.ArrayPool<byte>.Shared.Rent(PageSize);
                        _pages.Add(index, page);
                        Interlocked.Add(ref _pageBytes, PageSize);
                        added = true;
                    }

                    data[..count].CopyTo(page.AsSpan(inPage, count));
                    data = data[count..];
                    offset += count;
                }

                if (added)
                {
                    Report();
                }
            }

            public void CopyTo(int offset, Span<byte> destination)
            {
                while (!destination.IsEmpty)
                {
                    int index = offset >> PageShift;
                    int inPage = offset & (PageSize - 1);
                    int count = Math.Min(PageSize - inPage, destination.Length);

                    if (_pages.TryGetValue(index, out byte[] page))
                    {
                        page.AsSpan(inPage, count).CopyTo(destination[..count]);
                    }
                    else
                    {
                        // Not reachable while the invariant holds (the gate checks it); counted rather than thrown.
                        destination[..count].Clear();
                        Interlocked.Increment(ref _missingPages);
                    }

                    destination = destination[count..];
                    offset += count;
                }
            }

            // BufferMirrorRangeList.FillData, with modData[i] read as the pending byte at offset + i.
            public void Fill(in BufferMirrorRangeList ranges, Span<byte> baseData, int offset, Span<byte> result)
            {
                int size = baseData.Length;
                int endOffset = offset + size;

                if (ranges.All() is not List<BufferMirrorRangeList.Range> list)
                {
                    baseData.CopyTo(result);
                    return;
                }

                int srcOffset = offset;
                int dstOffset = 0;
                bool activeRange = false;

                for (int i = 0; i < list.Count; i++)
                {
                    BufferMirrorRangeList.Range range = list[i];

                    int rangeEnd = range.Offset + range.Size;

                    if (activeRange)
                    {
                        if (range.Offset >= endOffset)
                        {
                            break;
                        }
                    }
                    else
                    {
                        if (rangeEnd <= offset)
                        {
                            continue;
                        }

                        activeRange = true;
                    }

                    int baseSize = range.Offset - srcOffset;

                    if (baseSize > 0)
                    {
                        baseData.Slice(dstOffset, baseSize).CopyTo(result.Slice(dstOffset, baseSize));
                        srcOffset += baseSize;
                        dstOffset += baseSize;
                    }

                    int modSize = Math.Min(rangeEnd - srcOffset, endOffset - srcOffset);
                    if (modSize != 0)
                    {
                        CopyTo(offset + dstOffset, result.Slice(dstOffset, modSize));
                        srcOffset += modSize;
                        dstOffset += modSize;
                    }
                }

                int baseSizeEnd = endOffset - srcOffset;

                if (baseSizeEnd > 0)
                {
                    baseData.Slice(dstOffset, baseSizeEnd).CopyTo(result.Slice(dstOffset, baseSizeEnd));
                }
            }

            // The bytes UploadPendingData sends, range after range, clipped to [offset, offset + size), in a rented array.
            public byte[] Gather(List<BufferMirrorRangeList.Range> ranges, int offset, int size)
            {
                int total = 0;

                foreach (BufferMirrorRangeList.Range range in ranges)
                {
                    total += Math.Min(offset + size, range.End) - Math.Max(offset, range.Offset);
                }

                byte[] gathered = System.Buffers.ArrayPool<byte>.Shared.Rent(Math.Max(total, 1));
                int position = 0;

                foreach (BufferMirrorRangeList.Range range in ranges)
                {
                    int rangeOffset = Math.Max(offset, range.Offset);
                    int rangeSize = Math.Min(offset + size, range.End) - rangeOffset;

                    CopyTo(rangeOffset, gathered.AsSpan(position, rangeSize));
                    position += rangeSize;
                }

                return gathered;
            }

            // Returns the pages of [offset, offset + size) that no pending range overlaps any more.
            public void Release(in BufferMirrorRangeList ranges, int offset, int size)
            {
                if (_pages.Count == 0 || size <= 0)
                {
                    return;
                }

                int first = offset >> PageShift;
                int last = (int)(((long)offset + size - 1) >> PageShift);

                if (last - first + 1 <= _pages.Count)
                {
                    for (int index = first; index <= last; index++)
                    {
                        ReleaseIfUncovered(ranges, index);
                    }
                }
                else
                {
                    List<int> candidates = null;

                    foreach (int index in _pages.Keys)
                    {
                        if (index >= first && index <= last)
                        {
                            (candidates ??= []).Add(index);
                        }
                    }

                    if (candidates != null)
                    {
                        foreach (int index in candidates)
                        {
                            ReleaseIfUncovered(ranges, index);
                        }
                    }
                }
            }

            private void ReleaseIfUncovered(in BufferMirrorRangeList ranges, int index)
            {
                if (_pages.TryGetValue(index, out byte[] page) && !ranges.OverlapsWith(index << PageShift, PageSize))
                {
                    _pages.Remove(index);
                    System.Buffers.ArrayPool<byte>.Shared.Return(page);
                    Interlocked.Add(ref _pageBytes, -PageSize);
                }
            }

            public void ReleaseAll()
            {
                if (_released)
                {
                    return;
                }

                _released = true;

                foreach (byte[] page in _pages.Values)
                {
                    System.Buffers.ArrayPool<byte>.Shared.Return(page);
                }

                Interlocked.Add(ref _pageBytes, -(long)_pages.Count * PageSize);
                _pages.Clear();
                Interlocked.Add(ref _fullBytes, -_size);

                if (Interlocked.Decrement(ref _buffers) == 0)
                {
                    // No buffer holds pending data (the session's buffers are gone): the next session journals afresh.
                    Volatile.Write(ref _reports, 0);
                    Volatile.Write(ref _nextFullReport, ReportStep);
                    Volatile.Write(ref _nextPageReport, ReportStep);
                }
            }

            private static void Report()
            {
                long full = Interlocked.Read(ref _fullBytes);
                long pages = Interlocked.Read(ref _pageBytes);

                if ((full < Volatile.Read(ref _nextFullReport) && pages < Volatile.Read(ref _nextPageReport)) ||
                    Volatile.Read(ref _reports) >= MaxReports)
                {
                    return;
                }

                while (full >= _nextFullReport)
                {
                    _nextFullReport += ReportStep;
                }

                while (pages >= _nextPageReport)
                {
                    _nextPageReport += ReportStep;
                }

                Interlocked.Increment(ref _reports);
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                    "bufferMirrors", "pendingPages", detail: $"{Volatile.Read(ref _buffers)} buffers with pending mirror data: full " +
                    $"copies would hold {full / (1024.0 * 1024.0):F1} MiB; pages hold {pages / (1024.0 * 1024.0):F1} MiB " +
                    "(adapt_mirror_pending_pages)");
            }
        }
    }
}
'''

PAIRS = ((FIELD_OLD, FIELD_NEW), (FILL_OLD, FILL_NEW), (UPLOAD_OLD, UPLOAD_NEW), (DIRECT_OLD, DIRECT_NEW),
         (WRITE_OLD, WRITE_NEW), (FALLTHROUGH_OLD, FALLTHROUGH_NEW), (DISPOSE_OLD, DISPOSE_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[HOLDER], old, new)
    return list(paths.values())
