// Protocol fixture for adapt_darwin_timed_waits: the adapter's DarwinSleepEvent, its text unchanged, compiled next to a
// stand-in for the libSystem calls it makes (a semaphore table that records each release and refuses any use after it),
// so that its signalling runs on any host. The Apple timing itself is measured by the other fixture on macOS.
// Modes:
//   lost <signals>  two producers change a generation and signal, a waiter alternates Sleep() and a far SleepUntil and
//                   reads the generation after each wake: every signal must be seen within 200 ms (a lost signal leaves
//                   the waiter asleep until its far deadline, or for ever)
//   dispose <rounds> a thread signals in a loop while the owner disposes: no exception, no use after release, the
//                   semaphore released exactly once per event
//   semantics       a deadline already reached returns false; a timed wait ends at its deadline; a signal made before
//                   the wait ends it at once; signals made while none is consumed count once
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Threading;
using Ryujinx.Common.PreciseSleep;

namespace Ryujinx.Common.PreciseSleep
{
    public interface IPreciseSleepEvent : IDisposable
    {
        long AdjustTimePoint(long timePoint, long timeoutNs);
        bool SleepUntil(long timePoint);
        void Sleep();
        void Signal();
    }

    internal static class DarwinTimedWait
    {
        internal const ulong TimeNow = 0, TimeForever = ulong.MaxValue;
        private static readonly ConcurrentDictionary<nint, SemaphoreSlim> s_live = new();
        private static long s_next;
        internal static long Created, Released, Misuses;

        internal static long NanosecondsUntil(long timePoint) =>
            (long)((timePoint - Stopwatch.GetTimestamp()) * (1_000_000_000.0 / Stopwatch.Frequency));

        internal static nint dispatch_semaphore_create(nint value)
        {
            nint handle = (nint)Interlocked.Increment(ref s_next);
            s_live[handle] = new SemaphoreSlim((int)value);
            Interlocked.Increment(ref Created);
            return handle;
        }

        private static SemaphoreSlim Live(nint handle)
        {
            if (!s_live.TryGetValue(handle, out SemaphoreSlim semaphore))
            {
                Interlocked.Increment(ref Misuses);
                throw new InvalidOperationException("semaphore used after its release");
            }

            return semaphore;
        }

        internal static ulong dispatch_time(ulong when, long deltaNanoseconds) =>
            (ulong)(Stopwatch.GetTimestamp() + (long)(deltaNanoseconds * (Stopwatch.Frequency / 1_000_000_000.0)));

        internal static nint dispatch_semaphore_wait(nint handle, ulong timeout)
        {
            SemaphoreSlim semaphore = Live(handle);
            if (timeout == TimeNow)
            {
                return semaphore.Wait(0) ? 0 : 1;
            }

            if (timeout == TimeForever)
            {
                semaphore.Wait();
                return 0;
            }

            long remaining = (long)timeout - Stopwatch.GetTimestamp();
            return semaphore.Wait(TimeSpan.FromTicks(Math.Max(0, remaining * TimeSpan.TicksPerSecond / Stopwatch.Frequency))) ? 0 : 1;
        }

        internal static nint dispatch_semaphore_signal(nint handle)
        {
            Live(handle).Release();
            return 0;
        }

        internal static void dispatch_release(nint handle)
        {
            if (!s_live.TryRemove(handle, out _))
            {
                Interlocked.Increment(ref Misuses);
                throw new InvalidOperationException("semaphore released twice");
            }

            Interlocked.Increment(ref Released);
        }
    }
}

static class Program
{
    static long Ticks(double ms) => (long)(ms * Stopwatch.Frequency / 1000);

