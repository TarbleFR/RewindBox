// Fixture of test/melonx_host_thread_class_system_test.py (macOS): the adapter's real helper (Helper.cs, generated from
// adapt_host_thread_class) with the system's own call, on the kinds of thread a process can have. One JSON line, written
// by hand: the same source runs under the host runtime and compiled ahead of time (NativeAOT), where reflection-based
// serialization is not available.
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Ryujinx.Common
{
    // The engine journal's entry point the helper calls on a refusal.
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "")
        {
            lock (Records) Records.Add(stage + " " + status + " " + code + ": " + detail);
        }
    }
}

public static unsafe class Program
{
    [DllImport("/usr/lib/libSystem.B.dylib", EntryPoint = "qos_class_self")]
    private static extern uint QosClassSelf();
    [DllImport("/usr/lib/libSystem.B.dylib", EntryPoint = "pthread_set_qos_class_self_np")]
    private static extern int SetQosClassSelf(uint qosClass, int relativePriority);
    [DllImport("/usr/lib/libSystem.B.dylib", EntryPoint = "pthread_create")]
    private static extern int PthreadCreate(out IntPtr thread, IntPtr attributes, delegate* unmanaged<IntPtr, IntPtr> start, IntPtr argument);
    [DllImport("/usr/lib/libSystem.B.dylib", EntryPoint = "pthread_join")]
    private static extern int PthreadJoin(IntPtr thread, out IntPtr value);

    private static readonly Dictionary<string, string> Report = new();

    // helper: the adapter's RaiseCurrentThread; raw: the system call itself (its return value is an errno).
    private static string Measure(bool helper)
    {
        uint before = QosClassSelf();
        string answer = helper ? (Ryujinx.Common.HostThreadClass.RaiseCurrentThread() ? "true" : "false") : SetQosClassSelf(0x21, 0).ToString();
        return "{\"classBefore\":" + before + ",\"answer\":" + answer + ",\"classAfter\":" + QosClassSelf() + "}";
    }

    private static string Text(string value) => "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

    private static string _kind;
    private static bool _helper;

    [UnmanagedCallersOnly]
    private static IntPtr Start(IntPtr argument)
    {
        Report[_kind] = Measure(_helper);
        return IntPtr.Zero;
    }

    private static void SystemThread(string kind, bool helper)
    {
        _kind = kind; _helper = helper;
        if (PthreadCreate(out IntPtr thread, IntPtr.Zero, &Start, IntPtr.Zero) != 0) { Report[kind] = Text("pthread_create failed"); return; }
        PthreadJoin(thread, out _);
    }

    private static void RuntimeThread(string kind, bool helper)
    {
        var thread = new Thread(() => Report[kind] = Measure(helper)) { Name = kind };
        thread.Start();
        thread.Join();
    }

    public static int Main()
    {
        // A thread of the system (pthread_create with default attributes): what a NativeAOT runtime's threads are.
        SystemThread("systemThreadRaw", false);
        SystemThread("systemThreadHelper", true);
        // A thread this host runtime creates (new Thread), and one of its pool.
        RuntimeThread("runtimeThreadRaw", false);
        RuntimeThread("runtimeThreadHelper", true);
        Task.Run(() => Report["poolThreadRaw"] = Measure(false)).Wait();
        Report["records"] = "[" + string.Join(",", Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.Select(Text)) + "]";
        Report["runtime"] = Text(RuntimeInformation.FrameworkDescription);
        Report["aheadOfTime"] = RuntimeFeature.IsDynamicCodeSupported ? "false" : "true";
        Report["os"] = Text(RuntimeInformation.OSDescription);
        Console.WriteLine("{" + string.Join(",", Report.Select(pair => Text(pair.Key) + ":" + pair.Value)) + "}");
        return 0;
    }
}
