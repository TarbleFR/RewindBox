using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common;
using Ryujinx.Common.PreciseSleep;
using Ryujinx.HLE.HOS.Kernel;
using Ryujinx.HLE.HOS.Kernel.Common;

namespace Ryujinx.Common
{
    static class PerformanceCounter
    {
        internal static long Now;
        public const long TicksPerSecond = 1_000_000_000;
        public static long ElapsedTicks => Volatile.Read(ref Now);
    }
}
namespace Ryujinx.HLE.HOS.Kernel
{
    class KernelContext { public readonly CriticalSection CriticalSection = new(); }
    class CriticalSection { public readonly object Lock = new(); }
}
namespace Ryujinx.Common.PreciseSleep
{
    static class PreciseSleepHelper
    {
        internal static TestSleepEvent LastCreated;
        public static IPreciseSleepEvent CreateEvent()
        {
            TestSleepEvent value = new();
            Volatile.Write(ref LastCreated, value);
            return value;
        }
        public static void SpinWaitUntilTimePoint(long timePoint, ref long wake)
            => throw new Exception("Controlled event must perform its wait");
    }
    class TestSleepEvent : IPreciseSleepEvent
    {
        private readonly object _gate = new();
        private bool _signaled;
        internal readonly ManualResetEventSlim EnteredWait = new();
        internal readonly ManualResetEventSlim Closed = new();
        internal Action<long> BeforeSleepUntil;
        internal bool Noop;
        public long AdjustTimePoint(long timePoint, long timeoutNs) => timePoint;
        public bool SleepUntil(long timePoint)
        {
            BeforeSleepUntil?.Invoke(timePoint);
            Wait(timePoint);
            return true;
        }
        public void Sleep() => Wait(null);
        private void Wait(long? timePoint)
        {
            if (Noop) return;
            lock (_gate)
            {
                EnteredWait.Set();
                while (!_signaled && (!timePoint.HasValue || PerformanceCounter.ElapsedTicks < timePoint.Value))
                    Monitor.Wait(_gate);
                _signaled = false;
            }
        }
        public void Signal()
        {
            if (Noop) return;
            lock (_gate) { _signaled = true; Monitor.PulseAll(_gate); }
        }
        public void Dispose() { Closed.Set(); }
    }
}

class TimerObject : IKFutureSchedulerObject
{
    internal readonly int Id;
    internal readonly KernelContext Context;
    internal int Calls;
    internal Action OnTimeUp;
    internal TimerObject(int id, KernelContext context) { Id = id; Context = context; }
    public void TimeUp()
    {
        if (!Monitor.IsEntered(Context.CriticalSection.Lock)) throw new Exception("Timer callback outside kernel lock");
        Interlocked.Increment(ref Calls);
        OnTimeUp?.Invoke();
    }
}

