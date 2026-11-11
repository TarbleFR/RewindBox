// Fixture of test/melonx_host_thread_class_test.py. It loads the side's real assemblies (Ryujinx.Common, Ryujinx.Audio,
// Ryujinx.HLE, built from the side's tree) and runs, each on its own named thread, the real body of every thread the
// adapter raises, on an object left uninitialized: the body's first statements run, then it ends on its own (a loop
// whose flag is false) or on the first field it reads. The helper's two seams (the platform test and the system call)
// are replaced to observe the request on a host that is not an Apple platform.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;

public static class Program
{
    private const BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;

    // (assembly, type, method name or a part of a local function's name, thread)
    private static readonly (string Assembly, string Type, string Method, string Thread)[] Sites =
    {
        ("Ryujinx.Common", "Ryujinx.Common.PreciseSleep.NanosleepPool+NanosleepThread", "Loop", "Common.Nanosleep.N"),
        ("Ryujinx.HLE", "Ryujinx.HLE.HOS.Kernel.Threading.KThread", "ThreadStart", "guest and HLE service threads"),
        ("Ryujinx.HLE", "Ryujinx.HLE.HOS.Kernel.Common.KTimeManager", "WaitAndCheckScheduledObjects", "HLE.TimeManager"),
        ("Ryujinx.HLE", "Ryujinx.HLE.HOS.Kernel.KernelContext", "PreemptionThreadStart", "HLE.PreemptionThread"),
        ("Ryujinx.HLE", "Ryujinx.HLE.HOS.Services.SurfaceFlinger.SurfaceFlinger", "HandleComposition", "SurfaceFlinger.Composer"),
        ("Ryujinx.Audio", "Ryujinx.Audio.Renderer.Dsp.AudioProcessor", "Work", "AudioProcessor.Worker"),
        ("Ryujinx.Audio", "Ryujinx.Audio.Renderer.Server.AudioRendererManager", "SendCommands", "AudioRendererManager.Worker"),
        ("Ryujinx.Audio", "Ryujinx.Audio.AudioManager", "Update", "AudioManager.Worker"),
    };

    private static readonly ConcurrentQueue<(int Thread, uint Class, int Relative)> Requests = new();
    private static bool _apple;
    private static int _answer;
    private static Exception _fault;

    [DllImport("/usr/lib/libSystem.B.dylib", EntryPoint = "qos_class_self")]
    private static extern uint QosClassSelf();

    private static int Request(uint qosClass, int relativePriority)
    {
        Requests.Enqueue((Environment.CurrentManagedThreadId, qosClass, relativePriority));
        if (_fault != null) throw _fault;
        return _answer;
    }

    private static Assembly Load(string directory, string name) => Assembly.LoadFrom(Path.Combine(directory, name + ".dll"));

    private static MethodInfo Find(Type type, string name) =>
        type.GetMethods(Any).SingleOrDefault(method => method.Name == name) ??
        type.GetMethods(Any).SingleOrDefault(method => method.Name.Contains("g__" + name + "|"));

    // Runs `body` on its own named thread; returns the requests that thread made and how the body ended.
    private static Dictionary<string, object> OnThread(string name, Func<object> body)
    {
        string end = "timeout";
        object value = null;
        int id = 0;
        var thread = new Thread(() =>
        {
            id = Environment.CurrentManagedThreadId;
            try { value = body(); end = "returned"; }
            catch (TargetInvocationException error) { end = error.InnerException.GetType().Name; }
            catch (Exception error) { end = "fixture: " + error.GetType().Name; }
        }) { Name = name, IsBackground = true };
        int before = Requests.Count;
        thread.Start();
        thread.Join(20000);
        var made = Requests.Skip(before).ToArray();
        return new Dictionary<string, object>
        {
            ["end"] = end, ["value"] = value,
            ["requests"] = made.Select(request => new[] { (long)request.Class, request.Relative }).ToArray(),
            ["onItsOwnThread"] = made.All(request => request.Thread == id),
        };
    }

