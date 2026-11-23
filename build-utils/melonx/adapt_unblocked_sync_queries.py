"""The GPU thread's sync query no longer waits behind a reader's GPU wait; host sync waits are journaled by waiter (every
title).

IPA 822, Hogwarts Legacy (private journals, counts and durations only), one 5.4 s window of 85 frames: the GPU is busy
19.2 ms per frame (30 %), the render thread 2 839 ms of 5 000, the GPU thread dispatches 2 578 ms and waits for guest
commands 2 728 ms of 5 523: the pipeline drains. Host syncs: 343 strict and 1 210 not strict per 5 s on the GPU thread;
the render thread runs CreateSync 1 939 times in 248.6 ms. Over the 16 windows of the session, CreateSync time is the
strict syncs' submissions (340 submits at 0.50 ms each, 170 ms, of which vkQueueSubmit, where MoltenVK encodes the
command buffer, is 349 of 362 ms of all submits); what is left over the other syncs is -51 to +155 ms per window, i.e.
noise around a few microseconds each. A sync that waits for the command buffer allocates no Vulkan object: it holds the
fence of the command buffer it waits for (one per submission, shared), in a managed holder of its own. "Sync waits"
(SyncManager.Wait, 1 087.2 ms per window, 9 to 15 ms per frame since IPA 733) are taken only through WaitSync: guest
threads flushing GPU-written buffers or textures for a CPU access (Buffer.ExternalFlush, TextureGroupHandle.Sync), not
NvHostEvent (syncpoints are incremented on the GPU thread). Those waits keep fast flush mode on in 85 of 85 frames
(entered above 1.5 ms of waits per frame on average over 20 frames, left below 0.1 ms): its trigger holds.

The serialization removed: SyncManager.Wait holds the handle's lock while the GPU completes the handle's command buffer
(up to 1 s). SyncManager.GetCurrent, which GpuContext.CreateHostSyncIfNeeded calls on the GPU thread whenever a buffer
migration is pending, takes the lock of every handle in turn while holding the lock of the handle queue. A query meeting
a waited handle therefore waited for that GPU work too, and meanwhile held every SyncManager.Create (render thread),
Cleanup (render thread, each frame) and Wait (other readers, even of a sync long signalled) behind it: the GPU thread and
the render thread stop feeding the GPU while one reader waits for it.

Change (every title; no submission, sync creation, fence or flush decision changes):
- SyncManager.GetCurrent takes each handle with Monitor.TryEnter. A handle a reader holds is not waited for: it counts as
  not signalled yet unless its state was already read signalled, exactly as a poll that comes too early, and the scan
  goes on (the scan, the polls and the result of a free handle are the delivered ones). The value can only be lower than
  the delivered query would have returned after its wait; it only decides when buffer migrations are released (later is
  conservative). No other lock is held across a GPU wait.
- Journal (diagnostics only): SyncManager.Cleanup logs every 5 s on the render thread "Vulkan host sync waits over N ms:
  W waits X ms (longest; GPU thread, render thread, other threads; submitted for the waiter); waits for the render thread
  to create the sync A ms (longest); sync queries Q ms (longest, fence holders polled, passed a sync being waited for P)".
  SyncMap.WaitSyncAvailability counts the waits for a sync the render thread had not created yet (render-thread lag).
Read on the next device session: P > 0 per window confirms the delivered query met readers; "sync queries" longest
well under 1 ms confirms the GPU thread no longer waits there; the waiter split says who waits the "sync waits".
Not measured on an iPhone. Rollback: remove this adapter. Fail closed on drift: the files must be the Core 827
preparation's.
"""
import hashlib
from adapt_session import once

SYNC = 'src/Ryujinx.Graphics.Vulkan/SyncManager.cs'
MAP = 'src/Ryujinx.Graphics.GAL/Multithreading/SyncMap.cs'
BASELINE = {
    SYNC: '67086a58125c6bb21815a41e6461d07632cf8895aa18ac79180e87f30d2a46e0',
    MAP: 'db9f32728fbba061aa16ab6d2021c0c5ba4d4f1c97bb501e38f57cced689bcb8',
}
TAG = 'RewindBox (adapt_unblocked_sync_queries)'

