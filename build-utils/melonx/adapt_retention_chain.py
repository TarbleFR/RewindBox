"""Name the deepest part of a closed session still reachable after its final collection (Core 707, journal only).

IPA 694 and earlier (private journals): the "sessionRetention" line at a close reads, for every session closed in play
since Core 661 (Hogwarts Legacy pids 34380, 35880, 38401, 40200; Super Smash Bros. Ultimate pid 25853), "Switch still
reachable 1/1 (latest yes); GpuContext 1/1; PerformanceStatistics 1/1; Horizon 1/1; time service and Bluetooth
references 0; binder registry entries 0", with 500-563 MB of managed heap after the forced full collection, against
197 MB for Hogwarts sessions closed before their game threads ran (pids 25743, 35729, 36711: one guest thread at the
close, released) and 23 MB for the CI homebrew sessions (released). In pid 40200 the next session (SSBU) started 27 s
later on that heap (gen2 275 -> 279 MB, LOH 261 -> 419 MB five seconds into it). The probe only says that the Switch is
held, not by what: the timer, time service, Bluetooth and binder roots of Core 661/654 are released; the statics read
in this preparation (Switch.Shared, KernelStatic thread statics, the Library's fields, the session coordinator's
delegates, the window's input subscriptions, nvdrv's host1x registry, the tamper machine, the audio session handles)
release or overwrite theirs. The chain is not demonstrated, so nothing is changed yet.

Change (journal only, no behaviour change): just before the guest is terminated (WindowBase's guest stop, before
Horizon.Dispose clears the process list), the Library takes weak references to its
parts (window, input managers, Horizon, renderer, audio driver; through Ryujinx.HLE's SessionPartsDiagnostics the
kernel, each process, the application's CPU context and memory, each KThread and its host Thread, from a snapshot of
the process thread list under its lock). After the final collection of the close, a "retentionChain close" line counts
the parts still reachable per kind and the host threads still running (up to eight names); at the next session's first
frame a "retentionChain nextFirstFrame" line reports them again with the full collections since the close, then the
references are dropped. Weak references only (they never extend a lifetime); no collection added; one capture and two
lines per session. Fail closed on drift: the five files must be the Core 705 preparation's.
"""
import hashlib
from adapt_session import once

LIBRARY = 'src/Ryujinx.Library/Library.cs'
MEMORY = 'src/Ryujinx.Library/EmbeddedMemory.cs'
WINDOW = 'src/Ryujinx.Library/Window/WindowBase.cs'
HORIZON = 'src/Ryujinx.HLE/HOS/Horizon.cs'
PROCESS = 'src/Ryujinx.HLE/HOS/Kernel/Process/KProcess.cs'
BASELINE = {
    LIBRARY: '267268d0ce10d11a1c0330fcf6ba6f0161e0b539ff38066cfa6856b635bb776d',
    MEMORY: '3723ffb346980b3ee8d0a9a1a3199655052fe9f8c23c72033b6c8cd3aad584ee',
    WINDOW: '4aef1042198769fb746e5b752cad7d601c49eef9035f14773a782efb1b0d5705',
    HORIZON: 'e54f3c6c8596b247a6d316cdcc289e62139275b7b9dfd3c9d79e15d488928b66',
    PROCESS: '32e5867da5b800d1c2a4925beab6c35a7caae589ab38f036f2efa5a770fe62a0',
}

CAPTURE_OLD = '''                _gpuCancellationTokenSource.Cancel();
                Device.System.Dispose();
'''
CAPTURE_NEW = '''                _gpuCancellationTokenSource.Cancel();
                // RewindBox (adapt_retention_chain): weak references to the session's parts, before the guest is terminated.
                Library.NoteSessionParts(Device, this);
                Device.System.Dispose();
'''

REPORT_OLD = '''            // RewindBox (adapt_binder_teardown): journal only, after the final collection.
            RecordSessionRetention();
'''
REPORT_NEW = '''            // RewindBox (adapt_binder_teardown): journal only, after the final collection.
            RecordSessionRetention();
            // RewindBox (adapt_retention_chain): which parts of that session are still reachable.
            RecordRetentionChain("close");
'''

