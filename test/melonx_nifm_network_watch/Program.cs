// Host fixture of adapt_nifm_network_watch: the production Ryujinx.HLE assembly of the control or of the candidate is
// loaded from the directory given as the first argument and driven by reflection (no source of it is compiled here).
// The session's reference chain is the production one: a real nifm IGeneralService, given a real ServerBase through
// IpcService.TrySetServer, whose _context is a real KernelContext whose Device is a real Switch. The server, kernel and
// Switch are uninitialized objects (no emulation runs): only who references whom is under test.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.NetworkInformation;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;

static class Program
{
    const BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    const int PayloadBytes = 8 * 1024 * 1024;
    static Assembly Hle, Common;
    static readonly ConditionalWeakTable<object, byte[]> Payloads = new();

    static Type T(string name) => Hle.GetType(name, throwOnError: true);
    static Type ServiceType => T("Ryujinx.HLE.HOS.Services.Nifm.StaticService.IGeneralService");
    static Type Watch => Hle.GetType("Ryujinx.HLE.HOS.Services.Nifm.StaticService.NetworkAddressWatch");

    static void SetField(object target, Type type, string name, object value) =>
        (type.GetField(name, Any) ?? throw new MissingFieldException(type.FullName, name)).SetValue(target, value);

    static object GetField(object target, Type type, string name) =>
        (type.GetField(name, Any) ?? throw new MissingFieldException(type.FullName, name)).GetValue(target);

    sealed class Session { public object Service, Server, Kernel, Device, Context; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static Session Create(int payloadBytes)
    {
        Type switchType = T("Ryujinx.HLE.Switch");
        object device = RuntimeHelpers.GetUninitializedObject(switchType);
        GC.SuppressFinalize(device);
        Type hacks = Common.GetType("Ryujinx.Common.Configuration.DirtyHacks", true);
        Type enabled = Common.GetType("Ryujinx.Common.Configuration.EnabledDirtyHack", true);
        SetField(device, switchType, "<DirtyHacks>k__BackingField", Activator.CreateInstance(hacks, new object[] { Array.CreateInstance(enabled, 0) }));
        Type configurationType = T("Ryujinx.HLE.HleConfiguration");
        object configuration = RuntimeHelpers.GetUninitializedObject(configurationType);
        configurationType.GetProperty("MultiplayerLanInterfaceId", Any).SetValue(configuration, "0");
        SetField(device, switchType, "<Configuration>k__BackingField", configuration);
        if (payloadBytes > 0) Payloads.Add(device, new byte[payloadBytes]);
        object context = Activator.CreateInstance(T("Ryujinx.HLE.HOS.ServiceCtx"), Any, null,
            new object[] { device, null, null, null, null, null, null, null }, null);
        Type kernelType = T("Ryujinx.HLE.HOS.Kernel.KernelContext");
        object kernel = RuntimeHelpers.GetUninitializedObject(kernelType);
        GC.SuppressFinalize(kernel);
        SetField(kernel, kernelType, "<Device>k__BackingField", device);
        Type serverType = T("Ryujinx.HLE.HOS.Services.ServerBase");
        object server = RuntimeHelpers.GetUninitializedObject(serverType);
        GC.SuppressFinalize(server);
        SetField(server, serverType, "_context", kernel);
        object service = Activator.CreateInstance(ServiceType, Any, null, new object[] { context }, null);
        bool set = (bool)T("Ryujinx.HLE.HOS.Services.IpcService").GetMethod("TrySetServer", Any).Invoke(service, new[] { server });
        if (!set || !ReferenceEquals(T("Ryujinx.HLE.HOS.Services.IpcService").GetProperty("Server", Any).GetValue(service), server))
            throw new InvalidOperationException("the service did not take its server");
        return new Session { Service = service, Server = server, Kernel = kernel, Device = device, Context = context };
    }

    // A session whose general service is never disposed (the guest closed its domain's session: ServerBase.DestroySession
    // disposes the root object only), or is disposed; then every reference this fixture holds is dropped.
    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference[] CreateAndAbandon(bool dispose, int payloadBytes)
    {
        Session s = Create(payloadBytes);
        if (dispose) ((IDisposable)s.Service).Dispose();
        return new[] { new WeakReference(s.Service), new WeakReference(s.Server), new WeakReference(s.Kernel), new WeakReference(s.Device) };
    }

