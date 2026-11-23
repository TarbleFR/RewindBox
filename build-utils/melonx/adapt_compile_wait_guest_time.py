"""The guest's clock stands still while the guest's GPU path waits for a pipeline compile beyond 33 ms (every title).

Evidence (private journals of IPA 824, Hogwarts Legacy, two sessions, and of IPA 822, one session; counts and times only):
- Both IPA 824 sessions end with SIGABRT 47 and 48 s in, raised on the guest's FHeartBeatThread: the thread writes guest
  address 3 (relativeOffset 0x40000003 past the 1 GiB page table), NativePageTable.VirtualMemoryEvent throws inside the
  signal handler, nothing above it catches, the runtime fails fast. Unreal's heartbeat thread does that on purpose once
  a watched thread has not ticked for 25 s of guest time. The symbolised host frames are that path and nothing else.
- What stopped 25 s earlier: the game's first gameplay frame (the first eye-adaptation read-back into a buffer, 21.2 and
  22.2 s in; the IPA 820, 821 and 822 sessions make their second read-back 1.3 to 22 s later, the IPA 824 sessions
  never). From then on no GPU-thread or render-thread phase completes (performance windows of 5 s: 0 FIFO waits, 0
  drains, 0 idles), the guest's RenderThread waits 14 s for one condition variable, all 50 guest threads wait, and the
  pipeline workers complete 9 to 14 compute pipelines per window, 350 to 1 100 ms each, their time summing to the
  window's length.
- Why so slow: Metal compiled cold. IPA 822, same title, same pipeline cache: 535 compute pipelines in 1.2 s and 3 059
  graphics pipelines in the first window, MoltenVK's lazily compiled cache libraries 2 816 in 908 ms. IPA 824: 8 to 113
  compute pipelines per window, about one graphics pipeline, fewer than 256 lazy libraries in a whole session, the first
  one 135 ms (0 ms in IPA 822); the build journal counts 2 compilations of its own in the second session (the others
  were served by the pipeline cache: the time is Metal's own compile of the cached MSL). No MoltenVK input differs
  between the two cores: the system's Metal cache was empty or evicted.
- Why that ends the game: a compute dispatch cannot skip, so the render thread waits for each pipeline it lacks
  (BackgroundCompilationScheduler.WaitForPipelineAtDraw, unbounded), one after the other, and the guest's GPU work and
  the guest with it stand still. At 0.5 to 1 s for each of hundreds of compute programs (535 warmed at startup in IPA
  822), the first frame lasts longer than the watchdog's 25 s. The user reports the same end with the earlier IPA.
- A console never waits for a pipeline compile: its shaders are compiled ahead. The time the guest measures across such
  a wait is the emulator's, not the game's.

Change (an independent review's six findings on a first version are answered here: no short hold touches the clock, the
scalar is never read from a transition, a failed replacement restores the clock, a stale session's wait is ignored,
pause no longer stops the stopwatch under its readers, a stall of many waits is held as one):
- Ryujinx.Common (new GuestTimeHold.cs): Begin() and End(token) around a compile wait. The clock is held only once the
  wait has lasted 33 ms (a one-shot timer), so a shorter wait is seen in full and never touches the clock; a wait that
  begins less than 250 ms after a held one ended is held from its start, so a stall of many waits shows the guest 33 ms
  plus the rendering between them, not 33 ms per wait. Nested waits count once, any thread; a token from before the
  session's clock was attached is ignored. A Gpu journal line for each of the first 16 waits of 1 s or more; the
  render-stage line counts the waits, the held ones and the time not counted. Begin, End and the journal text are
  published to the Vulkan backend through AppContext (BCL delegates: the backend shares no type with this file).
- Ryujinx.Cpu (TickSource.cs): the clock the guest reads (the CNTPCT counter of the JIT, svcGetSystemTick, the time
  services and the buffer queue's timestamps all read it) freezes for two reasons, a hold and a pause (Suspend/Resume
  of Horizon.TogglePauseEmulation, now in the snapshot: the stopwatch is never stopped under its readers). Frozen, it
  returns one value; thawed, it goes on from that value: it never goes back, from any thread. Readers add the host
  ticks to the snapshot still published after reading them, and wait out a transition; a writer publishes the
  transition, reads its host ticks, then the new snapshot, or the previous one again if that fails; a freeze starts
  10 microseconds ahead (a reader's counter read reordered after its second snapshot read). The scalar getter waits
  out a transition too. The tick source attaches itself as the session's clock when it is created.
- Ryujinx.Graphics.Vulkan (BackgroundCompilationScheduler.cs): WaitForPipelineAtDraw (the draw and dispatch waits for a
  background compile, render thread) is held around its unchanged body, renamed WaitForPipelineAtDrawHeld; the
  render-stage line's draw-wait text gains the hold counts.
Not changed: which pipelines are compiled, where, in which order and with which priority; what a draw or a dispatch
binds and when it waits; the skip of draws that may skip; compiles on the workers; startup; pause semantics (the
paused time stays out of the clock); kernel time (KTimeManager, host time: a thread sleeping during a held wait wakes as
before and reads the held clock); host time; a pipeline the render thread creates itself without a background compile
(not held).

Scope: every title, only while the render thread waits for a background pipeline compile for 33 ms or more. With warm
caches such waits are rare (IPA 760, Super Smash Bros. Ultimate: 98 ms for a program new to the device). Expected on the
device (not measured): with an empty Metal cache, a long frozen picture at the first gameplay frame instead of the
abort; a "Pipeline compile wait of ... ms" line for each long wait; the render-stage line's "compile waits held from
the guest's clock". Refuted if a session with such lines still ends on the heartbeat thread's write to address 3. No
frame rate gain is claimed; a compile is not faster.

Fail closed: every edited file must be the final preparation's (BASELINE) and GuestTimeHold.cs absent or the adapter's; each
replacement occurs once. Rollback: drop this adapter from prepare_embedded.py and ORDER.
"""
import hashlib
from adapt_session import once

