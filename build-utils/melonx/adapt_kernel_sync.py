"""Make the emulated kernel's condition variables and address arbiter wake the
threads the Horizon kernel wakes.

FINAL FANTASY TACTICS - The Ivalice Chronicles, 28 October 2026 (Build 576
app.log, three launches): 0.4 s after start every guest thread of the game
waited in the kernel, the main thread in nn::os::WaitEvent, three job threads
in WaitEvent and two idle workers waiting for work, with no service call and
no SVC failure after the save data was mounted. A thread that should have
been woken was not. Four places where this kernel differs from the real one
(Atmosphere's mesosphere, reverse engineered from it) can lose or misdirect a
wakeup:

- A timed wait that expired left its thread in the condition variable (or
  address arbiter) waiter list until that thread ran again. A signal in that
  window picked the thread that had already timed out, and the thread still
  waiting was never woken: a lost wakeup when, as in a job system, several
  threads wait on one condition variable. The kernel cancels a timed wait under
  the scheduler lock and removes the thread from the waiter tree at once
  (KConditionVariable / KAddressArbiter CancelWait). KThread.TimeUp now does
  the same, as does thread termination.
- Waiters of equal priority were inserted at the position List.BinarySearch
  happened to return, so a signal could wake the newest waiter first. The
  kernel's waiter trees keep equal priorities first in, first out.
- SignalToAddress(SignalAndModifyByWaitingCountIfEqual) left the value unchanged
  when exactly `count` threads waited, and subtracted 2 when count <= 0. The
  kernel subtracts 1 whenever the signal leaves no waiter (Atmosphere,
  "kern: mea culpa (some time since 7.x)"), as the code's own comment states.
  nn::os::LightEvent signals with this type and count 1.
- WaitForAddress(DecrementAndWaitIfLessThan) decremented the value even when it
  was not below the threshold (and then returned InvalidState). The kernel's
  DecrementIfLessThan only writes a value that is below it.

Also as in the kernel: a condition variable wait with a zero timeout returns
TimedOut without joining the waiter list, and SignalProcessWideKey clears the
has-waiter word whenever no waiter remains. Nothing else changes in
scheduling. Fail closed on drift.
"""
from adapt_session import once


def replace_all(path, old, new, count):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == count, (str(path), old[:90], text.count(old))
    path.write_text(text.replace(old, new), encoding='utf-8')


