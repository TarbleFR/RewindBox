// Fixture for adapt_collection_class: the adapter's class text, unchanged (the gate writes it next to this file), driven
// by the runtime's real collection callouts.
// Compiled ahead of time (the Core's runtime kind):
//   "host" (any platform): the platform functions are the fixture's (a class per thread, counted overrides, real
//     clocks): which collections raise their thread, where the override ends for each kind of collection, that
//     nothing is allocated inside a collection, the accounting by class, the session mark.
//   "plain" (not an Apple platform): nothing is registered and collections run as they are.
//   "apple" (macOS arm64): the production platform functions (QoS classes, overrides, thread clocks) on threads of real
//     classes, while user-interactive threads run native code that a collection does not stop: wall and CPU time of
//     the collections a utility thread triggers, with the raising off and on.
// Run on the just-in-time runtime ("refused"): that runtime has no such registration; the class reports it and
// collections run as they are.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using System.Threading;

static unsafe class Host
{
    [DllImport("libc", EntryPoint = "pthread_self"), SuppressGCTransition] static extern nint pthread_self();
    [StructLayout(LayoutKind.Sequential)] struct Timespec { public long Seconds, Nanoseconds; }
    [DllImport("libc", EntryPoint = "clock_gettime"), SuppressGCTransition] static extern int clock_gettime(int clock, Timespec* time);

    const int Slots = 64;
    static readonly nint[] Threads = new nint[Slots];
    static readonly uint[] Classes = new uint[Slots];
    public static readonly int[] RaisedBySlot = new int[Slots];
    static int _used;
    public static int Alive, MostAlive, Raises, Lowers, UnknownThread;

    public static int SetClass(uint qosClass)
    {
        nint self = pthread_self();
        int slot = SlotOf(self); // a handle is used again once its thread has ended
        if (slot < 0) slot = Interlocked.Increment(ref _used) - 1;
        Classes[slot] = qosClass;
        RaisedBySlot[slot] = 0;
        Threads[slot] = self;
        return slot;
    }

    static int SlotOf(nint thread)
    {
        for (int i = 0; i < Slots; i++) if (Threads[i] == thread) return i;
        return -1;
    }

    static nint Self() => pthread_self();
    static uint ClassOfSelf() { int slot = SlotOf(pthread_self()); return slot < 0 ? CollectionClass.Default : Classes[slot]; }
    static nint Raise(nint thread)
    {
        int slot = SlotOf(thread);
        if (slot < 0) { UnknownThread++; return 0; }
        RaisedBySlot[slot]++;
        Raises++;
        int alive = Interlocked.Increment(ref Alive);
        if (alive > MostAlive) MostAlive = alive;
        return slot + 1;
    }
    static void Lower(nint token) { Lowers++; Interlocked.Decrement(ref Alive); }
    static ulong Clock(int clock) { Timespec time; clock_gettime(clock, &time); return (ulong)time.Seconds * 1_000_000_000UL + (ulong)time.Nanoseconds; }
    static ulong WallNs() => Clock(1); // CLOCK_MONOTONIC
    static ulong CpuNs() => Clock(3);  // CLOCK_THREAD_CPUTIME_ID

    public static void Install()
    {
        CollectionClass.Self = &Self;
        CollectionClass.ClassOfSelf = &ClassOfSelf;
        CollectionClass.Raise = &Raise;
        CollectionClass.Lower = &Lower;
        CollectionClass.WallNs = &WallNs;
        CollectionClass.CpuNs = &CpuNs;
        CollectionClass.Applies = true;
    }
}

static unsafe class Apple
{
    const string LibSystem = "/usr/lib/libSystem.B.dylib";
    [DllImport(LibSystem, EntryPoint = "pthread_set_qos_class_self_np")] public static extern int SetClass(uint qosClass, int relativePriority);
    [DllImport(LibSystem, EntryPoint = "qos_class_self")] public static extern uint ClassOfSelf();
    [DllImport(LibSystem, EntryPoint = "CC_SHA256")] public static extern byte* Sha256(byte* data, uint length, byte* digest);
    [DllImport(LibSystem, EntryPoint = "sysctlbyname")] static extern int sysctlbyname(byte* name, void* value, nuint* size, void* newValue, nuint newSize);

