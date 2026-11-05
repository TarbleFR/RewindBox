using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.Gpu.Shader;

// The GPU thread (ThreadedRenderer's GPU.MainThread) runs the real save poll once per loop pass, as Switch.ProcessFrame
// does, while the real render thread is blocked on a compile. Argument: control or candidate. One JSON line of results.
static class Program
{
    static int Checks;
    static readonly Dictionary<string, object> Report = [];

    static void Check(bool condition, string message)
    {
        Checks++;
        if (!condition)
        {
            throw new Exception("FAILED: " + message);
        }
    }

    static double Ms(long ticks) => Math.Round(ticks * 1000.0 / Stopwatch.Frequency, 3);
    static long Now => Stopwatch.GetTimestamp();
    static readonly byte[] Spirv = [1, 2, 3, 4];

    static bool Compiled(IProgram program) =>
        (bool)program.GetType().GetField("Compiled", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(program);

    sealed class Session
    {
        public readonly Backend Backend = new();
        public readonly ThreadedRenderer Renderer;
        public readonly ShaderCache Cache = new();
        private readonly FieldInfo _commandCount = typeof(ThreadedRenderer).GetField("_commandCount", BindingFlags.Instance | BindingFlags.NonPublic);

        public Session() => Renderer = new ThreadedRenderer(Backend);

        public int Pending => (int)_commandCount.GetValue(Renderer);

        public IProgram Create(CompileDouble native)
        {
            Backend.Planned.Enqueue(native);
            return Renderer.CreateProgram([], default);
        }

        public void Run(string name, Action gpu)
        {
            Exception error = null;
            ManualResetEventSlim gpuDone = new(false);
            Thread render = new(() =>
            {
                Backend.RenderThread = Thread.CurrentThread;
                try
                {
                    Renderer.RunLoop(() =>
                    {
                        try { gpu(); }
                        catch (Exception e) { error = e; }
                        finally { gpuDone.Set(); }
                    });
                }
                catch (Exception e) { error ??= e; }
            }) { IsBackground = true, Name = "render" };
            render.Start();
            Check(gpuDone.Wait(60000), name + ": scenario finished");
            Renderer.Dispose();
            Check(render.Join(10000), name + ": render loop exited");
            if (error != null)
            {
                throw new Exception(name + " failed", error);
            }
        }
    }

    sealed class Polls
    {
        public int Passes, PassesWhileBlocked, MaxPendingWhileBlocked;
        public double FirstPollMs = -1, MaxPollMs;

        // One GPU loop pass: the save poll, then the rest of the frame (sleep), as Switch.ProcessFrame.
        public void Pass(Session session, Func<bool> renderBlocked, int restMs)
        {
            long start = Now;
            session.Cache.ProcessShaderCacheQueue();
            double ms = Ms(Now - start);
            Passes++;
            if (FirstPollMs < 0)
            {
                FirstPollMs = ms;
            }

            MaxPollMs = Math.Max(MaxPollMs, ms);
            if (renderBlocked())
            {
                PassesWhileBlocked++;
                MaxPendingWhileBlocked = Math.Max(MaxPendingWhileBlocked, session.Pending);
            }

            Thread.Sleep(restMs);
        }

        public Dictionary<string, object> Json() => new()
        {
            ["passes"] = Passes, ["passesReturnedWhileRenderBlocked"] = PassesWhileBlocked,
            ["maxPendingCommandsWhileRenderBlocked"] = MaxPendingWhileBlocked, ["firstPollMs"] = FirstPollMs, ["maxPollMs"] = MaxPollMs,
        };
    }

    static Thread After(int ms, Action action)
    {
        Thread thread = new(() => { Thread.Sleep(ms); action(); }) { IsBackground = true };
        thread.Start();
        return thread;
    }

    // Hogwarts 658 shape: a program compiled during play (asyncShaders=False), queued for the disk cache, then bound: the
    // render thread waits in SetProgram (ProgramQueue.WaitForProgram -> CheckProgramLink(true)) for 1500 ms.
    static void BlockedInSetProgram()
    {
        Session s = new();
        CompileDouble native = new("p1", s.Backend);
        Polls polls = new();
        IProgram program = null;
        long savedAt = 0;
        s.Run("blockedInSetProgram", () =>
        {
            program = s.Create(native);
            s.Cache.Enqueue(new CachedShaderProgram("p1"), program, Spirv);
            s.Renderer.Pipeline.SetProgram(program);
            Check(native.BlockEntered.Wait(10000), "render thread blocked in SetProgram's link wait");
            Thread timer = After(1500, () => native.Complete(ProgramLinkStatus.Success));
            long start = Now;
            while (s.Cache.Writer.Added.Count == 0 && Ms(Now - start) < 10000)
            {
                polls.Pass(s, () => native.RenderBlocked, 2);
            }

            timer.Join();
            s.Renderer.FlushThreadedCommands();
            savedAt = s.Cache.Writer.Added.Count == 1 ? s.Cache.Writer.Added[0].At : 0;
        });
        Check(s.Cache.Writer.Added.Select(a => a.Name).SequenceEqual(["p1"]) && s.Cache.Queued == 0, "p1 saved once, queue empty");
        Check(s.Cache.Writer.Added[0].Bytes == Spirv.Length && native.BinaryReads == 0, "saved from BinaryCode, no GetBinary");
        Check(savedAt >= native.LinkedAt, "never saved before it is linked");
        Check(native.OffRenderThreadChecks == 0 && native.CreatedOnRenderThread, "the backend program is only touched by the render thread");
        Check(s.Backend.NativePipeline.Bound == 1 && ReferenceEquals(s.Backend.NativePipeline.LastProgram, native), "the draw's program bound once");
        Check(Compiled(program), "the threaded program is marked compiled");
        Dictionary<string, object> r = polls.Json();
        r["savedAfterLinkMs"] = Ms(savedAt - native.LinkedAt);
        r["blockingChecks"] = native.BlockingChecks;
        r["nonBlockingChecks"] = native.NonBlockingChecks;
        Report["blockedInSetProgram"] = r;
    }

    // The render thread is busy with unrelated queued work (a draw-time pipeline build, 1000 ms) while the head program is
    // linked but not yet observed by the render thread: the old poll drains the whole queue first.
    static void BlockedInOtherWork()
    {
        Session s = new();
        CompileDouble native = new("p6", s.Backend);
        ManualResetEventSlim entered = new(false), release = new(false);
        bool busy = false;
        long freedAt = 0;
        s.Backend.OnPreFrame = () => { busy = true; entered.Set(); release.Wait(); freedAt = Now; busy = false; };
        Polls polls = new();
        s.Run("blockedInOtherWork", () =>
        {
            IProgram program = s.Create(native);
            s.Cache.Enqueue(new CachedShaderProgram("p6"), program, Spirv);
            s.Renderer.PreFrame();
            Check(entered.Wait(10000), "render thread inside the long command");
            native.Complete(ProgramLinkStatus.Success); // linked behind the render thread's back: it has not observed it
            Thread timer = After(1000, release.Set);
            long start = Now;
            while (s.Cache.Writer.Added.Count == 0 && Ms(Now - start) < 10000)
            {
                polls.Pass(s, () => Volatile.Read(ref busy), 2);
            }

            timer.Join();
        });
        Check(s.Cache.Writer.Added.Select(a => a.Name).SequenceEqual(["p6"]), "p6 saved once");
        Check(native.OffRenderThreadChecks == 0, "backend program only touched by the render thread");
        Dictionary<string, object> r = polls.Json();
        r["savedAfterRenderFreeMs"] = Ms(s.Cache.Writer.Added[0].At - freedAt);
        Report["blockedInOtherWork"] = r;
    }

    // N already-linked programs, created and bound by the render thread (so it observed their final status), while the render
    // thread is busy 800 ms in unrelated work: one GPU pass saves all N. The control drains the render queue first (a round
    // trip per program), the candidate answers from the published statuses with no round trip and no queued check.
    static void LinkedBurst()
    {
        const int N = 40;
        Session s = new();
        CompileDouble[] natives = Enumerable.Range(0, N).Select(i => new CompileDouble("b" + i, s.Backend)).ToArray();
        foreach (CompileDouble native in natives)
        {
            native.Complete(ProgramLinkStatus.Success);
        }

        ManualResetEventSlim entered = new(false), release = new(false);
        s.Backend.OnPreFrame = () => { entered.Set(); release.Wait(); };
        Polls polls = new();
        int savedInFirstPass = -1, pendingDuring = -1;
        s.Run("linkedBurst", () =>
        {
            foreach (CompileDouble native in natives)
            {
                IProgram program = s.Create(native);
                s.Cache.Enqueue(new CachedShaderProgram(native.Name), program, Spirv);
                s.Renderer.Pipeline.SetProgram(program);
            }

            s.Renderer.FlushThreadedCommands();
            s.Renderer.PreFrame();
            Check(entered.Wait(10000), "render thread inside the long command");
            Thread timer = After(800, release.Set);
            polls.Pass(s, () => !release.IsSet, 0);
            savedInFirstPass = s.Cache.Writer.Added.Count;
            pendingDuring = polls.MaxPendingWhileBlocked;
            timer.Join();
            s.Renderer.FlushThreadedCommands();
            Thread.Sleep(50);
        });
        Check(s.Cache.Writer.Added.Select(a => a.Name).SequenceEqual(natives.Select(n => n.Name)) && s.Cache.Queued == 0,
              "all linked programs saved once, in order");
        Check(natives.All(n => n.OffRenderThreadChecks == 0), "backend programs only touched by the render thread");
        Dictionary<string, object> r = polls.Json();
        r["programs"] = N;
        r["savedInFirstPass"] = savedInFirstPass;
        r["pendingDuringFirstPass"] = pendingDuring;
        Report["linkedBurst"] = r;
    }

    // A program that is never bound compiles in the background for 300 ms while the render thread is idle: it must still
    // be saved (no lost save), and the check rate stays at most one per pass.
    static void NeverBound()
    {
        Session s = new();
        CompileDouble native = new("p2", s.Backend, canBindWhileIncomplete: true);
        Polls polls = new();
        IProgram program = null;
        s.Run("neverBound", () =>
        {
            program = s.Create(native);
            s.Cache.Enqueue(new CachedShaderProgram("p2"), program, Spirv);
            Thread timer = After(300, () => native.Complete(ProgramLinkStatus.Success));
            long start = Now;
            while (s.Cache.Writer.Added.Count == 0 && Ms(Now - start) < 10000)
            {
                polls.Pass(s, () => false, 1);
            }

            timer.Join();
            s.Renderer.FlushThreadedCommands();
        });
        Check(s.Cache.Writer.Added.Select(a => a.Name).SequenceEqual(["p2"]) && s.Cache.Queued == 0, "never-bound program saved");
        Check(s.Cache.Writer.Added[0].At >= native.LinkedAt, "saved after it is linked");
        Check(native.OffRenderThreadChecks == 0 && native.BlockingChecks == 0, "only non-blocking checks, on the render thread");
        Check(native.NonBlockingChecks <= polls.Passes + 2, "at most one render-thread check per pass (plus ProgramQueue's own)");
        Check(Compiled(program), "the threaded program is marked compiled by the check");
        Dictionary<string, object> r = polls.Json();
        r["savedAfterLinkMs"] = Ms(s.Cache.Writer.Added[0].At - native.LinkedAt);
        r["nonBlockingChecks"] = native.NonBlockingChecks;
        Report["neverBound"] = r;
    }

    // Order and failures: p3 links 200 ms late, p4 is linked, p5 failed. Saved in order (p4 waits for p3), p5 dropped.
    static void OrderAndFailure()
    {
        Session s = new();
        CompileDouble p3 = new("p3", s.Backend, true), p4 = new("p4", s.Backend, true), p5 = new("p5", s.Backend, true);
        p4.Complete(ProgramLinkStatus.Success);
        p5.Complete(ProgramLinkStatus.Failure);
        Polls polls = new();
        s.Run("orderAndFailure", () =>
        {
            foreach (CompileDouble native in new[] { p3, p4, p5 })
            {
                s.Cache.Enqueue(new CachedShaderProgram(native.Name), s.Create(native), Spirv);
            }

            Thread timer = After(200, () => p3.Complete(ProgramLinkStatus.Success));
            long start = Now;
            while (s.Cache.Queued != 0 && Ms(Now - start) < 10000)
            {
                polls.Pass(s, () => false, 1);
            }

            timer.Join();
            s.Renderer.FlushThreadedCommands();
        });
        var added = s.Cache.Writer.Added;
        Check(added.Select(a => a.Name).SequenceEqual(["p3", "p4"]) && s.Cache.Queued == 0, "saved in order, failure dropped: " +
              string.Join(",", added.Select(a => a.Name)));
        Check(added[1].At >= p3.LinkedAt, "p4 waits for p3");
        Check(new[] { p3, p4, p5 }.All(p => p.OffRenderThreadChecks == 0), "backend programs only touched by the render thread");
        Report["orderAndFailure"] = new Dictionary<string, object> { ["saved"] = added.Select(a => a.Name).ToArray(), ["passes"] = polls.Passes };
    }

    // The default member keeps every backend's answer (no threaded wrapper): a non-blocking link check.
    static void DefaultMember()
    {
#if CANDIDATE
        Backend backend = new();
        CompileDouble native = new("direct", backend);
        IProgram direct = native;
        Check(direct.PeekLinkStatus() == ProgramLinkStatus.Incomplete && native.NonBlockingChecks == 1 && native.BlockingChecks == 0,
              "default PeekLinkStatus is CheckProgramLink(false)");
        native.Complete(ProgramLinkStatus.Failure);
        Check(direct.PeekLinkStatus() == ProgramLinkStatus.Failure && native.NonBlockingChecks == 2, "default answer follows the backend");
        Report["defaultMember"] = "CheckProgramLink(false)";
#else
        Report["defaultMember"] = null;
#endif
    }

    static void Main(string[] args)
    {
        string variant = args[0];
#if CANDIDATE
        Check(variant == "candidate", "candidate build");
#else
        Check(variant == "control", "control build");
#endif
        BlockedInSetProgram();
        BlockedInOtherWork();
        LinkedBurst();
        NeverBound();
        OrderAndFailure();
        DefaultMember();
        Report["variant"] = variant;
        Report["checks"] = Checks;
        Console.WriteLine(JsonSerializer.Serialize(Report));
    }
}
