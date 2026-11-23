// Probe of adapt_compile_wait_guest_time: the production TickSource.cs (and, for the candidate, GuestTimeHold.cs) of the
// control or the candidate, compiled with the production ITickSource.cs and ICounter.cs and the double below (the Logger
// GuestTimeHold writes its long-wait line to). CONTROL has no hold: its "compile wait" is the wait itself, as the guest
// saw it before. Prints one JSON line.
using Ryujinx.Cpu;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Threading;

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }

    public static class Logger
    {
        public static readonly List<string> Lines = new();

        public readonly struct Log
        {
            public void Print(LogClass logClass, string message)
            {
                lock (Lines)
                {
                    Lines.Add(logClass + ": " + message);
                }
            }
        }

        public static Log? Warning { get; } = new Log();
    }
}

namespace Probe
{
    internal static class Program
    {
        private const ulong Frequency = 19200000;
        private static int _checks;
        private static readonly List<string> _failures = new();

        private static void Check(bool condition, string message)
        {
            _checks++;
            if (!condition)
            {
                _failures.Add(message);
            }
        }

        private static double HostMs(long from) => (Stopwatch.GetTimestamp() - from) * 1000.0 / Stopwatch.Frequency;

        private static void Spin(double milliseconds)
        {
            long end = Stopwatch.GetTimestamp() + (long)(milliseconds * Stopwatch.Frequency / 1000);
            while (Stopwatch.GetTimestamp() < end)
            {
                Thread.SpinWait(16);
            }
        }

        // The compile wait of the guest's GPU path: held in the candidate (as WaitForPipelineAtDraw holds it), plain in the control.
        private static void CompileWait(double milliseconds, Action during = null)
        {
#if CANDIDATE
            long token = Ryujinx.Common.GuestTimeHold.Begin();
            try
            {
                if (during != null) during(); else Thread.Sleep(TimeSpan.FromMilliseconds(milliseconds));
            }
            finally
            {
                Ryujinx.Common.GuestTimeHold.End(token);
            }
#else
            if (during != null) during(); else Thread.Sleep(TimeSpan.FromMilliseconds(milliseconds));
#endif
        }

        private static double GuestMs(TickSource ticks, ulong from) => (ticks.Counter - from) * 1000.0 / Frequency;

        private static string F(double value) => value.ToString("F3", CultureInfo.InvariantCulture);

        // Longer than the burst gap: the next wait starts a new burst.
        private static void Quiet() => Thread.Sleep(400);

        private static int Main(string[] args)
        {
            int cycles = args.Length > 0 ? int.Parse(args[0], CultureInfo.InvariantCulture) : 20000;
            var json = new StringBuilder("{");
            void Add(string key, string value) => json.Append(json.Length > 1 ? "," : "").Append('"').Append(key).Append("\":").Append(value);

            TickSource ticks = new(Frequency);
            Add("variant",
#if CANDIDATE
                "\"candidate\"");
#else
                "\"control\"");
#endif

            // 1. Short waits never touch the clock: 200 000 empty waits, the guest's clock keeps host time.
            ulong from = ticks.Counter;
            long hostFrom = Stopwatch.GetTimestamp();
            for (int i = 0; i < 200000; i++)
            {
                CompileWait(0, () => { });
            }
            double shortHost = HostMs(hostFrom), shortGuest = GuestMs(ticks, from);
            Add("shortWaits", $"{{\"waits\":200000,\"hostMs\":{F(shortHost)},\"guestMs\":{F(shortGuest)}}}");
            Check(Math.Abs(shortGuest - shortHost) < 0.5 + shortHost * 0.001, "short waits: the guest's clock keeps host time");
            Quiet();