METHODS_OLD = '''        private static WindowBase CreateWindow(Options options)
'''
METHODS_NEW = '''        // RewindBox (adapt_retention_chain): the parts of the latest session closed, as weak references taken just before its
        // teardown (replaced at every close, dropped once reported at the next session's first frame), and the number of
        // full collections at that moment. Journal only: they never extend a lifetime.
        private static List<(string Kind, WeakReference Part)> _closingParts;
        private static int _closingFullCollections;
        private const int RunningThreadNames = 8;

        [MethodImpl(MethodImplOptions.NoInlining)]
        internal static void NoteSessionParts(Ryujinx.HLE.Switch context, WindowBase window)
        {
            try
            {
                List<(string Kind, WeakReference Part)> parts = new();

                void Add(string kind, object part)
                {
                    if (part != null)
                    {
                        parts.Add((kind, new WeakReference(part)));
                    }
                }

                Add("window", window);
                Add("npad", window?.NpadManager);
                Add("touch", window?.TouchScreenManager);
                Add("horizon", context.System);
                Add("renderer", context.Gpu?.Renderer);
                Add("audioDriver", context.AudioDeviceDriver);
                Ryujinx.HLE.HOS.SessionPartsDiagnostics.Capture(context.System, parts);

                lock (_releasedSessionsLock)
                {
                    _closingParts = parts;
                    _closingFullCollections = GC.CollectionCount(2);
                }
            }
            catch (Exception error)
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("retentionChain", "unavailable", detail: error.GetType().Name);
            }
        }

        // "close" after the final collection of a close; "nextFirstFrame" at the next session's first frame (then dropped).
        internal static void RecordRetentionChain(string when)
        {
            List<(string Kind, WeakReference Part)> parts;
            int fullCollections;

            lock (_releasedSessionsLock)
            {
                parts = _closingParts;
                fullCollections = _closingFullCollections;

                if (when != "close")
                {
                    _closingParts = null;
                }
            }

            if (parts == null)
            {
                return;
            }

            try
            {
                SortedDictionary<string, (int Alive, int Total)> kinds = new(StringComparer.Ordinal);
                List<string> running = new();
                int threads = 0, threadsAlive = 0, threadsRunning = 0;

                foreach ((string kind, WeakReference part) in parts)
                {
                    object target = part.Target;

                    if (kind.StartsWith("hostThread:", StringComparison.Ordinal))
                    {
                        threads++;

                        if (target is System.Threading.Thread thread)
                        {
                            threadsAlive++;

                            if (thread.IsAlive)
                            {
                                threadsRunning++;

                                if (running.Count < RunningThreadNames)
                                {
                                    running.Add(kind.Substring("hostThread:".Length));
                                }
                            }
                        }

                        continue;
                    }

                    kinds.TryGetValue(kind, out (int Alive, int Total) count);
                    kinds[kind] = (count.Alive + (target != null ? 1 : 0), count.Total + 1);
                }

                StringBuilder text = new();
                text.Append(when == "close" ? "after the final collection" : "at the next session's first frame")
                    .Append(" (full collections since the close: ").Append(GC.CollectionCount(2) - fullCollections)
                    .Append("), still reachable:");

                foreach (KeyValuePair<string, (int Alive, int Total)> entry in kinds)
                {
                    text.Append(' ').Append(entry.Key).Append(' ').Append(entry.Value.Alive).Append('/').Append(entry.Value.Total).Append(';');
                }

                text.Append(" host threads ").Append(threadsAlive).Append('/').Append(threads).Append(" (running ").Append(threadsRunning)
                    .Append(running.Count != 0 ? ": " + string.Join(", ", running) : string.Empty)
                    .Append("); managed heap ").Append(GC.GetTotalMemory(false) / (1024 * 1024)).Append(" MB (adapt_retention_chain)");
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("retentionChain", when, detail: text.ToString());
            }
            catch (Exception error)
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("retentionChain", "unavailable", detail: when + ": " + error.GetType().Name);
            }
        }

        private static WindowBase CreateWindow(Options options)
'''

FIRST_FRAME_OLD = '''        catch (System.Exception error)
        {
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("memory", "heapCompactionFailed", detail: "firstFrame: " + error.GetType().Name);
        }
    }
'''
FIRST_FRAME_NEW = '''        catch (System.Exception error)
        {
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("memory", "heapCompactionFailed", detail: "firstFrame: " + error.GetType().Name);
        }

        // RewindBox (adapt_retention_chain): the previous session's parts still reachable once this one shows its first frame.
        Library.RecordRetentionChain("nextFirstFrame");
    }
'''

HORIZON_OLD = '''                return KernelContext.Processes.Values.FirstOrDefault(x => x.IsApplication);
            }
        }
    }
}
'''
HORIZON_NEW = '''                return KernelContext.Processes.Values.FirstOrDefault(x => x.IsApplication);
            }
        }
    }

    /// <summary>
    /// RewindBox (adapt_retention_chain): weak references to the kernel parts of a session about to be closed (the kernel,
    /// each process, the application's CPU context and memory, each KThread and its host thread), for the host's
    /// retention journal. Called once, just before the teardown; never holds a strong reference.
    /// </summary>
    public static class SessionPartsDiagnostics
    {
        public static void Capture(Horizon system, System.Collections.Generic.List<(string Kind, WeakReference Part)> parts)
        {
            KernelContext kernel = system?.KernelContext;

            if (kernel == null)
            {
                return;
            }

            parts.Add(("kernel", new WeakReference(kernel)));

            foreach (KProcess process in kernel.Processes.Values)
            {
                parts.Add((process.IsApplication ? "applicationProcess" : "serviceProcess", new WeakReference(process)));

                if (process.IsApplication && process.Context != null)
                {
                    parts.Add(("cpuContext", new WeakReference(process.Context)));
                    parts.Add(("cpuMemory", new WeakReference(process.CpuMemory)));
                }

                foreach (KThread thread in process.RetentionThreads())
                {
                    parts.Add(("kthread", new WeakReference(thread)));

                    if (thread.HostThread != null)
                    {
                        parts.Add(("hostThread:" + thread.HostThread.Name, new WeakReference(thread.HostThread)));
                    }
                }
            }
        }
    }
}
'''

PROCESS_OLD = '''        public void RemoveThread(KThread thread)
'''
PROCESS_NEW = '''        // RewindBox (adapt_retention_chain): a snapshot of the thread list, for the host's retention journal at a close.
        public KThread[] RetentionThreads()
        {
            lock (_threadingLock)
            {
                KThread[] threads = new KThread[_threads.Count];
                _threads.CopyTo(threads, 0);

                return threads;
            }
        }

        public void RemoveThread(KThread thread)
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[WINDOW], CAPTURE_OLD, CAPTURE_NEW)
    once(paths[LIBRARY], REPORT_OLD, REPORT_NEW)
    once(paths[LIBRARY], METHODS_OLD, METHODS_NEW)
    once(paths[MEMORY], FIRST_FRAME_OLD, FIRST_FRAME_NEW)
    once(paths[HORIZON], HORIZON_OLD, HORIZON_NEW)
    once(paths[PROCESS], PROCESS_OLD, PROCESS_NEW)
    return list(paths.values())
