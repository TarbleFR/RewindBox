"""Hogwarts Legacy policy: syncpoint increments queued behind their occlusion reports (maintainer's go-ahead, 3 Nov 2026).

Design: docs/melonx-optimization-map-2026-11-03.md, "Design of #2". Build 629: at each increment with pending reports
the GPU thread submitted, drained the threaded renderer and waited for every report (11.8 s of 90 s). With
GpuContext.QueueSyncpointsBehindReports (assigned per session by the Library, Hogwarts only) and the occlusion report
synchronisation on, such an increment submits as before, takes the pending reports and joins a FIFO of the context
instead of waiting; every later increment queues behind it while the FIFO is not empty, so the guest sees the
increments in command order, each after its reports are published. The GPU thread publishes and increments from the
head of the FIFO once its reports are complete (GPFifoDevice.WaitForCommands, 1 ms waits while the FIFO is not
empty), drains it with the blocking flush before a GPU-side syncpoint wait or when its head is 50 ms old, and disposal
increments what is left without publishing. Off, the delivered path runs unchanged. Counted and logged every 4096
queued increments and at disposal. Applied after adapt_hogwarts_dma_copies (its Library line is the anchor).

After the compiled fixture (test/melonx_queued_syncpoints_fixture_test.py, 3 Nov 2026), as the blocking path does:
- a drain that waits for a report first lets the renderer run the submissions queued so far (one
  Renderer.BackgroundContextAction per drain), so the backend's bounded wait never starts before its query is
  submitted (threaded renderer: the report could time out and its syncpoint be withheld);
- an increment leaves the FIFO once published, so a report that cannot complete keeps it at the head (withheld, the
  error raised as by the blocking path) and disposal still releases it;
- the 3D engine's increment (ThreedClass.IncrementSyncpoint, made blocking by adapt_occlusion_completion) drains the
  FIFO first, so it never becomes visible before the increments queued ahead of it (counted apart).
"""
from pathlib import Path

from adapt_hogwarts_dma_copies import LIBRARY

GPU_CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
GPFIFO_CLASS = 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs'
GPFIFO_DEVICE = 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs'
THREED_CLASS = 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs'
COUNTER_CACHE = 'src/Ryujinx.Graphics.Gpu/Memory/CounterCache.cs'
DEFERRED_REPORT = 'src/Ryujinx.Graphics.Gpu/Memory/DeferredCounterReport.cs'