HOLD = 'src/Ryujinx.Common/GuestTimeHold.cs'
TICKS = 'src/Ryujinx.Cpu/TickSource.cs'
SCHEDULER = 'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs'
BASELINE = {
    TICKS: '463a535323c1701a1de8658821e292146ca9e70c83f693b1331773a9d3e1f222',
    SCHEDULER: '77c30aedcb3f058e0af27ef19ed1ff08e602ff7389c186379dcd9257bed54efc',
}
ADDED = [HOLD]

HOLD_SOURCE = '''using Ryujinx.Common.Logging;
using System;
using System.Diagnostics;
using System.Threading;

namespace Ryujinx.Common
{
    /// <summary>
    /// RewindBox (adapt_compile_wait_guest_time): the guest's clock stands still while the guest's GPU path waits for a
    /// pipeline compile beyond <see cref="VisibleMilliseconds"/>. A console never waits for a pipeline compile; here the
    /// render thread can wait for Metal's compiler, and a game whose watchdog measures a frame in guest time ends itself
    /// after a long enough wait. A wait shorter than the visible span never touches the clock; a longer one is held from
    /// that point (a one-shot timer); a wait that begins within <see cref="BurstGapMilliseconds"/> of a held one's end is
    /// held from its start. Nested waits count once; any thread; a token from before the clock was attached is ignored.
    /// The Vulkan backend reaches <see cref="Begin"/>, <see cref="End"/> and <see cref="TakeText"/> through AppContext.
    /// </summary>
    public static class GuestTimeHold
    {
        /// <summary>The session's clock: frozen by <see cref="Hold"/>, going on from the frozen value after <see cref="Release"/>.</summary>
        public interface IClock
        {
            void Hold();

            void Release();
        }

        public const int VisibleMilliseconds = 33;
        public const int BurstGapMilliseconds = 250;
        public const int LongWaitMilliseconds = 1000;
        public const int LongWaitLines = 16;
        public const string BeginKey = "RewindBox.GuestTimeHold.Begin";
        public const string EndKey = "RewindBox.GuestTimeHold.End";
        public const string TextKey = "RewindBox.GuestTimeHold.Text";

        private static readonly object _lock = new();
        private static readonly Timer _timer;
        private static IClock _clock;
        private static long _generation;
        private static int _depth;
        private static bool _holding;
        private static long _start, _heldStart, _lastHeldEnd;
        private static long _waits, _heldWaits, _hiddenTicks, _longestTicks;
        private static int _longWaits;

        static GuestTimeHold()
        {
            _lastHeldEnd = long.MinValue / 2;
            _timer = new Timer(OnTimer, null, Timeout.Infinite, Timeout.Infinite);
            AppContext.SetData(BeginKey, (Func<long>)Begin);
            AppContext.SetData(EndKey, (Action<long>)End);
            AppContext.SetData(TextKey, (Func<string>)TakeText);
        }

        private static long Ticks(long milliseconds) => milliseconds * Stopwatch.Frequency / 1000;

        /// <summary>The session's clock from now on; a hold of the previous one ends, earlier tokens are ignored.</summary>
        public static void Attach(IClock clock)
        {
            lock (_lock)
            {
                ReleaseLocked(Stopwatch.GetTimestamp(), false);
                _clock = clock;
                _depth = 0;
                _generation++;
                _timer.Change(Timeout.Infinite, Timeout.Infinite);
            }
        }

        public static void Detach(IClock clock)
        {
            lock (_lock)
            {
                if (clock == null || !ReferenceEquals(_clock, clock))
                {
                    return;
                }

                ReleaseLocked(Stopwatch.GetTimestamp(), false);
                _clock = null;
                _depth = 0;
                _generation++;
                _timer.Change(Timeout.Infinite, Timeout.Infinite);
            }
        }

        public static long Begin()
        {
            lock (_lock)
            {
                if (_depth++ != 0)
                {
                    return _generation;
                }

                _start = Stopwatch.GetTimestamp();

                if (_clock != null)
                {
                    if (_start - _lastHeldEnd < Ticks(BurstGapMilliseconds))
                    {
                        HoldLocked(_start);
                    }
                    else
                    {
                        _timer.Change(VisibleMilliseconds, Timeout.Infinite);
                    }
                }

                return _generation;
            }
        }

        public static void End(long token)
        {
            long waited, counted;

            lock (_lock)
            {
                if (token != _generation || _depth == 0 || --_depth != 0)
                {
                    return;
                }

                _timer.Change(Timeout.Infinite, Timeout.Infinite);
                long now = Stopwatch.GetTimestamp();
                waited = now - _start;
                counted = waited - (_holding ? now - _heldStart : 0);
                ReleaseLocked(now, true);
                _waits++;

                if (waited > _longestTicks)
                {
                    _longestTicks = waited;
                }

                if (waited < Ticks(LongWaitMilliseconds) || _longWaits >= LongWaitLines)
                {
                    return;
                }

                _longWaits++;
            }

            Logger.Warning?.Print(LogClass.Gpu,
                "Pipeline compile wait of " + (waited * 1000 / Stopwatch.Frequency) + " ms on the guest's GPU path: the guest's clock counted " +
                (counted * 1000 / Stopwatch.Frequency) + " ms of it (adapt_compile_wait_guest_time)");
        }

        public static string TakeText()
        {
            lock (_lock)
            {
                string text = "; compile waits held from the guest's clock " + _heldWaits + " of " + _waits + " (" +
                    (_hiddenTicks * 1000 / Stopwatch.Frequency) + " ms not counted, longest wait " +
                    (_longestTicks * 1000 / Stopwatch.Frequency) + " ms)";

                _waits = _heldWaits = _hiddenTicks = _longestTicks = 0;

                return text;
            }
        }

        private static void OnTimer(object state)
        {
            try
            {
                lock (_lock)
                {
                    if (_depth == 0 || _holding || _clock == null)
                    {
                        return;
                    }

                    long now = Stopwatch.GetTimestamp();
                    long remaining = _start + Ticks(VisibleMilliseconds) - now;

                    if (remaining > 0)
                    {
                        _timer.Change(Math.Max(1, remaining * 1000 / Stopwatch.Frequency), Timeout.Infinite);

                        return;
                    }

                    HoldLocked(now);
                }
            }
            catch (Exception)
            {
                // A timer callback must not end the process; the clock keeps running.
            }
        }

        private static void HoldLocked(long now)
        {
            try
            {
                _clock.Hold();
                _holding = true;
                _heldStart = now;
            }
            catch (Exception)
            {
                _holding = false; // The clock restored its snapshot and runs.
            }
        }

        private static void ReleaseLocked(long now, bool count)
        {
            if (!_holding)
            {
                return;
            }

            _holding = false;

            if (count)
            {
                _lastHeldEnd = now;
                _heldWaits++;
                _hiddenTicks += now - _heldStart;
            }

            try
            {
                _clock?.Release();
            }
            catch (Exception)
            {
                // The clock restored its snapshot (frozen); the next attach or hold replaces it.
            }
        }
    }
}
'''