    public static int Cores()
    {
        int cores = 0;
        nuint size = sizeof(int);
        fixed (byte* name = "hw.ncpu\0"u8) sysctlbyname(name, &cores, &size, null, 0);
        return cores;
    }
}

static unsafe class Program
{
    static readonly List<byte[]> Kept = new();

    // Allocates on the calling thread until it has triggered `collections` more collections of generation 0.
    static void AllocateUntil(int collections, int keepEvery = 0)
    {
        int target = GC.CollectionCount(0) + collections;
        Random random = new(7);
        long n = 0;
        while (GC.CollectionCount(0) < target)
        {
            byte[] block = new byte[random.Next(64, 2048)];
            if (keepEvery != 0 && ++n % keepEvery == 0)
            {
                lock (Kept) { Kept.Add(block); if (Kept.Count > 40000) Kept.RemoveRange(0, 20000); }
            }
        }
    }

    // Collections with work to do, as in a game's heap: an old array of references whose slots keep receiving new
    // objects, so each collection of the young generation scans it and promotes what it now holds.
    static object[] _old;

    static void SurviveUntil(int collections)
    {
        _old ??= new object[3_000_000];
        int target = GC.CollectionCount(0) + collections;
        Random random = new(11);
        while (GC.CollectionCount(0) < target)
        {
            for (int i = 0; i < 256; i++) _old[random.Next(_old.Length)] = new byte[random.Next(64, 1024)];
        }
    }

    static T On<T>(Func<T> body)
    {
        T result = default;
        Thread thread = new(() => result = body());
        thread.Start();
        thread.Join();
        return result;
    }

    static void WaitForBackground(long index)
    {
        for (int i = 0; i < 400 && GC.GetGCMemoryInfo(GCKind.Background).Index == index; i++) Thread.Sleep(10);
        Thread.Sleep(50);
    }

    static JsonObject Stress(bool poll)
    {
        long startsBefore = CollectionClass.Starts, endsBefore = CollectionClass.Ends, generation2 = GC.CollectionCount(2);
        long nextStart = CollectionClass.EndedByNextStart, another = CollectionClass.EndedByAnotherThread, polls = CollectionClass.EndedAfterRestart;
        long raises = Host.Raises, lowers = Host.Lowers;
        uint[] classes = { CollectionClass.Utility, CollectionClass.Default, CollectionClass.Background, CollectionClass.UserInteractive };
        Thread[] threads = new Thread[classes.Length];
        long deadline = Environment.TickCount64 + 2000;
        for (int t = 0; t < threads.Length; t++)
        {
            uint qosClass = classes[t];
            int seed = t;
            threads[t] = new Thread(() =>
            {
                Host.SetClass(qosClass);
                Random random = new(seed);
                List<byte[]> mine = new();
                long n = 0;
                while (Environment.TickCount64 < deadline)
                {
                    byte[] block = new byte[random.Next(64, 4096)];
                    if (++n % 5 == 0) { mine.Add(block); if (mine.Count > 30000) mine.RemoveRange(0, 15000); }
                    if (n % 3000 == 0) mine.Add(new byte[120_000 + random.Next(200_000)]);
                    if (n % 50000 == 0 && seed == 1) GC.Collect(2, GCCollectionMode.Forced, blocking: false);
                }
            });
            threads[t].Start();
        }
        Thread poller = new(() =>
        {
            Host.SetClass(CollectionClass.Utility);
            while (Environment.TickCount64 < deadline) { Thread.Sleep(1); if (poll) CollectionClass.ReleaseAfterRestart(); }
        });
        poller.Start();
        foreach (Thread thread in threads) thread.Join();
        poller.Join();
        WaitForBackground(-1);
        On(() => { Host.SetClass(CollectionClass.UserInteractive); GC.Collect(2, GCCollectionMode.Forced, blocking: true); return 0; });
        Thread.Sleep(200);
        return new JsonObject
        {
            ["starts"] = CollectionClass.Starts - startsBefore, ["ends"] = CollectionClass.Ends - endsBefore, ["generation2"] = GC.CollectionCount(2) - generation2,
            ["endedByNextStart"] = CollectionClass.EndedByNextStart - nextStart, ["endedByAnotherThread"] = CollectionClass.EndedByAnotherThread - another,
            ["endedByPoll"] = CollectionClass.EndedAfterRestart - polls, ["raises"] = Host.Raises - raises, ["lowers"] = Host.Lowers - lowers,
            ["alive"] = Host.Alive, ["inForceAfter"] = CollectionClass.OverrideInForce,
        };
    }