            // 2. Monotonic from every thread, the scalar never read as 0, under holds and releases (a burst: each wait held
            //    from its start), scalar replacements, and pauses and resumes from another thread.
            long violations = 0, perThreadViolations = 0, reads = 0, scalarZero = 0, scalarReads = 0;
            ulong max = 0;
            bool stop = false;
            var readers = new List<Thread>();
            for (int r = 0; r < 2; r++)
            {
                var thread = new Thread(() =>
                {
                    ulong last = 0;
                    long localReads = 0, localViolations = 0, localThread = 0;
                    while (!Volatile.Read(ref stop))
                    {
                        ulong before = Volatile.Read(ref max);
                        ulong value = ticks.Counter;
                        localReads++;
                        if (value < before) localViolations++;
                        if (value < last) localThread++;
                        last = value;
                        ulong seen;
                        while (value > (seen = Volatile.Read(ref max)) && Interlocked.CompareExchange(ref max, value, seen) != seen) { }
                    }
                    Interlocked.Add(ref reads, localReads);
                    Interlocked.Add(ref violations, localViolations);
                    Interlocked.Add(ref perThreadViolations, localThread);
                }) { IsBackground = true };
                readers.Add(thread);
                thread.Start();
            }
            var scalarReader = new Thread(() =>
            {
                long zero = 0, count = 0;
                while (!Volatile.Read(ref stop))
                {
                    if (ticks.TickScalar == 0) zero++;
                    count++;
                }
                Interlocked.Add(ref scalarZero, zero);
                Interlocked.Add(ref scalarReads, count);
            }) { IsBackground = true };
            scalarReader.Start();
            bool pausing = true;
            var pauser = new Thread(() =>
            {
                int n = 0;
                while (Volatile.Read(ref pausing))
                {
                    ticks.Suspend();
                    Thread.SpinWait(200);
                    ticks.Resume();
                    if (++n % 8 == 0) Thread.Sleep(1);
                }
            }) { IsBackground = true };
            pauser.Start();
            var random = new Random(7);
            long writerStart = Stopwatch.GetTimestamp();
            CompileWait(40);
            for (int i = 0; i < cycles; i++)
            {
                double duration = random.NextDouble() * 0.2;
                CompileWait(duration, () => Spin(duration));
                if (i % 97 == 0)
                {
                    ticks.TickScalar = ITickSource.RealityTickScalar;
                }
            }
            double writerMs = HostMs(writerStart);
            Volatile.Write(ref pausing, false);
            pauser.Join();
            Volatile.Write(ref stop, true);
            foreach (var thread in readers) thread.Join();
            scalarReader.Join();
            Add("monotonic", $"{{\"cycles\":{cycles},\"reads\":{reads},\"violations\":{violations},\"perThreadViolations\":{perThreadViolations}," +
                $"\"scalarReads\":{scalarReads},\"scalarZero\":{scalarZero},\"writerMs\":{F(writerMs)}}}");
            Check(reads > 100000 && scalarReads > 100000, "the readers ran during the holds");
            Quiet();

            // 3. A long wait: the guest sees its first 33 ms (candidate) or all of it (control).
            from = ticks.Counter;
            hostFrom = Stopwatch.GetTimestamp();
            CompileWait(600);
            double longGuest = GuestMs(ticks, from), longHost = HostMs(hostFrom);
            Add("longWait", $"{{\"hostMs\":{F(longHost)},\"guestMs\":{F(longGuest)}}}");
            Quiet();

            // 4. A 10 ms wait: seen in full by both.
            from = ticks.Counter;
            hostFrom = Stopwatch.GetTimestamp();
            CompileWait(0, () => Spin(10));
            double tenGuest = GuestMs(ticks, from), tenHost = HostMs(hostFrom);
            Add("tenMsWait", $"{{\"hostMs\":{F(tenHost)},\"guestMs\":{F(tenGuest)}}}");
            Check(Math.Abs(tenGuest - tenHost) < 0.5, "a wait under 33 ms is seen in full: " + F(tenGuest) + " of " + F(tenHost));
            Quiet();

            // 5. Nested waits count once; a thread sleeping during the hold wakes on host time and reads the held clock.
            from = ticks.Counter;
            double sleeperHostMs = -1;
            ulong sleeperSaw = 0;
            CompileWait(0, () =>
            {
                CompileWait(0, () =>
                {
                    var sleeper = new Thread(() =>
                    {
                        long s = Stopwatch.GetTimestamp();
                        Thread.Sleep(80);
                        sleeperHostMs = HostMs(s);
                        sleeperSaw = ticks.Counter;
                    });
                    sleeper.Start();
                    Thread.Sleep(150);
                    sleeper.Join();
                });
                Thread.Sleep(50);
            });
            double nestedGuest = GuestMs(ticks, from);
            Add("nested", $"{{\"guestMs\":{F(nestedGuest)},\"sleeperHostMs\":{F(sleeperHostMs)},\"sleeperGuestMs\":{F((sleeperSaw - from) * 1000.0 / Frequency)}}}");
            Check(sleeperHostMs >= 75, "a thread sleeping during a hold wakes on host time");
            Quiet();

            // 6. Unreal's heartbeat, scaled: a watched thread that has not ticked for 2 s of guest time is reported hung.
            //    The game thread's frame is 16 compile waits of 150 ms (2.4 s of host time), twice.
            bool hung = false;
            double longestGap = 0;
            ulong lastBeat = ticks.Counter;
            bool done = false;
            var heartbeat = new Thread(() =>
            {
                while (!Volatile.Read(ref done))
                {
                    double gap = (ticks.Counter - Volatile.Read(ref lastBeat)) / (double)Frequency;
                    longestGap = Math.Max(longestGap, gap);
                    if (gap > 2.0) hung = true;
                    Thread.Sleep(20);
                }
            });
            heartbeat.Start();
            var frames = new List<double>();
            for (int frame = 0; frame < 2; frame++)
            {
                ulong frameStart = ticks.Counter;
                for (int wait = 0; wait < 16; wait++)
                {
                    CompileWait(150);
                    Spin(1); // the rendering between two waits
                }
                frames.Add(GuestMs(ticks, frameStart));
                Volatile.Write(ref lastBeat, ticks.Counter);
            }
            Volatile.Write(ref done, true);
            heartbeat.Join();
            Add("heartbeat", $"{{\"hung\":{(hung ? "true" : "false")},\"longestGapS\":{F(longestGap)},\"frameGuestMs\":[{F(frames[0])},{F(frames[1])}]}}");
            Quiet();

