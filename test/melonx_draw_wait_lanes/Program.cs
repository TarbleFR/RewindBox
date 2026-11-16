// Fixture of melonx_draw_wait_lanes_test.py: the real BackgroundCompilationScheduler and the real GAL ProgramQueue, with a
// render thread and a GPU thread that follow the production order (CreateProgram command, ProcessQueue, the draw's promotion
// and wait). LANES is defined for the variant that holds adapt_draw_wait_lanes. A pipeline compile is a timed sleep.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.GAL.Multithreading.Resources.Programs;
using Ryujinx.Graphics.Vulkan;

record Compile(string Key, string Thread, int Cache, double Start, double End);

class World : IDisposable
{
    public readonly PipelineCacheManager Manager = new();
    public readonly BackgroundCompilationScheduler Scheduler;
    public readonly ProgramQueue Queue = new(null);
    public readonly List<Compile> Records = new();
    private readonly Stopwatch _clock = Stopwatch.StartNew();

    public World()
    {
        Scheduler = new(Manager);
    }

    public double Now => _clock.Elapsed.TotalMilliseconds;

    public Task Schedule(string key, int ms, bool demanded = false, Exception failure = null)
    {
        return Scheduler.SchedulePipelineCompile(cache =>
        {
            double start = Now;

            Thread.Sleep(ms);

            lock (Records)
            {
                Records.Add(new(key, Thread.CurrentThread.Name, cache.Index, start, Now));
            }

            if (failure != null)
            {
                throw failure;
            }
        }, highPriority: true, demanded: demanded);
    }

    public Compile Record(string key)
    {
        lock (Records)
        {
            return Records.Single(r => r.Key == key);
        }
    }

    public List<Compile> Snapshot()
    {
        lock (Records)
        {
            return Records.OrderBy(r => r.Start).ToList();
        }
    }

    // What a draw does once its program is bound: the promotion, then the wait.
    public void DrawWait(Task task)
    {
        if (task.IsCompleted)
        {
            return;
        }

        Scheduler.PromotePipelineCompile(task);
#if LANES
        Scheduler.WaitForPipelineAtDraw(task);
#else
        task.Wait();
#endif
    }

    public static void Bind(ProgramQueue queue)
    {
#if LANES
        RenderThreadPrograms.Bind(queue);
#endif
    }

    public static string TakeText()
    {
#if LANES
        return DrawWaitCounters.TakeText();
#else
        return null;
#endif
    }

    public void Dispose()
    {
        Scheduler.Dispose();
    }
}

class FakeProgram : IProgram
{
    public string Key;
    public Task WarmUp;

    // The modules of a program translated during play exist a few milliseconds after its creation; the warm-up is detached.
    public ProgramLinkStatus CheckProgramLink(bool blocking) => ProgramLinkStatus.Success;
}

class Request : IProgramRequest
{
    public ThreadedProgram Threaded { get; set; } = new();
    public Func<IProgram> Factory;
    public double CreatedAt = -1;
    public string CreatedOn;
    public int Creations;

    public IProgram Create(IRenderer renderer)
    {
        Creations++;
        CreatedOn = Thread.CurrentThread.Name;

        return Factory();
    }
}

static class Program
{
    private const string Worker = "Vulkan Pipeline Compile 0";
    private const string Demand = "Vulkan Pipeline Demand Compile";

    private static object Row(Compile c) => new { key = c.Key, thread = c.Thread, cache = c.Cache, start = Math.Round(c.Start, 1), end = Math.Round(c.End, 1) };

    private static void Run(string name, Action body)
    {
        Exception failure = null;
        Thread thread = new(() =>
        {
            try
            {
                body();
            }
            catch (Exception exception)
            {
                failure = exception;
            }
        })
        { Name = name };

        thread.Start();
        thread.Join();

        if (failure != null)
        {
            throw new InvalidOperationException(name + " failed", failure);
        }
    }

    // A frame that brings `count` programs new to the device: the GPU thread queues one every `translateMs` after the
    // first, the render thread runs each program's CreateProgram command, binds it and draws with it, in order.
    // `bindMs`: SetProgram's wait for the program's shader modules, during which the warm-up is queued and the worker
    // takes it (IPA 740: the build began 3.9 ms or more before the render thread's wait). 0: the draw promotes the
    // warm-up before any thread has taken it.
    private static object Burst(int count, int compileMs, int translateMs, int bindMs)
    {
        using World world = new();
        Request[] requests = new Request[count];
        ManualResetEventSlim[] commands = new ManualResetEventSlim[count];
        double[] drawnAt = new double[count];
        bool[] pipelineExisted = new bool[count];