USING_OLD = '''using System.Diagnostics;

namespace Ryujinx.Graphics.Vulkan
'''
USING_NEW = '''using System.Diagnostics;
using System.Threading;

namespace Ryujinx.Graphics.Vulkan
'''

FIELDS_OLD = '''        private ulong _flushId;
        private long _waitTicks;
'''
FIELDS_NEW = '''        private ulong _flushId;
        private long _waitTicks;

        // ''' + TAG + ''': the journal of the host sync waits (by waiter: GPU thread, render thread, other
        // threads; those for which the waiter had the command buffer submitted) and of the sync queries. Added by any
        // thread, read and cleared by Cleanup on the render thread every 5 s.
        private readonly long[] _waitCalls = new long[3];
        private readonly long[] _waitKindTicks = new long[3];
        private long _waitLongest, _flushedWaits, _flushedWaitTicks;
        private long _queries, _queryTicks, _queryLongest, _queryPolls, _queryPassed;
        private long _journalStart;
        private int _renderThreadId;
'''

QUERY_OLD = '''        public ulong GetCurrent()
        {
            lock (_handles)
            {
                ulong lastHandle = _firstHandle;

                foreach (SyncHandle handle in _handles)
                {
                    lock (handle)
                    {
                        if (handle.Waitable == null)
                        {
                            continue;
                        }

                        if (handle.ID > lastHandle)
                        {
                            bool signaled = handle.Signalled || handle.Waitable.WaitForFences(_gd.Api, _device, 0);
                            if (signaled)
                            {
                                lastHandle = handle.ID;
                                handle.Signalled = true;
                            }
                        }
                    }
                }

                return lastHandle;
            }
        }
'''
QUERY_NEW = '''        public ulong GetCurrent()
        {
            long queryStart = Stopwatch.GetTimestamp(); // ''' + TAG + '''
            ulong current;
            long polls = 0;
            long passed = 0;

            lock (_handles)
            {
                ulong lastHandle = _firstHandle;

                foreach (SyncHandle handle in _handles)
                {
                    // ''' + TAG + ''': a reader in Wait holds its handle while the GPU completes the
                    // handle's command buffer. The query does not wait for that work here (it holds the handle queue, so
                    // every sync creation, cleanup and lookup would wait with it): the handle counts as not signalled yet,
                    // as a poll that comes too early would, unless it was already read signalled; the scan goes on.
                    if (!Monitor.TryEnter(handle))
                    {
                        passed++;

                        if (handle.Signalled && handle.ID > lastHandle)
                        {
                            lastHandle = handle.ID;
                        }

                        continue;
                    }

                    try
                    {
                        if (handle.Waitable == null)
                        {
                            continue;
                        }

                        if (handle.ID > lastHandle)
                        {
                            polls += handle.Signalled ? 0 : 1; // ''' + TAG + '''
                            bool signaled = handle.Signalled || handle.Waitable.WaitForFences(_gd.Api, _device, 0);
                            if (signaled)
                            {
                                lastHandle = handle.ID;
                                handle.Signalled = true;
                            }
                        }
                    }
                    finally
                    {
                        Monitor.Exit(handle);
                    }
                }

                current = lastHandle;
            }

            NoteQuery(Stopwatch.GetTimestamp() - queryStart, polls, passed); // ''' + TAG + '''

            return current;
        }

        // ''' + TAG + ''': journal counters (diagnostics only).
        private void NoteQuery(long ticks, long polls, long passed)
        {
            Interlocked.Increment(ref _queries);
            Interlocked.Add(ref _queryTicks, ticks);
            Interlocked.Add(ref _queryPolls, polls);
            Interlocked.Add(ref _queryPassed, passed);
            RaiseLongest(ref _queryLongest, ticks);
        }

        private void NoteWait(long ticks, bool flushRequested)
        {
            int kind = Environment.CurrentManagedThreadId == Volatile.Read(ref _renderThreadId) ? 1 :
                Thread.CurrentThread.Name == "GPU.MainThread" ? 0 : 2;
            Interlocked.Increment(ref _waitCalls[kind]);
            Interlocked.Add(ref _waitKindTicks[kind], ticks);
            RaiseLongest(ref _waitLongest, ticks);

            if (flushRequested)
            {
                Interlocked.Increment(ref _flushedWaits);
                Interlocked.Add(ref _flushedWaitTicks, ticks);
            }
        }

        private static void RaiseLongest(ref long longest, long ticks)
        {
            long seen = Volatile.Read(ref longest);

            while (ticks > seen)
            {
                long found = Interlocked.CompareExchange(ref longest, ticks, seen);

                if (found == seen)
                {
                    break;
                }

                seen = found;
            }
        }

        private static string JournalMs(long ticks) =>
            (ticks * 1000.0 / Stopwatch.Frequency).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);

        private void LogJournalIfDue()
        {
            long now = Stopwatch.GetTimestamp();
            Volatile.Write(ref _renderThreadId, Environment.CurrentManagedThreadId);

            if (_journalStart == 0)
            {
                _journalStart = now;

                return;
            }

            if (now - _journalStart < Stopwatch.Frequency * 5)
            {
                return;
            }

            long[] calls = new long[3];
            long[] ticks = new long[3];

            for (int kind = 0; kind < 3; kind++)
            {
                calls[kind] = Interlocked.Exchange(ref _waitCalls[kind], 0);
                ticks[kind] = Interlocked.Exchange(ref _waitKindTicks[kind], 0);
            }

            Ryujinx.Graphics.GAL.Multithreading.SyncAvailabilityWaits.Take(out long laggedCalls, out long laggedTicks, out long laggedLongest);
            System.Text.StringBuilder text = new("Vulkan host sync waits over ");
            text.Append(JournalMs(now - _journalStart)).Append(" ms: ").Append(calls[0] + calls[1] + calls[2]).Append(" waits ")
                .Append(JournalMs(ticks[0] + ticks[1] + ticks[2])).Append(" ms (longest ").Append(JournalMs(Interlocked.Exchange(ref _waitLongest, 0)))
                .Append(" ms; GPU thread ").Append(calls[0]).Append(' ').Append(JournalMs(ticks[0])).Append(" ms, render thread ")
                .Append(calls[1]).Append(' ').Append(JournalMs(ticks[1])).Append(" ms, other threads ").Append(calls[2]).Append(' ')
                .Append(JournalMs(ticks[2])).Append(" ms; submitted for the waiter ").Append(Interlocked.Exchange(ref _flushedWaits, 0))
                .Append(' ').Append(JournalMs(Interlocked.Exchange(ref _flushedWaitTicks, 0))).Append(" ms); waits for the render thread to create the sync ")
                .Append(laggedCalls).Append(' ').Append(JournalMs(laggedTicks)).Append(" ms (longest ").Append(JournalMs(laggedLongest))
                .Append(" ms); sync queries ").Append(Interlocked.Exchange(ref _queries, 0)).Append(' ')
                .Append(JournalMs(Interlocked.Exchange(ref _queryTicks, 0))).Append(" ms (longest ").Append(JournalMs(Interlocked.Exchange(ref _queryLongest, 0)))
                .Append(" ms, fence holders polled ").Append(Interlocked.Exchange(ref _queryPolls, 0)).Append(", passed a sync being waited for ")
                .Append(Interlocked.Exchange(ref _queryPassed, 0)).Append(") (adapt_unblocked_sync_queries)");
            _journalStart = now;
            Logger.Warning?.Print(LogClass.Gpu, text.ToString());
        }
'''