def apply(source):
    threading = source / 'src/Ryujinx.HLE/HOS/Kernel/Threading'
    thread = threading / 'KThread.cs'
    once(thread, '''        public bool WaitingInArbitration { get; set; }
''', '''        public bool WaitingInArbitration { get; set; }

        // The condition variable or address arbiter waiter list holding this
        // thread, under the kernel critical section; null when not listed.
        public List<KThread> SyncWaitList { get; set; }

        public void LeaveSyncWaitList()
        {
            if (SyncWaitList != null)
            {
                SyncWaitList.Remove(this);
                SyncWaitList = null;
                WaitingInArbitration = false;
            }
        }
''')
    once(thread, '''        public void TimeUp()
        {
            ReleaseAndResume();
        }
''', '''        public void TimeUp()
        {
            KernelContext.CriticalSection.Enter();

            // As the kernel cancels an expired wait: leave the waiter list now,
            // so that no signal picks this thread instead of one still waiting.
            LeaveSyncWaitList();

            ReleaseAndResume();

            KernelContext.CriticalSection.Leave();
        }
''')
    once(thread, '''                    SignaledObj = null;
                    ObjSyncResult = KernelResult.ThreadTerminating;

                    ReleaseAndResume();
''', '''                    SignaledObj = null;
                    ObjSyncResult = KernelResult.ThreadTerminating;

                    LeaveSyncWaitList();

                    ReleaseAndResume();
''')

    arbiter = threading / 'KAddressArbiter.cs'
    once(arbiter, '''            if (!KernelTransfer.KernelToUser(mutexAddress, mutexValue))
            {
                _context.CriticalSection.Leave();

                return KernelResult.InvalidMemState;
            }
''', '''            if (!KernelTransfer.KernelToUser(mutexAddress, mutexValue))
            {
                _context.CriticalSection.Leave();

                return KernelResult.InvalidMemState;
            }

            if (timeout == 0)
            {
                _context.CriticalSection.Leave();

                return KernelResult.TimedOut;
            }
''')
    once(arbiter, '''            if (_condVarThreads.TryGetValue(condVarAddress, out List<KThread> threads))
            {
                int i = 0;

                if (threads.Count > 0)
                {
                    i = threads.BinarySearch(currentThread, _byDynamicPriority);
                    if (i < 0) i = ~i;
                }
                
                threads.Insert(i, currentThread);
            }
            else
            {
                _condVarThreads.Add(condVarAddress, [currentThread]);
            }
''', '''            InsertWaiter(_condVarThreads, condVarAddress, currentThread);
''')
    once(arbiter, '''            _condVarThreads[condVarAddress].Remove(currentThread);
''', '''            currentThread.LeaveSyncWaitList();
''')
    replace_all(arbiter, '''                if (_arbiterThreads.TryGetValue(address, out List<KThread> threads))
                {
                    int i = 0;

                    if (threads.Count > 0)
                    {
                        i = threads.BinarySearch(currentThread, _byDynamicPriority);
                        if (i < 0) i = ~i;
                    }
                
                    threads.Insert(i, currentThread);
                }
                else
                {
                    _arbiterThreads.Add(address, [currentThread]);
                }
''', '''                InsertWaiter(_arbiterThreads, address, currentThread);
''', 2)
    replace_all(arbiter, '''                if (currentThread.WaitingInArbitration)
                {
                    _arbiterThreads[address].Remove(currentThread);

                    currentThread.WaitingInArbitration = false;
                }
''', '''                currentThread.LeaveSyncWaitList();
''', 2)
    once(arbiter, '''            if (validThreads == 0)
            {
                KernelTransfer.KernelToUser(address, 0);
            }
''', '''            if (threads == null || threads.Count == 0)
            {
                KernelTransfer.KernelToUser(address, 0);
            }
''')
    once(arbiter, '''            if (shouldDecrement)
            {
                currentValue = Interlocked.Decrement(ref currentProcess.CpuMemory.GetRef<int>(address)) + 1;
            }
''', '''            if (shouldDecrement)
            {
                // DecrementIfLessThan: memory changes only below the threshold.
                ref int valueRef = ref currentProcess.CpuMemory.GetRef<int>(address);

                do
                {
                    currentValue = Volatile.Read(ref valueRef);
                }
                while (currentValue < value &&
                       Interlocked.CompareExchange(ref valueRef, currentValue - 1, currentValue) != currentValue);
            }
''')
    once(arbiter, '''            if (waitingCount > 0)
            {
                if (count <= 0)
                {
                    addend = -2;
                }
                else if (waitingCount < count)
                {
                    addend = -1;
                }
                else
                {
                    addend = 0;
                }
            }
''', '''            if (waitingCount > 0)
            {
                addend = count <= 0 || waitingCount <= count ? -1 : 0;
            }
''')
    once(arbiter, '''            for (int i = 0; i < validCount; i++)
            {
                KThread thread = threads[i];
                removeCallback(thread);
            }
''', '''            for (int i = 0; i < validCount; i++)
            {
                KThread thread = threads[i];
                thread.SyncWaitList = null;
                removeCallback(thread);
            }
''')
    once(arbiter, '''        private class ByDynamicPriority : IComparer<KThread>
''', '''        // After every waiter of the same or a higher priority: first in, first
        // out within a priority, as the kernel's waiter trees.
        private void InsertWaiter(Dictionary<ulong, List<KThread>> waiters, ulong key, KThread thread)
        {
            if (!waiters.TryGetValue(key, out List<KThread> threads))
            {
                threads = [];
                waiters.Add(key, threads);
            }

            int low = 0, high = threads.Count;

            while (low < high)
            {
                int middle = (low + high) >>> 1;

                if (_byDynamicPriority.Compare(threads[middle], thread) <= 0)
                {
                    low = middle + 1;
                }
                else
                {
                    high = middle;
                }
            }

            threads.Insert(low, thread);
            thread.SyncWaitList = threads;
        }

        private class ByDynamicPriority : IComparer<KThread>
''')
    return [thread, arbiter]