        for (int index = 0; index < count; index++)
        {
            int k = index;

            commands[k] = new(false);
            requests[k] = new Request();
            requests[k].Factory = () =>
            {
                requests[k].CreatedAt = world.Now;

                return new FakeProgram { Key = "program " + k, WarmUp = world.Schedule("program " + k, compileMs) };
            };
        }

        Thread gpu = new(() =>
        {
            for (int k = 0; k < count; k++)
            {
                if (k != 0)
                {
                    Thread.Sleep(translateMs);
                }

                world.Queue.Add(requests[k]);
                commands[k].Set();
            }
        })
        { Name = "GPU.MainThread" };

        double start = 0;

        Run("Render", () =>
        {
            World.Bind(world.Queue);
            World.TakeText();
            start = world.Now;
            gpu.Start();

            for (int k = 0; k < count; k++)
            {
                commands[k].Wait();

                // CreateProgramCommand.Run
                if (requests[k].Threaded.Base == null)
                {
                    requests[k].Threaded.Base = requests[k].Create(null);
                }

                world.Queue.ProcessQueue();

                // SetProgramCommand.Run: the program exists; its modules compile; then the draw.
                FakeProgram program = (FakeProgram)requests[k].Threaded.Base;

                if (bindMs != 0 && !program.WarmUp.IsCompleted)
                {
                    Thread.Sleep(bindMs);
                }

                world.DrawWait(program.WarmUp);
                pipelineExisted[k] = program.WarmUp.IsCompletedSuccessfully;
                drawnAt[k] = world.Now;
            }

            World.Bind(null);
        });

        gpu.Join();

        double total = drawnAt[count - 1] - start;
        List<Compile> records = world.Snapshot();
        Compile[] byProgram = Enumerable.Range(0, count).Select(k => world.Record("program " + k)).ToArray();

        return new
        {
            totalMs = Math.Round(total, 1),
            compiles = records.Count,
            compiledOnce = Enumerable.Range(0, count).All(k => records.Count(r => r.Key == "program " + k) == 1),
            createdOnce = requests.All(r => r.Creations == 1),
            createdOnRenderThread = requests.All(r => r.CreatedOn == "Render"),
            createdInOrder = Enumerable.Range(1, count - 1).All(k => requests[k].CreatedAt >= requests[k - 1].CreatedAt),
            drawnInOrder = Enumerable.Range(1, count - 1).All(k => drawnAt[k] >= drawnAt[k - 1]),
            everyDrawAfterItsPipeline = Enumerable.Range(0, count).All(k => pipelineExisted[k] && drawnAt[k] >= byProgram[k].End),
            onDemandThread = records.Count(r => r.Thread == Demand),
            onWorker = records.Count(r => r.Thread == Worker),
            demandCache = records.Where(r => r.Thread == Demand).Select(r => r.Cache).Distinct().ToArray(),
            overlappedMs = Math.Round(records.Where(r => r.Thread == Demand)
                .Sum(d => records.Where(r => r.Thread == Worker).Sum(w => Math.Max(0, Math.Min(d.End, w.End) - Math.Max(d.Start, w.Start)))), 1),
            createdBeforeFirstDrawEnd = requests.Count(r => r.CreatedAt >= 0 && r.CreatedAt < drawnAt[0] - 1),
            notified = world.Manager.Notified,
            text = World.TakeText(),
            textAgain = World.TakeText(),
            records = records.Select(Row).ToArray(),
        };
    }

    // No draw waits: the demand thread stays reserved for demanded compiles.
    private static object Reserved(int compileMs)
    {
        using World world = new();

        World.TakeText();
        Task.WaitAll(Enumerable.Range(0, 3).Select(k => world.Schedule("queued " + k, compileMs)).ToArray());

        return new { threads = world.Snapshot().Select(r => r.Thread).ToArray(), text = World.TakeText() };
    }

    // The worker compiles A, a draw waits for A, B and C are queued behind it, then Y is demanded while both threads are
    // busy: when a thread is free it takes Y before C.
    private static object Precedence(int compileMs)
    {
        using World world = new();
        Task a = world.Schedule("A", compileMs);

