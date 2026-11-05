// Executed scenarios of melonx_setprogram_warmup_test.py, run once per variant on the real members compiled with
// Double.cs. One "render thread" (this thread) runs CreateProgramCommand, SetProgramCommand and the draws/dispatches,
// as the threaded renderer does; compiles are timed sleeps recorded with their cache and thread (Native.Records).
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Commands;
using Ryujinx.Graphics.GAL.Multithreading.Commands.Renderer;
using Ryujinx.Graphics.GAL.Multithreading.Model;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.GAL.Multithreading.Resources.Programs;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Vulkan;
using Ryujinx.Common.Logging;

Thread.CurrentThread.Name = "render";
string variant = args[0];
int P = Native.PipelineMs = int.Parse(args[1]);
var report = new Dictionary<string, object> { ["variant"] = variant, ["pipelineMs"] = P,
    ["pipelineWorkers"] = BackgroundCompilationScheduler.PipelineWorkerCount, ["processors"] = Environment.ProcessorCount };
bool hasPolicy = typeof(VulkanRenderer).GetProperty("DetachPlayTimeWarmUps") != null;
report["hasPolicyProperty"] = hasPolicy;

const int List = 0, Strip = 1;

ShaderSource[] Graphics(bool failFragment = false) => [new() { Stage = ShaderStage.Vertex }, new() { Stage = ShaderStage.Fragment, FailModule = failFragment }];
ShaderSource[] Compute() => [new() { Stage = ShaderStage.Compute }];
ShaderInfo GraphicsInfo(int topology, bool restart, bool fromCache = false, bool async = false) =>
    new(0, new ResourceLayout(), new ProgramPipelineState { Topology = topology, PrimitiveRestartEnable = restart }, fromCache, async, false);
ShaderInfo ComputeInfo(bool fromCache = false) => new(0, new ResourceLayout(), fromCache, false, false);

int MissLines() { lock (Logger.Warning.Lines) return Logger.Warning.Lines.Count(l => l.StartsWith("Background pipeline compile missed on draw")); }
string[] Warnings() { lock (Logger.Warning.Lines) return Logger.Warning.Lines.ToArray(); }
Compile[] Records() { lock (Native.Records) return Native.Records.ToArray(); }

void ClearLogs()
{
    foreach (Sink sink in new[] { Logger.Warning, Logger.Error, Logger.Debug }) lock (sink.Lines) sink.Lines.Clear();
}

// Every warm-up record (keys of a program's pipeline state at translation) compiled on the render thread.
int RenderThreadWarmUps(Compile[] records, params string[] warmUpKeys) => records.Count(r => r.Thread == "render" && warmUpKeys.Contains(r.Key));

void Settle(params Session[] sessions)
{
    foreach (Session s in sessions)
        foreach (ShaderCollection program in s.Gd.Shaders.ToArray())
            program.WaitForBackgroundCompilation();
    Thread.Sleep(20);
}

object Describe(Compile c, double origin) => new { key = c.Key, cache = c.Cache == 0 ? "main" : "worker" + (c.Cache - 1),
    thread = c.Thread, start = Math.Round(c.Start - origin, 1), end = Math.Round(c.End - origin, 1), failed = c.Handle == 0 };

