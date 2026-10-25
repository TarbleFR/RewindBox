#!/usr/bin/env python3
"""Execute the production session/window owners with deterministic fake workers."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='melonx-session-') as temporary:
    work = Path(temporary)
    for name in ['EmbeddedSessionCoordinator', 'EmbeddedWindowLifetime']:
        (work / (name + '.cs')).write_bytes((root / 'native/melonx' / (name + '.cs')).read_bytes())
    (work / 'Session.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk">
      <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework></PropertyGroup>
    </Project>''')
    (work / 'Program.cs').write_text(r'''using System;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Library;
int passed = 0;
void Check(bool condition) { if (!condition) throw new Exception("Assertion failed"); }
void Case(string name, Action test) { test(); passed++; Console.WriteLine("PASS " + name); }
void Throws(Action action) {
    try { action(); } catch (InvalidOperationException) { return; }
    throw new Exception("Expected failure");
}
void Wait(ManualResetEventSlim value) { Check(value.Wait(5000)); }
Case("exclusive preparation", () => {
    var owner = new EmbeddedSessionCoordinator(); int won = 0;
    Parallel.For(0, 32, _ => { if (owner.Prepare() > 0) Interlocked.Increment(ref won); });
    Check(won == 1 && owner.State == 1);
});
Case("stop before run never launches", () => {
    var owner = new EmbeddedSessionCoordinator(); long id = owner.Prepare();
    Check(owner.Stop(id));
    Check(owner.Run(id, () => throw new Exception("Must not launch")) == 0 && owner.State == 0);
});
Case("cancel prepared reservation", () => {
    var owner = new EmbeddedSessionCoordinator(); long id = owner.Prepare();
    Check(owner.CancelPrepared(id) && !owner.CancelPrepared(id));
    Check(owner.Run(id, () => 0) == 2 && owner.Prepare() > id);
});
Case("generation rejects stale stop and pause", () => {
    var owner = new EmbeddedSessionCoordinator(); long old = owner.Prepare();
    Check(owner.Run(old, () => 0) == 0); long id = owner.Prepare();
    Check(!owner.Stop(old) && !owner.Pause(old, true) && !owner.CancelPrepared(old));
    Check(owner.State == 1 && owner.Run(id, () => 7) == 7 && owner.State == 0);
});
Case("one executing owner until completion", () => {
    var owner = new EmbeddedSessionCoordinator(); long id = owner.Prepare();
    using var entered = new ManualResetEventSlim(); using var finish = new ManualResetEventSlim();
    var task = Task.Run(() => owner.Run(id, () => { entered.Set(); Wait(finish); return 0; }));
    Wait(entered);
    Check(owner.Prepare() < 0 && owner.Run(id, () => 0) == 2 && !owner.CancelPrepared(id));
    owner.Stop(id); Check(owner.State == 3 && owner.Prepare() < 0);
    finish.Set(); Check(task.GetAwaiter().GetResult() == 0 && owner.State == 0);
});
Case("early stop delivered when controls appear", () => {
    var owner = new EmbeddedSessionCoordinator(); long id = owner.Prepare(); int stops = 0;
    Check(owner.Run(id, () => {
        owner.Stop(id); owner.PublishControls(() => stops++, _ => throw new Exception());
        Check(!owner.Pause(id, true)); owner.WithdrawControls(); owner.Stop(id); return 0;
    }) == 0 && stops == 1);
});
Case("pause and withdrawn controls", () => {
    var owner = new EmbeddedSessionCoordinator(); long id = owner.Prepare(); bool paused = false;
    Check(owner.Run(id, () => {
        owner.PublishControls(() => {}, p => paused = p);
        Check(owner.Pause(id, true) && paused && owner.Pause(id, false) && !paused);
        owner.WithdrawControls(); Check(!owner.Pause(id, true)); return 0;
    }) == 0);
});
Case("pause during startup is applied before the guest executes", () => {
    var owner = new EmbeddedSessionCoordinator(); long id = owner.Prepare(); bool paused = false;
    Check(owner.Pause(id, true));
    Check(owner.Run(id, () => {
        owner.PublishControls(() => {}, value => paused = value);
        Check(paused && owner.Pause(id, false) && !paused);
        owner.WithdrawControls(); Check(!owner.Pause(id, true)); return 0;
    }) == 0);
    long next = owner.Prepare();
    Check(!owner.Pause(id, true));
    Check(owner.Run(next, () => { owner.PublishControls(() => {}, value => paused = value); Check(!paused); return 0; }) == 0);
});
Case("failure quarantines and preserves diagnostic", () => {
    var owner = new EmbeddedSessionCoordinator(); long id = owner.Prepare();
    Check(owner.Run(id, () => throw new InvalidOperationException("sentinel failure")) == 3);
    Check(owner.State == 4 && owner.LastFailure.Contains("sentinel failure") && owner.Prepare() < 0);
    Check(!owner.Stop(id) && owner.Run(id, () => 0) == 2);
});
Case("many clean game sessions", () => {
    var owner = new EmbeddedSessionCoordinator(); long previous = 0;
    for (int i = 0; i < 100; i++) {
        long id = owner.Prepare(); Check(id > previous);
        Check(owner.Run(id, () => 0) == 0 && owner.State == 0); previous = id;
    }
});
Case("stop during load still services and retires the already-created guest", () => {
    var life = new EmbeddedWindowLifetime(); life.RequestStop();
    using var ready = new ManualResetEventSlim();
    bool guestStopped = false, gpuReleased = false;
    life.Run(() => throw new Exception("Stopped input must not run"), () => {
        Check(life.RenderAllowed && !life.InputAllowed);
        ready.Set();
        while (life.RenderAllowed) Thread.Yield();
        Check(guestStopped);
    }, () => {
        Wait(ready); // The real guest can wait for renderer initialization.
        guestStopped = true;
    }, () => { Check(guestStopped); gpuReleased = true; });
    int releases = 0; life.Dispose(() => releases++); life.Dispose(() => releases++);
    Check(guestStopped && gpuReleased && releases == 1 && !life.InputAllowed && !life.RenderAllowed);
});
Case("guest stops before GPU release and worker join", () => {
    var life = new EmbeddedWindowLifetime(); using var rendered = new ManualResetEventSlim();
    int phase = 0; int gpuThread = 0;
    life.Run(() => { Wait(rendered); life.RequestStop(); }, () => {
        gpuThread = Environment.CurrentManagedThreadId; rendered.Set();
        while (life.RenderAllowed) Thread.Yield();
        Check(Volatile.Read(ref phase) == 1);
    }, () => { Check(life.RenderAllowed && !life.InputAllowed); Volatile.Write(ref phase, 1); }, () => {
        Check(phase == 1 && Environment.CurrentManagedThreadId == gpuThread); phase = 2;
    });
    life.Dispose(() => { Check(phase == 2 && !life.RenderAllowed); phase = 3; });
    Check(phase == 3);
});
Case("stop releases a paused render worker", () => {
    var life = new EmbeddedWindowLifetime(); life.SetPaused(true);
    using var waiting = new ManualResetEventSlim(); bool resumed = false;
    life.Run(() => { Wait(waiting); life.RequestStop(); }, () => {
        waiting.Set(); life.WaitUntilResumed(); resumed = true;
        while (life.RenderAllowed) Thread.Yield();
    }, () => {}, () => {});
    Check(resumed); life.Dispose(() => {});
});
Case("render exception joins and propagates", () => {
    var life = new EmbeddedWindowLifetime(); bool guest = false, gpu = false;
    Throws(() => life.Run(() => { while (life.InputAllowed) Thread.Yield(); },
        () => throw new InvalidOperationException("GPU sentinel"), () => guest = true, () => { Check(guest); gpu = true; }));
    Check(guest && gpu); life.Dispose(() => {});
});
Case("input exception still stops guest and joins GPU", () => {
    var life = new EmbeddedWindowLifetime(); bool guest = false, gpu = false;
    Throws(() => life.Run(() => throw new InvalidOperationException("input sentinel"),
        () => { while (life.RenderAllowed) Thread.Yield(); }, () => guest = true, () => { Check(guest); gpu = true; }));
    Check(guest && gpu); life.Dispose(() => {});
});
Case("guest stop failure joins worker and retains unsafe resources", () => {
    var life = new EmbeddedWindowLifetime(); bool gpu = false;
    Throws(() => life.Run(() => {}, () => { while (life.RenderAllowed) Thread.Yield(); },
        () => throw new InvalidOperationException("guest sentinel"), () => gpu = true));
    Check(!gpu && life.GuestStopFailed && !life.RenderAllowed);
    Throws(() => life.Dispose(() => throw new Exception("Released resources with unproven guest termination")));
});
Case("GPU release failure is surfaced once", () => {
    var life = new EmbeddedWindowLifetime(); int attempts = 0;
    Throws(() => life.Run(() => {}, () => { while (life.RenderAllowed) Thread.Yield(); }, () => {},
        () => { attempts++; throw new InvalidOperationException("release sentinel"); }));
    Check(attempts == 1); life.Dispose(() => {});
});
Case("live worker cannot be disposed", () => {
    var life = new EmbeddedWindowLifetime(); using var entered = new ManualResetEventSlim(); using var finish = new ManualResetEventSlim();
    var task = Task.Run(() => life.Run(() => { entered.Set(); Wait(finish); },
        () => { while (life.RenderAllowed) Thread.Yield(); }, () => {}, () => {}));
    Wait(entered); Throws(() => life.Dispose(() => throw new Exception("unsafe disposal")));
    life.RequestStop(); finish.Set(); task.GetAwaiter().GetResult(); life.Dispose(() => {});
});
Case("disposed window rejects reuse and ignores late controls", () => {
    var life = new EmbeddedWindowLifetime(); int releases = 0;
    life.Dispose(() => releases++); life.RequestStop(); life.SetPaused(true); life.Dispose(() => releases++);
    Throws(() => life.Run(() => {}, () => {}, () => {}, () => {})); Check(releases == 1);
});
Case("window cannot execute twice", () => {
    var life = new EmbeddedWindowLifetime(); life.RequestStop();
    life.Run(() => {}, () => {}, () => {}, () => {});
    Throws(() => life.Run(() => {}, () => {}, () => {}, () => {})); life.Dispose(() => {});
});
Case("parallel stop requests are harmless", () => {
    var life = new EmbeddedWindowLifetime();
    life.Run(() => Parallel.For(0, 100, _ => life.RequestStop()),
        () => { while (life.RenderAllowed) Thread.Yield(); }, () => {}, () => {});
    life.Dispose(() => {});
});
Case("generation gates prepared and stale input", () => {
    var owner = new EmbeddedSessionCoordinator(); long id=owner.Prepare(); int writes=0;
    Check(owner.WithInputs(id,()=>writes++) && !owner.WithInputs(id+1,()=>writes++));
    owner.CancelPrepared(id); Check(!owner.WithInputs(id,()=>writes++));
    long next=owner.Prepare(); Check(!owner.WithInputs(id,()=>writes++) && owner.WithInputs(next,()=>writes++));
    Check(writes==2); owner.CancelPrepared(next);
});
Case("withdrawal and stop seal input before resource cleanup", () => {
    var owner=new EmbeddedSessionCoordinator();long id=owner.Prepare();int writes=0;
    Check(owner.Run(id,()=>{
        owner.PublishControls(()=>{},_=>{}); Check(owner.WithInputs(id,()=>writes++));
        owner.WithdrawControls(); Check(!owner.WithInputs(id,()=>writes++));
        owner.PublishControls(()=>{},_=>{}); Check(owner.WithInputs(id,()=>writes++));
        owner.Stop(id); Check(!owner.WithInputs(id,()=>writes++)); return 0;
    })==0 && writes==2 && !owner.WithInputs(id,()=>writes++));
});
Case("stop waits for in-flight input to finish", () => {
    var owner=new EmbeddedSessionCoordinator();long id=owner.Prepare();
    using var entered=new ManualResetEventSlim();using var release=new ManualResetEventSlim();
    using var stopping=new ManualResetEventSlim();
    var input=Task.Run(()=>owner.WithInputs(id,()=>{entered.Set();Wait(release);}));Wait(entered);
    var stop=Task.Run(()=>{stopping.Set();return owner.Stop(id);});Wait(stopping);Check(!stop.IsCompleted);
    release.Set();Check(input.GetAwaiter().GetResult() && stop.GetAwaiter().GetResult());
    Check(!owner.WithInputs(id,()=>throw new Exception()));owner.CancelPrepared(id);
});
Console.WriteLine($"Embedded session and window lifetime: {passed} cases passed.");
''')
    subprocess.run(['dotnet', 'run', '--project', str(work / 'Session.csproj'), '-c', 'Release'], check=True, timeout=120)
