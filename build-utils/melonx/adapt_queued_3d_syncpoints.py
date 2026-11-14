"""The 3D engine's syncpoint increment is queued behind its occlusion reports instead of waiting for them (Hogwarts Legacy).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journal, pid 5954, 21 gameplay windows of core-performance, 127.2 s):
gpuDispatch 85.0 s, of which counterReports (CounterCache.FlushPendingReports) 15.65 s over 2 115 calls (18.4 % of
gpuDispatch) and syncInvoke (ThreadedRenderer.InvokeCommand, the renderer barrier of GpuContext.FlushCounterReports)
11.36 s over 2 167 calls; together 27.0 s, 31.8 % of gpuDispatch. In the 20 render-thread windows of 5 s in gameplay,
the GPU thread's synchronous render-thread commands (about one per strict "counter reports" sync) are 1 912 waits,
9.40 s, of which 0.33 s in the commands themselves (the rest is render-thread work queued ahead of them), 2.2 to
10.8 ms per wait depending on the window. "Host syncs created" (pid 5954, 36 windows of 5 s in the core journal): "counter reports"
strict 40-136 in 29 windows (0-7 in the 7 others), "queued syncpoints" and "GPFifo syncpoint" 0 in all. So the queue of
adapt_queued_syncpoints never served this title: its increments with pending reports are the 3D engine's
(ThreedClass.IncrementSyncpoint, the SyncpointAction method), which drained that queue and then blocked in
FlushCounterReports (forced sync, renderer barrier, wait for every report) since adapt_occlusion_completion.
Upper bound of the gain: those 27.0 s of GPU-thread blocking over 127.2 s. Over the 19 windows that have frame lines in
the per-window frame report (22.3 s of the 27.0 s; the 2 others hold 4.7 s), about 9.8 ms per presented frame (2 269
frames) and 14.9 ms per game frame (1 500). The GPU thread already waited for guest commands 33.4 s of the 127.2 s
(gpuFifoWait, 26 %), so the frame-rate gain is unknown: about nil if the guest waits for this syncpoint as soon as it is
sent. Bounds, not measurements.

Change (Hogwarts policy only: GpuContext.QueueSyncpointsBehindReports && SynchronizeOcclusionReports, both assigned per
session by the Library before the first command; off, every path below is the delivered one):
(a) ThreedClass.IncrementSyncpoint asks QueueSyncpointBehindReports first, as GPFifoClass.Syncpointb does: with reports
    pending, or increments already queued, the increment is submitted (forced host sync when reports are pending), takes
    the pending reports and joins the FIFO; the counters are polled and the method returns. Otherwise the delivered path
    runs: its DrainQueuedSyncpoints(byIncrement: true) is kept as a guard but finds the FIFO empty (the queue declines
    only when nothing is pending and the FIFO is empty), so "by a 3D increment" stays 0 in the queue's log line.
(b) GpuContext.QueueSyncpointBehindReports takes its call site ([CallerMemberName]). With pending reports the sync stays
    forced (never paced, counted as "queued syncpoints"); without, it is the site's own strict sync, so StrictSyncPacer
    (adapt_paced_strict_syncs) paces a queued 3D increment exactly as an unqueued one, and the sync is counted under its
    site ("3D syncpoint", or "GPFifo syncpoint" for Syncpointb, which the pacer never paces). This widens the scope that
    adapt_paced_strict_syncs states ("syncpoints queued behind reports ... untouched"); a strict sync is a latency
    choice, not a correctness one (its docstring).
(c) GPFifoDevice.DispatchCallsCore processes the FIFO (ProcessQueuedSyncpoints: increments whose reports completed, or
    that waited QueuedSyncpointMaxAgeMs) after each GPFIFO entry while it is not empty. Before, only WaitForCommands did,
    once the GPFIFO ran empty: an increment would have waited for the whole burst of entries behind it.
(e) Address rewrite. A report handed to a queued increment stays in CounterCache._items (it leaves only _pending). A
    later report to the same GPU address would make AddOrUpdate invalidate it (Invalid, _publish = null): IsReady, no
    publication, and the increment visible with the address holding neither value. DeferredCounterReport.AwaitsPublication
    and CounterCache.HasQueuedReportAt (under the cache's lock: the entry at that address is a deferred report awaiting
    publication that is not pending, so it belongs to a queued increment) let SemaphoreUpdater.ReportCounter publish the
    FIFO first (DrainQueuedSyncpoints, blocking, no lock held, counted as "drained by a wait"), for every report type,
    before the new report is created or a Payload report writes its value.

Guest-visible order kept, as on the blocking path:
- Increments of the GPU command stream become visible in command order. Syncpointb (Incr) and the 3D engine's method
  are its only increment sites (checked below; NvHostSyncPt and NvFence increment from the CPU side, Host1x is another
  engine) and both queue now. An increment that is not queued finds the FIFO empty, so none overtakes a queued one;
  the FIFO is published from its head only.
- Every report written before an increment is published before that increment is visible: the reports pending at the
  increment are taken by its entry and PublishAndIncrement flushes each (blocking if it must) before incrementing;
  earlier reports belong to earlier entries. With (e), a later report to the same address cannot remove that value.
- A GPU-side syncpoint wait (Syncpointb Wait) drains the FIFO first; a CPU-side wait (NvHostEvent) does not give up
  while it is not empty (GpuContext.ForcedWaitGpuIdle); disposal increments what is left without publishing.
- Conditional rendering that reads a queued report's address flushes that report (FindEvent, then Flush): its value
  is written before its increment, as allowed.
Relaxed, as for the GPFIFO increments queued since 3 Nov 2026 (and, between a report and its increment, already for
every deferred report): guest writes of commands after a queued increment (semaphore release, I2M, DMA, reports to other
addresses) can become visible before it; a later command reading a queued report's address on the GPU side (DMA copy)
reads the earlier memory; a later non-report write to that address (semaphore release, I2M, DMA) is overwritten when
the report is published. Latency: an increment becomes visible at the first FIFO pass after its reports complete (one
GPFIFO entry with (c), 1 ms when the GPU thread is idle); WaitForCommands wakes every 1 ms more often (the FIFO is
non-empty for part of each frame); the drain by age (50 ms) stays blocking.

Expected on the device (same save and route): "Host syncs created": "queued syncpoints" strict about the former
"counter reports" count (40-136 per 5 s window in gameplay), "counter reports" near 0; "Queued syncpoints (Hogwarts
policy)": "by a 3D increment" 0, "by age" rare; core-performance: counterReports and syncInvoke near 0 ms. Judged by
gpuFifoWait and game frames per window: refuted, and the adapter removed, if gpuFifoWait grows by as much with no more
game frames, or if "by age" drains become frequent. Not measured on an iPhone. Applied at the end of ORDER, after
adapt_pool_slot_copy; GpuContext.cs after adapt_texture_play_clock (disjoint anchors: once that adapter is wired before
this one, the GpuContext.cs BASELINE entry is its post-image). Rollback: drop this adapter from prepare_embedded.py and
ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

THREED = 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs'
CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
DEVICE = 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs'
REPORT = 'src/Ryujinx.Graphics.Gpu/Memory/DeferredCounterReport.cs'
CACHE = 'src/Ryujinx.Graphics.Gpu/Memory/CounterCache.cs'
SEMAPHORE = 'src/Ryujinx.Graphics.Gpu/Engine/Threed/SemaphoreUpdater.cs'
GPFIFO_CLASS = 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs'  # read only (the ordering check)
BASELINE = {
    THREED: '21d6288eea430e45b1fe6f4fef5440ffddd2105284d89e7870b958750946a499',
    # adapt_texture_play_clock's post-image (it is applied before this one on the Core bacdcacd preparation).
    CONTEXT: 'f86ea9357faa62ff4ef3e7e48c94bbc856798bbcf472d3c9f4cf8551f0107050',
    DEVICE: '0fe0e778ae3dc65802e4b845c56f705a2365a66603f5ccd509148421bc1432c8',
    REPORT: '8ff7b8fd73e9660e6e1f98acc69bc3db206e2fdbfda77d17504794abfa1cb2c3',
    CACHE: '15a8e0d8adec000b599310f9f44f5ba1efd30b7a216162a5f63e6e18d8380097',
    SEMAPHORE: '21203441c93f9c3155b3b75fcf022b916bcdc7bd03db15561cbf4a3b668f33d9',
}

# (a) The 3D engine's increment as adapt_occlusion_completion and adapt_queued_syncpoints wrote it.
INCREMENT_OLD = '''            uint syncpointId = (uint)argument & 0xFFFF;

            _context.AdvanceSequence();
            // RewindBox (Hogwarts policy): the increments queued behind reports come first, in command order.
            _context.DrainQueuedSyncpoints(byIncrement: true);
            if (!_context.SynchronizeOcclusionReports || !_context.FlushCounterReports())
'''
INCREMENT_NEW = '''            uint syncpointId = (uint)argument & 0xFFFF;

            _context.AdvanceSequence();
            // RewindBox (adapt_queued_3d_syncpoints): Hogwarts policy. Behind its pending reports, or behind the
            // increments already queued, the increment joins the FIFO (submitted, not waited for), as a GPFIFO one does.
            if (_context.QueueSyncpointBehindReports(syncpointId))
            {
                _context.Renderer.UpdateCounters(); // Poll the query counters, the game may want an updated result.
                return;
            }

            // RewindBox (Hogwarts policy): the increments queued behind reports come first, in command order.
            // (adapt_queued_3d_syncpoints: a guard; the FIFO is empty whenever the increment above was not queued.)
            _context.DrainQueuedSyncpoints(byIncrement: true);
            if (!_context.SynchronizeOcclusionReports || !_context.FlushCounterReports())
'''

# (b) The queue's host sync: the call site's own when no report is pending.
SIGNATURE_OLD = '''        internal bool QueueSyncpointBehindReports(uint syncpoint)
'''
SIGNATURE_NEW = '''        internal bool QueueSyncpointBehindReports(uint syncpoint, [System.Runtime.CompilerServices.CallerMemberName] string site = "")
'''

SYNC_OLD = '''            CreateHostSyncIfNeeded(pending ? HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force : HostSyncFlags.StrictSyncpoint);
'''
SYNC_NEW = '''            // RewindBox (adapt_queued_3d_syncpoints): with no report pending the sync is the call site's own, so the 3D
            // engine's increment ("IncrementSyncpoint") is paced by StrictSyncPacer as when it is not queued, and counted
            // under its site; the forced sync of pending reports is never paced ("queued syncpoints").
            if (pending)
            {
                CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force);
            }
            else
            {
                CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint, site);
            }
'''

# (c) The FIFO after each GPFIFO entry, not only once the GPFIFO ran empty.
ENTRY_OLD = '''                    entry.Processor.Process(entry.EntryAddress, words);
                }
                finally
'''
ENTRY_NEW = '''                    entry.Processor.Process(entry.EntryAddress, words);

                    // RewindBox (adapt_queued_3d_syncpoints): the queued increments whose reports completed meanwhile, or
                    // that waited too long, after each GPFIFO entry (WaitForCommands only runs once the GPFIFO is empty).
                    if (_context.HasQueuedSyncpoints)
                    {
                        _context.ProcessQueuedSyncpoints();
                    }
                }
                finally
'''

# (e) A later report to the address of a queued, unpublished one publishes the FIFO first.
READY_OLD = '''        internal bool IsReady => Invalid || _publish == null || Volatile.Read(ref _ready) != 0;
        private void Release()'''
READY_NEW = '''        internal bool IsReady => Invalid || _publish == null || Volatile.Read(ref _ready) != 0;
        // RewindBox (adapt_queued_3d_syncpoints): neither cancelled nor published yet.
        internal bool AwaitsPublication => !Invalid && _publish != null;
        private void Release()'''

FIND_OLD = '''                return index >= 0 ? _items[index].Event : null;
            }
        }

        /// <summary>
        /// Performs binary search'''
FIND_NEW = '''                return index >= 0 ? _items[index].Event : null;
            }
        }

        /// <summary>
        /// RewindBox (adapt_queued_3d_syncpoints): whether the report at this address was handed to a queued syncpoint
        /// increment (taken from the pending list) and is not published yet. AddOrUpdate at this address would invalidate
        /// it and the increment would become visible without its value: the caller publishes the queue first.
        /// </summary>
        internal bool HasQueuedReportAt(ulong gpuVa)
        {
            lock (_gate)
            {
                int index = BinarySearch(gpuVa);

                return index >= 0 && _items[index].Event is DeferredCounterReport report && report.AwaitsPublication &&
                       !_pending.Contains(report);
            }
        }

        /// <summary>
        /// Performs binary search'''

COUNTER_OLD = '''            ulong ticks = _context.GetTimestamp();

            if (_context.SynchronizeOcclusionReports && type == ReportCounterType.SamplesPassed)
'''
COUNTER_NEW = '''            ulong ticks = _context.GetTimestamp();

            // RewindBox (adapt_queued_3d_syncpoints): this report would replace one that a queued increment has not
            // published yet (CounterCache.AddOrUpdate invalidates it): the queue is published first, in command order
            // (blocking, no lock held), before any report type creates its counter or writes its value here.
            if (_context.HasQueuedSyncpoints && _channel.MemoryManager.CounterCache.HasQueuedReportAt(gpuVa))
            {
                _context.DrainQueuedSyncpoints();
            }

            if (_context.SynchronizeOcclusionReports && type == ReportCounterType.SamplesPassed)
'''

PAIRS = ((THREED, INCREMENT_OLD, INCREMENT_NEW), (CONTEXT, SIGNATURE_OLD, SIGNATURE_NEW), (CONTEXT, SYNC_OLD, SYNC_NEW),
         (DEVICE, ENTRY_OLD, ENTRY_NEW), (REPORT, READY_OLD, READY_NEW), (CACHE, FIND_OLD, FIND_NEW),
         (SEMAPHORE, COUNTER_OLD, COUNTER_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    # The ordering argument: in the GPU project, only Syncpointb and the 3D engine's method increment a syncpoint
    # (besides the queue's own publication in GpuContext), and they are QueueSyncpointBehindReports' only callers, so
    # its site is one of the two and every GPU-stream increment goes through the queue.
    gpu = source / 'src/Ryujinx.Graphics.Gpu' if digests else None
    for path in (gpu.rglob('*.cs') if gpu else ()):
        name = path.relative_to(source).as_posix()
        text = path.read_text(encoding='utf-8-sig')
        expected = {GPFIFO_CLASS: (1, 1), THREED: (1, 0)}.get(name, (0, 0))
        found = (text.count('Synchronization.IncrementSyncpoint('), text.count('QueueSyncpointBehindReports('))
        assert name == CONTEXT or found == expected, (name, found)
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
