"""Waits that spin before blocking spin as long as it pays (Core 747 candidate; every title).

IPA 733 / Core 745 (source ced57c6d, iPhone binary 2943e064), Hogwarts Legacy 1x (pid 61839, session 4AC66D23, 78 s
with frames presented): 2.06 W of CPU work (the kernel's energy accounting), 274 % of a core, 69 600 context switches,
150 000 system calls and 4 200 wakeups by interrupt per second. In the three [MeloNX:hot] captures (300 samples each,
symbolized with the Core 745 symbol map) 46-48 % of the running samples of the busiest threads are spinning before a
wait: <MainThread> 48 %, <RenderThread_1> 61 %, <RHIThread> 75 %, <AK__EventManager> 85 %, the render thread 27 %;
over every capture of the journal, 44 % of all samples sit in one kernel call, the yield the spin makes
(PalSwitchToThread < Thread.Yield < SpinWait.SpinOnceCore < ManualResetEventSlim.Wait), against 0.5 % in the pause
loop. The waits: the guest scheduler's KThread.SchedulerWaitEvent (KScheduler.Schedule and KCriticalSection.Leave,
under SendSyncRequest, WaitProcessWideKeyAtomic and the other waits of every guest thread) and the threaded
renderer's _galWorkAvailable (the render loop) and _invokeRun (the GPU thread's synchronous invokes). Each is a
ManualResetEventSlim at the runtime's default spin: 35 SpinWait iterations, ten of pause instructions, then pauses
alternating with Thread.Yield and Thread.Sleep(0). Smash (same IPA, session 0D5275AF): 37-40 %.

Measured on the host (test/melonx_wait_spin_bound, two threads handing over as KScheduler does): the yields pay only
when the partner answers within a few microseconds (1 us: 560 000 handoffs/s with them, 72 000 without); past that
both block in the kernel and the yields cost 7-10 us of CPU per handoff at equal throughput and latency. A fixed bound
would lose the short handoffs (synchronous IPC is among the spinning waits).

Change: AdaptiveSpinEvent (appended to Ryujinx.Common's AsyncWorkQueue.cs) replaces the three events. It keeps the
default spin for an event whose waits end inside it and keeps only the ten pause iterations for an event whose waits
mostly outlast it; the decision is made by a waiter that blocked, from the time the event was set (stamped by the
setter only while a waiter blocks), less the setter's own wake delay when it was woken during that wait, against the
length of a full spin measured once. A wait still returns only once its event is set; Set, Reset and Dispose are the
event's. Nothing else changes: no thread, priority, timeout or frame pacing.

Expected on the device (same save, route and conditions as the IPA 733 capture): system calls per second (sw=) and
the share of [MeloNX:hot] samples in the yield fall by half or more, CPU power (en=) and process CPU (cpu=) fall,
presented frames per second and frame times unchanged. Refuted and removed if presented fps fall or the frame time
p95 rises by more than 2 ms, or if sw= and en= do not fall.
Rollback: drop this adapter from prepare_embedded.py and the plan. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

COMMON = 'src/Ryujinx.Common/AsyncWorkQueue.cs'
THREAD = 'src/Ryujinx.HLE/HOS/Kernel/Threading/KThread.cs'
RENDERER = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
BASELINE = {
    COMMON: '6f5c2a136bb4239c55c42e60c1a35590035bee1fd00ad464162c2d3046874ca6',
    THREAD: '78579fcf0e2af1e9e00d4e517a8c995a73e6eacda9b867e14eb39bcc88f71ac9',
    RENDERER: '8314fca1df4327f995460e0fab596bac58d75b3b6d5abc18facbdc7804cf5927',
}

CLASS = '''    // RewindBox (adapt_wait_spin_bound): a ManualResetEventSlim whose spin before blocking follows what the spin buys.
    // The runtime's default spin (35 SpinWait iterations: ten of pause instructions, then pauses alternating with
    // Thread.Yield and Thread.Sleep(0)) is kept for an event whose waits are short enough to end inside it, and
    // reduced to the ten pause iterations for an event whose waits mostly outlast it, where the yields only kept a
    // core busy before the same block in the kernel (IPA 733, Hogwarts Legacy: 44 % of the busiest threads' samples
    // inside that yield; the guest scheduler's and the render thread's events).
    // The decision, made only by a waiter that blocked: the thread that sets the event stamps the time, and how late it
    // was itself woken if that happened during this wait (its own block in the kernel, which a spinning partner does
    // not pay); the waiter compares the time its wait needed, less that delay, with the length of a full spin.
    // Nothing is read from the clock by a wait that ends inside its spin, nor by a Set while no waiter blocks. Waits still
    // return only once the event is set, as before.
    public sealed class AdaptiveSpinEvent : System.IDisposable
    {
        // SpinWait's iterations before its first yield, and ManualResetEventSlim's default spin on a multi-core host.
        public const int PauseIterations = 10;
        public const int FullIterations = 35;
        // A saturating score per event: a short wait adds 2, a long one takes 1; the full spin while it is not negative.
        public const int ScoreLimit = 4;

        private readonly System.Threading.ManualResetEventSlim _event;
        private long _setTicks, _setterWokeTicks, _setterWakeDelay;
        private int _score;
        private int _blocking; // a waiter is about to block or blocked: only then does Set read the clock

        // The calling thread's last return from a block on such an event: when, and how long after the set (0 after a
        // wait that ended inside its spin).
        [System.ThreadStatic] private static long t_wokeTicks;
        [System.ThreadStatic] private static long t_wakeDelay;

        // The length of a full spin and of the pause iterations alone (Stopwatch ticks), measured once per process on
        // the first thread that blocks: they depend on the machine, not on the event.
        private static long s_fullSpinTicks, s_pauseSpinTicks;

        public AdaptiveSpinEvent(bool initialState = false)
        {
            // The spin is this class's; the underlying event blocks at once.
            _event = new System.Threading.ManualResetEventSlim(initialState, 0);
        }

        public bool IsSet => _event.IsSet;

        public int SpinBudget => _score >= 0 ? FullIterations : PauseIterations;

        public void Set()
        {
            if (System.Threading.Volatile.Read(ref _blocking) != 0 && !_event.IsSet)
            {
                _setterWokeTicks = t_wokeTicks;
                _setterWakeDelay = t_wakeDelay;
                System.Threading.Volatile.Write(ref _setTicks, System.Diagnostics.Stopwatch.GetTimestamp());
            }

            _event.Set();
        }

        public void Reset() => _event.Reset();

        public void Wait()
        {
            if (_event.IsSet)
            {
                return;
            }

            int budget = SpinBudget;
            System.Threading.SpinWait spinner = default;

            while (spinner.Count < budget)
            {
                spinner.SpinOnce(sleep1Threshold: -1);

                if (_event.IsSet)
                {
                    // Ended inside the spin: short.
                    // (The thread's wake record is left as it is: older than any later wait it would be passed to, it is
                    // not subtracted there.)
                    if (_score < ScoreLimit)
                    {
                        _score = System.Math.Min(ScoreLimit, _score + 2);
                    }

                    return;
                }
            }

            if (System.Threading.Volatile.Read(ref s_fullSpinTicks) == 0)
            {
                Calibrate();
            }

            long blocked = System.Diagnostics.Stopwatch.GetTimestamp();
            System.Threading.Interlocked.Exchange(ref _blocking, 1);
            _event.Wait();
            System.Threading.Volatile.Write(ref _blocking, 0);
            long woke = System.Diagnostics.Stopwatch.GetTimestamp();

            // When the event was set, from the start of this wait (the spin's length before the block), less the setter's
            // own wake delay when it was woken during this wait: inside a full spin's length or not.
            long spin = budget == FullIterations ? s_fullSpinTicks : s_pauseSpinTicks;
            long start = blocked - spin;
            long setTicks = System.Threading.Volatile.Read(ref _setTicks);
            if (setTicks < blocked - spin)
            {
                // Set before this wait blocked (no stamp for it): it ended at once, short.
                setTicks = blocked;
            }

            long needed = setTicks - start;
            if (_setterWakeDelay > 0 && _setterWokeTicks >= start)
            {
                needed -= _setterWakeDelay;
            }

            _score = needed <= s_fullSpinTicks ? System.Math.Min(ScoreLimit, _score + 2) : System.Math.Max(-ScoreLimit, _score - 1);

            t_wokeTicks = woke;
            t_wakeDelay = System.Math.Max(0, woke - setTicks);
        }

        // Times the two spins once, on the first thread that blocks (it was about to wait anyway).
        private static void Calibrate()
        {
            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            System.Threading.SpinWait spinner = default;
            while (spinner.Count < PauseIterations)
            {
                spinner.SpinOnce(sleep1Threshold: -1);
            }

            long pause = System.Diagnostics.Stopwatch.GetTimestamp() - start;
            while (spinner.Count < FullIterations)
            {
                spinner.SpinOnce(sleep1Threshold: -1);
            }

            long full = System.Diagnostics.Stopwatch.GetTimestamp() - start;
            System.Threading.Volatile.Write(ref s_pauseSpinTicks, System.Math.Max(1, pause));
            System.Threading.Volatile.Write(ref s_fullSpinTicks, System.Math.Max(2, full));
        }

        public void Dispose() => _event.Dispose();
    }
'''

TAIL_OLD = '''            _cts.Dispose();
        }
    }
}
'''
TAIL_NEW = '''            _cts.Dispose();
        }
    }

''' + CLASS + '''}
'''

FIELD_OLD = '''        private ManualResetEventSlim _schedulerWaitEvent;

        public ManualResetEventSlim SchedulerWaitEvent => _schedulerWaitEvent;
'''
FIELD_NEW = '''        // RewindBox (adapt_wait_spin_bound): spins before blocking only as long as it pays.
        private Ryujinx.Common.AdaptiveSpinEvent _schedulerWaitEvent;

        public Ryujinx.Common.AdaptiveSpinEvent SchedulerWaitEvent => _schedulerWaitEvent;
'''

START_OLD = '''                ManualResetEventSlim schedulerWaitEvent = new(false);
'''
START_NEW = '''                Ryujinx.Common.AdaptiveSpinEvent schedulerWaitEvent = new(false); // RewindBox (adapt_wait_spin_bound)
'''

RENDER_FIELDS_OLD = '''        private readonly ManualResetEventSlim _galWorkAvailable;
'''
RENDER_FIELDS_NEW = '''        private readonly Ryujinx.Common.AdaptiveSpinEvent _galWorkAvailable; // RewindBox (adapt_wait_spin_bound)
'''
INVOKE_FIELD_OLD = '''        private readonly ManualResetEventSlim _invokeRun;
'''
INVOKE_FIELD_NEW = '''        private readonly Ryujinx.Common.AdaptiveSpinEvent _invokeRun; // RewindBox (adapt_wait_spin_bound)
'''
CREATE_OLD = '''            _galWorkAvailable = new ManualResetEventSlim(false);
            _invokeRun = new ManualResetEventSlim();
'''
CREATE_NEW = '''            _galWorkAvailable = new Ryujinx.Common.AdaptiveSpinEvent(false);
            _invokeRun = new Ryujinx.Common.AdaptiveSpinEvent();
'''

FILE_PAIRS = {
    COMMON: ((TAIL_OLD, TAIL_NEW),),
    THREAD: ((FIELD_OLD, FIELD_NEW), (START_OLD, START_NEW)),
    RENDERER: ((RENDER_FIELDS_OLD, RENDER_FIELDS_NEW), (INVOKE_FIELD_OLD, INVOKE_FIELD_NEW), (CREATE_OLD, CREATE_NEW)),
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