QUEUE_MEMBERS = '''
        // RewindBox (Hogwarts policy): syncpoint increments queued behind their occlusion reports, in command order,
        // on the GPU thread only (docs/melonx-optimization-map-2026-11-03.md, design of #2). Off: the path above.
        public static bool QueueSyncpointsBehindReports { get; set; }
        private const double QueuedSyncpointMaxAgeMs = 50;
        private readonly Queue<(uint Syncpoint, DeferredCounterReport[] Reports, long Timestamp)> _queuedSyncpoints = new();
        private long _syncpointsQueued, _syncpointsReady, _syncpointsByWait, _syncpointsByIncrement, _syncpointsByAge, _deepestSyncpointQueue;
        private double _oldestQueuedSyncpointMs;

        internal bool HasQueuedSyncpoints => _queuedSyncpoints.Count != 0;

        internal bool QueueSyncpointBehindReports(uint syncpoint)
        {
            if (!QueueSyncpointsBehindReports || !SynchronizeOcclusionReports) return false;
            bool pending = false;
            foreach (var cache in _counterReportCaches) pending |= cache.HasPendingReports;
            if (!pending && _queuedSyncpoints.Count == 0) return false;
            // Submitted as the blocking path submits, without waiting for the renderer or the reports.
            CreateHostSyncIfNeeded(pending ? HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force : HostSyncFlags.StrictSyncpoint);
            List<DeferredCounterReport> reports = new();
            foreach (var cache in _counterReportCaches) reports.AddRange(cache.TakePendingReports());
            _counterReportCaches.Clear();
            _queuedSyncpoints.Enqueue((syncpoint, reports.ToArray(), System.Diagnostics.Stopwatch.GetTimestamp()));
            _syncpointsQueued++;
            _deepestSyncpointQueue = Math.Max(_deepestSyncpointQueue, _queuedSyncpoints.Count);
            if ((_syncpointsQueued & 4095) == 0) LogQueuedSyncpoints();
            return true;
        }

        internal void ProcessQueuedSyncpoints()
        {
            bool submitted = false;
            while (_queuedSyncpoints.Count != 0)
            {
                var head = _queuedSyncpoints.Peek();
                double age = System.Diagnostics.Stopwatch.GetElapsedTime(head.Timestamp).TotalMilliseconds;
                bool ready = Array.TrueForAll(head.Reports, static report => report.IsReady);
                if (!ready && age < QueuedSyncpointMaxAgeMs) return;
                if (!ready) AwaitQueuedSubmissions(ref submitted);
                PublishAndIncrement(head, age);
                _queuedSyncpoints.Dequeue();
                if (ready) _syncpointsReady++; else _syncpointsByAge++;
            }
        }

        // Before a GPU-side syncpoint wait (GPFifoClass) or a 3D engine increment (ThreedClass, byIncrement).
        internal void DrainQueuedSyncpoints(bool byIncrement = false)
        {
            bool submitted = false;
            while (_queuedSyncpoints.Count != 0)
            {
                var head = _queuedSyncpoints.Peek();
                if (!Array.TrueForAll(head.Reports, static report => report.IsReady)) AwaitQueuedSubmissions(ref submitted);
                PublishAndIncrement(head, System.Diagnostics.Stopwatch.GetElapsedTime(head.Timestamp).TotalMilliseconds);
                _queuedSyncpoints.Dequeue();
                if (byIncrement) _syncpointsByIncrement++; else _syncpointsByWait++;
            }
        }

        // As the blocking path, before a report is waited for: the renderer has run every submission queued so far (the
        // empty synchronous action establishes completion of their CreateSync commands). Once per drain.
        private void AwaitQueuedSubmissions(ref bool submitted)
        {
            if (submitted) return;
            Renderer.BackgroundContextAction(static () => { });
            submitted = true;
        }

        // Leaves the entry at the head: a report that cannot complete throws, as the blocking path, before the increment.
        private void PublishAndIncrement((uint Syncpoint, DeferredCounterReport[] Reports, long Timestamp) entry, double age)
        {
            _oldestQueuedSyncpointMs = Math.Max(_oldestQueuedSyncpointMs, age);
            // The blocking flush of each report, immediate once it is complete.
            foreach (var report in entry.Reports) report.Flush();
            Synchronization.IncrementSyncpoint(entry.Syncpoint);
        }

        private void ReleaseQueuedSyncpoints()
        {
            if (_syncpointsQueued != 0) LogQueuedSyncpoints();
            while (_queuedSyncpoints.Count != 0)
            {
                var entry = _queuedSyncpoints.Dequeue();
                foreach (var report in entry.Reports) report.Invalid = true;
                Synchronization.IncrementSyncpoint(entry.Syncpoint);
            }
        }

        private void LogQueuedSyncpoints() => Ryujinx.Common.Logging.Logger.Info?.PrintMsg(Ryujinx.Common.Logging.LogClass.Gpu,
            $"Queued syncpoints (Hogwarts policy): {_syncpointsQueued} queued, {_syncpointsReady} ready, " +
            $"{_syncpointsByWait} drained by a wait, {_syncpointsByIncrement} by a 3D increment, {_syncpointsByAge} by age; " +
            $"deepest {_deepestSyncpointQueue}, " +
            $"oldest {_oldestQueuedSyncpointMs:F1} ms");
'''

FLUSH_END = '''            foreach (var cache in _counterReportCaches) cache.FlushPendingReports();
            _counterReportCaches.Clear();
            return true;
        }
'''
DISPOSE_OLD = '''            foreach (var cache in _counterReportCaches) cache.CancelPendingReports();
            _counterReportCaches.Clear();
            GPFifo.Dispose();'''
WAIT_OLD = '''                _context.Synchronization.WaitOnSyncpoint(syncpointId, threshold, Timeout.InfiniteTimeSpan);
            }
            else if (operation == SyncpointbOperation.Incr)'''
INCREMENT_OLD = '''                if (!_context.SynchronizeOcclusionReports || !_context.FlushCounterReports())
                    _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
                _context.Synchronization.IncrementSyncpoint(syncpointId);'''
FIFO_OLD = '''            if (!_commandBufferQueue.IsEmpty) return true;
            using var waitMeasurement = PD.Measure(PD.Phase.GpuFifoWait);
            return _event.WaitOne(8) && !_commandBufferQueue.IsEmpty;'''
