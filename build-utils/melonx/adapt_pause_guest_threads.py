"""Record what each guest thread is doing when the host pauses the game (diagnostics only).

IPA 640 (session 53DAD35F) and IPA 643 (session CBDD62E9), Hogwarts Legacy v1.0.5, 4 November 2026 (private logs and
recordings, not in the repository; the maintainer confirms the 3D scene starts only after a pause and the return to
the game): after launch the game presents 30 frames a second of a nearly empty frame (about 22 draws, no texture
upload, no video decode) while Wwise keeps playing sound, so the screen is black with sound. Its <MainThread> stays at
16-17 % of a core and Wwise's <AK::BankManager> does not run. A host pause (the MeloNX menu, or Control Center when a
screen recording is started: willResignActive pauses the session in MeloNXMetalSessionViewController) and the return
end it: within 0-4 s <AK::BankManager> runs and the scene renders (hundreds of draws a frame). In 643 a pause of about
1 s did not end it and one of 4 s did; in 640 one of about 2 s did.

The pause (Horizon.TogglePauseEmulation, delivered) suspends every thread of the application process
(KProcess.SetActivity), the guest tick source and the audio renderer. Suspending and resuming threads changes their
scheduling state and requests a new selection of the thread each guest core runs (KThread.AdjustScheduling,
ThreadReselectionRequested, KCriticalSection.Leave), so a thread able to run that no core had selected, or one waiting
on something the pause ends, would be released this way. Which thread waits, on what, and since when decides the
correction (scheduler, a kernel wait, a timer, audio or a service), so nothing is changed before it is known.

Change, diagnostics only: before the first 3 host pauses of a session suspend the application, each of its threads
(at most 64) is logged once: guest name, id, dynamic and base priority, current, preferred and active core, affinity
mask, scheduling state and force-pause flags, the kind of wait (synchronization objects with their types, mutex or
condition variable, address arbiter, other), whether a guest core is running it, and for one that is not, the
milliseconds since it last stopped running. The fields are read under the kernel's critical-section monitor without
entering the critical section, so taking the record selects no thread, reschedules nothing and changes no state. One
durable Core journal line per pause ("guestThreads") counts the threads by state and names the threads able to run that
no core has run for more than 500 ms, and the longest waits. Not measured on an iPhone.
Fail closed on drift: each file must be the Core 642 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.HLE/HOS/Horizon.cs': 'ffccd410ef4826504ad5de4437ecefd49f2249c90e39b2fbe835120e43511b26',
    'src/Ryujinx.HLE/HOS/Kernel/Process/KProcess.cs': 'eb053785918e3f2967e914ea4a946dbb556ca1796425cb8772be7a62b7661709',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    process = paths['src/Ryujinx.HLE/HOS/Kernel/Process/KProcess.cs']
    once(process, '''        public Result SetActivity(bool pause)
        {''', '''        // RewindBox (adapt_pause_guest_threads): a copy of this process's thread list for the host-pause record.
        internal KThread[] SnapshotThreads()
        {
            lock (_threadingLock)
            {
                KThread[] threads = new KThread[_threads.Count];
                _threads.CopyTo(threads, 0);

                return threads;
            }
        }

        public Result SetActivity(bool pause)
        {''')

    horizon = paths['src/Ryujinx.HLE/HOS/Horizon.cs']
    once(horizon, '''                    if (process.IsApplication)
                    {
                        // Only game process should be paused.
                        process.SetActivity(pause);
                    }''', '''                    if (process.IsApplication)
                    {
                        if (pause && !IsPaused)
                        {
                            // RewindBox (adapt_pause_guest_threads): diagnostics only, before the threads are suspended.
                            NoteGuestThreadsAtPause(process);
                        }

                        // Only game process should be paused.
                        process.SetActivity(pause);
                    }''')
    once(horizon, '''        internal IDebuggableProcess DebugGetApplicationProcessDebugInterface()''', '''        // RewindBox (adapt_pause_guest_threads): the first host pauses of a session record what every application thread
        // is doing just before it is suspended. Fields are read under the critical-section monitor without entering the
        // critical section: no thread selection, no rescheduling, no state change.
        private const int PauseRecordLimit = 3;
        private const int PauseRecordThreadLimit = 64;
        private const double StarvedMs = 500;
        private int _pauseRecords;

        private void NoteGuestThreadsAtPause(KProcess process)
        {
            if (_pauseRecords >= PauseRecordLimit)
            {
                return;
            }

            int record = ++_pauseRecords;
            KThread[] threads = process.SnapshotThreads();
            int count = Math.Min(threads.Length, PauseRecordThreadLimit);
            string[] lines = new string[count];
            List<string> starved = [];
            List<(double Ms, string Text)> waits = [];
            int running = 0, onCore = 0, waiting = 0, other = 0;
            long now = Ryujinx.Common.PerformanceCounter.ElapsedTicks;

            lock (KernelContext.CriticalSection.Lock)
            {
                HashSet<KThread> current = [];

                foreach (KScheduler scheduler in KernelContext.Schedulers)
                {
                    if (scheduler?.CurrentThread != null)
                    {
                        current.Add(scheduler.CurrentThread);
                    }
                }

                for (int i = 0; i < count; i++)
                {
                    KThread thread = threads[i];
                    ThreadSchedState state = thread.SchedFlags & ThreadSchedState.LowMask;
                    ThreadSchedState pauseFlags = thread.SchedFlags & ThreadSchedState.ForcePauseMask;
                    string name;

                    try
                    {
                        name = thread.GetThreadName();
                    }
                    catch (Exception)
                    {
                        name = "";
                    }

                    if (string.IsNullOrEmpty(name))
                    {
                        name = thread.HostThread?.Name ?? "?";
                    }

                    string wait = "-";

                    if (state == ThreadSchedState.Paused)
                    {
                        if (thread.WaitingSync)
                        {
                            List<string> kinds = [];

                            foreach (Ryujinx.HLE.HOS.Kernel.Common.KSynchronizationObject syncObject in thread.WaitSyncObjects)
                            {
                                if (syncObject != null && kinds.Count < 4)
                                {
                                    kinds.Add(syncObject.GetType().Name);
                                }
                            }

                            wait = "sync wait on " + (kinds.Count != 0 ? string.Join("+", kinds) : "objects");
                        }
                        else if (thread.MutexAddress != 0)
                        {
                            wait = $"mutex/condition variable 0x{thread.MutexAddress:X}";
                        }
                        else if (thread.WaitingInArbitration)
                        {
                            wait = "address arbiter";
                        }
                        else
                        {
                            wait = "other wait (sleep, IPC reply or event)";
                        }
                    }

                    bool isCurrent = current.Contains(thread);
                    double idleMs = thread.LastScheduledTime == 0 ? -1 :
                        (now - thread.LastScheduledTime) * 1000.0 / Ryujinx.Common.PerformanceCounter.TicksPerSecond;
                    string ran = isCurrent ? "running on a guest core" :
                        idleMs < 0 ? "never stopped running" : $"last ran {idleMs:F0} ms ago";

                    if (state == ThreadSchedState.Running)
                    {
                        running++;
                        onCore += isCurrent ? 1 : 0;

                        if (!isCurrent && idleMs >= StarvedMs && pauseFlags == 0)
                        {
                            starved.Add($"{name} ({idleMs:F0} ms, prio {thread.DynamicPriority}, core {thread.ActiveCore})");
                        }
                    }
                    else if (state == ThreadSchedState.Paused)
                    {
                        waiting++;
                        waits.Add((idleMs, $"{name} {idleMs:F0} ms {wait}"));
                    }
                    else
                    {
                        other++;
                    }

                    lines[i] = $"Host pause #{record} guest thread {i + 1}/{threads.Length}: {name} id {thread.ThreadUid} " +
                        $"prio {thread.DynamicPriority}/{thread.BasePriority} core {thread.ActiveCore} (current {thread.CurrentCore}, " +
                        $"preferred {thread.PreferredCore}, mask 0x{thread.AffinityMask:X}) {state}" +
                        $"{(pauseFlags != 0 ? " force-pause " + pauseFlags : "")}; {wait}; {ran}";
                }
            }

            foreach (string line in lines)
            {
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Kernel, line);
            }

            waits.Sort((a, b) => b.Ms.CompareTo(a.Ms));
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("guestThreads", "hostPause", record,
                $"{threads.Length} threads: able to run {running} (on a guest core {onCore}), waiting {waiting}, other {other}; " +
                $"able to run but not run for {StarvedMs:F0} ms or more: {(starved.Count != 0 ? string.Join(", ", starved) : "none")}; " +
                $"longest waits: {string.Join("; ", waits.Take(6).Select(w => w.Text))}");
        }

        internal IDebuggableProcess DebugGetApplicationProcessDebugInterface()''')
    return list(paths.values())
