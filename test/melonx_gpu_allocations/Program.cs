using Ryujinx.Common.Memory;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Engine.GPFifo;
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading.Tasks;

static class Program
{
    static int _checks;

    static void Check(bool value, string message)
    {
        _checks++;
        if (!value) throw new Exception(message);
    }

    static long UploadRoundtrip()
    {
        var owners = new MemoryOwner<byte>[8];
        for (int round = 0; round < 20; round++) Round();
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int round = 0; round < 2000; round++) Round();
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        Check(allocated <= 64L * 8 * 2000, $"pooled upload bookkeeping allocated {allocated} bytes");
        return allocated;

        void Round()
        {
            for (int i = 0; i < owners.Length; i++)
            {
                owners[i] = MemoryOwner<byte>.Rent(128 * 1024);
                owners[i].Span[0] = (byte)i;
            }
            for (int i = 0; i < owners.Length; i++)
            {
                if (owners[i].Span[0] != (byte)i) throw new Exception("live upload arrays alias");
                owners[i].Dispose();
                owners[i].Dispose();
            }
        }
    }

    static void Owners()
    {
        using (var a = MemoryOwner<int>.RentCopy(new[] { 1, 2, 3, 4 }))
        {
            Check(a.Length == 4 && a.Span.SequenceEqual(new[] { 1, 2, 3, 4 }), "copy/length");
            a.Memory.Span[3] = 7;
            Check(a.Span[3] == 7, "Memory and Span share the lease");
        }
        using (var a = MemoryOwner<int>.RentCleared(3))
            Check(a.Span.SequenceEqual(new int[3]), "cleared logical range");
        var disposed = MemoryOwner<int>.Rent(16);
        disposed.Dispose();
        disposed.Dispose();
        bool threw = false;
        try { _ = disposed.Span; } catch (ObjectDisposedException) { threw = true; }
        Check(threw, "disposed access throws");

        Parallel.For(0, 4, worker =>
        {
            for (int i = 0; i < 500; i++)
            {
                using var a = MemoryOwner<int>.Rent(32768 + worker);
                a.Span.Fill(worker);
                if (a.Span[0] != worker || a.Span[^1] != worker) throw new Exception("concurrent lease alias");
            }
        });
        Check(true, "concurrent ownership");

        var budget = new MemoryOwner<long>[140];
        for (int i = 0; i < budget.Length; i++) budget[i] = MemoryOwner<long>.Rent(65536);
        foreach (var item in budget) item.Dispose();
        Type pool = typeof(MemoryOwner<long>).GetNestedType("ArrayPooling", BindingFlags.NonPublic)!
            .MakeGenericType(typeof(long));
        const BindingFlags fields = BindingFlags.NonPublic | BindingFlags.Static;
        long spareBytes = (long)pool.GetField("_spareBytes", fields)!.GetValue(null)!;
        Check(spareBytes > 0 && spareBytes <= 64L * 1024 * 1024, "spare byte budget");
        using var live = MemoryOwner<long>.Rent(65536);
        live.Span.Fill(777);
        // Advance only the timestamps of idle entries; exercise the actual production timer callback.
        var spares = (System.Collections.IEnumerable)pool.GetField("_spares", fields)!.GetValue(null)!;
        foreach (var spare in spares)
            spare!.GetType().GetField("Returned")!.SetValue(spare, Environment.TickCount64 - 4000);
        pool.GetMethod("ReleaseIdleSpares", fields)!.Invoke(null, new object?[] { null });
        Check((long)pool.GetField("_spareBytes", fields)!.GetValue(null)! == 0, "idle spares released");
        Check(live.Span[0] == 777 && live.Span[^1] == 777, "idle trim preserves the leased array");
    }

    static void Fifo()
    {
        void Scenario(bool failDirty, bool failProcess, bool interrupt)
        {
            var context = new GpuContext();
            var fifo = new GPFifoDevice(context);
            var processor = new GPFifoProcessor { FailDirty = failDirty, FailProcess = failProcess };
            int rents = TrackingPool.Shared.Rents;
            int returns = TrackingPool.Shared.Returns;
            fifo.PushEntries(processor, new[] { 3UL << 8, 3UL << 8 });
            Check(TrackingPool.Shared.Rents == rents + 2, "two prefetched buffers rented");
            if (interrupt) fifo.Interrupt();
            bool threw = false;
            try { fifo.DispatchCalls(); } catch (InvalidOperationException) { threw = true; }
            Check(threw == (!interrupt && (failDirty || failProcess)), "original processing error propagated");
            fifo.Dispose();
            Check(TrackingPool.Shared.Returns == returns + 2, "all FIFO buffers returned once after error/stop");
            if (!failDirty && !failProcess && !interrupt)
                Check(processor.Calls == 2 && processor.LastWords!.AsSpan().SequenceEqual(new[] { 11, 22, 33 }), "logical word count/content");
        }
        Scenario(false, false, false);
        Scenario(true, false, false);
        Scenario(false, true, false);
        Scenario(false, false, true);

        using var host = new GPFifoDevice(new GpuContext());
        var processor = new GPFifoProcessor();
        int before = TrackingPool.Shared.Returns;
        host.PushHostCommandBuffer(processor, new[] { 5, 6 });
        host.DispatchCalls();
        Check(TrackingPool.Shared.Returns == before && processor.LastWords!.Length == 2, "host-owned words never returned");

        using var lazy = new GPFifoDevice(new GpuContext());
        int rentsBefore = TrackingPool.Shared.Rents;
        lazy.PushEntries(new GPFifoProcessor(), new[] { (3UL << 8) | 1, 3UL << 8 });
        lazy.DispatchCalls();
        Check(TrackingPool.Shared.Rents == rentsBefore, "barrier keeps subsequent command fetches lazy");
    }

    static void Main()
    {
        Owners();
        long allocated = UploadRoundtrip();
        Fifo();
        Console.WriteLine(JsonSerializer.Serialize(new { passed = true, checks = _checks,
            uploadOperations = 16000, allocatedBytes = allocated, bytesPerUpload = allocated / 16000.0,
            fifoRents = TrackingPool.Shared.Rents, fifoReturns = TrackingPool.Shared.Returns }));
    }
}
