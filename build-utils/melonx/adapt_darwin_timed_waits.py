"""On Apple platforms a wait until a host time is one kernel timed wait (heat lot 2; Core 749 candidate; every title).

IPA 733 / Core 745 (iPhone binary 2943e064), Hogwarts Legacy 1x (pid 61839), per-thread CPU over 44 s of play from
the [MeloNX:stall] snapshots: the guest timer thread HLE.TimeManager 3.0 % of a core, the nanosleep helper threads
Common.Nanosleep.0-7 2.5 % (four of them active), the compositor SurfaceFlinger.Composer 0.6 %, all in the
user-interactive class (performance cores). Read in the source (Ryujinx.Common/PreciseSleep, KTimeManager,
SurfaceFlinger): on iOS a guest deadline 1 ms or more away is first waited for with WaitOne(whole milliseconds), then
the sub-millisecond rest is handed to a helper thread that nanosleeps and signals the timer thread, which waits up to
1 ms for that signal (two threads and four kernel wakeups per deadline, eight helper threads); a deadline within the
nanosleep bias (about 5 us) is waited for a whole millisecond. The compositor, at each 60 Hz display interval, wakes
150-300 us early (nanosleep's strict bias) and spins with Thread.SpinWait until the exact time.

Change (PreciseSleepHelper.cs only; Apple platforms; other platforms unchanged): PreciseSleepHelper.CreateEvent returns
DarwinSleepEvent, whose SleepUntil is one dispatch_semaphore_wait with the deadline as timeout (Signal posts the
semaphore, with NanosleepEvent's AutoResetEvent semantics); SpinWaitUntilTimePoint(timePoint) first sleeps with
mach_wait_until until that time on the same clock, then finishes as before if it woke early. Deadlines are the same
host times: a wait ends at its deadline or at a signal; nothing is delayed, no rate or cadence changes, no thread's
class changes. The eight nanosleep helper threads are no longer started on Apple platforms.

Expected on the device (same save and route as the IPA 733 capture): HLE.TimeManager plus Common.Nanosleep.* CPU from
5.5 % of a core to under 2.5 %, SurfaceFlinger.Composer under 0.3 %; presented fps, frame times and audio counters
(dsp= late episodes) unchanged. Refuted and removed if frame times or audio lateness worsen, or the timer threads'
CPU does not fall.
Rollback: drop this adapter from prepare_embedded.py and the plan. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

HELPER = 'src/Ryujinx.Common/PreciseSleep/PreciseSleepHelper.cs'
BASELINE = {HELPER: '7bbb2e800017795fb6a71e2790c57673ad80f40adbbb7bc3d425e033ba402c0d'}

CLASS = '''    // RewindBox (adapt_darwin_timed_waits): on Apple platforms a wait until a host time is one kernel timed wait.
    // IPA 733 / Core 745, Hogwarts Legacy (pid 61839, 44 s of play): the guest timer thread (HLE.TimeManager, 3.0 % of
    // a core) and the eight nanosleep helper threads (2.5 %) at the user-interactive class, and the compositor
    // (SurfaceFlinger.Composer, 0.6 %). A guest deadline less than a millisecond away was served by a helper thread
    // that slept and then signalled the timer thread (two threads woken per deadline, after a first wait rounded to the
    // millisecond); one within the nanosleep bias waited a whole millisecond. The compositor woke 150-300 us before
    // each display interval and spun until it (Thread.SpinWait).
    // Here the timer thread waits on a dispatch semaphore with the deadline as its timeout (Signal still wakes it at
    // once), and the compositor's final approach is mach_wait_until on the same clock. The deadlines are the same
    // host times; a wait still ends at its deadline or at a signal, never later by design.
    internal static unsafe class DarwinTimedWait
    {
        private const string LibSystem = "/usr/lib/libSystem.B.dylib";

        [System.Runtime.InteropServices.DllImport(LibSystem)]
        internal static extern nint dispatch_semaphore_create(nint value);
        [System.Runtime.InteropServices.DllImport(LibSystem)]
        internal static extern nint dispatch_semaphore_wait(nint semaphore, ulong timeout);
        [System.Runtime.InteropServices.DllImport(LibSystem)]
        internal static extern nint dispatch_semaphore_signal(nint semaphore);
        [System.Runtime.InteropServices.DllImport(LibSystem)]
        internal static extern ulong dispatch_time(ulong when, long deltaNanoseconds);
        [System.Runtime.InteropServices.DllImport(LibSystem)]
        internal static extern void dispatch_release(nint obj);
        [System.Runtime.InteropServices.DllImport(LibSystem)]
        private static extern ulong mach_absolute_time();
        [System.Runtime.InteropServices.DllImport(LibSystem)]
        private static extern int mach_wait_until(ulong deadline);
        [System.Runtime.InteropServices.DllImport(LibSystem)]
        private static extern int mach_timebase_info(uint* info);

        internal const ulong TimeNow = 0, TimeForever = ulong.MaxValue;

        // Apple platforms only; false keeps the previous behaviour (the fixture's control).
        internal static bool Applies = System.OperatingSystem.IsIOS() || System.OperatingSystem.IsMacOS() ||
            System.OperatingSystem.IsMacCatalyst() || System.OperatingSystem.IsTvOS();

        private static readonly double s_ticksToNs = 1_000_000_000.0 / System.Diagnostics.Stopwatch.Frequency;
        private static double s_nsToMach;

        // Nanoseconds from now until a host time of PerformanceCounter (Stopwatch ticks).
        internal static long NanosecondsUntil(long timePoint) =>
            (long)((timePoint - PerformanceCounter.ElapsedTicks) * s_ticksToNs);

        /// <summary>Sleeps until the host time (Stopwatch ticks). False when it could not (the caller then spins).</summary>
        internal static bool WaitUntil(long timePoint)
        {
            long ns = NanosecondsUntil(timePoint);
            if (ns <= 0)
            {
                return true;
            }

            if (s_nsToMach == 0)
            {
                uint* info = stackalloc uint[2];
                if (mach_timebase_info(info) != 0 || info[0] == 0)
                {
                    return false;
                }

                s_nsToMach = (double)info[1] / info[0];
            }

            return mach_wait_until(mach_absolute_time() + (ulong)(ns * s_nsToMach)) == 0;
        }
    }

    // RewindBox (adapt_darwin_timed_waits): the guest timer thread's event on Apple platforms (see DarwinTimedWait).
    // Signal has the AutoResetEvent semantics of NanosleepEvent's: signals made while none is consumed count once. After
    // a wake the waiter takes any count left, then clears the mark: a signal made before the clear is seen by the
    // caller's read of the timer state that follows, one made after it posts again (no lost wakeup). A Signal after
    // Dispose does nothing (KTimeManager.Dispose signals while the timer thread may be disposing the event); the
    // semaphore is released by the last of Dispose and the signals in progress.
    internal sealed class DarwinSleepEvent : IPreciseSleepEvent
    {
        private readonly nint _semaphore;
        private int _signalled;
        private int _references = 1; // the owner's until Dispose, and one per Signal in progress
        private int _disposed;

        public DarwinSleepEvent()
        {
            _semaphore = DarwinTimedWait.dispatch_semaphore_create(0);
            if (_semaphore == 0)
            {
                throw new System.InvalidOperationException("dispatch_semaphore_create failed");
            }
        }

        public long AdjustTimePoint(long timePoint, long timeoutNs) => timePoint;

        public bool SleepUntil(long timePoint)
        {
            long ns = DarwinTimedWait.NanosecondsUntil(timePoint);
            if (ns <= 0)
            {
                return false;
            }

            DarwinTimedWait.dispatch_semaphore_wait(_semaphore, DarwinTimedWait.dispatch_time(DarwinTimedWait.TimeNow, ns));
            Consume();
            return true;
        }

        public void Sleep()
        {
            DarwinTimedWait.dispatch_semaphore_wait(_semaphore, DarwinTimedWait.TimeForever);
            Consume();
        }

        public void Signal()
        {
            int references;
            do
            {
                references = System.Threading.Volatile.Read(ref _references);
                if (references == 0)
                {
                    return;
                }
            }
            while (System.Threading.Interlocked.CompareExchange(ref _references, references + 1, references) != references);

            if (System.Threading.Interlocked.Exchange(ref _signalled, 1) == 0)
            {
                DarwinTimedWait.dispatch_semaphore_signal(_semaphore);
            }

            Release();
        }

        // After a wake (deadline or signal): any count left is taken, then the mark is cleared.
        private void Consume()
        {
            while (DarwinTimedWait.dispatch_semaphore_wait(_semaphore, DarwinTimedWait.TimeNow) == 0)
            {
            }

            System.Threading.Interlocked.Exchange(ref _signalled, 0);
        }

        public void Dispose()
        {
            if (System.Threading.Interlocked.Exchange(ref _disposed, 1) == 0)
            {
                Release();
            }
        }

        private void Release()
        {
            if (System.Threading.Interlocked.Decrement(ref _references) == 0)
            {
                DarwinTimedWait.dispatch_release(_semaphore);
            }
        }
    }
'''

CREATE_OLD = '''        public static IPreciseSleepEvent CreateEvent()
        {
            if (OperatingSystem.IsLinux() || OperatingSystem.IsMacOS() || OperatingSystem.IsIOS() || OperatingSystem.IsAndroid())
'''
CREATE_NEW = '''        public static IPreciseSleepEvent CreateEvent()
        {
            // RewindBox (adapt_darwin_timed_waits): one kernel timed wait per deadline on Apple platforms.
            if (DarwinTimedWait.Applies)
            {
                return new DarwinSleepEvent();
            }

            if (OperatingSystem.IsLinux() || OperatingSystem.IsMacOS() || OperatingSystem.IsIOS() || OperatingSystem.IsAndroid())
'''

SPIN_OLD = '''        public static void SpinWaitUntilTimePoint(long timePoint)
        {
            while (PerformanceCounter.ElapsedTicks < timePoint)
'''
SPIN_NEW = '''        public static void SpinWaitUntilTimePoint(long timePoint)
        {
            // RewindBox (adapt_darwin_timed_waits): sleep until that time on Apple platforms; the loop below only
            // finishes a wait that ended early.
            if (DarwinTimedWait.Applies)
            {
                DarwinTimedWait.WaitUntil(timePoint);
            }

            while (PerformanceCounter.ElapsedTicks < timePoint)
'''

TAIL_OLD = '''                Thread.SpinWait(5);
            }
        }
    }
}
'''
TAIL_NEW = '''                Thread.SpinWait(5);
            }
        }
    }

''' + CLASS + '''}
'''

PAIRS = ((CREATE_OLD, CREATE_NEW), (SPIN_OLD, SPIN_NEW), (TAIL_OLD, TAIL_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[HELPER], old, new)
    return list(paths.values())
