using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.GAL.Multithreading.Resources.Programs;
using Ryujinx.Library;

sealed class RendererFault(string message) : Exception(message);

static class Program
{
    static int Checks;
    static readonly List<string> Scenarios = [];
    static void Check(bool value, string message)
    { Interlocked.Increment(ref Checks); if (!value) throw new Exception(message); }
    static void Ready(ManualResetEventSlim signal, string name) => Check(signal.Wait(5000), name);
    static void Joined(Thread thread, string name) => Check(thread.Join(5000), name);
    [MethodImpl(MethodImplOptions.NoInlining)]
    static void Origin(RendererFault error) => throw error;
    static void Same(Exception actual, RendererFault expected, string name)
    { Check(ReferenceEquals(actual, expected), name + " original identity"); Check(actual.StackTrace.Contains(nameof(Origin)), name + " original stack"); }
    static T Field<T>(object obj, string name) => (T)obj.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(obj);
    static void SetField(object obj, string name, object value) => obj.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).SetValue(obj, value);
    static Exception Capture(Action action) { try { action(); return null; } catch (Exception e) { return e; } }

    sealed class Session
    {
        public readonly Backend Backend = new();
        public readonly ThreadedRenderer Renderer;
        public readonly ManualResetEventSlim Returned = new(false), GpuDone = new(false);
        public Thread Worker;
        public Exception Error;
        public Session() => Renderer = new(Backend);
        public void Start(Action gpu)
        {
            Worker = new(() =>
            {
                try { Renderer.RunLoop(() => { try { gpu(); } finally { GpuDone.Set(); } }); }
                catch (Exception e) { Error = e; }
                finally { Returned.Set(); }
            }) { IsBackground = true };
            Worker.Start();
        }
        public void Close()
        {
            Ready(GpuDone, "producer exited before dispose");
            Renderer.Dispose();
            Joined(Worker, "backend exited after dispose");
            Check(Backend.Disposals == 1, "backend disposed once");
            Check(Field<object[]>(Renderer, "_refQueue").All(x => x == null), "no queued roots after close");
        }
    }

    static void Normal()
    {
        Session s = new();
        // Make normal backend disposal wait for the consumer's natural return,
        // including on the old implementation, to isolate failure transport.
        s.Backend.OnDispose = () => Ready(s.Returned, "normal consumer returned");
        s.Start(() =>
        {
            s.Renderer.PreFrame();
            s.Renderer.UpdateCounters();
            BufferHandle buffer = s.Renderer.CreateBuffer(4, BufferAccess.Default);
            s.Renderer.CreateSync(8, false);
            IProgram program = s.Renderer.CreateProgram([], default);
            Check(program.CheckProgramLink(true) == ProgramLinkStatus.Success, "normal program result");
            Check(program.GetBinary().SequenceEqual(new byte[] {1, 2, 3}), "normal binary result");
            using (s.Renderer.GetBufferData(buffer, 0, 4)) { }
            s.Renderer.WaitSync(8);
            ITexture texture = s.Renderer.CreateTexture(default);
            s.Renderer.Window.Present(texture, default, () => { });
            s.Renderer.FlushThreadedCommands();
        });
        s.Close();
        Check(s.Error == null, "normal session no failure");
        Check(s.Backend.Frames == 1 && s.Backend.Counters == 1 && s.Backend.Buffers == 1 && s.Backend.Syncs == 1 && s.Backend.Waits == 1 && s.Backend.Reads == 1, "normal command effects");
        Check(((NativeWindow)s.Backend.Window).Presents == 1, "normal presentation");
        Scenarios.Add("normal-real-command-results-and-close");
    }

    static void ProgramFailure(bool ensureCreation, bool control = false)
    {
        Session s = new();
        RendererFault failure = new("program fatal");
        ProgramLinkStatus result = ProgramLinkStatus.Success;
        if (ensureCreation) s.Backend.OnCreateProgram = () => Origin(failure);
        else s.Backend.OnCheck = blocking => { if (blocking) Origin(failure); return ProgramLinkStatus.Success; };
        s.Start(() =>
        {
            // Bypass only the eager CreateProgram command to force the actual
            // EnsureProgramCreated path inside ProgramCheckLinkCommand.
            ThreadedProgram program = new(s.Renderer);
            s.Renderer.Programs.Add(new SourceProgramRequest(program, [], default));
            result = program.CheckProgramLink(true);
        });
        if (control)
        {
            Ready(s.GpuDone, "old invoke returns despite native failure");
            Check(result == ProgramLinkStatus.Incomplete, "old invoke exposes unset ResultBox");
            Check(s.Error == null && !s.Returned.IsSet, "old command helper swallowed failure");
            Check(Field<object[]>(s.Renderer, "_refQueue").Any(x => x != null), "old failed command leaves partial refs");
            Scenarios.Add("old-program-error-swallowed-default-result-and-partial-refs");
            Print();
            Environment.Exit(0); // Isolated control process retains its abandoned renderer.
        }
        Ready(s.Returned, "program backend reports error");
        Same(s.Error, failure, "program error");
        Ready(s.GpuDone, "failed invoke wakes producer");
        Check(Field<object[]>(s.Renderer, "_refQueue").Any(x => x != null), "failed command leaves unconsumed result reference");
        Same(Capture(() => s.Renderer.GetCapabilities()), failure, "late invoke");
        Same(Capture(() => s.Renderer.FlushThreadedCommands()), failure, "late flush");
        s.Close();
        Scenarios.Add(ensureCreation ? "ensure-program-created-failure" : "program-link-failure-partial-reference-consumption");
    }

    static void PreFrameWaits(bool control = false)
    {
        Session s = new();
        RendererFault failure = new("preframe fatal");
        using ManualResetEventSlim inside = new(false), trigger = new(false), queued = new(false);
        s.Backend.OnPreFrame = () => { inside.Set(); Ready(trigger, "release preframe"); Origin(failure); };
        BufferHandle buffer = default;
        ThreadedTexture texture = null;
        ThreadedCounterEvent counter = null;
        s.Start(() =>
        {
            s.Renderer.PreFrame();
            Ready(inside, "consumer entered preframe");
            buffer = s.Renderer.CreateBuffer(4, BufferAccess.Default);
            s.Renderer.CreateSync(9, false);
            texture = (ThreadedTexture)s.Renderer.CreateTexture(default);
            counter = (ThreadedCounterEvent)s.Renderer.ReportCounter(CounterType.SamplesPassed, null, 1, false);
            s.Renderer.WaitForFrame(); // Consume the initial frame token.
            queued.Set();
            s.Renderer.Window.Present(texture, default, () => { });
        });
        Ready(queued, "pending resources queued");
        if (control)
        {
            trigger.Set();
            Check(SpinWait.SpinUntil(() => s.Backend.Buffers == 1 && s.Backend.Syncs == 1, 5000), "old queue continues after native fatal");
            Check(s.Error == null && !s.Returned.IsSet, "old preframe fatal swallowed");
            Check(!s.GpuDone.Wait(200), "old frame wait receives no failure wake");
            Scenarios.Add("old-preframe-error-swallowed-queue-resumed-frame-wait-stranded"); Print(); Environment.Exit(0);
        }

        List<(Thread thread, Func<Exception> error)> waits = [];
        using CountdownEvent started = new(13);
        void Waiter(Action action)
        {
            Exception error = null;
            Thread thread = new(() => { started.Signal(); error = Capture(action); }) { IsBackground = true };
            waits.Add((thread, () => error)); thread.Start();
        }
        for (int i = 0; i < 3; i++) Waiter(() => { using (s.Renderer.GetBufferData(buffer, 0, 4)) { } });
        for (int i = 0; i < 3; i++) Waiter(() => s.Renderer.WaitSync(9));
        Waiter(() => { using (texture.GetData()) { } });
        Waiter(() => { using (texture.GetData(0, 0)) { } });
        Waiter(() => texture.CopyTo(new ThreadedTexture(s.Renderer, default), default(Extents2D), default, false));
        Waiter(counter.Flush);
        SetField(counter, "_createLock", 1); // State retained if ReportCounter itself faults.
        Waiter(() => counter.ReserveForHostAccess());
        Waiter(s.Renderer.FlushThreadedCommands);
        Waiter(() => s.Backend.Interrupt(() => throw new Exception("must not run after fatal")));
        Check(started.Wait(5000), "all external waiters entered");
        trigger.Set(); Ready(s.Returned, "preframe error reaches owner");
        Same(s.Error, failure, "preframe");
        foreach (var waiter in waits) { Joined(waiter.thread, "failure woke external waiter"); Same(waiter.error(), failure, "external waiter"); }
        Ready(s.GpuDone, "frame wait wakes");
        Check(s.Backend.Buffers == 0 && s.Backend.Syncs == 0 && s.Backend.Reads == 0 && s.Backend.Waits == 0, "abandoned commands/native waits not executed");

        // Ready fast paths must also reject an already-published error.
        s.Renderer.Buffers.AssignBuffer(buffer, Backend.Handle(88));
        s.Renderer.Sync.AssignSync(9);
        NativeTexture native = new(); texture.Base = native;
        NativeCounter nativeCounter = new(); counter.Base = nativeCounter;
        Same(Capture(() => { using (s.Renderer.GetBufferData(buffer, 0, 4)) { } }), failure, "mapped buffer fast path");
        Same(Capture(() => s.Renderer.WaitSync(9)), failure, "available sync fast path");
        Same(Capture(() => { using (texture.GetData()) { } }), failure, "ready texture fast path");
        Same(Capture(counter.Flush), failure, "ready counter fast path");
        Same(Capture(() => s.Backend.Interrupt(() => { })), failure, "late interrupt");
        Check(native.Calls == 0 && nativeCounter.Calls == 0, "no native resource access after published error");
        s.Close();
        Scenarios.Add("preframe-frame-buffer-sync-texture-counter-flush-interrupt-waits");
    }

    static void QueueFull()
    {
        Session s = new(); RendererFault failure = new("full ring fatal");
        using ManualResetEventSlim inside = new(false), trigger = new(false), full = new(false);
        s.Backend.OnPreFrame = () => { inside.Set(); Ready(trigger, "release full queue"); Origin(failure); };
        s.Start(() =>
        {
            s.Renderer.PreFrame(); Ready(inside, "full queue backend blocked");
            for (int i = 0; i < 9998; i++) s.Renderer.UpdateCounters();
            full.Set(); s.Renderer.UpdateCounters();
        });
        Ready(full, "9999 real commands fill usable ring");
        Check(Field<int>(s.Renderer, "_commandCount") == 9999, "ring really full with reserved sentinel slot");
        trigger.Set(); Ready(s.Returned, "full ring backend error");
        Same(s.Error, failure, "full ring"); s.Close();
        Check(s.Backend.Counters == 0, "full abandoned ring not executed");
        Scenarios.Add("full-command-ring-wakes-producer");
    }

    static void ProducerFailure()
    {
        Session s = new(); RendererFault failure = new("GPU loop fatal");
        s.Start(() => Origin(failure));
        Ready(s.Returned, "producer error reaches idle consumer");
        Same(s.Error, failure, "producer");
        Same(Capture(() => s.Backend.Interrupt(() => { })), failure, "producer late interrupt");
        s.Close(); Scenarios.Add("producer-thread-failure-is-contained-and-reported");
    }

    static void InterruptFailure()
    {
        Session s = new(); RendererFault failure = new("interrupt fatal");
        using ManualResetEventSlim gpuReady = new(false), releaseGpu = new(false);
        s.Start(() => { gpuReady.Set(); Ready(releaseGpu, "release interrupt GPU"); });
        Ready(gpuReady, "interrupt GPU ready");
        Exception interrupt = Capture(() => s.Backend.Interrupt(() => Origin(failure)));
        Same(interrupt, failure, "interrupt waiter"); Ready(s.Returned, "interrupt owner return");
        Same(s.Error, failure, "interrupt owner");
        releaseGpu.Set(); s.Close(); Scenarios.Add("interrupt-action-exception-wakes-caller");
    }

    static void PauseOwner(bool stopFails)
    {
        Backend backend = new(); ThreadedRenderer renderer = new(backend);
        EmbeddedWindowLifetime lifetime = new(); lifetime.SetPaused(true);
        RendererFault failure = new("paused preframe fatal");
        using ManualResetEventSlim paused = new(false), resumed = new(false), gpuDone = new(false);
        bool stopped = false, released = false;
        backend.OnPreFrame = () => { Ready(paused, "GPU reached pause"); Origin(failure); };
        Exception error = Capture(() => lifetime.Run(
            () => Check(SpinWait.SpinUntil(() => !lifetime.InputAllowed, 5000), "real owner receives render failure"),
            () => renderer.RunLoop(() =>
            {
                renderer.PreFrame(); paused.Set(); lifetime.WaitUntilResumed(); resumed.Set();
                Check(SpinWait.SpinUntil(() => !lifetime.RenderAllowed, 5000), "owner stops rendering after guest stop");
                lifetime.NotifyRenderDrained(); gpuDone.Set();
            }),
            () => { stopped = true; Ready(resumed, "RequestStop wakes paused GPU before release"); if (stopFails) throw new Exception("guest stop failed"); },
            () => { Check(stopped, "guest stop precedes release"); renderer.Dispose(); released = true; }));
        Check(error is InvalidOperationException, "owner preserves failure envelope");
        Ready(gpuDone, "paused GPU finishes");
        if (stopFails)
        {
            Check(lifetime.GuestStopFailed && !released && backend.Disposals == 0, "unproven guest quarantines backend");
            Check(Capture(() => lifetime.Dispose(() => throw new Exception("must not release"))) is InvalidOperationException, "quarantine rejects disposal");
            Scenarios.Add("real-owner-guest-stop-failure-remains-quarantined");
        }
        else
        {
            Same(error.InnerException, failure, "real owner original error");
            Check(released && backend.Disposals == 1 && !lifetime.GuestStopFailed, "real owner completes safe release");
            lifetime.Dispose(() => { });
            Scenarios.Add("real-owner-paused-GPU-request-stop-before-join");
        }
    }

    static void Print() => Console.WriteLine(JsonSerializer.Serialize(new { checks = Checks, scenarios = Scenarios }));
    static void Main(string[] args)
    {
        switch (args[0])
        {
            case "normal": Normal(); break;
            case "old-invoke": ProgramFailure(false, true); break;
            case "old-preframe": PreFrameWaits(true); break;
            case "failures":
                ProgramFailure(false); ProgramFailure(true); PreFrameWaits(); QueueFull();
                ProducerFailure(); InterruptFailure(); PauseOwner(false); PauseOwner(true);
                break;
            default: throw new Exception("unknown scenario");
        }
        Print();
    }
}
