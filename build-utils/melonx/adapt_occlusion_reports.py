"""Publish opt-in occlusion results on the FIFO owner before its syncpoint.

Applied after the historical adapters. Exact pre/post hashes make the whole
adapter idempotent and reject drift before modifying any file.
"""
import hashlib
from pathlib import Path


REPORT = '''using Ryujinx.Graphics.GAL;
using System;
using System.Threading;

namespace Ryujinx.Graphics.Gpu.Memory
{
    // Consumer callbacks only hand off scalar data. Guest writes belong to
    // the GPU/FIFO owner, never the Vulkan counter consumer or render thread.
    sealed class DeferredCounterReport : ICounterEvent
    {
        private ICounterEvent _counter;
        private Action<ulong> _publish;
        private Action _release;
        private ulong _value;
        private int _ready;
        private int _invalid;
        public bool Invalid
        {
            get => Volatile.Read(ref _invalid) != 0;
            set { if (value) { Volatile.Write(ref _invalid, 1); _publish = null; Release(); } }
        }

        public DeferredCounterReport(Action<ulong> publish, Action release) { _publish = publish; _release = release; }
        private void Release() => Interlocked.Exchange(ref _release, null)?.Invoke();
        public void Attach(ICounterEvent counter) { _counter = counter; }
        public void Complete(object sender, ulong value)
        {
            _value = value;
            Volatile.Write(ref _ready, 1);
        }
        public bool ReserveForHostAccess() => false;
        public void Dispose() { Invalid = true; } // backend still owns its query
        public void Flush()
        {
            if (Invalid || _publish == null) return;
            if (Volatile.Read(ref _ready) == 0) _counter.Flush();
            if (Invalid) return;
            if (Volatile.Read(ref _ready) == 0)
                throw new InvalidOperationException("Occlusion report was not completed; syncpoint withheld.");
            var publish = _publish;
            try { publish?.Invoke(_value); }
            finally { _publish = null; Release(); }
        }
    }
}
'''


