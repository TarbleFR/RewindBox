using System;
using System.Buffers;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using Ryujinx.Memory;
using Ryujinx.Memory.Tracking;

static class Check
{
    public static int Count;
    public static void That(bool value, string message)
    {
        Interlocked.Increment(ref Count);
        if (!value) throw new Exception(message);
    }
}

// Only the pool boundary is replaced in ownership mode. The real production
// tracking, locking, bitmap, range hierarchy and callback bodies are compiled.
sealed class SnapshotPoolProbe<T>
{
    public static readonly SnapshotPoolProbe<T> Shared = new();
    static readonly object Gate = new();
    static readonly HashSet<T[]> Live = new();
    public static int Rents, Returns, PeakLive, ClearedReturns, MaxRequested;
    public T[] Rent(int length)
    {
        T[] value = ArrayPool<T>.Shared.Rent(length);
        lock (Gate)
        {
            Check.That(Live.Add(value), "A live snapshot is never rented twice");
            Rents++; PeakLive = Math.Max(PeakLive, Live.Count);
            MaxRequested = Math.Max(MaxRequested, length);
        }
        return value;
    }
    public void Return(T[] value, bool clearArray = false)
    {
        lock (Gate)
        {
            Check.That(Live.Remove(value), "Every returned snapshot has one live owner");
            Check.That(clearArray, "Pool returns must clear all reference slots");
            Returns++; ClearedReturns++;
        }
        ArrayPool<T>.Shared.Return(value, clearArray);
    }
    public static void Balanced()
    {
        lock (Gate) Check.That(Live.Count == 0 && Rents == Returns, "No snapshot survives its signalling invocation");
    }
}

sealed class MemoryBoundary : IVirtualMemoryManager
{
    public bool Record;
    public bool Mapped = true;
    public Action OnProtect;
    public int ProtectionCalls;
    public bool IsRangeMapped(ulong address, ulong size) => Mapped;
    public void TrackingReprotect(ulong address, ulong size, MemoryPermission permission, bool guest)
    {
        ProtectionCalls++;
        if (Record) Program.Trace.Add($"protect:{address:X}:{size:X}:{permission}:{guest}");
        OnProtect?.Invoke();
    }
}

static class Program
{
#if ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif
#if POOL_PROBE
    const bool Probed = true;
#else
    const bool Probed = false;
#endif
    public static readonly List<string> Trace = new();
    static int Cases;

    static (MemoryTracking, MemoryBoundary) Create(bool record = true)
    {
        var boundary = new MemoryBoundary { Record = record };
        return (new MemoryTracking(boundary, 0x1000), boundary);
    }

    static RegionHandle[] Make(MemoryTracking tracking, int count, ulong address = 0x4000)
    {
        var handles = new RegionHandle[count];
        for (int i = 0; i < count; i++) handles[i] = tracking.BeginTracking(address, 0x1000, i + 1);
        return handles;
    }

    static void Basic(int count, bool precise, bool guest, bool write, bool mutate, int? exempt)
    {
        Cases++;
        (var tracking, var boundary) = Create();
        RegionHandle[] handles = Make(tracking, count);
        var live = new HashSet<RegionHandle>(handles);
        RegionHandle added = null;
        int calls = 0;
        for (int i = 0; i < count; i++)
        {
            int index = i;
            handles[i].Reprotect();
            handles[i].RegisterDirtyEvent(() => Trace.Add($"dirty:{index}"));
            handles[i].RegisterPreciseAction((address, size, written) =>
            {
                Trace.Add($"precise:{index}:{address:X}:{size:X}:{written}");
                return index % 3 == 2;
            });
            handles[i].RegisterAction((address, size) =>
            {
                calls++;
                Check.That(!Monitor.IsEntered(tracking.TrackingLock), "Pre-actions still run outside TrackingLock");
                Trace.Add($"action:{index}:{address:X}:{size:X}");
                if (mutate && index == 0)
                {
                    int victim = count - 1;
                    handles[victim].Dispose(); live.Remove(handles[victim]);
                    added = tracking.BeginTracking(0x4000, 0x1000, 900);
                    added.RegisterAction((a, s) => Trace.Add("unexpected-new-handle"));
                    live.Add(added);
                }
            });
        }
        Trace.Add($"case:{count}:{precise}:{guest}:{write}:{mutate}:{exempt}");
        tracking.VirtualMemoryEvent(0x4108, 0x20, write, precise, exempt, guest);
        Check.That(!Trace.Contains("unexpected-new-handle"), "A handle created after unlock is absent from the private snapshot");
        int expected = Enumerable.Range(0, count).Count(i => i + 1 != exempt && (!precise || i % 3 != 2));
        Check.That(calls == expected, "All original eligible pre-actions execute exactly once");
        foreach (RegionHandle handle in live) handle.Dispose();
        Check.That(tracking.GetRegionCount() == 0, "All virtual regions are removed after case cleanup");
        SnapshotPoolProbe<RegionHandle>.Balanced();
    }

