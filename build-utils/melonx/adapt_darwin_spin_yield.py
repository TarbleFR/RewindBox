"""The adaptive spin yields without lowering the waiting thread to priority 0 on Apple platforms (every title).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journal, pid 5954): in the [MeloNX:hot] profiles of the slow phases,
855 of 3 258 running samples of the busiest threads (26.2 %) are in AdaptiveSpinEvent.Wait's yield (SpinWait.SpinOnce
-> Thread.Yield), RHIThread 65-68 of its 300; the [MeloNX:stall] snapshots catch the yielding threads in state R at
pth_curpri 0 for a base of 31, 37 or 47 while threads at 4 and 20 run. On Apple platforms Thread.Yield is the runtime's
PalSwitchToThread, sched_yield, which XNU implements as swtch_pri(0): when another thread is ready, the yielding thread
is depressed to priority 0 until it runs again, up to a quantum (10 ms). A game thread at 47 then queues behind the
shader compilers (31), the background GC (31) and the helpers (20), and its partner's Set does not wake it, since it is
not blocked. Measured in this repository on a real XNU kernel (docs/rpcs3-cell579.md, CI Mac, five busy threads):
sched_yield up to 22.4 ms, 6 271 ms for 800 yields; thread_switch(MACH_PORT_NULL, SWITCH_OPTION_NONE, 0) up to 18 us,
0.4 ms in all (RPCS3's CELL579 writer yield uses it on the iPhone). adapt_wait_spin_bound's bound stops the yields that
outlast two spins on a free core, but an event set during the first, depressed yield still paid it, at every wait.

Change (AsyncWorkQueue.cs, AdaptiveSpinEvent): on Apple platforms, past the ten pause iterations, the spin yields with
thread_switch(MACH_PORT_NULL, SWITCH_OPTION_NONE, 0) (libSystem) at the iterations where SpinWait yields, and pauses
(Thread.SpinWait(8), about SpinWait's own pause there) at the others; Wait and Calibrate count the same iterations,
budgets and bound unchanged. Elsewhere, and on Apple if the export cannot be bound (the call throws once: the flag is
cleared and SpinWait's own yield is made), the iteration is SpinWait.SpinOnce as before. The waits end the same ways.

Expected on the device: the [MeloNX:stall] samples in AdaptiveSpinEvent's yield no longer at pth_curpri 0; GPU-thread
waits on the render thread and slow-phase frame gaps lower. Not measured on an iPhone; the host gate (Linux) proves the
other platforms unchanged and the fallback. Applied after adapt_wait_spin_bound (its post-image). Rollback: drop this
adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

COMMON = 'src/Ryujinx.Common/AsyncWorkQueue.cs'
BASELINE = {COMMON: 'aed94a41c35379f6969715a45de4865e530555abdc787418164a6b7633856882'}

MEMBERS_OLD = '''        public int SpinBudget => _score >= 0 ? FullIterations : PauseIterations;
'''
MEMBERS_NEW = '''        public int SpinBudget => _score >= 0 ? FullIterations : PauseIterations;

        // RewindBox (adapt_darwin_spin_yield): on Apple platforms Thread.Yield is sched_yield, which XNU implements as
        // swtch_pri(0): the yielding thread drops to priority 0 until it runs again, behind every ready thread, and its
        // partner's Set does not wake it. Past the pause iterations the spin yields with thread_switch(MACH_PORT_NULL,
        // SWITCH_OPTION_NONE, 0) instead, which gives the core away without the depression. Cleared if the export
        // cannot be bound (SpinWait's own yield is made then).
        internal static bool YieldWithoutDepression = System.OperatingSystem.IsIOS() || System.OperatingSystem.IsMacOS() ||
            System.OperatingSystem.IsMacCatalyst() || System.OperatingSystem.IsTvOS();

        // About SpinWait's pause between two of its yields (its OptimalMaxSpinWaitsPerSpinIteration is internal).
        private const int YieldPause = 8;

        [System.Runtime.InteropServices.DllImport("/usr/lib/libSystem.B.dylib")]
        private static extern int thread_switch(uint threadName, int option, uint optionTime);

        // One iteration of the spin: SpinWait's own; on Apple past the pause iterations, a yield without depression at
        // the iterations where SpinWait yields (every other one) and a pause at the others.
        private static void SpinOnce(ref System.Threading.SpinWait spinner, ref int count)
        {
            if (YieldWithoutDepression && count >= PauseIterations)
            {
                if (((count - PauseIterations) & 1) == 0)
                {
                    try
                    {
                        thread_switch(0, 0, 0);
                    }
                    catch (System.Exception)
                    {
                        YieldWithoutDepression = false;
                        spinner.SpinOnce(sleep1Threshold: -1);
                    }
                }
                else
                {
                    System.Threading.Thread.SpinWait(YieldPause);
                }
            }
            else
            {
                spinner.SpinOnce(sleep1Threshold: -1);
            }

            count++;
        }
'''

WAIT_OLD = '''            System.Threading.SpinWait spinner = default;

            while (spinner.Count < budget)
            {
                if (spinner.Count == PauseIterations)
                {
                    // The pause iterations are over: the iterations that yield start now.
                    yields = System.Diagnostics.Stopwatch.GetTimestamp();
                }

                spinner.SpinOnce(sleep1Threshold: -1);

                if (_event.IsSet)
'''
WAIT_NEW = '''            System.Threading.SpinWait spinner = default;
            int count = 0; // RewindBox (adapt_darwin_spin_yield): the spin's iterations, SpinWait's or the Apple ones

            while (count < budget)
            {
                if (count == PauseIterations)
                {
                    // The pause iterations are over: the iterations that yield start now.
                    yields = System.Diagnostics.Stopwatch.GetTimestamp();
                }

                SpinOnce(ref spinner, ref count);

                if (_event.IsSet)
'''

CALIBRATE_OLD = '''                System.Threading.SpinWait spinner = default;
                while (spinner.Count < PauseIterations)
                {
                    spinner.SpinOnce(sleep1Threshold: -1);
                }

                pause = System.Math.Min(pause, System.Diagnostics.Stopwatch.GetTimestamp() - start);
                while (spinner.Count < FullIterations)
                {
                    spinner.SpinOnce(sleep1Threshold: -1);
                }
'''
CALIBRATE_NEW = '''                System.Threading.SpinWait spinner = default;
                int count = 0; // RewindBox (adapt_darwin_spin_yield): the same iterations as Wait's
                while (count < PauseIterations)
                {
                    SpinOnce(ref spinner, ref count);
                }

                pause = System.Math.Min(pause, System.Diagnostics.Stopwatch.GetTimestamp() - start);
                while (count < FullIterations)
                {
                    SpinOnce(ref spinner, ref count);
                }
'''

PAIRS = ((MEMBERS_OLD, MEMBERS_NEW), (WAIT_OLD, WAIT_NEW), (CALIBRATE_OLD, CALIBRATE_NEW))
FILE_PAIRS = {COMMON: PAIRS}


def apply(source):
    path = source / COMMON
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, COMMON
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
