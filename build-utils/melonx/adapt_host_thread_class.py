"""The threads a frame or the sound waits for run in the user-interactive class, as the render and GPU threads do.

IPA 725, Hogwarts Legacy on an iPhone 16 Pro Max (two performance and four efficiency cores; pid 51986; private
journals, not in the repository; aggregates only). The per-second journal lists the busiest threads with their base
priority and, since lot 11, the share of their CPU time spent on performance cores:
- the engine's render and GPU threads (raised by adapt_host_qos_pipeline_budget): priority 47, 80 to 97 % of their
  time on performance cores;
- the guest's own threads: priority 31. `<MainThread>`, the largest CPU consumer of the process (53.4 s of 290 s at
  t=120 s), 61 % on performance cores in the 20 s at 30 FPS and 20 to 35 % in the stretches at 20 FPS;
  `<RenderThread_1>` and `<RHIThread>` 23 to 32 % there;
- every other thread .NET starts: priority 31 as well, including those upstream asks a higher priority for
  (HLE.TimeManager, SurfaceFlinger.Composer and the sleep pool set ThreadPriority.AboveNormal: without effect here).
Over those stretches the process's threads waited for a core 1.4 to 1.8 times as long as they ran (hw=, the kernel's
runnable time less the CPU time). The stage that feeds the frame chain is the one the scheduler serves last.

Change: a helper (Ryujinx.Common.HostThreadClass, in NanosleepPool.cs: the one file of Ryujinx.Common this adapter
edits, so that every tree built with a part of it holds the helper) asks the user-interactive class for the calling
thread (pthread_set_qos_class_self_np, as HostThreadQos does for the render and GPU threads), on Apple platforms only.
Each of these threads calls it first thing:
- KThread.ThreadStart: every guest thread and every HLE service thread (the guest's scheduler runs at most one of them
  per virtual core; the others wait on their scheduler event);
- KTimeManager's worker (it wakes the guest threads at their deadlines) and the kernel's preemption thread;
- the sleep pool's threads (Common.Nanosleep.N);
- SurfaceFlinger's composer (it presents at the guest's vertical blank);
- the audio workers (AudioProcessor.Worker: 1 965 late DSP episodes in the 182 s sampled; AudioRendererManager.Worker;
  AudioManager.Worker).
A refusal changes nothing for the thread and is recorded once in the engine journal ("hostThreadClass refused").
Not changed: what the threads do, the guest scheduler, the helpers that are not on a frame's path (collector, pipeline
compile workers, disk cache writer, logger, thread pool) and HostThreadQos.

Not measured on an iPhone: to read on the next run, cpu= (priority 47 for the guest threads) and pc= (their share on
performance cores), hw= (waiting for a core), dsp= (late episodes) and th= (the thermal state: more work on the
performance cores). Fail closed on drift: the eight files must be the Core 731 preparation's.
"""
import hashlib
from adapt_session import once

SLEEP = 'src/Ryujinx.Common/PreciseSleep/NanosleepPool.cs'
THREAD = 'src/Ryujinx.HLE/HOS/Kernel/Threading/KThread.cs'
TIMER = 'src/Ryujinx.HLE/HOS/Kernel/Common/KTimeManager.cs'
KERNEL = 'src/Ryujinx.HLE/HOS/Kernel/KernelContext.cs'
FLINGER = 'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/SurfaceFlinger.cs'
PROCESSOR = 'src/Ryujinx.Audio/Renderer/Dsp/AudioProcessor.cs'
RENDERER = 'src/Ryujinx.Audio/Renderer/Server/AudioRendererManager.cs'
MANAGER = 'src/Ryujinx.Audio/AudioManager.cs'
BASELINE = {
    SLEEP: '8129273336c9254952b981dcd98a77bb8e8ed8f107ccadd7d3d2b225ff964dbf',
    THREAD: 'f2f87513fc6698983ea3fc8969707cf256d40b197fa572430ea28340989fc148',
    TIMER: '72a9c2ebe5ad38a5259a2f8eb847e98db9a34f3c614c65710631595d79f520a3',
    KERNEL: '282e985a72b9d4c47e3152900d61936193884ad8b5af32d82807788f183654fc',
    FLINGER: '725c9111dbf94e64362adc1e3adb905f6cae7a5bae31649db79917a5f361f29a',
    PROCESSOR: '3ea1ab4e0a63dd2822cfff664ce8f58cd229dc6d3dacae4303794d2126dfa2ea',
    RENDERER: '7bb129025f1964e227df42fe99cd8b7b67c8a5723013c7f76d0eb6f0e2b1b96c',
    MANAGER: '980c75966c94e6e34cda5acf6b7a995cb345c2fe6179138f4e6699fbf79ad11b',
}