static class Program
{
    static readonly Type TimerType = typeof(KTimeManager);
    static readonly BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
    static readonly MethodInfo GetNextMethod = TimerType.GetMethod("GetNextWaitingObject", Private);
    static readonly FieldInfo Waiting = TimerType.GetField("_waitingObjects", Private);
    static readonly Type WaitingType = Waiting.FieldType.GenericTypeArguments[0];
    static readonly MethodInfo RemoveMethod = Waiting.FieldType.GetMethod("Remove");
    static readonly StringBuilder Trace = new();
    static int _checks, _cases;
    static bool _candidate;
    static void Check(bool condition, string message) { _checks++; if (!condition) throw new Exception(message); }
    static void SetField(KTimeManager manager, string name, object value) => TimerType.GetField(name, Private)?.SetValue(manager, value);
    static KTimeManager Manual(KernelContext context)
    {
        KTimeManager manager = (KTimeManager)RuntimeHelpers.GetUninitializedObject(TimerType);
        SetField(manager, "_context", context);
        SetField(manager, "_waitingObjects", Activator.CreateInstance(Waiting.FieldType));
        SetField(manager, "_waitEvent", new TestSleepEvent { Noop = true });
        SetField(manager, "_waitingEpoch", new object());
        return manager;
    }
    static object Next(KTimeManager manager) => GetNextMethod.Invoke(manager, null);
    static bool Valid(object next) => next != null && (!_candidate || (bool)WaitingType.GetProperty("IsValid").GetValue(next));
    static TimerObject Target(object next) => (TimerObject)WaitingType.GetProperty("Object").GetValue(next);
    static long TimePoint(object next) => (long)WaitingType.GetProperty("TimePoint").GetValue(next);
    static bool Remove(KTimeManager manager, object next) => (bool)RemoveMethod.Invoke(Waiting.GetValue(manager), new[] { next });
    static void ListCases()
    {
        Random random = new(831760);
        foreach (int count in new[] { 0, 1, 2, 8, 64, 256 })
        for (int run = 0; run < 20; run++)
        {
            KernelContext context = new(); KTimeManager manager = Manual(context);
            PerformanceCounter.Now = run;
            List<(TimerObject obj, long deadline)> expected = new();
            for (int i = 0; i < count; i++)
            {
                TimerObject obj = new(i, context);
                long delay = random.Next(1, 9);
                manager.ScheduleFutureInvocation(obj, delay);
                expected.Add((obj, run + delay));
            }
            foreach (var item in expected.OrderBy(x => x.deadline))
            {
                object next = Next(manager);
                Check(Valid(next) && ReferenceEquals(Target(next), item.obj) && TimePoint(next) == item.deadline, "Timer ordering/deadline changed");
                Check(Remove(manager, next), "Live arm not removable");
                Check(!Remove(manager, next), "Arm removed twice");
                Trace.Append(item.obj.Id).Append(':').Append(item.deadline).Append(';');
            }
            Check(!Valid(Next(manager)), "Empty timer list selected an arm");
            _cases++;
        }
        foreach (bool rollover in new[] { false, true })
        {
            KernelContext context = new(); KTimeManager manager = Manual(context);
            TimerObject obj = new(1, context);
            PerformanceCounter.Now = 0;
            if (rollover) SetField(manager, "_waitingSequence", ulong.MaxValue - 1);
            manager.ScheduleFutureInvocation(obj, 20);
            object old = Next(manager);
            manager.UnscheduleFutureInvocation(obj);
            if (rollover)
            {
                manager.ScheduleFutureInvocation(new TimerObject(2, context), 40);
                SetField(manager, "_waitingSequence", ulong.MaxValue - 1);
            }
            manager.ScheduleFutureInvocation(obj, 20);
            Check(!Remove(manager, old), "Captured cancelled arm removed a rearm with same target/deadline");
            Check(Remove(manager, Next(manager)), "Rearmed timer disappeared");
            _cases++;
        }
        // The original saturating deadline arithmetic, including its overflow boundary.
        foreach (long start in new[] { 0L, 4L, long.MaxValue - 10 })
        foreach (long delay in new[] { 1L, 9L, 20L, long.MaxValue })
        {
            KernelContext context = new(); KTimeManager manager = Manual(context);
            PerformanceCounter.Now = start;
            manager.ScheduleFutureInvocation(new TimerObject(0, context), delay);
            long actual = TimePoint(Next(manager));
            long expected = unchecked(start + KTimeManager.ConvertNanosecondsToHostTicks(delay));
            if (expected < start) expected = long.MaxValue;
            Check(actual == expected, "Overflow deadline arithmetic changed");
            Trace.Append(actual).Append(';'); _cases++;
        }
    }
    static (KTimeManager manager, TestSleepEvent ev) Worker(KernelContext context)
    {
        Volatile.Write(ref PreciseSleepHelper.LastCreated, null);
        KTimeManager manager = new(context);
        Check(SpinWait.SpinUntil(() => Volatile.Read(ref PreciseSleepHelper.LastCreated)?.EnteredWait.IsSet == true, 5000), "Worker did not enter its wait");
        return (manager, PreciseSleepHelper.LastCreated);
    }
    static void Close(KTimeManager manager, TestSleepEvent ev)
    {
        manager.Dispose();
        Check(ev.Closed.Wait(5000), "Timer worker did not terminate");
    }
    static void WorkerRearm(bool rollover)
    {
        KernelContext context = new(); PerformanceCounter.Now = 0;
        var (manager, ev) = Worker(context);
        ConcurrentQueue<int> order = new();
        TimerObject a = new(1, context), b = new(2, context);
        a.OnTimeUp = () => order.Enqueue(1); b.OnTimeUp = () => order.Enqueue(2);
        using ManualResetEventSlim captured = new(), resume = new();
        ev.BeforeSleepUntil = _ => { ev.BeforeSleepUntil = null; captured.Set(); if (!resume.Wait(5000)) throw new Exception("Rearm worker gate timed out"); };
        if (rollover) SetField(manager, "_waitingSequence", ulong.MaxValue - 1);
        manager.ScheduleFutureInvocation(a, 10);
        Check(captured.Wait(5000), "Worker did not capture first arm");
        manager.UnscheduleFutureInvocation(a);
        manager.ScheduleFutureInvocation(b, 10);
        if (rollover) SetField(manager, "_waitingSequence", ulong.MaxValue - 1);
        manager.ScheduleFutureInvocation(a, 10);
        Volatile.Write(ref PerformanceCounter.Now, 10);
        resume.Set(); ev.Signal();
        Check(SpinWait.SpinUntil(() => order.Count == 2, 5000), "Rearmed callbacks not executed");
        Check(order.SequenceEqual(new[] { 2, 1 }), "Old captured arm consumed later rearm or equal-deadline order changed");
        Check(a.Calls == 1 && b.Calls == 1, "Duplicate timer callback");
        Trace.AppendJoin(',', order).Append(';');
        Close(manager, ev); _cases++;
    }
    static void WorkerConcurrentAndDispose()
    {
        KernelContext context = new(); PerformanceCounter.Now = 0;
        var (manager, ev) = Worker(context);
        TimerObject[] targets = Enumerable.Range(0, 2048).Select(i => new TimerObject(i, context)).ToArray();
        Parallel.For(0, targets.Length, i =>
        {
            manager.ScheduleFutureInvocation(targets[i], 100_000_000);
            if ((i & 1) == 0) { manager.UnscheduleFutureInvocation(targets[i]); manager.ScheduleFutureInvocation(targets[i], 100_000_000); }
        });
        Volatile.Write(ref PerformanceCounter.Now, 100_000_000); ev.Signal();
        Check(SpinWait.SpinUntil(() => targets.All(t => Volatile.Read(ref t.Calls) == 1), 5000), "Concurrent timer callbacks lost or duplicated");
        Close(manager, ev); _cases++;
        PerformanceCounter.Now = 0;
        (manager, ev) = Worker(context);
        TimerObject future = new(3, context);
        manager.ScheduleFutureInvocation(future, 1000);
        Close(manager, ev);
        Volatile.Write(ref PerformanceCounter.Now, 2000);
        Check(future.Calls == 0, "Termination dispatched a future arm"); _cases++;
    }
    static void WorkerCallbackRearm()
    {
        KernelContext context = new(); PerformanceCounter.Now = 0;
        var (manager, ev) = Worker(context);
        TimerObject target = new(4, context);
        target.OnTimeUp = () => { if (target.Calls < 3) manager.ScheduleFutureInvocation(target, 10); };
        manager.ScheduleFutureInvocation(target, 10);
        for (int i = 1; i <= 3; i++)
        {
            Volatile.Write(ref PerformanceCounter.Now, i * 10); ev.Signal();
            int expected = i;
            Check(SpinWait.SpinUntil(() => Volatile.Read(ref target.Calls) == expected, 5000), "Callback rearm lost");
            // Wait until the callback has actually scheduled before advancing time again.
            lock (context.CriticalSection.Lock) { }
        }
        Close(manager, ev); _cases++;
    }
    static (long bytes, double[] milliseconds, int operations, int slotBytes) Measure()
    {
        KernelContext context = new(); KTimeManager manager = Manual(context);
        TimerObject target = new(1, context);
        PerformanceCounter.Now = 0;
        for (int i = 0; i < 10_000; i++) { manager.ScheduleFutureInvocation(target, 1000); manager.UnscheduleFutureInvocation(target); }
        const int operations = 200_000;
        long start = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < operations; i++) { manager.ScheduleFutureInvocation(target, 1000); manager.UnscheduleFutureInvocation(target); }
        long bytes = GC.GetAllocatedBytesForCurrentThread() - start;
        double[] times = new double[5];
        for (int sample = 0; sample < times.Length; sample++)
        {
            long tick = Stopwatch.GetTimestamp();
            for (int i = 0; i < operations; i++) { manager.ScheduleFutureInvocation(target, 1000); manager.UnscheduleFutureInvocation(target); }
            times[sample] = Stopwatch.GetElapsedTime(tick).TotalMilliseconds;
        }
        int slotBytes = (int)typeof(Unsafe).GetMethod(nameof(Unsafe.SizeOf)).MakeGenericMethod(WaitingType).Invoke(null, null);
        return (bytes, times, operations, slotBytes);
    }
    public static void Main(string[] args)
    {
        _candidate = args[0] == "candidate";
        ListCases(); WorkerRearm(false); WorkerRearm(true); WorkerConcurrentAndDispose(); WorkerCallbackRearm();
        var measured = Measure();
        Console.WriteLine(JsonSerializer.Serialize(new {
            variant = args[0], checks = _checks, scenarios = _cases,
            functionalDigest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Trace.ToString()))),
            allocatedBytes = measured.bytes, armOperations = measured.operations,
            timingMilliseconds = measured.milliseconds, waitingSlotBytes = measured.slotBytes,
            concurrentWorkerCallbacks = 2048, productionWorkerExecuted = true,
            forcedSequenceRolloverExercised = _candidate,
        }));
    }
}
