// Fixture of melonx_pause_guest_threads_test.py: the real NoteGuestThreadsAtPause (Horizon.cs) and KProcess.SnapshotThreads
// extracted from the candidate, run with doubles of the kernel types. The critical section double throws if the record
// enters or leaves it (that would select threads); thread doubles count every write after construction.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common.Logging;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.HLE.HOS.Kernel.Common;

namespace Ryujinx.Common.Logging
{
    enum LogClass { Kernel }
    sealed class Sink { public readonly List<string> Lines = new(); public void Print(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Warning; }
}
namespace Ryujinx.Common
{
    static class PerformanceCounter { public static long TicksPerSecond = 1000; public static long ElapsedTicks = 100000; }
    static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
            => Records.Add($"{stage} {status} {code} {detail}");
    }
}
namespace Ryujinx.HLE.HOS.Kernel.Common
{
    class KSynchronizationObject { }
    class KEvent : KSynchronizationObject { }
}
namespace Ryujinx.HLE.HOS.Kernel.Threading
{
    using Ryujinx.HLE.HOS.Kernel.Common;
    [Flags] enum ThreadSchedState : ushort { LowMask = 0xf, ForcePauseMask = 0x1f0, ProcessPauseFlag = 1 << 4, None = 0, Paused = 1, Running = 2, TerminationPending = 3 }
    sealed class KCriticalSection
    {
        public object Lock { get; } = new();
        public void Enter() => throw new InvalidOperationException("the record entered the critical section");
        public void Leave() => throw new InvalidOperationException("the record left the critical section");
    }
    sealed class KScheduler { public KThread CurrentThread { get; set; } }
    sealed class KThread
    {
        public int Writes;
        private string _name; private bool _sealed;
        private void W() { if (_sealed) Interlocked.Increment(ref Writes); }
        private ThreadSchedState _flags; public ThreadSchedState SchedFlags { get => _flags; set { W(); _flags = value; } }
        public Thread HostThread { get; set; }
        public ulong ThreadUid { get; set; }
        public int DynamicPriority { get; set; }
        public int BasePriority { get; set; }
        public int ActiveCore { get; set; }
        public int CurrentCore { get; set; }
        public int PreferredCore { get; set; }
        public ulong AffinityMask { get; set; }
        public bool WaitingSync { get; set; }
        public ulong MutexAddress { get; set; }
        public bool WaitingInArbitration { get; set; }
        public long LastScheduledTime { get; set; }
        public KSynchronizationObject[] WaitSyncObjects { get; } = new KSynchronizationObject[64];
        public KThread(string name) { _name = name; }
        public void Seal() => _sealed = true;
        public string GetThreadName() => _name;
    }
}
namespace Ryujinx.HLE.HOS.Kernel.Process
{
    sealed class KProcess
    {
        private readonly object _threadingLock = new();
        private readonly LinkedList<KThread> _threads = new();
        public KProcess(IEnumerable<KThread> threads) { foreach (KThread t in threads) _threads.AddLast(t); }
//__SNAPSHOT__
    }
}
namespace Ryujinx.HLE.HOS
{
    sealed class KernelContext
    {
        public KCriticalSection CriticalSection { get; } = new();
        public KScheduler[] Schedulers { get; } = { new(), new(), new(), new() };
    }
    sealed class Horizon
    {
        public KernelContext KernelContext { get; } = new();
//__RECORD__
        public void Pause(KProcess process) => NoteGuestThreadsAtPause(process);
    }
}
static class Program
{
    static void Main()
    {
        var sink = new Sink(); Logger.Warning = sink;
        var horizon = new Ryujinx.HLE.HOS.Horizon();
        // 100000 ticks at 1000 per second: now = 100 s.
        KThread T(string name, ThreadSchedState state, long lastMs, int prio = 44, int core = 0)
            => new(name) { SchedFlags = state, DynamicPriority = prio, BasePriority = prio, ActiveCore = core, CurrentCore = core,
                           PreferredCore = core, AffinityMask = 0xF, LastScheduledTime = lastMs < 0 ? 0 : 100000 - lastMs, ThreadUid = 7 };
        var main = T("<MainThread>", ThreadSchedState.Running, 0, 28, 0);
        var bank = T("<AK::BankManager>", ThreadSchedState.Running, 12000, 44, 2);
        var brief = T("<TaskGraphThreadHP 2>", ThreadSchedState.Running, 20, 30, 1);
        var io = T("<AK::IOThread>", ThreadSchedState.Paused, 15000, 30, 2); io.WaitingSync = true; io.WaitSyncObjects[0] = new KEvent();
        var cv = T("<PoolThread 1>", ThreadSchedState.Paused, 3000); cv.MutexAddress = 0x8000;
        var arb = T("<RHIThread>", ThreadSchedState.Paused, 900); arb.WaitingInArbitration = true;
        var sleeper = T("<FAsyncLoadingThread>", ThreadSchedState.Paused, 400);
        var paused = T("<Paused>", ThreadSchedState.Running | ThreadSchedState.ProcessPauseFlag, 9000);
        var all = new List<KThread> { main, bank, brief, io, cv, arb, sleeper, paused };
        for (int i = 0; i < 70; i++) all.Add(T($"<Worker {i}>", ThreadSchedState.Paused, 100));
        all.ForEach(t => t.Seal());
        horizon.KernelContext.Schedulers[0].CurrentThread = main;
        var process = new KProcess(all);
        for (int i = 0; i < 5; i++) horizon.Pause(process);
        var report = new Dictionary<string, object>
        {
            ["lines"] = sink.Lines.Count,
            ["firstLines"] = sink.Lines.Take(8).ToList(),
            ["records"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records,
            ["writes"] = all.Sum(t => t.Writes),
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
