"""Journal only: how many bytes the managed whole-buffer copies of mirror data hold (every title).

IPA 759 / Core 127b72b9, Hogwarts Legacy outdoors (private journals, pid 23031; docs/melonx-hogwarts-outdoor-2026-11-16.md):
the large object heap holds 275 to 277 MiB of live data after a collection (gcEvent, memoryInventory) while the mapped
Vulkan buffers are 246 MiB in 6 513 blocks (vulkanMemory); the heap has 145 to 156 MiB of holes in play, a compaction
gives 237 to 274 MiB of footprint back and the holes are there again 30 s later.

Read in the source (BufferHolder.SetData): on a tile-based GPU every host-mapped buffer uses mirrors; the first update of
a range the GPU may still read allocates `_pendingData = new byte[Size]`, a managed copy of the WHOLE buffer, kept until
the buffer is disposed. A copy of 85 000 bytes or more is a large-object-heap array, and every buffer the cache
recreates allocates a new one. adapt_mirror_pending_pages (10 November, not wired) replaced that copy by pages and was
parked on one missing figure: what share of the heap these copies are on the device. This adapter gives that figure and
changes nothing else.

Change (BufferHolder.cs only): the allocation of the copy and the disposal of a buffer that holds one are counted
(MirrorCopyJournal, interlocked counters); a journal record (stage bufferMirrors, at most 32 per process) is written
each time the bytes held reach a new 16 MiB step: the buffers holding a copy, the bytes, and the part in copies of
85 000 bytes or more. The step starts again when no buffer holds a copy (the next session).
Not changed: when a copy is allocated, its size, its life, mirrors, uploads, rebinds.

Expected on the device: the bufferMirrors lines of a Hogwarts Legacy session outdoors, read with lohOccupiedAfterBytes
of the gcEvent lines. If the copies are a large part of the live large object heap, adapt_mirror_pending_pages with its
settle step is worth finishing; if not, that lead is closed. Rollback: drop this adapter from prepare_embedded.py and
ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

HOLDER = 'src/Ryujinx.Graphics.Vulkan/BufferHolder.cs'
# The preparation of Core 9943a5ca (IPA 761).
BASELINE = {HOLDER: '9b5e77bef55cb51b9942b4d24a5f3d544512036dd7384c71b8d98e821c0402e1'}

ALLOCATE_OLD = '''                if (_pendingData == null)
                {
                    _pendingData = new byte[Size];
                    _mirrors = new Dictionary<ulong, StagingBufferReserved>();
                }
'''
ALLOCATE_NEW = '''                if (_pendingData == null)
                {
                    _pendingData = new byte[Size];
                    _mirrors = new Dictionary<ulong, StagingBufferReserved>();
                    MirrorCopyJournal.Added(Size); // RewindBox (adapt_mirror_copy_journal)
                }
'''

DISPOSE_OLD = '''        public void Dispose()
        {
            _gd.PipelineInternal?.FlushCommandsIfWeightExceeding(_buffer, (ulong)Size);
'''
DISPOSE_NEW = '''        public void Dispose()
        {
            // RewindBox (adapt_mirror_copy_journal): this buffer's managed copy, if it has one, is counted out once.
            if (_pendingData != null && !_mirrorCopyCountedOut)
            {
                _mirrorCopyCountedOut = true;
                MirrorCopyJournal.Removed(Size);
            }

            _gd.PipelineInternal?.FlushCommandsIfWeightExceeding(_buffer, (ulong)Size);
'''

FIELD_OLD = '''        private byte[] _pendingData;
'''
FIELD_NEW = '''        private byte[] _pendingData;
        private bool _mirrorCopyCountedOut; // RewindBox (adapt_mirror_copy_journal)
'''

CLASS_OLD = '''            _flushLock.ExitWriteLock();
        }
    }
}
'''
CLASS_NEW = '''            _flushLock.ExitWriteLock();
        }
    }

    /// <summary>
    /// RewindBox (adapt_mirror_copy_journal): the managed copies of whole buffers that hold mirror data (BufferHolder's
    /// _pendingData), counted for the journal only. IPA 759, Hogwarts Legacy: 275 to 277 MiB of live large object heap
    /// beside 246 MiB of mapped Vulkan buffers; what part of it these copies are was not known. A record each time the
    /// bytes held reach a new 16 MiB step, at most 32 per process.
    /// </summary>
    static class MirrorCopyJournal
    {
        private const long ReportStep = 16L * 1024 * 1024;
        private const int MaxReports = 32;
        private const int LargeObjectBytes = 85000;

        private static readonly object _lock = new();
        private static long _buffers, _bytes, _largeBuffers, _largeBytes;
        private static long _nextReport = ReportStep;
        private static int _reports;

        public static void Added(int size)
        {
            Interlocked.Increment(ref _buffers);

            if (size >= LargeObjectBytes)
            {
                Interlocked.Increment(ref _largeBuffers);
                Interlocked.Add(ref _largeBytes, size);
            }

            long bytes = Interlocked.Add(ref _bytes, size);

            if (bytes < Volatile.Read(ref _nextReport))
            {
                return;
            }

            lock (_lock)
            {
                if (bytes < _nextReport || _reports >= MaxReports)
                {
                    return;
                }

                while (bytes >= _nextReport)
                {
                    _nextReport += ReportStep;
                }

                _reports++;
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("bufferMirrors", "wholeCopies", detail: Text(bytes));
            }
        }

        public static void Removed(int size)
        {
            if (size >= LargeObjectBytes)
            {
                Interlocked.Decrement(ref _largeBuffers);
                Interlocked.Add(ref _largeBytes, -size);
            }

            Interlocked.Add(ref _bytes, -size);

            if (Interlocked.Decrement(ref _buffers) == 0)
            {
                // No buffer holds a copy any more (the session's renderer is gone): the next one starts at the first step.
                lock (_lock)
                {
                    _nextReport = ReportStep;
                }
            }
        }

        private static string Text(long bytes)
        {
            System.Globalization.CultureInfo invariant = System.Globalization.CultureInfo.InvariantCulture;

            return Volatile.Read(ref _buffers).ToString(invariant) + " buffers hold a managed copy of their whole size for mirror data: " +
                (bytes / (1024.0 * 1024.0)).ToString("F1", invariant) + " MiB, of which " +
                (Volatile.Read(ref _largeBytes) / (1024.0 * 1024.0)).ToString("F1", invariant) + " MiB in " +
                Volatile.Read(ref _largeBuffers).ToString(invariant) +
                " copies of 85 000 bytes or more (large object heap) (adapt_mirror_copy_journal)";
        }
    }
}
'''

PAIRS = ((HOLDER, FIELD_OLD, FIELD_NEW), (HOLDER, ALLOCATE_OLD, ALLOCATE_NEW), (HOLDER, DISPOSE_OLD, DISPOSE_NEW),
         (HOLDER, CLASS_OLD, CLASS_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
