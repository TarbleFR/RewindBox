using System;
using System.Buffers;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Memory;
using Buffer = Ryujinx.Graphics.Gpu.Memory.Buffer;

static class Program
{
    static int checks;
    static ulong digest = 14695981039346656037;
    static void Check(bool okay, string message)
    {
        checks++;
        if (!okay) throw new Exception(message);
    }
    static void Record(ulong value) => digest = unchecked((digest ^ value) * 1099511628211);
    static void RecordRange(ulong address, ulong size) { Record(address); Record(size); }
    static (GpuContext Context, Buffer Buffer, BufferModifiedRangeList List) Make(ulong sync = 10,
        BufferFlushAction flush = null)
    {
        var context = new GpuContext { SyncNumber = sync };
        var buffer = new Buffer { Address = 0, Size = 65536 };
        var list = new BufferModifiedRangeList(context, buffer, flush ?? (static (_, _, _) => { }));
        return (context, buffer, list);
    }
    static void ExpectFailure(Action action)
    {
        bool failed = false;
        try { action(); } catch (ProbeFailure) { failed = true; }
        Check(failed, "exception must propagate");
    }

    static void Functional()
    {
        var empty = Make();
        empty.List.GetRanges(0, 4096, (_, _) => throw new Exception("empty callback"));
        empty.List.WaitForAndFlushRanges(0, 4096);
        Check(empty.Context.Renderer.Waits.Count == 0 && empty.List.Count == 0, "empty");

        // Address-order and snapshot behavior, including callback mutation/nested enumeration.
        for (int n = 1; n <= 128; n++)
        {
            var item = Make();
            for (int i = n - 1; i >= 0; i--) item.List.SignalModified((ulong)i * 64, 16);
            int visited = 0;
            item.List.GetRanges(0, 16384, (address, size) =>
            {
                Check(address == (ulong)visited * 64 && size == 16, "ordered snapshot");
                RecordRange(address, size);
                visited++;
                if (visited == 1)
                {
                    item.List.GetRanges(0, 16384, RecordRange);
                    item.List.SignalModified(32768, 16);
                }
            });
            Check(visited == n && item.List.Count == n + 1, "private reentrant snapshot");
            item.List.WaitForAndFlushRanges(0, 65536);
            Check(item.Context.Renderer.Waits.Count == 0, "current sync ignored");
            item.Context.SyncNumber++;
            item.List.WaitForAndFlushRanges(0, 65536);
            Check(item.List.Count == 0 && item.Context.Renderer.Waits.SequenceEqual(new ulong[] { 10 }), "flush older sync");
        }

        // Signed wraparound fence arithmetic is unchanged.
        foreach (ulong current in new ulong[] { 0, 1, 10, ulong.MaxValue - 1, ulong.MaxValue })
        {
            var flushes = new List<(ulong, ulong, ulong)>();
            var item = Make(current, (a, s, n) => { flushes.Add((a, s, n)); Record(a); Record(s); Record(n); });
            foreach (var pair in new (ulong Address, ulong Sync)[] { (0, unchecked(current - 2)), (64, unchecked(current - 1)), (128, current), (192, unchecked(current + 1)) })
            {
                item.Context.SyncNumber = pair.Sync;
                item.List.SignalModified(pair.Address, 16);
            }
            item.Context.SyncNumber = current;
            item.List.WaitForAndFlushRanges(8, 144);
            Check(item.Context.Renderer.Waits.SequenceEqual(new[] { unchecked(current - 1) }), "wrap wait");
            Check(flushes.Count == 2 && flushes[0] == (8UL, 8UL, unchecked(current - 1)) &&
                flushes[1] == (64UL, 16UL, unchecked(current - 1)), "clamped flush");
            Check(item.List.HasRange(0, 8) && !item.List.HasRange(8, 8) && item.List.HasRange(128, 16), "remaining regions");
        }

        // All migration sources remain live until the original sync completes.
        for (int n = 0; n <= 64; n++)
        {
            var source = Make(9);
            for (int i = 0; i < n; i++) source.List.SignalModified((ulong)i * 64, 16);
            var target = Make(10);
            int registrations = 0;
            target.List.InheritRanges(source.List, (a, s) => { registrations++; RecordRange(a, s); });
            Check(registrations == n && source.Buffer.References == 2 && target.List.Count == n, "inherit");
            target.List.GetRanges(0, 65536, RecordRange);
            source.List.WaitForAndFlushRanges(0, 65536);
            Check(target.List.Count == 0, "redirect inherited flush");
            foreach (var migration in target.Context.Migrations) migration.Dispose();
            Check(source.Buffer.References == 1, "migration disposal");
        }
    }

#if POOL_PROBE
    static object Ownership()
    {
        var pool = ProbePool<BufferModifiedRange>.Shared;
        int initialRents = pool.Rents, initialReturns = pool.Returns;
        var same = Make();
        same.List.SignalModified(0, 32);
        for (int i = 0; i < 1000; i++) same.List.WaitForAndFlushRanges(0, 32);
        int currentRentals = pool.Rents - initialRents;
        int currentReturns = pool.Returns - initialReturns;
#if ADAPTED
        Check(currentRentals == 1000 && currentReturns == 1000, "return current/future sync snapshots");
#else
        Check(currentRentals == 1000 && currentReturns == 0, "baseline missing returns reproduced");
#endif