    static int Lost(int signals)
    {
        var e = new DarwinSleepEvent();
        long generation = 0, seen = 0, lost = 0, sent = 0;
        bool stop = false;
        var waiter = new Thread(() =>
        {
            for (int round = 0; !Volatile.Read(ref stop); round++)
            {
                long now = Volatile.Read(ref generation);
                if (now != Volatile.Read(ref seen))
                {
                    Volatile.Write(ref seen, now);
                    continue;
                }

                if ((round & 1) == 0)
                {
                    e.Sleep();
                }
                else
                {
                    e.SleepUntil(Stopwatch.GetTimestamp() + Ticks(60_000));
                }
            }
        }) { IsBackground = true };
        waiter.Start();
        Thread[] producers = new Thread[2];
        for (int p = 0; p < producers.Length; p++)
        {
            int me = p;
            producers[p] = new Thread(() =>
            {
                var random = new Random(31 + me);
                for (int i = 0; i < signals && Volatile.Read(ref lost) == 0; i++)
                {
                    Thread.SpinWait(random.Next(200));
                    long mine = Interlocked.Increment(ref generation);
                    e.Signal();
                    Interlocked.Increment(ref sent);
                    long end = Stopwatch.GetTimestamp() + Ticks(200);
                    while (Volatile.Read(ref seen) < mine)
                    {
                        if (Stopwatch.GetTimestamp() > end)
                        {
                            Interlocked.Increment(ref lost);
                            return;
                        }

                        Thread.SpinWait(20);
                    }
                }
            }) { IsBackground = true };
            producers[p].Start();
        }

        foreach (Thread t in producers) t.Join();
        Volatile.Write(ref stop, true);
        e.Signal();
        bool ended = waiter.Join(2000);
        Console.WriteLine($"{{\"mode\":\"lost\",\"signals\":{Volatile.Read(ref sent)},\"lost\":{lost},\"waiterEnded\":{(ended ? "true" : "false")}}}");
        return 0;
    }

    static int Dispose(int rounds)
    {
        long exceptions = 0;
        var random = new Random(7);
        long created = DarwinTimedWait.Created;
        for (int r = 0; r < rounds; r++)
        {
            var e = new DarwinSleepEvent();
            bool stop = false;
            var signaller = new Thread(() =>
            {
                try
                {
                    while (!Volatile.Read(ref stop)) e.Signal();
                    for (int i = 0; i < 100; i++) e.Signal();
                }
                catch (Exception)
                {
                    Interlocked.Increment(ref exceptions);
                }
            });
            signaller.Start();
            Thread.SpinWait(random.Next(20_000));
            try
            {
                e.Dispose();
                e.Dispose();
            }
            catch (Exception)
            {
                Interlocked.Increment(ref exceptions);
            }

            Volatile.Write(ref stop, true);
            signaller.Join();
        }

        long made = DarwinTimedWait.Created - created;
        Console.WriteLine($"{{\"mode\":\"dispose\",\"rounds\":{rounds},\"created\":{made},\"released\":{DarwinTimedWait.Released}," +
                          $"\"misuses\":{DarwinTimedWait.Misuses},\"exceptions\":{exceptions}}}");
        return 0;
    }

    static int Semantics()
    {
        var e = new DarwinSleepEvent();
        bool pastIsFalse = !e.SleepUntil(Stopwatch.GetTimestamp() - 1);
        long start = Stopwatch.GetTimestamp();
        bool slept = e.SleepUntil(start + Ticks(30));
        double timedMs = (Stopwatch.GetTimestamp() - start) * 1000.0 / Stopwatch.Frequency;
        e.Signal();
        start = Stopwatch.GetTimestamp();
        e.SleepUntil(start + Ticks(2000));
        double signalledMs = (Stopwatch.GetTimestamp() - start) * 1000.0 / Stopwatch.Frequency;
        e.Signal();
        e.Signal();
        e.Signal();
        e.Sleep();
        start = Stopwatch.GetTimestamp();
        e.SleepUntil(start + Ticks(30));
        double afterCoalescedMs = (Stopwatch.GetTimestamp() - start) * 1000.0 / Stopwatch.Frequency;
        bool unchangedTimePoint = e.AdjustTimePoint(12345, 1000) == 12345;
        e.Dispose();
        Console.WriteLine(string.Create(System.Globalization.CultureInfo.InvariantCulture,
            $"{{\"mode\":\"semantics\",\"pastIsFalse\":{(pastIsFalse ? "true" : "false")},\"slept\":{(slept ? "true" : "false")},\"timedMs\":{timedMs:F2}," +
            $"\"signalledMs\":{signalledMs:F2},\"afterCoalescedMs\":{afterCoalescedMs:F2},\"unchangedTimePoint\":{(unchangedTimePoint ? "true" : "false")}," +
            $"\"released\":{DarwinTimedWait.Released},\"misuses\":{DarwinTimedWait.Misuses}}}"));
        return 0;
    }

    static int Main(string[] args) => args[0] switch
    {
        "lost" => Lost(int.Parse(args[1])),
        "dispose" => Dispose(int.Parse(args[1])),
        "semantics" => Semantics(),
        _ => throw new ArgumentException(args[0]),
    };
}
