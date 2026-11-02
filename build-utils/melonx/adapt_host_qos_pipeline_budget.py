"""Raise the threads that pace a frame, and keep large games' pipeline caches (every title).

Build 620 journals, iPhone 16 Pro (A18 Pro: two performance cores of six), 2 November 2026:

- Hogwarts Legacy (PID 66809, 13-16 FPS): the render thread, NeoStation.MeloNX.Render, is the
  busiest thread (55-65 % CPU, busy 96 % of each 5.1 s window), and GPU.MainThread paces the GPU
  commands. Both run at priority 31 (default QoS): .NET starts its threads without a QoS class.
  The guest's and the system's GCD work above them runs at 37-47, so the scheduler may keep the
  two threads off the performance cores.
- Super Smash Bros. Ultimate (PID 67058, 57.6 FPS, p50/p95/p99 17 ms): 143 pauses over 50 ms
  and 80 over 100 ms (up to 3.75 s), each in a window of pipeline builds of 120-320 ms each.
  During them the GPU thread waits for the render thread (up to 2.5 s per window), and the guest
  for the GPU ("ServiceNv Wait"). A draw waits for its demanded pipeline compile; the demand
  thread runs at the default QoS, and so does the Metal compilation it requests. The main
  pipeline cache loaded 383.81 MiB of its 384 MiB budget and "will not be persisted until it
  fits". A full main cache cannot take a worker cache either: the worker 0 cache was recycled
  six times in 10 s at its 64 MiB budget. So nothing a session compiles is kept, and the same
  pipelines are converted again, in game, every session.

Changes, for every title:
- ThreadedRenderer.RunLoop raises the render thread (its caller) and the GPU command thread it
  starts to user-interactive QoS (pthread_set_qos_class_self_np), on Apple platforms only.
  Elsewhere, or if the call is unavailable, nothing changes.
- The demand thread of BackgroundCompilationScheduler, which compiles what a draw waits for,
  raises itself the same way. The background workers keep their QoS.
- The pipeline cache budget is 1 GiB (main 768 MiB, 128 MiB per worker), 512 MiB before;
  everything else in its policy is unchanged. MoltenVK keeps that data LZ4-compressed in memory.
  Hogwarts Legacy's cache is 104 MiB and does not grow from this change.

Not measured on the iPhone; no FPS claim. Fail closed on drift.
"""
from pathlib import Path

from adapt_session import once

THREADED = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
PIPELINE_CACHE = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
SCHEDULER = 'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs'
NAMES = [THREADED, PIPELINE_CACHE, SCHEDULER]

THREADED_NAMESPACE_OLD = '''    /// <summary>
    /// The ThreadedRenderer is a layer'''
THREADED_NAMESPACE_NEW = '''    /// <summary>
    /// Apple platforms: the render thread and the GPU command thread pace every frame, and .NET starts them at the default
    /// QoS, below the guest's and the system's user-interactive work, so the scheduler may keep them off the performance
    /// cores. They raise themselves to user-interactive QoS. Elsewhere, or if the call is unavailable, nothing changes.
    /// </summary>
    public static partial class HostThreadQos
    {
        private const uint UserInteractive = 0x21;
        private static int _failureNoted;

        [LibraryImport("/usr/lib/libSystem.B.dylib", EntryPoint = "pthread_set_qos_class_self_np")]
        private static partial int SetQosClassSelf(uint qosClass, int relativePriority);

        public static void RaiseCurrentThread()
        {
            if (!OperatingSystem.IsIOS() && !OperatingSystem.IsMacOS() && !OperatingSystem.IsMacCatalyst())
            {
                return;
            }

            try
            {
                int result = SetQosClassSelf(UserInteractive, 0);

                // The thread keeps its QoS when the call fails (EPERM after pthread_setschedparam): logged once.
                if (result != 0 && Interlocked.Exchange(ref _failureNoted, 1) == 0)
                {
                    Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu,
                        $"Host thread QoS: pthread_set_qos_class_self_np returned {result} on {Thread.CurrentThread.Name}");
                }
            }
            catch (DllNotFoundException)
            {
            }
            catch (EntryPointNotFoundException)
            {
            }
        }
    }

    /// <summary>
    /// The ThreadedRenderer is a layer'''
THREADED_OLD = '''            _backendThread = Thread.CurrentThread;

            _gpuThread = new Thread(() =>
            {
                try { gpuLoop(); }'''
THREADED_NEW = '''            _backendThread = Thread.CurrentThread;
            HostThreadQos.RaiseCurrentThread();

            _gpuThread = new Thread(() =>
            {
                HostThreadQos.RaiseCurrentThread();
                try { gpuLoop(); }'''

PIPELINE_BUDGET_OLD = '''        private const long TotalCacheBudget = 512L * 1024 * 1024;'''
PIPELINE_BUDGET_NEW = '''        // Super Smash Bros. Ultimate filled the 384 MiB main budget (383.81 MiB loaded in build 620): nothing a session
        // compiled was kept any more, and the same pipelines were converted again in game every session.
        private const long TotalCacheBudget = 1024L * 1024 * 1024;'''

SCHEDULER_OLD = '''            private void WorkerLoop(int workerIndex, bool demandOnly)
            {
                while (true)'''
SCHEDULER_NEW = '''            private void WorkerLoop(int workerIndex, bool demandOnly)
            {
                if (demandOnly)
                {
                    // A draw waits for every demanded compile: this thread, and the Metal compilation it requests, run at
                    // user-interactive QoS on Apple platforms. The background workers keep their QoS.
                    Ryujinx.Graphics.GAL.Multithreading.HostThreadQos.RaiseCurrentThread();
                }

                while (true)'''



def apply_threaded(path):
    once(Path(path), THREADED_NAMESPACE_OLD, THREADED_NAMESPACE_NEW)
    once(Path(path), THREADED_OLD, THREADED_NEW)


def apply_pipeline_budget(path):
    once(Path(path), PIPELINE_BUDGET_OLD, PIPELINE_BUDGET_NEW)


def apply_scheduler(path):
    once(Path(path), SCHEDULER_OLD, SCHEDULER_NEW)


def apply(source):
    source = Path(source)
    apply_threaded(source / THREADED)
    apply_pipeline_budget(source / PIPELINE_CACHE)
    apply_scheduler(source / SCHEDULER)
    return NAMES