# The 3D engine's syncpoint increment as adapt_occlusion_completion writes it (its first two lines).
THREED_OLD = '''            _context.AdvanceSequence();
            if (!_context.SynchronizeOcclusionReports || !_context.FlushCounterReports())'''
PENDING_OLD = '        internal int PendingReportCount { get { lock (_gate) return _pending.Count; } }\n'
REPORT_OLD = '        public DeferredCounterReport(Action<ulong> publish, Action release) { _publish = publish; _release = release; }\n'
LIBRARY_ANCHOR = '            Ryujinx.Graphics.Vulkan.EncodingPolicy.IncrementalArrayDescriptors = hogwarts;'

HUNKS = {
    GPU_CONTEXT: [(FLUSH_END, FLUSH_END + QUEUE_MEMBERS),
                  (DISPOSE_OLD, DISPOSE_OLD.replace('            GPFifo.Dispose();',
                                                    '            ReleaseQueuedSyncpoints();\n            GPFifo.Dispose();'))],
    GPFIFO_CLASS: [(WAIT_OLD, '                // RewindBox (Hogwarts policy): the increments queued behind reports come first.\n'
                              '                _context.DrainQueuedSyncpoints();\n' + WAIT_OLD),
                   (INCREMENT_OLD, '                // RewindBox (Hogwarts policy): queued behind its reports instead of waiting for them.\n'
                                   '                if (!_context.QueueSyncpointBehindReports(syncpointId))\n'
                                   '                {\n' +
                                   ''.join('    ' + line + '\n' for line in INCREMENT_OLD.split('\n')) +
                                   '                }')],
    GPFIFO_DEVICE: [(FIFO_OLD, '            // RewindBox (Hogwarts policy): increments whose reports are complete, or waited too long.\n'
                               '            _context.ProcessQueuedSyncpoints();\n' +
                               FIFO_OLD.replace('_event.WaitOne(8)', '_event.WaitOne(_context.HasQueuedSyncpoints ? 1 : 8)'))],
    THREED_CLASS: [(THREED_OLD, THREED_OLD.replace('            if (', '            // RewindBox (Hogwarts policy): the increments queued behind reports come first, in command order.\n'
                                                               '            _context.DrainQueuedSyncpoints(byIncrement: true);\n'
                                                               '            if (', 1))],
    COUNTER_CACHE: [(PENDING_OLD, PENDING_OLD + '''
        // RewindBox (Hogwarts policy): the pending reports, handed over to a queued syncpoint increment.
        internal DeferredCounterReport[] TakePendingReports()
        {
            lock (_gate)
            {
                DeferredCounterReport[] reports = _pending.ToArray();
                _pending.Clear();
                return reports;
            }
        }
''')],
    DEFERRED_REPORT: [(REPORT_OLD, REPORT_OLD + '        // RewindBox (Hogwarts policy): complete, cancelled or published: Flush() does not wait.\n'
                                                '        internal bool IsReady => Invalid || _publish == null || Volatile.Read(ref _ready) != 0;\n')],
    LIBRARY: [(LIBRARY_ANCHOR, LIBRARY_ANCHOR + '\n            // Occlusion reports: syncpoint increments queued behind them instead of waited for.\n'
                                                '            Ryujinx.Graphics.Gpu.GpuContext.QueueSyncpointsBehindReports = hogwarts;')],
}

NAMES = list(HUNKS)


def apply(source, names=None):
    """Applies every hunk exactly once (an anchor that drifted fails); returns the changed files.

    names limits it to some of the files, for a fixture that holds only those; prepare_embedded applies them all."""
    source = Path(source)
    chosen = [relative for relative in HUNKS if names is None or relative in names]
    if names is not None and set(names) - set(chosen):
        raise SystemExit('adapt_queued_syncpoints: unknown file ' + ', '.join(sorted(set(names) - set(chosen))))
    for relative in chosen:
        hunks = HUNKS[relative]
        path = source / relative
        raw = path.read_bytes()
        bom = raw.startswith(b'\xef\xbb\xbf')
        text = raw.decode('utf-8-sig')
        for old, new in hunks:
            if text.count(old) != 1 or new in text:
                raise SystemExit(f'adapt_queued_syncpoints: anchor not found exactly once in {relative}: {old[:70]!r}')
            text = text.replace(old, new)
        path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8'))
    return chosen