// 1. The 658 miss: the program's warm-up has topology List without restart, its first draw Strip with restart.
//    SetProgram must not wait for that warm-up, the draw builds its own pipeline (never skipped) and binds it.
Dictionary<string, object> Mismatch(bool policy)
{
    Native.Reset(); ClearLogs();
    var s = new Session(policy);
    double origin = Native.Now;
    ThreadedProgram program = s.Create(Graphics(), GraphicsInfo(List, false));
    double setStart = Native.Now;
    s.SetProgram(program);
    double setEnd = Native.Now;
    bool drawn = s.Gd.Full.Draw(Strip, true);
    double drawEnd = Native.Now;
    ulong bound = s.Gd.Full.BoundHandle;
    Settle(s);
    // A later draw with the warm-up's key binds the warm-up's pipeline without compiling again.
    bool second = s.Gd.Full.Draw(List, false);
    ulong secondBound = s.Gd.Full.BoundHandle;
    Compile[] records = Records();
    Compile warmUp = records.Single(r => r.Key == "graphics topology 0");
    Compile own = records.Single(r => r.Key == "graphics topology 1 restart");
    var shader = (ShaderCollection)program.Base;
    return new()
    {
        ["compilesInBackground"] = shader.CompilesInBackground,
        ["canBindWhileIncomplete"] = shader.CanBindWhileIncomplete,
        ["setProgramMs"] = Math.Round(setEnd - setStart, 1),
        ["bindMs"] = Math.Round(setEnd - origin, 1),
        ["drawMs"] = Math.Round(drawEnd - setEnd, 1),
        ["toFirstDrawMs"] = Math.Round(drawEnd - origin, 1),
        ["setProgramReturnedBeforeWarmUpEnd"] = setEnd < warmUp.End,
        ["drawBuildStartedBeforeWarmUpEnd"] = own.Start < warmUp.End,
        ["drawn"] = drawn, ["boundOwnPipeline"] = bound == own.Handle,
        ["secondDrawn"] = second, ["secondBoundWarmUp"] = secondBound == warmUp.Handle,
        ["compiles"] = records.Length, ["renderThreadWarmUps"] = RenderThreadWarmUps(records, warmUp.Key),
        ["warmUp"] = Describe(warmUp, origin), ["drawBuild"] = Describe(own, origin),
        ["missLines"] = Warnings().Where(l => l.StartsWith("Background pipeline compile missed on draw")).ToArray(),
    };
}

// 2. The draw needs exactly the warm-up's pipeline: it gets that pipeline (no second compile), not skipped.
Dictionary<string, object> Match(bool policy, bool fromCache = false, bool async = false)
{
    Native.Reset(); ClearLogs();
    var s = new Session(policy);
    double origin = Native.Now;
    ThreadedProgram program = s.Create(Graphics(), GraphicsInfo(List, false, fromCache, async));
    double setStart = Native.Now;
    s.SetProgram(program);
    double setEnd = Native.Now;
    bool drawn = s.Gd.Full.Draw(List, false);
    double drawEnd = Native.Now;
    ulong bound = s.Gd.Full.BoundHandle;
    Settle(s);
    Compile[] records = Records();
    Compile warmUp = records.Single();
    var shader = (ShaderCollection)program.Base;
    return new()
    {
        ["compilesInBackground"] = shader.CompilesInBackground,
        ["canBindWhileIncomplete"] = shader.CanBindWhileIncomplete,
        ["setProgramMs"] = Math.Round(setEnd - setStart, 1),
        ["bindMs"] = Math.Round(setEnd - origin, 1),
        ["drawMs"] = Math.Round(drawEnd - setEnd, 1),
        ["toFirstDrawMs"] = Math.Round(drawEnd - origin, 1),
        ["setProgramReturnedBeforeWarmUpEnd"] = setEnd < warmUp.End,
        ["drawEndedAfterWarmUpEnd"] = drawEnd >= warmUp.End,
        ["drawn"] = drawn, ["boundWarmUp"] = bound == warmUp.Handle, ["skipped"] = s.Gd.Full.SkippedDraw,
        ["compiles"] = records.Length, ["renderThreadWarmUps"] = RenderThreadWarmUps(records, warmUp.Key),
        ["warmUp"] = Describe(warmUp, origin), ["missLines"] = MissLines(),
    };
}

