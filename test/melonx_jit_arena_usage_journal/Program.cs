// One process of the application: a script of launches, in the order the application runs them
// (MeloNXInternalBridgePlugin.swift: content preflight, neostation_melonx_prepare_jit, then the session and its guest).
// Usage: Fixture <games directory> <operation>...   (test/melonx_jit_arena_usage_journal_test.py lists the scripts)
//   budget=<MiB>              the process memory budget (HostMemoryBudget.TotalBytes)
//   helper=<ns>,<stop>,<fail> the helper double: nanoseconds per 16 KiB page; 1 = every thread stopped meanwhile,
//                             0 = only the caller waits; a failure mode (helper_double.c)
//   L<MiB>                    a launch whose title asks for <MiB> of arena (0: the default)
//   K<MiB>                    the same launch, abandoned by the user while the arena is prepared (no session follows)
//   U<MiB>                    the running guest translates code until its cache has allocated <MiB>
//   C                         the game is closed
//   A<state>                  EmbeddedSessions.State
//   Q                         wait until the journal holds the "reached" lines that are due
//   R<seed>                   randomized: threads translate through the real Map while launches and journal polls go on
//   B<count>                  the cost of one Map (64 bytes of code), best of seven rounds of <count>
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using Fixture;
using Ryujinx.Common;
using Ryujinx.Common.Configuration;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.Cache;
using Ryujinx.Memory;

static class Program
{
    private const ulong MiB = 1UL << 20;
    private static readonly List<Dictionary<string, object>> Steps = new();
    private static Translator _translator;
    private static DualMappedNoWxCache _cache;
    private static int _guestRuns, _sessions;
    private static long _sessionAllocated;
    private static int _sessionJournalStart;
    private static int _journalRead;

    private static int BeatThreads() => Directory.GetDirectories("/proc/self/task")
        .Count(task => { try { return File.ReadAllText(Path.Combine(task, "comm")).StartsWith("RewindBox.JitAr"); } catch { return false; } });

    private static List<object[]> NewJournal()
    {
        JournalEvent[] all = EmbeddedLaunchDiagnostics.Snapshot();
        var lines = all.Skip(_journalRead).Select(e => new object[] { Math.Round(e.Ms, 3), e.Stage, e.Status, e.Code, e.Detail }).ToList();
        _journalRead = all.Length;
        return lines;
    }

