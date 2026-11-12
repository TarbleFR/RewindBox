"""A collection that stops the engine runs in the user-interactive class, whichever thread triggers it (Core 745 candidate).

IPA 729 / Core 743, Hogwarts Legacy 1x (pid 58475), gcPause journal: ephemeral collections that promote almost nothing
stop the engine for hundreds of milliseconds (gen0 363.9 ms promoting 2.2 MiB, gen0 447.6 ms promoting 0.1 MiB with
gen0 16.0 -> 0.1 MiB, gen0 720.6 ms promoting 1.1 MiB; session: gen0 pauses 1 880 ms, gen1 2 446 ms, 33 pauses over one
33.3 ms frame). The work of such a collection is a few milliseconds of CPU.

Cause, from the runtime's source and two measurements. The workstation collector runs a blocking collection on the
thread whose allocation triggered it (gc.cpp garbage_collect, called by the allocating thread once the engine is
suspended); the other engine threads wait for it. The guest's CPU threads, the render thread and GPU.MainThread are in
the user-interactive class since Core 733 (adapt_host_thread_class) and the guest's threads run translated code, which
a collection does not stop; every other engine thread (thread pool, pipeline compile workers, cache loader, decoders,
the keep-alive) is in the default class or lower. IPA 725 freeze snapshot: the thread inside the collector had
priority 20 and received 15.6 ms of CPU in 961 ms, the render and GPU threads parked. Scheduling probe on macOS arm64
(test/melonx_collection_class/qos_probe.c, workflow run 43315146893, as an interactive job, three runs): 20 ms of CPU on
a utility, default or background thread while cores + 2 user-interactive threads are busy takes 107-120 ms; with a
user-interactive QoS override on the thread (started by itself or by another thread) 20.0 ms; the override ended, 108-188 ms
again; a user-interactive thread 20.0 ms throughout. This class with the real runtime, same workflow (run 43323499544,
compiled ahead of time for osx-arm64; cores + 2 user-interactive threads in native calls of several hundred
milliseconds each, as guest threads in translated code): the collections a utility thread triggered took 10 197.8 ms
for 492.7 ms of CPU with the raising off (the longest 890.4 ms for 31.3 ms of CPU) and 510.8 ms for 491.6 ms with it on.

Change (EmbeddedSession.cs only). The runtime's restricted callouts for the start and the end of a collection
(RhRegisterGcCallout, the registration its own Objective-C support uses) are registered once per process when the
first session starts. At a start, on the collecting thread: its QoS class and clocks are read, and unless it is
user-interactive already or outside the QoS classes it receives a user-interactive override
(pthread_override_qos_class_start_np). The override is ended at the collection's end (by the thread that reports it),
at the next collection's start, or - when the collection goes on in the background with the engine running again and
reports no end before it finishes - by the keep-alive's next poll (250 ms), which runs managed code and therefore only
when the engine is running. Each collection is accounted by the class of the thread that ran it (count, wall and CPU
time, the longest with its CPU time) and the session's close journals one line (gcPause, class): on the device this
line is the measure that decides the mechanism (wall far above CPU for the lower classes without the override; wall
near CPU with it). The callouts allocate nothing and call only functions bound at the registration.
No collection is added, requested, delayed or resized; no thread keeps a raised class outside a collection; threads
that are not in a collection are untouched; CollectionClass.RaiseCollectingThread = false leaves the accounting alone.
Other platforms, a runtime without the callouts, a system that gives the registering thread no override: nothing is
registered (status 2, 3 or 4 in the journal line). The end callout is registered before the start one.

Expected on the device (same save and route): ephemeral pauses that promote under 5 MiB stay under 33 ms (729: up to
720 ms), gcPause summary "over 33.3 ms" 33 -> 10 or fewer, and the class line shows wall within 1.5 times CPU for every
class. Refuted and removed if the long low-promotion pauses stay while the class line shows them run with wall near
CPU (the time is then spent inside the collection: memory, not scheduling), or if presented frames per second fall.
Not treated: the parts of a background collection its own thread runs with the engine stopped (the class line does not
time them), the gen1 collections that really promote 15-104 MiB (their CPU work), collections run by a thread outside
the QoS classes (counted as "unspecified").
Rollback: drop this adapter from prepare_embedded.py and the plan. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {SESSION: 'ada8f577b6bec5c6d7111132298146305f8b7de2e6a2953cfceccbe47f388e5f'}

START_OLD = '''            try { run.CountsAtStart = ReadCollectionCounts(); } catch { } // RewindBox (adapt_gc_pause_journal)
'''
START_NEW = START_OLD + '''            // RewindBox (adapt_collection_class): once per process; the journal's totals are this session's.
            try { CollectionClass.Register(); CollectionClass.MarkSession(); } catch { }
'''

STOP_OLD = '''        try { EmbeddedLaunchDiagnostics.Record("gcPause", "summary", detail: PauseSummary(run)); } catch { } // adapt_gc_pause_journal
'''
STOP_NEW = STOP_OLD + '''        try { EmbeddedLaunchDiagnostics.Record("gcPause", "class", detail: CollectionClass.Describe()); } catch { } // adapt_collection_class
'''

POLL_OLD = '''                System.Threading.Thread.Sleep(PollMs);
                long now = ReadMilliseconds();
'''
POLL_NEW = '''                System.Threading.Thread.Sleep(PollMs);
                // RewindBox (adapt_collection_class): this runs, so the engine does: no collection needs the override it
                // left on its starting thread any more (a collection that goes on in the background).
                CollectionClass.ReleaseAfterRestart();
                long now = ReadMilliseconds();
'''

TAIL_OLD = '''        catch { } // Never change the emulator's result.
    }
}
'''

CLASS = '''// RewindBox (adapt_collection_class): a collection that stops every engine thread runs on the thread whose allocation
// triggered it, while the guest's own threads keep running native code in the user-interactive class. A thread of a
// lower class (thread pool, compile workers, cache and decoder threads) then finishes the collection late: the frame
// waits for it (IPA 725: a collection run by a thread of priority 20 received 15.6 ms of CPU in 961 ms). For the time
// of such a collection the collecting thread is raised to the user-interactive class (a QoS override, ended when the
// collection ends, by whichever thread ends it, or by the keep-alive's next poll when the collection goes on in the
// background with the engine running again), and each collection is accounted by the class of the thread that ran it
// (wall and CPU time), for the session's journal.
// The two callouts run inside the collector, with the engine stopped: they allocate nothing and call only functions
// bound before the registration.
public static unsafe class CollectionClass
{
    // GcRestrictedCalloutKind of the runtime.
    private const int StartCollection = 0, EndCollection = 1;
    public const uint UserInteractive = 0x21, UserInitiated = 0x19, Default = 0x15, Utility = 0x11, Background = 0x09, Unspecified = 0;
    private const int Buckets = 6;
    private const string LibSystem = "/usr/lib/libSystem.B.dylib";

    // The runtime's own registration of a function called when a collection starts or ends; linked statically.
    [System.Runtime.InteropServices.DllImport("*", EntryPoint = "RhRegisterGcCallout"), System.Runtime.InteropServices.SuppressGCTransition]
    private static extern int RhRegisterGcCallout(int kind, delegate* unmanaged<uint, void> callout);

    [System.Runtime.InteropServices.DllImport(LibSystem, EntryPoint = "pthread_self"), System.Runtime.InteropServices.SuppressGCTransition]
    private static extern nint pthread_self();
    [System.Runtime.InteropServices.DllImport(LibSystem, EntryPoint = "qos_class_self"), System.Runtime.InteropServices.SuppressGCTransition]
    private static extern uint qos_class_self();
    [System.Runtime.InteropServices.DllImport(LibSystem, EntryPoint = "pthread_override_qos_class_start_np"), System.Runtime.InteropServices.SuppressGCTransition]
    private static extern nint pthread_override_qos_class_start_np(nint thread, uint qosClass, int relativePriority);
    [System.Runtime.InteropServices.DllImport(LibSystem, EntryPoint = "pthread_override_qos_class_end_np"), System.Runtime.InteropServices.SuppressGCTransition]
    private static extern int pthread_override_qos_class_end_np(nint token);
    [System.Runtime.InteropServices.DllImport(LibSystem, EntryPoint = "clock_gettime_nsec_np"), System.Runtime.InteropServices.SuppressGCTransition]
    private static extern ulong clock_gettime_nsec_np(int clock);

    private static nint PlatformSelf() => pthread_self();
    private static uint PlatformClass() => qos_class_self();
    private static nint PlatformRaise(nint thread) => pthread_override_qos_class_start_np(thread, UserInteractive, 0);
    private static void PlatformLower(nint token) => pthread_override_qos_class_end_np(token);
    private static ulong PlatformWallNs() => clock_gettime_nsec_np(8);  // CLOCK_UPTIME_RAW
    private static ulong PlatformCpuNs() => clock_gettime_nsec_np(16);  // CLOCK_THREAD_CPUTIME_ID

    // The platform: Apple's by default; a fixture sets its own before Register.
    internal static delegate*<nint> Self = &PlatformSelf;
    internal static delegate*<uint> ClassOfSelf = &PlatformClass;
    internal static delegate*<nint, nint> Raise = &PlatformRaise;
    internal static delegate*<nint, void> Lower = &PlatformLower;
    internal static delegate*<ulong> WallNs = &PlatformWallNs;
    internal static delegate*<ulong> CpuNs = &PlatformCpuNs;
    internal static bool Applies = System.OperatingSystem.IsIOS() || System.OperatingSystem.IsMacOS() ||
        System.OperatingSystem.IsMacCatalyst() || System.OperatingSystem.IsTvOS();

    /// <summary>False leaves every collecting thread in its own class (accounting only).</summary>
    public static bool RaiseCollectingThread = true;

    private struct Totals
    {
        public fixed long Count[Buckets];
        public fixed long WallNs[Buckets];
        public fixed long CpuNs[Buckets];
        public fixed long LongestWallNs[Buckets];
        public fixed long LongestCpuNs[Buckets];
    }

    private static Totals _totals;
    private static int _status; // 0 not asked, 1 registered, 2 not this platform, 3 refused by the runtime, 4 no override
    private static nint _token; // the override in force
    private static nint _startThread;
    private static ulong _startWallNs, _startCpuNs;
    private static uint _startClass;
    private static long _starts, _ends, _raised, _refused, _endedByNextStart, _endedByAnotherThread, _endedAfterRestart;

    private static int Bucket(uint qosClass) => qosClass switch
    {
        UserInteractive => 0, UserInitiated => 1, Default => 2, Utility => 3, Background => 4, _ => 5,
    };

    [System.Runtime.InteropServices.UnmanagedCallersOnly]
    private static void OnStart(uint condemnedGeneration)
    {
        // An override whose collection has not ended yet (a background collection still running): ended here.
        nint pending = System.Threading.Interlocked.Exchange(ref _token, 0);
        if (pending != 0)
        {
            Lower(pending);
            _endedByNextStart++;
        }

        _starts++;
        nint self = Self();
        uint qosClass = ClassOfSelf();
        _startThread = self;
        _startClass = qosClass;
        _startCpuNs = CpuNs();
        _startWallNs = WallNs();

        // A thread outside the QoS classes (an explicit priority) is left as it is.
        if (RaiseCollectingThread && qosClass != UserInteractive && qosClass != Unspecified)
        {
            nint token = Raise(self);
            if (token != 0)
            {
                System.Threading.Interlocked.Exchange(ref _token, token);
                _raised++;
            }
            else
            {
                _refused++;
            }
        }
    }

    [System.Runtime.InteropServices.UnmanagedCallersOnly]
    private static void OnEnd(uint condemnedGeneration)
    {
        _ends++;
        nint self = Self();

        // The first end on the thread that started: the part that ran with the engine stopped on that thread.
        if (self == _startThread && _startWallNs != 0)
        {
            long wall = (long)(WallNs() - _startWallNs), cpu = (long)(CpuNs() - _startCpuNs);
            int bucket = Bucket(_startClass);
            _totals.Count[bucket]++;
            _totals.WallNs[bucket] += wall;
            _totals.CpuNs[bucket] += cpu;
            if (wall > _totals.LongestWallNs[bucket])
            {
                _totals.LongestWallNs[bucket] = wall;
                _totals.LongestCpuNs[bucket] = cpu;
            }
            _startWallNs = 0;
        }

        nint token = System.Threading.Interlocked.Exchange(ref _token, 0);
        if (token != 0)
        {
            Lower(token);
            if (self != _startThread) _endedByAnotherThread++;
        }
    }

    /// <summary>
    /// Once per process, from an engine thread before play: 1 registered, 2 not this platform, 3 refused by the runtime,
    /// 4 no override from the system.
    /// </summary>
    public static int Register()
    {
        int status = System.Threading.Volatile.Read(ref _status);
        if (status != 0) return status;
        if (!Applies) return System.Threading.Interlocked.CompareExchange(ref _status, 2, 0) == 0 ? 2 : _status;
        try
        {
            // Every function a callout calls is bound here, outside any collection (a first call binds its library).
            nint self = Self();
            ClassOfSelf();
            CpuNs();
            WallNs();
            nint token = Raise(self);
            if (token == 0)
            {
                status = 4; // the system gives this thread no override (and the end function is not bound): nothing registered
            }
            else
            {
                Lower(token);
                // The end first: a start is never reported without its end.
                bool registered = (RhRegisterGcCallout(EndCollection, &OnEnd) & 0xff) != 0 && (RhRegisterGcCallout(StartCollection, &OnStart) & 0xff) != 0;
                status = registered ? 1 : 3;
            }
        }
        catch (System.Exception)
        {
            status = 3; // not the runtime this was written for: collections stay as they are
        }
        return System.Threading.Interlocked.CompareExchange(ref _status, status, 0) == 0 ? status : _status;
    }

    /// <summary>
    /// From managed code, so with the engine running: ends the override a collection left on the thread that started it
    /// when that collection goes on in the background (no end is reported before the background collection finishes).
    /// </summary>
    public static void ReleaseAfterRestart()
    {
        if (System.Threading.Volatile.Read(ref _token) == 0) return;
        nint token = System.Threading.Interlocked.Exchange(ref _token, 0);
        if (token == 0) return;
        Lower(token);
        System.Threading.Interlocked.Increment(ref _endedAfterRestart);
    }

    /// <summary>A session starts: the journal's totals are the session's.</summary>
    public static void MarkSession()
    {
        _totals = default;
        _starts = _ends = _raised = _refused = _endedByNextStart = _endedByAnotherThread = _endedAfterRestart = 0;
    }

    public static int Status => System.Threading.Volatile.Read(ref _status);
    public static long Starts => _starts;
    public static long Ends => _ends;
    public static long Raised => _raised;
    public static long EndedByNextStart => _endedByNextStart;
    public static long EndedByAnotherThread => _endedByAnotherThread;
    public static long EndedAfterRestart => _endedAfterRestart;
    public static bool OverrideInForce => System.Threading.Volatile.Read(ref _token) != 0;
    public static (long Count, long WallNs, long CpuNs, long LongestWallNs, long LongestCpuNs) Of(uint qosClass)
    {
        int bucket = Bucket(qosClass);
        return (_totals.Count[bucket], _totals.WallNs[bucket], _totals.CpuNs[bucket], _totals.LongestWallNs[bucket], _totals.LongestCpuNs[bucket]);
    }

    /// <summary>For the session's journal, outside any collection.</summary>
    public static string Describe()
    {
        int status = Status;
        if (status != 1)
        {
            return status switch
            {
                0 => "collection class: not registered", 2 => "collection class: not this platform",
                4 => "collection class: no override from the system", _ => "collection class: refused by the runtime",
            } +
                " (adapt_collection_class)";
        }
        System.Text.StringBuilder text = new("Collections that stopped the engine, by the class of the thread that ran them: ");
        (string Name, uint Class)[] classes =
        {
            ("user-interactive", UserInteractive), ("user-initiated", UserInitiated), ("default", Default), ("utility", Utility),
            ("background", Background), ("unspecified", Unspecified),
        };
        System.Globalization.CultureInfo invariant = System.Globalization.CultureInfo.InvariantCulture;
        foreach ((string name, uint qosClass) in classes)
        {
            var t = Of(qosClass);
            if (t.Count == 0) continue;
            text.Append(invariant, $"{name} {t.Count} (wall {t.WallNs / 1e6:0.0} ms, CPU {t.CpuNs / 1e6:0.0} ms; longest {t.LongestWallNs / 1e6:0.0} ms with {t.LongestCpuNs / 1e6:0.0} ms of CPU); ");
        }
        text.Append(invariant, $"collecting thread raised {_raised} times (refused {_refused}), override ended by the next collection {_endedByNextStart}, " +
            $"by another thread {_endedByAnotherThread}, by the keep-alive with the engine running {_endedAfterRestart}; starts {_starts}, ends {_ends}" +
            $"{(RaiseCollectingThread ? "" : "; raising off")} (adapt_collection_class).");
        return text.ToString();
    }
}
'''

TAIL_NEW = TAIL_OLD + '\n' + CLASS

PAIRS = ((START_OLD, START_NEW), (STOP_OLD, STOP_NEW), (POLL_OLD, POLL_NEW), (TAIL_OLD, TAIL_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[SESSION], old, new)
    return list(paths.values())