    static void Collect()
    {
        for (int i = 0; i < 3; i++)
        {
            GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
            GC.WaitForPendingFinalizers();
        }
    }

    static int Alive(WeakReference[] parts) => parts.Count(p => p.IsAlive);

    static (object Properties, object Address) Read(Session s)
    {
        object pair = ServiceType.GetMethod("GetLocalInterface", Any).Invoke(s.Service, new[] { s.Context });
        return (pair.GetType().GetField("Item1").GetValue(pair), pair.GetType().GetField("Item2").GetValue(pair));
    }

    // What the runtime's event does when the network address changes: the control's handler of every subscribed service,
    // the candidate's one static handler.
    static void RaiseAddressChange(IEnumerable<Session> subscribed)
    {
        if (Watch != null)
        {
            Watch.GetMethod("OnAddressChanged", Any).Invoke(null, new object[] { null, EventArgs.Empty });
            return;
        }
        foreach (Session s in subscribed)
            ServiceType.GetMethod("LocalInterfaceCacheHandler", Any).Invoke(s.Service, new object[] { null, EventArgs.Empty });
    }

    static int Main(string[] args)
    {
        string directory = args[0];
        string mode = args.Length > 1 ? args[1] : "sessions";
        // A class library's output holds its project references, not its packages: those come from the restore cache the
        // build itself used.
        string packages = Environment.GetEnvironmentVariable("NUGET_PACKAGES") ??
            System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".nuget", "packages");
        AppDomain.CurrentDomain.AssemblyResolve += (_, request) =>
        {
            var name = new AssemblyName(request.Name);
            string local = System.IO.Path.Combine(directory, name.Name + ".dll");
            if (System.IO.File.Exists(local)) return Assembly.LoadFrom(local);
            if (!System.IO.Directory.Exists(packages)) return null;
            // The package's name need not be the assembly's: every package's lib folders are looked at; the requested
            // version first, then the newest target framework.
            string lib = System.IO.Path.DirectorySeparatorChar + "lib" + System.IO.Path.DirectorySeparatorChar;
            string found = System.IO.Directory.EnumerateDirectories(packages)
                .SelectMany(package => System.IO.Directory.EnumerateFiles(package, name.Name + ".dll", System.IO.SearchOption.AllDirectories))
                .Where(path => path.Contains(lib))
                .OrderByDescending(path => name.Version != null && AssemblyName.GetAssemblyName(path).Version == name.Version)
                .ThenByDescending(path => path, StringComparer.Ordinal)
                .FirstOrDefault();
            return found == null ? null : Assembly.LoadFrom(found);
        };
        Hle = Assembly.LoadFrom(System.IO.Path.Combine(directory, "Ryujinx.HLE.dll"));
        Common = Assembly.LoadFrom(System.IO.Path.Combine(directory, "Ryujinx.Common.dll"));
        var report = new Dictionary<string, object> { ["candidate"] = Watch != null, ["mode"] = mode };

        if (mode == "seam")
        {
            // Candidate only: how many times the process-wide event is subscribed, and what the handler holds.
            var handlers = new List<NetworkAddressChangedEventHandler>();
            Watch.GetField("Subscribe", Any).SetValue(null, (Action<NetworkAddressChangedEventHandler>)(handlers.Add));
            var kept = new List<Session>();
            for (int i = 0; i < 5; i++) kept.Add(Create(0));
            int before = (int)Watch.GetProperty("Version", Any).GetValue(null);
            handlers[0](null, EventArgs.Empty);
            report["subscriptions"] = handlers.Count;
            report["handlerTargetIsNull"] = handlers[0].Target == null;
            report["handlerIsStatic"] = handlers[0].Method.IsStatic;
            report["versionStep"] = (int)Watch.GetProperty("Version", Any).GetValue(null) - before;
            // A runtime that refuses the subscription fails the creation, as the control's constructor did, and the next
            // creation tries again.
            Watch.GetField("_subscribed", Any).SetValue(null, 0);
            int attempts = 0;
            Watch.GetField("Subscribe", Any).SetValue(null, (Action<NetworkAddressChangedEventHandler>)(_ => { if (attempts++ == 0) throw new PlatformNotSupportedException(); }));
            bool threw = false;
            try { Create(0); } catch (TargetInvocationException e) when (e.InnerException is PlatformNotSupportedException) { threw = true; }
            Create(0);
            report["refusedSubscriptionThrows"] = threw;
            report["subscriptionRetried"] = attempts == 2;
            GC.KeepAlive(kept);
            Console.WriteLine(JsonSerializer.Serialize(report));
            return 0;
        }

