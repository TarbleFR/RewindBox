using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;

// The GPU thread (ThreadedRenderer's GPU.MainThread) makes synchronous calls (a buffer read-back, BackgroundContextAction,
// GetCapabilities) while the real render thread first drains queued work, over two 5 s windows of render work.
// Argument: control, candidate or final. One JSON line: the GPU thread's own timing of each call and every "Render thread
// commands" line the production LogRenderWork printed. Plan 748 ranks 14 and 17 (every variant, asserted on the final
// source): where the command queue lives and whether a compacting collection moves it; what NoteRenderCommand returns
// and whether the times it adds telescope when its return value is the next start.
static class Program
{
    static long Now => Stopwatch.GetTimestamp();
    static double Ms(long ticks) => Math.Round(ticks * 1000.0 / Stopwatch.Frequency, 3);

    static readonly byte[] Data = [1, 2, 3, 4];

    static void Main(string[] args)
    {
        string variant = args[0];
#if FINAL
        if (variant != "final") throw new Exception("final build");
#elif CANDIDATE
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
        // Plan 748 rank 17 (adapt_pinned_command_queue): a large array allocated just before the renderer's command queue
        // and dropped leaves a hole in front of it; a compacting full collection (large objects included) then moves a
        // movable queue, never a pinned one.
        byte[] hole = new byte[4 << 20];
        var renderer = new ThreadedRenderer(backend);
        GC.KeepAlive(hole);
        hole = null;
        var report = new Dictionary<string, object> { ["variant"] = variant, ["queue"] = Queue(renderer) };
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
        report["note"] = Note();
        Console.WriteLine(JsonSerializer.Serialize(report));
    }

    static T Field<T>(ThreadedRenderer renderer, string name) =>
        (T)typeof(ThreadedRenderer).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance).GetValue(renderer);

    // Where the command queue lives: its address before and after a compacting full collection, the pinned object heap's
    // size after it, and whether the queue is zeroed before any command.
    static Dictionary<string, object> Queue(ThreadedRenderer renderer)
    {
        byte[] queue = Field<byte[]>(renderer, "_commandQueue");
        long before = Marshal.UnsafeAddrOfPinnedArrayElement(queue, 0).ToInt64();
        GCSettings.LargeObjectHeapCompactionMode = GCLargeObjectHeapCompactionMode.CompactOnce;
        GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
        long after = Marshal.UnsafeAddrOfPinnedArrayElement(queue, 0).ToInt64();
        GCMemoryInfo info = GC.GetGCMemoryInfo(GCKind.Any);
        return new Dictionary<string, object>
        {
            ["bytes"] = queue.Length,
            ["moved"] = before != after,
            ["pinnedHeapBytes"] = info.GenerationInfo.Length > 4 ? info.GenerationInfo[4].SizeAfterBytes : -1,
            ["zeroed"] = queue.All(b => b == 0),
        };
    }

    // NoteRenderCommand of a renderer that runs no loop: what it returns and, when it returns a time, whether 1 000
    // commands chained on it add exactly the time from the first start to the last return; then a window closed 5 s
    // ago: its line is written and the start returned is read after it (no command is charged with the line).
    static Dictionary<string, object> Note()
    {
        var renderer = new ThreadedRenderer(new Backend());
        MethodInfo note = typeof(ThreadedRenderer).GetMethod("NoteRenderCommand", BindingFlags.NonPublic | BindingFlags.Instance);
        var result = new Dictionary<string, object> { ["returns"] = note.ReturnType.Name };
        if (note.ReturnType != typeof(long))
        {
            return result;
        }
        long first = Stopwatch.GetTimestamp(), start = first;
        for (int i = 0; i < 1000; i++)
        {
            long next = (long)note.Invoke(renderer, new object[] { (byte)1, start });
            if (next < start) throw new Exception("NoteRenderCommand returned a time before the command's start");
            start = next;
        }
        long[] ticks = Field<long[]>(renderer, "_renderWorkTicks");
        long[] calls = Field<long[]>(renderer, "_renderWorkCalls");
        result["calls"] = calls[1];
        result["telescoped"] = ticks.Sum() == start - first;
        int lines = 0;
        EventHandler<LogEventArgs> count = (_, e) => { if (e.Message.Contains("Render thread commands")) Interlocked.Increment(ref lines); };
        Logger.Updated += count;
        typeof(ThreadedRenderer).GetField("_renderWorkStart", BindingFlags.NonPublic | BindingFlags.Instance)
            .SetValue(renderer, Stopwatch.GetTimestamp() - 6 * Stopwatch.Frequency);
        long returned = (long)note.Invoke(renderer, new object[] { (byte)1, Stopwatch.GetTimestamp() });
        Logger.Updated -= count;
        long windowStart = Field<long>(renderer, "_renderWorkStart");
        result["windowLines"] = Volatile.Read(ref lines);
        result["startAfterLine"] = returned >= windowStart && Field<long[]>(renderer, "_renderWorkTicks").Sum() == 0;
        return result;
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