FLUSH_OLD = '''                long beforeTicks = Stopwatch.GetTimestamp();

                if (result.NeedsFlush(System.Threading.Volatile.Read(ref _flushId)))
                {
                    RequestFlush(result);
                }
'''
FLUSH_NEW = '''                long beforeTicks = Stopwatch.GetTimestamp();
                bool flushRequested = result.NeedsFlush(System.Threading.Volatile.Read(ref _flushId)); // ''' + TAG + '''

                if (flushRequested)
                {
                    RequestFlush(result);
                }
'''

WAITED_OLD = '''                        System.Threading.Interlocked.Add(ref _waitTicks, Stopwatch.GetTimestamp() - beforeTicks);
                        result.Signalled = true;
'''
WAITED_NEW = '''                        long waited = Stopwatch.GetTimestamp() - beforeTicks; // ''' + TAG + '''
                        System.Threading.Interlocked.Add(ref _waitTicks, waited);
                        result.Signalled = true;
                        NoteWait(waited, flushRequested); // ''' + TAG + '''
'''

CLEANUP_OLD = '''            // Iterate through handles and remove any that have already been signalled.

            while (true)
'''
CLEANUP_NEW = '''            // Iterate through handles and remove any that have already been signalled.
            LogJournalIfDue(); // ''' + TAG + '''

            while (true)
'''