        // 1. A general service that is disposed releases its session.
        WeakReference[] disposed = CreateAndAbandon(dispose: true, 0);
        Collect();
        report["disposedSessionPartsAlive"] = Alive(disposed);

        // 2. One the guest left undisposed. Parts: service, server, kernel, Switch.
        long baseline = GC.GetTotalMemory(forceFullCollection: true);
        WeakReference[] abandoned = CreateAndAbandon(dispose: false, PayloadBytes);
        Collect();
        report["abandonedSessionPartsAlive"] = Alive(abandoned);
        report["abandonedSwitchAlive"] = abandoned[3].IsAlive;
        report["heapAfterOneBytes"] = GC.GetTotalMemory(forceFullCollection: true) - baseline;

        // 3. Ten more sessions in a row, as many game changes without restarting the application.
        var more = new List<WeakReference[]>();
        for (int i = 0; i < 10; i++)
        {
            more.Add(CreateAndAbandon(dispose: false, PayloadBytes));
            Collect();
        }
        report["sessionsCreated"] = 11;
        report["switchesAlive"] = more.Count(parts => parts[3].IsAlive) + (abandoned[3].IsAlive ? 1 : 0);
        report["heapAfterElevenBytes"] = GC.GetTotalMemory(forceFullCollection: true) - baseline;
        report["payloadBytes"] = PayloadBytes;

        // 4. The cached interface, as GetLocalInterface returns it to its callers. Two services exist when the address
        // changes (one read before and after, one read only after); a third is created after the change.
        bool available = NetworkInterface.GetIsNetworkAvailable();
        report["networkAvailable"] = available;
        NetworkInterface any = NetworkInterface.GetAllNetworkInterfaces().First(n => n.GetIPProperties().UnicastAddresses.Count > 0);
        object sentinelProperties = any.GetIPProperties();
        object sentinelAddress = any.GetIPProperties().UnicastAddresses[0];
        void Prime(Session s)
        {
            SetField(s.Service, ServiceType, "_targetPropertiesCache", sentinelProperties);
            SetField(s.Service, ServiceType, "_targetAddressInfoCache", sentinelAddress);
            SetField(s.Service, ServiceType, "_cacheChosenInterface", "0");
        }
        var observations = new List<string>();
        void Observe(string label, Session s)
        {
            (object properties, object address) = Read(s);
            observations.Add(label + ":" + (ReferenceEquals(properties, sentinelProperties) && ReferenceEquals(address, sentinelAddress) ? "cached" :
                properties == null && address == null ? "none" : "fresh"));
        }
        Session first = Create(0), second = Create(0);
        Prime(first); Prime(second);
        Observe("first before", first);
        Observe("first again", first);
        RaiseAddressChange(new[] { first, second });
        Observe("first after change", first);
        Observe("second after change", second);
        (object p1, object a1) = Read(first);
        (object p2, object a2) = Read(first);
        observations.Add("first refilled once:" + (ReferenceEquals(p1, p2) && ReferenceEquals(a1, a2)));
        Session third = Create(0);
        Prime(third);
        Observe("third created after the change", third);
        RaiseAddressChange(new[] { first, second, third });
        Observe("third after a second change", third);
        report["observations"] = observations;
        GC.KeepAlive(first); GC.KeepAlive(second); GC.KeepAlive(third);

        // 5. The journal's counts (candidate).
        Type diagnostics = Hle.GetType("Ryujinx.HLE.HOS.Services.Nifm.StaticService.NifmSessionDiagnostics");
        report["describe"] = diagnostics?.GetMethod("Describe", Any).Invoke(null, null) as string;
        report["diagnosticsIsPublic"] = diagnostics?.IsPublic ?? false;
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
