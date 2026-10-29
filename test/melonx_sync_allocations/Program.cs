using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;
using Ryujinx.Common.Logging;

static class Program
{
    static int Checks, Cases;
    static long Sink;
    static readonly StringBuilder Trace = new();
    static void Check(bool value, string message) { Checks++; if (!value) throw new Exception(message); }
    static int Pending(SyncManager sync) => ((ICollection)typeof(SyncManager).GetField("_handles", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(sync)).Count;
    static (SyncManager sync, VulkanRenderer gd) Manager(bool register = true)
    {
        var gd = new VulkanRenderer(); var sync = new SyncManager(gd, default);
        gd.InterruptAction = action => action();
        if (register) gd.OnFlush = sync.RegisterFlush;
        return (sync, gd);
    }
    static void Functional()
    {
        foreach (bool strict in new[] { false, true })
        foreach (bool interrupt in new[] { false, true })
        {
            var (sync, gd) = Manager();
            if (!interrupt) gd.InterruptAction = null;
            sync.Create(1, strict);
            var first = gd.CommandBufferPool.Added[0];
            Check(gd.CommandBufferPool.Strict == (strict || !interrupt ? 1 : 0), "Strict creation changed");
            Check(gd.CommandBufferPool.Relaxed == (!strict && interrupt ? 1 : 0), "Relaxed creation changed");
            first.Signaled = true;
            Check(sync.GetCurrent() == 1, "Signaled handle not reported");
            if (interrupt) sync.Wait(1);
            sync.RegisterFlush(); int before = MultiFenceHolder.FencePool.Returns;
            sync.Cleanup(); sync.Cleanup();
            Check(Pending(sync) == 0 && MultiFenceHolder.FencePool.Returns == before + 1, "Retirement/pool return changed");
            sync.Wait(0); sync.Wait(1); sync.Wait(123456);
            Trace.Append(gd.CommandBufferPool.Strict).Append(':').Append(gd.CommandBufferPool.Relaxed).Append(';'); Cases++;
        }
        // Keep a later completed handle behind the incomplete head. Retirement
        // must stop at the head, while GetCurrent preserves its existing scan.
        {
            var (sync, gd) = Manager();
            sync.Create(10, false); sync.Create(20, false); sync.RegisterFlush();
            gd.CommandBufferPool.Added[1].Signaled = true;
            Check(sync.GetCurrent() == 20, "Current ID scan order changed");
            sync.Cleanup(); Check(Pending(sync) == 2, "Cleanup passed an incomplete head");
            gd.CommandBufferPool.Added[0].Signaled = true;
            sync.Cleanup(); Check(Pending(sync) == 0 && sync.GetCurrent() == 21, "Head retirement result changed"); Cases++;
        }
        // Delayed interrupts retain their own handle and recheck flush state.
        foreach (bool flushBeforeCallback in new[] { false, true })
        {
            var (sync, gd) = Manager(); var actions = new List<Action>();
            gd.InterruptAction = actions.Add;
            sync.Create(31, false); sync.Wait(31);
            Check(actions.Count == 1, "Missing interrupt for unsubmitted sync");
            if (flushBeforeCallback) sync.RegisterFlush();
            int before = gd.Flushes; actions[0]();
            Check(gd.Flushes == before + (flushBeforeCallback ? 0 : 1), "Delayed callback did not recheck flush");
            gd.CommandBufferPool.Added[0].Signaled = true;
            sync.Wait(31); sync.Cleanup(); Check(Pending(sync) == 0, "Delayed wait did not retire"); Cases++;
        }
        // Repeated wrap/grow/dequeue cycles preserve FIFO ID and release count.
        {
            var (sync, gd) = Manager(); ulong id = 1; int returned = MultiFenceHolder.FencePool.Returns;
            for (int batch = 0; batch < 200; batch++)
            {
                int count = 1 + batch % 97;
                for (int i = 0; i < count; i++) { sync.Create(id++, false); gd.CommandBufferPool.Added[^1].Signaled = true; }
                sync.RegisterFlush(); sync.Cleanup();
                returned += count;
                Check(Pending(sync) == 0 && sync.GetCurrent() == id && MultiFenceHolder.FencePool.Returns == returned, "FIFO wrap/grow lifecycle changed");
                gd.CommandBufferPool.Added.Clear(); Trace.Append(id).Append(';'); Cases++;
            }
        }
        // Independent waiters contend with cleanup using the production locks.
        {
            var (sync, gd) = Manager();
            for (ulong i = 1; i <= 512; i++) { sync.Create(i, false); gd.CommandBufferPool.Added[^1].Signaled = true; }
            sync.RegisterFlush();
            Parallel.Invoke(() => { for (ulong i = 1; i <= 512; i++) sync.Wait(i); },
                () => { for (int i = 0; i < 256; i++) sync.GetCurrent(); }, () => sync.Cleanup());
            sync.Cleanup(); Check(Pending(sync) == 0 && sync.GetCurrent() == 513, "Concurrent wait/cleanup lost a handle"); Cases++;
        }
        // A fence error still propagates and leaves the same pending handle.
        {
            var (sync, gd) = Manager(); sync.Create(7, false); sync.RegisterFlush();
            gd.CommandBufferPool.Added[0].OnWait = () => throw new InvalidOperationException("native boundary");
            try { sync.Wait(7); throw new Exception("Lost fence error"); } catch (InvalidOperationException) { }
            Check(Pending(sync) == 1, "Fence failure retired a live handle");
            gd.CommandBufferPool.Added[0].OnWait = null; gd.CommandBufferPool.Added[0].Signaled = true;
            sync.Cleanup(); Check(Pending(sync) == 0, "Fence error left a lock held"); Cases++;
        }
    }
    static void BitmapCases()
    {
        var random = new Random(918431);
        foreach (int size in new[] { 1, 31, 4096, 10001, 131072 })
        foreach (int granularity in new[] { 16, 4096 })
        {
            var bitmap = new BufferUsageBitmap(size, granularity);
            int pages = (size + granularity - 1) / granularity;
            bool[,,] oracle = new bool[16, 2, pages];
            for (int iteration = 0; iteration < 20000; iteration++)
            {
                int cb = random.Next(16), offset = random.Next(size), length = random.Next(size - offset + 1);
                bool write = random.Next(2) == 0;
                int op = random.Next(5);
                if (op == 0)
                {
                    bitmap.Clear(cb);
                    for (int k = 0; k < 2; k++) for (int p = 0; p < pages; p++) oracle[cb, k, p] = false;
                }
                else if (op == 1)
                {
                    bitmap.Add(cb, offset, length, write);
                    if (length != 0) for (int p = offset / granularity; p <= (offset + length - 1) / granularity; p++) oracle[cb, write ? 1 : 0, p] = true;
                }
                else
                {
                    bool expected = false;
                    if (length != 0) for (int slot = 0; slot < 16; slot++)
                        for (int p = offset / granularity; p <= (offset + length - 1) / granularity; p++) expected |= oracle[slot, write ? 1 : 0, p];
                    bool actual = bitmap.OverlapsWith(offset, length, write);
                    Check(actual == expected, "Bitmap hazard differs from independent page oracle");
                    Trace.Append(actual ? '1' : '0');
                }
            }
            foreach (int offset in new[] { -4096, -1, 0, size, int.MaxValue })
            foreach (int length in new[] { 0, -1, 1, 4096, int.MaxValue })
            foreach (bool write in new[] { false, true })
            {
                try { Trace.Append(bitmap.OverlapsWith(offset, length, write)); }
                catch (Exception error) { Trace.Append(error.GetType().Name); }
            }
            Cases++;
        }
    }
    static object[] Allocations()
    {
        List<object> reports = new();
        foreach (string mode in new[] { "absent", "retired", "signaled", "interrupt" })
        {
            var (sync, gd) = Manager(mode != "interrupt");
            ulong id = 1;
            if (mode != "absent")
            {
                sync.Create(id, false); gd.CommandBufferPool.Added[0].Signaled = true;
                if (mode != "interrupt") sync.RegisterFlush();
                if (mode == "retired") sync.Cleanup();
            }
            for (int i = 0; i < 1000; i++) sync.Wait(id);
            long start = GC.GetAllocatedBytesForCurrentThread();
            const int calls = 20000;
            for (int i = 0; i < calls; i++) sync.Wait(id);
            long bytes = GC.GetAllocatedBytesForCurrentThread() - start;
            reports.Add(new { mode, calls, allocatedBytes = bytes });
        }
        return reports.ToArray();
    }
    static object[] CleanupTimings()
    {
        List<object> reports = new();
        foreach (int count in new[] { 1, 32, 256, 4096 })
        {
            double[] times = new double[7]; long bytes = 0;
            for (int sample = -1; sample < times.Length; sample++)
            {
                var (sync, gd) = Manager();
                for (ulong i = 1; i <= (ulong)count; i++) { sync.Create(i, false); gd.CommandBufferPool.Added[^1].Signaled = true; }
                sync.RegisterFlush();
                long before = GC.GetAllocatedBytesForCurrentThread(), start = Stopwatch.GetTimestamp(); sync.Cleanup();
                if (sample >= 0) { times[sample] = Stopwatch.GetElapsedTime(start).TotalNanoseconds; bytes += GC.GetAllocatedBytesForCurrentThread() - before; }
                Check(Pending(sync) == 0, "Cleanup measurement left live handles");
            }
            Array.Sort(times); reports.Add(new { count, allocatedBytes = bytes, medianNanoseconds = times[3], samplesNanoseconds = times });
        }
        return reports.ToArray();
    }
    static object[] BitmapTimings()
    {
        List<object> reports = new();
        foreach (int slot in new[] { -1, 0, 15 })
        {
            var bitmap = new BufferUsageBitmap(1 << 20, 4096);
            if (slot >= 0) bitmap.Add(slot, 4096, 4096, false);
            for (int i = 0; i < 2000; i++) Sink += bitmap.OverlapsWith(4096, 4096, false) ? 1 : 0;
            double[] times = new double[7]; long bytes = 0; const int calls = 200000;
            for (int sample = 0; sample < times.Length; sample++)
            {
                long before = GC.GetAllocatedBytesForCurrentThread(), start = Stopwatch.GetTimestamp();
                for (int i = 0; i < calls; i++) Sink += bitmap.OverlapsWith(4096, 4096, false) ? 1 : 0;
                times[sample] = Stopwatch.GetElapsedTime(start).TotalNanoseconds / calls;
                bytes += GC.GetAllocatedBytesForCurrentThread() - before;
            }
            Check(bytes == 0, "Bitmap queries allocated");
            Array.Sort(times); reports.Add(new { slot, calls, allocatedBytes = bytes, medianNanoseconds = times[3], samplesNanoseconds = times });
        }
        return reports.ToArray();
    }
    static void Main()
    {
        Functional(); BitmapCases(); var allocation = Allocations(); var cleanup = CleanupTimings(); var bitmap = BitmapTimings();
        Console.WriteLine(JsonSerializer.Serialize(new { checks = Checks, scenarios = Cases,
            functionalDigest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Trace.ToString()))),
            allocation, cleanup, bitmap, physicalDeviceTested = false, sink = Sink }));
    }
}