    static void Exceptions(bool precise, bool protection)
    {
        Cases++;
        (var tracking, var boundary) = Create();
        RegionHandle[] handles = Make(tracking, 17);
        RegionSignal action = (_, _) => { if (!protection) throw new InvalidOperationException("action"); };
        handles[0].RegisterAction(action);
        if (protection) boundary.OnProtect = () => throw new InvalidOperationException("protection");
        bool caught = false;
        try { tracking.VirtualMemoryEvent(0x4100, 16, false, precise); }
        catch (InvalidOperationException error) { caught = true; Trace.Add($"caught:{error.Message}:{precise}"); }
        Check.That(caught, "The original callback/protection exception is propagated");
        Check.That(!Monitor.IsEntered(tracking.TrackingLock), "TrackingLock is balanced after an exception");
        SnapshotPoolProbe<RegionHandle>.Balanced();
        boundary.OnProtect = null;
        foreach (RegionHandle handle in handles) handle.Dispose();
    }

    static void Reentrant()
    {
        Cases++;
        (var tracking, _) = Create();
        RegionHandle[] outer = Make(tracking, 17);
        RegionHandle[] inner = Make(tracking, 3, 0x8000);
        foreach (RegionHandle h in inner) h.RegisterAction((a, s) => Trace.Add($"inner:{h.Id}"));
        outer[0].RegisterAction((a, s) =>
        {
            Trace.Add("outer:start");
            tracking.VirtualMemoryEvent(0x8080, 16, true, false);
            Trace.Add("outer:end");
        });
        outer[1].RegisterAction((a, s) => Trace.Add("outer:second"));
        tracking.VirtualMemoryEvent(0x4080, 16, true, false);
        foreach (RegionHandle h in outer.Concat(inner)) h.Dispose();
        if (Probed && Adapted) Check.That(SnapshotPoolProbe<RegionHandle>.PeakLive >= 2, "Nested signalling owns independent simultaneous snapshots");
        SnapshotPoolProbe<RegionHandle>.Balanced();
    }

    static void ConcurrentMutation()
    {
        Cases++;
        (var tracking, _) = Create(record: false);
        RegionHandle[] handles = Make(tracking, 8);
        RegionHandle added = null;
        using var entered = new ManualResetEventSlim();
        using var mutated = new ManualResetEventSlim();
        Exception workerError = null;
        int oldAction = 0, newAction = 0;
        handles[0].RegisterAction((a, s) =>
        {
            entered.Set();
            Check.That(mutated.Wait(TimeSpan.FromSeconds(10)), "Another thread can mutate topology while the pre-action is unlocked");
        });
        handles[7].RegisterAction((a, s) => Interlocked.Increment(ref oldAction));
        var worker = new Thread(() =>
        {
            try
            {
                Check.That(entered.Wait(TimeSpan.FromSeconds(10)), "The first callback reaches its unlocked boundary");
                handles[7].Dispose();
                added = tracking.BeginTracking(0x4000, 0x1000, 99);
                added.RegisterAction((a, s) => Interlocked.Increment(ref newAction));
            }
            catch (Exception error) { workerError = error; }
            finally { mutated.Set(); }
        });
        worker.Start();
        try { tracking.VirtualMemoryEvent(0x4100, 16, false, false); }
        finally { Check.That(worker.Join(TimeSpan.FromSeconds(10)), "The mutation worker terminates"); }
        if (workerError != null) throw workerError;
        Check.That(oldAction == 1 && newAction == 0, "The unlocked traversal keeps its original private list across concurrent mutation");
        for (int i = 0; i < 7; i++) handles[i].Dispose();
        added.Dispose();
        SnapshotPoolProbe<RegionHandle>.Balanced();
    }

    static void Mapping()
    {
        Cases++;
        (var tracking, var boundary) = Create();
        RegionHandle[] handles = Make(tracking, 2);
        int calls = 0;
        handles[0].RegisterAction((a, s) => calls++);
        boundary.Mapped = false;
        tracking.Unmap(0x4000, 0x1000);
        tracking.VirtualMemoryEvent(0x4100, 8, true, false);
        Check.That(calls == 0, "Unmapped handles consume a pre-action without executing it");
        boundary.Mapped = true;
        tracking.Map(0x4000, 0x1000);
        tracking.VirtualMemoryEvent(0x4100, 8, true, false);
        Check.That(calls == 0, "Consumed pre-actions cannot flush after remapping");
        foreach (RegionHandle h in handles) h.Dispose();
    }

