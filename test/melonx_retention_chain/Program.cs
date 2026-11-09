// The production RecordRetentionChain (Library.cs, adapt_retention_chain) with its fields, run on real weak references
// and real threads: a part kept alive, a part released, a host thread still running, one finished but still referenced,
// one finished and unreferenced. The journal is a double that keeps the lines.
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace Ryujinx.Common
{
    static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Lines = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
            => Lines.Add(stage + " " + status + " " + detail);
    }
}

namespace Ryujinx.Library
{
    partial class Library
    {
        private static readonly object _releasedSessionsLock = new();

        internal static void Set(List<(string Kind, WeakReference Part)> parts)
        {
            lock (_releasedSessionsLock)
            {
                _closingParts = parts;
                _closingFullCollections = GC.CollectionCount(2);
            }
        }
    }

    static class Program
    {
        static object _kept;
        static Thread _keptThread;

        [MethodImpl(MethodImplOptions.NoInlining)]
        static List<(string Kind, WeakReference Part)> Parts(ManualResetEventSlim release)
        {
            _kept = new object();
            Thread running = new(() => release.Wait()) { Name = "HLE.GuestThread.7", IsBackground = true };
            running.Start();
            Thread finishedKept = new(() => { }) { Name = "HLE.GuestThread.8" };
            finishedKept.Start();
            finishedKept.Join();
            _keptThread = finishedKept;
            Thread finished = new(() => { }) { Name = "HLE.OsThread.9" };
            finished.Start();
            finished.Join();
            return new()
            {
                ("window", new WeakReference(_kept)),
                ("horizon", new WeakReference(new object())),
                ("kthread", new WeakReference(_kept)),
                ("kthread", new WeakReference(new object())),
                ("hostThread:" + running.Name, new WeakReference(running)),
                ("hostThread:" + finishedKept.Name, new WeakReference(finishedKept)),
                ("hostThread:" + finished.Name, new WeakReference(finished)),
            };
        }

        static void Main()
        {
            using ManualResetEventSlim release = new(false);
            Library.Set(Parts(release));
            GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
            GC.WaitForPendingFinalizers();
            GC.Collect();
            Library.RecordRetentionChain("close");
            Library.RecordRetentionChain("nextFirstFrame");
            Library.RecordRetentionChain("nextFirstFrame");
            release.Set();
            Console.WriteLine(JsonSerializer.Serialize(new { lines = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines, kept = _kept != null && _keptThread != null }));
        }
    }
}