        Thread.Sleep(20);

        Task b = world.Schedule("B", compileMs);
        Task c = world.Schedule("C", compileMs);
        Task y = null;

        World.TakeText();
        Thread demander = new(() =>
        {
            Thread.Sleep(compileMs / 3);
            y = world.Schedule("Y", compileMs, demanded: true);
        });

        demander.Start();
        Run("Render", () =>
        {
            World.Bind(world.Queue);
            world.DrawWait(a);
            World.Bind(null);
        });
        demander.Join();
        Task.WaitAll(b, c, y);

        Compile ra = world.Record("A"), rb = world.Record("B"), rc = world.Record("C"), ry = world.Record("Y");

        return new
        {
            aThread = ra.Thread,
            bThread = rb.Thread,
            bStartedDuringWait = rb.Start < ra.End - 1,
            yBeforeC = ry.Start < rc.Start,
            yStartAfterDemandMs = Math.Round(ry.Start - (ra.Start + compileMs / 3.0), 1),
            yStartAfterFirstEndMs = Math.Round(ry.Start - Math.Min(ra.End, rb.End), 1),
            text = World.TakeText(),
            records = world.Snapshot().Select(Row).ToArray(),
        };
    }

    // The awaited compile runs on the demand thread itself; when it completes that thread takes no high priority compile.
    private static object AfterAwaited(int compileMs)
    {
        using World world = new();
        Task l = world.Schedule("L", 3 * compileMs);

        Thread.Sleep(20);

        Task x = world.Schedule("X", compileMs, demanded: true);
        Task h = world.Schedule("H", compileMs);

        World.TakeText();
        Run("Render", () =>
        {
            World.Bind(world.Queue);
            world.DrawWait(x);
            World.Bind(null);
        });
        Task.WaitAll(l, h);

        Compile rl = world.Record("L"), rx = world.Record("X"), rh = world.Record("H");

        return new { xThread = rx.Thread, lThread = rl.Thread, hThread = rh.Thread, hAfterL = rh.Start >= rl.End - 1, text = World.TakeText() };
    }

    // The draw waits for a program whose pipeline compile is not queued yet (its modules have just compiled; a thread
    // pool continuation queues it a moment later, demanded). The worker runs S and T is queued behind it. The demand
    // thread must stay free for the awaited compile.
    private static object NotQueuedYet(int compileMs)
    {
        using World world = new();
        Task s = world.Schedule("S", 2 * compileMs);

        Thread.Sleep(20);

        Task t = world.Schedule("T", compileMs);
        TaskCompletionSource<bool> outer = new(TaskCreationOptions.RunContinuationsAsynchronously);
        double queuedAt = 0;
        Task x = null;

        World.TakeText();
        Thread continuation = new(() =>
        {
            Thread.Sleep(30);
            queuedAt = world.Now;
            x = world.Schedule("X", compileMs, demanded: true);
            x.Wait();
            outer.SetResult(true);
        });

        continuation.Start();
        Run("Render", () =>
        {
            World.Bind(world.Queue);
            world.DrawWait(outer.Task);
            World.Bind(null);
        });
        continuation.Join();
        Task.WaitAll(s, t);

        Compile rx = world.Record("X"), rt = world.Record("T");

        return new { xThread = rx.Thread, tThread = rt.Thread, xStartAfterQueuedMs = Math.Round(rx.Start - queuedAt, 1), text = World.TakeText() };
    }

#if LANES
    // A thread that is not a bound render thread waits as before: nothing is created.
    private static object Unbound(int compileMs)
    {
        using World world = new();
        Request request = new() { Factory = () => new FakeProgram() };

        world.Queue.Add(request);

        Task task = world.Schedule("solo", compileMs);

        Thread.Sleep(20);

        Task queued = world.Schedule("queued", compileMs / 2);
        bool bound = true;
        int created = -1;

        World.TakeText();
        Run("Other", () =>
        {
            bound = RenderThreadPrograms.Bound;
            created = RenderThreadPrograms.CreateQueued();
            world.Scheduler.PromotePipelineCompile(task);
            world.Scheduler.WaitForPipelineAtDraw(task);
        });
        queued.Wait();

