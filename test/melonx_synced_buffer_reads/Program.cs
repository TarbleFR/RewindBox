using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;

// The GPU thread (ThreadedRenderer's GPU.MainThread) reads a buffer after the sync of its writes, as Buffer.FlushImpl
// does after BufferModifiedRangeList.WaitForAndFlushRanges: control calls GetBufferData (the Core 699 call), candidate
// GetBufferDataAfterSync (adapt_synced_buffer_reads). The render thread first runs queued work. Argument: control or
// candidate. One JSON line.
static class Program
{
    static long Now => Stopwatch.GetTimestamp();
    static double Ms(long ticks) => Math.Round(ticks * 1000.0 / Stopwatch.Frequency, 3);

    static byte[] Pattern(byte value) => Enumerable.Repeat(value, 64).ToArray();

    static byte[] Read(ThreadedRenderer renderer, BufferHandle buffer)
    {
#if CANDIDATE
        using PinnedSpan<byte> data = ((IRenderer)renderer).GetBufferDataAfterSync(buffer, 0, 64);
#else
        using PinnedSpan<byte> data = renderer.GetBufferData(buffer, 0, 64);
#endif
        return data.Get().ToArray();
    }

    static string Value(byte[] data) => data.All(b => b == data[0]) ? data[0].ToString() : "mixed";

    static (double Ms, string Value) Timed(Func<byte[]> read)
    {
        long start = Now;
        byte[] data = read();
        return (Ms(Now - start), Value(data));
    }

    static ulong _sync;

    // The writes queued so far have run once their sync is waited for (ThreadedRenderer.WaitSync).
    static void Sync(ThreadedRenderer renderer)
    {
        ulong id = ++_sync;
        renderer.CreateSync(id, true);
        renderer.WaitSync(id);
    }

    static void Session(Action<ThreadedRenderer, Backend> gpu, out Exception error, out Exception loop)
    {
        var backend = new Backend();
        var renderer = new ThreadedRenderer(backend);
        Exception gpuError = null, loopError = null;
        var done = new ManualResetEventSlim(false);
        var render = new Thread(() =>
        {
            backend.RenderThread = Thread.CurrentThread;
            try
            {
                renderer.RunLoop(() =>
                {
                    try { gpu(renderer, backend); }
                    catch (Exception e) { gpuError = e; }
                    finally { done.Set(); }
                });
            }
            catch (Exception e) { loopError = e; }
        }) { IsBackground = true, Name = "render" };
        render.Start();
        if (!done.Wait(60000)) throw new Exception("scenario timed out (blocked)");
        try { renderer.Dispose(); } catch (Exception e) { loopError ??= e; }
        if (!render.Join(10000)) throw new Exception("render loop did not exit");
        error = gpuError;
        loop = loopError;
    }

