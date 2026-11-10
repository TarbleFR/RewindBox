using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;

// The GPU thread (ThreadedRenderer's GPU.MainThread) makes synchronous calls (a buffer read-back, BackgroundContextAction,
// GetCapabilities) while the real render thread first drains queued work, over two 5 s windows of render work.
// Argument: control or candidate. One JSON line: the GPU thread's own timing of each call and every "Render thread
// commands" line the production LogRenderWork printed.
static class Program
{
    static long Now => Stopwatch.GetTimestamp();
    static double Ms(long ticks) => Math.Round(ticks * 1000.0 / Stopwatch.Frequency, 3);

    static readonly byte[] Data = [1, 2, 3, 4];

    static void Main(string[] args)
    {
        string variant = args[0];
#if CANDIDATE
        if (variant != "candidate") throw new Exception("candidate build");
#else
        if (variant != "control") throw new Exception("control build");
#endif
        var lines = new ConcurrentQueue<string>();
        int allLines = 0;
        Logger.Updated += (_, e) =>
        {
            Interlocked.Increment(ref allLines);
            if (e.Message.Contains("Render thread commands"))
            {
                lines.Enqueue(e.Message);
            }
        };

        var backend = new Backend();
        var renderer = new ThreadedRenderer(backend);
        var report = new Dictionary<string, object> { ["variant"] = variant };
        Exception error = null;
        var done = new ManualResetEventSlim(false);
        var render = new Thread(() =>
        {
            backend.RenderThread = Thread.CurrentThread;
            try
            {
                renderer.RunLoop(() =>
                {
                    try { Scenario(renderer, backend, report, lines); }
                    catch (Exception e) { error = e; }
                    finally { done.Set(); }
                });
            }
            catch (Exception e) { error ??= e; }
        }) { IsBackground = true, Name = "render" };
        render.Start();
        if (!done.Wait(120000)) throw new Exception("scenario timed out");
        renderer.Dispose();
        if (!render.Join(10000)) throw new Exception("render loop did not exit");
        if (error != null) throw new Exception("scenario failed", error);
        report["lines"] = lines.ToArray();
        report["loggerEvents"] = Volatile.Read(ref allLines);
        report["readBacks"] = backend.ReadBacks;
        report["readBacksOffRenderThread"] = backend.ReadBacksOffRenderThread;
        Console.WriteLine(JsonSerializer.Serialize(report));
    }

    static double Timed(Action call)
    {
        long start = Now;
        call();
        return Ms(Now - start);
    }

    // Ends the current window: the first command that ends 5 s after the window began prints its line (LogRenderWork),
    // before the render thread runs the synchronous call queued behind it.
    static void EndWindow(ThreadedRenderer renderer, BufferHandle buffer, long windowStart, ConcurrentQueue<string> lines, int expected)
    {
        long due = windowStart + (long)(5.3 * Stopwatch.Frequency);
        while (Now < due)
        {
            Thread.Sleep(10);
        }

        renderer.SetBufferData(buffer, 0, Data);
        renderer.GetCapabilities();
        if (lines.Count != expected) throw new Exception("expected " + expected + " render work lines, saw " + lines.Count);
    }

    static void Scenario(ThreadedRenderer renderer, Backend backend, Dictionary<string, object> report, ConcurrentQueue<string> lines)
    {
        if (Thread.CurrentThread.Name != "GPU.MainThread") throw new Exception("not the GPU thread");
        long first = Now;
        BufferHandle buffer = renderer.CreateBuffer(64, BufferAccess.Default);
        double warmUp = Timed(() => renderer.GetCapabilities());

        // A: a read-back (200 ms on the render thread) queued behind 300 ms of render work.
        backend.BusyMs = 300;
        backend.ReadBackMs = 200;
        double readBackBehindWork = Timed(() =>
        {
            renderer.SetBufferData(buffer, 0, Data);
            renderer.GetBufferData(buffer, 0, 4).Dispose();
        });
        backend.ReadBackMs = 0;

        // B: an empty synchronous action (the counter-report sync) behind 250 ms of render work.
        backend.BusyMs = 250;
        double emptyActionBehindWork = Timed(() =>
        {
            renderer.SetBufferData(buffer, 0, Data);
            renderer.BackgroundContextAction(static () => { });
        });
        backend.BusyMs = 0;

        // C: an action that itself takes 150 ms on the render thread, nothing queued ahead.
        double busyAction = Timed(() => renderer.BackgroundContextAction(static () => Backend.Spin(150)));

        EndWindow(renderer, buffer, first, lines, 1);
        long second = Now;

        // D, next window: a 50 ms read-back alone (the first window's counts were cleared).
        backend.ReadBackMs = 50;
        double readBackAlone = Timed(() => renderer.GetBufferData(buffer, 0, 4).Dispose());
        backend.ReadBackMs = 0;

        EndWindow(renderer, buffer, second, lines, 2);

        report["calls"] = new Dictionary<string, object>
        {
            ["warmUpGetCapabilitiesMs"] = warmUp,
            ["readBackBehindWorkMs"] = readBackBehindWork,
            ["emptyActionBehindWorkMs"] = emptyActionBehindWork,
            ["busyActionMs"] = busyAction,
            ["readBackAloneMs"] = readBackAlone,
        };
    }
}
