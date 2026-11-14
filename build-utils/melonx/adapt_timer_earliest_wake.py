"""The guest timer thread is woken by a new deadline only when it comes before the one it sleeps for (every title).

IPA 736 / Core c4a25b94, Hogwarts Legacy (private journal, pid 2349, 51 s in the world between two [MeloNX:stall]
snapshots): HLE.TimeManager 3.7 % of a core in the user-interactive class, mostly in the kernel (666 ms of CPU, 512 ms
of them in the kernel, in the 6.1 s of the first loading gap). Read in the source: KTimeManager.ScheduleFutureInvocation
signals the timer thread at every new deadline, whatever its time; the thread wakes, takes the kernel's critical
section, scans the waiting list and goes back to sleep for the same deadline when the new one is later (a guest wait
with a long limit while a nearer one is pending, the usual case).

Change (KTimeManager.cs only): the timer thread records, inside the critical section in which it picks the nearest
deadline, the time it is about to sleep for (long.MaxValue when it sleeps with no deadline). A new deadline, added in
the same critical section, signals the thread only when it is earlier than that time. A later one needs no signal: the
thread wakes at the nearer deadline and picks the nearest again inside the critical section before it sleeps again.
Deadlines, their order and the times they fire are unchanged; a cancelled deadline still wakes the thread at its time,
as before. Dispose still signals.

Expected on the device: HLE.TimeManager CPU and sw= context switches lower; frame times and audio unchanged. Refuted
and removed if a guest wait with a limit ends late. Rollback: drop this adapter from prepare_embedded.py and ORDER.
Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.HLE/HOS/Kernel/Common/KTimeManager.cs'
BASELINE = {MANAGER: '8639138cb478fe9ed976f4049e08f04203c42fe128e629af0da6d65cd3a89394'}

FIELD_OLD = '''        private long _enforceWakeupFromSpinWait;

        private const long NanosecondsPerSecond = 1000000000L;
'''
FIELD_NEW = '''        private long _enforceWakeupFromSpinWait;
        // RewindBox (adapt_timer_earliest_wake): the time the timer thread sleeps for (long.MaxValue with no deadline, and
        // until its first pick: every deadline signals then), written and read inside the critical section only.
        private long _sleepingUntil = long.MaxValue;

        private const long NanosecondsPerSecond = 1000000000L;
'''

ADD_OLD = '''                _waitingObjects.Add(new WaitingObject(schedulerObj, timePoint, _waitingEpoch, sequence));

                if (timeout < NanosecondsPerMillisecond)
                {
                    Interlocked.Exchange(ref _enforceWakeupFromSpinWait, 1);
                }
            }

            _waitEvent.Signal();
        }
'''
ADD_NEW = '''                _waitingObjects.Add(new WaitingObject(schedulerObj, timePoint, _waitingEpoch, sequence));

                if (timeout < NanosecondsPerMillisecond)
                {
                    Interlocked.Exchange(ref _enforceWakeupFromSpinWait, 1);
                }

                // RewindBox (adapt_timer_earliest_wake): a deadline at or after the one the timer thread sleeps for needs
                // no signal: the thread wakes at the nearer one and picks the nearest again before it sleeps.
                earlier = timePoint < _sleepingUntil;
            }

            if (earlier)
            {
                _waitEvent.Signal();
            }
        }
'''

LOCAL_OLD = '''            timePoint = _waitEvent.AdjustTimePoint(timePoint, timeout);

            lock (_context.CriticalSection.Lock)
            {
                ulong sequence = unchecked(++_waitingSequence);
'''
LOCAL_NEW = '''            timePoint = _waitEvent.AdjustTimePoint(timePoint, timeout);
            bool earlier;

            lock (_context.CriticalSection.Lock)
            {
                ulong sequence = unchecked(++_waitingSequence);
'''

PICK_OLD = '''                        Interlocked.Exchange(ref _enforceWakeupFromSpinWait, 0);

                        next = GetNextWaitingObject();
                    }
'''
PICK_NEW = '''                        Interlocked.Exchange(ref _enforceWakeupFromSpinWait, 0);

                        next = GetNextWaitingObject();
                        _sleepingUntil = next.IsValid ? next.TimePoint : long.MaxValue; // RewindBox (adapt_timer_earliest_wake)
                    }
'''

PAIRS = ((FIELD_OLD, FIELD_NEW), (LOCAL_OLD, LOCAL_NEW), (ADD_OLD, ADD_NEW), (PICK_OLD, PICK_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[MANAGER], old, new)
    return list(paths.values())