    public static int Main(string[] arguments)
    {
        string directory = arguments[0];
        var report = new Dictionary<string, object> { ["variant"] = arguments[1] };
        var assemblies = Sites.Select(site => site.Assembly).Distinct().ToDictionary(name => name, name => Load(directory, name));
        Type helper = assemblies["Ryujinx.Common"].GetType("Ryujinx.Common.HostThreadClass");
        Type journal = assemblies["Ryujinx.Common"].GetType("Ryujinx.Common.EmbeddedLaunchDiagnostics", true);
        report["helper"] = helper != null;

        FieldInfo platform = helper?.GetField("ApplePlatform", Any), system = helper?.GetField("SetClass", Any);
        MethodInfo raise = helper?.GetMethod("RaiseCurrentThread", Any);
        object ownPlatform = platform?.GetValue(null), ownSystem = system?.GetValue(null);
        void Seams(bool apple, int answer, Exception fault = null)
        {
            _apple = apple; _answer = answer; _fault = fault;
            platform?.SetValue(null, (Func<bool>)(() => _apple));
            system?.SetValue(null, (Func<uint, int, int>)Request);
        }
        int Recorded() // "hostThreadClass" records of the side's real journal
        {
            using var document = JsonDocument.Parse((byte[])journal.GetMethod("Snapshot").Invoke(null, null));
            return document.RootElement.GetProperty("events").EnumerateArray().Count(item => item.GetProperty("stage").GetString() == "hostThreadClass");
        }

        // --- Every raised thread's real body, on an Apple platform that grants the class ---
        var sites = new Dictionary<string, object>();
        Seams(apple: true, answer: 0);
        foreach (var site in Sites)
        {
            Type type = assemblies[site.Assembly].GetType(site.Type, true);
            MethodInfo method = Find(type, site.Method);
            if (method == null) { sites[site.Thread] = new Dictionary<string, object> { ["end"] = "method not found" }; continue; }
            object target = method.IsStatic ? null : RuntimeHelpers.GetUninitializedObject(type);
            var result = OnThread(site.Thread, () => method.Invoke(target, null));
            result["method"] = method.Name;
            sites[site.Thread] = result;
        }
        report["sites"] = sites;
        report["recordsAfterGrants"] = Recorded();

        if (helper != null)
        {
            // --- The helper alone ---
            report["granted"] = OnThread("granted", () => raise.Invoke(null, null));
            Seams(apple: false, answer: 0);
            report["notApple"] = OnThread("notApple", () => raise.Invoke(null, null));
            Seams(apple: true, answer: 1);
            report["refused"] = Enumerable.Range(0, 3).Select(index => OnThread("refused " + index, () => raise.Invoke(null, null))).ToArray();
            report["recordsAfterRefusals"] = Recorded();
            using (var document = JsonDocument.Parse((byte[])journal.GetMethod("Snapshot").Invoke(null, null)))
            {
                report["refusalRecords"] = document.RootElement.GetProperty("events").EnumerateArray()
                    .Where(item => item.GetProperty("stage").GetString() == "hostThreadClass")
                    .Select(item => item.GetProperty("status").GetString() + " " + item.GetProperty("nativeStatus").GetInt32() + ": " + item.GetProperty("diagnostic").GetString()).ToArray();
            }
            Seams(apple: true, answer: 0, fault: new DllNotFoundException("fixture"));
            report["libraryMissing"] = OnThread("libraryMissing", () => raise.Invoke(null, null));
            Seams(apple: true, answer: 0, fault: new EntryPointNotFoundException("fixture"));
            report["entryMissing"] = OnThread("entryMissing", () => raise.Invoke(null, null));

            // --- The engine's own seams on this host: nothing asked elsewhere; on macOS the thread's class is read back ---
            platform.SetValue(null, ownPlatform); system.SetValue(null, ownSystem);
            bool apple = OperatingSystem.IsMacOS();
            uint before = 0, after = 0;
            var own = OnThread("ownSeams", () =>
            {
                if (apple) before = QosClassSelf();
                object value = raise.Invoke(null, null);
                if (apple) after = QosClassSelf();
                return value;
            });
            own["applePlatform"] = apple; own["classBefore"] = before; own["classAfter"] = after;
            report["ownSeams"] = own;
        }

        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