MAP_WAIT_OLD = '''            bool signal = false;

            while (true)
            {
                lock (_inFlight)
                {
                    if (!_inFlight.Contains(id))
                    {
                        break;
                    }
                }

                _renderer.ThrowIfFailed();
'''
MAP_WAIT_NEW = '''            bool signal = false;
            long waitStart = 0; // ''' + TAG + '''

            while (true)
            {
                lock (_inFlight)
                {
                    if (!_inFlight.Contains(id))
                    {
                        break;
                    }
                }

                waitStart = waitStart != 0 ? waitStart : System.Diagnostics.Stopwatch.GetTimestamp(); // ''' + TAG + '''
                _renderer.ThrowIfFailed();
'''

MAP_DONE_OLD = '''            _renderer.ThrowIfFailed();

            if (signal)
            {
'''
MAP_DONE_NEW = '''            _renderer.ThrowIfFailed();

            if (waitStart != 0)
            {
                SyncAvailabilityWaits.Note(System.Diagnostics.Stopwatch.GetTimestamp() - waitStart); // ''' + TAG + '''
            }

            if (signal)
            {
'''

MAP_CLASS_OLD = '''        public void Dispose()
        {
            _inFlightChanged.Dispose();
        }
    }
}'''
MAP_CLASS_NEW = '''        public void Dispose()
        {
            _inFlightChanged.Dispose();
        }
    }

    /// <summary>
    /// ''' + TAG + ''': the waits for a sync the render thread had not created yet when a reader asked for it
    /// (WaitSyncAvailability): calls, time and the longest, added by the waiting threads and taken by the backend's journal.
    /// </summary>
    public static class SyncAvailabilityWaits
    {
        private static long _calls, _ticks, _longest;

        internal static void Note(long ticks)
        {
            Interlocked.Increment(ref _calls);
            Interlocked.Add(ref _ticks, ticks);
            long seen = Volatile.Read(ref _longest);

            while (ticks > seen)
            {
                long found = Interlocked.CompareExchange(ref _longest, ticks, seen);

                if (found == seen)
                {
                    break;
                }

                seen = found;
            }
        }

        public static void Take(out long calls, out long ticks, out long longest)
        {
            calls = Interlocked.Exchange(ref _calls, 0);
            ticks = Interlocked.Exchange(ref _ticks, 0);
            longest = Interlocked.Exchange(ref _longest, 0);
        }
    }
}'''

PAIRS = [
    (SYNC, USING_OLD, USING_NEW),
    (SYNC, FIELDS_OLD, FIELDS_NEW),
    (SYNC, QUERY_OLD, QUERY_NEW),
    (SYNC, FLUSH_OLD, FLUSH_NEW),
    (SYNC, WAITED_OLD, WAITED_NEW),
    (SYNC, CLEANUP_OLD, CLEANUP_NEW),
    (MAP, MAP_WAIT_OLD, MAP_WAIT_NEW),
    (MAP, MAP_DONE_OLD, MAP_DONE_NEW),
    (MAP, MAP_CLASS_OLD, MAP_CLASS_NEW),
]


def apply(source):
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(source / name, old, new)
    return [source / name for name in BASELINE]