    private static object CacheField(string name) =>
        typeof(DualMappedNoWxCache).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static).GetValue(_cache);

    // The session the application creates after a successful preparation: the guest's translator and its cache
    // (Translator's constructor: DualMappedNoWxCache.InitMemoryCache(); new DualMappedNoWxCache(this)), then guest code.
    private static unsafe void StartSession(Dictionary<string, object> step)
    {
        _sessions++;
        _sessionAllocated = 0;
        _sessionJournalStart = EmbeddedLaunchDiagnostics.Snapshot().Length;
        _translator = new Translator();
        DualMappedNoWxCache.InitMemoryCache();
        _cache = new DualMappedNoWxCache(_translator);
        if (RuntimeInformation.ProcessArchitecture == Architecture.X64)
        {
            // "Guest code": mov eax, imm32; ret, written through the RW alias by the real Map and run through the RX one.
            int value = 0x1000 + _sessions;
            byte[] code = { 0xb8, (byte)value, (byte)(value >> 8), 0, 0, 0xc3 };
            nint function = _cache.Map(code, 0x8000000UL + (ulong)_sessions * 0x1000, 4);
            step["guestValue"] = ((delegate* unmanaged<int>)function)();
            step["guestExpected"] = value;
            step["mapAgainSame"] = _cache.Map(code, 0x8000000UL + (ulong)_sessions * 0x1000, 4) == function;
        }
        _guestRuns++;
    }

    private static void Launch(string argument, bool abandoned)
    {
        var step = new Dictionary<string, object> { ["op"] = (abandoned ? "K" : "L") + argument };
        ulong hint = ulong.Parse(argument) * MiB;
        ulong traps = Helper.Traps, pages = Helper.Pages, regions = Helper.Regions, aliases = Helper.Aliases;
        double held = Helper.HeldMs;
        Ryujinx.Library.Library.Preflight(hint);
        int rc = -1;
        long beside = 0;
        bool preparing = true;
        // A launch step that would run beside the preparation: it counts the milliseconds in which it could work.
        var worker = new Thread(() =>
        {
            long last = Stopwatch.GetTimestamp();
            while (Volatile.Read(ref preparing))
            {
                Thread.Sleep(1);
                long now = Stopwatch.GetTimestamp();
                if (Stopwatch.GetElapsedTime(last, now).TotalMilliseconds < 5) beside++;
                last = now;
            }
        });
        // The host polls the journal while it waits, and a second host call needs the engine's gate.
        int polls = 0;
        double gateWaitMs = -1;
        bool gateAfterPrepare = false;
        var poller = new Thread(() => { while (Volatile.Read(ref preparing)) { EmbeddedLaunchDiagnostics.Snapshot(); polls++; Thread.Sleep(2); } });
        var second = new Thread(() =>
        {
            while (Volatile.Read(ref preparing) && Helper.Traps == traps) Thread.Sleep(1);
            long asked = Stopwatch.GetTimestamp();
            lock (Ryujinx.Library.Library.EmbeddedHostGate)
            {
                gateWaitMs = Stopwatch.GetElapsedTime(asked).TotalMilliseconds;
                // Held by the preparation until its outcome is journalled: whoever gets the gate next sees that outcome.
                gateAfterPrepare = EmbeddedLaunchDiagnostics.Snapshot().Any(e => e.Stage == "jitArena" && e.Status is "passed" or "failed");
            }
        });
        worker.Start(); poller.Start();
        if (abandoned) second.Start();
        long start = Stopwatch.GetTimestamp();
        rc = Ryujinx.Library.Library.EmbeddedPrepareJit();
        double ms = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
        step["beatThreadsAtReturn"] = BeatThreads();
        Volatile.Write(ref preparing, false);
        worker.Join(); poller.Join();
        if (abandoned) { second.Join(); step["gateWaitMs"] = Math.Round(gateWaitMs, 2); step["gateAfterPrepare"] = gateAfterPrepare; }
        step["rc"] = rc;
        step["prepareMs"] = Math.Round(ms, 2);
        step["besideWorkMs"] = beside;
        step["polls"] = polls;
        step["mappedMiB"] = DualMappedMemory.ArenaSize / MiB;
        step["trapsAdded"] = Helper.Traps - traps;
        step["pagesAdded"] = Helper.Pages - pages;
        step["regionsAdded"] = Helper.Regions - regions;
        step["aliasesAdded"] = Helper.Aliases - aliases;
        step["heldMs"] = Math.Round(Helper.HeldMs - held, 2);
        step["quarantined"] = Ryujinx.Library.Library.Quarantined;
        int guestBefore = _guestRuns;
        // As the application: a failed preparation throws out of the launch before the session host exists.
        if (rc == 0 && !abandoned) StartSession(step);
        step["guestRan"] = _guestRuns - guestBefore;
        step["journal"] = NewJournal();
        Steps.Add(step);
    }

    private static void Use(string argument)
    {
        var step = new Dictionary<string, object> { ["op"] = "U" + argument };
        long target = long.Parse(argument) * (long)MiB;
        object shared = CacheField("_sharedCache");
        MethodInfo allocate = shared.GetType().GetMethod("Allocate");
        PropertyInfo peak = shared.GetType().GetProperty("PeakBytes");
        string failure = "";
        try
        {
            // The real cache allocator, without writing the code, until this session has allocated the target
            // (4 KiB stand for the session's own function).
            while (_sessionAllocated + 4096 < target)
            {
                int size = (int)Math.Min(8 * (long)MiB, target - 4096 - _sessionAllocated);
                allocate.Invoke(shared, new object[] { size });
                _sessionAllocated += size;
            }
        }
        catch (TargetInvocationException error) { failure = error.InnerException.GetType().Name + ": " + error.InnerException.Message; }
        step["allocatedMiB"] = _sessionAllocated / (long)MiB;
        step["failure"] = failure;
        if (peak != null) step["cachePeakBytes"] = (int)peak.GetValue(shared);
        step["journal"] = NewJournal();
        Steps.Add(step);
    }

    private static void Close()
    {
        var step = new Dictionary<string, object> { ["op"] = "C" };
        step["cachePeakBytes"] = CachePeak();
        // Translator.Dispose: the cache is disposed; the arena stays. A second Dispose must add nothing.
        _cache.Dispose();
        _cache.Dispose();
        _cache = null; _translator = null;
        step["mappedMiB"] = DualMappedMemory.ArenaSize / MiB;
        step["journal"] = NewJournal();
        Steps.Add(step);
    }

    private static int CachePeak()
    {
        object shared = CacheField("_sharedCache");
        PropertyInfo peak = shared.GetType().GetProperty("PeakBytes");
        return peak == null ? -1 : (int)peak.GetValue(shared);
    }

    private static void Settle()
    {
        var step = new Dictionary<string, object> { ["op"] = "Q" };
        int peak = _cache == null ? -1 : CachePeak();
        long start = Stopwatch.GetTimestamp();
        while (peak >= 0 && Stopwatch.GetElapsedTime(start).TotalMilliseconds < 5000 &&
               EmbeddedLaunchDiagnostics.Snapshot().Skip(_sessionJournalStart).Count(e => e.Status == "reached") < peak / (64 << 20)) Thread.Sleep(5);
        Thread.Sleep(60);
        step["cachePeakBytes"] = peak;
        step["journal"] = NewJournal();
        Steps.Add(step);
    }

    // Randomized: threads translate functions of random sizes through the real Map (one cache, its own lock), while
    // another takes launches, another flips the session state and another polls the journal.
    private static void Race(string argument)
    {
        var step = new Dictionary<string, object> { ["op"] = "R" + argument };
        int seed = int.Parse(argument);
        var random = new Random(seed);
        int threads = 4, maps = 500 + random.Next(300);
        int[] seeds = Enumerable.Range(0, threads + 2).Select(_ => random.Next()).ToArray();
        long[] sums = new long[threads];
        var failures = new List<string>();
        int launches = 0, refused = 0, busy = 0, mapped = 0;
        var gate = new ManualResetEventSlim(false);
        var workers = new List<Thread>();
        byte[] code = new byte[128 * 1024];
        for (int t = 0; t < threads; t++)
        {
            int index = t;
            workers.Add(new Thread(() =>
            {
                var local = new Random(seeds[index]);
                gate.Wait();
                try
                {
                    for (int i = 0; i < maps; i++)
                    {
                        int size = local.Next(8) == 0 ? local.Next(1, code.Length) : local.Next(1, 96 * 1024);
                        _cache.Map(code.AsSpan(0, size), 0x10000000UL + ((ulong)index << 24) + (ulong)i * 16, 4);
                        sums[index] += (size + 3) & ~3;
                        Interlocked.Increment(ref mapped);
                        if (local.Next(32) == 0) Thread.Yield();
                    }
                }
                catch (Exception error) { lock (failures) failures.Add(error.GetType().Name + ": " + error.Message); }
            }));
        }
        workers.Add(new Thread(() =>
        {
            var local = new Random(seeds[threads]);
            gate.Wait();
            for (int i = 0; i < 60; i++)
            {
                Ryujinx.Library.Library.Preflight(local.Next(3) == 0 ? 1024 * MiB : 0);
                int rc = Ryujinx.Library.Library.EmbeddedPrepareJit();
                if (rc == 0) Interlocked.Increment(ref launches);
                else if (rc == 1) Interlocked.Increment(ref refused);
                else if (rc == 2) Interlocked.Increment(ref busy);
                else lock (failures) failures.Add("prepare returned " + rc);
                if (local.Next(4) == 0) Thread.Sleep(local.Next(3));
            }
        }));
        workers.Add(new Thread(() =>
        {
            var local = new Random(seeds[threads + 1]);
            gate.Wait();
            for (int i = 0; i < 200; i++)
            {
                lock (Ryujinx.Library.Library.EmbeddedHostGate) Ryujinx.Library.EmbeddedSessions.State = local.Next(3) == 0 ? 1 : 0;
                Thread.Sleep(local.Next(2));
            }
            lock (Ryujinx.Library.Library.EmbeddedHostGate) Ryujinx.Library.EmbeddedSessions.State = 0;
        }));
        workers.Add(new Thread(() =>
        {
            gate.Wait();
            for (int i = 0; i < 300; i++) { EmbeddedLaunchDiagnostics.Snapshot(); Thread.Yield(); }
        }));
        long before = _sessionAllocated + 8; // the session's own function
        foreach (Thread worker in workers) worker.Start();
        gate.Set();
        foreach (Thread worker in workers)
        {
            if (!worker.Join(120000)) failures.Add("a thread is blocked");
        }
        step["seed"] = seed;
        step["expectedPeak"] = before + sums.Sum();
        step["mapped"] = mapped;
        step["registered"] = _translator.Registered;
        step["launches"] = launches; step["refused"] = refused; step["busy"] = busy;
        step["failures"] = failures;
        step["beatThreads"] = BeatThreads();
        step["quarantined"] = Ryujinx.Library.Library.Quarantined;
        step["journal"] = NewJournal();
        Steps.Add(step);
    }

    // What the tracking costs on the translation path: the real Map of a 64-byte function, best of seven rounds.
    private static void Bench(string argument)
    {
        var step = new Dictionary<string, object> { ["op"] = "B" + argument };
        int count = int.Parse(argument);
        byte[] code = new byte[64];
        double best = double.MaxValue;
        ulong address = 0x40000000UL;
        for (int round = 0; round < 7; round++)
        {
            long start = Stopwatch.GetTimestamp();
            for (int i = 0; i < count; i++) _cache.Map(code, address += 64, 64);
            best = Math.Min(best, Stopwatch.GetElapsedTime(start).TotalNanoseconds / count);
        }
        step["nsPerMap"] = Math.Round(best, 2);
        step["journal"] = NewJournal();
        Steps.Add(step);
    }

    private static int Main(string[] args)
    {
        string games = args[0];
        AppDataManager.GamesDirPath = games == "-" ? null : games;
        Helper.Handle = NativeLibrary.Load(Path.Combine(AppContext.BaseDirectory, "libhelper_double.so"));
        HostMemoryBudget.TotalBytes = 8192 * MiB;
        string crash = "";
        try
        {
            foreach (string op in args.Skip(1))
            {
                if (op.StartsWith("budget=")) HostMemoryBudget.TotalBytes = ulong.Parse(op[7..]) * MiB;
                else if (op.StartsWith("helper="))
                {
                    long[] v = op[7..].Split(',').Select(long.Parse).ToArray();
                    Helper.helper_double_configure(v[0], (int)v[1], (int)v[2]);
                }
                else if (op == "nodual") Helper.DualMappingEnabled = false;
                else if (op[0] == 'L') Launch(op[1..], false);
                else if (op[0] == 'K') Launch(op[1..], true);
                else if (op[0] == 'U') Use(op[1..]);
                else if (op[0] == 'C') Close();
                else if (op[0] == 'A') Ryujinx.Library.EmbeddedSessions.State = int.Parse(op[1..]);
                else if (op[0] == 'Q') Settle();
                else if (op[0] == 'R') Race(op[1..]);
                else if (op[0] == 'B') Bench(op[1..]);
                else throw new ArgumentException(op);
            }
        }
        catch (Exception error) { crash = error.ToString(); }
        var report = new Dictionary<string, object>
        {
            ["steps"] = Steps,
            ["crash"] = crash,
            ["traps"] = Helper.Traps, ["pages"] = Helper.Pages, ["detaches"] = Helper.Detaches, ["sizedRequests"] = Helper.SizedRequests,
            ["aliases"] = Helper.Aliases, ["trapsAfterDetach"] = Helper.TrapsAfterDetach, ["regions"] = Helper.Regions,
            ["heldMs"] = Math.Round(Helper.HeldMs, 2),
            ["guestRuns"] = _guestRuns,
            ["beatThreads"] = BeatThreads(),
            ["invalidations"] = JitSupportDarwin.Invalidations,
            ["gamesFiles"] = games == "-" ? 0 : Directory.GetFileSystemEntries(games).Length,
            ["architecture"] = RuntimeInformation.ProcessArchitecture.ToString(),
            ["tail"] = NewJournal(),
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