    static JsonObject HostRun()
    {
        Host.Install();
        int first = CollectionClass.Register(), second = CollectionClass.Register();
        Host.SetClass(CollectionClass.UserInteractive); // the main thread

        // 1. A utility thread's own collections.
        var utility = On(() =>
        {
            int slot = Host.SetClass(CollectionClass.Utility);
            long before = CollectionClass.Of(CollectionClass.Utility).Count, raised = CollectionClass.Raised;
            AllocateUntil(25);
            var totals = CollectionClass.Of(CollectionClass.Utility);
            return new JsonObject { ["collections"] = totals.Count - before, ["raised"] = CollectionClass.Raised - raised, ["raisedThisThread"] = Host.RaisedBySlot[slot],
                         ["inForceAfter"] = CollectionClass.OverrideInForce, ["cpuWithinWall"] = totals.CpuNs <= totals.WallNs + 2_000_000 };
        });

        // 2. A user-interactive thread and a thread outside the classes are left as they are.
        var interactive = On(() =>
        {
            int slot = Host.SetClass(CollectionClass.UserInteractive);
            long before = CollectionClass.Of(CollectionClass.UserInteractive).Count, raised = CollectionClass.Raised;
            AllocateUntil(10);
            return new JsonObject { ["collections"] = CollectionClass.Of(CollectionClass.UserInteractive).Count - before, ["raised"] = CollectionClass.Raised - raised,
                         ["raisedThisThread"] = Host.RaisedBySlot[slot] };
        });
        var unspecified = On(() =>
        {
            int slot = Host.SetClass(CollectionClass.Unspecified);
            long before = CollectionClass.Of(CollectionClass.Unspecified).Count, raised = CollectionClass.Raised;
            AllocateUntil(10);
            return new JsonObject { ["collections"] = CollectionClass.Of(CollectionClass.Unspecified).Count - before, ["raised"] = CollectionClass.Raised - raised,
                         ["raisedThisThread"] = Host.RaisedBySlot[slot] };
        });

        // 3. Nothing is allocated inside a collection (the callouts run on the collecting thread).
        var allocation = On(() =>
        {
            Host.SetClass(CollectionClass.Utility);
            long raised = CollectionClass.Raised, before = GC.GetAllocatedBytesForCurrentThread();
            GC.Collect(0, GCCollectionMode.Forced, blocking: true);
            GC.Collect(1, GCCollectionMode.Forced, blocking: true);
            GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
            long after = GC.GetAllocatedBytesForCurrentThread();
            return new JsonObject { ["bytesAllocatedByThreeCollections"] = after - before, ["raised"] = CollectionClass.Raised - raised, ["inForceAfter"] = CollectionClass.OverrideInForce };
        });

        // 5. Raising off: accounted, never raised.
        CollectionClass.RaiseCollectingThread = false;
        var off = On(() =>
        {
            Host.SetClass(CollectionClass.Utility);
            long before = CollectionClass.Of(CollectionClass.Utility).Count, raised = CollectionClass.Raised;
            AllocateUntil(10);
            return new JsonObject { ["collections"] = CollectionClass.Of(CollectionClass.Utility).Count - before, ["raised"] = CollectionClass.Raised - raised };
        });
        CollectionClass.RaiseCollectingThread = true;

        // 6. Four threads of four classes for two seconds, with survivors and large blocks so that background collections
        //    start with and without a collection before them, and collections happen while one runs. Twice: as it is
        //    (an override left by a collection that goes on in the background is ended by the next collection or by the
        //    background thread), then with a thread that polls as the keep-alive does (managed code runs, so the engine
        //    is running again: the override is ended there).
        JsonObject stress = Stress(poll: false), polled = Stress(poll: true);

        // 4. A background collection requested by a default-class thread, the background thread being there: whatever
        //    the runtime decides (in the background, with or without a collection first, or blocking), an override is in
        //    force when the request returns only if no end was reported, and the poll ends it.
        var background = On(() =>
        {
            Host.SetClass(CollectionClass.Default);
            JsonArray requests = new();
            for (int attempt = 0; attempt < 3; attempt++)
            {
                long index = GC.GetGCMemoryInfo(GCKind.Background).Index, blocking = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
                long raised = CollectionClass.Raised, starts = CollectionClass.Starts, ends = CollectionClass.Ends, polls = CollectionClass.EndedAfterRestart;
                GC.Collect(2, GCCollectionMode.Forced, blocking: false);
                bool inForce = CollectionClass.OverrideInForce;
                long startsAtReturn = CollectionClass.Starts - starts, endsAtReturn = CollectionClass.Ends - ends;
                CollectionClass.ReleaseAfterRestart();
                bool inForceAfterPoll = CollectionClass.OverrideInForce;
                int alive = Host.Alive;
                if (GC.GetGCMemoryInfo(GCKind.FullBlocking).Index == blocking) WaitForBackground(index);
                requests.Add((JsonNode)new JsonObject { ["startsAtReturn"] = startsAtReturn, ["endsAtReturn"] = endsAtReturn, ["raised"] = CollectionClass.Raised - raised,
                    ["inForceAtReturn"] = inForce, ["inForceAfterPoll"] = inForceAfterPoll, ["aliveAfterPoll"] = alive,
                    ["endedByPoll"] = CollectionClass.EndedAfterRestart - polls, ["ranBlocking"] = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index != blocking,
                    ["inBackground"] = GC.GetGCMemoryInfo(GCKind.Background).Index != index, ["inForceAfter"] = CollectionClass.OverrideInForce });
                AllocateUntil(1);
            }
            return new JsonObject { ["requests"] = requests };
        });

        // 7. The collections the macOS measurement uses (an old array that keeps receiving new objects): their cost here.
        var surviving = On(() =>
        {
            Host.SetClass(CollectionClass.Utility);
            var before = CollectionClass.Of(CollectionClass.Utility);
            SurviveUntil(12);
            var after = CollectionClass.Of(CollectionClass.Utility);
            long count = after.Count - before.Count;
            return new JsonObject { ["collections"] = count, ["cpuMsEach"] = count == 0 ? 0 : (after.CpuNs - before.CpuNs) / 1e6 / count,
                ["wallMsEach"] = count == 0 ? 0 : (after.WallNs - before.WallNs) / 1e6 / count };
        });
        _old = null;

        string describe = CollectionClass.Describe();
        long raisedInAll = CollectionClass.Raised;
        CollectionClass.MarkSession();
        JsonObject marked = new JsonObject { ["starts"] = CollectionClass.Starts, ["raised"] = CollectionClass.Raised,
            ["utility"] = CollectionClass.Of(CollectionClass.Utility).Count, ["describe"] = CollectionClass.Describe() };
        return new JsonObject {
            ["mode"] = "host", ["registered"] = first, ["registeredAgain"] = second, ["utility"] = utility, ["interactive"] = interactive, ["unspecified"] = unspecified, ["allocation"] = allocation, ["off"] = off, ["stress"] = stress, ["polled"] = polled, ["background"] = background, ["surviving"] = surviving,
            ["platform"] = new JsonObject { ["raises"] = Host.Raises, ["lowers"] = Host.Lowers, ["alive"] = Host.Alive, ["mostAlive"] = Host.MostAlive, ["unknownThread"] = Host.UnknownThread },
            ["raised"] = raisedInAll, ["describe"] = describe, ["marked"] = marked
        };
    }