TICKS_CLASS_START = '    public class TickSource : ITickSource\n'
TICKS_CLASS_NEW = '''    public class TickSource : ITickSource, Ryujinx.Common.GuestTimeHold.IClock
    {
        private sealed class TickSnapshot
        {
            public long HostTicks { get; }
            public long ElapsedTicks { get; }
            public long TickScalar { get; }
            // RewindBox (adapt_compile_wait_guest_time): the clock stands at ElapsedTicks.
            public bool Frozen { get; }

            public TickSnapshot(long hostTicks, long elapsedTicks, long tickScalar, bool frozen)
            {
                HostTicks = hostTicks;
                ElapsedTicks = elapsedTicks;
                TickScalar = tickScalar;
                Frozen = frozen;
            }

            public long GetElapsedTicks(long hostTicks)
            {
                // RewindBox (adapt_compile_wait_guest_time): frozen, the value stands; host ticks read before the
                // snapshot's own add nothing (never below it).
                return Frozen ? ElapsedTicks : ElapsedTicks + Math.Max(0, hostTicks - HostTicks) * TickScalar / ITickSource.RealityTickScalar;
            }
        }

        // RewindBox (adapt_compile_wait_guest_time): published while a writer replaces the snapshot (readers wait for the
        // next one); a freeze starts this far ahead (a reader's counter read reordered after its second snapshot read).
        private static readonly TickSnapshot _transition = new(0, 0, ITickSource.RealityTickScalar, true);
        private static readonly long _freezeLeadTicks = Math.Max(1, Stopwatch.Frequency / 100000);
        private const int FrozenByPause = 1;
        private const int FrozenByHold = 2;

        private readonly Stopwatch _tickCounter;
        private readonly double _hostTickFreq;
        private readonly object _tickScalarLock = new();
        private TickSnapshot _snapshot;
        private int _frozen; // under _tickScalarLock

        /// <inheritdoc/>
        public ulong Frequency { get; }

        /// <inheritdoc/>
        public ulong Counter => (ulong)(ElapsedSeconds * Frequency);


        public long TickScalar
        {
            get => Current().TickScalar;
            set
            {
                lock (_tickScalarLock)
                {
                    Replace(value, _frozen != 0, 0);
                }
            }
        }

        private long ElapsedTicks
        {
            get
            {
                // RewindBox (adapt_compile_wait_guest_time): the host ticks are added to the snapshot still published
                // after they were read; a transition is waited out.
                int spins = 0;

                while (true)
                {
                    TickSnapshot snapshot = Volatile.Read(ref _snapshot);

                    if (!ReferenceEquals(snapshot, _transition))
                    {
                        long hostTicks = _tickCounter.ElapsedTicks;

                        if (ReferenceEquals(Volatile.Read(ref _snapshot), snapshot))
                        {
                            return snapshot.GetElapsedTicks(hostTicks);
                        }
                    }

                    Wait(ref spins);
                }
            }
        }

        /// <inheritdoc/>

        public TimeSpan ElapsedTime => Stopwatch.GetElapsedTime(0, ElapsedTicks);

        /// <inheritdoc/>
        public double ElapsedSeconds => ElapsedTicks * _hostTickFreq;

        public TickSource(ulong frequency)
        {
            Frequency = frequency;
            _hostTickFreq = 1.0 / Stopwatch.Frequency;
            _snapshot = new TickSnapshot(0, 0, ITickSource.RealityTickScalar, false);

            _tickCounter = new Stopwatch();
            _tickCounter.Start();

            // RewindBox (adapt_compile_wait_guest_time): the session's clock for the holds of its compile waits.
            Ryujinx.Common.GuestTimeHold.Attach(this);
        }

        /// <inheritdoc/>
        public void Suspend()
        {
            // RewindBox (adapt_compile_wait_guest_time): frozen in the snapshot; the stopwatch keeps running under its readers.
            lock (_tickScalarLock)
            {
                Freeze(FrozenByPause);
            }
        }

        /// <inheritdoc/>
        public void Resume()
        {
            lock (_tickScalarLock)
            {
                Thaw(FrozenByPause);
            }
        }

        /// <inheritdoc/>
        public void Hold()
        {
            lock (_tickScalarLock)
            {
                Freeze(FrozenByHold);
            }
        }

        /// <inheritdoc/>
        public void Release()
        {
            lock (_tickScalarLock)
            {
                Thaw(FrozenByHold);
            }
        }

        private TickSnapshot Current()
        {
            int spins = 0;

            while (true)
            {
                TickSnapshot snapshot = Volatile.Read(ref _snapshot);

                if (!ReferenceEquals(snapshot, _transition))
                {
                    return snapshot;
                }

                Wait(ref spins);
            }
        }

        private static void Wait(ref int spins)
        {
            if (++spins < 64)
            {
                Thread.SpinWait(8);
            }
            else
            {
                Thread.Yield();
            }
        }

        // Under _tickScalarLock; the reason is recorded once the snapshot is replaced.
        private void Freeze(int reason)
        {
            if (_frozen == 0)
            {
                Replace(Volatile.Read(ref _snapshot).TickScalar, true, _freezeLeadTicks);
            }

            _frozen |= reason;
        }

        private void Thaw(int reason)
        {
            if ((_frozen & reason) == 0)
            {
                return;
            }

            if (_frozen == reason)
            {
                Replace(Volatile.Read(ref _snapshot).TickScalar, false, 0);
            }

            _frozen &= ~reason;
        }

        // Under _tickScalarLock. The transition is published, then the host ticks are read: every reader still adding to
        // the previous snapshot read its host ticks before these. On a failure the previous snapshot is published again.
        private void Replace(long tickScalar, bool frozen, long lead)
        {
            TickSnapshot snapshot = Volatile.Read(ref _snapshot);
            TickSnapshot next = snapshot;

            Volatile.Write(ref _snapshot, _transition);

            try
            {
                Interlocked.MemoryBarrier();
                long hostTicks = _tickCounter.ElapsedTicks;
                long ahead = snapshot.Frozen ? 0 : lead * snapshot.TickScalar / ITickSource.RealityTickScalar;

                next = new TickSnapshot(hostTicks, snapshot.GetElapsedTicks(hostTicks) + ahead, tickScalar, frozen);
            }
            finally
            {
                Volatile.Write(ref _snapshot, next);
            }
        }
    }
}
'''