    static void Main(string[] args)
    {
        string variant = args[0];
#if CANDIDATE
        if (variant != "candidate") throw new Exception("candidate build");
#else
        if (variant != "control") throw new Exception("control build");
#endif
        var report = new Dictionary<string, object> { ["variant"] = variant };

        Session((renderer, backend) =>
        {
            if (Thread.CurrentThread.Name != "GPU.MainThread") throw new Exception("not the GPU thread");
            BufferHandle busy = renderer.CreateBuffer(16, BufferAccess.Default);
            BufferHandle x = renderer.CreateBuffer(64, BufferAccess.Default);
            renderer.SetBufferData(x, 0, Pattern(1));
            Sync(renderer);

            // No work queued.
            var noWork = Timed(() => Read(renderer, x));

            // A: a read behind 300 ms of queued work.
            backend.BusyMs = 300;
            renderer.SetBufferData(busy, 0, new byte[4]);
            var behindWork = Timed(() => Read(renderer, x));
            Sync(renderer);

            // B: 20 successive reads, each behind 20 ms of queued work.
            backend.BusyMs = 20;
            int readsBefore = backend.ReadBacks, offBefore = backend.ReadBacksOffRenderThread;
            long start = Now;
            double longest = 0;
            var values = new List<string>();
            for (int i = 0; i < 20; i++)
            {
                renderer.SetBufferData(busy, 0, new byte[4]);
                var r = Timed(() => Read(renderer, x));
                longest = Math.Max(longest, r.Ms);
                values.Add(r.Value);
            }
            double repeatedMs = Ms(Now - start);
            int repeatedReads = backend.ReadBacks - readsBefore, repeatedOff = backend.ReadBacksOffRenderThread - offBefore;
            Sync(renderer);

            // C: read after write: a write behind 200 ms of work, its sync waited for, then read.
            backend.BusyMs = 200;
            renderer.SetBufferData(busy, 0, new byte[4]);
            renderer.SetBufferData(x, 0, Pattern(2));
            Sync(renderer);
            var afterWrite = Timed(() => Read(renderer, x));
            // A later write queued behind 200 ms of work, not synced: the read returns the synced state or, after
            // draining, the later one, never a mix.
            renderer.SetBufferData(busy, 0, new byte[4]);
            renderer.SetBufferData(x, 0, Pattern(3));
            var unsyncedLater = Timed(() => Read(renderer, x));
            Sync(renderer);
            var afterLaterSync = Timed(() => Read(renderer, x));

            // D: a buffer still being created (queued behind 300 ms): the read waits for it, never reads a missing one.
            backend.BusyMs = 300;
            renderer.SetBufferData(busy, 0, new byte[4]);
            BufferHandle y = renderer.CreateBuffer(64, BufferAccess.Default);
            var inFlight = Timed(() => Read(renderer, y));
            Sync(renderer);
            backend.BusyMs = 0;

            // F: the whole path, from the necessary wait to usable bytes: writes, their sync, then 300 ms of later work queued
            // behind the sync (the next commands), then WaitSync and the read; then the time until the next sync, which needs
            // that later work (so a gain there would only be the GPU thread's own work done meanwhile, not measured here).
            backend.BusyMs = 300;
            renderer.SetBufferData(x, 0, Pattern(4));
            ulong waited = ++_sync;
            renderer.CreateSync(waited, true);
            renderer.SetBufferData(busy, 0, new byte[4]);
            long pathStart = Now;
            renderer.WaitSync(waited);
            double necessaryWaitMs = Ms(Now - pathStart);
            byte[] usable = Read(renderer, x);
            double toUsableBytesMs = Ms(Now - pathStart);
            Sync(renderer);
            double toNextSyncMs = Ms(Now - pathStart);
            backend.BusyMs = 0;

            // G: concurrent reads: a guest-like thread reads the same synced buffer through GetBufferData (its direct branch)
            // while the GPU thread reads it after the sync and queues work for the render thread.
            int concurrentBad = 0, concurrentReads = 0;
            var guest = new Thread(() =>
            {
                for (int i = 0; i < 200; i++)
                {
                    using PinnedSpan<byte> data = renderer.GetBufferData(x, 0, 64);
                    if (Value(data.Get().ToArray()) != "4") Interlocked.Increment(ref concurrentBad);
                    Interlocked.Increment(ref concurrentReads);
                }
            }) { Name = "guest" };
            backend.BusyMs = 1;
            guest.Start();
            for (int i = 0; i < 200; i++)
            {
                renderer.SetBufferData(busy, 0, new byte[4]);
                if (Value(Read(renderer, x)) != "4") Interlocked.Increment(ref concurrentBad);
                Interlocked.Increment(ref concurrentReads);
            }
            guest.Join();
            Sync(renderer);
            backend.BusyMs = 0;

            report["calls"] = new Dictionary<string, object>
            {
                ["necessaryWaitMs"] = necessaryWaitMs, ["toUsableBytesMs"] = toUsableBytesMs, ["toNextSyncMs"] = toNextSyncMs,
                ["usableValue"] = Value(usable), ["concurrentReads"] = concurrentReads, ["concurrentBad"] = concurrentBad,
                ["noWorkMs"] = noWork.Ms, ["noWorkValue"] = noWork.Value,
                ["behindWorkMs"] = behindWork.Ms, ["behindWorkValue"] = behindWork.Value,
                ["repeatedMs"] = repeatedMs, ["repeatedLongestMs"] = longest, ["repeatedValues"] = values.Distinct().ToArray(),
                ["repeatedReads"] = repeatedReads, ["repeatedReadsOffRenderThread"] = repeatedOff,
                ["afterWriteMs"] = afterWrite.Ms, ["afterWriteValue"] = afterWrite.Value,
                ["unsyncedLaterMs"] = unsyncedLater.Ms, ["unsyncedLaterValue"] = unsyncedLater.Value,
                ["afterLaterSyncValue"] = afterLaterSync.Value,
                ["inFlightMs"] = inFlight.Ms, ["inFlightValue"] = inFlight.Value,
                ["readsOfMissingBuffers"] = backend.ReadsOfMissingBuffers,
            };
        }, out Exception error, out Exception loop);
        if (error != null) throw new Exception("scenario failed", error);
        report["loopError"] = loop?.GetType().Name;

        // E: the renderer fails (a queued command throws on the render thread): a read after it fails, it does not block.
        string failure = null;
        double failureMs = -1;
        Session((renderer, backend) =>
        {
            BufferHandle busy = renderer.CreateBuffer(16, BufferAccess.Default);
            BufferHandle x = renderer.CreateBuffer(64, BufferAccess.Default);
            renderer.SetBufferData(x, 0, Pattern(1));
            Sync(renderer);
            backend.FailNextWrite = true;
            renderer.SetBufferData(x, 0, Pattern(9));
            Thread.Sleep(300);
            long start = Now;
            try { Read(renderer, x); failure = "none"; }
            catch (Exception e) { failure = e.GetType().Name + ": " + e.Message; }
            failureMs = Ms(Now - start);
        }, out Exception failedError, out Exception failedLoop);
        report["failure"] = new Dictionary<string, object>
        {
            ["readOutcome"] = failure, ["readMs"] = failureMs, ["scenarioError"] = failedError?.Message,
            ["loopError"] = failedLoop?.Message,
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