def edits(source):
    result = {}

    def change(relative, old, new):
        path = source / relative
        text = result.get(path, path.read_text(encoding='utf-8-sig'))
        if text.count(old) != 1:
            raise RuntimeError('Occlusion adapter anchor drift: ' + relative + ' ' + old[:60])
        result[path] = text.replace(old, new)

    gpu = 'src/Ryujinx.Graphics.Gpu/'
    cache = gpu + 'Memory/CounterCache.cs'
    # Index zero is a valid entry. Upper-bound search previously selected the
    # next entry and could skip every counter in an unmapped half-open range.
    path = source / cache
    text = path.read_text(encoding='utf-8-sig')
    if text.count('if (index > 0)') != 2:
        raise RuntimeError('CounterCache lookup drift')
    result[path] = text.replace('if (index > 0)', 'if (index >= 0)')
    change(cache, '        private readonly List<CounterEntry> _items;', '''        private readonly List<CounterEntry> _items;
        private readonly object _gate = new();
        private readonly List<DeferredCounterReport> _pending = new();

        internal bool HasPendingReports { get { lock (_gate) return _pending.Count != 0; } }
        internal int PendingReportCount { get { lock (_gate) return _pending.Count; } }

        internal void FlushPendingReports()
        {
            DeferredCounterReport[] reports;
            lock (_gate) reports = _pending.ToArray();
            // No cache, page-table or queue lock may be held while waiting.
            foreach (var report in reports) report.Flush();
            lock (_gate) foreach (var report in reports) _pending.Remove(report);
        }

        internal void CancelPendingReports()
        {
            lock (_gate)
            {
                foreach (var report in _pending) report.Invalid = true;
                _pending.Clear();
            }
        }''')
    change(cache, '''            int index = BinarySearch(gpuVa);

            CounterEntry entry = new(gpuVa, evt);''', '''            lock (_gate)
            {
            int index = BinarySearch(gpuVa);

            if (evt is DeferredCounterReport pending) _pending.Add(pending);
            CounterEntry entry = new(gpuVa, evt);''')
    change(cache, '''                _items[index] = entry;
            }
        }''', '''                if (_items[index].Event is DeferredCounterReport old) old.Invalid = true;
                _items[index] = entry;
            }
            }
        }''')
    start = '        private void RemoveRange(ulong gpuVa, ulong size)'
    end = '        /// <summary>\n        /// Checks whenever'
    body = result[path]
    a, b = body.index(start), body.index(end)
    result[path] = body[:a] + '''        private void RemoveRange(ulong gpuVa, ulong size)
        {
            if (size == 0) return;
            lock (_gate)
            {
                int first = BinarySearch(gpuVa);
                if (first < 0) first = ~first;
                // A CounterData spans 16 bytes; include a report overlapping
                // the beginning of an unmapped page, not just its base address.
                while (first > 0 && gpuVa - _items[first - 1].Address < 16) first--;
                int last = first;
                while (last < _items.Count)
                {
                    ulong address = _items[last].Address;
                    if (address >= gpuVa && address - gpuVa >= size) break;
                    if (_items[last].Event != null) _items[last].Event.Invalid = true;
                    last++;
                }
                _items.RemoveRange(first, last - first);
            }
        }

''' + body[b:]
    change(cache, '            return BinarySearch(gpuVa) >= 0;', '            lock (_gate) return BinarySearch(gpuVa) >= 0;')
    # Snapshot event under the cache lock, then wait outside it.
    a = result[path].index('            int index = BinarySearch(gpuVa);', result[path].index('public bool FindAndFlush'))
    b = result[path].index('\n        /// <summary>', a)
    result[path] = result[path][:a] + '''            ICounterEvent evt;
            lock (_gate)
            {
                int index = BinarySearch(gpuVa);
                if (index < 0) return false;
                evt = _items[index].Event;
            }
            evt?.Flush();
            return true;
        }
''' + result[path][b:]
    change(cache, '''            int index = BinarySearch(gpuVa);
            if (index >= 0)
            {
                return _items[index].Event;
            }
            else
            {
                return null;
            }''', '''            lock (_gate)
            {
                int index = BinarySearch(gpuVa);
                return index >= 0 ? _items[index].Event : null;
            }''')
    change(gpu + 'Memory/MemoryManager.cs', '        public void Write<T>(ulong va, T value) where T : unmanaged', '''        internal DeferredCounterReport BeginCounterReport(ulong va, System.Action<ulong> publish)
        {
            lock (_pageTable)
            {
                Physical.IncrementReferenceCount();
                var report = new DeferredCounterReport(publish, Physical.DecrementReferenceCount);
                if (!IsMapped(va) || !IsMapped(va + 15) || !IsMappedOnPhysical(va) || !IsMappedOnPhysical(va + 15))
                    report.Invalid = true;
                CounterCache.AddOrUpdate(va, report);
                return report;
            }
        }

        internal void WriteCounterReport<T>(DeferredCounterReport report, ulong va, T value) where T : unmanaged
        {
            lock (_pageTable)
            {
                if (report.Invalid || !IsMapped(va) || !IsMapped(va + 15) ||
                    !IsMappedOnPhysical(va) || !IsMappedOnPhysical(va + 15)) return;
                // Unmap/remap handlers invalidate the report under this same
                // page-table lock before changing any PTE.
                Write(va, value);
            }
        }

        public void Write<T>(ulong va, T value) where T : unmanaged''')
    change(gpu + 'GpuContext.cs', '        private bool _pendingSync;', '''        private bool _pendingSync;
        public bool SynchronizeOcclusionReports { get; set; }
        private readonly HashSet<CounterCache> _counterReportCaches = new();

        internal void TrackCounterReports(CounterCache cache) => _counterReportCaches.Add(cache);

        internal bool FlushCounterReports()
        {
            bool pending = false;
            foreach (var cache in _counterReportCaches) pending |= cache.HasPendingReports;
            if (!pending) return false;
            // Submit before waiting, including in the threaded GAL. The empty
            // synchronous action establishes completion of the CreateSync command.
            CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force);
            Renderer.BackgroundContextAction(static () => { });
            foreach (var cache in _counterReportCaches) cache.FlushPendingReports();
            _counterReportCaches.Clear();
            return true;
        }''')
    change(gpu + 'GpuContext.cs', '            GPFifo.Dispose();', '''            foreach (var cache in _counterReportCaches) cache.CancelPendingReports();
            _counterReportCaches.Clear();
            GPFifo.Dispose();''')
    change(gpu + 'Engine/GPFifo/GPFifoClass.cs', '''                _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
                _context.Synchronization.IncrementSyncpoint(syncpointId);''', '''                if (!_context.SynchronizeOcclusionReports || !_context.FlushCounterReports())
                    _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
                _context.Synchronization.IncrementSyncpoint(syncpointId);''')
    change(gpu + 'Engine/Threed/SemaphoreUpdater.cs', '            ICounterEvent counter = null;', '''            if (_context.SynchronizeOcclusionReports && type == ReportCounterType.SamplesPassed)
            {
                var memory = _channel.MemoryManager;
                var cache = memory.CounterCache;
                if (cache.PendingReportCount >= 1024) _context.FlushCounterReports();
                Ryujinx.Graphics.Gpu.Memory.DeferredCounterReport report = null;
                report = memory.BeginCounterReport(gpuVa, result => memory.WriteCounterReport(report, gpuVa,
                    new CounterData { Counter = result, Timestamp = ticks }));
                _context.TrackCounterReports(cache);
                float scale = _channel.TextureManager.RenderTargetScale;
                try { report.Attach(_context.Renderer.ReportCounter(CounterType.SamplesPassed, report.Complete, scale * scale, false)); }
                catch { report.Invalid = true; throw; }
                return;
            }

            ICounterEvent counter = null;''')
    # Only consume fully available results, including on the no-wait path.
    buffered = 'src/Ryujinx.Graphics.Vulkan/Queries/BufferedQuery.cs'
    change(buffered, '            return result != _defaultValue;', '            return !WaitingForValue(result);')
    event = 'src/Ryujinx.Graphics.Vulkan/Queries/CounterQueueEvent.cs'
    change(event, '                    queryResult = _counter.AwaitResult(wakeSignal);', '''                    queryResult = _counter.AwaitResult(wakeSignal);
                    if (!_counter.TryGetResult(out queryResult))
                    {
                        Invalid = true;
                        Dispose();
                        return true;
                    }''')
    # Volatile publication covers FlushTo's completion flag after OnResult.
    change(event, '        public bool Disposed { get; private set; }', '''        private volatile bool _disposed;
        public bool Disposed => _disposed;''')
    change(event, '            Disposed = true;', '            _disposed = true;')
    # One consumer owns aggregation; blocking flush must never consume under
    # the queue lock while the real consumer holds an event's lock.
    queue = 'src/Ryujinx.Graphics.Vulkan/Queries/CounterQueue.cs'
    change(queue, '        private CounterQueueEvent _current;', '''        private CounterQueueEvent _current;
        private CounterQueueEvent _lastQueued;''')
    change(queue, '        public bool Disposed { get; private set; }', '''        private volatile bool _disposed;
        public bool Disposed => _disposed;''')
    change(queue, '                _events.Enqueue(_current);', '                _events.Enqueue(_current);\n                _lastQueued = _current;')
    path = source / queue
    body = result[path]
    a = body.index('            lock (_lock)', body.index('        public void Flush(bool blocking)'))
    b = body.index('        public void FlushTo(', a)
    result[path] = body[:a] + '''            CounterQueueEvent last;
            lock (_lock) last = _lastQueued;
            if (last != null) FlushTo(last);
        }

''' + body[b:]
    change(queue, '''            // Flush the counter queue on the main thread.
            Interlocked.Increment(ref _waiterCount);''', '''            if (Thread.CurrentThread == _consumerThread)
                throw new InvalidOperationException("Counter consumer cannot wait on itself.");
            // Wait outside the queue lock; only the consumer updates the sum.
            Interlocked.Increment(ref _waiterCount);''')
    change(queue, '            while (!evt.Disposed)', '            while (!evt.Disposed && !Disposed)')
    change(queue, '                Disposed = true;', '                _disposed = true;')
    # Declarative integration points; settings are assigned before threads run.
    library = 'src/Ryujinx.Library/Library.cs'
    change(library, '            renderer = renderer.TryMakeThreaded(options.BackendThreading);', '''            bool querySync = EmbeddedGraphics.OcclusionQuerySync && EmbeddedIsHogwarts(options.InputPath);
            if (renderer is VulkanRenderer vulkan) vulkan.RelaxQueryFlushing = querySync && EmbeddedGraphics.RelaxQueryFlushing;
            renderer = renderer.TryMakeThreaded(options.BackendThreading);''')
    change(library, '            return new Switch(configuration);', '''            var context = new Switch(configuration);
            context.Gpu.SynchronizeOcclusionReports = querySync;
            return context;''')
    result[source / (gpu + 'Memory/DeferredCounterReport.cs')] = REPORT
    return result


def apply(source):
    # The manifest is written only after every anchor is validated. An exact
    # postimage pass is a no-op; any mixed/unknown state fails closed.
    import json
    manifest = Path(__file__).with_name('occlusion-adapter-contract.json')
    expected = json.loads(manifest.read_text())
    def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    actual = {p: digest(source / p) for p in expected['before']}
    if actual == expected['after']:
        return [source / p for p in actual]
    if actual != expected['before']:
        raise RuntimeError('Occlusion adapter source drift: ' + str([p for p in actual if actual[p] != expected['before'][p]]))
    output = edits(source)
    if {str(p.relative_to(source)): hashlib.sha256(s.encode()).hexdigest() for p, s in output.items()} != expected['after']:
        raise RuntimeError('Occlusion postimage contract drift')
    for path, text in output.items(): path.write_text(text)
    return list(output)
