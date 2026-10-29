using System;
using System.Buffers;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
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
        Count++;
        if (!value) throw new Exception(message);
    }
    public static void Throws<T>(Action action, string message) where T : Exception
    {
        try { action(); }
        catch (T) { Count++; return; }
        throw new Exception(message);
    }
}

// Test-only pool boundary. Production ArrayPool calls are redirected here only
// in the ownership probe, never in the unmodified-body timing executable.
static class TrackingProbe
{
    public static int Searches, Rents, Returns, DirtyReturns;
    public static void Reset() => Searches = Rents = Returns = DirtyReturns = 0;
}

sealed class TrackingPoolProbe<T>
{
    public static readonly TrackingPoolProbe<T> Shared = new();
    public T[] Rent(int length)
    {
        TrackingProbe.Rents++;
        return ArrayPool<T>.Shared.Rent(length);
    }
    public void Return(T[] array, bool clearArray = false)
    {
        TrackingProbe.Returns++;
        if (clearArray) Array.Clear(array);
        if (array.Any(value => value != null)) TrackingProbe.DirtyReturns++;
        ArrayPool<T>.Shared.Return(array);
    }
}

sealed class MemoryDouble : IVirtualMemoryManager
{
    public readonly List<string> Trace;
    public readonly List<(ulong Address, ulong Size)> Unmapped = new();
    public int ProtectionCalls;
    public bool Record = true;
    public MemoryDouble(List<string> trace) => Trace = trace;
    public bool IsRangeMapped(ulong address, ulong size)
    {
        bool mapped = address < 0x100000000 && size <= 0x100000000 - address &&
            !Unmapped.Any(range => address < range.Address + range.Size && range.Address < address + size);
        if (Record) Trace.Add($"mapped:{address:X}:{size:X}:{mapped}");
        return mapped;
    }
    public void TrackingReprotect(ulong address, ulong size, MemoryPermission permission, bool guest)
    {
        ProtectionCalls++;
        if (Record) Trace.Add($"protect:{address:X}:{size:X}:{permission}:{guest}");
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
    const bool Instrumented = true;
#else
    const bool Instrumented = false;
#endif
    static readonly List<string> Trace = new();

    static MemoryTracking Create(out MemoryDouble memory, bool singleByte = false)
    {
        memory = new(Trace);
        return new MemoryTracking(memory, 0x1000, address => { Trace.Add($"invalid:{address:X}"); return false; }, singleByte);
    }

    static void Watch(RegionHandle handle, string name, bool preciseResult = true)
    {
        handle.RegisterPreciseAction((address, size, write) =>
        {
            Trace.Add($"precise:{name}:{address:X}:{size:X}:{write}");
            return preciseResult;
        });
        handle.RegisterDirtyEvent(() => Trace.Add($"dirty:{name}"));
    }

    static object Cached(MemoryTracking tracking, bool guest)
        => typeof(MemoryTracking).GetField(guest ? "_lastGuestVirtualRegion" : "_lastVirtualRegion",
            BindingFlags.NonPublic | BindingFlags.Instance)?.GetValue(tracking);

    static void Basic(bool singleByte)
    {
        MemoryTracking tracking = Create(out MemoryDouble memory, singleByte);
        using RegionHandle first = tracking.BeginTracking(0x4000, 0x3000, 1, RegionFlags.UnalignedAccess);
        using RegionHandle second = tracking.BeginTracking(0x9000, 0x2000, 2);
        Watch(first, "first", preciseResult: false);
        Watch(second, "second");
        first.Reprotect();
        tracking.VirtualMemoryEvent(0x4101, 1, false, false);
        Check.That(!first.Dirty, "Read does not dirty the handle");
        tracking.VirtualMemoryEvent(0x4101, 1, true, false, 1);
        Check.That(!first.Dirty, "Exempt ID is preserved on a repeated region hit");
        tracking.VirtualMemoryEvent(0x4101, 1, true, false);
        Check.That(first.Dirty, "Repeated lookup still performs dirty signalling");
        for (int i = 0; i < 12; i++)
        {
            bool guest = (i & 1) != 0;
            tracking.VirtualMemoryEvent(0x4400 + (ulong)i, 16, (i & 2) != 0, true, guest: guest);
        }
        if (Adapted)
        {
            Check.That(Cached(tracking, false) != null && Cached(tracking, true) != null,
                "Host and guest keep separate live-region lookup caches");
        }
        // Adjacent/gap/empty/wrapped accesses must retain the original lookup path.
        foreach ((ulong address, ulong size) in new[]
        {
            (0x6fffUL, 1UL), (0x7000UL, 1UL), (0x8fffUL, 2UL), (0x9000UL, 0UL),
            (0x9001UL, 0UL), (0xa000UL, 1UL), (ulong.MaxValue - 1, 4UL),
        })
        {
            tracking.VirtualMemoryEvent(address, size, false, true);
        }
        if (singleByte)
            tracking.VirtualMemoryEvent(0x3100, 1, false, true, guest: true);
        memory.Unmapped.Add((0x4000, 0x1000));
        tracking.Unmap(0x4000, 0x1000);
        Check.That(first.Unmapped, "Partial unmap still invalidates the tracking handle");
        tracking.VirtualMemoryEvent(0x4400, 4, true, false);
        Check.That(!first.Dirty, "Cached region does not bypass unmapped state");
        memory.Unmapped.Clear();
        tracking.Map(0x4000, 0x1000);
        Check.That(!first.Unmapped, "Remap still restores the handle");
        tracking.VirtualMemoryEvent(0x4400, 4, true, false);
        Check.That(first.Dirty, "Remapped cached region can become dirty again");
        Check.Throws<InvalidMemoryRegionException>(() => tracking.VirtualMemoryEvent(0x200000000, 1, false, false),
            "Invalid-access handler and exception remain intact");
    }

    static void Topology()
    {
        MemoryTracking tracking = Create(out _);
        RegionHandle outer = tracking.BeginTracking(0x10000, 0x10000, 10);
        Watch(outer, "outer");
        tracking.VirtualMemoryEvent(0x14500, 4, false, true);
        tracking.VirtualMemoryEvent(0x14500, 4, false, true, guest: true);
        RegionHandle inner = tracking.BeginTracking(0x14000, 0x4000, 11);
        Watch(inner, "inner");
        if (Adapted) Check.That(Cached(tracking, false) == null && Cached(tracking, true) == null,
            "Adding/splitting regions invalidates both affected caches");
        tracking.VirtualMemoryEvent(0x14500, 4, true, true);
        tracking.VirtualMemoryEvent(0x13000, 0x6000, true, true);
        tracking.VirtualMemoryEvent(0x14500, 4, true, true, guest: true);
        inner.Dispose();
        tracking.VirtualMemoryEvent(0x14500, 4, true, true);
        outer.Dispose();
        Check.That(tracking.GetRegionCount() == 0, "All split regions removed after handle disposal");
        if (Adapted) Check.That(Cached(tracking, false) == null && Cached(tracking, true) == null,
            "Removed regions are not rooted by the lookup caches");
        tracking.VirtualMemoryEvent(0x14500, 4, true, true);
        using RegionHandle replacement = tracking.BeginTracking(0x14000, 0x4000, 12);
        Watch(replacement, "replacement");
        tracking.VirtualMemoryEvent(0x14500, 4, true, true);
        tracking.VirtualMemoryEvent(0x14500, 4, true, true, guest: true);
    }

    static void Reentrant()
    {
        MemoryTracking tracking = Create(out _);
        using RegionHandle left = tracking.BeginTracking(0x20000, 0x2000, 20);
        RegionHandle right = tracking.BeginTracking(0x23000, 0x2000, 21);
        RegionHandle added = null;
        Watch(right, "removed-right");
        left.RegisterPreciseAction((address, size, write) =>
        {
            Trace.Add("mutation:begin");
            right.Dispose();
            added = tracking.BeginTracking(0x23000, 0x2000, 22);
            Watch(added, "added-right");
            Trace.Add("mutation:end");
            return true;
        });
        tracking.VirtualMemoryEvent(0x20000, 0x5000, false, true);
        left.RegisterPreciseAction((address, size, write) => true);
        tracking.VirtualMemoryEvent(0x23000, 4, false, true);
        added.Dispose();

        using RegionHandle broad = tracking.BeginTracking(0x30000, 0x8000, 23);
        RegionHandle split = null;
        using var actionStarted = new ManualResetEventSlim();
        using var workerDone = new ManualResetEventSlim();
        Exception workerFailure = null;
        var worker = new Thread(() =>
        {
            try
            {
                if (!actionStarted.Wait(TimeSpan.FromSeconds(5))) throw new Exception("Pre-action did not start");
                split = tracking.BeginTracking(0x34000, 0x1000, 24);
                Watch(split, "worker-split");
            }
            catch (Exception error) { workerFailure = error; }
            finally { workerDone.Set(); }
        });
        tracking.VirtualMemoryEvent(0x34100, 4, false, true);
        broad.RegisterAction((address, size) =>
        {
            actionStarted.Set();
            Check.That(workerDone.Wait(TimeSpan.FromSeconds(5)), "Pre-action still releases TrackingLock");
            if (workerFailure != null) throw workerFailure;
            Trace.Add("threaded-split:complete");
        });
        worker.Start();
        tracking.VirtualMemoryEvent(0x34100, 4, false, false);
        Check.That(worker.Join(TimeSpan.FromSeconds(5)), "Concurrent topology mutation completes");
        tracking.VirtualMemoryEvent(0x34100, 4, false, true);
        tracking.VirtualMemoryEvent(0x33100, 0x2000, false, true);
        split.Dispose();
    }

    static object ProbeOwnership()
    {
        MemoryTracking tracking = Create(out _);
        using RegionHandle first = tracking.BeginTracking(0x40000, 0x1000, 40);
        using RegionHandle second = tracking.BeginTracking(0x42000, 0x1000, 41);
        first.RegisterPreciseAction((address, size, write) => true);
        second.RegisterPreciseAction((address, size, write) => true);
        TrackingProbe.Reset();
        for (int i = 0; i < 1000; i++)
            tracking.VirtualMemoryEvent(0x40100, 16, false, true, guest: (i & 1) != 0);
        int hotSearches = TrackingProbe.Searches, hotRents = TrackingProbe.Rents;
        Check.That(hotSearches == (Adapted ? 2 : 1000), "Repeated host/guest accesses reuse only their exact region");
        Check.That(hotRents == (Adapted ? 0 : 1000), "Single-region lookup does not rent or copy a reference array");
        TrackingProbe.Reset();
        for (int i = 0; i < 1000; i++)
            tracking.VirtualMemoryEvent((i & 1) == 0 ? 0x40100UL : 0x42100UL, 16, false, true);
        int changingRents = TrackingProbe.Rents;
        Check.That(changingRents == (Adapted ? 0 : 1000), "Even single-region misses avoid the snapshot array");
        TrackingProbe.Reset();
        tracking.VirtualMemoryEvent(0x40000, 0x3000, false, true);
        Check.That(TrackingProbe.Rents == 1 && TrackingProbe.Returns == 1, "Multi-region iteration retains a private snapshot");
        Check.That(TrackingProbe.DirtyReturns == (Adapted ? 0 : 1), "Returned snapshots release their region references");
        first.RegisterPreciseAction((address, size, write) => throw new InvalidOperationException("probe"));
        TrackingProbe.Reset();
        Check.Throws<InvalidOperationException>(() => tracking.VirtualMemoryEvent(0x40000, 0x3000, false, true),
            "Callback exceptions are not swallowed");
        Check.That(TrackingProbe.Rents == 1 && TrackingProbe.Returns == (Adapted ? 1 : 0),
            "Exceptional multi-region path returns its snapshot");
        Check.That(TrackingProbe.DirtyReturns == 0, "Exceptional snapshot is cleared before returning");
        return new { hotSearches, hotRents, changingRents, exceptionRents = TrackingProbe.Rents, exceptionReturns = TrackingProbe.Returns };
    }

    static void TopologyChurn()
    {
        MemoryTracking tracking = Create(out MemoryDouble memory, singleByte: true);
        var live = new List<(int Id, RegionHandle Handle)>();
        uint random = 0x6b1d5729;
        uint Next()
        {
            random ^= random << 13; random ^= random >> 17; random ^= random << 5;
            return random;
        }
        int nextId = 100;
        for (int step = 0; step < 2400; step++)
        {
            int operation = (int)(Next() % 8);
            ulong page = 0x80000 + (Next() % 48) * 0x1000UL;
            ulong size = ((Next() % 6) + 1) * 0x1000UL;
            if ((operation == 0 && live.Count < 40) || live.Count == 0)
            {
                int id = nextId++;
                RegionHandle handle = tracking.BeginTracking(page, size, id,
                    (id & 1) == 0 ? RegionFlags.UnalignedAccess : RegionFlags.None);
                Watch(handle, $"churn-{id}", preciseResult: (id & 2) == 0);
                live.Add((id, handle));
            }
            else if (operation == 1)
            {
                int index = (int)(Next() % live.Count);
                live[index].Handle.Dispose();
                live.RemoveAt(index);
            }
            else if (operation == 2)
            {
                memory.Unmapped.Add((page, 0x1000));
                tracking.Unmap(page, 0x1000);
            }
            else if (operation == 3)
            {
                memory.Unmapped.RemoveAll(range => range.Address == page);
                tracking.Map(page, 0x1000);
            }
            else if (operation == 4)
            {
                (int id, RegionHandle handle) = live[(int)(Next() % live.Count)];
                handle.Reprotect();
                if ((step & 3) == 0)
                    handle.RegisterAction((address, count) => Trace.Add($"preaction:{id}:{address:X}:{count:X}"));
            }
            else
            {
                bool precise = (Next() & 1) != 0, guest = (Next() & 1) != 0, write = (Next() & 1) != 0;
                int? exempt = (Next() & 3) == 0 ? live[(int)(Next() % live.Count)].Id : null;
                try { tracking.VirtualMemoryEvent(page + (Next() & 0xfff), size, write, precise, exempt, guest); }
                catch (InvalidMemoryRegionException) { Trace.Add("churn:invalid"); }
            }
            foreach ((int id, RegionHandle handle) in live)
                Trace.Add($"state:{step}:{id}:{handle.Dirty}:{handle.Unmapped}");
            if (Adapted)
            {
                foreach (bool guest in new[] { false, true })
                {
                    var cached = (VirtualRegion)Cached(tracking, guest);
                    if (cached != null)
                    {
                        var regions = (IEnumerable<VirtualRegion>)typeof(MemoryTracking).GetField(
                            guest ? "_guestVirtualRegions" : "_virtualRegions",
                            BindingFlags.NonPublic | BindingFlags.Instance).GetValue(tracking);
                        Check.That(cached.Handles.Count > 0 && regions.Contains(cached),
                            "Cached region remains live through topology churn");
                    }
                }
            }
        }
        foreach (var entry in live) entry.Handle.Dispose();
        Check.That(tracking.GetRegionCount() == 0, "Random topology churn releases all regions");
    }

    static object Benchmark()
    {
        var trace = new List<string>();
        var memory = new MemoryDouble(trace) { Record = false };
        var tracking = new MemoryTracking(memory, 0x1000);
        const int regionCount = 4096;
        var handles = new RegionHandle[regionCount];
        long signals = 0;
        for (int i = 0; i < handles.Length; i++)
        {
            handles[i] = tracking.BeginTracking(0x10000 + (ulong)i * 0x2000, 0x1000, i);
            handles[i].RegisterPreciseAction((address, size, write) => { signals++; return true; });
        }
        const int iterations = 150000;
        var measurements = new List<object>();
        foreach (string mode in new[] { "same-region", "changing-region", "multi-region" })
        {
            void Events(int count)
            {
                for (int i = 0; i < count; i++)
                {
                    int index = mode == "same-region" ? 2048 : (i * 101) & (regionCount - 2);
                    tracking.VirtualMemoryEvent(0x10000 + (ulong)index * 0x2000 + 16,
                        mode == "multi-region" ? 0x2000UL : 16UL, false, true, guest: (i & 1) != 0);
                }
            }
            Events(30000);
            var timings = new double[5];
            long allocated = 0;
            for (int repeat = 0; repeat < timings.Length; repeat++)
            {
                long bytes = GC.GetAllocatedBytesForCurrentThread();
                long start = Stopwatch.GetTimestamp();
                Events(iterations);
                timings[repeat] = Stopwatch.GetElapsedTime(start).TotalNanoseconds / iterations;
                allocated += GC.GetAllocatedBytesForCurrentThread() - bytes;
            }
            Array.Sort(timings);
            measurements.Add(new { mode, nanosecondsPerEvent = timings[2], allocatedBytes = allocated, iterations, repeats = timings.Length });
        }
        Check.That(signals == 4L * (30000 + 5L * iterations), "Benchmarks preserve all callback executions");
        foreach (RegionHandle handle in handles) handle.Dispose();
        return new { regionCount, signals, measurements };
    }

    static void Main()
    {
        if (Instrumented)
        {
            Basic(false); Basic(true); Topology(); Reentrant(); TopologyChurn();
            string digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n', Trace))));
            object ownership = ProbeOwnership();
            Console.WriteLine(JsonSerializer.Serialize(new { adapted = Adapted, checks = Check.Count, semanticTrace = digest,
                traceEvents = Trace.Count, ownership, physicalDeviceTested = false, nativeMemoryProtectionDoubled = true }));
        }
        else
        {
            object benchmark = Benchmark();
            Console.WriteLine(JsonSerializer.Serialize(new { adapted = Adapted, checks = Check.Count, benchmark,
                physicalDeviceTested = false, uninstrumentedProductionBodies = true }));
        }
    }
}

namespace Ryujinx.Common { internal static class NamespaceBoundary { } }

namespace Ryujinx.Memory
{
    // Only the native memory protection/mapping boundary is doubled.
    public interface IVirtualMemoryManager
    {
        bool IsRangeMapped(ulong address, ulong size);
        void TrackingReprotect(ulong address, ulong size, MemoryPermission permission, bool guest);
    }
}
