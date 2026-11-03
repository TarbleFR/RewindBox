"""Source checks of adapt_queued_syncpoints (Hogwarts policy: syncpoint increments queued behind occlusion reports).

Run on a prepared tree (`--source`, prepared with or without this adapter): the seven files are taken before the adapter
(its hunks reversed when it already ran), the adapter is applied to copies, and the result is checked: every hunk once,
a second application and a drifted anchor refused, the delivered increment path kept whole inside the policy's
fallback, the queue drained before the GPU thread waits on a syncpoint, the 1 ms FIFO wait only while increments are
queued, the reports handed over under the cache's lock, readiness without waiting, the Library assigning the flag once
next to the encoding policy, disposal releasing the queue, the renderer barrier before a drain waits for a report, an
increment leaving the FIFO only once published, the 3D engine's increment draining the FIFO first. The FIFO's runtime
behaviour is the compiled fixture's: test/melonx_queued_syncpoints_fixture_test.py.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import adapt_queued_syncpoints as queued  # noqa: E402

CHECKS = 0


def check(condition, message):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise SystemExit('FAIL: ' + message)


def before_adapter(text, hunks):
    for old, new in reversed(hunks):
        if new in text:
            text = text.replace(new, old)
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True, help='prepared MeloNX tree (its src/ holds the engine)')
    source = parser.parse_args().source
    with tempfile.TemporaryDirectory(prefix='queued-syncpoints-') as temporary:
        work = Path(temporary)
        originals = {}
        for relative, hunks in queued.HUNKS.items():
            text = before_adapter((source / relative).read_text(encoding='utf-8-sig'), hunks)
            originals[relative] = text
            (work / relative).parent.mkdir(parents=True, exist_ok=True)
            (work / relative).write_text(text, encoding='utf-8')
            for old, new in hunks:
                check(text.count(old) == 1 and new not in text, f'{relative}: anchor before the adapter')
        check(queued.apply(work) == queued.NAMES, 'changed files')
        final = {relative: (work / relative).read_text(encoding='utf-8') for relative in queued.HUNKS}
        for relative, hunks in queued.HUNKS.items():
            check(before_adapter(final[relative], hunks) == originals[relative], f'{relative}: changed beyond its hunks')
        try:
            queued.apply(work)
            check(False, 'a second application was accepted')
        except SystemExit as error:
            check('anchor not found exactly once' in str(error), 'second application message')
        drifted = work / 'drifted'
        shutil.copytree(work / 'src', drifted / 'src')
        path = drifted / queued.GPFIFO_DEVICE
        path.write_text(originals[queued.GPFIFO_DEVICE].replace('_event.WaitOne(8)', '_event.WaitOne(16)'), encoding='utf-8')
        for relative in queued.HUNKS:
            if relative != queued.GPFIFO_DEVICE:
                (drifted / relative).write_text(originals[relative], encoding='utf-8')
        try:
            queued.apply(drifted)
            check(False, 'a drifted anchor was accepted')
        except SystemExit:
            check(True, 'drift refused')

    fifo_class, device = final[queued.GPFIFO_CLASS], final[queued.GPFIFO_DEVICE]
    context, cache = final[queued.GPU_CONTEXT], final[queued.COUNTER_CACHE]
    report, library = final[queued.DEFERRED_REPORT], final[queued.LIBRARY]
    threed = final[queued.THREED_CLASS]
    # The delivered increment path is whole, as the fallback of the policy.
    fallback = '''                if (!_context.QueueSyncpointBehindReports(syncpointId))
                {
                    if (!_context.SynchronizeOcclusionReports || !_context.FlushCounterReports())
                        _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
                    _context.Synchronization.IncrementSyncpoint(syncpointId);
                }'''
    check(fallback in fifo_class, 'delivered increment path not kept as the fallback')
    check(fifo_class.index('_context.DrainQueuedSyncpoints();') < fifo_class.index('_context.Synchronization.WaitOnSyncpoint('),
          'the queue is not drained before the GPU thread waits on a syncpoint')
    check(fifo_class.count('IncrementSyncpoint(') == 1, 'another increment in GPFifoClass')
    check('_context.ProcessQueuedSyncpoints();\n            if (!_commandBufferQueue.IsEmpty) return true;' in device and
          '_event.WaitOne(_context.HasQueuedSyncpoints ? 1 : 8)' in device, 'FIFO processing or its wait')
    check('if (!QueueSyncpointsBehindReports || !SynchronizeOcclusionReports) return false;' in context and
          'if (!pending && _queuedSyncpoints.Count == 0) return false;' in context, 'policy and empty-queue fallbacks')
    check(context.index('CreateHostSyncIfNeeded(pending ? HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force') <
          context.index('_queuedSyncpoints.Enqueue('), 'submitted before queued')
    check('BackgroundContextAction' not in context.split('internal bool QueueSyncpointBehindReports')[1].split('internal void ProcessQueuedSyncpoints')[0],
          'the queued path drains the threaded renderer')
    check('if (!ready && age < QueuedSyncpointMaxAgeMs) return;' in context and 'private const double QueuedSyncpointMaxAgeMs = 50;' in context,
          'age bound')
    check(context.index('foreach (var report in entry.Reports) report.Flush();') <
          context.index('Synchronization.IncrementSyncpoint(entry.Syncpoint);'), 'published before incremented')
    check('            ReleaseQueuedSyncpoints();\n            GPFifo.Dispose();' in context and
          'foreach (var report in entry.Reports) report.Invalid = true;' in context, 'disposal releases the queue')
    check('lock (_gate)\n            {\n                DeferredCounterReport[] reports = _pending.ToArray();\n                _pending.Clear();' in cache,
          'reports handed over outside the lock')
    check('internal bool IsReady => Invalid || _publish == null || Volatile.Read(ref _ready) != 0;' in report, 'readiness')
    check(library.count('Ryujinx.Graphics.Gpu.GpuContext.QueueSyncpointsBehindReports = hogwarts;') == 1 and
          library.index('EncodingPolicy.IncrementalArrayDescriptors = hogwarts;') <
          library.index('GpuContext.QueueSyncpointsBehindReports = hogwarts;'), 'Library assignment')
    check('QueueSyncpointsBehindReports = true' not in ''.join(final.values()), 'enabled outside the Library')
    # As the blocking path: the renderer runs the queued submissions before a drain waits for a report.
    process = context.split('internal void ProcessQueuedSyncpoints()')[1].split('internal void DrainQueuedSyncpoints(')[0]
    drain = context.split('internal void DrainQueuedSyncpoints(bool byIncrement = false)')[1].split('private void AwaitQueuedSubmissions(')[0]
    barrier = context.split('private void AwaitQueuedSubmissions(ref bool submitted)')[1].split('private void PublishAndIncrement(')[0]
    check('Renderer.BackgroundContextAction(static () => { });' in barrier and 'if (submitted) return;' in barrier,
          'one renderer barrier per drain')
    for name, body in (('age', process), ('drain', drain)):
        check(body.index('AwaitQueuedSubmissions(ref submitted)') < body.index('PublishAndIncrement(head') <
              body.index('_queuedSyncpoints.Dequeue();'), name + ': barrier, publication, then dequeued')
    check('if (!ready) AwaitQueuedSubmissions(ref submitted);' in process and
          'if (!Array.TrueForAll(head.Reports, static report => report.IsReady)) AwaitQueuedSubmissions(ref submitted);' in drain,
          'the barrier only for an incomplete head')
    check('_queuedSyncpoints.Dequeue()' not in context.split('private void PublishAndIncrement(')[1].split('private void ReleaseQueuedSyncpoints(')[0],
          'publication does not dequeue')
    # The 3D engine's increment: the FIFO first, then the delivered blocking path, whole.
    check(threed.count('_context.DrainQueuedSyncpoints(byIncrement: true);') == 1 and
          threed.index('_context.AdvanceSequence();') < threed.index('_context.DrainQueuedSyncpoints(byIncrement: true);') <
          threed.index('if (!_context.SynchronizeOcclusionReports || !_context.FlushCounterReports())'),
          '3D increment drains the FIFO before its own flush')
    check(before_adapter(threed, queued.HUNKS[queued.THREED_CLASS]) == originals[queued.THREED_CLASS], '3D path otherwise delivered')
    check('{_syncpointsByIncrement} by a 3D increment' in context, '3D drains counted apart')
    print(f'PASS {CHECKS} queued syncpoint checks (source; the FIFO behaviour: test/melonx_queued_syncpoints_fixture_test.py)')


if __name__ == '__main__':
    main()