    // Collections a utility thread triggers while user-interactive threads run native code (not stopped by a collection).
    static JsonObject AppleRound(bool raise, int collections, int loads)
    {
        CollectionClass.RaiseCollectingThread = raise;
        int stop = 0;
        Thread[] busy = new Thread[loads];
        for (int i = 0; i < loads; i++)
        {
            busy[i] = new Thread(() =>
            {
                Apple.SetClass(CollectionClass.UserInteractive, 0);
                byte* data = (byte*)NativeMemory.Alloc(1 << 20);
                byte* digest = stackalloc byte[32];
                new Span<byte>(data, 1 << 20).Fill(1);
                while (Volatile.Read(ref stop) == 0) Apple.Sha256(data, 1 << 20, digest); // native code, preemptive
                NativeMemory.Free(data);
            });
            busy[i].Start();
        }
        Thread.Sleep(300);
        var result = On(() =>
        {
            int status = Apple.SetClass(CollectionClass.Utility, 0);
            var before = CollectionClass.Of(CollectionClass.Utility);
            long raised = CollectionClass.Raised;
            SurviveUntil(collections);
            var after = CollectionClass.Of(CollectionClass.Utility);
            return new JsonObject {
                ["raise"] = raise, ["setClassStatus"] = status, ["classIsUtility"] = Apple.ClassOfSelf() == CollectionClass.Utility,
                ["collections"] = after.Count - before.Count, ["raised"] = CollectionClass.Raised - raised,
                ["wallMs"] = (after.WallNs - before.WallNs) / 1e6, ["cpuMs"] = (after.CpuNs - before.CpuNs) / 1e6,
                ["inForceAfter"] = CollectionClass.OverrideInForce
            };
        });
        Volatile.Write(ref stop, 1);
        foreach (Thread thread in busy) thread.Join();
        return result;
    }