// 3. A burst: three programs created ahead (ProgramQueue) are warming up when the bound program arrives. Its draw
//    either needs its own warm-up (match) or another state (mismatch).
Dictionary<string, object> Burst(bool policy, bool match)
{
    Native.Reset(); ClearLogs();
    var s = new Session(policy);
    double origin = Native.Now;
    s.Create(Graphics(), GraphicsInfo(10, false));
    s.Create(Graphics(), GraphicsInfo(11, false));
    s.Create(Graphics(), GraphicsInfo(12, false));
    Thread.Sleep(30);
    ThreadedProgram bound = s.Create(Graphics(), GraphicsInfo(13, false));
    double setStart = Native.Now;
    s.SetProgram(bound);
    double setEnd = Native.Now;
    bool drawn = match ? s.Gd.Full.Draw(13, false) : s.Gd.Full.Draw(14, true);
    double drawEnd = Native.Now;
    ulong handle = s.Gd.Full.BoundHandle;
    Settle(s);
    Compile[] records = Records();
    Compile mine = records.Single(r => r.Key == "graphics topology 13");
    Compile used = match ? mine : records.Single(r => r.Key == "graphics topology 14 restart");
    Compile[] others = records.Where(r => r.Key is "graphics topology 10" or "graphics topology 11" or "graphics topology 12").ToArray();
    return new()
    {
        ["setProgramMs"] = Math.Round(setEnd - setStart, 1),
        ["toFirstDrawMs"] = Math.Round(drawEnd - origin, 1),
        ["drawn"] = drawn, ["boundNeeded"] = handle == used.Handle,
        ["neededServedBeforeQueuedWarmUps"] = others.Count(o => o.End <= used.Start),
        ["compiles"] = records.Length,
        ["mainCacheWarmUps"] = records.Count(r => r.Cache == 0 && r != used),
        ["renderThreadWarmUps"] = RenderThreadWarmUps(records, "graphics topology 10", "graphics topology 11", "graphics topology 12", "graphics topology 13"),
        ["records"] = records.OrderBy(r => r.Start).Select(r => Describe(r, origin)).ToArray(),
    };
}

// 4. A compute program translated during play, and its first dispatch (SpecData.Empty, the warm-up's key).
Dictionary<string, object> ComputeDispatch(bool policy, bool fromCache = false)
{
    Native.Reset(); ClearLogs();
    var s = new Session(policy);
    double origin = Native.Now;
    ThreadedProgram program = s.Create(Compute(), ComputeInfo(fromCache));
    double setStart = Native.Now;
    s.SetProgram(program);
    double setEnd = Native.Now;
    bool dispatched = s.Gd.Full.Dispatch();
    double dispatchEnd = Native.Now;
    ulong bound = s.Gd.Full.BoundHandle;
    Settle(s);
    Compile[] records = Records();
    var shader = (ShaderCollection)program.Base;
    return new()
    {
        ["compilesInBackground"] = shader.CompilesInBackground,
        ["setProgramMs"] = Math.Round(setEnd - setStart, 1),
        ["bindMs"] = Math.Round(setEnd - origin, 1),
        ["toFirstDispatchMs"] = Math.Round(dispatchEnd - origin, 1),
        ["setProgramReturnedBeforeWarmUpEnd"] = setEnd < records.Min(r => r.End),
        ["dispatched"] = dispatched, ["boundCompiled"] = records.Any(r => r.Handle == bound),
        ["compiles"] = records.Length, ["renderThreadWarmUps"] = fromCache ? 0 : RenderThreadWarmUps(records, "compute spec 0"),
        ["records"] = records.Select(r => Describe(r, origin)).ToArray(),
    };
}

// 5. The GPU thread's disk-cache save poll (ShaderCache.ProcessShaderCacheQueue -> CheckProgramLink(false)) while the
//    warm-up compiles: it only asks whether the program failed.
Dictionary<string, object> SavePoll(bool policy)
{
    Native.Reset();
    var s = new Session(policy);
    ThreadedProgram program = s.Create(Graphics(), GraphicsInfo(List, false));
    Thread.Sleep(Math.Min(60, P / 4));
    ProgramLinkStatus during = program.Base.CheckProgramLink(false);
    Settle(s);
    return new() { ["duringWarmUp"] = during.ToString(), ["after"] = program.Base.CheckProgramLink(false).ToString() };
}

