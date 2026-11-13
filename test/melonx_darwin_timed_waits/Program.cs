// Fixture for adapt_darwin_timed_waits: the production Ryujinx.Common/PreciseSleep files (control or candidate text,
// written next to this file by the gate) driven the way the engine drives them.
// "timers": the guest timer thread's loop as KTimeManager.WaitAndCheckScheduledObjects runs it (the next deadline under
//   a lock; SleepUntil, else the wake-able spin; fire when due; Sleep when none), fed by four threads that each schedule
//   a deadline 50 us to 5 ms ahead (signalling the timer thread when theirs is the earliest) and wait until it fires.
// "vsync": the compositor's loop as SurfaceFlinger.UpdateLoop runs it at 60 Hz (SleepUntilTimePoint, then the
//   no-wake spin under 2 ms, else WaitOne).
// Per run: deadlines (or frames), process CPU per deadline (or frame), lateness percentiles, threads started.
// Usage: fixture <timers|vsync> <milliseconds>
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using Ryujinx.Common;
using Ryujinx.Common.PreciseSleep;

namespace Ryujinx.Common
{
    // The engine journal, which HostThreadClass records a refusal to (adapt_host_thread_class): not under test.
    public static class EmbeddedLaunchDiagnostics
    {
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0) { }
    }
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
    static double CpuMs() { Rusage r; getrusage(0, &r); return (r.UserSec + r.SysSec) * 1000.0 + (r.UserUsec + r.SysUsec) / 1000.0; }
    static double Us(long ticks) => ticks * 1_000_000.0 / Stopwatch.Frequency;

    static string Percentiles(List<long> values)
    {
        values.Sort();
        double P(double q) => values.Count == 0 ? 0 : Us(values[Math.Min(values.Count - 1, (int)(q * values.Count))]);
        return string.Create(System.Globalization.CultureInfo.InvariantCulture, $"\"latenessUsP50\":{P(0.5):F1},\"latenessUsP90\":{P(0.9):F1},\"latenessUsP99\":{P(0.99):F1},\"latenessUsMax\":{P(1.0):F1}");
    }

    static int Threads() => Process.GetCurrentProcess().Threads.Count;

    // The nanosleep helper threads the event's pool started (0 for an event without a pool): read through the private
    // fields, nothing changed. The process's thread count also moves with the runtime's own threads.
    static int HelperThreads(IPreciseSleepEvent evt)
    {
        const System.Reflection.BindingFlags Private = System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
        object pool = evt.GetType().GetField("_pool", Private)?.GetValue(evt);
        return pool?.GetType().GetField("_threads", Private)?.GetValue(pool) is System.Collections.ICollection threads ? threads.Count : 0;
    }

    static int Timers(int ms)
    {
        object gate = new();
        List<(long At, ManualResetEventSlim Done)> waiting = new();
        IPreciseSleepEvent evt = PreciseSleepHelper.CreateEvent();
        long enforce = 0;
        bool running = true;
        List<long> lateness = new();
        int fired = 0;
        int threadsBefore = Threads();

        Thread timer = new(() =>
        {
            HostThreadClass.RaiseCurrentThread();
            while (Volatile.Read(ref running))
            {
                (long At, ManualResetEventSlim Done) next = default;
                bool valid;
                lock (gate)
                {
                    Interlocked.Exchange(ref enforce, 0);
                    valid = waiting.Count > 0;
                    if (valid)
                    {
                        next = waiting[0];
                        foreach (var w in waiting) if (w.At < next.At) next = w;
                    }
                }
                if (valid)
                {
                    if (next.At > PerformanceCounter.ElapsedTicks && !evt.SleepUntil(next.At))
                    {
                        PreciseSleepHelper.SpinWaitUntilTimePoint(next.At, ref enforce);
                    }
                    long now = PerformanceCounter.ElapsedTicks;
                    if (now >= next.At)
                    {
                        lock (gate)
                        {
                            if (waiting.Remove(next)) { lateness.Add(now - next.At); fired++; next.Done.Set(); }
                        }
                    }
                }
                else
                {
                    evt.Sleep();
                }
            }
        }) { IsBackground = true, Name = "Fixture.TimeManager" };
        timer.Start();

        Thread[] producers = new Thread[4];
        for (int p = 0; p < producers.Length; p++)
        {
            int seed = p;
            producers[p] = new Thread(() =>
            {
                HostThreadClass.RaiseCurrentThread();
                Random random = new(seed);
                ManualResetEventSlim done = new(false);
                while (Volatile.Read(ref running))
                {
                    long at = PerformanceCounter.ElapsedTicks + (50 + random.Next(4950)) * Stopwatch.Frequency / 1_000_000;
                    done.Reset();
                    bool earliest;
                    lock (gate)
                    {
                        earliest = true;
                        foreach (var w in waiting) if (w.At <= at) earliest = false;
                        waiting.Add((at, done));
                    }
                    if (earliest) { Interlocked.Exchange(ref enforce, 1); evt.Signal(); }
                    done.Wait(200);
                }
            }) { IsBackground = true };
            producers[p].Start();
        }

        Thread.Sleep(300);
        double cpu0 = CpuMs(); int fired0; lock (gate) { fired0 = fired; lateness.Clear(); }
        Thread.Sleep(ms);
        double cpu1 = CpuMs(); int fired1; List<long> sample; lock (gate) { fired1 = fired; sample = new List<long>(lateness); }
        int threadsDuring = Threads(), helpers = HelperThreads(evt);
        Volatile.Write(ref running, false);
        evt.Signal();
        foreach (Thread t in producers) t.Join(2000);
        timer.Join(2000);
        int count = fired1 - fired0;
        Console.WriteLine(string.Create(System.Globalization.CultureInfo.InvariantCulture,
            $"{{\"mode\":\"timers\",\"event\":\"{evt.GetType().Name}\",\"deadlines\":{count},\"cpuUsPerDeadline\":{(cpu1 - cpu0) * 1000 / Math.Max(1, count):F2}," +
            $"\"threadsStarted\":{threadsDuring - threadsBefore},\"helperThreads\":{helpers},{Percentiles(sample)}}}"));
        return 0;
    }

    static int Vsync(int ms)
    {
        // SurfaceFlinger.UpdateLoop at swap interval 1 (the compose itself is not timed here).
        long ticksPerFrame = Stopwatch.Frequency / 60, spinTicks = Stopwatch.Frequency / 500, oneMs = Stopwatch.Frequency / 1000;
        AutoResetEvent wake = new(false);
        List<long> lateness = new();
        int threadsBefore = Threads();
        long frames = 0;
        double cpu0 = 0;
        long measuredFrom = 0;
        Thread composer = new(() =>
        {
            HostThreadClass.RaiseCurrentThread();
            long accumulated = 0, lastTicks = PerformanceCounter.ElapsedTicks, origin = lastTicks, target = origin + ticksPerFrame;
            long end = origin + (ms + 300) * Stopwatch.Frequency / 1000;
            while (PerformanceCounter.ElapsedTicks < end)
            {
                long ticks = PerformanceCounter.ElapsedTicks;
                accumulated += ticks - lastTicks;
                lastTicks = ticks;
                if (accumulated >= ticksPerFrame)
                {
                    if (ticks - origin >= 300 * oneMs)
                    {
                        if (measuredFrom == 0) { measuredFrom = frames; cpu0 = CpuMs(); }
                        lateness.Add(Math.Max(0, ticks - target));
                    }
                    frames++;
                    target += ticksPerFrame;
                    accumulated = Math.Min(accumulated - ticksPerFrame, ticksPerFrame * 3);
                }
                long diff = ticksPerFrame - (accumulated + PerformanceCounter.ElapsedTicks - ticks);
                if (diff > 0)
                {
                    PreciseSleepHelper.SleepUntilTimePoint(wake, PerformanceCounter.ElapsedTicks + diff);
                    diff = ticksPerFrame - (accumulated + PerformanceCounter.ElapsedTicks - ticks);
                    if (diff < spinTicks)
                    {
                        PreciseSleepHelper.SpinWaitUntilTimePoint(PerformanceCounter.ElapsedTicks + diff);
                    }
                    else
                    {
                        wake.WaitOne((int)(diff / oneMs));
                    }
                }
            }
        }) { IsBackground = true, Name = "Fixture.Composer" };
        composer.Start();
        composer.Join();
        double cpu1 = CpuMs();
        long counted = frames - measuredFrom;
        Console.WriteLine(string.Create(System.Globalization.CultureInfo.InvariantCulture,
            $"{{\"mode\":\"vsync\",\"frames\":{counted},\"cpuUsPerFrame\":{(cpu1 - cpu0) * 1000 / Math.Max(1, counted):F2}," +
            $"\"threadsStarted\":{Threads() - threadsBefore},{Percentiles(lateness)}}}"));
        return 0;
    }

    static int Main(string[] args) => args[0] == "timers" ? Timers(int.Parse(args[1])) : Vsync(int.Parse(args[1]));
}