    static JsonObject AppleRun()
    {
        int registered = CollectionClass.Register();
        int cores = Apple.Cores();
        Apple.SetClass(CollectionClass.UserInteractive, 0);
        JsonArray rounds = new();
        for (int i = 0; i < 3; i++)
        {
            rounds.Add((JsonNode)AppleRound(raise: false, 12, cores + 2));
            rounds.Add((JsonNode)AppleRound(raise: true, 12, cores + 2));
        }
        return new JsonObject { ["mode"] = "apple", ["registered"] = registered, ["cores"] = cores, ["busyUserInteractiveThreads"] = cores + 2, ["rounds"] = rounds, ["describe"] = CollectionClass.Describe() };
    }

    // Nothing registered (not this platform, or a runtime without the registration): collections run as they are.
    static JsonObject UnregisteredRun(string mode, bool install)
    {
        if (install) Host.Install();
        int first = CollectionClass.Register(), second = CollectionClass.Register();
        int before = GC.CollectionCount(0);
        On(() => { AllocateUntil(10); GC.Collect(2, GCCollectionMode.Forced, blocking: true); return 0; });
        CollectionClass.ReleaseAfterRestart();
        CollectionClass.MarkSession();
        return new JsonObject { ["mode"] = mode, ["registered"] = first, ["registeredAgain"] = second, ["status"] = CollectionClass.Status,
            ["collections"] = GC.CollectionCount(0) - before, ["starts"] = CollectionClass.Starts, ["ends"] = CollectionClass.Ends,
            ["raised"] = CollectionClass.Raised, ["inForce"] = CollectionClass.OverrideInForce, ["platformRaises"] = Host.Raises,
            ["platformLowers"] = Host.Lowers, ["describe"] = CollectionClass.Describe() };
    }

    static int Main(string[] arguments)
    {
        string mode = arguments.Length > 0 ? arguments[0] : "host";
        JsonObject result = mode switch
        {
            "apple" => AppleRun(),
            "plain" => UnregisteredRun(mode, install: false),
            "refused" => UnregisteredRun(mode, install: true),
            _ => HostRun(),
        };
        Console.WriteLine(result.ToJsonString());
        return 0;
    }
}
