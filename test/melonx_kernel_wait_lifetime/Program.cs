using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Ryujinx.HLE.HOS.Kernel;
using Ryujinx.HLE.HOS.Kernel.Common;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.HLE.HOS.Kernel.SupervisorCall;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.Horizon.Common;

namespace Ryujinx.HLE.HOS.Kernel
{
    class KernelContext
    {
        internal readonly ConcurrentDictionary<string, KAutoObject> AutoObjectNames = new();
        internal readonly CriticalSection CriticalSection = new();
        internal readonly TimeManager TimeManager = new();
        internal readonly KSynchronization Synchronization;
        public KernelContext() { Synchronization = new(this); }
    }
    static class KernelStatic
    {
        [ThreadStatic] internal static KThread Thread;
        [ThreadStatic] internal static KProcess Process;
        public static KThread GetCurrentThread() => Thread;
        public static KProcess GetCurrentProcess() => Process;
    }
    class CriticalSection
    {
        internal int Depth;
        internal Action OnPark;
        public void Enter() => Depth++;
        public void Leave()
        {
            if (--Depth < 0) throw new Exception("Unbalanced critical section");
            if (Depth == 0 && KernelStatic.Thread?.WaitingSync == true && OnPark != null)
            {
                Action action = OnPark;
                OnPark = null;
                action();
            }
        }
    }
    class TimeManager
    {
        internal int Scheduled, Unscheduled;
        internal long Timeout;
        public void ScheduleFutureInvocation(KThread thread, long timeout) { Scheduled++; Timeout = timeout; }
        public void UnscheduleFutureInvocation(KThread thread) { Unscheduled++; }
    }
}
namespace Ryujinx.HLE.HOS.Kernel.Common
{
    static class KTimeManager { public const long DefaultTimeIncrementNanoseconds = 105; }
}
namespace Ryujinx.HLE.HOS.Kernel.Threading
{
    class KThread : KSynchronizationObject
    {
        public const int MaxWaitSyncObjects = 64;
        public readonly KSynchronizationObject[] WaitSyncObjects = new KSynchronizationObject[64];
        public bool TerminationRequested, SyncCancelled, WaitingSync;
        public KSynchronizationObject SignaledObj;
        public Result ObjSyncResult;
        public ThreadSchedState SchedFlags = ThreadSchedState.Running;
        public int Reschedules;
        public KThread(KernelContext context) : base(context) { }
        public void Reschedule(ThreadSchedState state) { SchedFlags = state; Reschedules++; }
    }
}
namespace Ryujinx.HLE.HOS.Kernel.Process
{
    class HandleTable
    {
        public readonly Dictionary<int, KSynchronizationObject> Objects = new();
        public T GetObject<T>(int handle) where T : class => Objects.TryGetValue(handle, out var obj) ? obj as T : null;
    }
    class KProcess { public readonly HandleTable HandleTable = new(); }
}

class ProbeObject : KSynchronizationObject
{
    internal bool Signaled, ThrowOnRead, ThrowOnDestroy;
    internal int Destroyed;
    internal ProbeObject(KernelContext context) : base(context) { }
    public override bool IsSignaled() => ThrowOnRead ? throw new InvalidOperationException("Injected read failure") : Signaled;
    protected override void Destroy() { Destroyed++; if (ThrowOnDestroy) throw new InvalidOperationException("Injected release failure"); }
}

