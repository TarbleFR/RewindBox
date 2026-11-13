// Fixture for adapt_wait_spin_bound: the handoff the guest scheduler makes at every guest context switch
// (KScheduler.Schedule: reset its own SchedulerWaitEvent, set the next thread's, wait on its own), between two
// threads, with the event of the control (ManualResetEventSlim at the runtime's default spin) and of the candidate
// (the adapter's AdaptiveSpinEvent, its text unchanged, compiled next to this file).
// Per run: handoffs completed per second, process CPU time per handoff beyond the work itself, voluntary context
// switches per handoff, and the wake latency (from Set to the waiter's return) percentiles. The time a thread runs
// before handing over is fixed, or mixed (a share of short slices among long ones).
// Usage: fixture <control|bound|adaptive> <shortUs> <longUs> <shortPercent> <milliseconds>
//        fixture ring <milliseconds>   (correctness: a ring of eight threads, then a wait on an unset event)
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using Ryujinx.Common;

abstract class Evt { public abstract void Set(); public abstract void Reset(); public abstract void Wait(); }
sealed class Mres : Evt
{
    readonly ManualResetEventSlim _e;
    public Mres(int spin) { _e = spin < 0 ? new ManualResetEventSlim(false) : new ManualResetEventSlim(false, spin); }
    public override void Set() => _e.Set(); public override void Reset() => _e.Reset(); public override void Wait() => _e.Wait();
}
sealed class Adaptive : Evt
{
    public readonly AdaptiveSpinEvent E = new(false);
    public override void Set() => E.Set(); public override void Reset() => E.Reset(); public override void Wait() => E.Wait();
}

static unsafe class Program
{
    [StructLayout(LayoutKind.Sequential)]
    struct Rusage
    {
        public long UserSec, UserUsec, SysSec, SysUsec;
        public long MaxRss, Ixrss, Idrss, Isrss, Minflt, Majflt, Nswap, Inblock, Oublock, Msgsnd, Msgrcv, Nsignals, Nvcsw, Nivcsw;
    }
    [DllImport("libc", EntryPoint = "getrusage")] static extern int getrusage(int who, Rusage* usage);
    static Rusage Usage() { Rusage r; getrusage(0, &r); return r; }
    static double CpuMs(Rusage r) => (r.UserSec + r.SysSec) * 1000.0 + (r.UserUsec + r.SysUsec) / 1000.0;

    static void Busy(long ticks)
    {
        long end = Stopwatch.GetTimestamp() + ticks;
        while (Stopwatch.GetTimestamp() < end) { }
    }

    // Correctness: eight threads hand a token round a ring as the guest scheduler does (reset own, set next, wait own),
    // with random slices from 0 to 300 us, then a wait on an event nobody sets must stay blocked, and return at Set.
    static int Ring(int ms)
    {
        const int N = 8;
        Adaptive[] events = new Adaptive[N];
        for (int i = 0; i < N; i++) events[i] = new Adaptive();
        long laps = 0;
        int holders = 0, maxHolders = 0;
        bool stop = false;
        Thread[] threads = new Thread[N];
        for (int i = 0; i < N; i++)
        {
            int me = i;
            threads[i] = new Thread(() =>
            {
                Random random = new(me);
                if (me != 0) events[me].Wait();
                while (!Volatile.Read(ref stop))
                {
                    int h = Interlocked.Increment(ref holders);
                    if (h > maxHolders) maxHolders = h;
                    Busy(random.Next(4) == 0 ? random.Next(300) * Stopwatch.Frequency / 1_000_000 : random.Next(3) * Stopwatch.Frequency / 1_000_000);
                    if (me == 0) laps++;
                    Interlocked.Decrement(ref holders);
                    events[me].Reset();
                    events[(me + 1) % N].Set();
                    events[me].Wait();
                }
                events[(me + 1) % N].Set();
            }) { IsBackground = true };
            threads[i].Start();
        }
        Thread.Sleep(ms);
        Volatile.Write(ref stop, true);
        foreach (Adaptive e in events) e.Set();
        bool joined = true;
        foreach (Thread t in threads) joined &= t.Join(3000);
        int[] budgets = new int[N];
        for (int i = 0; i < N; i++) budgets[i] = events[i].E.SpinBudget;

        AdaptiveSpinEvent unset = new(false);
        long returnedAt = 0;
        Thread waiter = new(() => { unset.Wait(); Volatile.Write(ref returnedAt, Stopwatch.GetTimestamp()); }) { IsBackground = true };
        waiter.Start();
        Thread.Sleep(200);
        bool stayedBlocked = Volatile.Read(ref returnedAt) == 0;
        long setAt = Stopwatch.GetTimestamp();
        unset.Set();
        bool returned = waiter.Join(2000) && Volatile.Read(ref returnedAt) >= setAt;
        Console.WriteLine(string.Create(System.Globalization.CultureInfo.InvariantCulture,
            $"{{\"kind\":\"ring\",\"threads\":{N},\"laps\":{laps},\"joined\":{(joined ? "true" : "false")},\"maxHolders\":{maxHolders}," +
            $"\"unsetStayedBlocked\":{(stayedBlocked ? "true" : "false")},\"returnedAfterSet\":{(returned ? "true" : "false")},\"budgets\":[{string.Join(",", budgets)}]}}"));
        return 0;
    }