HELPER_BEGIN = '    // RewindBox (adapt_host_thread_class): begin\n'
HELPER_END = '    // RewindBox (adapt_host_thread_class): end\n'
HELPER_OLD = '''namespace Ryujinx.Common.PreciseSleep
{
'''
HELPER_NEW = '''namespace Ryujinx.Common
{
''' + HELPER_BEGIN + '''    /// <summary>
    /// Apple platforms start every thread .NET creates in the default class (base priority 31), and Thread.Priority
    /// changes nothing there. The threads a frame or the sound waits for (the guest's threads and the services they
    /// call, the kernel's timer and preemption threads, the sleep pool, the compositor, the audio workers) ask the
    /// user-interactive class for themselves, where the render and GPU threads already are (HostThreadQos). Elsewhere,
    /// or if the call is unavailable or refused, the thread keeps its class.
    /// </summary>
    public static class HostThreadClass
    {
        public const uint UserInteractive = 0x21;

        // Replaced by the fixture only (the host that runs it is not an Apple platform); never assigned in the engine.
        internal static System.Func<bool> ApplePlatform = () => System.OperatingSystem.IsIOS() || System.OperatingSystem.IsMacOS() || System.OperatingSystem.IsMacCatalyst();
        internal static System.Func<uint, int, int> SetClass = SetQosClassSelf;

        private static int _refusalNoted;

        [System.Runtime.InteropServices.DllImport("/usr/lib/libSystem.B.dylib", EntryPoint = "pthread_set_qos_class_self_np")]
        private static extern int SetQosClassSelf(uint qosClass, int relativePriority);

        /// <returns>True when the calling thread is now in the user-interactive class</returns>
        public static bool RaiseCurrentThread()
        {
            if (!ApplePlatform())
            {
                return false;
            }

            int result;

            try
            {
                result = SetClass(UserInteractive, 0);
            }
            catch (System.DllNotFoundException)
            {
                return false;
            }
            catch (System.EntryPointNotFoundException)
            {
                return false;
            }

            if (result != 0 && System.Threading.Interlocked.Exchange(ref _refusalNoted, 1) == 0)
            {
                // The thread keeps its class (EPERM after pthread_setschedparam): recorded once.
                EmbeddedLaunchDiagnostics.Record("hostThreadClass", "refused", result,
                    $"pthread_set_qos_class_self_np returned {result} on {System.Threading.Thread.CurrentThread.Name} (adapt_host_thread_class)");
            }

            return result == 0;
        }
    }
''' + HELPER_END + '''}

namespace Ryujinx.Common.PreciseSleep
{
'''

CALL = 'Ryujinx.Common.HostThreadClass.RaiseCurrentThread(); // RewindBox (adapt_host_thread_class)\n'


def first(indent, head, next_line):
    """(old, new): the call as the first statement of a thread's body."""
    old = head + indent + next_line
    return old, head + indent + CALL + indent + next_line


# (file, thread, old, new): one site per thread kind.
SITES = (
    (SLEEP, 'Common.Nanosleep.N', *first('                ', '            private void Loop()\n            {\n', '_newWaitEvent.WaitOne();\n')),
    (THREAD, 'guest and HLE service threads', *first('            ', '        private void ThreadStart()\n        {\n', '_schedulerWaitEvent.Wait();\n')),
    (TIMER, 'HLE.TimeManager', *first('            ', '        private void WaitAndCheckScheduledObjects()\n        {\n', 'WaitingObject next;\n')),
    (KERNEL, 'HLE.PreemptionThread', *first('                ', '            void PreemptionThreadStart()\n            {\n', 'KScheduler.PreemptionThreadLoop(this);\n')),
    (FLINGER, 'SurfaceFlinger.Composer', *first('            ', '        private void HandleComposition()\n        {\n', '_isRunning = true;\n')),
    (PROCESSOR, 'AudioProcessor.Worker', *first('            ', '        private void Work()\n        {\n', 'if (_mailbox.ReceiveMessage() != MailboxMessage.Start)\n')),
    (RENDERER, 'AudioRendererManager.Worker', *first('            ', '        private void SendCommands()\n        {\n',
                                                     'Logger.Info?.Print(LogClass.AudioRenderer, "Starting audio renderer");\n')),
    (MANAGER, 'AudioManager.Worker', *first('            ', '        private void Update()\n        {\n', 'while (_isRunning)\n')),
)

PAIRS = ((SLEEP, HELPER_OLD, HELPER_NEW),) + tuple((name, old, new) for name, _, old, new in SITES)


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