    static void Bounds(int count)
    {
        Cases++;
        (var tracking, _) = Create(record: false);
        RegionHandle[] handles = Make(tracking, count);
        int before = SnapshotPoolProbe<RegionHandle>.Rents;
        int calls = 0;
        handles[0].RegisterAction((a, s) => calls++);
        tracking.VirtualMemoryEvent(0x4100, 8, false, false);
        Check.That(calls == 1, "Boundary-sized snapshot executes its pre-action once");
        if (Probed && Adapted)
            Check.That(SnapshotPoolProbe<RegionHandle>.Rents - before == (count > 1 && count <= 4096 ? 1 : 0),
                "Only snapshots between two and 4096 references enter the pool");
        foreach (RegionHandle h in handles) h.Dispose();
        SnapshotPoolProbe<RegionHandle>.Balanced();
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference FinishedOwner()
    {
        (var tracking, _) = Create(record: false);
        RegionHandle[] handles = Make(tracking, 17);
        handles[0].RegisterAction(static (a, s) => { });
        tracking.VirtualMemoryEvent(0x4100, 8, false, false);
        foreach (RegionHandle h in handles) h.Dispose();
        return new WeakReference(tracking);
    }

    static void Lifetime()
    {
        Cases++;
        WeakReference owner = FinishedOwner();
        for (int i = 0; i < 3 && owner.IsAlive; i++) { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
        Check.That(!owner.IsAlive, "Returned snapshot arrays do not root a closed tracking hierarchy");
    }

    static object Benchmark(int count)
    {
        (var tracking, _) = Create(record: false);
        RegionHandle[] handles = Make(tracking, count);
        RegionSignal action = static (a, s) => { };
        void Access(int iterations)
        {
            for (int i = 0; i < iterations; i++)
            {
                handles[0].RegisterAction(action);
                tracking.VirtualMemoryEvent(0x4100, 8, false, false);
            }
        }
        Access(1500);
        int rounds = count > 1024 ? 1200 : 12000;
        var timings = new double[5];
        long total = 0;
        for (int repeat = 0; repeat < timings.Length; repeat++)
        {
            long allocated = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            Access(rounds);
            timings[repeat] = Stopwatch.GetElapsedTime(start).TotalNanoseconds / rounds;
            total += GC.GetAllocatedBytesForCurrentThread() - allocated;
        }
        Array.Sort(timings);
        foreach (RegionHandle h in handles) h.Dispose();
        return new { count, rounds, repeats = timings.Length, allocatedBytes = total,
            bytesPerEvent = (double)total / (rounds * timings.Length), medianNanosecondsPerEvent = timings[2] };
    }

    static void Main()
    {
        foreach (int count in new[] { 1, 2, 8, 16, 17, 64 })
            foreach (bool precise in new[] { false, true })
                foreach (bool guest in new[] { false, true })
                    foreach (bool write in new[] { false, true })
                    {
                        Basic(count, precise, guest, write, mutate: false, exempt: null);
                        Basic(count, precise, guest, write, mutate: true, exempt: null);
                        Basic(count, precise, guest, write, mutate: false, exempt: 1);
                    }
        Exceptions(false, false); Exceptions(true, false);
        Exceptions(false, true); Exceptions(true, true);
        Reentrant(); ConcurrentMutation(); Mapping();
        foreach (int count in new[] { 1, 2, 4096, 4097 }) Bounds(count);
        Lifetime();
        string digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n', Trace))));
        object benchmark = Probed ? null : new[] { 1, 2, 16, 64, 512, 4096, 4097 }.Select(Benchmark).ToArray();
        Console.WriteLine(JsonSerializer.Serialize(new { adapted = Adapted, probed = Probed, cases = Cases,
            checks = Check.Count, semanticTrace = digest, traceEvents = Trace.Count, benchmark,
            pool = new { rents = SnapshotPoolProbe<RegionHandle>.Rents, returns = SnapshotPoolProbe<RegionHandle>.Returns,
                clearedReturns = SnapshotPoolProbe<RegionHandle>.ClearedReturns, peakLive = SnapshotPoolProbe<RegionHandle>.PeakLive,
                maxRequested = SnapshotPoolProbe<RegionHandle>.MaxRequested }, physicalDeviceTested = false }));
    }
}

namespace Ryujinx.Common { internal static class BoundaryNamespace { } }
namespace Ryujinx.Memory
{
    public interface IVirtualMemoryManager
    {
        bool IsRangeMapped(ulong address, ulong size);
        void TrackingReprotect(ulong address, ulong size, MemoryPermission permission, bool guest);
    }
}