            // 7. Pause inside a hold, and alone (Horizon.TogglePauseEmulation): the paused time stays out, no step back.
            from = ticks.Counter;
            ulong pausedAt = 0, resumedAt = 0;
            CompileWait(0, () =>
            {
                Thread.Sleep(50);
                ticks.Suspend();
                Thread.Sleep(80);
                pausedAt = ticks.Counter;
                ticks.Resume();
                Thread.Sleep(20);
                resumedAt = ticks.Counter;
            });
            double pauseHeldGuest = GuestMs(ticks, from);
            Quiet();
            from = ticks.Counter;
            ticks.Suspend();
            Thread.Sleep(60);
            ulong alonePaused = ticks.Counter;
            ticks.Resume();
            Thread.Sleep(20);
            double pauseAloneGuest = GuestMs(ticks, from);
            Add("pause", $"{{\"heldGuestMs\":{F(pauseHeldGuest)},\"aloneGuestMs\":{F(pauseAloneGuest)},\"alonePausedGuestMs\":{F((alonePaused - from) * 1000.0 / Frequency)}}}");
            Check(resumedAt >= pausedAt, "pause inside a hold: no step back");
            Check(pauseAloneGuest > 15 && pauseAloneGuest < 30 && (alonePaused - from) * 1000.0 / Frequency < 0.1, "a pause alone: its time stays out");
            Quiet();

#if CANDIDATE
            // 8. The long-wait line and the journal text.
            Ryujinx.Common.Logging.Logger.Lines.Clear();
            Ryujinx.Common.GuestTimeHold.TakeText();
            CompileWait(1100);
            Quiet();
            CompileWait(5);
            string text = Ryujinx.Common.GuestTimeHold.TakeText();
            string lines;
            lock (Ryujinx.Common.Logging.Logger.Lines) lines = string.Join("|", Ryujinx.Common.Logging.Logger.Lines);
            Add("journal", "{\"text\":\"" + text.Replace("\"", "'") + "\",\"lines\":\"" + lines.Replace("\"", "'") + "\"}");
            Quiet();

            // 9. Session lifetime: a new clock ends the hold of the previous one and its waits' tokens are ignored.
            from = ticks.Counter;
            long staleToken = Ryujinx.Common.GuestTimeHold.Begin();
            Thread.Sleep(100);
            TickSource next = new(Frequency); // attaches itself
            ulong released = ticks.Counter;
            Thread.Sleep(30);
            double previousAfterRelease = (ticks.Counter - released) * 1000.0 / Frequency;
            Ryujinx.Common.GuestTimeHold.End(staleToken);
            ulong nextFrom = next.Counter;
            CompileWait(300);
            double nextGuest = GuestMs(next, nextFrom);
            Quiet();
            ulong nextQuiet = next.Counter;
            Thread.Sleep(40);
            double nextRuns = GuestMs(next, nextQuiet);
            Add("lifetime", $"{{\"previousRunsAfterNewClockMs\":{F(previousAfterRelease)},\"laterClockWaitGuestMs\":{F(nextGuest)},\"laterClockRunsMs\":{F(nextRuns)}}}");
            Check(previousAfterRelease > 25, "the previous clock runs again once a new one is attached");
            Check(nextGuest > 30 && nextGuest < 60, "the later clock holds its own waits: " + F(nextGuest));
            Check(nextRuns > 35, "a stale token leaves the later clock running");
            ticks = next;
#endif

            // 10. The cost of a read, one thread, never held.
            TickSource cost = new(Frequency);
            ulong sink = 0;
            for (int i = 0; i < 200000; i++) sink += cost.Counter;
            long costStart = Stopwatch.GetTimestamp();
            const int costReads = 5000000;
            for (int i = 0; i < costReads; i++) sink += cost.Counter;
            double costNs = (Stopwatch.GetTimestamp() - costStart) * 1e9 / Stopwatch.Frequency / costReads;
            Add("readCostNs", F(costNs));
            Add("sink", (sink & 1).ToString(CultureInfo.InvariantCulture));

            Add("checks", _checks.ToString(CultureInfo.InvariantCulture));
            Add("failures", "[" + string.Join(",", _failures.ConvertAll(f => "\"" + f.Replace("\"", "'") + "\"")) + "]");
            json.Append('}');
            Console.WriteLine(json.ToString());

            return _failures.Count == 0 ? 0 : 1;
        }
    }
}