    static int Main(string[] args)
    {
        if (args[0] == "ring") return Ring(int.Parse(args[1]));
        string kind = args[0];
        int shortUs = int.Parse(args[1]), longUs = int.Parse(args[2]), shortPercent = int.Parse(args[3]), ms = int.Parse(args[4]);
        Func<Evt> make = kind switch { "control" => () => new Mres(-1), "bound" => () => new Mres(10), "adaptive" => () => new Adaptive(), _ => throw new ArgumentException(kind) };
        Evt[] events = { make(), make() };
        long shortTicks = shortUs * Stopwatch.Frequency / 1_000_000, longTicks = longUs * Stopwatch.Frequency / 1_000_000;
        long handoffs = 0, workTicks = 0;
        long[] latency = new long[1 << 21];
        int samples = 0;
        long setAt = 0;
        bool stop = false;
        Barrier start = new(3);
        Thread[] threads = new Thread[2];
        for (int side = 0; side < 2; side++)
        {
            int me = side, other = 1 - side;
            threads[side] = new Thread(() =>
            {
                Evt own = events[me], next = events[other];
                Random random = new(17 + me);
                start.SignalAndWait();
                if (me == 1) own.Wait();
                while (!Volatile.Read(ref stop))
                {
                    if (me == 1 && samples < latency.Length) latency[samples++] = Stopwatch.GetTimestamp() - Volatile.Read(ref setAt);
                    long work = random.Next(100) < shortPercent ? shortTicks : longTicks;
                    Busy(work);
                    workTicks += work;
                    own.Reset();
                    Volatile.Write(ref setAt, Stopwatch.GetTimestamp());
                    next.Set();
                    own.Wait();
                    handoffs++;
                }
                next.Set();
            }) { IsBackground = true };
            threads[side].Start();
        }
        start.SignalAndWait();
        Thread.Sleep(Math.Min(300, ms / 4)); // the adaptive event's score settles; the control's behavior is constant
        Rusage before = Usage();
        long h0 = Volatile.Read(ref handoffs), w0 = Volatile.Read(ref workTicks), s0 = samples, t0 = Stopwatch.GetTimestamp();
        Thread.Sleep(ms);
        Rusage after = Usage();
        long h1 = Volatile.Read(ref handoffs), w1 = Volatile.Read(ref workTicks), s1 = samples, t1 = Stopwatch.GetTimestamp();
        Volatile.Write(ref stop, true);
        events[0].Set(); events[1].Set();
        foreach (Thread t in threads) t.Join(2000);

        long count = h1 - h0;
        double seconds = (t1 - t0) / (double)Stopwatch.Frequency;
        double cpu = CpuMs(after) - CpuMs(before), workMs = (w1 - w0) * 1000.0 / Stopwatch.Frequency;
        long[] window = latency[(int)Math.Min(s0, latency.Length)..(int)Math.Min(s1, latency.Length)];
        Array.Sort(window);
        double Us(long ticks) => ticks * 1_000_000.0 / Stopwatch.Frequency;
        double P(double q) => window.Length == 0 ? 0 : Us(window[Math.Min(window.Length - 1, (int)(q * window.Length))]);
        string budget = kind == "adaptive" ? $",\"spinBudgets\":[{((Adaptive)events[0]).E.SpinBudget},{((Adaptive)events[1]).E.SpinBudget}]" : "";
        Console.WriteLine(string.Create(System.Globalization.CultureInfo.InvariantCulture,
            $"{{\"kind\":\"{kind}\",\"shortUs\":{shortUs},\"longUs\":{longUs},\"shortPercent\":{shortPercent},\"seconds\":{seconds:F3},\"handoffs\":{count}," +
            $"\"handoffsPerSecond\":{count / seconds:F0},\"cpuMs\":{cpu:F1},\"overheadCpuUsPerHandoff\":{(cpu - workMs) * 1000 / Math.Max(count, 1):F2}," +
            $"\"voluntarySwitchesPerHandoff\":{(after.Nvcsw - before.Nvcsw) / (double)Math.Max(count, 1):F3}," +
            $"\"wakeUsP50\":{P(0.5):F1},\"wakeUsP90\":{P(0.9):F1},\"wakeUsP99\":{P(0.99):F1}{budget}}}"));
        return 0;
    }
}