        return new
        {
            bound,
            created,
            requestCreated = request.Threaded.Base != null,
            completed = task.IsCompletedSuccessfully,
            queuedThread = world.Record("queued").Thread,
            text = World.TakeText(),
        };
    }

    // A failed compile is thrown as Wait() throws it, and the wait is over for the queue.
    private static object Failure(int compileMs)
    {
        using World world = new();
        Task plain = world.Schedule("plain", compileMs, failure: new InvalidOperationException("compile failed"));
        string expected = Describe(() => plain.Wait());
        Task atDraw = world.Schedule("at draw", compileMs, failure: new InvalidOperationException("compile failed"));
        string thrown = null;

        Run("Render", () =>
        {
            World.Bind(world.Queue);
            thrown = Describe(() => world.Scheduler.WaitForPipelineAtDraw(atDraw));
            World.Bind(null);
        });

        // Afterwards no draw waits: a queued compile stays with the worker.
        Task busy = world.Schedule("busy", compileMs);

        Thread.Sleep(20);

        Task queued = world.Schedule("queued", compileMs);

        Task.WaitAll(busy, queued);

        return new { expected, thrown, queuedThread = world.Record("queued").Thread };
    }

    private static string Describe(Action action)
    {
        try
        {
            action();

            return "no exception";
        }
        catch (Exception exception)
        {
            return exception.GetType().FullName + " < " + exception.InnerException?.GetType().FullName + ": " + exception.InnerException?.Message;
        }
    }

    // A creation that asks again from inside itself creates nothing more and does not recurse.
    private static object Reentrant()
    {
        using World world = new();
        int nested = -1, outer = -1;
        Request first = new(), second = new() { Factory = () => new FakeProgram() };

        first.Factory = () =>
        {
            nested = RenderThreadPrograms.CreateQueued();

            return new FakeProgram();
        };
        world.Queue.Add(first);
        world.Queue.Add(second);

        Run("Render", () =>
        {
            RenderThreadPrograms.Bind(world.Queue);
            outer = RenderThreadPrograms.CreateQueued();
            RenderThreadPrograms.Bind(null);
        });

        return new { outer, nested, firstCreations = first.Creations, secondCreations = second.Creations };
    }

    // One wait with nothing queued: slices, not a busy loop.
    private static object Idle(int waitMs)
    {
        using World world = new();
        Task task = world.Schedule("idle", waitMs);
        double processorMs = 0, elapsed = 0;

        World.TakeText();
        Run("Render", () =>
        {
            World.Bind(world.Queue);

            TimeSpan before = Process.GetCurrentProcess().TotalProcessorTime;
            double start = world.Now;

            world.Scheduler.WaitForPipelineAtDraw(task);
            elapsed = world.Now - start;
            processorMs = (Process.GetCurrentProcess().TotalProcessorTime - before).TotalMilliseconds;
            World.Bind(null);
        });

        return new { elapsedMs = Math.Round(elapsed, 1), processorMs = Math.Round(processorMs, 1), sliceMs = BackgroundCompilationScheduler.DrawWaitSliceMs, text = World.TakeText() };
    }
#endif

    private static int Main(string[] arguments)
    {
        int compileMs = int.Parse(arguments[1]);
        Dictionary<string, object> report = new()
        {
            ["variant"] = arguments[0],
            ["processors"] = Environment.ProcessorCount,
            ["pipelineWorkers"] = BackgroundCompilationScheduler.PipelineWorkerCount,
            ["burst"] = Burst(5, compileMs, 6, 4),
            ["pair"] = Burst(2, compileMs, 6, 4),
            ["single"] = Burst(1, compileMs, 6, 4),
            ["burstPromotedFirst"] = Burst(5, compileMs, 6, 0),
            ["pairPromotedFirst"] = Burst(2, compileMs, 6, 0),
            ["reserved"] = Reserved(compileMs / 4),
            ["precedence"] = Precedence(compileMs),
            ["afterAwaited"] = AfterAwaited(compileMs),
            ["notQueuedYet"] = NotQueuedYet(compileMs),
        };
#if LANES
        report["unbound"] = Unbound(compileMs / 2);
        report["failure"] = Failure(compileMs / 4);
        report["reentrant"] = Reentrant();
        report["idle"] = Idle(2 * compileMs);
#endif
        Console.WriteLine(JsonSerializer.Serialize(report));

        return 0;
    }
}