WAIT_OLD = '''        public void WaitForPipelineAtDraw(Task task)
        {
            if (!Ryujinx.Graphics.GAL.Multithreading.Resources.RenderThreadPrograms.Bound)'''
WAIT_NEW = '''        public void WaitForPipelineAtDraw(Task task)
        {
            // RewindBox (adapt_compile_wait_guest_time): past 33 ms, the guest's clock stands still until the wait ends.
            long hold = CompileWaitGuestTime.Begin();

            try
            {
                WaitForPipelineAtDrawHeld(task);
            }
            finally
            {
                CompileWaitGuestTime.End(hold);
            }
        }

        private void WaitForPipelineAtDrawHeld(Task task)
        {
            if (!Ryujinx.Graphics.GAL.Multithreading.Resources.RenderThreadPrograms.Bound)'''
TEXT_OLD = '''                ", compiles started ahead " + Interlocked.Exchange(ref _startedAhead, 0) + ")";
        }
    }
'''
TEXT_NEW = '''                ", compiles started ahead " + Interlocked.Exchange(ref _startedAhead, 0) + ")" +
                CompileWaitGuestTime.TakeText(); // RewindBox (adapt_compile_wait_guest_time)
        }
    }

    /// <summary>
    /// RewindBox (adapt_compile_wait_guest_time): Ryujinx.Common.GuestTimeHold, published through AppContext when the
    /// session's tick source is created (BCL delegates: no type is shared with it). Unset, nothing is held or written.
    /// </summary>
    static class CompileWaitGuestTime
    {
        public static long Begin()
        {
            return AppContext.GetData("RewindBox.GuestTimeHold.Begin") is Func<long> begin ? begin() : 0;
        }

        public static void End(long token)
        {
            if (AppContext.GetData("RewindBox.GuestTimeHold.End") is Action<long> end)
            {
                end(token);
            }
        }

        public static string TakeText()
        {
            return AppContext.GetData("RewindBox.GuestTimeHold.Text") is Func<string> text ? text() : "";
        }
    }
'''