        int before = pool.Returns;
        ExpectFailure(() => same.List.GetRanges(0, 32, (_, _) => throw new ProbeFailure()));
#if ADAPTED
        Check(pool.Returns == before + 1, "callback failure returns snapshot");
#else
        Check(pool.Returns == before, "baseline callback loss");
#endif
        same.Context.SyncNumber++;
        same.Context.Renderer.OnWait = _ => throw new ProbeFailure();
        before = pool.Returns;
        ExpectFailure(() => same.List.WaitForAndFlushRanges(0, 32));
#if ADAPTED
        Check(!same.List.Lock.IsWriteLockHeld && pool.Returns == before + 1, "fence failure cleanup");
#else
        Check(same.List.Lock.IsWriteLockHeld && pool.Returns == before, "baseline fence leak reproduced");
        same.List.Lock.ExitWriteLock();
#endif
        var source = Make(9);
        source.List.SignalModified(0, 32);
        var target = Make(10);
        before = pool.Returns;
        ExpectFailure(() => target.List.InheritRanges(source.List, (_, _) => throw new ProbeFailure()));
#if ADAPTED
        Check(pool.Returns == before + 1, "inherit callback cleanup");
#else
        Check(pool.Returns == before, "baseline inherit callback loss");
#endif
        Check(!source.List.Lock.IsReadLockHeld && !target.List.Lock.IsWriteLockHeld, "inherit locks");

        var flushing = Make(9, (_, _, _) => throw new ProbeFailure());
        flushing.List.SignalModified(0, 32);
        flushing.Context.SyncNumber++;
        before = pool.Returns;
        ExpectFailure(() => flushing.List.WaitForAndFlushRanges(0, 32));
#if ADAPTED
        Check(!flushing.List.Lock.IsWriteLockHeld && pool.Returns == before + 1, "flush callback cleanup");
#else
        Check(flushing.List.Lock.IsWriteLockHeld && pool.Returns == before, "baseline flush lock leak");
        flushing.List.Lock.ExitWriteLock();
#endif

        // A failed migrated flush has no active user after stack unwinding.
        // The old path leaves the counter positive, causing Dispose to spin.
        var migratingSource = Make(9, (_, _, _) => throw new ProbeFailure());
        var migrationTarget = Make(10);
        migrationTarget.List.InheritRanges(migratingSource.List, static (_, _) => { });
        var migration = migrationTarget.Context.Migrations.Single();
        ExpectFailure(() => migration.RangeActionWithMigration(0, 32, 9, static (_, _, _) => { }));
        var field = typeof(BufferMigration).GetField("_refCount", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
        int active = (int)field.GetValue(migration);
#if ADAPTED
        Check(active == 0, "failed migration releases active traversal");
        migration.Dispose();
        Check(migratingSource.Buffer.References == 1, "failed migration can be disposed");
#else
        Check(active == 1, "baseline leaked traversal reproduced without spinning teardown");
#endif

        // Failure acquiring the snapshot must also release the original lock.
        pool.FailRent = true;
        ExpectFailure(() => same.List.GetRanges(0, 32, RecordRange));
#if ADAPTED
        Check(!same.List.Lock.IsReadLockHeld, "rent failure unlocks reader");
#else
        Check(same.List.Lock.IsReadLockHeld, "baseline rent reader lock leak");
        same.List.Lock.ExitReadLock();
#endif
        pool.FailRent = true;
        ExpectFailure(() => same.List.WaitForAndFlushRanges(0, 32));
#if ADAPTED
        Check(!same.List.Lock.IsWriteLockHeld, "rent failure unlocks writer");
#else
        Check(same.List.Lock.IsWriteLockHeld, "baseline rent writer lock leak");
        same.List.Lock.ExitWriteLock();
#endif
#if ADAPTED
        Check(pool.Outstanding.Count == 0 && pool.RetainedReferences() == 0, "no pooled range roots");
#else
        Check(pool.Outstanding.Count > 1000 && pool.RetainedReferences() > 0, "baseline roots reproduced");
#endif
        return new { currentRentals, currentReturns, outstanding = pool.Outstanding.Count,
            retainedReferences = pool.RetainedReferences(), rents = pool.Rents, returns = pool.Returns };
    }
#else
    static object Bench()
    {
        var item = Make();
        item.List.SignalModified(0, 32);
        for (int i = 0; i < 1000; i++) item.List.WaitForAndFlushRanges(0, 32);
        long allocated = GC.GetAllocatedBytesForCurrentThread();
        long started = Stopwatch.GetTimestamp();
        for (int i = 0; i < 20000; i++) item.List.WaitForAndFlushRanges(0, 32);
        long elapsed = Stopwatch.GetTimestamp() - started;
        long allocatedBytes = GC.GetAllocatedBytesForCurrentThread() - allocated;
        return new { iterations = 20000, allocatedBytes,
            elapsedNs = elapsed * (1e9 / Stopwatch.Frequency) };
    }
#endif
    static void Main()
    {
        Functional();
        ulong semanticDigest = digest;
#if POOL_PROBE
        var measurements = Ownership();
#else
        var measurements = Bench();
#endif
        Console.WriteLine(JsonSerializer.Serialize(new { checks, semanticDigest, measurements }));
    }
}