// 6. Dispose/teardown (CancelPendingWarmUp) of a program whose warm-up no worker has taken yet.
Dictionary<string, object> Cancel(bool policy)
{
    Native.Reset(); ClearLogs();
    var s = new Session(policy);
    int workers = BackgroundCompilationScheduler.PipelineWorkerCount;
    using var entered = new CountdownEvent(workers);
    using var release = new ManualResetEventSlim();
    for (int i = 0; i < workers; i++)
        s.Gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { entered.Signal(); release.Wait(); });
    entered.Wait(5000);
    ThreadedProgram program = s.Create(Graphics(), GraphicsInfo(List, false));
    Thread.Sleep(30);
    var shader = (ShaderCollection)program.Base;
    shader.CancelPendingWarmUp();
    release.Set();
    Settle(s);
    return new() { ["warmUpCompiled"] = Records().Length, ["failureLines"] = Logger.Warning.Lines.Count + Logger.Error.Lines.Count };
}

// 7. Failures: a warm-up whose pipeline fails (the draw still builds and binds it), a fragment module that fails.
Dictionary<string, object> Failures(bool policy)
{
    Native.Reset(); ClearLogs();
    var s = new Session(policy);
    lock (Native.FailOnce) Native.FailOnce.Add("graphics topology 0");
    ThreadedProgram program = s.Create(Graphics(), GraphicsInfo(List, false));
    s.SetProgram(program);
    bool drawn = s.Gd.Full.Draw(List, false);
    ulong bound = s.Gd.Full.BoundHandle;
    Settle(s);
    Compile[] records = Records();
    Native.Reset();
    var broken = new Session(policy);
    ThreadedProgram failed = broken.Create(Graphics(failFragment: true), GraphicsInfo(List, false));
    broken.SetProgram(failed);
    bool brokenDrawn = broken.Gd.Full.Draw(List, false);
    Settle(broken);
    return new()
    {
        ["warmUpFailedDrawn"] = drawn, ["warmUpFailedBoundSecondBuild"] = records.Length == 2 && bound == records[1].Handle && records[0].Handle == 0,
        ["warmUpFailedCompiles"] = records.Length,
        ["moduleFailedLink"] = ((ShaderCollection)failed.Base).LinkStatus.ToString(), ["moduleFailedDrawn"] = brokenDrawn,
        ["moduleFailedCompiles"] = Records().Length,
    };
}

report["mismatch"] = Mismatch(true);
report["match"] = Match(true);
report["burstMatch"] = Burst(true, match: true);
report["burstMismatch"] = Burst(true, match: false);
report["compute"] = ComputeDispatch(true);
report["savePoll"] = SavePoll(true);
report["cancel"] = Cancel(true);
report["failures"] = Failures(true);
// Gates: the policy off (other titles), a program from the cache, async shaders on.
report["mismatchPolicyOff"] = Mismatch(false);
report["computePolicyOff"] = ComputeDispatch(false);
report["cachedMatch"] = Match(true, fromCache: true);
report["cachedCompute"] = ComputeDispatch(true, fromCache: true);
report["asyncMatch"] = Match(true, async: true);
Console.WriteLine(JsonSerializer.Serialize(report));

class Session
{
    public readonly VulkanRenderer Gd = new();
    public readonly ThreadedRenderer Threaded;

    public Session(bool policy)
    {
        Threaded = new ThreadedRenderer(Gd);
        // The Library's per-session assignment (candidate only; the control has no such property).
        typeof(VulkanRenderer).GetProperty("DetachPlayTimeWarmUps")?.SetValue(Gd, policy);
    }

    // ThreadedRenderer.CreateProgram (GPU thread: queue the request) then CreateProgramCommand.Run (render thread).
    public ThreadedProgram Create(ShaderSource[] sources, ShaderInfo info)
    {
        var program = new ThreadedProgram();
        var request = new SourceProgramRequest(program, sources, info);
        Threaded.Programs.Add(request);
        var command = new CreateProgramCommand();
        command.Set(new TableRef<IProgramRequest>(Threaded, request));
        CreateProgramCommand.Run(ref command, Threaded, Gd);
        return program;
    }

    public void SetProgram(ThreadedProgram program)
    {
        var command = new SetProgramCommand();
        command.Set(new TableRef<IProgram>(Threaded, program));
        SetProgramCommand.Run(ref command, Threaded, Gd);
    }
}