FILE_PAIRS = {
    SCHEDULER: [(WAIT_OLD, WAIT_NEW), (TEXT_OLD, TEXT_NEW)],
}


def tick_source_old(text):
    """The original TickSource class: from its declaration to the end of the file (namespace closed)."""
    assert text.count(TICKS_CLASS_START) == 1 and text.endswith('    }\n}\n'), 'TickSource.cs'
    return text[text.index(TICKS_CLASS_START):]


def apply(source):
    for name, expected in BASELINE.items():
        path = source / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, (name, actual)
    for name in ADDED:
        # A reversed control keeps the file (only BASELINE is restored): the adapter's own text is accepted, nothing else.
        assert not (source / name).exists() or (source / name).read_text(encoding='utf-8') == HOLD_SOURCE, name
    ticks = source / TICKS
    # A composition (melonx_adapter_control.apply_present) may lack TickSource.cs: its once() skips absent files, and
    # GuestTimeHold.cs, used by the clock only, goes with it.
    present = ticks.exists()
    once(ticks, tick_source_old(ticks.read_text(encoding='utf-8-sig')) if present else TICKS_CLASS_START, TICKS_CLASS_NEW)
    scheduler = source / SCHEDULER
    for old, new in FILE_PAIRS[SCHEDULER]:
        once(scheduler, old, new)
    changed = [path for path in (ticks, scheduler) if path.exists()]
    if present:
        hold = source / HOLD
        hold.parent.mkdir(parents=True, exist_ok=True)
        hold.write_text(HOLD_SOURCE, encoding='utf-8')
        changed.append(hold)
    return changed
