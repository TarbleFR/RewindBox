// Probe of test/melonx_unblocked_sync_queries_test.py: the production SyncManager, fence holders, command buffer pool and
// GAL SyncMap of one tree (control or candidate), against the GPU model of Double.cs. Prints one JSON line.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Program
{
    static int Checks;
    static void Check(bool value, string message) { Checks++; if (!value) throw new Exception(message); }
    static double Ms(long ticks) => ticks * 1000.0 / Stopwatch.Frequency;
    static double Round(double value) => Math.Round(value, 3);

    // 1. Scripted, one thread, GPU completion on demand: every query, wait and pool count is traced. Without a reader
    // waiting meanwhile, the candidate must give the control's trace byte for byte.
    static object Scripted()
    {
        var gpu = new GpuModel(manual: true);
        var gd = new VulkanRenderer(gpu);
        SyncManager sync = gd.SyncManager;
        gd.InterruptAction = action => action();
        var random = new Random(822);
        var trace = new StringBuilder();
        var required = new Dictionary<ulong, long>();
        var flushesAt = new Dictionary<ulong, long>();
        ulong id = 0;
        int violations = 0;

        for (int step = 0; step < 6000; step++)
        {
            int op = random.Next(12);

            // The pool has 16 command buffers; renting a 17th waits for the oldest, which only CompleteNext executes here.
            while (gpu.Pending >= 12)
            {
                gpu.CompleteNext();
                trace.Append('G');
            }

            if (op <= 4)
            {
                gd.Draw(random.Next(3), 10);
            }
            else if (op <= 6)
            {
                bool strict = op == 6;
                required[id] = gpu.Recorded;
                flushesAt[id] = gd.Flushes;
                sync.Create(id, strict);
                trace.Append(strict ? 's' : 'c').Append(id).Append(';');
                id++;
            }
            else if (op == 7)
            {
                gd.FlushAllCommands();
                trace.Append('f');
            }
            else if (op == 8)
            {
                trace.Append(gpu.CompleteNext() ? 'g' : 'n');
            }
            else if (op == 9)
            {
                ulong current = sync.GetCurrent();
                trace.Append('q').Append(current).Append(';');
                violations += current > 0 && required.TryGetValue(current - 1, out long need) && need > gpu.Completed ? 1 : 0;
            }
            else if (op == 10 && id > 0)
            {
                // A reader of a sync whose work the GPU completed: returns at once in both trees.
                ulong wanted = (ulong)random.Next((int)id);

                if (gd.Flushes > flushesAt[wanted] && gpu.Pending == 0)
                {
                    sync.Wait(wanted);
                    trace.Append('w').Append(wanted).Append(';');
                }
            }
            else
            {
                sync.Cleanup();
                trace.Append('x');
            }
        }

        trace.Append("|flushes ").Append(gd.Flushes).Append(" fences ").Append(gpu.FencesCreated).Append(" submits ").Append(gpu.Submits)
            .Append(" polls ").Append(gpu.Polls).Append(" syncs ").Append(id);
        Check(violations == 0, "a query reported a sync whose work was not complete");
        Check(Logger.Error.Lines.IsEmpty, "a sync failed to signal");
        return new
        {
            digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(trace.ToString()))),
            syncs = id, flushes = gd.Flushes, submits = gpu.Submits, fencesCreated = gpu.FencesCreated, polls = gpu.Polls, violations,
        };
    }

    // 2. The convoy: a reader waits for a command buffer with 60 ms of GPU work left; meanwhile the GPU thread queries
    // the current sync, the render thread creates a sync and another reader looks up a sync completed long ago.
    static object Convoy()
    {
        var gpu = new GpuModel(manual: false);
        var gd = new VulkanRenderer(gpu);
        SyncManager sync = gd.SyncManager;
        gd.InterruptAction = action => action();

        gd.Draw(0, 100);
        sync.Create(0, true);
        sync.Wait(0);
        Check(gpu.Completed == gpu.Recorded, "first sync complete");

        gd.Draw(0, 60_000);
        long need = gpu.Recorded;
        sync.Create(1, false);
        gd.FlushAllCommands();
        long submitted = Stopwatch.GetTimestamp();
        long readerDone = 0, createTicks = 0, lookupTicks = 0;
        bool readerEarly = false;
        var queryStarted = new ManualResetEventSlim(false);

        var reader = new Thread(() =>
        {
            sync.Wait(1);
            readerEarly = gpu.Completed < need;
            readerDone = Stopwatch.GetTimestamp();
        }) { Name = "Guest reader" };
        reader.Start();

        long guard = Stopwatch.GetTimestamp() + Stopwatch.Frequency;
        while (Interlocked.Read(ref gpu.WaitsInProgress) == 0 && Stopwatch.GetTimestamp() < guard)
        {
            Thread.Yield();
        }

        Check(Interlocked.Read(ref gpu.WaitsInProgress) == 1, "the reader waits for the GPU inside SyncManager.Wait");
        Thread.Sleep(5);

        var render = new Thread(() =>
        {
            queryStarted.Wait();
            Thread.Sleep(2);
            long start = Stopwatch.GetTimestamp();
            sync.Create(2, false);
            createTicks = Stopwatch.GetTimestamp() - start;
        }) { Name = "Render thread" };
        var other = new Thread(() =>
        {
            queryStarted.Wait();
            Thread.Sleep(2);
            long start = Stopwatch.GetTimestamp();
            sync.Wait(0);
            lookupTicks = Stopwatch.GetTimestamp() - start;
        }) { Name = "Other reader" };
        render.Start();
        other.Start();

        long queryStart = Stopwatch.GetTimestamp();
        queryStarted.Set();
        ulong during = sync.GetCurrent();
        long queryTicks = Stopwatch.GetTimestamp() - queryStart;
        bool readerStillWaiting = readerDone == 0;
        reader.Join();
        render.Join();
        other.Join();
        ulong after = sync.GetCurrent();
        double gpuLeft = Ms(readerDone - queryStart);
        gpu.Stop();

        Check(!readerEarly, "the reader returned before its command buffer completed");
        Check(Logger.Error.Lines.IsEmpty, "a sync failed to signal");
        return new
        {
            queryMs = Round(Ms(queryTicks)), createMs = Round(Ms(createTicks)), signalledLookupMs = Round(Ms(lookupTicks)),
            readerWaitMs = Round(Ms(readerDone - submitted)), gpuWorkLeftAtQueryMs = Round(gpuLeft), readerStillWaitingAfterQuery = readerStillWaiting,
            currentDuring = during, currentAfter = after,
        };
    }

    // 3. The journal (candidate): known waits from three kinds of thread, queries, and one wait for a sync the render
    // thread had not created yet, over one 5 s window.
    static object Journal()
    {
#if CANDIDATE
        var gpu = new GpuModel(manual: true);
        var gd = new VulkanRenderer(gpu);
        SyncManager sync = gd.SyncManager;
        gd.InterruptAction = action => action();
        while (Logger.Warning.Lines.TryDequeue(out _)) { }
        SyncAvailabilityWaits.Take(out _, out _, out _);
        sync.Cleanup(); // opens the window on this (render) thread
        gd.Draw(0, 10);
        sync.Create(0, true);
        Check(gpu.CompleteNext(), "submitted");
        gd.Draw(0, 10);
        sync.Create(1, false); // waited before its command buffer is submitted: the waiter has it submitted
        var completer = new Thread(() => { while (gpu.Pending == 0) Thread.Yield(); gpu.CompleteNext(); });
        completer.Start();
        sync.Wait(1);
        completer.Join();
        sync.Wait(0);
        sync.Wait(0);
        var gpuThread = new Thread(() => { sync.Wait(0); sync.Wait(1); }) { Name = "GPU.MainThread" };
        var guest = new Thread(() => sync.Wait(0)) { Name = "Guest" };
        gpuThread.Start(); gpuThread.Join(); guest.Start(); guest.Join();

        for (int i = 0; i < 4; i++)
        {
            sync.GetCurrent();
        }

        var map = new SyncMap(new ThreadedRenderer());
        map.CreateSyncHandle(9);
        map.CreateSyncHandle(10);
        var lagged = new Thread(() => map.WaitSyncAvailability(9));
        lagged.Start();
        Thread.Sleep(30);
        map.AssignSync(9);
        lagged.Join();
        map.AssignSync(10);
        map.WaitSyncAvailability(10); // created already: not counted
        Check(Logger.Warning.Lines.IsEmpty, "no journal line before 5 s");
        Thread.Sleep(5050);
        sync.Cleanup();
        Check(Logger.Warning.Lines.Count == 1, "one journal line after 5 s");
        Logger.Warning.Lines.TryDequeue(out string line);
        sync.Cleanup();
        Check(Logger.Warning.Lines.IsEmpty, "the next window starts again");
        return new { line };
#else
        return null;
#endif
    }

    // 4. The command stream shaped like the IPA 822 Hogwarts Legacy window (scaled to a quarter of the draws, each four
    // times longer): per frame 400 draws over 25 framebuffers, 18 host syncs (4 strict, 14 waiting for the command
    // buffer), one present; GPU 19.2 ms, render thread 12 ms plus 10.4 us of submission per draw, GPU thread 16 ms. The
    // guest submits a frame once the GPU thread has processed the previous one (a syncpoint), reads back GPU-written data
    // of the frame's 8th sync (WaitSync), then computes 12 ms. Another guest thread reads GPU-written memory every 2 ms
    // (WaitSync of the sync four before the last created). With migrations pending (queries), the GPU thread asks the
    // current sync before each sync it creates, as GpuContext.CreateHostSyncIfNeeded does.
    sealed class Command { public int Kind; public int Framebuffer; public ulong Id; public bool Strict; }

    static object Stream(string label, bool queries, int frames, int draws, int framebuffers, int syncsPerFrame, int strictEvery,
        int readbackSync, double gpuMicros, double renderMicros, double gpuThreadMicros, double guestMillis, bool readers)
    {
        var gpu = new GpuModel(manual: false) { EncodeMicrosPerItem = 10.4 };
        var gd = new VulkanRenderer(gpu);
        SyncManager sync = gd.SyncManager;
        var map = new SyncMap(new ThreadedRenderer());
        var queue = new ConcurrentQueue<Command>();
        var work = new AutoResetEvent(false);
        var interruptDone = new AutoResetEvent(false);
        object interruptLock = new();
        Action pending = null;
        Thread renderThread = null;
        bool running = true;
        var required = new ConcurrentDictionary<ulong, long>();
        long violations = 0, nonStrictCreateTicks = 0, nonStrictCreateMax = 0, nonStrictCreates = 0, cleanupTicks = 0, queryTicks = 0, queryMax = 0, queryCalls = 0;
        long readerWaits = 0, readerTicks = 0, readerMax = 0, readbackTicks = 0;
        long lastAssigned = -1;
        long processedFrame = -1;
        var frameProcessed = new AutoResetEvent(false);
        var readbackIds = new long[frames];
        Array.Fill(readbackIds, -1);
        var fifo = new BlockingCollection<int>();
        var readbackReady = new AutoResetEvent(false);
        int lastFramebuffer = -1;
        var frameStarts = new long[frames];

        gd.InterruptAction = action =>
        {
            if (Thread.CurrentThread == renderThread)
            {
                action();
                return;
            }

            lock (interruptLock)
            {
                Volatile.Write(ref pending, action);
                work.Set();
                interruptDone.WaitOne();
            }
        };

        void RunInterrupt()
        {
            Action action = Interlocked.Exchange(ref pending, null);

            if (action != null)
            {
                action();
                interruptDone.Set();
            }
        }

        void Run(Command command)
        {
            switch (command.Kind)
            {
                case 0:
                    // AutoFlushCounter.ShouldFlushAttachmentChange with the 6 ms pacing (adapt_paced_strict_syncs).
                    if (command.Framebuffer != lastFramebuffer)
                    {
                        lastFramebuffer = command.Framebuffer;

                        if (gd.DrawsSinceFlush >= 10 && Stopwatch.GetTimestamp() - gd.LastFlushTicks > Stopwatch.Frequency * 6 / 1000)
                        {
                            RenderStageTimer.NextSubmitCause = RenderStageTimer.SubmitCause.AttachmentAutoFlush;
                            gd.FlushAllCommands();
                        }
                    }

                    gd.Draw(command.Framebuffer, gpuMicros);
                    Spin.For(renderMicros);
                    break;
                case 1:
                    required[command.Id] = gpu.Recorded;
                    long start = Stopwatch.GetTimestamp();
                    sync.Create(command.Id, command.Strict);
                    long took = Stopwatch.GetTimestamp() - start;

                    if (!command.Strict)
                    {
                        nonStrictCreates++;
                        nonStrictCreateTicks += took;
                        nonStrictCreateMax = Math.Max(nonStrictCreateMax, took);
                    }

                    map.AssignSync(command.Id);
                    Volatile.Write(ref lastAssigned, (long)command.Id);
                    break;
                case 2:
                    RenderStageTimer.NextSubmitCause = RenderStageTimer.SubmitCause.Present;
                    gd.FlushAllCommands();
                    break;
                case 3:
                    long cleanupStart = Stopwatch.GetTimestamp();
                    sync.Cleanup();
                    cleanupTicks += Stopwatch.GetTimestamp() - cleanupStart;
                    break;
            }
        }

        renderThread = new Thread(() =>
        {
            while (Volatile.Read(ref running) || !queue.IsEmpty)
            {
                work.WaitOne(5);
                RunInterrupt();

                while (queue.TryDequeue(out Command command))
                {
                    Run(command);
                    RunInterrupt();
                }
            }
        }) { Name = "Render thread" };

        void Enqueue(Command command)
        {
            while (queue.Count > 10000)
            {
                Thread.Sleep(1);
            }

            queue.Enqueue(command);
            work.Set();
        }

        ulong nextId = 0;
        int drawsPerSync = draws / (syncsPerFrame + 1);
        var gpuThread = new Thread(() =>
        {
            foreach (int frame in fifo.GetConsumingEnumerable())
            {
                Enqueue(new Command { Kind = 3 });
                int sync_k = 0;

                for (int draw = 0; draw < draws; draw++)
                {
                    Spin.For(gpuThreadMicros);
                    Enqueue(new Command { Kind = 0, Framebuffer = draw / (draws / framebuffers) });

                    if ((draw + 1) % drawsPerSync == 0 && sync_k < syncsPerFrame)
                    {
                        sync_k++;

                        if (queries)
                        {
                            long start = Stopwatch.GetTimestamp();
                            ulong current = sync.GetCurrent();
                            long took = Stopwatch.GetTimestamp() - start;
                            queryCalls++;
                            queryTicks += took;
                            queryMax = Math.Max(queryMax, took);

                            if (current > 0 && required.TryGetValue(current - 1, out long need) && need > gpu.Completed)
                            {
                                Interlocked.Increment(ref violations);
                            }
                        }

                        ulong id = nextId++;
                        map.CreateSyncHandle(id);
                        Enqueue(new Command { Kind = 1, Id = id, Strict = sync_k % strictEvery == 1 });

                        if (sync_k == readbackSync)
                        {
                            Volatile.Write(ref readbackIds[frame], (long)id);
                            readbackReady.Set();
                        }
                    }
                }

                Enqueue(new Command { Kind = 2 });
                Volatile.Write(ref processedFrame, frame);
                frameProcessed.Set();
            }
        }) { Name = "GPU.MainThread" };

        void WaitSync(ulong id, ref long ticks, ref long max, ref long count)
        {
            long start = Stopwatch.GetTimestamp();
            map.WaitSyncAvailability(id);
            sync.Wait(id);
            long took = Stopwatch.GetTimestamp() - start;

            if (required.TryGetValue(id, out long need) && need > gpu.Completed)
            {
                Interlocked.Increment(ref violations);
            }

            ticks += took;
            max = Math.Max(max, took);
            count++;
        }

        bool readersRunning = readers;
        var readerThread = new Thread(() =>
        {
            while (Volatile.Read(ref readersRunning))
            {
                long last = Volatile.Read(ref lastAssigned);

                if (last >= 4)
                {
                    WaitSync((ulong)(last - 4), ref readerTicks, ref readerMax, ref readerWaits);
                }

                Thread.Sleep(2);
            }
        }) { Name = "Guest memory reader" };

        long gpuBusyStart = 0, gpuIdleStart = 0;
        renderThread.Start();
        gpuThread.Start();
        readerThread.Start();
        long readbackMax = 0, readbacks = 0;
        const int Warmup = 5;

        for (int frame = 0; frame < frames; frame++)
        {
            while (Volatile.Read(ref processedFrame) < frame - 1)
            {
                frameProcessed.WaitOne(1);
            }

            frameStarts[frame] = Stopwatch.GetTimestamp();

            if (frame == Warmup)
            {
                gpuBusyStart = gpu.BusyTicks;
                gpuIdleStart = gpu.IdleTicks;
            }

            fifo.Add(frame);

            if (readbackSync > 0)
            {
                while (Volatile.Read(ref readbackIds[frame]) < 0)
                {
                    readbackReady.WaitOne(1);
                }

                long before = readbackTicks;
                WaitSync((ulong)readbackIds[frame], ref readbackTicks, ref readbackMax, ref readbacks);

                if (frame < Warmup)
                {
                    readbackTicks = before;
                    readbacks--;
                }
            }

            Spin.For(guestMillis * 1000);
        }

        fifo.CompleteAdding();
        gpuThread.Join();
        long end = Stopwatch.GetTimestamp();
        Volatile.Write(ref readersRunning, false);
        readerThread.Join();
        Volatile.Write(ref running, false);
        work.Set();
        renderThread.Join();
        long busy = gpu.BusyTicks - gpuBusyStart, idle = gpu.IdleTicks - gpuIdleStart;
        gpu.Stop();
        int measured = frames - Warmup;
        double frameMs = Ms(end - frameStarts[Warmup]) / measured;

        return new
        {
            label, queries, frames, frameMs = Round(frameMs), fps = Round(1000 / frameMs),
            gpuBusyPercent = Round(100.0 * busy / Math.Max(1, busy + idle)),
            submitsPerFrame = Round((double)gpu.Submits / frames), syncsPerFrame = Round((double)nextId / frames),
            fencesCreatedPerFrame = Round((double)gpu.FencesCreated / frames), holdersPerFrame = Round((double)nextId / frames),
            passesPerFrame = Round((double)gd.PassBegins / frames), passResumesPerFrame = Round((double)gd.PassResumes / frames),
            flushesByCause = new
            {
                strictSync = gd.FlushesByCause[(int)RenderStageTimer.SubmitCause.StrictSync],
                syncWait = gd.FlushesByCause[(int)RenderStageTimer.SubmitCause.SyncWait],
                attachment = gd.FlushesByCause[(int)RenderStageTimer.SubmitCause.AttachmentAutoFlush],
                present = gd.FlushesByCause[(int)RenderStageTimer.SubmitCause.Present],
            },
            gpuThreadQueryMs = Round(Ms(queryTicks)), gpuThreadQueryMaxMs = Round(Ms(queryMax)), queryCalls,
            renderNonStrictCreateMs = Round(Ms(nonStrictCreateTicks)), renderNonStrictCreateMaxMs = Round(Ms(nonStrictCreateMax)), nonStrictCreates,
            renderCleanupMs = Round(Ms(cleanupTicks)),
            readbackWaitPerFrameMs = Round(Ms(readbackTicks) / Math.Max(1, readbacks)), readbackWaitMaxMs = Round(Ms(readbackMax)),
            readerWaits, readerWaitMeanMs = Round(Ms(readerTicks) / Math.Max(1, readerWaits)), readerWaitMaxMs = Round(Ms(readerMax)),
            violations, signalTimeouts = Logger.Error.Lines.Count,
        };
    }

    // 5. Cost of an uncontended query and of a wait on a signalled sync (the journal's counters included in the candidate).
    static object Costs()
    {
        var gpu = new GpuModel(manual: true);
        var gd = new VulkanRenderer(gpu);
        SyncManager sync = gd.SyncManager;
        gd.InterruptAction = action => action();

        for (ulong i = 0; i < 24; i++)
        {
            gd.Draw(0, 1);
            sync.Create(i, i % 4 == 0);

            if (i == 11)
            {
                gd.FlushAllCommands();

                while (gpu.CompleteNext()) { }
            }
        }

        sync.Wait(3);
        double[] query = new double[7], wait = new double[7];
        const int Calls = 50000;

        for (int sample = -1; sample < 7; sample++)
        {
            long start = Stopwatch.GetTimestamp();
            for (int i = 0; i < Calls; i++) sync.GetCurrent();
            long middle = Stopwatch.GetTimestamp();
            for (int i = 0; i < Calls; i++) sync.Wait(3);
            long stop = Stopwatch.GetTimestamp();

            if (sample >= 0)
            {
                query[sample] = Ms(middle - start) * 1e6 / Calls;
                wait[sample] = Ms(stop - middle) * 1e6 / Calls;
            }
        }

        Array.Sort(query);
        Array.Sort(wait);
        return new { queryNanoseconds = Round(query[3]), signalledWaitNanoseconds = Round(wait[3]), current = sync.GetCurrent() };
    }

    static void Main(string[] args)
    {
        var scripted = Scripted();
        var convoy = Convoy();
        var journal = Journal();
        var costs = Costs();
        var streams = new List<object>();
        int repeats = int.Parse(args[0]);

        for (int repeat = 0; repeat < repeats; repeat++)
        {
            streams.Add(Stream("hogwarts-queries", true, 45, 400, 25, 18, 5, 8, 48, 30, 40, 12, true));
            streams.Add(Stream("hogwarts-no-queries", false, 45, 400, 25, 18, 5, 8, 48, 30, 40, 12, true));
            streams.Add(Stream("light-queries", true, 45, 200, 4, 4, 2, 0, 20, 10, 10, 6, false));
        }

        Console.WriteLine(JsonSerializer.Serialize(new { checks = Checks, scripted, convoy, journal, costs, streams }));
    }
}