static class Program
{
    static int _checks, _cases;
    static bool _candidate;
    static readonly StringBuilder Functional = new();
    static readonly FieldInfo RefCount = typeof(KAutoObject).GetField("_referenceCount", BindingFlags.NonPublic | BindingFlags.Instance);
    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }
    static int Count(KAutoObject obj) => (int)RefCount.GetValue(obj);
    static void Collect() { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
    static (KernelContext context, KThread thread, KProcess process, Syscall syscall) Setup()
    {
        KernelContext context = new();
        KThread thread = new(context);
        KProcess process = new();
        KernelStatic.Thread = thread; KernelStatic.Process = process;
        return (context, thread, process, new Syscall(context));
    }
    static void Scenarios()
    {
        foreach (int count in new[] { 0, 1, 2, 16, 64 })
        foreach (long timeout in new long[] { -1, 0, 90 })
        foreach (string mode in new[] { "timeout", "signal", "cancel", "terminate", "invalid", "duplicates", "already" })
        {
            var (context, thread, process, syscall) = Setup();
            ProbeObject[] objects = Enumerable.Range(0, count).Select(_ => new ProbeObject(context)).ToArray();
            int[] handles = Enumerable.Range(1, count).ToArray();
            for (int i = 0; i < count; i++) process.HandleTable.Objects[i + 1] = mode == "duplicates" ? objects[0] : objects[i];
            if (mode == "already" && count > 0) objects[count / 2].Signaled = true;
            if (mode == "invalid" && count > 0) handles[count / 2] = -1;
            if (mode == "cancel") thread.SyncCancelled = true;
            if (mode == "terminate") thread.TerminationRequested = true;
            context.CriticalSection.OnPark = () =>
            {
                if ((mode == "signal" || mode == "duplicates") && count > 0)
                {
                    ProbeObject obj = mode == "duplicates" ? objects[0] : objects[count / 2];
                    obj.Signaled = true;
                    context.Synchronization.SignalObject(obj);
                }
                else thread.Reschedule(ThreadSchedState.Running);
            };
            Result result = syscall.WaitSynchronization(out int index, handles, timeout);
            Result expected;
            int expectedIndex;
            if (mode == "invalid" && count > 0) { expected = KernelResult.InvalidHandle; expectedIndex = 0; }
            else if (mode == "already" && count > 0) { expected = Result.Success; expectedIndex = count / 2; }
            else if (timeout == 0) { expected = KernelResult.TimedOut; expectedIndex = 0; }
            else if (mode == "terminate") { expected = KernelResult.ThreadTerminating; expectedIndex = 0; }
            else if (mode == "cancel") { expected = KernelResult.Cancelled; expectedIndex = 0; }
            else if ((mode == "signal" || mode == "duplicates") && count > 0)
            { expected = Result.Success; expectedIndex = mode == "duplicates" ? count - 1 : count / 2; }
            else { expected = KernelResult.TimedOut; expectedIndex = -1; }
            Check(result == expected && index == expectedIndex, $"Result {mode}/{count}/{timeout}: {result} {index}");
            Check(context.CriticalSection.Depth == 0, "Critical section left held");
            Check(context.TimeManager.Scheduled == context.TimeManager.Unscheduled, "Unbalanced timed wait");
            foreach (ProbeObject obj in objects)
            {
                Check(obj.WaitingThreads.Count == 0, "Waiter left linked");
                Check(Count(obj) == 1, "Native reference count changed");
            }
            if (_candidate)
            {
                Check(thread.WaitSyncObjects.All(obj => obj == null), "Wait slot retained object");
                Check(thread.SignaledObj == null, "Completed wait retained signal result");
            }
            Functional.AppendJoin(':', mode, count, timeout, result.ErrorCode, index, thread.Reschedules,
                context.TimeManager.Scheduled, context.TimeManager.Unscheduled).Append(';');
            _cases++;
        }
        var (_, maximumThread, _, maximumSyscall) = Setup();
        Check(maximumSyscall.WaitSynchronization(out int maximumIndex, new int[65], 0) == KernelResult.MaximumExceeded && maximumIndex == 0, "Maximum-handle validation changed");
        Check(maximumThread.WaitSyncObjects.All(obj => obj == null), "Rejected count wrote slots");
        _cases++;
    }
    static void NodeOrderAndReuse()
    {
        for (int count = 1; count <= 64; count++)
        {
            var (context, _, _, _) = Setup();
            ProbeObject obj = new(context);
            KThread[] threads = Enumerable.Range(0, count).Select(_ => new KThread(context)).ToArray();
            LinkedListNode<KThread>[] nodes = threads.Select(obj.AddWaitingThread).ToArray();
            Check(obj.WaitingThreads.SequenceEqual(threads), "Registration order changed");
            for (int i = count - 1; i >= 0; i--)
            {
                obj.RemoveWaitingThread(nodes[i]);
                Check(nodes[i].List == null, "Released node remains linked");
                if (_candidate) Check(nodes[i].Value == null, "Pool retained thread");
            }
            Check(obj.WaitingThreads.Count == 0, "List not empty after reverse removals");
            _cases++;
        }
        Parallel.For(0, 8, worker =>
        {
            KernelContext context = new();
            ProbeObject obj = new(context);
            KThread thread = new(context);
            for (int i = 0; i < 500; i++)
            {
                var node = obj.AddWaitingThread(thread);
                if (node.Value != thread || node.List != obj.WaitingThreads) throw new Exception("Cross-thread pool ownership");
                obj.RemoveWaitingThread(node);
                if (node.List != null || (_candidate && node.Value != null)) throw new Exception("Pool return ownership");
            }
        });
        _cases += 8;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference NodeRetention()
    {
        KernelContext context = new();
        ProbeObject obj = new(context);
        KThread thread = new(context);
        var node = obj.AddWaitingThread(thread);
        obj.RemoveWaitingThread(node);
        return new WeakReference(context);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (WeakReference target, KThread root) SlotRetention()
    {
        var (context, thread, process, syscall) = Setup();
        ProbeObject target = new(context) { Signaled = true };
        process.HandleTable.Objects[1] = target;
        Check(syscall.WaitSynchronization(out _, new[] { 1 }, 0) == Result.Success, "Retention setup");
        process.HandleTable.Objects.Clear(); target.DecrementReferenceCount();
        KernelStatic.Thread = null; KernelStatic.Process = null;
        return (new WeakReference(target), thread);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (WeakReference target, KThread root) SignalRetention()
    {
        var (context, thread, _, _) = Setup();
        ProbeObject target = new(context);
        context.CriticalSection.OnPark = () => { target.Signaled = true; context.Synchronization.SignalObject(target); };
        Check(context.Synchronization.WaitFor(new KSynchronizationObject[] { target }, -1, out int index) == Result.Success && index == 0, "Signal setup");
        KernelStatic.Thread = null; KernelStatic.Process = null;
        return (new WeakReference(target), thread);
    }
    static void ExceptionalCleanup()
    {
        var (context, thread, process, syscall) = Setup();
        ProbeObject a = new(context), b = new(context) { ThrowOnRead = true };
        process.HandleTable.Objects[1] = a; process.HandleTable.Objects[2] = b;
        try { syscall.WaitSynchronization(out _, new[] { 1, 2 }, -1); throw new Exception("Expected read failure"); }
        catch (InvalidOperationException) { }
        Check(Count(a) == (_candidate ? 1 : 2) && Count(b) == (_candidate ? 1 : 2), "Failure lease cleanup");
        Check(thread.WaitSyncObjects.Take(2).All(obj => obj == null) == _candidate, "Failure slots");
        // Scheduler/IsSignaled failure leaves its original critical-section behaviour unchanged.
        Check(context.CriticalSection.Depth == 1, "Unexpected scheduler redesign");
        _cases++;

        (context, thread, process, syscall) = Setup();
        a = new(context) { ThrowOnDestroy = true }; b = new(context);
        process.HandleTable.Objects[1] = a; process.HandleTable.Objects[2] = b;
        context.CriticalSection.OnPark = () =>
        {
            a.DecrementReferenceCount(); b.DecrementReferenceCount();
            process.HandleTable.Objects.Clear(); thread.Reschedule(ThreadSchedState.Running);
        };
        try { syscall.WaitSynchronization(out _, new[] { 1, 2 }, -1); throw new Exception("Expected release failure"); }
        catch (InvalidOperationException) { }
        Check(a.Destroyed == 1 && Count(b) == 1, "Release failure semantics changed");
        Check(thread.WaitSyncObjects.Take(2).All(obj => obj == null) == _candidate, "Release-exception slots retained");
        _cases++;

        // Complete a wide wait and then an invalid short one on the same thread.
        (context, thread, process, syscall) = Setup();
        for (int i = 1; i <= 64; i++) process.HandleTable.Objects[i] = new ProbeObject(context);
        syscall.WaitSynchronization(out _, Enumerable.Range(1, 64).ToArray(), 0);
        syscall.WaitSynchronization(out _, new[] { 1, -1 }, 0);
        Check(thread.WaitSyncObjects.All(obj => obj == null) == _candidate, "Short/invalid wait retained old slots");
        foreach (var obj in process.HandleTable.Objects.Values) Check(Count(obj) == 1, "Invalid handle rollback");
        _cases++;
    }
    public static void Main(string[] args)
    {
        _candidate = args[0] == "candidate";
        Scenarios(); NodeOrderAndReuse(); ExceptionalCleanup();
        KernelStatic.Thread = null; KernelStatic.Process = null;
        WeakReference node = NodeRetention();
        Collect();
        bool retainedNodes = node.IsAlive;
        var slots = SlotRetention();
        var signal = SignalRetention();
        Collect();
        bool retainedSlots = slots.target.IsAlive, retainedSignal = signal.target.IsAlive;
        Check(retainedNodes != _candidate, "Static waiter pool retention reproduction");
        Check(retainedSlots != _candidate, "Thread wait-slot retention reproduction");
        Check(retainedSignal != _candidate, "Signal-result retention reproduction");
        GC.KeepAlive(slots.root); GC.KeepAlive(signal.root);
        Console.WriteLine(JsonSerializer.Serialize(new {
            variant = args[0], checks = _checks, scenarios = _cases,
            functionalDigest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Functional.ToString()))),
            retainedWaitNodes = retainedNodes, retainedWaitSlots = retainedSlots,
            retainedSignaledObject = retainedSignal, concurrentPoolCycles = 4000,
            schedulerExecuted = false, productionWaitAlgorithmExecuted = true,
        }));
    }
}
